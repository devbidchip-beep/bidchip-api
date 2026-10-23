"""
Pricing service — the ONLY place fees are computed.
Never accept prices from the browser.
"""

from decimal import Decimal, ROUND_HALF_UP
from typing import NamedTuple

from django.db import models
from django.utils import timezone


# ---------------------------------------------------------------------------
# States that surcharge is banned in (no surcharge allowed for credit cards)
# ---------------------------------------------------------------------------

SURCHARGE_BANNED_STATES = {
    "CT",  # Connecticut
    "MA",  # Massachusetts
    "ME",  # Maine
    "OK",  # Oklahoma
    "PR",  # Puerto Rico
}


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

class OrderPricing(NamedTuple):
    principal: Decimal
    buyer_fee: Decimal
    seller_fee: Decimal
    inspection_fee: Decimal
    compliance_fee: Decimal
    shipping_estimate: Decimal
    oem_uplift: Decimal
    tax_total: Decimal
    card_surcharge: Decimal
    card_surcharge_rate: Decimal
    grand_total: Decimal
    seller_payout: Decimal
    fee_schedule_id: str
    pricing_snapshot: dict


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_platform_setting(key: str, default=None):
    """
    Reads a value from core.models.PlatformSetting by key.
    Returns default if the key does not exist.
    """
    from core.models import PlatformSetting
    try:
        ps = PlatformSetting.objects.get(key=key)
        return ps.value
    except PlatformSetting.DoesNotExist:
        return default


def compute_marginal_fee(amount: Decimal, schedule: "FeeSchedule") -> Decimal:
    """
    Applies marginal brackets to amount.

    Example: $50,000 with brackets [0→7%, 25k→6%, 100k→5%]
    = 25000*0.07 + 25000*0.06 = 1750 + 1500 = 3250

    Never uses float. Returns Decimal rounded to 2dp.
    """
    brackets = list(schedule.brackets.order_by("lower_bound"))
    if not brackets:
        return Decimal("0.00")

    total_fee = Decimal("0")
    remaining = Decimal(str(amount))

    for i, bracket in enumerate(brackets):
        if remaining <= 0:
            break
        lower = Decimal(str(bracket.lower_bound))
        upper = Decimal(str(bracket.upper_bound)) if bracket.upper_bound is not None else None
        rate = Decimal(str(bracket.rate))

        if upper is not None:
            bracket_width = upper - lower
            taxable_in_bracket = min(remaining, bracket_width)
        else:
            taxable_in_bracket = remaining

        total_fee += taxable_in_bracket * rate
        remaining -= taxable_in_bracket

    result = total_fee.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    # Apply min_fee if set
    if schedule.min_fee is not None:
        min_fee = Decimal(str(schedule.min_fee))
        if result < min_fee:
            result = min_fee

    return result


def get_active_schedule(kind: str = "standard", side: str = "buyer", company=None) -> "FeeSchedule":
    """
    Returns the most specific active FeeSchedule:
    company-specific override first, then platform default.
    """
    from pricing.models import FeeSchedule
    today = timezone.now().date()

    base_qs = FeeSchedule.objects.filter(
        kind=kind,
        side=side,
        is_active=True,
        effective_from__lte=today,
    ).filter(
        models.Q(effective_to__isnull=True) | models.Q(effective_to__gte=today)
    )

    # Try company-specific first
    if company is not None:
        company_qs = base_qs.filter(company=company).order_by("-effective_from")
        schedule = company_qs.first()
        if schedule:
            return schedule

    # Fall back to default (no company)
    default_qs = base_qs.filter(company__isnull=True).order_by("-effective_from")
    schedule = default_qs.first()
    if schedule is None:
        raise ValueError(f"No active FeeSchedule found for kind={kind} side={side}")
    return schedule


# ---------------------------------------------------------------------------
# Import models inside function to avoid circular imports at module load
# ---------------------------------------------------------------------------

