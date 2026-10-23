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

            # Phase 3: winner selection and Order creation placeholder
            if listing.kind in (Listing.Kind.REVERSE, Listing.Kind.BOM):
                # TODO (Phase 3): query bids for each line, pick lowest price /
                # exact-match winner, create Order stubs.
                logger.info(
                    "close_expired_listings: listing %s closed — bid award pending Phase 3",
                    listing.number,
                )
            else:
                logger.info(
                    "close_expired_listings: listing %s closed (kind=%s)",
                    listing.number,
                    listing.kind,
                )

            # TODO (Phase 2/3): send notification to buyer_company and invited suppliers
            logger.info(
                "close_expired_listings: [NOTIFY PLACEHOLDER] listing %s closed",
                listing.number,
            )
