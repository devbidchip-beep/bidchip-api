"""
Trust models: RiskAssessment, Dispute, DisputeFile, Rating, MessageThread,
Message, SellerChainEvent.
"""

import uuid

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _


def generate_uuid() -> uuid.UUID:
    return uuid.uuid4()


# ---------------------------------------------------------------------------
# RiskAssessment
# ---------------------------------------------------------------------------

class RiskAssessment(models.Model):
    class Tier(models.TextChoices):
        GREEN = "green", _("Green")
        YELLOW = "yellow", _("Yellow")
        RED = "red", _("Red")

    id = models.UUIDField(primary_key=True, default=generate_uuid, editable=False)
    supplier_order = models.OneToOneField(
        "orders.SupplierOrder",
        on_delete=models.PROTECT,
        related_name="risk_assessment",
    )
    score = models.DecimalField(max_digits=5, decimal_places=2)
    tier = models.CharField(max_length=10, choices=Tier.choices)
    factors = models.JSONField(default=dict)
    override_tier = models.CharField(
        max_length=10,
        choices=Tier.choices,
        null=True,
        blank=True,
    )
    overridden_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="risk_overrides",
    )
    override_reason = models.TextField(blank=True)
    assessed_at = models.DateTimeField(auto_now_add=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Risk Assessment"
        verbose_name_plural = "Risk Assessments"
        ordering = ["-assessed_at"]

    def __str__(self):
        return f"RiskAssessment {self.supplier_order_id} — {self.tier} ({self.score})"

    @property
    def effective_tier(self):
        return self.override_tier or self.tier


# ---------------------------------------------------------------------------
# Dispute
# ---------------------------------------------------------------------------

class Dispute(models.Model):
    class Reason(models.TextChoices):
        NOT_AS_DESCRIBED = "not_as_described", _("Not as Described")
        QUANTITY = "quantity", _("Quantity")
        COUNTERFEIT_SUSPECTED = "counterfeit_suspected", _("Counterfeit Suspected")
        DAMAGED = "damaged", _("Damaged")
        NOT_RECEIVED = "not_received", _("Not Received")
        OTHER = "other", _("Other")

    class Status(models.TextChoices):
        OPEN = "open", _("Open")
        AWAITING_RETURN = "awaiting_return", _("Awaiting Return")
        UNDER_REVIEW = "under_review", _("Under Review")
        RESOLVED_BUYER = "resolved_buyer", _("Resolved — Buyer")
        RESOLVED_SELLER = "resolved_seller", _("Resolved — Seller")
        SPLIT = "split", _("Split")
        WITHDRAWN = "withdrawn", _("Withdrawn")

    id = models.UUIDField(primary_key=True, default=generate_uuid, editable=False)
    supplier_order = models.ForeignKey(
        "orders.SupplierOrder",
        on_delete=models.PROTECT,
        related_name="disputes",
    )
    opened_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.PROTECT,
        related_name="opened_disputes",
    )
    reason = models.CharField(max_length=30, choices=Reason.choices)
    description = models.TextField()
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.OPEN,
    )
    resolution_note = models.TextField(blank=True)
    resolved_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="resolved_disputes",
    )
    opened_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Dispute"
        verbose_name_plural = "Disputes"
        ordering = ["-opened_at"]

    def __str__(self):
        return f"Dispute {self.id} — {self.reason} ({self.status})"

    def save(self, *args, **kwargs):
        is_new = self._state.adding
        # Detect status change to 'open' for new records
        if is_new and self.status == self.Status.OPEN:
            super().save(*args, **kwargs)
            self._on_opened()
        else:
            super().save(*args, **kwargs)

    def _on_opened(self):
        """Set supplier_order to disputed and pause any pending payout."""
        supplier_order = self.supplier_order
        # Direct status update (bypass FSM for disputed state)
        from orders.models import DISPUTED
        supplier_order.status = DISPUTED
        supplier_order.save(update_fields=["status", "updated_at"])

        # Pause payout
        try:
            from payments.models import Payout
            payout = supplier_order.payout
            if payout.status == Payout.Status.SCHEDULED:
                payout.status = Payout.Status.AWAITING_RELEASE
                payout.save(update_fields=["status", "updated_at"])
        except Exception:
            pass


# ---------------------------------------------------------------------------
# DisputeFile
# ---------------------------------------------------------------------------

class DisputeFile(models.Model):
    id = models.UUIDField(primary_key=True, default=generate_uuid, editable=False)
    dispute = models.ForeignKey(
        Dispute,
        on_delete=models.CASCADE,
        related_name="files",
    )
    file = models.CharField(max_length=500)  # S3 key
    uploaded_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.PROTECT,
        related_name="dispute_files",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Dispute File"
        verbose_name_plural = "Dispute Files"
        ordering = ["-created_at"]

    def __str__(self):
        return f"DisputeFile {self.id} — {self.dispute_id}"


# ---------------------------------------------------------------------------
# Rating
# ---------------------------------------------------------------------------

SCORE_VALIDATORS = [MinValueValidator(1), MaxValueValidator(5)]


