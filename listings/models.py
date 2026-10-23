import uuid
from decimal import Decimal

from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


def generate_uuid() -> uuid.UUID:
    """UUID4 primary key helper."""
    return uuid.uuid4()


# ---------------------------------------------------------------------------
# Listing
# ---------------------------------------------------------------------------

class Listing(models.Model):
    class Kind(models.TextChoices):
        REVERSE = "reverse", _("Reverse Auction")
        BOM = "bom", _("BOM")
        RFQ = "rfq", _("RFQ")
        FORWARD = "forward", _("Forward Auction")

    class Status(models.TextChoices):
        DRAFT = "draft", _("Draft")
        PENDING_APPROVAL = "pending_approval", _("Pending Approval")
        PUBLISHED = "published", _("Published")
        CLOSED = "closed", _("Closed")
        AWARDED = "awarded", _("Awarded")
        CANCELLED = "cancelled", _("Cancelled")
        EXPIRED = "expired", _("Expired")

    class Source(models.TextChoices):
        MANUAL = "manual", _("Manual")
        AI_INTAKE = "ai_intake", _("AI Intake")
        NIMBLE = "nimble", _("Nimble")
        API = "api", _("API")

    id = models.UUIDField(primary_key=True, default=generate_uuid, editable=False)
    number = models.CharField(max_length=20, unique=True, blank=True)  # e.g. RA-2026-001234
    kind = models.CharField(max_length=20, choices=Kind.choices)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    buyer_company = models.ForeignKey(
        "accounts.Company",
        on_delete=models.PROTECT,
        related_name="listings",
    )
    created_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.PROTECT,
        related_name="created_listings",
    )
    source = models.CharField(max_length=20, choices=Source.choices, default=Source.MANUAL)
    intake = models.ForeignKey(
        "intake.IntakeMessage",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="listings",
    )
    title = models.CharField(max_length=200)
    starts_at = models.DateTimeField(null=True, blank=True)
    duration_minutes = models.PositiveIntegerField(default=4320)  # 72h
    ends_at = models.DateTimeField(null=True, blank=True)  # computed by core.calendar.add_running_time
    invite_only = models.BooleanField(default=False)
    anonymous = models.BooleanField(default=True)
    ship_to = models.ForeignKey(
        "accounts.Address",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="listings",
    )
    currency = models.CharField(max_length=3, default="USD")
    published_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Listing"
        verbose_name_plural = "Listings"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "ends_at"]),  # closing task
            models.Index(fields=["buyer_company", "status"]),
        ]

    def __str__(self):
        return f"{self.number or str(self.pk)[:8]} — {self.title}"

    def save(self, *args, **kwargs):
        # Auto-generate number if blank
        if not self.number:
            year = timezone.now().year
            count = Listing.objects.filter(kind=self.kind).count() + 1
            self.number = f"{self.kind[:2].upper()}-{year}-{str(count).zfill(6)}"

        # Compute ends_at when publishing
        if (
            self.status == self.Status.PUBLISHED
            and self.starts_at is not None
            and self.ends_at is None
        ):
            from core.calendar import add_running_time
            self.ends_at = add_running_time(self.starts_at, self.duration_minutes)

        super().save(*args, **kwargs)


# ---------------------------------------------------------------------------
# ListingLine
# ---------------------------------------------------------------------------

