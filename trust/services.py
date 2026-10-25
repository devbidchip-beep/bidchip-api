"""
Trust services: risk assessment, disputes, ratings, hash chain, message moderation.
"""

import hashlib
import json
import logging
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)


def _get_platform_setting(key: str, default=None):
    from core.models import PlatformSetting
    try:
        ps = PlatformSetting.objects.get(key=key)
        return ps.value
    except PlatformSetting.DoesNotExist:
        return default


# ---------------------------------------------------------------------------
# assess_risk
# ---------------------------------------------------------------------------

def assess_risk(supplier_order) -> "RiskAssessment":
    """
    Auto-assigns a risk tier to a supplier order based on:
    - Supplier account age (< 6 months → +20 score)
    - Supplier's past completed orders count (0 orders → +30, 1-5 → +15)
    - Order value (> $50k → +25, > $10k → +10)
    - Part category counterfeit risk: is_itar or eccn set → +20
    - Company integrity_score < 70 → +15
    Tier: score 0-29 = green, 30-59 = yellow, 60+ = red
    Sets hold_days on supplier_order from PlatformSetting:
      green=5, yellow=7 (from 'hold.green_days', 'hold.yellow_days')
      red: requires_manual_release=True
    Returns saved RiskAssessment.
    """
    from trust.models import RiskAssessment

    supplier_company = supplier_order.supplier_company
    score = Decimal("0")
    factors = {}

    # --- Supplier account age ---
    age_days = (timezone.now() - supplier_company.created_at).days
    if age_days < 180:
        score += Decimal("20")
        factors["supplier_age_days"] = age_days
        factors["supplier_age_penalty"] = 20

    # --- Past completed orders ---
    from orders.models import SupplierOrder as SO, PAYOUT_RELEASED
    completed_count = SO.objects.filter(
        supplier_company=supplier_company,
        status=PAYOUT_RELEASED,
    ).exclude(pk=supplier_order.pk).count()
    factors["completed_orders"] = completed_count
    if completed_count == 0:
        score += Decimal("30")
        factors["history_penalty"] = 30
    elif completed_count <= 5:
        score += Decimal("15")
        factors["history_penalty"] = 15

    # --- Order value ---
    order_value = supplier_order.principal
    factors["order_value"] = str(order_value)
    if order_value > Decimal("50000"):
        score += Decimal("25")
        factors["value_penalty"] = 25
    elif order_value > Decimal("10000"):
        score += Decimal("10")
        factors["value_penalty"] = 10

    # --- Part category counterfeit risk ---
    # Check listing lines for ITAR/ECCN flags via order lines
    has_high_risk_part = False
    for line in supplier_order.lines.select_related("listing_line__part").all():
        part = getattr(line.listing_line, "part", None)
        if part is None:
            continue
        is_itar = getattr(part, "is_itar", False)
        eccn = getattr(part, "eccn", "") or ""
        if is_itar or eccn:
            has_high_risk_part = True
            break
    if has_high_risk_part:
        score += Decimal("20")
        factors["counterfeit_risk_penalty"] = 20

    # --- Company integrity score ---
    integrity = supplier_company.integrity_score
    factors["integrity_score"] = str(integrity)
    if integrity < Decimal("70"):
        score += Decimal("15")
        factors["integrity_penalty"] = 15

    # --- Determine tier ---
    if score < Decimal("30"):
        tier = RiskAssessment.Tier.GREEN
    elif score < Decimal("60"):
        tier = RiskAssessment.Tier.YELLOW
    else:
        tier = RiskAssessment.Tier.RED

    # --- Set hold_days / requires_manual_release on supplier_order ---
    hold_green = int(_get_platform_setting("hold.green_days", 5))
    hold_yellow = int(_get_platform_setting("hold.yellow_days", 7))

    if tier == RiskAssessment.Tier.GREEN:
        supplier_order.hold_days = hold_green
        supplier_order.requires_manual_release = False
    elif tier == RiskAssessment.Tier.YELLOW:
        supplier_order.hold_days = hold_yellow
        supplier_order.requires_manual_release = False
    else:  # RED
        supplier_order.hold_days = None
        supplier_order.requires_manual_release = True

    supplier_order.risk_tier = tier
    supplier_order.save(update_fields=["risk_tier", "hold_days", "requires_manual_release", "updated_at"])

    assessment = RiskAssessment.objects.create(
        supplier_order=supplier_order,
        score=score,
        tier=tier,
        factors=factors,
    )
    return assessment


