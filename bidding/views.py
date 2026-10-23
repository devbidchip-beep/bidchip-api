import uuid

from django.core.exceptions import ValidationError as DjangoValidationError
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from bidding.models import Award, Bid
from bidding.serializers import AwardSerializer, BidSerializer, PlaceBidSerializer
from bidding.services import award_line, place_bid, withdraw_bid
from listings.models import ListingLine


class IsVerifiedSupplier(IsAuthenticated):
    """Allows access only to authenticated users whose company is a verified supplier."""

    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False
        return request.user.memberships.filter(
            company__is_supplier=True,
            company__status="verified",
            status="active",
        ).exists()


class BidListView(APIView):
    """
    GET /api/v1/bidding/bids/?line={line_id}
    Returns bids for a line.
    - Suppliers see only their own bids.
    - Staff and buyer see all.
    Ordered by: is_exact_match desc, unit_price asc.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        line_id = request.query_params.get("line")
        if not line_id:
            return Response({"detail": "line query parameter is required."}, status=400)

        line = get_object_or_404(ListingLine, pk=line_id)
        qs = Bid.objects.filter(line=line).order_by("-is_exact_match", "unit_price")

        user = request.user
        is_staff = user.is_staff
        is_buyer = user.memberships.filter(
            company=line.listing.buyer_company, status="active"
        ).exists()

        if not is_staff and not is_buyer:
            # Supplier: only their own bids
            supplier_companies = user.memberships.filter(status="active").values_list(
                "company_id", flat=True
            )
            qs = qs.filter(supplier_company__in=supplier_companies)

        serializer = BidSerializer(qs, many=True, context={"request": request})
        return Response(serializer.data)


class PlaceBidView(APIView):
    """
    POST /api/v1/bidding/bids/
    Places a bid. Requires authenticated verified supplier.
    """

    permission_classes = [IsVerifiedSupplier]

    def post(self, request):
        serializer = PlaceBidSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        # Resolve line
        line = get_object_or_404(ListingLine, pk=data["line"])

        # Resolve supplier_company (first active verified supplier membership)
        membership = (
            request.user.memberships.filter(
                company__is_supplier=True,
                company__status="verified",
                status="active",
            )
            .select_related("company")
            .first()
        )
        supplier_company = membership.company

        try:
            bid = place_bid(
                line=line,
                supplier_company=supplier_company,
                placed_by=request.user,
                unit_price=data["unit_price"],
                quantity_offered=data["quantity_offered"],
                date_code_year=data.get("date_code_year"),
                packaging=data.get("packaging"),
                lead_time_days=data.get("lead_time_days", 0),
            )
        except DjangoValidationError as exc:
            return Response({"detail": exc.message}, status=status.HTTP_400_BAD_REQUEST)

        return Response(BidSerializer(bid, context={"request": request}).data, status=201)


class WithdrawBidView(APIView):
    """
    POST /api/v1/bidding/bids/{id}/withdraw/
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        bid = get_object_or_404(Bid, pk=pk)
        try:
            bid = withdraw_bid(bid, request.user)
        except DjangoValidationError as exc:
            return Response({"detail": exc.message}, status=status.HTTP_400_BAD_REQUEST)
        return Response(BidSerializer(bid, context={"request": request}).data)


class AwardLineView(APIView):
    """
    POST /api/v1/bidding/lines/{line_id}/award/
    Manually award a line (buyer chooses from bids/exceptions).
    Payload: { "awards": [{"bid": "<uuid>", "quantity": <int>}, ...] }
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, line_id):
        line = get_object_or_404(ListingLine, pk=line_id)

        # Must be listing owner company
        listing = line.listing
        is_buyer = request.user.memberships.filter(
            company=listing.buyer_company, status="active"
        ).exists()
        if not is_buyer and not request.user.is_staff:
            return Response(
                {"detail": "Only the listing owner can award lines."},
                status=status.HTTP_403_FORBIDDEN,
            )

        raw_awards = request.data.get("awards", [])
        if not raw_awards:
            return Response({"detail": "awards list is required."}, status=400)

        awards_input = []
        for entry in raw_awards:
            bid_pk = entry.get("bid")
            quantity = entry.get("quantity")
            if not bid_pk or not quantity:
                return Response(
                    {"detail": "Each award entry must have 'bid' and 'quantity'."},
                    status=400,
                )
            bid = get_object_or_404(Bid, pk=bid_pk)
            awards_input.append({"bid": bid, "quantity": int(quantity)})

        try:
            award_objects = award_line(line, awards_input, awarded_by=request.user)
        except DjangoValidationError as exc:
            return Response({"detail": exc.message}, status=status.HTTP_400_BAD_REQUEST)

        return Response(AwardSerializer(award_objects, many=True).data, status=201)
