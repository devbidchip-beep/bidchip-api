from django.contrib import admin

from bidding.models import Award, Bid


@admin.register(Bid)
class BidAdmin(admin.ModelAdmin):
    list_display = ["line", "supplier_company", "unit_price", "quantity_offered", "is_exact_match", "status"]
    list_filter = ["status", "is_exact_match"]
    search_fields = ["supplier_company__legal_name"]
    readonly_fields = ["commitment_hash", "is_exact_match", "exception_reasons", "created_at", "updated_at"]


@admin.register(Award)
class AwardAdmin(admin.ModelAdmin):
    list_display = ["line", "bid", "quantity_awarded", "unit_price", "status"]
    list_filter = ["status"]
    readonly_fields = ["awarded_at", "created_at"]
