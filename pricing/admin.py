from django.contrib import admin

from pricing.models import (
    CompanyVolume,
    EMSCommission,
    FeeBracket,
    FeeAdjustment,
    FeeSchedule,
    OEMEMSLink,
    VolumeDiscountTier,
)


class FeeBracketInline(admin.TabularInline):
    model = FeeBracket
    extra = 1


@admin.register(FeeSchedule)
class FeeScheduleAdmin(admin.ModelAdmin):
    list_display = ("name", "kind", "side", "company", "is_active", "effective_from", "effective_to")
    list_filter = ("kind", "side", "is_active")
    search_fields = ("name",)
    inlines = [FeeBracketInline]


@admin.register(VolumeDiscountTier)
class VolumeDiscountTierAdmin(admin.ModelAdmin):
    list_display = ("lower_bound", "upper_bound", "points_off", "negotiated")


@admin.register(CompanyVolume)
class CompanyVolumeAdmin(admin.ModelAdmin):
    list_display = ("company", "as_of", "volume_12m_buyer", "volume_12m_seller", "eligible")
    list_filter = ("eligible",)


@admin.register(OEMEMSLink)
class OEMEMSLinkAdmin(admin.ModelAdmin):
    list_display = ("oem_company", "ems_company", "status", "commission_rate", "origin")
    list_filter = ("status", "origin")


@admin.register(EMSCommission)
class EMSCommissionAdmin(admin.ModelAdmin):
    list_display = ("order", "link", "amount", "currency", "status", "paid_at")
    list_filter = ("status",)


@admin.register(FeeAdjustment)
class FeeAdjustmentAdmin(admin.ModelAdmin):
    list_display = ("order", "side", "amount", "status", "requested_by", "approved_by")
    list_filter = ("status", "side")
