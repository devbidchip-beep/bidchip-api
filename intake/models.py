import uuid

from django.db import models
from django.utils.translation import gettext_lazy as _


def generate_uuid() -> uuid.UUID:
    """UUID4 primary key helper."""
    return uuid.uuid4()


# ---------------------------------------------------------------------------
# IntakeMessage
# ---------------------------------------------------------------------------

class IntakeMessage(models.Model):
    class Channel(models.TextChoices):
        EMAIL = "email", _("Email")
        UPLOAD = "upload", _("Upload")
        API = "api", _("API")

    class Status(models.TextChoices):
        RECEIVED = "received", _("Received")
        EXTRACTING = "extracting", _("Extracting")
        NEEDS_REVIEW = "needs_review", _("Needs Review")
        DRAFT_CREATED = "draft_created", _("Draft Created")
        FAILED = "failed", _("Failed")
        REJECTED_SENDER = "rejected_sender", _("Rejected Sender")

    id = models.UUIDField(primary_key=True, default=generate_uuid, editable=False)
    channel = models.CharField(max_length=20, choices=Channel.choices)
    from_email = models.EmailField(null=True, blank=True)
    company = models.ForeignKey(
        "accounts.Company",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="intake_messages",
    )
    user = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="intake_messages",
    )
    subject = models.CharField(max_length=500, blank=True)
    raw_s3_key = models.CharField(max_length=500, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.RECEIVED)
    received_at = models.DateTimeField(auto_now_add=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Intake Message"
        verbose_name_plural = "Intake Messages"
        ordering = ["-received_at"]
        indexes = [
            models.Index(fields=["company", "status"]),
            models.Index(fields=["status", "-received_at"]),
        ]

    def __str__(self):
        return f"{self.channel} from {self.from_email or 'unknown'} ({self.status})"

    def save(self, *args, **kwargs):
        # Normalize email to lowercase
        if self.from_email:
            self.from_email = self.from_email.lower()
        super().save(*args, **kwargs)


# ---------------------------------------------------------------------------
# IntakeFile
# ---------------------------------------------------------------------------

class IntakeFile(models.Model):
    class Kind(models.TextChoices):
        XLSX = "xlsx", _("Excel (xlsx)")
        CSV = "csv", _("CSV")
        PDF = "pdf", _("PDF")
        IMAGE = "image", _("Image")
        BODY_TEXT = "body_text", _("Body Text")

    id = models.UUIDField(primary_key=True, default=generate_uuid, editable=False)
    message = models.ForeignKey(
        IntakeMessage,
        on_delete=models.CASCADE,
        related_name="files",
    )
    filename = models.CharField(max_length=255)
    mime = models.CharField(max_length=100)
    s3_key = models.CharField(max_length=500)
    kind = models.CharField(max_length=20, choices=Kind.choices)
    text_extracted = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Intake File"
        verbose_name_plural = "Intake Files"
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.filename} ({self.kind})"


# ---------------------------------------------------------------------------
# IntakeExtraction
# ---------------------------------------------------------------------------

class IntakeExtraction(models.Model):
    id = models.UUIDField(primary_key=True, default=generate_uuid, editable=False)
    message = models.ForeignKey(
        IntakeMessage,
        on_delete=models.CASCADE,
        related_name="extractions",
    )
    model = models.CharField(max_length=100)  # e.g. 'claude-sonnet-4-6'
    prompt_version = models.CharField(max_length=20)  # e.g. 'v1'
    result = models.JSONField(default=dict)  # structured extraction result
    confidence = models.DecimalField(max_digits=4, decimal_places=3, null=True, blank=True)
    line_count = models.SmallIntegerField(default=0)
    listing = models.ForeignKey(
        "listings.Listing",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="extractions",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Intake Extraction"
        verbose_name_plural = "Intake Extractions"
        ordering = ["-created_at"]

    def __str__(self):
        return f"Extraction for {self.message} ({self.model})"
