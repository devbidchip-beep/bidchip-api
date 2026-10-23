import uuid

from django.db import models
from django.utils.translation import gettext_lazy as _


def generate_uuid() -> uuid.UUID:
    return uuid.uuid4()


class NotificationTemplate(models.Model):
    id = models.UUIDField(primary_key=True, default=generate_uuid, editable=False)
    key = models.CharField(max_length=100, unique=True)
    subject = models.CharField(max_length=200)
    body_html = models.TextField()
    body_text = models.TextField()
    version = models.PositiveIntegerField(default=1)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Notification Template"
        verbose_name_plural = "Notification Templates"
        ordering = ["key"]

    def __str__(self):
        return f"{self.key} (v{self.version})"


class Notification(models.Model):
    class Channel(models.TextChoices):
        EMAIL = "email", _("Email")
        IN_APP = "in_app", _("In-App")

    class Status(models.TextChoices):
        QUEUED = "queued", _("Queued")
        SENT = "sent", _("Sent")
        FAILED = "failed", _("Failed")
        READ = "read", _("Read")

    id = models.UUIDField(primary_key=True, default=generate_uuid, editable=False)
    user = models.ForeignKey(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    template = models.ForeignKey(
        NotificationTemplate,
        on_delete=models.PROTECT,
        related_name="notifications",
    )
    channel = models.CharField(max_length=10, choices=Channel.choices, default=Channel.EMAIL)
    context = models.JSONField(default=dict)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.QUEUED)
    ses_message_id = models.CharField(max_length=200, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Notification"
        verbose_name_plural = "Notifications"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "status"]),
        ]

    def __str__(self):
        return f"Notification({self.template.key}) → {self.user} [{self.status}]"
