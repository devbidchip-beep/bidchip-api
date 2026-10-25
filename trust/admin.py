"""
Trust admin: Dispute, Rating, Message, SellerChainEvent, RiskAssessment.
"""

from django.contrib import admin

from trust.models import (
    Dispute,
    DisputeFile,
    Message,
    MessageThread,
    Rating,
    RiskAssessment,
    SellerChainEvent,
)


# ---------------------------------------------------------------------------
# DisputeAdmin
# ---------------------------------------------------------------------------

@admin.register(Dispute)
class DisputeAdmin(admin.ModelAdmin):
    list_display = ["supplier_order", "reason", "status", "opened_by", "opened_at"]
    list_filter = ["status", "reason"]
    search_fields = ["description"]
    readonly_fields = ["id", "opened_at", "resolved_at", "created_at", "updated_at"]
    actions = ["mark_under_review"]

    @admin.action(description="Mark selected disputes as under review")
    def mark_under_review(self, request, queryset):
        updated = queryset.filter(
            status__in=[Dispute.Status.OPEN, Dispute.Status.AWAITING_RETURN]
        ).update(status=Dispute.Status.UNDER_REVIEW)
        self.message_user(request, f"{updated} dispute(s) marked as under review.")


@admin.register(DisputeFile)
class DisputeFileAdmin(admin.ModelAdmin):
    list_display = ["dispute", "uploaded_by", "created_at"]
    readonly_fields = ["id", "created_at"]


# ---------------------------------------------------------------------------
# RatingAdmin
# ---------------------------------------------------------------------------

@admin.register(Rating)
class RatingAdmin(admin.ModelAdmin):
    list_display = ["ratee_company", "direction", "quality", "communication", "created_at"]
    list_filter = ["direction"]
    readonly_fields = ["supplier_order", "id", "created_at"]


# ---------------------------------------------------------------------------
# MessageAdmin
# ---------------------------------------------------------------------------

@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ["thread", "sender", "moderation_status", "sent_at"]
    list_filter = ["moderation_status"]
    readonly_fields = ["id", "sent_at", "created_at"]
    actions = ["approve_messages", "block_messages"]

    @admin.action(description="Approve selected messages")
    def approve_messages(self, request, queryset):
        from trust.services import moderate_message
        count = 0
        for message in queryset.filter(moderation_status=Message.ModerationStatus.PENDING):
            moderate_message(message=message, moderator=request.user, approved=True)
            count += 1
        self.message_user(request, f"{count} message(s) approved.")

    @admin.action(description="Block selected messages")
    def block_messages(self, request, queryset):
        from trust.services import moderate_message
        count = 0
        for message in queryset.filter(moderation_status=Message.ModerationStatus.PENDING):
            moderate_message(message=message, moderator=request.user, approved=False)
            count += 1
        self.message_user(request, f"{count} message(s) blocked.")


@admin.register(MessageThread)
class MessageThreadAdmin(admin.ModelAdmin):
    list_display = ["id", "buyer_company", "supplier_company", "status", "created_at"]
    list_filter = ["status"]
    readonly_fields = ["id", "created_at", "updated_at"]


# ---------------------------------------------------------------------------
# SellerChainEventAdmin — insert-only, no add/change
# ---------------------------------------------------------------------------

@admin.register(SellerChainEvent)
class SellerChainEventAdmin(admin.ModelAdmin):
    list_display = ["supplier_company", "seq", "event_type", "created_at"]
    readonly_fields = [
        "id",
        "supplier_company",
        "seq",
        "event_type",
        "ref_type",
        "ref_id",
        "payload_hash",
        "prev_hash",
        "hash",
        "kms_sig",
        "created_at",
    ]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


# ---------------------------------------------------------------------------
# RiskAssessmentAdmin
# ---------------------------------------------------------------------------

@admin.register(RiskAssessment)
class RiskAssessmentAdmin(admin.ModelAdmin):
    list_display = ["supplier_order", "tier", "score", "override_tier", "assessed_at"]
    list_filter = ["tier"]
    readonly_fields = ["id", "supplier_order", "score", "tier", "factors", "assessed_at", "created_at"]
