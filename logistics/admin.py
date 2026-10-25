"""
Django admin for the logistics app.
Customized for warehouse and lab staff roles.
"""

from django.contrib import admin

from logistics.models import (
    Inspection,
    InspectionPhoto,
    LabTest,
    Package,
    RateQuote,
    Shipment,
)


# ---------------------------------------------------------------------------
# Shipment
# ---------------------------------------------------------------------------

@admin.register(Shipment)
class ShipmentAdmin(admin.ModelAdmin):
    list_display = ["id", "leg", "carrier", "tracking_number", "status", "shipped_at", "delivered_at"]
    list_filter = ["leg", "carrier", "status"]
    search_fields = ["tracking_number", "po_number_on_label"]
    readonly_fields = ["id", "created_at", "updated_at"]
    ordering = ["-created_at"]
    fieldsets = [
        (
            "Identity",
            {
                "fields": ["id", "leg", "order", "supplier_order", "dispute"],
            },
        ),
        (
            "Carrier",
            {
                "fields": ["carrier", "service_code", "tracking_number", "label", "po_number_on_label"],
            },
        ),
        (
            "Costs",
            {
                "fields": ["paid_by", "cost_estimated", "cost_actual"],
            },
        ),
        (
            "Status",
            {
                "fields": ["status", "is_partial", "shipped_at", "delivered_at"],
            },
        ),
        (
            "Timestamps",
            {
                "fields": ["created_at", "updated_at"],
                "classes": ["collapse"],
            },
        ),
    ]


@admin.register(Package)
class PackageAdmin(admin.ModelAdmin):
    list_display = ["id", "shipment", "weight_kg", "sized_by", "created_at"]
    list_filter = ["sized_by"]
    search_fields = ["shipment__tracking_number"]
    readonly_fields = ["id", "created_at"]


@admin.register(RateQuote)
class RateQuoteAdmin(admin.ModelAdmin):
    list_display = ["id", "shipment", "carrier", "service_code", "amount", "currency", "transit_days", "chosen", "quoted_at"]
    list_filter = ["carrier", "chosen", "is_next_day"]
    search_fields = ["shipment__tracking_number", "service_code"]
    readonly_fields = ["id", "quoted_at"]


# ---------------------------------------------------------------------------
# Inspection
# ---------------------------------------------------------------------------

class InspectionPhotoInline(admin.TabularInline):
    model = InspectionPhoto
    extra = 0
    fields = ["file", "caption", "order_line", "created_at"]
    readonly_fields = ["created_at"]

    def get_readonly_fields(self, request, obj=None):
        # Make all fields read-only if the inspection is completed
        if obj and obj.result:
            return ["file", "caption", "order_line", "created_at"]
        return self.readonly_fields


@admin.register(Inspection)
class InspectionAdmin(admin.ModelAdmin):
    list_display = ["id", "supplier_order", "inspector", "level", "result", "inspected_at"]
    list_filter = ["level", "result"]
    search_fields = ["supplier_order__anonymous_supplier_id", "inspector__email"]
    readonly_fields = ["id", "created_at", "updated_at"]
    inlines = [InspectionPhotoInline]

    def get_readonly_fields(self, request, obj=None):
        # Lock all fields on completed inspections
        if obj and obj.result:
            return [
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
            ]
        return self.readonly_fields

    fieldsets = [
        (
            "Inspection",
            {
                "fields": ["id", "supplier_order", "inspector", "level"],
            },
        ),
        (
            "Result",
            {
                "fields": ["result", "notes", "counted_quantity", "inspected_at"],
            },
        ),
        (
            "Timestamps",
            {
                "fields": ["created_at", "updated_at"],
                "classes": ["collapse"],
            },
        ),
    ]


# ---------------------------------------------------------------------------
# Lab Test
# ---------------------------------------------------------------------------

@admin.register(LabTest)
class LabTestAdmin(admin.ModelAdmin):
    list_display = ["id", "order_line", "lab_user", "method", "result", "completed_at"]
    list_filter = ["result"]
    search_fields = ["order_line__id", "lab_user__email", "method"]
    readonly_fields = ["id", "created_at", "updated_at"]
    ordering = ["-created_at"]