def price_order(
    awards: list,
    buyer_company,
    shipping_estimate: Decimal,
    payment_method: str = "card",
    card_funding: str = "debit",
    billing_state: str = "",
) -> OrderPricing:
    """
    Computes all fees for a set of awards before order creation.

    - awards: list of Award objects
    - Gets the active FeeSchedule for buyer and each supplier
    - Applies volume discount from latest CompanyVolume if eligible
    - Computes OEM uplift if buyer_company has an active OEMEMSLink
    - Card surcharge: read rate from PlatformSetting 'card.surcharge_rate';
      zero if not credit card; zero if billing_state in banned list
    - inspection_fee: from PlatformSetting 'inspection.min_fee' (default 400)
    - compliance_fee: from PlatformSetting 'compliance.fee' (default 30) per flagged line
    - Returns OrderPricing with pricing_snapshot dict capturing all inputs
    """
    from pricing.models import CompanyVolume, OEMEMSLink

    # ------------------------------------------------------------------
    # 1. Compute principal
    # ------------------------------------------------------------------
    principal = Decimal("0.00")
    for award in awards:
        line_total = Decimal(str(award.unit_price)) * Decimal(str(award.quantity_awarded))
        principal += line_total
    principal = principal.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    # ------------------------------------------------------------------
    # 2. Buyer volume discount
    # ------------------------------------------------------------------
    buyer_discount_points = Decimal("0")
    latest_buyer_vol = (
        CompanyVolume.objects.filter(company=buyer_company, eligible=True)
        .order_by("-as_of")
        .first()
    )
    if latest_buyer_vol:
        buyer_discount_points = Decimal(str(latest_buyer_vol.discount_points))

    # ------------------------------------------------------------------
    # 3. Buyer fee (marginal brackets, with volume discount)
    # ------------------------------------------------------------------
    buyer_schedule = get_active_schedule(kind="standard", side="buyer", company=buyer_company)

    buyer_fee = compute_marginal_fee(principal, buyer_schedule)

    # Apply volume discount: discount_points reduces the effective rate
    if buyer_discount_points > 0:
        discount_amount = (principal * buyer_discount_points).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        buyer_fee = max(Decimal("0.00"), buyer_fee - discount_amount)

    # ------------------------------------------------------------------
    # 4. Seller fee (marginal brackets per supplier, summed)
    # ------------------------------------------------------------------
    # Group awards by supplier
    supplier_awards: dict = {}
    for award in awards:
        supplier = award.bid.supplier_company
        supplier_awards.setdefault(supplier, []).append(award)

    seller_fee = Decimal("0.00")
    seller_payout_by_supplier: dict = {}
    seller_fee_schedule_id = None

    for supplier, sup_awards in supplier_awards.items():
        sup_principal = sum(
            Decimal(str(a.unit_price)) * Decimal(str(a.quantity_awarded))
            for a in sup_awards
        )
        sup_principal = sup_principal.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        # Seller volume discount
        seller_discount_points = Decimal("0")
        latest_seller_vol = (
            CompanyVolume.objects.filter(company=supplier, eligible=True)
            .order_by("-as_of")
            .first()
        )
        if latest_seller_vol:
            seller_discount_points = Decimal(str(latest_seller_vol.discount_points))

        sup_schedule = get_active_schedule(kind="standard", side="seller", company=supplier)
        if seller_fee_schedule_id is None:
            seller_fee_schedule_id = str(sup_schedule.id)

        sup_fee = compute_marginal_fee(sup_principal, sup_schedule)
        if seller_discount_points > 0:
            discount_amount = (sup_principal * seller_discount_points).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            sup_fee = max(Decimal("0.00"), sup_fee - discount_amount)

        seller_fee += sup_fee
        seller_payout_by_supplier[str(supplier.id)] = float(sup_principal - sup_fee)

    seller_fee = seller_fee.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    # ------------------------------------------------------------------
    # 5. Inspection fee
    # ------------------------------------------------------------------
    inspection_min = Decimal(str(_get_platform_setting("inspection.min_fee", 400)))
    # One inspection per supplier order; apply min
    num_suppliers = len(supplier_awards)
    inspection_fee = (inspection_min * num_suppliers).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )

    # ------------------------------------------------------------------
    # 6. Compliance fee — $30 per flagged line
    # ------------------------------------------------------------------
    compliance_fee_per_line = Decimal(str(_get_platform_setting("compliance.fee", 30)))
    flagged_count = 0
    for award in awards:
        listing_line = award.line
        if hasattr(listing_line, "compliance_status"):
            if listing_line.compliance_status == "flagged":
                flagged_count += 1
    compliance_fee = (compliance_fee_per_line * flagged_count).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )

    # ------------------------------------------------------------------
    # 7. OEM uplift
    # ------------------------------------------------------------------
    oem_uplift = Decimal("0.00")
    active_oem_link = (
        OEMEMSLink.objects.filter(
            ems_company=buyer_company,
            status="active",
        ).first()
    )
    if active_oem_link:
        oem_rate = Decimal(str(active_oem_link.commission_rate))
        oem_uplift = (principal * oem_rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    # ------------------------------------------------------------------
    # 8. Tax (placeholder)
    # ------------------------------------------------------------------
    tax_total = Decimal("0.00")

    # ------------------------------------------------------------------
    # 9. Card surcharge
    # ------------------------------------------------------------------
    card_surcharge = Decimal("0.00")
    card_surcharge_rate = Decimal("0.00")

    is_credit = payment_method == "card" and card_funding == "credit"
    state_banned = billing_state.upper() in SURCHARGE_BANNED_STATES

    if is_credit and not state_banned:
        card_surcharge_rate = Decimal(
            str(_get_platform_setting("card.surcharge_rate", "0.0300"))
        )
        subtotal = principal + buyer_fee + inspection_fee + compliance_fee + shipping_estimate + oem_uplift + tax_total
        card_surcharge = (subtotal * card_surcharge_rate).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

    # ------------------------------------------------------------------
    # 10. Grand total & seller payout
    # ------------------------------------------------------------------
    grand_total = (
        principal
        + buyer_fee
        + inspection_fee
        + compliance_fee
        + shipping_estimate
        + oem_uplift
        + tax_total
        + card_surcharge
    ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    seller_payout = (principal - seller_fee).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    # ------------------------------------------------------------------
    # 11. Pricing snapshot
    # ------------------------------------------------------------------
    pricing_snapshot = {
        "principal": str(principal),
        "buyer_fee": str(buyer_fee),
        "seller_fee": str(seller_fee),
        "inspection_fee": str(inspection_fee),
        "compliance_fee": str(compliance_fee),
        "shipping_estimate": str(shipping_estimate),
        "oem_uplift": str(oem_uplift),
        "tax_total": str(tax_total),
        "card_surcharge": str(card_surcharge),
        "card_surcharge_rate": str(card_surcharge_rate),
        "grand_total": str(grand_total),
        "seller_payout": str(seller_payout),
        "buyer_fee_schedule_id": str(buyer_schedule.id),
        "seller_fee_schedule_id": seller_fee_schedule_id,
        "buyer_discount_points": str(buyer_discount_points),
        "payment_method": payment_method,
        "card_funding": card_funding,
        "billing_state": billing_state,
        "oem_link_id": str(active_oem_link.id) if active_oem_link else None,
        "computed_at": timezone.now().isoformat(),
    }

    return OrderPricing(
        principal=principal,
        buyer_fee=buyer_fee,
        seller_fee=seller_fee,
        inspection_fee=inspection_fee,
        compliance_fee=compliance_fee,
        shipping_estimate=shipping_estimate,
        oem_uplift=oem_uplift,
        tax_total=tax_total,
        card_surcharge=card_surcharge,
        card_surcharge_rate=card_surcharge_rate,
        grand_total=grand_total,
        seller_payout=seller_payout,
        fee_schedule_id=str(buyer_schedule.id),
        pricing_snapshot=pricing_snapshot,
    )
