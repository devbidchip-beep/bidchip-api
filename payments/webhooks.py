"""
Stripe webhook endpoint — idempotent event processing.
"""

import json
import logging

import stripe
from django.conf import settings
from django.http import HttpResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Event handlers
# ---------------------------------------------------------------------------

def handle_charge_succeeded(payload: dict):
    """Mark order as paid when Stripe charge succeeds."""
    from orders.models import Order
    from orders.service import mark_order_paid
    from payments.models import Payment

    charge = payload.get("data", {}).get("object", {})
    stripe_charge_id = charge.get("id")
    payment_intent_id = charge.get("payment_intent")

    try:
        payment = Payment.objects.get(stripe_payment_intent=payment_intent_id)
    except Payment.DoesNotExist:
        logger.warning("charge.succeeded: no Payment found for PI %s", payment_intent_id)
        return

    payment.stripe_charge = stripe_charge_id
    payment.status = Payment.Status.SUCCEEDED
    payment.save(update_fields=["stripe_charge", "status", "updated_at"])

    mark_order_paid(
        order=payment.order,
        stripe_charge_id=stripe_charge_id,
    )


def handle_transfer_created(payload: dict):
    """Record Stripe transfer on Payout."""
    from payments.models import Payout

    transfer = payload.get("data", {}).get("object", {})
    transfer_id = transfer.get("id")
    idempotency_key = transfer.get("metadata", {}).get("idempotency_key")

    if not idempotency_key:
        return

    try:
        payout = Payout.objects.get(idempotency_key=idempotency_key)
    except Payout.DoesNotExist:
        logger.warning("transfer.created: no Payout found for key %s", idempotency_key)
        return

    payout.stripe_transfer_id = transfer_id
    payout.status = Payout.Status.RELEASED
    payout.released_at = timezone.now()
    payout.save(update_fields=["stripe_transfer_id", "status", "released_at", "updated_at"])


def handle_account_updated(payload: dict):
    """Sync StripeAccount from account.updated event."""
    from accounts.models import StripeAccount

    account = payload.get("data", {}).get("object", {})
    stripe_account_id = account.get("id")

    try:
        sa = StripeAccount.objects.get(stripe_account_id=stripe_account_id)
    except StripeAccount.DoesNotExist:
        return

    sa.charges_enabled = account.get("charges_enabled", sa.charges_enabled)
    sa.payouts_enabled = account.get("payouts_enabled", sa.payouts_enabled)
    sa.details_submitted = account.get("details_submitted", sa.details_submitted)
    sa.raw_data = account
    sa.save(update_fields=["charges_enabled", "payouts_enabled", "details_submitted", "raw_data", "updated_at"])


# ---------------------------------------------------------------------------
# Webhook view
# ---------------------------------------------------------------------------

EVENT_HANDLERS = {
    "charge.succeeded": handle_charge_succeeded,
    "transfer.created": handle_transfer_created,
    "account.updated": handle_account_updated,
}


@csrf_exempt
def stripe_webhook(request):
    """
    1. Verify Stripe-Signature header using stripe.Webhook.construct_event()
    2. Store StripeEvent immediately (even if processing fails)
    3. If signature_verified=False: return 400
    4. If event_id already processed: return 200 (idempotent)
    5. Route by event type
    6. Set processed_at on success, error on failure
    7. Always return 200 to Stripe (log errors internally)
    """
    from payments.models import StripeEvent

    payload = request.body
    sig_header = request.META.get("HTTP_STRIPE_SIGNATURE", "")
    webhook_secret = settings.STRIPE_WEBHOOK_SECRET

    # 1. Verify signature
    event = None
    signature_verified = False

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
        signature_verified = True
    except stripe.error.SignatureVerificationError:
        logger.warning("Stripe signature verification failed")
    except Exception as exc:
        logger.exception("Stripe webhook construct_event error: %s", exc)

    # Parse payload for storage
    try:
        payload_dict = json.loads(payload)
    except (json.JSONDecodeError, Exception):
        payload_dict = {}

    event_id = (event.id if event else None) or payload_dict.get("id", "unknown")
    event_type = (event.type if event else None) or payload_dict.get("type", "unknown")

    # 2. Store event immediately
    stripe_event, created = StripeEvent.objects.get_or_create(
        event_id=event_id,
        defaults={
            "type": event_type,
            "payload": payload_dict,
            "signature_verified": signature_verified,
        },
    )

    # 3. Reject unverified
    if not signature_verified:
        return HttpResponse(status=400)

    # 4. Idempotency check
    if not created and stripe_event.processed_at is not None:
        return HttpResponse(status=200)

    # 5. Route event
    handler = EVENT_HANDLERS.get(event_type)
    if handler:
        try:
            handler(payload_dict)
            stripe_event.processed_at = timezone.now()
            stripe_event.error = ""
            stripe_event.save(update_fields=["processed_at", "error"])
        except Exception as exc:
            logger.exception("Error processing Stripe event %s: %s", event_id, exc)
            stripe_event.error = str(exc)
            stripe_event.save(update_fields=["error"])
    else:
        # Unknown event type — mark processed so we don't retry
        stripe_event.processed_at = timezone.now()
        stripe_event.save(update_fields=["processed_at"])

    return HttpResponse(status=200)