class Rating(models.Model):
    class Direction(models.TextChoices):
        BUYER_TO_SUPPLIER = "buyer_to_supplier", _("Buyer to Supplier")
        SUPPLIER_TO_BUYER = "supplier_to_buyer", _("Supplier to Buyer")

    id = models.UUIDField(primary_key=True, default=generate_uuid, editable=False)
    supplier_order = models.ForeignKey(
        "orders.SupplierOrder",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ratings",
    )
    legacy_ref = models.CharField(max_length=100, blank=True, null=True)
    rater_company = models.ForeignKey(
        "accounts.Company",
        on_delete=models.PROTECT,
        related_name="given_ratings",
    )
    ratee_company = models.ForeignKey(
        "accounts.Company",
        on_delete=models.PROTECT,
        related_name="received_ratings",
    )
    direction = models.CharField(max_length=20, choices=Direction.choices)
    quality = models.SmallIntegerField(validators=SCORE_VALIDATORS)
    communication = models.SmallIntegerField(validators=SCORE_VALIDATORS)
    shipping = models.SmallIntegerField(validators=SCORE_VALIDATORS)
    documentation = models.SmallIntegerField(validators=SCORE_VALIDATORS)
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Rating"
        verbose_name_plural = "Ratings"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["supplier_order", "direction"],
                name="unique_rating_per_order_direction",
                condition=models.Q(supplier_order__isnull=False),
            )
        ]
        indexes = [
            models.Index(fields=["ratee_company", "direction"]),
        ]

    def __str__(self):
        return f"Rating {self.id} — {self.direction} ({self.quality}/{self.communication}/{self.shipping}/{self.documentation})"


# ---------------------------------------------------------------------------
# MessageThread
# ---------------------------------------------------------------------------

class MessageThread(models.Model):
    class Status(models.TextChoices):
        OPEN = "open", _("Open")
        CLOSED = "closed", _("Closed")

    id = models.UUIDField(primary_key=True, default=generate_uuid, editable=False)
    listing = models.ForeignKey(
        "listings.Listing",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="message_threads",
    )
    supplier_order = models.ForeignKey(
        "orders.SupplierOrder",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="message_threads",
    )
    buyer_company = models.ForeignKey(
        "accounts.Company",
        on_delete=models.PROTECT,
        related_name="buyer_threads",
    )
    supplier_company = models.ForeignKey(
        "accounts.Company",
        on_delete=models.PROTECT,
        related_name="supplier_threads",
    )
    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.OPEN,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Message Thread"
        verbose_name_plural = "Message Threads"
        ordering = ["-updated_at"]

    def __str__(self):
        return f"MessageThread {self.id} ({self.status})"


# ---------------------------------------------------------------------------
# Message — anonymous, moderated
# ---------------------------------------------------------------------------

class Message(models.Model):
    class ModerationStatus(models.TextChoices):
        PENDING = "pending", _("Pending")
        APPROVED = "approved", _("Approved")
        BLOCKED = "blocked", _("Blocked")

    id = models.UUIDField(primary_key=True, default=generate_uuid, editable=False)
    thread = models.ForeignKey(
        MessageThread,
        on_delete=models.CASCADE,
        related_name="messages",
    )
    sender = models.ForeignKey(
        "accounts.User",
        on_delete=models.PROTECT,
        related_name="sent_messages",
    )
    body = models.TextField()
    moderation_status = models.CharField(
        max_length=10,
        choices=ModerationStatus.choices,
        default=ModerationStatus.PENDING,
    )
    moderation_flags = models.JSONField(default=dict)
    moderated_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="moderated_messages",
    )
    sent_at = models.DateTimeField(auto_now_add=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Message"
        verbose_name_plural = "Messages"
        ordering = ["sent_at"]

    def __str__(self):
        return f"Message {self.id} — {self.moderation_status}"


# ---------------------------------------------------------------------------
# SellerChainEvent — payout protection hash chain (insert-only)
# ---------------------------------------------------------------------------

class SellerChainEvent(models.Model):
    """
    Insert-only append-only hash chain for payout protection.
    Each event links to its predecessor via prev_hash, forming a tamper-evident
    chain. Never update or delete rows — only append new ones.
    """

    class EventType(models.TextChoices):
        BID_COMMITTED = "bid_committed", _("Bid Committed")
        AWARD = "award", _("Award")
        SHIPPED = "shipped", _("Shipped")
        INSPECTED = "inspected", _("Inspected")
        DELIVERED = "delivered", _("Delivered")
        PAYOUT_RELEASE_REQUESTED = "payout_release_requested", _("Payout Release Requested")
        PAYOUT_RELEASED = "payout_released", _("Payout Released")
        BANK_CHANGED = "bank_changed", _("Bank Changed")
        LOGIN_STRONG = "login_strong", _("Login Strong")
        CHAIN_FROZEN = "chain_frozen", _("Chain Frozen")

    id = models.UUIDField(primary_key=True, default=generate_uuid, editable=False)
    supplier_company = models.ForeignKey(
        "accounts.Company",
        on_delete=models.PROTECT,
        related_name="chain_events",
    )
    seq = models.BigIntegerField()
    event_type = models.CharField(max_length=30, choices=EventType.choices)
    ref_type = models.CharField(max_length=50, blank=True)
    ref_id = models.CharField(max_length=36, blank=True)  # UUID of referenced object
    payload_hash = models.CharField(max_length=64)   # SHA-256 of event data
    prev_hash = models.CharField(max_length=64)       # previous event's hash
    hash = models.CharField(max_length=64)            # SHA-256(prev_hash || seq || event_type || payload_hash)
    kms_sig = models.TextField(blank=True)            # KMS signature placeholder
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Seller Chain Event"
        verbose_name_plural = "Seller Chain Events"
        ordering = ["supplier_company", "seq"]
        unique_together = [("supplier_company", "seq")]
        indexes = [
            models.Index(fields=["supplier_company", "seq"]),
        ]

    def __str__(self):
        return f"SellerChainEvent {self.supplier_company_id} seq={self.seq} {self.event_type}"
