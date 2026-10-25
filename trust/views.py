"""
Trust views: disputes, ratings, messaging, risk assessment.
"""

import logging

from rest_framework import generics, permissions, status
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from trust.models import Dispute, Message, MessageThread, Rating, RiskAssessment
from trust.serializers import (
    DisputeCreateSerializer,
    DisputeSerializer,
    MessageSerializer,
    MessageThreadSerializer,
    RatingCreateSerializer,
    RatingSerializer,
    RiskAssessmentSerializer,
)

logger = logging.getLogger(__name__)


def _get_supplier_order(pk):
    from orders.models import SupplierOrder
    try:
        return SupplierOrder.objects.get(pk=pk)
    except SupplierOrder.DoesNotExist:
        raise NotFound(f"SupplierOrder {pk} not found.")


# ---------------------------------------------------------------------------
# Dispute views
# ---------------------------------------------------------------------------

class DisputeListCreateView(generics.ListCreateAPIView):
    """
    GET  /api/v1/trust/disputes/  — list disputes (buyer sees own, staff sees all)
    POST /api/v1/trust/disputes/  — open a dispute
    """
    permission_classes = [permissions.IsAuthenticated]

    def get_serializer_class(self):
        if self.request.method == "POST":
            return DisputeCreateSerializer
        return DisputeSerializer

    def get_queryset(self):
        user = self.request.user
        if user.is_staff:
            return Dispute.objects.select_related(
                "supplier_order", "opened_by", "resolved_by"
            ).all()
        # Buyer sees disputes for orders where they are a member
        company_ids = user.memberships.filter(status="active").values_list("company_id", flat=True)
        return Dispute.objects.filter(
            supplier_order__order__buyer_company_id__in=company_ids
        ).select_related("supplier_order", "opened_by", "resolved_by")

    def create(self, request, *args, **kwargs):
        serializer = DisputeCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        supplier_order = _get_supplier_order(data["supplier_order"])

        from trust.services import open_dispute
        try:
            dispute = open_dispute(
                supplier_order=supplier_order,
                opened_by=request.user,
                reason=data["reason"],
                description=data["description"],
            )
        except (ValueError, PermissionError) as exc:
            raise ValidationError(str(exc))

        return Response(
            DisputeSerializer(dispute, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )


class DisputeDetailView(generics.RetrieveUpdateAPIView):
    """
    GET   /api/v1/trust/disputes/{id}/
    PATCH /api/v1/trust/disputes/{id}/  — trusty can resolve
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = DisputeSerializer

    def get_queryset(self):
        user = self.request.user
        if user.is_staff:
            return Dispute.objects.all()
        company_ids = user.memberships.filter(status="active").values_list("company_id", flat=True)
        return Dispute.objects.filter(
            supplier_order__order__buyer_company_id__in=company_ids
        )

    def partial_update(self, request, *args, **kwargs):
        dispute = self.get_object()
        if not request.user.is_staff:
            raise PermissionDenied("Only staff can resolve disputes.")

        new_status = request.data.get("status")
        resolution_note = request.data.get("resolution_note", "")

        from trust.services import resolve_dispute
        try:
            dispute = resolve_dispute(
                dispute=dispute,
                resolved_by=request.user,
                status=new_status,
                resolution_note=resolution_note,
            )
        except ValueError as exc:
            raise ValidationError(str(exc))

        return Response(DisputeSerializer(dispute, context={"request": request}).data)


# ---------------------------------------------------------------------------
# Rating views
# ---------------------------------------------------------------------------

class RatingListCreateView(generics.ListCreateAPIView):
    """
    GET  /api/v1/trust/ratings/  — filter by ratee_company or supplier_order
    POST /api/v1/trust/ratings/  — submit a rating
    """
    permission_classes = [permissions.IsAuthenticated]

    def get_serializer_class(self):
        if self.request.method == "POST":
            return RatingCreateSerializer
        return RatingSerializer

    def get_queryset(self):
        qs = Rating.objects.select_related("rater_company", "ratee_company", "supplier_order")
        ratee_company = self.request.query_params.get("ratee_company")
        supplier_order = self.request.query_params.get("supplier_order")
        if ratee_company:
            qs = qs.filter(ratee_company_id=ratee_company)
        if supplier_order:
            qs = qs.filter(supplier_order_id=supplier_order)
        return qs

    def create(self, request, *args, **kwargs):
        serializer = RatingCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        supplier_order = _get_supplier_order(data["supplier_order"])

        # Rater company = first active membership company
        membership = request.user.memberships.filter(status="active").first()
        if not membership:
            raise ValidationError("User has no active company membership.")
        rater_company = membership.company

        from trust.services import submit_rating
        try:
            rating = submit_rating(
                supplier_order=supplier_order,
                rater_company=rater_company,
                direction=data["direction"],
                quality=data["quality"],
                communication=data["communication"],
                shipping=data["shipping"],
                documentation=data["documentation"],
                comment=data.get("comment", ""),
            )
        except ValueError as exc:
            raise ValidationError(str(exc))

        return Response(
            RatingSerializer(rating, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )


# ---------------------------------------------------------------------------
# MessageThread views
# ---------------------------------------------------------------------------

class MessageThreadListCreateView(generics.ListCreateAPIView):
    """
    GET  /api/v1/trust/threads/
    POST /api/v1/trust/threads/
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = MessageThreadSerializer

    def get_queryset(self):
        user = self.request.user
        if user.is_staff:
            return MessageThread.objects.all()
        company_ids = user.memberships.filter(status="active").values_list("company_id", flat=True)
        return MessageThread.objects.filter(
            models_Q_buyer_or_supplier(company_ids)
        )

    def create(self, request, *args, **kwargs):
        # Minimal creation: buyer_company, supplier_company required
        buyer_company_id = request.data.get("buyer_company")
        supplier_company_id = request.data.get("supplier_company")
        listing_id = request.data.get("listing")
        supplier_order_id = request.data.get("supplier_order")

        from accounts.models import Company
        try:
            buyer_company = Company.objects.get(pk=buyer_company_id)
            supplier_company = Company.objects.get(pk=supplier_company_id)
        except Company.DoesNotExist:
            raise ValidationError("Invalid buyer_company or supplier_company.")

        thread = MessageThread.objects.create(
            buyer_company=buyer_company,
            supplier_company=supplier_company,
            listing_id=listing_id,
            supplier_order_id=supplier_order_id,
        )
        return Response(
            MessageThreadSerializer(thread, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )


def models_Q_buyer_or_supplier(company_ids):
    from django.db.models import Q
    return Q(buyer_company_id__in=company_ids) | Q(supplier_company_id__in=company_ids)


class MessageThreadDetailView(generics.RetrieveAPIView):
    """
    GET /api/v1/trust/threads/{id}/
    Returns thread + approved messages (pending shown to staff).
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = MessageThreadSerializer

    def get_queryset(self):
        user = self.request.user
        if user.is_staff:
            return MessageThread.objects.all()
        company_ids = user.memberships.filter(status="active").values_list("company_id", flat=True)
        return MessageThread.objects.filter(
            models_Q_buyer_or_supplier(company_ids)
        )


class SendMessageView(APIView):
    """
    POST /api/v1/trust/threads/{pk}/messages/
    Creates Message with moderation_status=pending.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        try:
            thread = MessageThread.objects.get(pk=pk)
        except MessageThread.DoesNotExist:
            raise NotFound("Thread not found.")

        body = request.data.get("body", "").strip()
        if not body:
            raise ValidationError("body is required.")

        message = Message.objects.create(
            thread=thread,
            sender=request.user,
            body=body,
            moderation_status=Message.ModerationStatus.PENDING,
        )

        # Append chain event placeholder
        if thread.supplier_order_id:
            try:
                from trust.services import append_chain_event
                company_ids = request.user.memberships.filter(
                    status="active"
                ).values_list("company_id", flat=True)
                # Use supplier_company if sender is a supplier member
                supplier_company = thread.supplier_company
                if supplier_company.id in list(company_ids):
                    append_chain_event(
                        supplier_company=supplier_company,
                        event_type="bid_committed",  # TODO: wire correct event type
                        ref_type="message",
                        ref_id=str(message.id),
                        payload={"message_id": str(message.id), "thread_id": str(thread.id)},
                    )
            except Exception:
                pass  # Chain events must not block messaging

        return Response(
            MessageSerializer(message, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )


class ModerateMessageView(APIView):
    """
    POST /api/v1/trust/messages/{pk}/moderate/
    Staff only. Calls moderate_message().
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        if not request.user.is_staff:
            raise PermissionDenied("Only staff can moderate messages.")

        try:
            message = Message.objects.select_related("thread").get(pk=pk)
        except Message.DoesNotExist:
            raise NotFound("Message not found.")

        approved = request.data.get("approved")
        if approved is None:
            raise ValidationError("'approved' field is required (true/false).")

        flags = request.data.get("flags", {})

        from trust.services import moderate_message
        message = moderate_message(
            message=message,
            moderator=request.user,
            approved=bool(approved),
            flags=flags,
        )

        return Response(MessageSerializer(message, context={"request": request}).data)


# ---------------------------------------------------------------------------
# RiskAssessment view
# ---------------------------------------------------------------------------

class RiskAssessmentView(APIView):
    """
    GET  /api/v1/trust/risk/{supplier_order_id}/  — retrieve risk assessment
    POST /api/v1/trust/risk/{supplier_order_id}/  — trusty override tier
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, supplier_order_id):
        supplier_order = _get_supplier_order(supplier_order_id)
        try:
            assessment = supplier_order.risk_assessment
        except RiskAssessment.DoesNotExist:
            raise NotFound("No risk assessment found for this supplier order.")
        return Response(
            RiskAssessmentSerializer(assessment, context={"request": request}).data
        )

    def post(self, request, supplier_order_id):
        if not request.user.is_staff:
            raise PermissionDenied("Only staff can override risk tier.")

        supplier_order = _get_supplier_order(supplier_order_id)
        try:
            assessment = supplier_order.risk_assessment
        except RiskAssessment.DoesNotExist:
            raise NotFound("No risk assessment found for this supplier order.")

        override_tier = request.data.get("override_tier")
        override_reason = request.data.get("override_reason", "")

        valid_tiers = [t[0] for t in RiskAssessment.Tier.choices]
        if override_tier not in valid_tiers:
            raise ValidationError(f"override_tier must be one of: {valid_tiers}")

        assessment.override_tier = override_tier
        assessment.override_reason = override_reason
        assessment.overridden_by = request.user
        assessment.save(update_fields=["override_tier", "override_reason", "overridden_by"])

        return Response(RiskAssessmentSerializer(assessment, context={"request": request}).data)
