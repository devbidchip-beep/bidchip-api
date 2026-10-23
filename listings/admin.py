from django.contrib import admin

from .models import ComplianceScreening, Listing, ListingInvite, ListingLine


class ListingLineInline(admin.TabularInline):
    model = ListingLine
    extra = 0
    fields = [
        "line_no",
        "mpn_raw",
        "manufacturer_raw",
        "quantity",
        "target_unit_price",
        "compliance_status",
        "status",
    ]
    readonly_fields = ["line_no"]


@admin.register(Listing)
class ListingAdmin(admin.ModelAdmin):
    list_display = ["number", "kind", "status", "buyer_company", "ends_at"]
    list_filter = ["kind", "status"]
    search_fields = ["number", "title"]
    readonly_fields = ["number", "ends_at", "published_at", "closed_at"]
    inlines = [ListingLineInline]
    autocomplete_fields = ["buyer_company", "created_by"]


@admin.register(ComplianceScreening)
class ComplianceScreeningAdmin(admin.ModelAdmin):
    list_display = ["line", "ai_flagged", "decision"]
    list_filter = ["ai_flagged", "decision"]
    search_fields = ["line__mpn_raw"]
    readonly_fields = ["created_at", "updated_at"]
    autocomplete_fields = ["officer"]


@admin.register(ListingInvite)
class ListingInviteAdmin(admin.ModelAdmin):
    list_display = ["listing", "supplier_company", "email", "status"]
    list_filter = ["status"]
    search_fields = ["email", "listing__number"]
    autocomplete_fields = ["listing", "supplier_company"]
