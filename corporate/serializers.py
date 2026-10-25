"""
Corporate serializers.
"""

from decimal import Decimal

from rest_framework import serializers

from .models import ApprovalRequest, Budget, Invitation, OrderLimit, ShipToAssignment


class InvitationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Invitation
        fields = ["id", "company", "email", "role", "expires_at", "accepted_at"]
        read_only_fields = ["id", "expires_at", "accepted_at"]


class BudgetSerializer(serializers.ModelSerializer):
    spent_this_period = serializers.SerializerMethodField()

    class Meta:
        model = Budget
        fields = [
            "id", "member", "period_start", "period",
            "amount", "currency", "spent_this_period",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def get_spent_this_period(self, obj) -> Decimal:
        from django.db.models import Sum
        from django.utils import timezone
        from orders.models import Order

        today = timezone.now().date()
        period_start = obj.period_start

        spent = (
            Order.objects.filter(
                placed_by=obj.member.user,
                buyer_company=obj.member.company,
                paid_at__date__gte=period_start,
            ).exclude(
                status__in=[Order.Status.CANCELLED, Order.Status.REFUNDED]
            ).aggregate(total=Sum("grand_total"))["total"]
            or Decimal("0.00")
        )
        return spent


class OrderLimitSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderLimit
        fields = ["id", "member", "max_order_amount", "currency", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]


class ApprovalRequestSerializer(serializers.ModelSerializer):
    requested_by_name = serializers.CharField(
        source="requested_by.full_name", read_only=True
    )
    approver_name = serializers.SerializerMethodField()

    class Meta:
        model = ApprovalRequest
        fields = [
            "id", "company", "requested_by", "requested_by_name",
            "approver", "approver_name", "subject_type",
            "listing", "order", "amount", "status",
            "decided_at", "note", "created_at", "updated_at",
        ]
        read_only_fields = [
            "id", "requested_by_name", "approver_name",
            "decided_at", "created_at", "updated_at",
        ]

    def get_approver_name(self, obj) -> str:
        if obj.approver:
            return obj.approver.full_name
        return ""


class AddressNestedSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    line1 = serializers.CharField()
    line2 = serializers.CharField()
    city = serializers.CharField()
    state = serializers.CharField()
    postal_code = serializers.CharField()
    country = serializers.CharField()
    address_type = serializers.CharField()


class ShipToAssignmentSerializer(serializers.ModelSerializer):
    address_detail = AddressNestedSerializer(source="address", read_only=True)

    class Meta:
        model = ShipToAssignment
        fields = ["id", "member", "address", "address_detail", "created_at"]
        read_only_fields = ["id", "created_at"]


class SpendingReportSerializer(serializers.Serializer):
    member_name = serializers.CharField()
    role = serializers.CharField()
    order_count = serializers.IntegerField()
    total_spent = serializers.DecimalField(max_digits=14, decimal_places=2)
    currency = serializers.CharField()
