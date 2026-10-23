"""
Orders service — creates orders from awarded bids.
"""

import random
import string
from decimal import Decimal

from django.db import transaction
from django.utils import timezone


def _generate_anonymous_supplier_id() -> str:
    """Generate anonymous supplier id in format S-XXXX-XXXX (uppercase alphanumeric)."""
    chars = string.ascii_uppercase + string.digits
    part1 = "".join(random.choices(chars, k=4))
    part2 = "".join(random.choices(chars, k=4))
    return f"S-{part1}-{part2}"


def _get_platform_setting(key: str, default=None):
    from core.models import PlatformSetting
    try:
        ps = PlatformSetting.objects.get(key=key)
        return ps.value
    except PlatformSetting.DoesNotExist:
        return default


@transaction.atomic
def create_order_from_awards(
    awards,
    buyer_company,
    placed_by,
    ship_to,
    shipping_estimate: Decimal,
    payment_method: str = "card",
    card_funding: str = "debit",
    billing_state: str = "",
    po_number: str = "",
    po_file: str = "",
) -> "Order":
    """
    Creates Order + SupplierOrders + OrderLines from a list of Award objects.

    Steps (all in one transaction):
    1. Call pricing.service.price_order() to compute fees
    2. Create Order with all totals + pricing_snapshot
    3. Group awards by supplier_company
    4. For each supplier group: create SupplierOrder
    5. For each award: create OrderLine
    6. Log transition: OrderStatusLog(to_status='payment_pending', actor_kind='system')
    Returns Order.
    """
    from listings.models import Listing
    from orders.models import Order, SupplierOrder, OrderLine, OrderStatusLog
    from pricing.service import price_order

    # 1. Compute pricing server-side
    pricing = price_order(
        awards=list(awards),
        buyer_company=buyer_company,
        shipping_estimate=Decimal(str(shipping_estimate)),
        payment_method=payment_method,
        card_funding=card_funding,
        billing_state=billing_state,
    )

    # Determine listing from first award
    first_award = awards[0]
    listing = first_award.line.listing

    # 2. Generate order number
    year = timezone.now().year
    count = Order.objects.count() + 1
    order_number = f"BC-{year}-{str(count).zfill(6)}"

    # Snapshot ship_to address
    ship_to_snapshot = {
        "id": str(ship_to.id),
        "line1": ship_to.line1,
        "line2": ship_to.line2,
        "city": ship_to.city,
        "state": ship_to.state,
        "postal_code": ship_to.postal_code,
        "country": ship_to.country,
    }

    order = Order.objects.create(
        number=order_number,
        buyer_company=buyer_company,
        placed_by=placed_by,
        listing=listing,
        po_number=po_number or None,
        po_file=po_file,
        status=Order.Status.PAYMENT_PENDING,
        ship_to=ship_to,
        ship_to_snapshot=ship_to_snapshot,
        principal_total=pricing.principal,
        buyer_fee_total=pricing.buyer_fee,
        inspection_fee_total=pricing.inspection_fee,
        compliance_fee_total=pricing.compliance_fee,
        shipping_estimate=pricing.shipping_estimate,
        oem_uplift_total=pricing.oem_uplift,
        tax_total=pricing.tax_total,
        card_surcharge=pricing.card_surcharge,
        card_surcharge_rate=pricing.card_surcharge_rate,
        grand_total=pricing.grand_total,
        pricing_snapshot=pricing.pricing_snapshot,
    )

    # 3. Group awards by supplier_company
    supplier_awards: dict = {}
    for award in awards:
        supplier = award.bid.supplier_company
        supplier_awards.setdefault(supplier, []).append(award)

    # Hold days from platform setting
    hold_green = int(_get_platform_setting("hold.green_days", 5))

    # 4. Create SupplierOrders
    for supplier, sup_awards in supplier_awards.items():
        sup_principal = sum(
            Decimal(str(a.unit_price)) * Decimal(str(a.quantity_awarded))
            for a in sup_awards
        )
        sup_principal = sup_principal.quantize(Decimal("0.01"))

        # Compute per-supplier seller fee proportionally
        if pricing.principal > 0:
            ratio = sup_principal / pricing.principal
        else:
            ratio = Decimal("0")
        sup_seller_fee = (pricing.seller_fee * ratio).quantize(Decimal("0.01"))
        sup_payout = max(Decimal("0.00"), sup_principal - sup_seller_fee)

        # Generate unique anonymous supplier id
        anon_id = _generate_anonymous_supplier_id()
        while SupplierOrder.objects.filter(anonymous_supplier_id=anon_id).exists():
            anon_id = _generate_anonymous_supplier_id()

        # Check for active OEM/EMS link for the order's buyer
        from pricing.models import OEMEMSLink
        ems_link = OEMEMSLink.objects.filter(
            ems_company=buyer_company,
            status="active",
        ).first()

        supplier_order = SupplierOrder.objects.create(
            order=order,
            supplier_company=supplier,
            anonymous_supplier_id=anon_id,
            status="awarded",
            risk_tier="green",
            principal=sup_principal,
            seller_fee=sup_seller_fee,
            payout_amount=sup_payout,
            hold_days=hold_green,
            ems_link=ems_link,
        )

        # 5. Create OrderLines
        for award in sup_awards:
            line_total = (
                Decimal(str(award.unit_price)) * Decimal(str(award.quantity_awarded))
            ).quantize(Decimal("0.01"))

            OrderLine.objects.create(
                supplier_order=supplier_order,
                award=award,
                listing_line=award.line,
                quantity=award.quantity_awarded,
                unit_price=award.unit_price,
                line_total=line_total,
            )

    # 6. Log transition
    OrderStatusLog.objects.create(
        order=order,
        from_status="",
        to_status=Order.Status.PAYMENT_PENDING,
        actor_kind="system",
    )

    return order


@transaction.atomic
def mark_order_paid(order, stripe_charge_id: str = None, confirmed_by=None) -> "Order":
    """
    Sets order.status = paid, order.paid_at = now().
    Calls supplier_order.mark_paid() for each supplier order.
    Logs OrderStatusLog.
    Freezes pricing_snapshot (sets a 'paid_at' key in it).
    Sends 'payment_received' notification to each supplier.
    """
    from orders.models import OrderStatusLog
    from notify.service import send_notification  # noqa: F401 — optional

    prev_status = order.status
    order.status = "paid"
    order.paid_at = timezone.now()

    # Freeze pricing snapshot
    snapshot = dict(order.pricing_snapshot)
    snapshot["paid_at"] = order.paid_at.isoformat()
    if stripe_charge_id:
        snapshot["stripe_charge_id"] = stripe_charge_id
    order.pricing_snapshot = snapshot
    order.save(update_fields=["status", "paid_at", "pricing_snapshot", "updated_at"])

    for sup_order in order.supplier_orders.all():
        sup_order.mark_paid()
        sup_order.save()

        OrderStatusLog.objects.create(
            order=order,
            supplier_order=sup_order,
            from_status=prev_status,
            to_status="paid",
            actor=confirmed_by,
            actor_kind="user" if confirmed_by else "system",
        )

        # Notify supplier
        try:
            from notify.service import send_notification
            send_notification(
                event="payment_received",
                recipient_company=sup_order.supplier_company,
                context={"order_number": order.number},
            )
        except Exception:
            pass  # Notifications must not break the payment flow

    OrderStatusLog.objects.create(
        order=order,
        from_status=prev_status,
        to_status="paid",
        actor=confirmed_by,
        actor_kind="user" if confirmed_by else "system",
    )

    return order
