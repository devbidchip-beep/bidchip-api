"""
Payments models: Payment, StripeEvent, Payout, Refund, LedgerJournal, LedgerEntry.
"""

import uuid

from django.db import models
from django.utils.translation import gettext_lazy as _
from simple_history.models import HistoricalRecords


def generate_uuid() -> uuid.UUID:
    return uuid.uuid4()


# ---------------------------------------------------------------------------
# Payment
# ---------------------------------------------------------------------------

class Payment(models.Model):
    class Method(models.TextChoices):
        CARD = "card", _("Card")
        ACH = "ach", _("ACH")
        WIRE = "wire", _("Wire")

    class CardFunding(models.TextChoices):
        CREDIT = "credit", _("Credit")
        DEBIT = "debit", _("Debit")
        PREPAID = "prepaid", _("Prepaid")
        UNKNOWN = "unknown", _("Unknown")

    class Status(models.TextChoices):
        PENDING = "pending", _("Pending")
        SUCCEEDED = "succeeded", _("Succeeded")
        FAILED = "failed", _("Failed")
        REFUNDED = "refunded", _("Refunded")
        PARTIALLY_REFUNDED = "partially_refunded", _("Partially Refunded")

    id = models.UUIDField(primary_key=True, default=generate_uuid, editable=False)
    order = models.ForeignKey(
        "orders.Order",
        on_delete=models.PROTECT,
        related_name="payments",
    )
    method = models.CharField(max_length=10, choices=Method.choices)
    card_funding = models.CharField(
        max_length=10, choices=CardFunding.choices, null=True, blank=True
    )
    billing_state = models.CharField(max_length=2, blank=True)
    surcharge_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    ach_account_holder_type = models.CharField(
        max_length=20, blank=True, help_text="Must be 'company'"
    )
    ach_verified = models.BooleanField(default=False)
    cleared_at = models.DateTimeField(null=True, blank=True)  # ACH only
    stripe_payment_intent = models.CharField(max_length=200, unique=True, null=True, blank=True)
    stripe_charge = models.CharField(max_length=200, unique=True, null=True, blank=True)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    currency = models.CharField(max_length=3, default="USD")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    wire_reference = models.CharField(max_length=100, null=True, blank=True)
    confirmed_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="confirmed_payments",
        help_text="Trusty user for wire confirmations",
    )
    confirmed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Payment"
        verbose_name_plural = "Payments"
        ordering = ["-created_at"]

    def __str__(self):
        return f"Payment {self.id} — {self.amount} {self.currency} ({self.status})"


# ---------------------------------------------------------------------------
# StripeEvent — idempotent webhook log
# ---------------------------------------------------------------------------

class StripeEvent(models.Model):
    id = models.UUIDField(primary_key=True, default=generate_uuid, editable=False)
    event_id = models.CharField(max_length=200, unique=True)
    type = models.CharField(max_length=100)
    payload = models.JSONField()
    signature_verified = models.BooleanField(default=False)
    received_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    error = models.TextField(blank=True)

    class Meta:
        verbose_name = "Stripe Event"
        verbose_name_plural = "Stripe Events"
        ordering = ["-received_at"]

    def __str__(self):
        return f"StripeEvent {self.event_id} ({self.type})"


# ---------------------------------------------------------------------------
# Payout — one per supplier order (unique enforces no double payout)
# ---------------------------------------------------------------------------

class Payout(models.Model):
    class Status(models.TextChoices):
        SCHEDULED = "scheduled", _("Scheduled")
        AWAITING_RELEASE = "awaiting_release", _("Awaiting Release")
        RELEASED = "released", _("Released")
        FAILED = "failed", _("Failed")
        REVERSED = "reversed", _("Reversed")

    id = models.UUIDField(primary_key=True, default=generate_uuid, editable=False)
    supplier_order = models.OneToOneField(
        "orders.SupplierOrder",
        on_delete=models.PROTECT,
        related_name="payout",
    )
    stripe_account = models.ForeignKey(
        "accounts.StripeAccount",
        on_delete=models.PROTECT,
        related_name="payouts",
    )
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    currency = models.CharField(max_length=3, default="USD")
    idempotency_key = models.CharField(max_length=200, unique=True)
    stripe_transfer_id = models.CharField(max_length=200, unique=True, null=True, blank=True)
    source_charge = models.CharField(max_length=200)  # buyer charge (source_transaction)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.SCHEDULED)
    released_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="released_payouts",
    )
    release_login = models.ForeignKey(
        "accounts.LoginEvent",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="payout_releases",
    )
    approved_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_payouts",
        help_text="Required for red tier supplier orders",
    )
    released_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    history = HistoricalRecords()

    class Meta:
        verbose_name = "Payout"
        verbose_name_plural = "Payouts"
        ordering = ["-created_at"]

    def __str__(self):
        return f"Payout {self.id} — {self.amount} {self.currency} ({self.status})"


