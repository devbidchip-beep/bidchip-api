"""
Celery tasks for the listings app.
"""

import logging

from celery import shared_task
from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task
def close_expired_listings():
    """
    Runs every minute via Celery Beat.
    Closes expired published listings in a transaction with SELECT FOR UPDATE.

    For each expired listing:
    - Sets status = 'closed', closed_at = now()
    - For reverse/bom: picks winning bids (lowest price, exact match first)
      and creates Order stubs (placeholder — full order creation in Phase 3)
    - Sends notification (placeholder log for now)

    Never runs on page loads.
    """
    from listings.models import Listing

    now = timezone.now()

    expired_ids = list(
        Listing.objects.filter(
            status=Listing.Status.PUBLISHED,
            ends_at__lte=now,
        ).values_list("id", flat=True)
    )

    if not expired_ids:
        return

    logger.info("close_expired_listings: found %d expired listings", len(expired_ids))

    for listing_id in expired_ids:
        with transaction.atomic():
            try:
                listing = (
                    Listing.objects.select_for_update()
                    .prefetch_related("lines")
                    .get(pk=listing_id, status=Listing.Status.PUBLISHED)
                )
            except Listing.DoesNotExist:
                # Another worker may have already closed it
                continue

            listing.status = Listing.Status.CLOSED
            listing.closed_at = now
            listing.save(update_fields=["status", "closed_at", "updated_at"])

            any_awarded = False

            if listing.kind in (Listing.Kind.REVERSE, Listing.Kind.BOM, Listing.Kind.RFQ):
                from bidding.services import auto_award_line
                from notify.service import notify

                for line in listing.lines.filter(status="open"):
                    try:
                        awards = auto_award_line(line)
                    except Exception as exc:
                        logger.exception(
                            "close_expired_listings: auto_award_line failed for line %s: %s",
                            line.pk,
                            exc,
                        )
                        awards = []

                    if awards:
                        any_awarded = True
                        notify(
                            listing.created_by,
                            "listing_awarded",
                            {"listing_number": listing.number},
                        )
                        for award in awards:
                            notify(
                                award.bid.placed_by,
                                "listing_awarded",
                                {"listing_number": listing.number},
                            )
                    else:
                        notify(
                            listing.created_by,
                            "listing_closed",
                            {"listing_number": listing.number},
                        )

            if any_awarded:
                listing.status = Listing.Status.AWARDED
                listing.save(update_fields=["status", "updated_at"])

            logger.info(
                "close_expired_listings: listing %s finalized with status=%s",
                listing.number,
                listing.status,
            )
