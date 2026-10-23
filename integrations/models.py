import uuid

from django.db import models
from django.utils.translation import gettext_lazy as _


def generate_uuid() -> uuid.UUID:
    return uuid.uuid4()


class NimbleRFQ(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", _("Pending")
        ACTIVE = "active", _("Active")
        CLOSED = "closed", _("Closed")

    id = models.UUIDField(primary_key=True, default=generate_uuid, editable=False)
    listing = models.OneToOneField(
        "listings.Listing",
        on_delete=models.PROTECT,
        related_name="nimble_rfq",
    )
    nimble_rfq_id = models.CharField(max_length=100, unique=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    pushed_at = models.DateTimeField(auto_now_add=True)
    last_pulled_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Nimble RFQ"
        verbose_name_plural = "Nimble RFQs"

    def __str__(self):
        return f"NimbleRFQ {self.nimble_rfq_id} — {self.listing}"


class NimbleQuote(models.Model):
    class Status(models.TextChoices):
        RECEIVED = "received", _("Received")
        AWARDED = "awarded", _("Awarded")
        REJECTED = "rejected", _("Rejected")

    id = models.UUIDField(primary_key=True, default=generate_uuid, editable=False)
    rfq = models.ForeignKey(NimbleRFQ, on_delete=models.PROTECT, related_name="quotes")
    line = models.ForeignKey(
        "listings.ListingLine", on_delete=models.PROTECT, related_name="nimble_quotes"
    )
    nimble_quote_id = models.CharField(max_length=100, unique=True)
    supplier_company = models.ForeignKey(
        "accounts.Company",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="nimble_quotes",
    )
    supplier_name_raw = models.CharField(max_length=255, blank=True)
    moq = models.PositiveIntegerField(default=1)
    lead_time_days = models.SmallIntegerField(default=0)
    date_code_year = models.SmallIntegerField(null=True, blank=True)
    packaging = models.CharField(max_length=50, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.RECEIVED)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Nimble Quote"
        verbose_name_plural = "Nimble Quotes"

    def __str__(self):
        return f"NimbleQuote {self.nimble_quote_id}"


class NimblePriceBreak(models.Model):
    id = models.UUIDField(primary_key=True, default=generate_uuid, editable=False)
    quote = models.ForeignKey(NimbleQuote, on_delete=models.CASCADE, related_name="price_breaks")
    min_qty = models.PositiveIntegerField()
    unit_price = models.DecimalField(max_digits=14, decimal_places=4)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Nimble Price Break"
        verbose_name_plural = "Nimble Price Breaks"
        unique_together = [("quote", "min_qty")]

    def __str__(self):
        return f"{self.quote} — qty {self.min_qty} @ {self.unit_price}"


class NimbleSyncLog(models.Model):
    class Direction(models.TextChoices):
        PUSH = "push", _("Push")
        PULL = "pull", _("Pull")

    id = models.UUIDField(primary_key=True, default=generate_uuid, editable=False)
    direction = models.CharField(max_length=10, choices=Direction.choices)
    request_hash = models.CharField(max_length=64, blank=True)
    status_code = models.SmallIntegerField(null=True, blank=True)
    error = models.TextField(blank=True)
    at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Nimble Sync Log"
        verbose_name_plural = "Nimble Sync Logs"
        ordering = ["-at"]

    def __str__(self):
        return f"NimbleSyncLog {self.direction} @ {self.at}"