# ---------------------------------------------------------------------------
# Refund
# ---------------------------------------------------------------------------

class Refund(models.Model):
    class Reason(models.TextChoices):
        FAILED_INSPECTION = "failed_inspection", _("Failed Inspection")
        DISPUTE = "dispute", _("Dispute")
        CANCELLED = "cancelled", _("Cancelled")
        FEE_ADJUSTMENT = "fee_adjustment", _("Fee Adjustment")
        SHIPPING_ADJUSTMENT = "shipping_adjustment", _("Shipping Adjustment")

    class Status(models.TextChoices):
        PENDING = "pending", _("Pending")
        APPROVED = "approved", _("Approved")
        PROCESSED = "processed", _("Processed")
        FAILED = "failed", _("Failed")

    id = models.UUIDField(primary_key=True, default=generate_uuid, editable=False)
    payment = models.ForeignKey(
        Payment,
        on_delete=models.PROTECT,
        related_name="refunds",
    )
    order_line = models.ForeignKey(
        "orders.OrderLine",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="refund_records",
    )
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    reason = models.CharField(max_length=25, choices=Reason.choices)
    stripe_refund_id = models.CharField(max_length=200, unique=True, null=True, blank=True)
    requested_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.PROTECT,
        related_name="requested_refunds",
    )
    approved_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="approved_refunds",
    )
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Refund"
        verbose_name_plural = "Refunds"
        ordering = ["-created_at"]

    def __str__(self):
        return f"Refund {self.id} — {self.amount} ({self.reason})"


# ---------------------------------------------------------------------------
# LedgerJournal
# ---------------------------------------------------------------------------

class LedgerJournal(models.Model):
    class Kind(models.TextChoices):
        CHARGE = "charge", _("Charge")
        FEE_EARNED = "fee_earned", _("Fee Earned")
        INSPECTION_EARNED = "inspection_earned", _("Inspection Earned")
        PAYOUT = "payout", _("Payout")
        REFUND = "refund", _("Refund")
        EMS_COMMISSION = "ems_commission", _("EMS Commission")
        TAX_COLLECTED = "tax_collected", _("Tax Collected")
        SHIPPING = "shipping", _("Shipping")

    id = models.UUIDField(primary_key=True, default=generate_uuid, editable=False)
    kind = models.CharField(max_length=25, choices=Kind.choices)
    order = models.ForeignKey(
        "orders.Order",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="ledger_journals",
    )
    supplier_order = models.ForeignKey(
        "orders.SupplierOrder",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="ledger_journals",
    )
    memo = models.TextField(blank=True)
    posted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Ledger Journal"
        verbose_name_plural = "Ledger Journals"
        ordering = ["-posted_at"]

    def __str__(self):
        return f"LedgerJournal {self.id} ({self.kind})"


# ---------------------------------------------------------------------------
# LedgerEntry — insert-only, double-entry
# ---------------------------------------------------------------------------

class LedgerEntry(models.Model):
    class Account(models.TextChoices):
        STRIPE_CLEARING = "stripe_clearing", _("Stripe Clearing")
        FUNDS_HELD_FOR_SUPPLIERS = "funds_held_for_suppliers", _("Funds Held for Suppliers")
        PLATFORM_FEE_REVENUE = "platform_fee_revenue", _("Platform Fee Revenue")
        INSPECTION_REVENUE = "inspection_revenue", _("Inspection Revenue")
        COMPLIANCE_REVENUE = "compliance_revenue", _("Compliance Revenue")
        SHIPPING_PAYABLE = "shipping_payable", _("Shipping Payable")
        SHIPPING_REVENUE = "shipping_revenue", _("Shipping Revenue")
        SALES_TAX_PAYABLE = "sales_tax_payable", _("Sales Tax Payable")
        EMS_COMMISSION_PAYABLE = "ems_commission_payable", _("EMS Commission Payable")
        REFUNDS = "refunds", _("Refunds")

    id = models.UUIDField(primary_key=True, default=generate_uuid, editable=False)
    journal = models.ForeignKey(
        LedgerJournal,
        on_delete=models.PROTECT,
        related_name="entries",
    )
    account = models.CharField(max_length=30, choices=Account.choices)
    debit = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    credit = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    currency = models.CharField(max_length=3, default="USD")

    class Meta:
        verbose_name = "Ledger Entry"
        verbose_name_plural = "Ledger Entries"

    def __str__(self):
        return f"LedgerEntry {self.id} — {self.account} DR:{self.debit} CR:{self.credit}"
