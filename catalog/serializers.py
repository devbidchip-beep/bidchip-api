from rest_framework import serializers

from .models import InventoryImport, InventoryItem, Manufacturer, Part


class ManufacturerSerializer(serializers.ModelSerializer):
    logo_url = serializers.SerializerMethodField()

    class Meta:
        model = Manufacturer
        fields = ["id", "name", "name_normalized", "logo_url", "is_active"]

    def get_logo_url(self, obj):
        if not obj.logo:
            return None
        request = self.context.get("request")
        if request:
            return request.build_absolute_uri(obj.logo)
        return obj.logo


class PartSerializer(serializers.ModelSerializer):
    manufacturer = ManufacturerSerializer(read_only=True)

    class Meta:
        model = Part
        fields = [
            "id",
            "mpn",
            "mpn_normalized",
            "manufacturer",
            "description",
            "category",
            "lifecycle",
            "eccn",
            "is_itar",
            "hts_code",
        ]


class PartSearchResultSerializer(serializers.ModelSerializer):
    """Lightweight serializer for part search results."""
    manufacturer_name = serializers.CharField(source="manufacturer.name", read_only=True)

    class Meta:
        model = Part
        fields = [
            "id",
            "mpn",
            "manufacturer_name",
            "description",
            "category",
            "lifecycle",
        ]


class InventoryItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = InventoryItem
        fields = [
            "id",
            "company",
            "part",
            "mpn_raw",
            "manufacturer_raw",
            "manufacturer",
            "quantity",
            "date_code_year",
            "packaging",
            "unit_price",
            "currency",
            "ship_from_country",
            "source",
            "import_job",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]


class InventoryImportSerializer(serializers.ModelSerializer):
    error_report_url = serializers.SerializerMethodField()

    class Meta:
        model = InventoryImport
        fields = [
            "id",
            "status",
            "rows_total",
            "rows_ok",
            "rows_failed",
            "error_report_url",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_error_report_url(self, obj):
        if not obj.error_report:
            return None
        # Return the S3 key — callers can generate a presigned URL as needed
        return obj.error_report
