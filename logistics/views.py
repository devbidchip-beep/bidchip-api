"""
Logistics views: rate quotes, label creation, tracking webhooks,
mark-shipped, and buyer delivery confirmation.
"""

import hashlib
import hmac
import logging

import boto3
from django.conf import settings
from rest_framework import status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.generics import get_object_or_404
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from logistics.models import RateQuote, Shipment
from logistics.serializers import RateQuoteSerializer, ShipmentSerializer
from logistics.service import (
    choose_rate,
    create_label,
    get_rate_quotes,
    handle_tracking_webhook,
)

logger = logging.getLogger(__name__)


class RateQuoteView(APIView):
    """
    POST /api/v1/logistics/shipments/{id}/rates/

    Trigger get_rate_quotes() for a shipment.
    Returns list of RateQuote objects sorted by amount asc.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        shipment = get_object_or_404(Shipment, pk=pk)

        from_address = request.data.get("from_address", {})
        to_address = request.data.get("to_address", {})
        packages_data = request.data.get("packages", [])

        # If no addresses provided, derive from shipment
        if not from_address or not to_address:
            from logistics.service import _build_addresses

            from_address, to_address = _build_addresses(shipment)

        if not packages_data:
            packages_data = [
                {
                    "length_cm": float(pkg.length_cm),
                    "width_cm": float(pkg.width_cm),
                    "height_cm": float(pkg.height_cm),
                    "weight_kg": float(pkg.weight_kg),
                }
                for pkg in shipment.packages.all()
            ]

        quotes = get_rate_quotes(shipment, from_address, to_address, packages_data)
        serializer = RateQuoteSerializer(quotes, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class ChooseRateView(APIView):
    """
    POST /api/v1/logistics/shipments/{id}/choose-rate/

    Body: { rate_quote_id }
    Mark the selected rate quote as chosen.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        shipment = get_object_or_404(Shipment, pk=pk)
        rate_quote_id = request.data.get("rate_quote_id")
        if not rate_quote_id:
            raise ValidationError({"rate_quote_id": "This field is required."})

        rate_quote = get_object_or_404(RateQuote, pk=rate_quote_id, shipment=shipment)
        choose_rate(shipment, rate_quote)
        serializer = RateQuoteSerializer(rate_quote)
        return Response(serializer.data, status=status.HTTP_200_OK)


