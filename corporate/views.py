"""
Corporate views.
"""

import csv
import logging
from datetime import date

from rest_framework import generics, status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import ApprovalRequest, Budget, Invitation, OrderLimit, ShipToAssignment
from .serializers import (
    ApprovalRequestSerializer,
    BudgetSerializer,
    InvitationSerializer,
    OrderLimitSerializer,
    ShipToAssignmentSerializer,
    SpendingReportSerializer,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Permission helpers
# ---------------------------------------------------------------------------

def _get_active_member(user, company=None):
    """Return the first active CompanyMember for this user (optionally filtered by company)."""
    qs = user.memberships.filter(status="active")
    if company:
        qs = qs.filter(company=company)
    return qs.select_related("company").first()


def _require_roles(member, roles):
    if member is None or member.role not in roles:
        raise PermissionDenied("Insufficient permissions.")


OWNER_MANAGER_FINANCE = ["owner", "manager", "finance"]
OWNER_MANAGER = ["owner", "manager"]
OWNER_FINANCE = ["owner", "finance"]


# ---------------------------------------------------------------------------
# InviteMemberView
# ---------------------------------------------------------------------------

class InviteMemberView(APIView):
    """POST /api/v1/corporate/invite/"""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        from .services import invite_member

        member = _get_active_member(request.user)
        if member is None:
            return Response({"error": "No active company membership."}, status=status.HTTP_400_BAD_REQUEST)

        _require_roles(member, OWNER_MANAGER_FINANCE)

        email = request.data.get("email", "").strip().lower()
        role = request.data.get("role", "")
        if not email or not role:
            return Response({"error": "email and role are required."}, status=status.HTTP_400_BAD_REQUEST)

        if role not in [r[0] for r in Invitation.Role.choices]:
            return Response({"error": f"Invalid role '{role}'."}, status=status.HTTP_400_BAD_REQUEST)

        raw_token, invitation = invite_member(
            company=member.company,
            email=email,
            role=role,
            invited_by=request.user,
        )

        return Response(
            {"invitation_id": str(invitation.id), "expires_at": invitation.expires_at},
            status=status.HTTP_201_CREATED,
        )


# ---------------------------------------------------------------------------
# AcceptInvitationView
# ---------------------------------------------------------------------------

class AcceptInvitationView(APIView):
    """POST /api/v1/corporate/accept-invitation/ — no auth required"""
    permission_classes = [AllowAny]

    def post(self, request):
        from .services import accept_invitation

        token = request.data.get("token", "").strip()
        if not token:
            return Response({"error": "token is required."}, status=status.HTTP_400_BAD_REQUEST)

        if not request.user or not request.user.is_authenticated:
            return Response(
                {"error": "Authentication required to accept an invitation."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        try:
            member = accept_invitation(token=token, user=request.user)
        except ValidationError as exc:
            return Response({"error": exc.detail}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            {"company_name": str(member.company), "role": member.role},
            status=status.HTTP_200_OK,
        )


# ---------------------------------------------------------------------------
# MemberListView
# ---------------------------------------------------------------------------

class MemberListView(generics.ListAPIView):
    """GET /api/v1/corporate/members/"""
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        from accounts.models import CompanyMember

        member = _get_active_member(self.request.user)
        if member is None:
            return CompanyMember.objects.none()
        return CompanyMember.objects.filter(
            company=member.company
        ).select_related("user", "company")

    def list(self, request, *args, **kwargs):
        from accounts.models import CompanyMember

        qs = self.get_queryset()
        data = [
            {
                "id": str(m.id),
                "user_id": str(m.user.id),
                "user_name": m.user.full_name,
                "email": m.user.email,
                "role": m.role,
                "status": m.status,
                "created_at": m.created_at,
            }
            for m in qs
        ]
        return Response(data)


# ---------------------------------------------------------------------------
# SuspendMemberView
# ---------------------------------------------------------------------------

class SuspendMemberView(APIView):
    """POST /api/v1/corporate/members/{id}/suspend/"""
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        from accounts.models import CompanyMember

        acting_member = _get_active_member(request.user)
        if acting_member is None:
            return Response({"error": "No active company membership."}, status=status.HTTP_400_BAD_REQUEST)

        _require_roles(acting_member, OWNER_MANAGER)

        try:
            target = CompanyMember.objects.get(id=pk, company=acting_member.company)
        except CompanyMember.DoesNotExist:
            return Response({"error": "Member not found."}, status=status.HTTP_404_NOT_FOUND)

        target.status = CompanyMember.Status.SUSPENDED
        target.save(update_fields=["status", "updated_at"])
        return Response({"status": "suspended"})


# ---------------------------------------------------------------------------
# BudgetListCreateView
# ---------------------------------------------------------------------------

class BudgetListCreateView(generics.ListCreateAPIView):
    """GET/POST /api/v1/corporate/budgets/"""
    serializer_class = BudgetSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        member = _get_active_member(self.request.user)
        if member is None:
            return Budget.objects.none()
        return Budget.objects.filter(
            member__company=member.company
        ).select_related("member__user")

    def create(self, request, *args, **kwargs):
        member = _get_active_member(request.user)
        if member is None:
            return Response({"error": "No active company membership."}, status=status.HTTP_400_BAD_REQUEST)

        _require_roles(member, OWNER_FINANCE)
        return super().create(request, *args, **kwargs)


# ---------------------------------------------------------------------------
# OrderLimitView
# ---------------------------------------------------------------------------

class OrderLimitView(APIView):
    """GET/PUT /api/v1/corporate/limits/{member_id}/"""
    permission_classes = [IsAuthenticated]

    def _get_target_member(self, request, member_id):
        from accounts.models import CompanyMember

        acting = _get_active_member(request.user)
        if acting is None:
            return None, None
        try:
            target = CompanyMember.objects.get(id=member_id, company=acting.company)
        except CompanyMember.DoesNotExist:
            return acting, None
        return acting, target

    def get(self, request, member_id):
        acting, target = self._get_target_member(request, member_id)
        if acting is None:
            return Response({"error": "No active company membership."}, status=status.HTTP_400_BAD_REQUEST)
        if target is None:
            return Response({"error": "Member not found."}, status=status.HTTP_404_NOT_FOUND)

        try:
            limit = OrderLimit.objects.get(member=target)
            return Response(OrderLimitSerializer(limit).data)
        except OrderLimit.DoesNotExist:
            return Response({}, status=status.HTTP_200_OK)

    def put(self, request, member_id):
        acting, target = self._get_target_member(request, member_id)
        if acting is None:
            return Response({"error": "No active company membership."}, status=status.HTTP_400_BAD_REQUEST)
        if target is None:
            return Response({"error": "Member not found."}, status=status.HTTP_404_NOT_FOUND)

        _require_roles(acting, OWNER_FINANCE)

        try:
            limit = OrderLimit.objects.get(member=target)
            serializer = OrderLimitSerializer(limit, data=request.data, partial=True)
        except OrderLimit.DoesNotExist:
            data = dict(request.data)
            data["member"] = str(target.id)
            serializer = OrderLimitSerializer(data=data)

        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


# ---------------------------------------------------------------------------
# ApprovalRequestListView
# ---------------------------------------------------------------------------

class ApprovalRequestListView(generics.ListAPIView):
    """GET /api/v1/corporate/approvals/"""
    serializer_class = ApprovalRequestSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        member = _get_active_member(self.request.user)
        if member is None:
            return ApprovalRequest.objects.none()

        qs = ApprovalRequest.objects.filter(
            company=member.company,
            status=ApprovalRequest.Status.PENDING,
        ).select_related("requested_by", "approver", "listing", "order")

        if member.role not in OWNER_MANAGER_FINANCE:
            # Regular members see only their own requests
            qs = qs.filter(requested_by=self.request.user)

        return qs


# ---------------------------------------------------------------------------
# ApprovalDecideView
# ---------------------------------------------------------------------------

class ApprovalDecideView(APIView):
    """POST /api/v1/corporate/approvals/{id}/decide/"""
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        from .services import decide_approval

        member = _get_active_member(request.user)
        if member is None:
            return Response({"error": "No active company membership."}, status=status.HTTP_400_BAD_REQUEST)

        _require_roles(member, OWNER_MANAGER_FINANCE)

        try:
            approval = ApprovalRequest.objects.get(id=pk, company=member.company)
        except ApprovalRequest.DoesNotExist:
            return Response({"error": "Approval request not found."}, status=status.HTTP_404_NOT_FOUND)

        if approval.status != ApprovalRequest.Status.PENDING:
            return Response({"error": "Approval request is not pending."}, status=status.HTTP_400_BAD_REQUEST)

        approved = request.data.get("approved")
        if approved is None:
            return Response({"error": "'approved' is required."}, status=status.HTTP_400_BAD_REQUEST)

        note = request.data.get("note", "")
        result = decide_approval(approval, approver=request.user, approved=bool(approved), note=note)
        return Response(ApprovalRequestSerializer(result).data)


# ---------------------------------------------------------------------------
# SpendingReportView
# ---------------------------------------------------------------------------

class SpendingReportView(APIView):
    """GET /api/v1/corporate/spending/?from=&to=  (add ?format=csv for CSV export)"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from .services import get_spending_report

        member = _get_active_member(request.user)
        if member is None:
            return Response({"error": "No active company membership."}, status=status.HTTP_400_BAD_REQUEST)

        _require_roles(member, OWNER_FINANCE)

        from_str = request.query_params.get("from", "")
        to_str = request.query_params.get("to", "")
        fmt = request.query_params.get("format", "")

        try:
            from_date = date.fromisoformat(from_str) if from_str else date.today().replace(day=1)
            to_date = date.fromisoformat(to_str) if to_str else date.today()
        except ValueError:
            return Response({"error": "Invalid date format. Use YYYY-MM-DD."}, status=status.HTTP_400_BAD_REQUEST)

        report = get_spending_report(company=member.company, from_date=from_date, to_date=to_date)

        if fmt == "csv":
            from django.http import HttpResponse

            response = HttpResponse(content_type="text/csv")
            response["Content-Disposition"] = 'attachment; filename="spending_report.csv"'
            writer = csv.DictWriter(
                response,
                fieldnames=["member_name", "role", "order_count", "total_spent", "currency"],
            )
            writer.writeheader()
            for row in report:
                writer.writerow(row)
            return response

        serializer = SpendingReportSerializer(report, many=True)
        return Response(serializer.data)


# ---------------------------------------------------------------------------
# ShipToAssignmentListCreateView
# ---------------------------------------------------------------------------

class ShipToAssignmentListCreateView(generics.ListCreateAPIView):
    """GET/POST /api/v1/corporate/ship-to/"""
    serializer_class = ShipToAssignmentSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        member = _get_active_member(self.request.user)
        if member is None:
            return ShipToAssignment.objects.none()
        return ShipToAssignment.objects.filter(
            member__company=member.company
        ).select_related("member__user", "address")

    def create(self, request, *args, **kwargs):
        member = _get_active_member(request.user)
        if member is None:
            return Response({"error": "No active company membership."}, status=status.HTTP_400_BAD_REQUEST)
        _require_roles(member, OWNER_MANAGER_FINANCE)
        return super().create(request, *args, **kwargs)


# ---------------------------------------------------------------------------
# ShipToAssignmentDeleteView
# ---------------------------------------------------------------------------

class ShipToAssignmentDeleteView(generics.DestroyAPIView):
    """DELETE /api/v1/corporate/ship-to/{id}/"""
    serializer_class = ShipToAssignmentSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        member = _get_active_member(self.request.user)
        if member is None:
            return ShipToAssignment.objects.none()
        return ShipToAssignment.objects.filter(member__company=member.company)

    def destroy(self, request, *args, **kwargs):
        member = _get_active_member(request.user)
        if member is None:
            return Response({"error": "No active company membership."}, status=status.HTTP_400_BAD_REQUEST)
        _require_roles(member, OWNER_MANAGER_FINANCE)
        return super().destroy(request, *args, **kwargs)
