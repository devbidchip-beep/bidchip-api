"""
Celery tasks for logistics: tracking poll fallback.
"""

import logging

from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task
def poll_tracking_updates():
    """
    Fallback polling task — runs every 30 minutes.

    For shipments in_transit older than 1 day and not yet delivered:
    - Calls UPS/FedEx tracking API to check status
    - Calls handle_tracking_webhook if delivered

    Primary delivery detection is via push webhooks (TrackingWebhookView).
    This task handles cases where push webhooks are missed or delayed.
    """
    from datetime import timedelta

    from logistics.carriers import fedex, ups
    from logistics.models import Shipment
    from logistics.service import handle_tracking_webhook

    cutoff = timezone.now() - timedelta(hours=24)

    shipments = Shipment.objects.filter(
        status="in_transit",
        shipped_at__lte=cutoff,
        tracking_number__isnull=False,
    ).exclude(tracking_number="")

    logger.info("poll_tracking_updates: checking %d in-transit shipments", shipments.count())

    for shipment in shipments:
        carrier = shipment.carrier
        tracking_number = shipment.tracking_number

        try:
            if carrier == "ups":
                result = ups.get_tracking(tracking_number)
            elif carrier == "fedex":
                result = fedex.get_tracking(tracking_number)
            else:
                logger.debug(
                    "poll_tracking_updates: skipping unsupported carrier=%s for shipment %s",
                    carrier,
                    shipment.id,
                )
                continue

            if result is None:
                continue

            status_code = result.get("status", "")
            event_time_str = result.get("timestamp", "")

            # Parse event_time (best-effort; fall back to now)
            try:
                from django.utils.dateparse import parse_datetime

                event_time = parse_datetime(event_time_str) or timezone.now()
            except Exception:
                event_time = timezone.now()

            handle_tracking_webhook(carrier, tracking_number, status_code, event_time)

        except Exception:
            logger.exception(
                "poll_tracking_updates: error processing shipment %s (carrier=%s tracking=%s)",
                shipment.id,
                carrier,
                tracking_number,
            )
