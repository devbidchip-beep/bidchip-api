"""
Corporate services: invite_member, accept_invitation, check_budget,
request_approval, decide_approval, get_spending_report.
"""

import hashlib
import logging
import secrets
from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def invite_member(company, email: str, role: str, invited_by) -> tuple:
    """
    Creates an Invitation for a new company member.
    - Generates a secure random token (secrets.token_urlsafe(32))
    - Stores token_hash = SHA-256(token)
    - Sets expires_at = now() + 7 days
    - Sends 'corporate_invitation' notification (email with accept link)
    - Returns (raw_token, invitation) — raw_token shown once, then discarded
    """
    from corporate.models import Invitation
    from notify.service import notify

    raw_token = secrets.token_urlsafe(32)
    token_hash = _hash_token(raw_token)
    expires_at = timezone.now() + timedelta(days=7)

    invitation = Invitation.objects.create(
        company=company,
        email=email.lower(),
        role=role,
        token_hash=token_hash,
        invited_by=invited_by,
        expires_at=expires_at,
    )

    notify(
        user=invited_by,
        template_key="corporate_invitation",
        context={
            "company_name": str(company),
            "email": email.lower(),
            "role": role,
            "token": raw_token,
        },
    )

    return raw_token, invitation


def accept_invitation(token: str, user):
    """
    Accepts an invitation.
    - Hash the token, look up Invitation by token_hash
    - Check not expired and not already accepted
    - Create CompanyMember(user, company, role)
    - Set invitation.accepted_at = now()
    - Returns CompanyMember
    """
    from accounts.models import CompanyMember
    from corporate.models import Invitation

    token_hash = _hash_token(token)

    try:
        invitation = Invitation.objects.get(token_hash=token_hash)
    except Invitation.DoesNotExist:
        from rest_framework.exceptions import ValidationError
        raise ValidationError("Invalid or expired invitation token.")

    now = timezone.now()
    if invitation.expires_at < now:
        from rest_framework.exceptions import ValidationError
        raise ValidationError("Invitation has expired.")

    if invitation.accepted_at is not None:
        from rest_framework.exceptions import ValidationError
        raise ValidationError("Invitation has already been accepted.")

    with transaction.atomic():
        member, _ = CompanyMember.objects.get_or_create(
            user=user,
            company=invitation.company,
            defaults={"role": invitation.role},
        )
        invitation.accepted_at = now
        invitation.save(update_fields=["accepted_at"])

    return member


def check_budget(member, amount: Decimal) -> tuple:
    """
    Checks whether a member can spend `amount` on a new order.
    FAIL CLOSED: any error returns (False, 'Budget check failed').

    Steps:
    1. Get OrderLimit for member; if max_order_amount < amount → (False, 'Exceeds order limit')
    2. Get current period Budget: period_start = first day of current month
    3. Sum all paid orders by this member this period
    4. If sum + amount > budget.amount → (False, 'Exceeds monthly budget')
    5. If no budget set → (True, 'No budget set')
    Returns (True, 'OK') if allowed.
    """
    try:
        from django.db.models import Sum

        from corporate.models import Budget, OrderLimit
        from orders.models import Order

        # 1. Check per-order limit
        try:
            order_limit = OrderLimit.objects.get(member=member)
            if order_limit.max_order_amount < amount:
                return False, "Exceeds order limit"
        except OrderLimit.DoesNotExist:
            pass  # No limit set — allow

        # 2. Get current period budget
        today = timezone.now().date()
        period_start = today.replace(day=1)

        try:
            budget = Budget.objects.get(member=member, period_start=period_start)
        except Budget.DoesNotExist:
            return True, "No budget set"

        # 3. Sum paid orders by this member this period
        period_start_dt = timezone.datetime(
            period_start.year, period_start.month, period_start.day,
            tzinfo=timezone.utc,
        )
        period_end = timezone.now()

        spent = (
            Order.objects.filter(
                placed_by=member.user,
                buyer_company=member.company,
                paid_at__gte=period_start_dt,
                paid_at__lte=period_end,
            ).exclude(
                status__in=[Order.Status.CANCELLED, Order.Status.REFUNDED]
            ).aggregate(total=Sum("grand_total"))["total"]
            or Decimal("0.00")
        )

        # 4. Check if adding this amount exceeds the budget
        if spent + amount > budget.amount:
            return False, "Exceeds monthly budget"

        return True, "OK"

    except Exception as exc:
        logger.exception("check_budget: unexpected error for member=%s amount=%s: %s", member, amount, exc)
        return False, "Budget check failed"


