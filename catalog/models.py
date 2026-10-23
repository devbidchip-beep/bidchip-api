# GIN trigram index requires: CREATE EXTENSION IF NOT EXISTS pg_trgm;

import uuid

from django.contrib.postgres.indexes import GinIndex
from django.db import models
from django.utils.translation import gettext_lazy as _


def generate_uuid() -> uuid.UUID:
    """UUID4 primary key helper."""
    return uuid.uuid4()


# ---------------------------------------------------------------------------
# Manufacturer
# ---------------------------------------------------------------------------

class Manufacturer(models.Model):
    id = models.UUIDField(primary_key=True, default=generate_uuid, editable=False)
    name = models.CharField(max_length=255)
    name_normalized = models.CharField(max_length=255, unique=True)
    logo = models.CharField(max_length=500, blank=True)  # S3 key
    website = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Manufacturer"
        verbose_name_plural = "Manufacturers"
        ordering = ["name"]

    def __str__(self):
        return self.name


# ---------------------------------------------------------------------------
# ManufacturerAlias
# ---------------------------------------------------------------------------

class ManufacturerAlias(models.Model):
    id = models.UUIDField(primary_key=True, default=generate_uuid, editable=False)
    manufacturer = models.ForeignKey(
        Manufacturer,
        on_delete=models.PROTECT,
        related_name="aliases",
    )
    alias_normalized = models.CharField(max_length=255, unique=True)  # "TI" → Texas Instruments
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Manufacturer Alias"
        verbose_name_plural = "Manufacturer Aliases"

    def __str__(self):
        return f"{self.alias_normalized} → {self.manufacturer.name}"


# ---------------------------------------------------------------------------
# Part
# ---------------------------------------------------------------------------

class Part(models.Model):
    """
    Electronic component from the BidChip catalog (~6.6M rows).
    Uses BigAutoField PK (not UUID) for join performance.
    """

    class Lifecycle(models.TextChoices):
        ACTIVE = "active", _("Active")
        NRND = "nrnd", _("Not Recommended for New Designs")
        EOL = "eol", _("End of Life")
        OBSOLETE = "obsolete", _("Obsolete")

    # BigAutoField PK — NOT uuid — 6.6M rows joined constantly
    id = models.BigAutoField(primary_key=True)
    mpn = models.CharField(max_length=80)
    mpn_normalized = models.CharField(max_length=80)  # uppercase, strip spaces/dashes/dots
    manufacturer = models.ForeignKey(
        Manufacturer,
        on_delete=models.PROTECT,
        related_name="parts",
    )
    description = models.TextField(blank=True)
    category = models.CharField(max_length=120, blank=True)
    lifecycle = models.CharField(
        max_length=20,
        choices=Lifecycle.choices,
        null=True,
        blank=True,
    )
    eccn = models.CharField(max_length=20, null=True, blank=True)  # export classification
    is_itar = models.BooleanField(default=False)
    hts_code = models.CharField(max_length=12, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Part"
        verbose_name_plural = "Parts"
        unique_together = [("mpn_normalized", "manufacturer")]
        indexes = [
            GinIndex(
                fields=["mpn_normalized"],
                name="part_mpn_gin",
                opclasses=["gin_trgm_ops"],
            ),
            models.Index(fields=["manufacturer", "mpn_normalized"]),
        ]

    def __str__(self):
        return f"{self.mpn} ({self.manufacturer})"


# ---------------------------------------------------------------------------
# InventoryImport
# ---------------------------------------------------------------------------

class InventoryImport(models.Model):
    """Tracks a bulk inventory import job for a company."""

    class Source(models.TextChoices):
        CSV = "csv", _("CSV")
        EMAIL = "email", _("Email")
        API = "api", _("API")

    class Status(models.TextChoices):
        QUEUED = "queued", _("Queued")
        PROCESSING = "processing", _("Processing")
        DONE = "done", _("Done")
        FAILED = "failed", _("Failed")

    id = models.UUIDField(primary_key=True, default=generate_uuid, editable=False)
    company = models.ForeignKey(
        "accounts.Company",
        on_delete=models.PROTECT,
        related_name="inventory_imports",
    )
    source = models.CharField(max_length=20, choices=Source.choices)
    file = models.CharField(max_length=500, blank=True)  # S3 key
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.QUEUED)
    rows_total = models.IntegerField(default=0)
    rows_ok = models.IntegerField(default=0)
    rows_failed = models.IntegerField(default=0)
    error_report = models.CharField(max_length=500, blank=True)  # S3 key
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Inventory Import"
        verbose_name_plural = "Inventory Imports"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.company} import {self.id} ({self.status})"


# ---------------------------------------------------------------------------
# InventoryItem
# ---------------------------------------------------------------------------

class InventoryItem(models.Model):
    """
    A single line of inventory held by a supplier company (~590k rows).
    """

    class Packaging(models.TextChoices):
        REEL = "reel", _("Reel")
        CUT_TAPE = "cut_tape", _("Cut Tape")
        TRAY = "tray", _("Tray")
        TUBE = "tube", _("Tube")
        BULK = "bulk", _("Bulk")
        OTHER = "other", _("Other")

    class Source(models.TextChoices):
        CSV = "csv", _("CSV")
        EMAIL = "email", _("Email")
        API = "api", _("API")
        MANUAL = "manual", _("Manual")

    id = models.UUIDField(primary_key=True, default=generate_uuid, editable=False)
    company = models.ForeignKey(
        "accounts.Company",
        on_delete=models.PROTECT,
        related_name="inventory_items",
    )
    part = models.ForeignKey(
        Part,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="inventory_items",
    )  # null when MPN not in catalog
    mpn_raw = models.CharField(max_length=120)
    manufacturer_raw = models.CharField(max_length=255)
    manufacturer = models.ForeignKey(
        Manufacturer,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="inventory_items",
    )
    quantity = models.PositiveIntegerField()
    date_code_year = models.SmallIntegerField(null=True, blank=True)
    packaging = models.CharField(
        max_length=20,
        choices=Packaging.choices,
        blank=True,
    )
    unit_price = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    currency = models.CharField(max_length=3, default="USD")
    ship_from_country = models.CharField(max_length=2, blank=True)
    source = models.CharField(max_length=20, choices=Source.choices)
    import_job = models.ForeignKey(
        InventoryImport,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="items",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Inventory Item"
        verbose_name_plural = "Inventory Items"
        indexes = [
            models.Index(fields=["part"]),
            models.Index(fields=["company", "is_active"]),
        ]

    def __str__(self):
        return f"{self.mpn_raw} @ {self.company} (qty {self.quantity})"
