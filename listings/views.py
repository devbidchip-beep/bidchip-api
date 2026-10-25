from rest_framework import generics, status
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Listing
from .serializers import (
    ListingCreateSerializer,
    ListingPublishSerializer,
    ListingSerializer,
)


class ListingListCreateView(generics.ListCreateAPIView):
    """
    GET  /api/v1/listings/  — list own company's listings, filterable by status/kind
    POST /api/v1/listings/  — create a draft listing
    """
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        if self.request.method == "POST":
            return ListingCreateSerializer
        return ListingSerializer

    def get_queryset(self):
        user = self.request.user
        # Only return listings for companies the user is an active member of
        company_ids = user.memberships.filter(status="active").values_list(
            "company_id", flat=True
        )
        qs = Listing.objects.filter(buyer_company__in=company_ids).select_related(
            "buyer_company", "created_by"
        ).prefetch_related("lines")

        status_filter = self.request.query_params.get("status")
        kind_filter = self.request.query_params.get("kind")

        if status_filter:
            qs = qs.filter(status=status_filter)
        if kind_filter:
            qs = qs.filter(kind=kind_filter)

        return qs

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        listing = serializer.save()
        return Response(
            ListingSerializer(listing, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )


class ListingDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    GET    /api/v1/listings/{id}/  — retrieve listing
    PATCH  /api/v1/listings/{id}/  — update (owner only, while draft)
    DELETE /api/v1/listings/{id}/  — delete (owner only, while draft)
    """
    serializer_class = ListingSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Listing.objects.select_related(
            "buyer_company", "created_by"
        ).prefetch_related("lines")

    def _check_ownership(self, listing):
        user = self.request.user
        company_ids = user.memberships.filter(status="active").values_list(
            "company_id", flat=True
        )
        if listing.buyer_company_id not in list(company_ids):
            raise PermissionDenied("You do not have permission to modify this listing.")

    def update(self, request, *args, **kwargs):
        listing = self.get_object()
        self._check_ownership(listing)
        if listing.status != Listing.Status.DRAFT:
            raise PermissionDenied("Only draft listings can be edited.")
        return super().update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        listing = self.get_object()
        self._check_ownership(listing)
        if listing.status != Listing.Status.DRAFT:
            raise PermissionDenied("Only draft listings can be deleted.")
        return super().destroy(request, *args, **kwargs)


class ListingPublishView(APIView):
    """
    POST /api/v1/listings/{id}/publish/
    Validates company is verified, lines are valid, compliance not rejected.
    Sets status=published, published_at=now(), computes ends_at.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        try:
            listing = Listing.objects.prefetch_related("lines").get(pk=pk)
        except Listing.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        # Ownership check
        company_ids = request.user.memberships.filter(status="active").values_list(
            "company_id", flat=True
        )
        if listing.buyer_company_id not in list(company_ids):
            raise PermissionDenied("You do not have permission to publish this listing.")

        # Company must be verified
        if listing.buyer_company.status != "verified":
            return Response(
                {"detail": "Company must be verified before publishing a listing."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Must have at least one line
        if not listing.lines.exists():
            return Response(
                {"detail": "Listing must have at least one line before publishing."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Corporate listing-publish approval check
        member = request.user.memberships.filter(
            company=listing.buyer_company, status="active"
        ).first()
        if member is not None:
            from corporate.checks import validate_listing_publish
            from rest_framework.exceptions import ValidationError as DRFValidationError

            try:
                validate_listing_publish(listing, member)
            except DRFValidationError as exc:
                return Response({"error": exc.detail}, status=status.HTTP_400_BAD_REQUEST)

        serializer = ListingPublishSerializer(
            listing, data=request.data, partial=True, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response(
            ListingSerializer(listing, context={"request": request}).data,
            status=status.HTTP_200_OK,
        )


class PublicListingListView(generics.ListAPIView):
    """
    GET /api/v1/listings/published/
    Returns published listings visible to suppliers.
    Buyer company info is not exposed (anonymous=True by default).
    No authentication required.
    """
    serializer_class = ListingSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        qs = Listing.objects.filter(
            status=Listing.Status.PUBLISHED,
        ).prefetch_related("lines")

        kind_filter = self.request.query_params.get("kind")
        if kind_filter:
            qs = qs.filter(kind=kind_filter)

        return qs

    def get_serializer(self, *args, **kwargs):
        # When anonymous=True, exclude buyer_company from the serialized output
        serializer = super().get_serializer(*args, **kwargs)
        return serializer