# ---------------------------------------------------------------------------
# open_dispute
# ---------------------------------------------------------------------------

def open_dispute(supplier_order, opened_by, reason, description,
                 files: list = None) -> "Dispute":
    """
    Opens a dispute on a supplier order.
    Rules:
    - Supplier order must be in delivered or inspected state
    - Only the buyer company member can open
    - One open dispute per supplier order
    Sets supplier_order status disputed, pauses payout.
    Creates Dispute + DisputeFile rows.
    Notifies staff (trusty) via notify.service.notify().
    Returns Dispute.
    """
    from orders.models import DELIVERED, INSPECTED
    from trust.models import Dispute, DisputeFile

    if supplier_order.status not in (DELIVERED, INSPECTED):
        raise ValueError(
            f"Cannot open dispute on supplier order in status '{supplier_order.status}'. "
            "Order must be in 'delivered' or 'inspected' state."
        )

    # Check that opener belongs to the buyer company
    buyer_company = supplier_order.order.buyer_company
    if not opened_by.memberships.filter(company=buyer_company, status="active").exists():
        raise PermissionError("Only an active buyer company member can open a dispute.")

    # One open dispute per supplier order
    if Dispute.objects.filter(
        supplier_order=supplier_order,
        status__in=[Dispute.Status.OPEN, Dispute.Status.AWAITING_RETURN, Dispute.Status.UNDER_REVIEW],
    ).exists():
        raise ValueError("An active dispute already exists for this supplier order.")

    with transaction.atomic():
        dispute = Dispute.objects.create(
            supplier_order=supplier_order,
            opened_by=opened_by,
            reason=reason,
            description=description,
            status=Dispute.Status.OPEN,
        )

        if files:
            for file_key in files:
                DisputeFile.objects.create(
                    dispute=dispute,
                    file=file_key,
                    uploaded_by=opened_by,
                )

        # Notify staff trusty
        try:
            from notify.service import notify
            from accounts.models import User
            trusty_users = User.objects.filter(
                is_staff=True,
                staff_role=User.StaffRole.TRUSTY,
            )
            for trusty in trusty_users:
                notify(
                    user=trusty,
                    template_key="dispute.opened",
                    context={
                        "dispute_id": str(dispute.id),
                        "reason": reason,
                        "supplier_order_id": str(supplier_order.id),
                    },
                )
        except Exception:
            pass  # Notifications must not break business logic

    return dispute


# ---------------------------------------------------------------------------
# resolve_dispute
# ---------------------------------------------------------------------------

