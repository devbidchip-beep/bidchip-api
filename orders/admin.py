from django.contrib import admin

from orders.models import Order, OrderLine, OrderStatusLog, Receipt, SupplierOrder


class OrderLineInline(admin.TabularInline):
    model = OrderLine
    extra = 0
    readonly_fields = ("award", "listing_line", "quantity", "unit_price", "line_total", "status")
    can_delete = False


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("number", "buyer_company", "status", "grand_total", "paid_at")
    list_filter = ("status",)
    search_fields = ("number", "po_number")
    readonly_fields = ("number", "pricing_snapshot")


@admin.register(SupplierOrder)
class SupplierOrderAdmin(admin.ModelAdmin):
    list_display = ("order", "supplier_company", "status", "payout_amount", "risk_tier")
    list_filter = ("status", "risk_tier")
    inlines = [OrderLineInline]


@admin.register(OrderStatusLog)
class OrderStatusLogAdmin(admin.ModelAdmin):
    list_display = ("order", "from_status", "to_status", "actor_kind", "at")
    readonly_fields = (
        "id",
        "order",
        "supplier_order",
        "from_status",
        "to_status",
        "actor",
        "actor_kind",
        "reason",
        "at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(Receipt)
class ReceiptAdmin(admin.ModelAdmin):
    list_display = ("number", "order", "issued_at")
    readonly_fields = ("number", "order", "issued_at", "lines", "totals")
