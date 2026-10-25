"""
Trust serializers: Dispute, Rating, Message, MessageThread, RiskAssessment.
"""

from decimal import Decimal

from rest_framework import serializers

from trust.models import (
    Dispute,
    DisputeFile,
    Message,
    MessageThread,
    Rating,
    RiskAssessment,
)


# ---------------------------------------------------------------------------
# Dispute
# ---------------------------------------------------------------------------

class DisputeSerializer(serializers.ModelSerializer):
    supplier_order = serializers.UUIDField(source="supplier_order_id", read_only=True)
    opened_by_name = serializers.CharField(source="opened_by.full_name", read_only=True)
    opened_by_role = serializers.SerializerMethodField()

    class Meta:
        model = Dispute
        fields = [
            "id",
            "supplier_order",
            "opened_by",
            "opened_by_name",
            "opened_by_role",
            "reason",
            "description",
            "status",
            "resolution_note",
            "resolved_by",
            "opened_at",
            "resolved_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_opened_by_role(self, obj):
        membership = obj.opened_by.memberships.filter(
            company=obj.supplier_order.order.buyer_company
        ).first()
        return membership.role if membership else None


class DisputeCreateSerializer(serializers.Serializer):
    supplier_order = serializers.UUIDField()
    reason = serializers.ChoiceField(choices=Dispute.Reason.choices)
    description = serializers.CharField()


# ---------------------------------------------------------------------------
# Rating
# ---------------------------------------------------------------------------

class RatingSerializer(serializers.ModelSerializer):
    average_score = serializers.SerializerMethodField()

    class Meta:
        model = Rating
        fields = [
            "id",
            "supplier_order",
            "legacy_ref",
            "rater_company",
            "ratee_company",
            "direction",
            "quality",
            "communication",
            "shipping",
            "documentation",
            "comment",
            "average_score",
            "created_at",
        ]
        read_only_fields = fields

    def get_average_score(self, obj):
        total = obj.quality + obj.communication + obj.shipping + obj.documentation
        return round(total / 4, 2)


class RatingCreateSerializer(serializers.Serializer):
    supplier_order = serializers.UUIDField()
    direction = serializers.ChoiceField(choices=Rating.Direction.choices)
    quality = serializers.IntegerField(min_value=1, max_value=5)
    communication = serializers.IntegerField(min_value=1, max_value=5)
    shipping = serializers.IntegerField(min_value=1, max_value=5)
    documentation = serializers.IntegerField(min_value=1, max_value=5)
    comment = serializers.CharField(required=False, allow_blank=True, default="")


# ---------------------------------------------------------------------------
# Message / MessageThread
# ---------------------------------------------------------------------------

class MessageSerializer(serializers.ModelSerializer):
    body = serializers.SerializerMethodField()
    moderation_status = serializers.SerializerMethodField()
    is_own = serializers.SerializerMethodField()

    class Meta:
        model = Message
        fields = [
            "id",
            "body",
            "moderation_status",
            "sent_at",
            "is_own",
        ]

    def get_body(self, obj):
        request = self.context.get("request")
        if obj.moderation_status == Message.ModerationStatus.PENDING:
            if request and request.user.is_staff:
                return obj.body
            # Show masked body if sender is viewing their own pending message
            if request and obj.sender_id == request.user.id:
                return obj.body
            return "[pending moderation]"
        return obj.body

    def get_moderation_status(self, obj):
        request = self.context.get("request")
        if request and request.user.is_staff:
            return obj.moderation_status
        return None

    def get_is_own(self, obj):
        request = self.context.get("request")
        if request:
            return obj.sender_id == request.user.id
        return False


class MessageThreadSerializer(serializers.ModelSerializer):
    messages = serializers.SerializerMethodField()

    class Meta:
        model = MessageThread
        fields = [
            "id",
            "status",
            "listing",
            "supplier_order",
            "buyer_company",
            "supplier_company",
            "created_at",
            "updated_at",
            "messages",
        ]
        read_only_fields = fields

    def get_messages(self, obj):
        request = self.context.get("request")
        qs = obj.messages.all()
        if request and not request.user.is_staff:
            qs = qs.filter(moderation_status=Message.ModerationStatus.APPROVED)
        return MessageSerializer(qs, many=True, context=self.context).data


# ---------------------------------------------------------------------------
# RiskAssessment
# ---------------------------------------------------------------------------

class RiskAssessmentSerializer(serializers.ModelSerializer):
    factors = serializers.SerializerMethodField()

    class Meta:
        model = RiskAssessment
        fields = [
            "id",
            "supplier_order",
            "score",
            "tier",
            "factors",
            "override_tier",
            "overridden_by",
            "override_reason",
            "assessed_at",
            "created_at",
        ]
        read_only_fields = [
            "id", "supplier_order", "score", "tier", "assessed_at", "created_at"
        ]

    def get_factors(self, obj):
        request = self.context.get("request")
        if request and request.user.is_staff:
            return obj.factors
        return None