class ListingLine(models.Model):
    class Packaging(models.TextChoices):
        REEL = "reel", _("Reel")
        CUT_TAPE = "cut_tape", _("Cut Tape")
        TRAY = "tray", _("Tray")
        TUBE = "tube", _("Tube")
        BULK = "bulk", _("Bulk")
        OTHER = "other", _("Other")

    class ComplianceStatus(models.TextChoices):
        CLEAR = "clear", _("Clear")
        FLAGGED = "flagged", _("Flagged")
        OFFICER_REVIEW = "officer_review", _("Officer Review")
        APPROVED = "approved", _("Approved")
        REJECTED = "rejected", _("Rejected")

    class Status(models.TextChoices):
        OPEN = "open", _("Open")
        AWARDED = "awarded", _("Awarded")
        PARTIALLY_AWARDED = "partially_awarded", _("Partially Awarded")
        NO_AWARD = "no_award", _("No Award")

    id = models.UUIDField(primary_key=True, default=generate_uuid, editable=False)
    listing = models.ForeignKey(
        Listing,
        on_delete=models.CASCADE,
        related_name="lines",
    )
    line_no = models.SmallIntegerField()
    part = models.ForeignKey(
        "catalog.Part",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="listing_lines",
    )
    mpn_raw = models.CharField(max_length=120)
    manufacturer_raw = models.CharField(max_length=255, blank=True)
    manufacturer = models.ForeignKey(
        "catalog.Manufacturer",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="listing_lines",
    )
    quantity = models.PositiveIntegerField()
    target_unit_price = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True)
    date_code_year_min = models.SmallIntegerField(null=True, blank=True)
    packaging = models.CharField(
        max_length=20,
        choices=Packaging.choices,
        null=True,
        blank=True,
    )
    allow_exceptions = models.BooleanField(default=True)
    allow_split = models.BooleanField(default=True)
    require_as6081 = models.BooleanField(default=False)
    lab_method = models.CharField(max_length=100, blank=True)
    docs_required = models.BooleanField(default=False)
    ncnr = models.BooleanField(default=False)
    compliance_status = models.CharField(
        max_length=20,
        choices=ComplianceStatus.choices,
        default=ComplianceStatus.CLEAR,
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.OPEN,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Listing Line"
        verbose_name_plural = "Listing Lines"
        unique_together = [("listing", "line_no")]
        ordering = ["listing", "line_no"]

    def __str__(self):
        return f"Line {self.line_no}: {self.mpn_raw} (qty {self.quantity})"


# ---------------------------------------------------------------------------
# ListingInvite
# ---------------------------------------------------------------------------

class ListingInvite(models.Model):
    class Status(models.TextChoices):
        SENT = "sent", _("Sent")
        JOINED = "joined", _("Joined")
        BID = "bid", _("Bid")
        DECLINED = "declined", _("Declined")

    id = models.UUIDField(primary_key=True, default=generate_uuid, editable=False)
    listing = models.ForeignKey(
        Listing,
        on_delete=models.CASCADE,
        related_name="invites",
    )
    supplier_company = models.ForeignKey(
        "accounts.Company",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="listing_invites",
    )
    email = models.EmailField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.SENT)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Listing Invite"
        verbose_name_plural = "Listing Invites"
        unique_together = [("listing", "supplier_company")]

    def __str__(self):
        return f"Invite: {self.listing} → {self.supplier_company or self.email}"


# ---------------------------------------------------------------------------
# ComplianceScreening
# ---------------------------------------------------------------------------

class ComplianceScreening(models.Model):
    class Decision(models.TextChoices):
        CLEAR = "clear", _("Clear")
        APPROVED = "approved", _("Approved")
        REJECTED = "rejected", _("Rejected")

    id = models.UUIDField(primary_key=True, default=generate_uuid, editable=False)
    line = models.OneToOneField(
        ListingLine,
        on_delete=models.CASCADE,
        related_name="compliance_screening",
    )
    ai_result = models.JSONField(default=dict)
    ai_flagged = models.BooleanField(default=False)
    officer = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="compliance_decisions",
    )
    decision = models.CharField(
        max_length=20,
        choices=Decision.choices,
        null=True,
        blank=True,
    )
    decision_note = models.TextField(blank=True)
    authority_reference = models.CharField(max_length=200, blank=True)
    fee_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("30.00"))
    decided_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Compliance Screening"
        verbose_name_plural = "Compliance Screenings"

    def __str__(self):
        return f"Screening for {self.line} — {self.decision or 'pending'}"