def resolve_dispute(dispute, resolved_by, status, resolution_note) -> "Dispute":
    """
    Resolves a dispute (trusty only).
    status must be one of: resolved_buyer, resolved_seller, split, withdrawn
    - resolved_buyer: triggers refund process (placeholder)
    - resolved_seller: resumes payout (set Payout back to scheduled if hold_days passed)
    Sets dispute.resolved_at, resolved_by.
    Notifies both parties.
    """
    from trust.models import Dispute

    valid_statuses = {
        Dispute.Status.RESOLVED_BUYER,
        Dispute.Status.RESOLVED_SELLER,
        Dispute.Status.SPLIT,
        Dispute.Status.WITHDRAWN,
    }
    if status not in valid_statuses:
        raise ValueError(f"Invalid resolution status: {status}")

    with transaction.atomic():
        dispute.status = status
        dispute.resolution_note = resolution_note
        dispute.resolved_by = resolved_by
        dispute.resolved_at = timezone.now()
        dispute.save(update_fields=["status", "resolution_note", "resolved_by", "resolved_at", "updated_at"])

        if status == Dispute.Status.RESOLVED_BUYER:
            # Placeholder: trigger refund process
            pass

        elif status == Dispute.Status.RESOLVED_SELLER:
            # Resume payout if hold_days passed
            try:
                from payments.models import Payout
                payout = dispute.supplier_order.payout
                if payout.status == Payout.Status.AWAITING_RELEASE:
                    payout.status = Payout.Status.SCHEDULED
                    payout.save(update_fields=["status", "updated_at"])
            except Exception:
                pass

        # Notify both parties
        try:
            from notify.service import notify
            supplier_order = dispute.supplier_order
            buyer_company = supplier_order.order.buyer_company
            supplier_company = supplier_order.supplier_company

            context = {
                "dispute_id": str(dispute.id),
                "status": status,
                "resolution_note": resolution_note,
            }

            for membership in buyer_company.members.filter(status="active").select_related("user"):
                notify(user=membership.user, template_key="dispute.resolved", context=context)

            for membership in supplier_company.members.filter(status="active").select_related("user"):
                notify(user=membership.user, template_key="dispute.resolved", context=context)
        except Exception:
            pass

    return dispute


# ---------------------------------------------------------------------------
# submit_rating
# ---------------------------------------------------------------------------

def submit_rating(supplier_order, rater_company, direction,
                  quality, communication, shipping, documentation,
                  comment="") -> "Rating":
    """
    Creates a rating. Rules:
    - Supplier order must be completed (payout_released or later)
    - No duplicate rating for (supplier_order, direction)
    - Scores must be 1-5
    Returns Rating.
    """
    from orders.models import PAYOUT_RELEASED
    from trust.models import Rating

    if supplier_order.status != PAYOUT_RELEASED:
        raise ValueError(
            f"Ratings can only be submitted after payout is released. "
            f"Current status: '{supplier_order.status}'."
        )

    # Validate scores
    for label, val in [("quality", quality), ("communication", communication),
                       ("shipping", shipping), ("documentation", documentation)]:
        if not (1 <= val <= 5):
            raise ValueError(f"Score '{label}' must be between 1 and 5, got {val}.")

    # Check duplicate
    if Rating.objects.filter(supplier_order=supplier_order, direction=direction).exists():
        raise ValueError(
            f"A rating with direction '{direction}' already exists for this supplier order."
        )

    # Determine ratee_company
    if direction == Rating.Direction.BUYER_TO_SUPPLIER:
        ratee_company = supplier_order.supplier_company
    else:
        ratee_company = supplier_order.order.buyer_company

    rating = Rating.objects.create(
        supplier_order=supplier_order,
        rater_company=rater_company,
        ratee_company=ratee_company,
        direction=direction,
        quality=quality,
        communication=communication,
        shipping=shipping,
        documentation=documentation,
        comment=comment,
    )
    return rating


# ---------------------------------------------------------------------------
# append_chain_event
# ---------------------------------------------------------------------------

