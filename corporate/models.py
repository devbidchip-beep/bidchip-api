"""
Corporate models: Invitation, Budget, OrderLimit, ApprovalRequest, ShipToAssignment.
"""

import uuid

from django.db import models
from django.utils.translation import gettext_lazy as _


def generate_uuid() -> uuid.UUID:
    return uuid.uuid4()


# ---------------------------------------------------------------------------
# Invitation
# ---------------------------------------------------------------------------

class Invitation(models.Model):
    """Email invite to join a company. Token is stored hashed (SHA-256); raw token shown once."""

    class Role(models.TextChoices):
        OWNER = "owner", _("Owner")
        FINANCE = "finance", _("Finance")
        MANAGER = "manager", _("Manager")
        BUYER = "buyer", _("Buyer")
        SELLER = "seller", _("Seller")
        READ_ONLY = "read_only", _("Read Only")

    id = models.UUIDField(primary_key=True, default=generate_uuid, editable=False)
    company = models.ForeignKey(
        "accounts.Company",
        on_delete=models.CASCADE,
        related_name="invitations",
    )
    email = models.EmailField()
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.READ_ONLY)
    token_hash = models.CharField(max_length=64)  # SHA-256 hex digest
    invited_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.PROTECT,
        related_name="sent_invitations",
    )
    expires_at = models.DateTimeField()
    accepted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Invitation"
        verbose_name_plural = "Invitations"
        indexes = [
            models.Index(fields=["company", "email"]),
        ]

    def save(self, *args, **kwargs):
        self.email = self.email.lower()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Invitation({self.email} → {self.company})"


# ---------------------------------------------------------------------------
# Budget
# ---------------------------------------------------------------------------

class Budget(models.Model):
    """Per-member spending limit per period."""

    class Period(models.TextChoices):
        MONTH = "month", _("Month")
        QUARTER = "quarter", _("Quarter")

    id = models.UUIDField(primary_key=True, default=generate_uuid, editable=False)
    member = models.ForeignKey(
        "accounts.CompanyMember",
        on_delete=models.CASCADE,
        related_name="budgets",
    )
    period_start = models.DateField()
    period = models.CharField(max_length=10, choices=Period.choices, default=Period.MONTH)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    currency = models.CharField(max_length=3, default="USD")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Budget"
        verbose_name_plural = "Budgets"
        unique_together = [("member", "period_start")]

    def __str__(self):
        return f"Budget({self.member} {self.period_start} {self.amount} {self.currency})"


# ---------------------------------------------------------------------------
# OrderLimit
# ---------------------------------------------------------------------------

class OrderLimit(models.Model):
    """Per-member maximum single order amount."""

    id = models.UUIDField(primary_key=True, default=generate_uuid, editable=False)
    member = models.OneToOneField(
        "accounts.CompanyMember",
        on_delete=models.CASCADE,
        related_name="order_limit",
    )
    max_order_amount = models.DecimalField(max_digits=14, decimal_places=2)
    currency = models.CharField(max_length=3, default="USD")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Order Limit"
        verbose_name_plural = "Order Limits"

    def __str__(self):
        return f"OrderLimit({self.member} max={self.max_order_amount} {self.currency})"


# ---------------------------------------------------------------------------
# ApprovalRequest
# ---------------------------------------------------------------------------

class ApprovalRequest(models.Model):
    """
    Fail-closed: no approval → no publish/pay.
    """

    class SubjectType(models.TextChoices):
        LISTING_PUBLISH = "listing_publish", _("Listing Publish")
        CHECKOUT = "checkout", _("Checkout")

    class Status(models.TextChoices):
        PENDING = "pending", _("Pending")
        APPROVED = "approved", _("Approved")
        REJECTED = "rejected", _("Rejected")

    id = models.UUIDField(primary_key=True, default=generate_uuid, editable=False)
    company = models.ForeignKey(
        "accounts.Company",
        on_delete=models.PROTECT,
        related_name="approval_requests",
    )
    requested_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.PROTECT,
        related_name="approval_requests_made",
    )
    approver = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approval_requests_decided",
    )
    subject_type = models.CharField(max_length=20, choices=SubjectType.choices)
    listing = models.ForeignKey(
        "listings.Listing",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approval_requests",
    )
    order = models.ForeignKey(
        "orders.Order",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approval_requests",
    )
    amount = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.PENDING,
    )
    decided_at = models.DateTimeField(null=True, blank=True)
    note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Approval Request"
        verbose_name_plural = "Approval Requests"
        ordering = ["-created_at"]

    def __str__(self):
        return f"ApprovalRequest({self.subject_type} by {self.requested_by} [{self.status}])"


# ---------------------------------------------------------------------------
# ShipToAssignment
# ---------------------------------------------------------------------------

class ShipToAssignment(models.Model):
    """Which addresses a buyer member may use for shipping."""

    id = models.UUIDField(primary_key=True, default=generate_uuid, editable=False)
    member = models.ForeignKey(
        "accounts.CompanyMember",
        on_delete=models.CASCADE,
        related_name="ship_to_assignments",
    )
    address = models.ForeignKey(
        "accounts.Address",
        on_delete=models.CASCADE,
        related_name="ship_to_assignments",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Ship-To Assignment"
        verbose_name_plural = "Ship-To Assignments"
        unique_together = [("member", "address")]

    def __str__(self):
        return f"ShipToAssignment({self.member} → {self.address})"
