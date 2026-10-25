import uuid

import boto3
from django.conf import settings
from rest_framework import generics, filters, status
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle, UserRateThrottle
from rest_framework.views import APIView

from .models import InventoryImport, InventoryItem, Manufacturer, Part
from .serializers import (
    InventoryImportSerializer,
    InventoryItemSerializer,
    ManufacturerSerializer,
    PartSearchResultSerializer,
    PartSerializer,
)
from .utils import normalize_mpn


class PartSearchAnonThrottle(AnonRateThrottle):
    rate = "10/min"


class PartSearchUserThrottle(UserRateThrottle):
    rate = "60/min"


class PartSearchView(generics.ListAPIView):
    """
    GET /api/v1/catalog/parts/search/?q=LM317T&limit=20

    Searches parts using trigram similarity on mpn_normalized.
    Falls back to icontains if q < 3 characters.
    """
    serializer_class = PartSearchResultSerializer
    permission_classes = [AllowAny]
    throttle_classes = [PartSearchAnonThrottle, PartSearchUserThrottle]

    def get_queryset(self):
        q = self.request.query_params.get("q", "").strip()
        limit = int(self.request.query_params.get("limit", 20))
        limit = min(limit, 100)  # cap at 100

        if not q:
            return Part.objects.none()

        q_normalized = normalize_mpn(q)

        if len(q_normalized) < 3:
            qs = Part.objects.filter(
                mpn_normalized__icontains=q_normalized
            ).select_related("manufacturer")
        else:
            qs = Part.objects.filter(
                mpn_normalized__trigram_similar=q_normalized
            ).select_related("manufacturer")

        return qs[:limit]


class PartDetailView(generics.RetrieveAPIView):
    """
    GET /api/v1/catalog/parts/{id}/
    """
    queryset = Part.objects.select_related("manufacturer")
    serializer_class = PartSerializer
    permission_classes = [AllowAny]


class ManufacturerListView(generics.ListAPIView):
    """
    GET /api/v1/catalog/manufacturers/?search=texas
    """
    serializer_class = ManufacturerSerializer
    permission_classes = [AllowAny]
    filter_backends = [filters.SearchFilter]
    search_fields = ["name", "name_normalized"]

    def get_queryset(self):
        qs = Manufacturer.objects.filter(is_active=True)
        search = self.request.query_params.get("search", "").strip()
        if search:
            qs = qs.filter(name_normalized__icontains=search.upper())
        return qs


# ---------------------------------------------------------------------------
# Inventory REST API
# ---------------------------------------------------------------------------

class IsSupplierPermission(IsAuthenticated):
    """Allow access only to users whose company is_supplier=True."""

    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False
        membership = (
            request.user.memberships.filter(status="active")
            .select_related("company")
            .first()
        )
        return membership is not None and membership.company.is_supplier


class InventoryItemListCreateView(generics.ListCreateAPIView):
    """
    GET  /api/v1/catalog/inventory/   — list current company's active inventory
    POST /api/v1/catalog/inventory/   — create a single inventory item
    Permission: IsAuthenticated + is_supplier
    """

    serializer_class = InventoryItemSerializer
    permission_classes = [IsSupplierPermission]

    def get_queryset(self):
        membership = (
            self.request.user.memberships.filter(status="active")
            .select_related("company")
            .first()
        )
        if not membership:
            return InventoryItem.objects.none()
        return InventoryItem.objects.filter(
            company=membership.company, is_active=True
        ).select_related("part", "manufacturer")

    def perform_create(self, serializer):
        membership = (
            self.request.user.memberships.filter(status="active")
            .select_related("company")
            .first()
        )
        serializer.save(
            company=membership.company,
            source=InventoryItem.Source.MANUAL,
        )


class InventoryItemDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    GET    /api/v1/catalog/inventory/{id}/
    PATCH  /api/v1/catalog/inventory/{id}/
    DELETE /api/v1/catalog/inventory/{id}/  — soft delete (sets is_active=False)
    """

    serializer_class = InventoryItemSerializer
    permission_classes = [IsSupplierPermission]

    def get_queryset(self):
        membership = (
            self.request.user.memberships.filter(status="active")
            .select_related("company")
            .first()
        )
        if not membership:
            return InventoryItem.objects.none()
        return InventoryItem.objects.filter(company=membership.company)

    def perform_destroy(self, instance):
        """Soft delete — set is_active=False instead of deleting."""
        instance.is_active = False
        instance.save(update_fields=["is_active", "updated_at"])


class InventoryBulkUploadView(APIView):
    """
    POST /api/v1/catalog/inventory/upload/

    Accepts CSV file upload (multipart).
    Creates InventoryImport job and queues process_inventory_import Celery task.
    Returns { import_id, status: 'queued' }.
    """

    parser_classes = [MultiPartParser]
    permission_classes = [IsSupplierPermission]

    def post(self, request, *args, **kwargs):
        from .tasks import process_inventory_import

        file_obj = request.FILES.get("file")
        if not file_obj:
            return Response(
                {"detail": "No file provided."}, status=status.HTTP_400_BAD_REQUEST
            )

        if not file_obj.name.lower().endswith(".csv"):
            return Response(
                {"detail": "Only CSV files are accepted."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        membership = (
            request.user.memberships.filter(status="active")
            .select_related("company")
            .first()
        )
        company = membership.company

        # Upload CSV to S3
        s3_key = f"inventory_imports/{company.pk}/{uuid.uuid4().hex[:8]}_{file_obj.name}"
        try:
            s3 = boto3.client(
                "s3",
                aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
                region_name=settings.AWS_S3_REGION_NAME,
            )
            s3.upload_fileobj(
                file_obj,
                settings.AWS_STORAGE_BUCKET_NAME,
                s3_key,
                ExtraArgs={"ContentType": "text/csv"},
            )
        except Exception as exc:
            import logging
            logging.getLogger(__name__).exception("InventoryBulkUploadView: S3 upload failed: %s", exc)
            return Response(
                {"detail": "File upload failed. Please try again."},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        import_job = InventoryImport.objects.create(
            company=company,
            source=InventoryImport.Source.CSV,
            file=s3_key,
            status=InventoryImport.Status.QUEUED,
        )

        process_inventory_import.delay(str(import_job.pk))

        return Response(
            {"import_id": str(import_job.pk), "status": "queued"},
            status=status.HTTP_202_ACCEPTED,
        )