class CreateLabelView(APIView):
    """
    POST /api/v1/logistics/shipments/{id}/label/

    Create a shipping label using the chosen rate quote.
    Returns { tracking_number, label_url (signed S3 URL) }.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        shipment = get_object_or_404(Shipment, pk=pk)

        if not shipment.rate_quotes.filter(chosen=True).exists():
            raise ValidationError(
                {"detail": "No chosen rate quote found. Call choose-rate first."}
            )

        updated_shipment = create_label(shipment)

        label_url = ""
        if updated_shipment.label:
            try:
                s3_client = boto3.client(
                    "s3",
                    aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                    aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
                    region_name=settings.AWS_S3_REGION_NAME,
                )
                label_url = s3_client.generate_presigned_url(
                    "get_object",
                    Params={
                        "Bucket": settings.AWS_STORAGE_BUCKET_NAME,
                        "Key": updated_shipment.label,
                    },
                    ExpiresIn=3600,
                )
            except Exception:
                logger.exception("CreateLabelView: failed to generate signed URL")

        return Response(
            {
                "tracking_number": updated_shipment.tracking_number,
                "label_url": label_url,
            },
            status=status.HTTP_200_OK,
        )


class TrackingWebhookView(APIView):
    """
    POST /api/v1/logistics/tracking/webhook/

    Receives UPS/FedEx delivery events.
    Validates carrier-specific signature header.
    Calls handle_tracking_webhook().
    Always returns 200 to the carrier.
    """

    permission_classes = []  # Public endpoint; signature verification below
    authentication_classes = []

    def post(self, request):
        carrier = request.query_params.get("carrier", "").lower()

        # Carrier-specific signature verification
        if not self._verify_signature(request, carrier):
            logger.warning(
                "TrackingWebhookView: invalid signature from carrier=%s ip=%s",
                carrier,
                request.META.get("REMOTE_ADDR"),
            )
            # Return 200 anyway to avoid leaking info to attackers; log for alerting
            return Response({"status": "ok"}, status=status.HTTP_200_OK)

        payload = request.data

        try:
            tracking_number, event_type, event_time = self._parse_payload(carrier, payload)
            if tracking_number:
                handle_tracking_webhook(carrier, tracking_number, event_type, event_time)
        except Exception:
            logger.exception(
                "TrackingWebhookView: error processing webhook carrier=%s", carrier
            )

        # Always return 200 to the carrier
        return Response({"status": "ok"}, status=status.HTTP_200_OK)

    def _verify_signature(self, request, carrier: str) -> bool:
        """Validate carrier-specific HMAC signature header."""
        if carrier == "ups":
            # UPS sends a X-SHIPPING-UNIQUE-DEVICE-PIN header
            expected_token = getattr(settings, "UPS_WEBHOOK_TOKEN", "")
            if not expected_token:
                return True  # Skip if not configured
            provided = request.headers.get("X-SHIPPING-UNIQUE-DEVICE-PIN", "")
            return hmac.compare_digest(provided, expected_token)

        if carrier == "fedex":
            # FedEx uses a shared secret in the request body
            expected_secret = getattr(settings, "FEDEX_WEBHOOK_SECRET", "")
            if not expected_secret:
                return True  # Skip if not configured
            payload_secret = request.data.get("secret", "")
            return hmac.compare_digest(str(payload_secret), expected_secret)

        # Unknown carrier — allow through (log only)
        return True

    def _parse_payload(self, carrier: str, payload: dict):
        """
        Extract (tracking_number, event_type, event_time) from carrier payload.
        Returns (None, None, None) if the payload cannot be parsed.
        """
        from django.utils.dateparse import parse_datetime
        from django.utils import timezone as dj_timezone

        if carrier == "ups":
            # UPS webhook payload structure
            try:
                shipment = (
                    payload.get("trackResponse", {})
                    .get("shipment", [{}])[0]
                )
                pkg = shipment.get("package", [{}])[0]
                tracking_number = pkg.get("trackingNumber", "")
                activity = pkg.get("activity", [{}])[0]
                event_type = activity.get("status", {}).get("type", "")
                date_str = activity.get("date", "") + " " + activity.get("time", "")
                event_time = parse_datetime(date_str.strip()) or dj_timezone.now()
                return tracking_number, event_type, event_time
            except (IndexError, KeyError, TypeError, AttributeError):
                logger.exception("TrackingWebhookView: failed to parse UPS payload")
                return None, None, None

        if carrier == "fedex":
            # FedEx webhook payload structure
            try:
                event = payload.get("event", {})
                tracking_number = event.get("trackingNumber", "")
                event_type = event.get("eventType", "")
                event_time_str = event.get("eventTime", "")
                event_time = parse_datetime(event_time_str) or dj_timezone.now()
                return tracking_number, event_type, event_time
            except Exception:
                logger.exception("TrackingWebhookView: failed to parse FedEx payload")
                return None, None, None

        logger.warning("TrackingWebhookView: unknown carrier=%s", carrier)
        return None, None, None


class MarkShippedView(APIView):
    """
    POST /api/v1/logistics/supplier-orders/{id}/mark-shipped/

    Suppliers self-report shipping by providing carrier + tracking_number.
    Body: { carrier, tracking_number }
    Permission: must be an authenticated member of the supplier company.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        from orders.models import SupplierOrder

        supplier_order = get_object_or_404(SupplierOrder, pk=pk)

        # Verify requester belongs to the supplier company
        user = request.user
        is_supplier_member = user.memberships.filter(
            company=supplier_order.supplier_company,
            status="active",
        ).exists()
        if not is_supplier_member:
            raise PermissionDenied(
                "You must be a member of the supplier company to mark this order as shipped."
            )

        carrier = request.data.get("carrier", "").lower()
        tracking_number = request.data.get("tracking_number", "").strip()

        if not carrier:
            raise ValidationError({"carrier": "This field is required."})
        if not tracking_number:
            raise ValidationError({"tracking_number": "This field is required."})

        # Update or create the inbound shipment
        shipment, _ = Shipment.objects.get_or_create(
            supplier_order=supplier_order,
            leg="inbound",
            defaults={"carrier": carrier, "status": "in_transit"},
        )
        shipment.carrier = carrier
        shipment.tracking_number = tracking_number
        shipment.status = "in_transit"
        shipment.save(update_fields=["carrier", "tracking_number", "status", "updated_at"])

        # Trigger FSM transition on supplier_order
        try:
            supplier_order.mark_shipped_to_warehouse()
            supplier_order.save(update_fields=["status", "updated_at"])
        except Exception:
            logger.exception(
                "MarkShippedView: FSM mark_shipped_to_warehouse failed for supplier_order %s",
                supplier_order.id,
            )
            raise ValidationError(
                {"detail": f"Cannot mark as shipped from current status: {supplier_order.status}"}
            )

        serializer = ShipmentSerializer(shipment)
        return Response(serializer.data, status=status.HTTP_200_OK)


class MarkDeliveredView(APIView):
    """
    POST /api/v1/logistics/supplier-orders/{id}/buyer-confirm-delivery/

    Buyer confirms receipt of goods (alternative to carrier scan).
    Permission: must be an authenticated member of the buyer company.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        from django.utils import timezone

        from logistics.service import handle_delivery
        from orders.models import SupplierOrder

        supplier_order = get_object_or_404(SupplierOrder, pk=pk)

        # Verify requester belongs to the buyer company
        user = request.user
        is_buyer_member = user.memberships.filter(
            company=supplier_order.order.buyer_company,
            status="active",
        ).exists()
        if not is_buyer_member:
            raise PermissionDenied(
                "You must be a member of the buyer company to confirm delivery."
            )

        # Set delivered_source before calling handle_delivery so it overrides the default
        supplier_order.delivered_source = "buyer_confirmation"
        supplier_order.delivered_at = timezone.now()
        supplier_order.save(update_fields=["delivered_source", "delivered_at", "updated_at"])

        try:
            handle_delivery(supplier_order)
        except Exception:
            logger.exception(
                "MarkDeliveredView: handle_delivery failed for supplier_order %s", pk
            )
            raise ValidationError(
                {"detail": f"Cannot confirm delivery from current status: {supplier_order.status}"}
            )

        return Response(
            {"detail": "Delivery confirmed.", "supplier_order_id": str(supplier_order.id)},
            status=status.HTTP_200_OK,
        )
