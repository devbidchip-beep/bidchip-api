from django.contrib import admin

from integrations.models import NimblePriceBreak, NimbleQuote, NimbleRFQ, NimbleSyncLog


@admin.register(NimbleRFQ)
class NimbleRFQAdmin(admin.ModelAdmin):
    list_display = ["nimble_rfq_id", "listing", "status", "pushed_at", "last_pulled_at"]
    list_filter = ["status"]
    search_fields = ["nimble_rfq_id"]


@admin.register(NimbleQuote)
class NimbleQuoteAdmin(admin.ModelAdmin):
    list_display = ["nimble_quote_id", "rfq", "line", "supplier_name_raw", "status"]
    list_filter = ["status"]


@admin.register(NimblePriceBreak)
class NimblePriceBreakAdmin(admin.ModelAdmin):
    list_display = ["quote", "min_qty", "unit_price"]


@admin.register(NimbleSyncLog)
class NimbleSyncLogAdmin(admin.ModelAdmin):
    list_display = ["direction", "status_code", "at"]
    list_filter = ["direction", "status_code"]
