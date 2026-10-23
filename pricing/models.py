"""
Pricing models: FeeSchedule, FeeBracket, VolumeDiscountTier, CompanyVolume,
OEMEMSLink, EMSCommission, FeeAdjustment.
"""

import uuid

from django.db import models
from django.db.models import Q, F
from django.utils.translation import gettext_lazy as _
from simple_history.models import HistoricalRecords


def generate_uuid() -> uuid.UUID:
    return uuid.uuid4()


# ---------------------------------------------------------------------------
# FeeSchedule
# ---------------------------------------------------------------------------

class FeeSchedule(models.Model):
    class Kind(models.TextChoices):
        STANDARD = "standard", _("Standard")
        BYOS = "byos", _("BYOS")
        HIGH_RISK = "high_risk", _("High Risk")

    class Side(models.TextChoices):
        BUYER = "buyer", _("Buyer")
        SELLER = "seller", _("Seller")

    id = models.UUIDField(primary_key=True, default=generate_uuid, editable=False)
    name = models.CharField(max_length=100)
    kind = models.CharField(max_length=20, choices=Kind.choices, default=Kind.STANDARD)
    side = models.CharField(max_length=10, choices=Side.choices, default=Side.BUYER)
    company = models.ForeignKey(
        "accounts.Company",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="fee_schedules",
        help_text="Null = platform default; set = per-company override",
    )
    min_fee = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    effective_from = models.DateField()
    effective_to = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.PROTECT,
        related_name="created_fee_schedules",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    history = HistoricalRecords()

    class Meta:
        verbose_name = "Fee Schedule"
        verbose_name_plural = "Fee Schedules"
        ordering = ["-effective_from"]

    def __str__(self):
        company_str = f" ({self.company})" if self.company_id else " (default)"
        return f"{self.name} — {self.kind}/{self.side}{company_str}"


# ---------------------------------------------------------------------------
# FeeBracket
# ---------------------------------------------------------------------------

class FeeBracket(models.Model):
    id = models.UUIDField(primary_key=True, default=generate_uuid, editable=False)
    schedule = models.ForeignKey(
        FeeSchedule,
        on_delete=models.CASCADE,
        related_name="brackets",
    )
    lower_bound = models.DecimalField(max_digits=14, decimal_places=2)
    upper_bound = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    rate = models.DecimalField(max_digits=6, decimal_places=4, help_text="0.0700 = 7%")

    class Meta:
        verbose_name = "Fee Bracket"
        verbose_name_plural = "Fee Brackets"
        unique_together = [("schedule", "lower_bound")]
        ordering = ["schedule", "lower_bound"]

    def __str__(self):
        upper = str(self.upper_bound) if self.upper_bound else "∞"
        return f"{self.schedule} [{self.lower_bound}–{upper}] @ {self.rate}"


# ---------------------------------------------------------------------------
# VolumeDiscountTier
# ---------------------------------------------------------------------------

class VolumeDiscountTier(models.Model):
    id = models.UUIDField(primary_key=True, default=generate_uuid, editable=False)
    lower_bound = models.DecimalField(max_digits=14, decimal_places=2)
    upper_bound = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    points_off = models.DecimalField(
        max_digits=6, decimal_places=4,
        help_text="0.0050 = 0.5 points off the rate",
    )
    negotiated = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Volume Discount Tier"
        verbose_name_plural = "Volume Discount Tiers"
        ordering = ["lower_bound"]

    def __str__(self):
        upper = str(self.upper_bound) if self.upper_bound else "∞"
        return f"[{self.lower_bound}–{upper}] -{self.points_off}"


# ---------------------------------------------------------------------------
# CompanyVolume  — nightly snapshot
# ---------------------------------------------------------------------------

class CompanyVolume(models.Model):
    id = models.UUIDField(primary_key=True, default=generate_uuid, editable=False)
    company = models.ForeignKey(
        "accounts.Company",
        on_delete=models.CASCADE,
        related_name="volume_snapshots",
    )
    as_of = models.DateField()
    volume_12m_buyer = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    volume_12m_seller = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    dispute_rate = models.DecimalField(max_digits=6, decimal_places=4, default=0)
    discount_points = models.DecimalField(max_digits=6, decimal_places=4, default=0)
    eligible = models.BooleanField(default=True)
    reason = models.CharField(max_length=200, blank=True)

    class Meta:
        verbose_name = "Company Volume"
        verbose_name_plural = "Company Volumes"
        unique_together = [("company", "as_of")]
        ordering = ["-as_of"]

    def __str__(self):
        return f"{self.company} volume as of {self.as_of}"


