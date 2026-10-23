from django.contrib import admin

from payments.models import (
    LedgerEntry,
    LedgerJournal,
    Payment,
    Payout,
    Refund,
    StripeEvent,
)


class LedgerEntryInline(admin.TabularInline):
    model = LedgerEntry
    extra = 0
    readonly_fields = ("account", "debit", "credit", "currency")
    can_delete = False


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("id", "order", "method", "amount", "currency", "status", "created_at")
    list_filter = ("method", "status")
    search_fields = ("stripe_payment_intent", "stripe_charge", "wire_reference")
    readonly_fields = ("stripe_payment_intent", "stripe_charge")


@admin.register(StripeEvent)
class StripeEventAdmin(admin.ModelAdmin):
    list_display = ("event_id", "type", "signature_verified", "received_at", "processed_at")
    list_filter = ("type", "signature_verified")
    readonly_fields = ("event_id", "type", "payload", "signature_verified", "received_at", "processed_at", "error")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(Payout)
class PayoutAdmin(admin.ModelAdmin):
    list_display = ("id", "supplier_order", "amount", "currency", "status", "released_at")
    list_filter = ("status",)
    readonly_fields = ("idempotency_key", "stripe_transfer_id", "source_charge")


@admin.register(Refund)
class RefundAdmin(admin.ModelAdmin):
    list_display = ("id", "payment", "amount", "reason", "status", "created_at")
    list_filter = ("reason", "status")


@admin.register(LedgerJournal)
class LedgerJournalAdmin(admin.ModelAdmin):
    list_display = ("id", "kind", "order", "posted_at")
    list_filter = ("kind",)
    inlines = [LedgerEntryInline]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
