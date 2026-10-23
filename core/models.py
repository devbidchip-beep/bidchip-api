"""
Core platform models: PlatformSetting, AuditEvent, BusinessHoliday.
"""

import uuid

from django.db import models
from django.utils.translation import gettext_lazy as _
from simple_history.models import HistoricalRecords


def generate_uuid() -> uuid.UUID:
    """UUID4 primary key helper. TODO: swap to uuid7 when library is added."""
    return uuid.uuid4()


# ---------------------------------------------------------------------------
# PlatformSetting
# ---------------------------------------------------------------------------

class PlatformSetting(models.Model):
    """
    Key-value store for platform-wide configuration flags and parameters.
    Changes are tracked via django-simple-history.
    """

    key = models.CharField(max_length=255, unique=True)
    value = models.JSONField()
    description = models.TextField(blank=True, default="")
    updated_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="platform_settings_updated",
    )
    updated_at = models.DateTimeField(auto_now=True)

    history = HistoricalRecords()

    class Meta:
        verbose_name = "Platform Setting"
        verbose_name_plural = "Platform Settings"
        ordering = ["key"]

    def __str__(self):
        return self.key


# ---------------------------------------------------------------------------
# AuditEvent
# ---------------------------------------------------------------------------

class AuditEvent(models.Model):
    """
    Immutable structured audit log for security-sensitive actions.
    Insert-only — no updated_at.
    """

    class EventType(models.TextChoices):
        # Auth
        LOGIN = "login", _("Login")
        LOGOUT = "logout", _("Logout")
        PASSWORD_CHANGE = "password_change", _("Password Change")
        MFA_ENABLED = "mfa_enabled", _("MFA Enabled")
        MFA_DISABLED = "mfa_disabled", _("MFA Disabled")
        # Company
        COMPANY_STATUS_CHANGE = "company_status_change", _("Company Status Change")
        COMPANY_VERIFIED = "company_verified", _("Company Verified")
        MEMBER_ADDED = "member_added", _("Member Added")
        MEMBER_REMOVED = "member_removed", _("Member Removed")
        # Financial
        PAYOUT_RELEASED = "payout_released", _("Payout Released")
        PAYOUT_HELD = "payout_held", _("Payout Held")
        # Admin
        SETTINGS_CHANGED = "settings_changed", _("Settings Changed")
        OTHER = "other", _("Other")

    id = models.UUIDField(primary_key=True, default=generate_uuid, editable=False)
    event_type = models.CharField(max_length=40, choices=EventType.choices)
    actor = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_events_as_actor",
    )
    target_user = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_events_as_target",
    )
    target_company = models.ForeignKey(
        "accounts.Company",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_events",
    )
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    description = models.TextField(blank=True, default="")
    extra_data = models.JSONField(blank=True, null=True)

    # Insert-only log — no updated_at
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Audit Event"
        verbose_name_plural = "Audit Events"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["event_type", "-created_at"]),
            models.Index(fields=["actor", "-created_at"]),
            models.Index(fields=["target_company", "-created_at"]),
        ]

    def __str__(self):
        return f"{self.event_type} by {self.actor} @ {self.created_at}"


# ---------------------------------------------------------------------------
# BusinessHoliday
# ---------------------------------------------------------------------------

class BusinessHoliday(models.Model):
    """
    US business holidays observed by the BidChip business clock.
    Used by core.calendar.add_running_time() to skip non-working days.
    """

    date = models.DateField(unique=True)
    name = models.CharField(max_length=100)
    observed_for = models.DateField(
        null=True,
        blank=True,
        help_text="The actual holiday date if this is an observed substitute.",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Only active holidays are considered by the business clock.",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Business Holiday"
        verbose_name_plural = "Business Holidays"
        ordering = ["date"]

    def __str__(self):
        return f"{self.date} — {self.name}"
