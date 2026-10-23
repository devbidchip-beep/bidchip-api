import hashlib
import uuid

from django.db import models
from django.utils.translation import gettext_lazy as _


def generate_uuid() -> uuid.UUID:
    return uuid.uuid4()


class Bid(models.Model):
    class Packaging(models.TextChoices):
        REEL = "reel", _("Reel")
        CUT_TAPE = "cut_tape", _("Cut Tape")
        TRAY = "tray", _("Tray")
        TUBE = "tube", _("Tube")
        BULK = "bulk", _("Bulk")
        OTHER = "other", _("Other")

    class Status(models.TextChoices):
        ACTIVE = "active", _("Active")
        WITHDRAWN = "withdrawn", _("Withdrawn")
        WON = "won", _("Won")
        PARTIALLY_WON = "partially_won", _("Partially Won")
        LOST = "lost", _("Lost")

    id = models.UUIDField(primary_key=True, default=generate_uuid, editable=False)
    line = models.ForeignKey(
        "listings.ListingLine",
        on_delete=models.PROTECT,
        related_name="bids",
    )
    supplier_company = models.ForeignKey(
        "accounts.Company",
        on_delete=models.PROTECT,
        related_name="bids",
    )
    placed_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.PROTECT,
        related_name="placed_bids",
    )
    unit_price = models.DecimalField(max_digits=14, decimal_places=4)
    quantity_offered = models.PositiveIntegerField()
    date_code_year = models.SmallIntegerField(null=True, blank=True)
    packaging = models.CharField(
        max_length=20,
        choices=Packaging.choices,
        null=True,
        blank=True,
    )
    lead_time_days = models.SmallIntegerField(default=0)
    inventory_item = models.ForeignKey(
        "catalog.InventoryItem",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="bids",
    )
    is_exact_match = models.BooleanField(default=False)
    exception_reasons = models.JSONField(default=list)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
    )
    commitment_hash = models.CharField(max_length=64, blank=True)
    supplier_net_shown = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Bid"
        verbose_name_plural = "Bids"
        indexes = [
            models.Index(fields=["line", "status", "is_exact_match", "unit_price"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["line", "supplier_company"],
                condition=models.Q(status="active"),
                name="unique_active_bid_per_supplier_per_line",
            )
        ]

    def __str__(self):
        return f"Bid by {self.supplier_company} on {self.line} @ {self.unit_price}"

    def _compute_match(self):
        """Compute is_exact_match and exception_reasons based on line requirements."""
        line = self.line
        exceptions = []

        # Quantity check
        qty_ok = self.quantity_offered >= line.quantity
        if not qty_ok:
            exceptions.append("qty_short")

        # Date code check
        if line.date_code_year_min is not None:
            if self.date_code_year is None or self.date_code_year < line.date_code_year_min:
                exceptions.append("date_code")

        # Packaging check
        if line.packaging is not None:
            if self.packaging is None or self.packaging != line.packaging:
                exceptions.append("packaging")

        self.is_exact_match = len(exceptions) == 0
        self.exception_reasons = exceptions

    def save(self, *args, **kwargs):
        self._compute_match()
        # Compute commitment hash from bid terms
        terms = f"{self.line_id}:{self.supplier_company_id}:{self.unit_price}:{self.quantity_offered}"
        self.commitment_hash = hashlib.sha256(terms.encode()).hexdigest()
        super().save(*args, **kwargs)


class Award(models.Model):
    class Status(models.TextChoices):
        AWARDED = "awarded", _("Awarded")
        CONVERTED = "converted", _("Converted")
        CANCELLED = "cancelled", _("Cancelled")

    id = models.UUIDField(primary_key=True, default=generate_uuid, editable=False)
    line = models.ForeignKey(
        "listings.ListingLine",
        on_delete=models.PROTECT,
        related_name="awards",
    )
    bid = models.ForeignKey(
        Bid,
        on_delete=models.PROTECT,
        related_name="awards",
    )
    quantity_awarded = models.PositiveIntegerField()
    unit_price = models.DecimalField(max_digits=14, decimal_places=4)
    rank = models.SmallIntegerField(default=1)
    awarded_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="awards_made",
    )
    awarded_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.AWARDED,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Award"
        verbose_name_plural = "Awards"
        ordering = ["rank"]

    def __str__(self):
        return f"Award: {self.line} → {self.bid.supplier_company} (qty {self.quantity_awarded})"
