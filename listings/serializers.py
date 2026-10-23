from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from catalog.models import Manufacturer, Part
from catalog.utils import normalize_mpn

from .models import ComplianceScreening, Listing, ListingInvite, ListingLine


class ListingLineSerializer(serializers.ModelSerializer):
    part_mpn = serializers.CharField(source="part.mpn", read_only=True, allow_null=True)
    manufacturer_name = serializers.CharField(
        source="manufacturer.name", read_only=True, allow_null=True
    )

    class Meta:
        model = ListingLine
        fields = [
            "id",
            "listing",
            "line_no",
            "part",
            "part_mpn",
            "mpn_raw",
            "manufacturer_raw",
            "manufacturer",
            "manufacturer_name",
            "quantity",
            "target_unit_price",
            "date_code_year_min",
            "packaging",
            "allow_exceptions",
            "allow_split",
            "require_as6081",
            "lab_method",
            "docs_required",
            "ncnr",
            "compliance_status",
            "status",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]


class ListingSerializer(serializers.ModelSerializer):
    lines = ListingLineSerializer(many=True, read_only=True)

    class Meta:
        model = Listing
        fields = [
            "id",
            "number",
            "kind",
            "status",
            "buyer_company",
            "created_by",
            "source",
            "intake",
            "title",
            "starts_at",
            "duration_minutes",
            "ends_at",
            "invite_only",
            "anonymous",
            "ship_to",
            "currency",
            "published_at",
            "closed_at",
            "created_at",
            "updated_at",
            "lines",
        ]
        read_only_fields = [
            "number",
            "ends_at",
            "published_at",
            "closed_at",
            "created_at",
            "updated_at",
        ]


class ListingLineCreateSerializer(serializers.Serializer):
    """Used inside ListingCreateSerializer for each line item."""
    mpn_raw = serializers.CharField(max_length=120)
    manufacturer_raw = serializers.CharField(max_length=255, default="", allow_blank=True)
    quantity = serializers.IntegerField(min_value=1)
    target_unit_price = serializers.DecimalField(
        max_digits=14, decimal_places=4, required=False, allow_null=True
    )
    date_code_year_min = serializers.IntegerField(required=False, allow_null=True)
    packaging = serializers.ChoiceField(
        choices=ListingLine.Packaging.choices, required=False, allow_null=True
    )
    allow_exceptions = serializers.BooleanField(default=True)
    allow_split = serializers.BooleanField(default=True)
    require_as6081 = serializers.BooleanField(default=False)
    lab_method = serializers.CharField(max_length=100, default="", allow_blank=True)
    docs_required = serializers.BooleanField(default=False)
    ncnr = serializers.BooleanField(default=False)


class ListingCreateSerializer(serializers.Serializer):
    """
    Creates a Listing plus its ListingLines in a single transaction.
    Auto-matches each line's mpn_raw to a catalog Part via normalize_mpn lookup.
    """
    title = serializers.CharField(max_length=200)
    kind = serializers.ChoiceField(choices=Listing.Kind.choices)
    duration_minutes = serializers.IntegerField(default=4320, min_value=1)
    ship_to = serializers.UUIDField(required=False, allow_null=True)
    currency = serializers.CharField(max_length=3, default="USD")
    lines = ListingLineCreateSerializer(many=True, min_length=1)

    def create(self, validated_data):
        lines_data = validated_data.pop("lines")
        ship_to_id = validated_data.pop("ship_to", None)
        request = self.context["request"]

        with transaction.atomic():
            listing = Listing.objects.create(
                buyer_company=request.user.memberships.filter(
                    status="active"
                ).first().company,
                created_by=request.user,
                ship_to_id=ship_to_id,
                **validated_data,
            )

            for line_no, line_data in enumerate(lines_data, start=1):
                mpn_raw = line_data["mpn_raw"]
                manufacturer_raw = line_data.get("manufacturer_raw", "")

                # Auto-match mpn_raw to catalog Part
                mpn_normalized = normalize_mpn(mpn_raw)
                part = None
                manufacturer = None

                matched_part = Part.objects.filter(
                    mpn_normalized=mpn_normalized
                ).select_related("manufacturer").first()

                if matched_part:
                    part = matched_part
                    manufacturer = matched_part.manufacturer
                elif manufacturer_raw:
                    from catalog.utils import normalize_name
                    name_norm = normalize_name(manufacturer_raw)
                    manufacturer = Manufacturer.objects.filter(
                        name_normalized=name_norm
                    ).first()

                ListingLine.objects.create(
                    listing=listing,
                    line_no=line_no,
                    part=part,
                    manufacturer=manufacturer,
                    **{k: v for k, v in line_data.items()},
                )

        return listing


class ListingPublishSerializer(serializers.ModelSerializer):
    """Validates and executes the transition to 'published' status."""

    class Meta:
        model = Listing
        fields = ["status", "starts_at"]

    def validate(self, data):
        listing = self.instance
        if listing.status not in (Listing.Status.DRAFT, Listing.Status.PENDING_APPROVAL):
            raise serializers.ValidationError(
                "Only draft or pending_approval listings can be published."
            )
        if listing.lines.filter(
            compliance_status=ListingLine.ComplianceStatus.REJECTED
        ).exists():
            raise serializers.ValidationError(
                "Cannot publish: one or more lines have a rejected compliance status."
            )
        return data

    def update(self, instance, validated_data):
        instance.status = Listing.Status.PUBLISHED
        instance.published_at = timezone.now()
        if validated_data.get("starts_at"):
            instance.starts_at = validated_data["starts_at"]
        # ends_at is computed in Listing.save()
        instance.save()
        return instance