def request_approval(company, requested_by, subject_type: str,
                     listing=None, order=None, amount=None):
    """
    Creates an ApprovalRequest when a member hits a limit.
    Notifies all manager/owner/finance members of the company.
    Returns ApprovalRequest.
    """
    from accounts.models import CompanyMember
    from corporate.models import ApprovalRequest
    from notify.service import notify

    approval = ApprovalRequest.objects.create(
        company=company,
        requested_by=requested_by,
        subject_type=subject_type,
        listing=listing,
        order=order,
        amount=amount,
        status=ApprovalRequest.Status.PENDING,
    )

    # Notify all manager/owner/finance members
    notify_roles = [
        CompanyMember.Role.MANAGER,
        CompanyMember.Role.OWNER,
        CompanyMember.Role.FINANCE,
    ]
    managers = CompanyMember.objects.filter(
        company=company,
        role__in=notify_roles,
        status=CompanyMember.Status.ACTIVE,
    ).select_related("user")

    for mgr_member in managers:
        notify(
            user=mgr_member.user,
            template_key="approval_requested",
            context={
                "subject_type": subject_type,
                "member_name": requested_by.full_name,
                "approval_id": str(approval.id),
                "amount": str(amount) if amount else "",
            },
        )

    return approval


def decide_approval(approval_request, approver, approved: bool, note=""):
    """
    Manager/owner/finance approves or rejects.
    Sets status, approver, decided_at, note.
    Notifies the requester.
    Returns updated ApprovalRequest.
    """
    from corporate.models import ApprovalRequest
    from notify.service import notify

    approval_request.status = (
        ApprovalRequest.Status.APPROVED if approved else ApprovalRequest.Status.REJECTED
    )
    approval_request.approver = approver
    approval_request.decided_at = timezone.now()
    approval_request.note = note
    approval_request.save(update_fields=["status", "approver", "decided_at", "note", "updated_at"])

    notify(
        user=approval_request.requested_by,
        template_key="approval_decided",
        context={
            "status": approval_request.status,
            "subject_type": approval_request.subject_type,
            "approver_name": approver.full_name,
            "note": note,
        },
    )

    return approval_request


def get_spending_report(company, from_date, to_date) -> list:
    """
    Returns spending per member for the given date range.
    [{ member_name, role, order_count, total_spent, currency }]
    Queries orders.Order where buyer_company=company, paid_at range.
    """
    from accounts.models import CompanyMember
    from django.db.models import Count, Sum
    from orders.models import Order

    members = CompanyMember.objects.filter(
        company=company,
        status=CompanyMember.Status.ACTIVE,
    ).select_related("user")

    report = []
    for member in members:
        qs = Order.objects.filter(
            buyer_company=company,
            placed_by=member.user,
            paid_at__date__gte=from_date,
            paid_at__date__lte=to_date,
        ).exclude(status__in=[Order.Status.CANCELLED, Order.Status.REFUNDED])

        aggregated = qs.aggregate(
            order_count=Count("id"),
            total_spent=Sum("grand_total"),
        )
        report.append({
            "member_name": member.user.full_name,
            "role": member.role,
            "order_count": aggregated["order_count"] or 0,
            "total_spent": aggregated["total_spent"] or Decimal("0.00"),
            "currency": "USD",
        })

    return report
