"""
Corporate admin registrations.
"""

from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from .models import ApprovalRequest, Budget, Invitation, OrderLimit, ShipToAssignment


@admin.register(Invitation)
class InvitationAdmin(admin.ModelAdmin):
    list_display = ["company", "email", "role", "expires_at", "accepted_at"]
    list_filter = ["role"]
    search_fields = ["email"]


@admin.register(Budget)
class BudgetAdmin(admin.ModelAdmin):
    list_display = ["member", "period", "amount", "period_start"]
    list_filter = ["period"]


@admin.register(OrderLimit)
class OrderLimitAdmin(admin.ModelAdmin):
    list_display = ["member", "max_order_amount", "currency"]


@admin.register(ApprovalRequest)
class ApprovalRequestAdmin(admin.ModelAdmin):
    list_display = ["company", "requested_by", "subject_type", "status", "created_at"]
    list_filter = ["status", "subject_type"]
    actions = ["approve_requests"]

    @admin.action(description=_("Approve selected requests"))
    def approve_requests(self, request, queryset):
        updated = queryset.filter(status=ApprovalRequest.Status.PENDING).update(
            status=ApprovalRequest.Status.APPROVED,
        )
        self.message_user(request, f"{updated} request(s) approved.")


@admin.register(ShipToAssignment)
class ShipToAssignmentAdmin(admin.ModelAdmin):
    list_display = ["member", "address"]
