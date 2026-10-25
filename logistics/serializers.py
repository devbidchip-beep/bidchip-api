"""
Serializers for the logistics app.
"""

import boto3
from django.conf import settings
from rest_framework import serializers

from logistics.models import (
    Inspection,
    InspectionPhoto,
    LabTest,
    Package,
    RateQuote,
    Shipment,
)


def _generate_signed_url(s3_key: str, expiry: int = 3600) -> str:
    """Generate a signed S3 URL for the given key. Returns empty string on error."""
    if not s3_key:
        return ""
    try:
        client = boto3.client(
            "s3",
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_S3_REGION_NAME,
        )
        return client.generate_presigned_url(
            "get_object",
            Params={"Bucket": settings.AWS_STORAGE_BUCKET_NAME, "Key": s3_key},
            ExpiresIn=expiry,
        )
    except Exception:
        return ""


class PackageSerializer(serializers.ModelSerializer):
    class Meta:
        model = Package
        fields = [
            "id",
            "shipment",
            "length_cm",
            "width_cm",
            "height_cm",
            "weight_kg",
            "sized_by",
            "contents",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]


class RateQuoteSerializer(serializers.ModelSerializer):
    class Meta:
        model = RateQuote
        fields = [
            "id",
            "shipment",
            "carrier",
            "service_code",
            "service_name",
            "amount",
            "currency",
            "transit_days",
            "is_next_day",
            "chosen",
            "quoted_at",
        ]
        read_only_fields = ["id", "quoted_at"]


class ShipmentSerializer(serializers.ModelSerializer):
    packages = PackageSerializer(many=True, read_only=True)
    rate_quotes = RateQuoteSerializer(many=True, read_only=True)

    class Meta:
        model = Shipment
        fields = [
            "id",
            "leg",
            "order",
            "supplier_order",
            "dispute",
            "carrier",
            "service_code",
            "tracking_number",
            "label",
            "po_number_on_label",
            "paid_by",
            "cost_estimated",
            "cost_actual",
            "status",
            "shipped_at",
            "delivered_at",
            "is_partial",
            "created_at",
            "updated_at",
            "packages",
            "rate_quotes",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class InspectionPhotoSerializer(serializers.ModelSerializer):
    file_url = serializers.SerializerMethodField()

    class Meta:
        model = InspectionPhoto
        fields = ["id", "file_url", "caption", "order_line", "created_at"]
        read_only_fields = ["id", "created_at"]

    def get_file_url(self, obj) -> str:
        return _generate_signed_url(obj.file)


class InspectionSerializer(serializers.ModelSerializer):
    photos = InspectionPhotoSerializer(many=True, read_only=True)

    class Meta:
        model = Inspection
        fields = [
            "id",
            "supplier_order",
            "inspector",
            "level",
            "result",
            "notes",
            "counted_quantity",
            "inspected_at",
            "created_at",
            "updated_at",
            "photos",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class LabTestSerializer(serializers.ModelSerializer):
    class Meta:
        model = LabTest
        fields = [
            "id",
            "order_line",
            "lab_user",
            "method",
            "price",
            "result",
            "report",
            "completed_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]
