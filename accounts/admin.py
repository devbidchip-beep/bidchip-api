from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.translation import gettext_lazy as _

from .models import (
    Address,
    Company,
    CompanyDocument,
    CompanyMember,
    LoginEvent,
    StripeAccount,
    TaxCertificate,
    User,
    VerificationCheck,
)


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ("email", "full_name", "staff_role", "is_active", "mfa_required", "created_at")
    list_filter = ("is_active", "is_staff", "staff_role", "mfa_required")
    search_fields = ("email", "full_name")
    ordering = ("email",)

    fieldsets = (
        (None, {"fields": ("email", "password")}),
        (
            _("Personal info"),
            {"fields": ("full_name", "phone")},
        ),
        (
            _("Staff"),
            {"fields": ("staff_role", "mfa_required")},
        ),
        (
            _("Permissions"),
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                )
            },
        ),
        (_("Important dates"), {"fields": ("last_login", "last_login_at", "created_at", "updated_at")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "full_name", "password1", "password2"),
            },
        ),
    )
    readonly_fields = ("created_at", "updated_at", "last_login_at")


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ("display_name", "legal_name", "country", "status", "created_at")
    list_filter = ("status", "country", "is_buyer", "is_supplier", "is_oem", "is_ems")
    search_fields = ("display_name", "legal_name")
    readonly_fields = ("created_at", "updated_at", "verified_at")


@admin.register(CompanyMember)
class CompanyMemberAdmin(admin.ModelAdmin):
    list_display = ("user", "company", "role", "status", "can_release_payout")
    list_filter = ("role", "status")
    search_fields = ("user__email", "company__display_name")


@admin.register(Address)
class AddressAdmin(admin.ModelAdmin):
    list_display = ("line1", "city", "country", "address_type", "is_primary")
    list_filter = ("address_type", "country", "is_primary")


@admin.register(CompanyDocument)
class CompanyDocumentAdmin(admin.ModelAdmin):
    list_display = ("company", "document_type", "uploaded_by", "created_at")
    list_filter = ("document_type",)
    readonly_fields = ("created_at",)


@admin.register(VerificationCheck)
class VerificationCheckAdmin(admin.ModelAdmin):
    list_display = ("company", "check_type", "result", "performed_by", "created_at")
    list_filter = ("check_type", "result")
    readonly_fields = ("created_at",)


@admin.register(TaxCertificate)
class TaxCertificateAdmin(admin.ModelAdmin):
    list_display = ("company", "state", "status", "expiry_date", "created_at")
    list_filter = ("status", "state")
    readonly_fields = ("created_at", "updated_at")


@admin.register(StripeAccount)
class StripeAccountAdmin(admin.ModelAdmin):
    list_display = (
        "company",
        "stripe_account_id",
        "status",
        "charges_enabled",
        "payouts_enabled",
    )
    list_filter = ("status", "account_type")
    readonly_fields = ("created_at", "updated_at")


@admin.register(LoginEvent)
class LoginEventAdmin(admin.ModelAdmin):
    list_display = ("email_attempted", "outcome", "ip_address", "mfa_used", "created_at")
    list_filter = ("outcome", "mfa_used")
    search_fields = ("email_attempted", "ip_address")
    readonly_fields = ("created_at",)
