"""
Bidding service layer — place bids, withdraw bids, award lines.
All business logic lives here; views are thin wrappers.
"""

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone


def place_bid(
    line,
    supplier_company,
    placed_by,
    unit_price,
    quantity_offered,
    date_code_year=None,
    packaging=None,
    lead_time_days=0,
    inventory_item=None,
) -> "Bid":
    """
    Validates and places a bid on a listing line.
    Raises ValidationError for any rule violation.
    """
    from bidding.models import Bid
    from listings.models import Listing

    now = timezone.now()

    # Rule 1: Listing must be published and not expired
    listing = line.listing
    if listing.status != Listing.Status.PUBLISHED:
        raise ValidationError("Listing is not published.")
    if listing.ends_at is not None and listing.ends_at <= now:
        raise ValidationError("Listing has expired.")

    # Rule 2: Supplier cannot bid on own listing
    if listing.buyer_company_id == supplier_company.pk:
        raise ValidationError("You cannot bid on your own listing.")

    # Rule 3: unit_price must be > 0
    if unit_price is None or Decimal(str(unit_price)) <= Decimal("0"):
        raise ValidationError("Unit price must be greater than zero.")

    # Rule 4: For reverse auctions — must beat current best active bid
    if listing.kind == Listing.Kind.REVERSE:
        best = (
            Bid.objects.filter(line=line, status=Bid.Status.ACTIVE)
            .order_by("unit_price")
            .first()
        )
        if best is not None and Decimal(str(unit_price)) >= best.unit_price:
            raise ValidationError(
                f"For a reverse auction your price must be lower than the current best bid "
                f"of {best.unit_price}."
            )

    # Rule 5: Supplier cannot already have an active bid on this line
    if Bid.objects.filter(
        line=line, supplier_company=supplier_company, status=Bid.Status.ACTIVE
    ).exists():
        raise ValidationError(
            "You already have an active bid on this line. Withdraw it before placing a new one."
        )

    # Build a tentative Bid to check exact-match before saving
    bid = Bid(
        line=line,
        supplier_company=supplier_company,
        placed_by=placed_by,
        unit_price=Decimal(str(unit_price)),
        quantity_offered=quantity_offered,
        date_code_year=date_code_year,
        packaging=packaging,
        lead_time_days=lead_time_days,
        inventory_item=inventory_item,
    )
    bid._compute_match()

    # Rule 6: If exceptions not allowed and bid is not exact match → reject
    if not line.allow_exceptions and not bid.is_exact_match:
        raise ValidationError(
            f"This line does not allow exceptions. Issues: {bid.exception_reasons}"
        )

    bid.save()
    return bid


def withdraw_bid(bid, withdrawn_by) -> "Bid":
    """Sets bid.status = withdrawn. Only the placing company or staff can withdraw."""
    from bidding.models import Bid

    is_own_company = (
        withdrawn_by.memberships.filter(
            company=bid.supplier_company, status="active"
        ).exists()
    )
    if not (is_own_company or withdrawn_by.is_staff):
        raise ValidationError("You do not have permission to withdraw this bid.")

    if bid.status != Bid.Status.ACTIVE:
        raise ValidationError("Only active bids can be withdrawn.")

    bid.status = Bid.Status.WITHDRAWN
    bid.save(update_fields=["status", "updated_at"])
    return bid


def award_line(line, awards: list[dict], awarded_by=None) -> list["Award"]:
    """
    Awards a listing line to one or more bids (split fill).
    awards = [{'bid': Bid, 'quantity': int}, ...]

    All operations happen inside SELECT FOR UPDATE on the line.
    """
    from bidding.models import Award, Bid
    from listings.models import ListingLine

    with transaction.atomic():
        # Re-fetch line with lock
        line = ListingLine.objects.select_for_update().get(pk=line.pk)

        # Rule 1: total awarded quantity <= line quantity
        total = sum(a["quantity"] for a in awards)
        if total > line.quantity:
            raise ValidationError(
                f"Total awarded quantity ({total}) exceeds line quantity ({line.quantity})."
            )

        # Rule 2: all bids must be active
        for entry in awards:
            bid = entry["bid"]
            if bid.status != Bid.Status.ACTIVE:
                raise ValidationError(f"Bid {bid.pk} is not active.")
            if bid.line_id != line.pk:
                raise ValidationError(f"Bid {bid.pk} does not belong to this line.")

        award_objects = []
        awarded_bid_ids = set()

        for rank, entry in enumerate(awards, start=1):
            bid = entry["bid"]
            qty = entry["quantity"]
            award = Award.objects.create(
                line=line,
                bid=bid,
                quantity_awarded=qty,
                unit_price=bid.unit_price,
                rank=rank,
                awarded_by=awarded_by,
                status=Award.Status.AWARDED,
            )
            award_objects.append(award)
            awarded_bid_ids.add(bid.pk)

            # Mark bid as won or partially won
            if qty >= bid.quantity_offered:
                bid.status = Bid.Status.WON
            else:
                bid.status = Bid.Status.PARTIALLY_WON
            bid.save(update_fields=["status", "updated_at"])

        # Mark all other active bids on this line as lost
        Bid.objects.filter(line=line, status=Bid.Status.ACTIVE).exclude(
            pk__in=awarded_bid_ids
        ).update(status=Bid.Status.LOST)

        # Update line status
        if total >= line.quantity:
            line.status = ListingLine.Status.AWARDED
        else:
            line.status = ListingLine.Status.PARTIALLY_AWARDED
        line.save(update_fields=["status", "updated_at"])

        return award_objects


def auto_award_line(line) -> list["Award"]:
    """
    Default winner selection for the closing task.
    - Rank 1: lowest-price exact-match bid
    - Fallback: lowest-price exception bid (if line.allow_exceptions=True)
    - No bids: line.status = no_award
    """
    from bidding.models import Bid
    from listings.models import ListingLine

    with transaction.atomic():
        active_bids = Bid.objects.filter(line=line, status=Bid.Status.ACTIVE).order_by(
            "-is_exact_match", "unit_price"
        )

        # Pick best exact match
        winner = active_bids.filter(is_exact_match=True).first()

        if winner is None and line.allow_exceptions:
            winner = active_bids.first()

        if winner is None:
            # No suitable bid found
            line_obj = type(line).objects.select_for_update().get(pk=line.pk)
            line_obj.status = ListingLine.Status.NO_AWARD
            line_obj.save(update_fields=["status", "updated_at"])
            return []

        return award_line(line, [{"bid": winner, "quantity": winner.quantity_offered}])
