from rest_framework import serializers

from bidding.models import Award, Bid


class BidSerializer(serializers.ModelSerializer):
    """
    Full bid serializer. supplier_company name is shown only to staff/owner;
    anonymous listings hide it from other suppliers.
    """

    supplier_company_name = serializers.SerializerMethodField()

    class Meta:
        model = Bid
        fields = [
            "id",
            "line",
            "supplier_company",
            "supplier_company_name",
            "placed_by",
            "unit_price",
            "quantity_offered",
            "date_code_year",
            "packaging",
            "lead_time_days",
            "inventory_item",
            "is_exact_match",
            "exception_reasons",
            "status",
            "commitment_hash",
            "supplier_net_shown",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_supplier_company_name(self, obj):
        request = self.context.get("request")
        if request is None:
            return None
        user = request.user
        # Staff always see the name
        if user.is_staff:
            return obj.supplier_company.legal_name
        # Owner (member of the supplier company) sees it
        if user.memberships.filter(company=obj.supplier_company, status="active").exists():
            return obj.supplier_company.legal_name
        # Buyer who owns the listing sees it
        listing = obj.line.listing
        if user.memberships.filter(company=listing.buyer_company, status="active").exists():
            return obj.supplier_company.legal_name
        # Anonymous — hide company identity
        return None


class PlaceBidSerializer(serializers.Serializer):
    line = serializers.UUIDField()
    unit_price = serializers.DecimalField(max_digits=14, decimal_places=4)
    quantity_offered = serializers.IntegerField(min_value=1)
    date_code_year = serializers.IntegerField(required=False, allow_null=True)
    packaging = serializers.ChoiceField(
        choices=Bid.Packaging.choices, required=False, allow_null=True
    )
    lead_time_days = serializers.IntegerField(required=False, default=0, min_value=0)

    def validate_unit_price(self, value):
        if value <= 0:
            raise serializers.ValidationError("Unit price must be greater than zero.")
        return value


class AwardSerializer(serializers.ModelSerializer):
    class Meta:
        model = Award
        fields = [
            "id",
            "line",
            "bid",
            "quantity_awarded",
            "unit_price",
            "rank",
            "awarded_by",
            "awarded_at",
            "status",
            "created_at",
        ]
        read_only_fields = fields
