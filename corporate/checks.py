"""
Corporate middleware / hooks for fail-closed validation.
Called from payments/views.py and listings/views.py.
"""

import logging
from decimal import Decimal

from rest_framework.exceptions import ValidationError

logger = logging.getLogger(__name__)


def validate_checkout(order_data: dict, member) -> None:
    """
    Called before checkout in payments/views.py CheckoutView.
    Raises ValidationError if:
    1. member has an active OrderLimit and amount > max_order_amount
    2. member has an active Budget and spending + amount > budget
    3. member's ship_to address not in ShipToAssignment (if any assignments exist for this member)
    If budget/limit exceeded: create ApprovalRequest, raise ValidationError(
        'Budget exceeded. An approval request has been submitted.',
        code='approval_required'
    )
    FAIL CLOSED: any exception raises ValidationError('Budget check failed').
    """
    try:
        from corporate.models import OrderLimit, ShipToAssignment
        from corporate.services import check_budget, request_approval

        amount = Decimal(str(order_data.get("grand_total", "0.00")))
        ship_to_id = order_data.get("ship_to_id")

        # 1 & 2: Check order limit and budget
        allowed, reason = check_budget(member, amount)
        if not allowed:
            if reason in ("Exceeds order limit", "Exceeds monthly budget"):
                request_approval(
                    company=member.company,
                    requested_by=member.user,
                    subject_type="checkout",
                    amount=amount,
                )
                raise ValidationError(
                    "Budget exceeded. An approval request has been submitted.",
                    code="approval_required",
                )
            # fail-closed for any other reason
            raise ValidationError("Budget check failed.")

        # 3. Check ship-to address assignment (only if assignments exist for this member)
        if ship_to_id:
            assignments_exist = ShipToAssignment.objects.filter(member=member).exists()
            if assignments_exist:
                address_allowed = ShipToAssignment.objects.filter(
                    member=member,
                    address_id=ship_to_id,
                ).exists()
                if not address_allowed:
                    raise ValidationError(
                        "Shipping address is not permitted for this member.",
                        code="address_not_allowed",
                    )

    except ValidationError:
        raise
    except Exception as exc:
        logger.exception("validate_checkout: unexpected error for member=%s: %s", member, exc)
        raise ValidationError("Budget check failed.")


def validate_listing_publish(listing, member) -> None:
    """
    Called before listing publish.
    Checks if member requires approval for listing_publish.
    If an ApprovalRequest exists and is approved: allow.
    If none exists: create one and raise ValidationError('Approval required before publishing.').
    """
    try:
        from corporate.models import ApprovalRequest
        from corporate.services import request_approval

        # Check if there is an approved request for this listing
        approved = ApprovalRequest.objects.filter(
            listing=listing,
            requested_by=member.user,
            subject_type=ApprovalRequest.SubjectType.LISTING_PUBLISH,
            status=ApprovalRequest.Status.APPROVED,
        ).exists()

        if approved:
            return  # Allowed

        # Check if a pending request already exists
        pending = ApprovalRequest.objects.filter(
            listing=listing,
            requested_by=member.user,
            subject_type=ApprovalRequest.SubjectType.LISTING_PUBLISH,
            status=ApprovalRequest.Status.PENDING,
        ).exists()

        if not pending:
            request_approval(
                company=member.company,
                requested_by=member.user,
                subject_type=ApprovalRequest.SubjectType.LISTING_PUBLISH,
                listing=listing,
            )

        raise ValidationError(
            "Approval required before publishing.",
            code="approval_required",
        )

    except ValidationError:
        raise
    except Exception as exc:
        logger.exception(
            "validate_listing_publish: unexpected error for listing=%s member=%s: %s",
            listing, member, exc,
        )
        raise ValidationError("Approval check failed.")
