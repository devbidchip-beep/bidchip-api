"""
Nimble Quote integration views.
Token-authenticated (DRF Token), not session auth.
"""

import hashlib
import json
import logging

from django.db import transaction
from rest_framework.authentication import TokenAuthentication
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

logger = logging.getLogger(__name__)


class NimbleRFQCreateView(APIView):
    """
    POST /api/v1/integrations/nimble/rfqs/

    Payload:
    {
        "title": str,
        "project_id": str,           # used as nimble_rfq_id
        "lead_time": int,
        "board_1".."board_8": str,   # optional board references
        "elements": [
            {"element_id": str, "sku": str, "manufacturer": str, "quantity": int, ...}
        ]
    }

    Creates: Listing (kind=rfq) + ListingLines + NimbleRFQ
    Returns: { "rfq_id": str, "listing_id": str, "lines": [{"element_id", "line_id"}] }
    """

    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        from accounts.models import Company
        from integrations.models import NimbleRFQ, NimbleSyncLog
        from listings.models import Listing, ListingLine

        data = request.data
        project_id = data.get("project_id", "")
        title = data.get("title", f"Nimble RFQ {project_id}")
        elements = data.get("elements", [])

        if not project_id:
            return Response({"detail": "project_id is required."}, status=400)
        if not elements:
            return Response({"detail": "elements list is required."}, status=400)

        # Log the push
        req_hash = hashlib.sha256(json.dumps(data, sort_keys=True, default=str).encode()).hexdigest()
        NimbleSyncLog.objects.create(direction="push", request_hash=req_hash, status_code=200)

        # Resolve buyer company from token user
        membership = (
            request.user.memberships.filter(status="active")
            .select_related("company")
            .first()
        )
        if membership is None:
            return Response({"detail": "Token user has no associated company."}, status=400)
        buyer_company = membership.company

        with transaction.atomic():
            listing = Listing.objects.create(
                title=title,
                kind=Listing.Kind.RFQ,
                status=Listing.Status.PUBLISHED,
                buyer_company=buyer_company,
                created_by=request.user,
                source=Listing.Source.NIMBLE,
            )

            nimble_rfq = NimbleRFQ.objects.create(
                listing=listing,
                nimble_rfq_id=project_id,
                status=NimbleRFQ.Status.ACTIVE,
            )

            lines_out = []
            for idx, elem in enumerate(elements, start=1):
                line = ListingLine.objects.create(
                    listing=listing,
                    line_no=idx,
                    mpn_raw=elem.get("sku", ""),
                    manufacturer_raw=elem.get("manufacturer", ""),
                    quantity=int(elem.get("quantity", 1)),
                )
                lines_out.append({"element_id": elem.get("element_id"), "line_id": str(line.pk)})

        return Response(
            {
                "rfq_id": str(nimble_rfq.pk),
                "listing_id": str(listing.pk),
                "lines": lines_out,
            },
            status=201,
        )


class NimbleQuoteResponseView(APIView):
    """
    POST /api/v1/integrations/nimble/rfqs/responses/

    Payload:
    {
        "project_id": str,
        "responses": [
            {
                "element_id": str,
                "supplier_name": str,
                "moq": int,
                "lead_time": int,
                "qty_range1".."qty_range8": int,
                "price_range1".."price_range8": str (decimal),
                "date_code": int,
                "packaging": str
            }
        ]
    }

    Creates NimbleQuote + NimblePriceBreak rows.
    Returns: { "received": N }
    """

    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        from integrations.models import NimblePriceBreak, NimbleQuote, NimbleRFQ, NimbleSyncLog
        from listings.models import ListingLine

        data = request.data
        project_id = data.get("project_id", "")
        responses = data.get("responses", [])

        req_hash = hashlib.sha256(json.dumps(data, sort_keys=True, default=str).encode()).hexdigest()

        try:
            nimble_rfq = NimbleRFQ.objects.get(nimble_rfq_id=project_id)
        except NimbleRFQ.DoesNotExist:
            NimbleSyncLog.objects.create(
                direction="pull",
                request_hash=req_hash,
                status_code=404,
                error=f"NimbleRFQ not found for project_id={project_id}",
            )
            return Response({"detail": f"NimbleRFQ not found for project_id={project_id}"}, status=404)

        # Build element_id → line mapping
        lines_qs = ListingLine.objects.filter(listing=nimble_rfq.listing)
        # element_id is stored as the line order (line_no corresponds to element index)
        # We'll look up by nimble_rfq lines in order
        all_lines = list(lines_qs.order_by("line_no"))
        line_by_element: dict = {}
        for line in all_lines:
            # element_id lookup: we store line_no = element position index
            line_by_element[str(line.line_no)] = line

        received = 0
        with transaction.atomic():
            for resp in responses:
                element_id = str(resp.get("element_id", ""))
                line = line_by_element.get(element_id)
                if line is None:
                    logger.warning("NimbleQuoteResponse: no line for element_id=%s", element_id)
                    continue

                nimble_quote_id = f"{project_id}_{element_id}_{resp.get('supplier_name', '')}".replace(" ", "_")

                quote, _ = NimbleQuote.objects.get_or_create(
                    nimble_quote_id=nimble_quote_id,
                    defaults={
                        "rfq": nimble_rfq,
                        "line": line,
                        "supplier_name_raw": resp.get("supplier_name", ""),
                        "moq": int(resp.get("moq", 1)),
                        "lead_time_days": int(resp.get("lead_time", 0)),
                        "date_code_year": resp.get("date_code") or None,
                        "packaging": resp.get("packaging", ""),
                        "status": NimbleQuote.Status.RECEIVED,
                    },
                )

                # Create price breaks from qty_range/price_range pairs
                for i in range(1, 9):
                    qty = resp.get(f"qty_range{i}")
                    price = resp.get(f"price_range{i}")
                    if qty and price:
                        try:
                            NimblePriceBreak.objects.get_or_create(
                                quote=quote,
                                min_qty=int(qty),
                                defaults={"unit_price": price},
                            )
                        except Exception as exc:
                            logger.warning("NimblePriceBreak error: %s", exc)

                received += 1

        # Update last_pulled_at
        from django.utils import timezone
        nimble_rfq.last_pulled_at = timezone.now()
        nimble_rfq.save(update_fields=["last_pulled_at", "updated_at"])

        NimbleSyncLog.objects.create(direction="pull", request_hash=req_hash, status_code=200)

        return Response({"received": received})