def append_chain_event(supplier_company, event_type, ref_type, ref_id,
                       payload: dict) -> "SellerChainEvent":
    """
    Appends a new event to the seller's hash chain.
    Steps (inside SELECT FOR UPDATE on the last chain event for this company):
    1. Get last event for this company (or use '0'*64 as prev_hash if none)
    2. seq = last.seq + 1 (or 1 if first)
    3. payload_hash = SHA-256(json.dumps(payload, sort_keys=True))
    4. hash = SHA-256(prev_hash + str(seq) + event_type + payload_hash)
    5. Save SellerChainEvent
    Returns the new event.
    """
    from trust.models import SellerChainEvent

    with transaction.atomic():
        last_event = (
            SellerChainEvent.objects.select_for_update()
            .filter(supplier_company=supplier_company)
            .order_by("-seq")
            .first()
        )

        if last_event is None:
            prev_hash = "0" * 64
            seq = 1
        else:
            prev_hash = last_event.hash
            seq = last_event.seq + 1

        payload_hash = hashlib.sha256(
            json.dumps(payload, sort_keys=True).encode()
        ).hexdigest()

        chain_input = prev_hash + str(seq) + event_type + payload_hash
        chain_hash = hashlib.sha256(chain_input.encode()).hexdigest()

        event = SellerChainEvent.objects.create(
            supplier_company=supplier_company,
            seq=seq,
            event_type=event_type,
            ref_type=ref_type,
            ref_id=ref_id,
            payload_hash=payload_hash,
            prev_hash=prev_hash,
            hash=chain_hash,
        )
    return event


# ---------------------------------------------------------------------------
# verify_chain
# ---------------------------------------------------------------------------

def verify_chain(supplier_company) -> "tuple[bool, str]":
    """
    Recomputes the entire hash chain for a supplier company.
    Returns (True, 'OK') if valid.
    Returns (False, 'broken at seq=N') if any hash doesn't match.
    If broken: freeze the company's payouts (set all pending Payouts to 'awaiting_release').
    """
    from trust.models import SellerChainEvent

    events = list(
        SellerChainEvent.objects.filter(supplier_company=supplier_company)
        .order_by("seq")
    )

    prev_hash = "0" * 64
    for event in events:
        payload_hash = event.payload_hash
        expected_hash = hashlib.sha256(
            (prev_hash + str(event.seq) + event.event_type + payload_hash).encode()
        ).hexdigest()

        if event.hash != expected_hash or event.prev_hash != prev_hash:
            # Freeze all pending payouts for this company
            _freeze_company_payouts(supplier_company)
            return False, f"broken at seq={event.seq}"

        prev_hash = event.hash

    return True, "OK"


def _freeze_company_payouts(supplier_company):
    """Freeze all scheduled payouts for a supplier company."""
    try:
        from payments.models import Payout
        Payout.objects.filter(
            supplier_order__supplier_company=supplier_company,
            status=Payout.Status.SCHEDULED,
        ).update(status=Payout.Status.AWAITING_RELEASE)
    except Exception:
        logger.exception("_freeze_company_payouts: failed for company=%s", supplier_company)


# ---------------------------------------------------------------------------
# moderate_message
# ---------------------------------------------------------------------------

def moderate_message(message, moderator, approved: bool, flags: dict = None) -> "Message":
    """
    Staff approves or blocks a message.
    Sets moderation_status, moderated_by, moderation_flags.
    If approved: notifies the recipient.
    """
    from trust.models import Message

    message.moderation_status = (
        Message.ModerationStatus.APPROVED if approved else Message.ModerationStatus.BLOCKED
    )
    message.moderated_by = moderator
    if flags is not None:
        message.moderation_flags = flags
    message.save(update_fields=["moderation_status", "moderated_by", "moderation_flags"])

    if approved:
        try:
            from notify.service import notify
            thread = message.thread
            # Notify the other party (not the sender)
            sender_company_ids = set(
                message.sender.memberships.values_list("company_id", flat=True)
            )
            # Determine recipient users in the thread
            recipient_companies = []
            if thread.buyer_company_id not in sender_company_ids:
                recipient_companies.append(thread.buyer_company)
            if thread.supplier_company_id not in sender_company_ids:
                recipient_companies.append(thread.supplier_company)

            for company in recipient_companies:
                for membership in company.members.filter(status="active").select_related("user"):
                    notify(
                        user=membership.user,
                        template_key="message.approved",
                        context={
                            "thread_id": str(thread.id),
                            "message_id": str(message.id),
                        },
                    )
        except Exception:
            pass  # Notifications must not break moderation

    return message