# ---------------------------------------------------------------------------
# OEMEMSLink
# ---------------------------------------------------------------------------

class OEMEMSLink(models.Model):
    class Origin(models.TextChoices):
        EMS_REFERRED = "ems_referred", _("EMS Referred")
        OEM_ADDED = "oem_added", _("OEM Added")

    class Status(models.TextChoices):
        PENDING = "pending", _("Pending")
        ACTIVE = "active", _("Active")
        ENDED = "ended", _("Ended")

    id = models.UUIDField(primary_key=True, default=generate_uuid, editable=False)
    oem_company = models.ForeignKey(
        "accounts.Company",
        on_delete=models.PROTECT,
        related_name="oem_links",
    )
    ems_company = models.ForeignKey(
        "accounts.Company",
        on_delete=models.PROTECT,
        related_name="ems_links",
    )
    origin = models.CharField(max_length=20, choices=Origin.choices)
    commission_rate = models.DecimalField(
        max_digits=6, decimal_places=4,
        help_text="Copied from PlatformSetting at link creation time",
    )
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    oem_approved_at = models.DateTimeField(null=True, blank=True)
    ems_approved_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "OEM/EMS Link"
        verbose_name_plural = "OEM/EMS Links"
        constraints = [
            models.UniqueConstraint(
                fields=["oem_company", "ems_company"],
                condition=Q(status="active"),
                name="unique_active_oem_ems_link",
            )
        ]

    def __str__(self):
        return f"{self.oem_company} / {self.ems_company} ({self.status})"


# ---------------------------------------------------------------------------
# EMSCommission
# ---------------------------------------------------------------------------

class EMSCommission(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", _("Pending")
        PAYABLE = "payable", _("Payable")
        PAID = "paid", _("Paid")
        CANCELLED = "cancelled", _("Cancelled")

    id = models.UUIDField(primary_key=True, default=generate_uuid, editable=False)
    # String ref to avoid circular import; enforced by FK at DB level via migration
    order = models.OneToOneField(
        "orders.Order",
        on_delete=models.PROTECT,
        related_name="ems_commission",
    )
    link = models.ForeignKey(
        OEMEMSLink,
        on_delete=models.PROTECT,
        related_name="commissions",
    )
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    currency = models.CharField(max_length=3, default="USD")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    stripe_transfer_id = models.CharField(max_length=200, unique=True, null=True, blank=True)
    idempotency_key = models.CharField(max_length=200, unique=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    tax_year = models.SmallIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "EMS Commission"
        verbose_name_plural = "EMS Commissions"

    def __str__(self):
        return f"EMSCommission {self.id} — {self.amount} {self.currency} ({self.status})"


# ---------------------------------------------------------------------------
# FeeAdjustment
# ---------------------------------------------------------------------------

class FeeAdjustment(models.Model):
    class Side(models.TextChoices):
        BUYER = "buyer", _("Buyer")
        SELLER = "seller", _("Seller")

    class Status(models.TextChoices):
        REQUESTED = "requested", _("Requested")
        APPROVED = "approved", _("Approved")
        REJECTED = "rejected", _("Rejected")
        APPLIED = "applied", _("Applied")

    id = models.UUIDField(primary_key=True, default=generate_uuid, editable=False)
    order = models.ForeignKey(
        "orders.Order",
        on_delete=models.PROTECT,
        related_name="fee_adjustments",
    )
    supplier_order = models.ForeignKey(
        "orders.SupplierOrder",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="fee_adjustments",
    )
    side = models.CharField(max_length=10, choices=Side.choices)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    reason = models.TextField()
    requested_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.PROTECT,
        related_name="fee_adjustment_requests",
    )
    approved_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="fee_adjustment_approvals",
    )
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.REQUESTED
    )
    refund = models.ForeignKey(
        "payments.Refund",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="fee_adjustments",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    history = HistoricalRecords()

    class Meta:
        verbose_name = "Fee Adjustment"
        verbose_name_plural = "Fee Adjustments"
        constraints = [
            models.CheckConstraint(
                check=~Q(approved_by=F("requested_by")),
                name="fee_adjustment_two_person",
            )
        ]

    def __str__(self):
        return f"FeeAdjustment {self.id} — {self.side} {self.amount} ({self.status})"
