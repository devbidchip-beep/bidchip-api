from django.contrib import admin

from .models import InventoryImport, InventoryItem, Manufacturer, ManufacturerAlias, Part


@admin.register(Manufacturer)
class ManufacturerAdmin(admin.ModelAdmin):
    list_display = ["name", "is_active"]
    search_fields = ["name"]
    list_filter = ["is_active"]


@admin.register(ManufacturerAlias)
class ManufacturerAliasAdmin(admin.ModelAdmin):
    list_display = ["alias_normalized", "manufacturer"]
    search_fields = ["alias_normalized"]
    autocomplete_fields = ["manufacturer"]


@admin.register(Part)
class PartAdmin(admin.ModelAdmin):
    list_display = ["mpn", "manufacturer", "lifecycle", "is_itar"]
    search_fields = ["mpn", "mpn_normalized"]
    list_filter = ["lifecycle", "is_itar", "manufacturer"]
    readonly_fields = ["mpn_normalized"]
    autocomplete_fields = ["manufacturer"]


@admin.register(InventoryItem)
class InventoryItemAdmin(admin.ModelAdmin):
    list_display = ["mpn_raw", "company", "quantity", "is_active"]
    list_filter = ["source", "is_active"]
    search_fields = ["mpn_raw", "manufacturer_raw"]
    autocomplete_fields = ["company", "part", "manufacturer"]


@admin.register(InventoryImport)
class InventoryImportAdmin(admin.ModelAdmin):
    list_display = ["company", "source", "status", "rows_total", "rows_ok", "rows_failed", "created_at"]
    list_filter = ["source", "status"]
    search_fields = ["company__legal_name"]
    readonly_fields = ["created_at", "updated_at"]
