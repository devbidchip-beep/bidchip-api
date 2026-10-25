"""
Logistics service layer: rate quotes, label creation, tracking webhooks,
and delivery handling.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import TYPE_CHECKING

from django.utils import timezone

if TYPE_CHECKING:
    from logistics.models import RateQuote, Shipment

logger = logging.getLogger(__name__)


def get_rate_quotes(
    shipment: "Shipment",
    from_address: dict,
    to_address: dict,
    packages: list,
) -> list["RateQuote"]:
    """
    Call both UPS and FedEx get_rates().
    Create RateQuote rows for each result.
    Mark is_next_day=True for 1-day services.
    Return all quotes sorted by amount asc.
    Never raises.
    """
    from logistics.carriers import fedex, ups
    from logistics.models import RateQuote

    all_rates = []

    try:
        ups_rates = ups.get_rates(from_address, to_address, packages)
        for rate in ups_rates:
            all_rates.append({"carrier": "ups", **rate})
    except Exception:
        logger.exception("get_rate_quotes: unexpected error calling UPS")

    try:
        fedex_rates = fedex.get_rates(from_address, to_address, packages)
        for rate in fedex_rates:
            all_rates.append({"carrier": "fedex", **rate})
    except Exception:
        logger.exception("get_rate_quotes: unexpected error calling FedEx")

    quotes = []
    for rate in all_rates:
        try:
            quote = RateQuote.objects.create(
                shipment=shipment,
                carrier=rate["carrier"],
                service_code=rate["service_code"],
                service_name=rate.get("service_name", ""),
                amount=Decimal(str(rate["amount"])),
                currency=rate.get("currency", "USD"),
                transit_days=rate.get("transit_days"),
                is_next_day=rate.get("is_next_day", False),
                chosen=False,
            )
            quotes.append(quote)
        except Exception:
            logger.exception("get_rate_quotes: failed to create RateQuote row")

    return sorted(quotes, key=lambda q: q.amount)


def choose_rate(shipment: "Shipment", rate_quote: "RateQuote") -> None:
    """
    Set chosen=True on the given quote, False on all others for this shipment.
    """
    from logistics.models import RateQuote

    RateQuote.objects.filter(shipment=shipment).update(chosen=False)
    rate_quote.chosen = True
    rate_quote.save(update_fields=["chosen"])


def create_label(shipment: "Shipment") -> "Shipment":
    """
    Use the chosen RateQuote carrier to create a label.
    Save tracking_number, label S3 key, status=label_created.
    Return updated shipment.
    """
    import base64

    import boto3
    from django.conf import settings

    from logistics.carriers import fedex, ups

    try:
        chosen_quote = shipment.rate_quotes.get(chosen=True)
    except Exception:
        logger.error("create_label: no chosen rate quote for shipment %s", shipment.id)
        return shipment

    # Build address dicts from order/supplier_order
    shipper, recipient = _build_addresses(shipment)

    packages = [
        {
            "length_cm": float(pkg.length_cm),
            "width_cm": float(pkg.width_cm),
            "height_cm": float(pkg.height_cm),
            "weight_kg": float(pkg.weight_kg),
        }
        for pkg in shipment.packages.all()
    ]

    reference = getattr(shipment, "po_number_on_label", "") or str(shipment.id)

    result = None
    if chosen_quote.carrier == "ups":
        result = ups.create_label(shipper, recipient, packages, chosen_quote.service_code, reference)
    elif chosen_quote.carrier == "fedex":
        result = fedex.create_label(shipper, recipient, packages, chosen_quote.service_code, reference)

    if not result:
        logger.error("create_label: carrier returned None for shipment %s", shipment.id)
        return shipment

    # Upload label to S3 and store the key
    label_s3_key = ""
    try:
        label_data = base64.b64decode(result["label_base64"])
        ext = result.get("label_format", "GIF").lower()
        s3_key = f"labels/{shipment.id}.{ext}"
        s3_client = boto3.client(
            "s3",
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_S3_REGION_NAME,
        )
        s3_client.put_object(
            Bucket=settings.AWS_STORAGE_BUCKET_NAME,
            Key=s3_key,
            Body=label_data,
        )
        label_s3_key = s3_key
    except Exception:
        logger.exception("create_label: failed to upload label to S3 for shipment %s", shipment.id)
        # Store raw base64 in label field as fallback
        label_s3_key = result.get("label_base64", "")[:500]

    shipment.tracking_number = result["tracking_number"]
    shipment.label = label_s3_key
    shipment.carrier = chosen_quote.carrier
    shipment.service_code = chosen_quote.service_code
    shipment.status = "label_created"
    shipment.save(update_fields=["tracking_number", "label", "carrier", "service_code", "status", "updated_at"])

    return shipment


def handle_tracking_webhook(
    carrier: str,
    tracking_number: str,
    event_type: str,
    event_time,
) -> None:
    """
    Called by carrier tracking webhook.
    Look up Shipment by tracking_number.
    If event_type indicates delivery:
      - Set shipment.status = delivered, shipment.delivered_at = event_time
      - If outbound: call handle_delivery(supplier_order)
    Log all events to core.AuditEvent.
    """
    from core.models import AuditEvent
    from logistics.models import Shipment

    try:
        shipment = Shipment.objects.get(tracking_number=tracking_number)
    except Shipment.DoesNotExist:
        logger.warning(
            "handle_tracking_webhook: no shipment found for tracking_number=%s carrier=%s",
            tracking_number,
            carrier,
        )
        return
    except Exception:
        logger.exception(
            "handle_tracking_webhook: error looking up tracking_number=%s", tracking_number
        )
        return

    # Log the raw event
    try:
        AuditEvent.objects.create(
            event_type=AuditEvent.EventType.OTHER,
            description=f"Carrier tracking event: carrier={carrier} event={event_type} tracking={tracking_number}",
            extra_data={
                "carrier": carrier,
                "tracking_number": tracking_number,
                "event_type": event_type,
                "event_time": str(event_time),
                "shipment_id": str(shipment.id),
            },
        )
    except Exception:
        logger.exception("handle_tracking_webhook: failed to write AuditEvent")

    # Normalise event_type to detect delivery
    delivered = _is_delivery_event(carrier, event_type)

    if delivered:
        shipment.status = "delivered"
        shipment.delivered_at = event_time
        shipment.save(update_fields=["status", "delivered_at", "updated_at"])
        logger.info(
            "handle_tracking_webhook: shipment %s marked delivered via carrier scan", shipment.id
        )

        # For inbound shipments that are being delivered to the warehouse,
        # trigger the delivery handler on the associated supplier_order
        if shipment.leg == "inbound" and shipment.supplier_order_id:
            try:
                handle_delivery(shipment.supplier_order)
            except Exception:
                logger.exception(
                    "handle_tracking_webhook: handle_delivery failed for supplier_order %s",
                    shipment.supplier_order_id,
                )
        elif shipment.leg == "outbound" and shipment.order_id:
            # Outbound: look up supplier orders and handle delivery
            try:
                for supplier_order in shipment.order.supplier_orders.all():
                    handle_delivery(supplier_order)
            except Exception:
                logger.exception(
                    "handle_tracking_webhook: handle_delivery failed for order %s",
                    shipment.order_id,
                )


def _is_delivery_event(carrier: str, event_type: str) -> bool:
    """Return True if the carrier event_type string indicates a delivered state."""
    event_upper = (event_type or "").upper()
    # UPS delivery event type codes
    ups_delivered = {"D", "DEL", "DELIVERED"}
    # FedEx delivery event type codes
    fedex_delivered = {"DL", "DELIVERED", "OD"}
    if carrier == "ups":
        return event_upper in ups_delivered or "DELIVERED" in event_upper
    if carrier == "fedex":
        return event_upper in fedex_delivered or "DELIVERED" in event_upper
    return "DELIVERED" in event_upper


def handle_delivery(supplier_order) -> None:
    """
    Called when carrier confirms delivery (inbound to warehouse) or when
    buyer confirms delivery of outbound shipment.

    - Calls supplier_order.mark_delivered() FSM transition
    - Sets delivered_source = 'carrier_scan'
    - Computes payout_eligible_at using core.calendar.add_running_time
      (N business days: hold_days * 8 * 60 approximate business minutes)
    - Sends 'delivered_payout_in_5_days' notification to buyer
    - Logs OrderStatusLog
    """
    from core.calendar import add_running_time
    from orders.models import OrderStatusLog

    from_status = supplier_order.status

    try:
        supplier_order.mark_delivered()
    except Exception:
        logger.exception(
            "handle_delivery: FSM mark_delivered failed for supplier_order %s (status=%s)",
            supplier_order.id,
            from_status,
        )
        return

    delivered_at = supplier_order.delivered_at or timezone.now()
    supplier_order.delivered_source = "carrier_scan"

    # Compute payout_eligible_at: N hold_days * 8h * 60min of running business time
    hold_days = supplier_order.hold_days or 5
    hold_minutes = hold_days * 8 * 60
    try:
        supplier_order.payout_eligible_at = add_running_time(delivered_at, hold_minutes)
    except Exception:
        logger.exception(
            "handle_delivery: failed to compute payout_eligible_at for supplier_order %s",
            supplier_order.id,
        )
        supplier_order.payout_eligible_at = None

    supplier_order.save(
        update_fields=["delivered_source", "payout_eligible_at", "status", "delivered_at", "updated_at"]
    )

    # Log the status transition
    try:
        OrderStatusLog.objects.create(
            supplier_order=supplier_order,
            from_status=from_status,
            to_status=supplier_order.status,
            actor_kind=OrderStatusLog.ActorKind.WEBHOOK,
            reason="Delivery confirmed via carrier scan",
        )
    except Exception:
        logger.exception(
            "handle_delivery: failed to write OrderStatusLog for supplier_order %s",
            supplier_order.id,
        )

    # Send notification to buyer
    _notify_buyer_delivered(supplier_order)


def _notify_buyer_delivered(supplier_order) -> None:
    """Send a 'delivered_payout_in_5_days' notification to the buyer."""
    try:
        from notify.service import send_notification  # type: ignore[import]

        send_notification(
            event="delivered_payout_in_5_days",
            recipient_company=supplier_order.order.buyer_company,
            context={
                "supplier_order_id": str(supplier_order.id),
                "payout_eligible_at": str(supplier_order.payout_eligible_at),
            },
        )
    except ImportError:
        logger.debug("_notify_buyer_delivered: notify.service not available")
    except Exception:
        logger.exception(
            "_notify_buyer_delivered: failed to send notification for supplier_order %s",
            supplier_order.id,
        )


def _build_addresses(shipment: "Shipment") -> tuple[dict, dict]:
    """
    Derive shipper and recipient address dicts from the shipment's related objects.
    Returns (shipper, recipient) dicts compatible with carrier get_rates / create_label.
    """
    # Warehouse address (BidChip) — used as default shipper/recipient for inbound/outbound
    warehouse = {
        "name": "BidChip Warehouse",
        "address_line": "123 Warehouse Blvd",
        "city": "Los Angeles",
        "state": "CA",
        "postal_code": "90001",
        "country_code": "US",
    }

    def _addr_from_address_obj(addr_obj) -> dict:
        return {
            "name": getattr(addr_obj, "company", None) and str(addr_obj.company) or "BidChip",
            "address_line": addr_obj.line1,
            "city": addr_obj.city,
            "state": addr_obj.state,
            "postal_code": addr_obj.postal_code,
            "country_code": addr_obj.country,
        }

    if shipment.leg == "inbound" and shipment.supplier_order_id:
        supplier_company = shipment.supplier_order.supplier_company
        shipper_addr = supplier_company.addresses.filter(
            address_type="shipping", is_primary=True
        ).first()
        shipper = _addr_from_address_obj(shipper_addr) if shipper_addr else warehouse
        recipient = warehouse

    elif shipment.leg == "outbound" and shipment.order_id:
        ship_to = shipment.order.ship_to
        shipper = warehouse
        recipient = _addr_from_address_obj(ship_to) if ship_to else warehouse

    else:
        shipper = warehouse
        recipient = warehouse

    return shipper, recipient
