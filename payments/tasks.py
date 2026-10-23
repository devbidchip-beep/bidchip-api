"""
Celery tasks for the payments app.
"""

import logging
from decimal import Decimal

from celery import shared_task
from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task
def release_eligible_payouts():
    """
    Runs every 15 minutes via Celery Beat.

    SELECT supplier_orders WHERE:
      status = 'delivered'
      AND payout_eligible_at <= now()
      AND no open dispute
      AND requires_manual_release = False
      FOR UPDATE SKIP LOCKED

    For each eligible supplier_order:
    1. Check Payout doesn't already exist (idempotency)
    2. Create Stripe Transfer with idempotency_key = str(supplier_order.id)
    3. Create Payout record
    4. Post ledger entry (post_payout)
    5. Call supplier_order.release_payout() FSM transition
    6. Log OrderStatusLog
    7. Notify supplier: 'payout_released'
    """
    import stripe
    from django.conf import settings

    from accounts.models import StripeAccount
    from orders.models import OrderStatusLog, SupplierOrder
    from payments.ledger import post_payout
    from payments.models import Payment, Payout

    stripe.api_key = settings.STRIPE_SECRET_KEY
    now = timezone.now()

    # Build queryset of eligible supplier orders
    qs = (
        SupplierOrder.objects.select_for_update(skip_locked=True)
        .filter(
            status="delivered",
            payout_eligible_at__lte=now,
            requires_manual_release=False,
        )
        .exclude(
            # Exclude orders with open disputes (trust app, Phase 4)
            # Using a safe fallback if trust app doesn't exist yet
        )
        .select_related("order", "supplier_company")
    )

    # Exclude open disputes if the trust app is available
    try:
        from trust.models import Dispute
        open_dispute_order_ids = Dispute.objects.filter(
            status="open"
        ).values_list("supplier_order_id", flat=True)
        qs = qs.exclude(id__in=open_dispute_order_ids)
    except ImportError:
        pass  # trust app not yet installed — skip dispute filter

    for supplier_order in qs:
        try:
            with transaction.atomic():
                # 1. Idempotency check
                if Payout.objects.filter(supplier_order=supplier_order).exists():
                    continue

                # Get Stripe account for supplier
                try:
                    stripe_account = StripeAccount.objects.get(
                        company=supplier_order.supplier_company
                    )
                except StripeAccount.DoesNotExist:
                    logger.warning(
                        "No StripeAccount for supplier %s — skipping payout",
                        supplier_order.supplier_company_id,
                    )
                    continue

                # Get source charge from the order's payment
                try:
                    payment = Payment.objects.get(
                        order=supplier_order.order,
                        status=Payment.Status.SUCCEEDED,
                    )
                    source_charge = payment.stripe_charge
                except Payment.DoesNotExist:
                    logger.warning(
                        "No succeeded Payment for order %s",
                        supplier_order.order_id,
                    )
                    continue

                payout_amount = Decimal(str(supplier_order.payout_amount))
                idempotency_key = str(supplier_order.id)

                # 2. Create Stripe Transfer
                transfer = stripe.Transfer.create(
                    amount=int(payout_amount * 100),  # cents
                    currency=supplier_order.order.currency.lower(),
                    destination=stripe_account.stripe_account_id,
                    source_transaction=source_charge,
                    metadata={"idempotency_key": idempotency_key},
                    idempotency_key=idempotency_key,
                )

                # 3. Create Payout record
                payout = Payout.objects.create(
                    supplier_order=supplier_order,
                    stripe_account=stripe_account,
                    amount=payout_amount,
                    currency=supplier_order.order.currency,
                    idempotency_key=idempotency_key,
                    stripe_transfer_id=transfer.id,
                    source_charge=source_charge,
                    status=Payout.Status.RELEASED,
                    released_at=now,
                )

                # 4. Post ledger entry
                post_payout(supplier_order=supplier_order, payout_amount=payout_amount)

                # 5. FSM transition
                supplier_order.release_payout()
                supplier_order.save()

                # 6. Log status
                OrderStatusLog.objects.create(
                    order=supplier_order.order,
                    supplier_order=supplier_order,
                    from_status="delivered",
                    to_status="payout_released",
                    actor_kind="system",
                    reason="Automatic payout release",
                )

                # 7. Notify supplier
                try:
                    from notify.service import send_notification
                    send_notification(
                        event="payout_released",
                        recipient_company=supplier_order.supplier_company,
                        context={
                            "order_number": supplier_order.order.number,
                            "payout_amount": str(payout_amount),
                        },
                    )
                except Exception as exc:
                    logger.warning("Notification failed for payout %s: %s", payout.id, exc)

        except Exception as exc:
            logger.exception(
                "Failed to release payout for supplier_order %s: %s",
                supplier_order.id,
                exc,
            )
            continue
