"""
Orders models: Order, SupplierOrder (FSM), OrderLine, OrderStatusLog, Receipt.
"""

import uuid

from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django_fsm import FSMField, transition


def generate_uuid() -> uuid.UUID:
    return uuid.uuid4()


# ---------------------------------------------------------------------------
# FSM state constants
# ---------------------------------------------------------------------------

AWARDED = "awarded"
PAID = "paid"
SHIPPED_TO_WAREHOUSE = "shipped_to_warehouse"
AT_WAREHOUSE = "at_warehouse"
INSPECTED = "inspected"
FAILED_INSPECTION = "failed_inspection"
SHIPPED_TO_BUYER = "shipped_to_buyer"
DELIVERED = "delivered"
PAYOUT_RELEASED = "payout_released"
DISPUTED = "disputed"
PAYOUT_PAUSED = "payout_paused"
CANCELLED = "cancelled"
REFUNDED = "refunded"


# ---------------------------------------------------------------------------
# Order
# ---------------------------------------------------------------------------

class Order(models.Model):
    class Status(models.TextChoices):
        PAYMENT_PENDING = "payment_pending", _("Payment Pending")
        PAID = "paid", _("Paid")
        IN_FULFILLMENT = "in_fulfillment", _("In Fulfillment")
        PARTIALLY_SHIPPED = "partially_shipped", _("Partially Shipped")
        SHIPPED = "shipped", _("Shipped")
        DELIVERED = "delivered", _("Delivered")
        COMPLETED = "completed", _("Completed")
        CANCELLED = "cancelled", _("Cancelled")
        REFUNDED = "refunded", _("Refunded")

    id = models.UUIDField(primary_key=True, default=generate_uuid, editable=False)
    number = models.CharField(max_length=20, unique=True)  # BC-2026-000123
    buyer_company = models.ForeignKey(
        "accounts.Company",
        on_delete=models.PROTECT,
        related_name="orders",
    )
    placed_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.PROTECT,
        related_name="placed_orders",
    )
    listing = models.ForeignKey(
        "listings.Listing",
        on_delete=models.PROTECT,
        related_name="orders",
    )
    po_number = models.CharField(max_length=60, blank=True, null=True)
    po_file = models.CharField(max_length=500, blank=True)  # S3 key
    status = models.CharField(
        max_length=30,
        choices=Status.choices,
        default=Status.PAYMENT_PENDING,
    )
    ship_to = models.ForeignKey(
        "accounts.Address",
        on_delete=models.PROTECT,
        related_name="orders",
    )
    ship_to_snapshot = models.JSONField(default=dict)  # copied at checkout
    currency = models.CharField(max_length=3, default="USD")

    # Financials — never use FloatField for money
    principal_total = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    buyer_fee_total = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    inspection_fee_total = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    compliance_fee_total = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    shipping_estimate = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    shipping_final = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    oem_uplift_total = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    tax_total = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    card_surcharge = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    card_surcharge_rate = models.DecimalField(max_digits=6, decimal_places=4, default=0)
    grand_total = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    tax_certificate = models.ForeignKey(
        "accounts.TaxCertificate",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="orders",
    )
    pricing_snapshot = models.JSONField(default=dict)  # frozen after payment

    paid_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Order"
        verbose_name_plural = "Orders"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["buyer_company", "paid_at"]),
            models.Index(fields=["po_number"]),
        ]

    def __str__(self):
        return self.number


# ---------------------------------------------------------------------------
# SupplierOrder — FSM state machine
# ---------------------------------------------------------------------------

class SupplierOrder(models.Model):
    class RiskTier(models.TextChoices):
        GREEN = "green", _("Green")
        YELLOW = "yellow", _("Yellow")
        RED = "red", _("Red")

    class DeliveredSource(models.TextChoices):
        CARRIER_SCAN = "carrier_scan", _("Carrier Scan")
        BUYER_CONFIRMATION = "buyer_confirmation", _("Buyer Confirmation")

    id = models.UUIDField(primary_key=True, default=generate_uuid, editable=False)
    order = models.ForeignKey(
        Order,
        on_delete=models.PROTECT,
        related_name="supplier_orders",
    )
    supplier_company = models.ForeignKey(
        "accounts.Company",
        on_delete=models.PROTECT,
        related_name="supplier_orders",
    )
    anonymous_supplier_id = models.CharField(max_length=16, unique=True)

    # FSM
    status = FSMField(default=AWARDED)

    risk_tier = models.CharField(
        max_length=10,
        choices=RiskTier.choices,
        default=RiskTier.GREEN,
    )

    # Financials — never use FloatField for money
    principal = models.DecimalField(max_digits=14, decimal_places=2)
    seller_fee = models.DecimalField(max_digits=14, decimal_places=2)
    payout_amount = models.DecimalField(max_digits=14, decimal_places=2)

    hold_days = models.SmallIntegerField(null=True, blank=True)
    requires_manual_release = models.BooleanField(default=False)
    delivered_at = models.DateTimeField(null=True, blank=True)
    delivered_source = models.CharField(
        max_length=20,
        choices=DeliveredSource.choices,
        null=True,
        blank=True,
    )
    payout_eligible_at = models.DateTimeField(null=True, blank=True)
    ems_link = models.ForeignKey(
        "pricing.OEMEMSLink",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="supplier_orders",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Supplier Order"
        verbose_name_plural = "Supplier Orders"
        indexes = [
            models.Index(fields=["status", "payout_eligible_at"]),
            models.Index(fields=["supplier_company", "status"]),
        ]
        constraints = [
            models.CheckConstraint(
                check=models.Q(payout_amount__gte=0),
                name="payout_amount_non_negative",
            )
        ]

    def __str__(self):
        return f"SupplierOrder {self.anonymous_supplier_id} ({self.status})"

    # ------------------------------------------------------------------
    # FSM transitions
    # ------------------------------------------------------------------

    @transition(field=status, source=AWARDED, target=PAID)
    def mark_paid(self):
        pass

    @transition(field=status, source=PAID, target=SHIPPED_TO_WAREHOUSE)
    def mark_shipped_to_warehouse(self):
        pass

    @transition(field=status, source=SHIPPED_TO_WAREHOUSE, target=AT_WAREHOUSE)
    def mark_at_warehouse(self):
        pass

    @transition(field=status, source=AT_WAREHOUSE, target=INSPECTED)
    def mark_inspected(self):
        pass

    @transition(field=status, source=AT_WAREHOUSE, target=FAILED_INSPECTION)
    def mark_failed_inspection(self):
        pass

    @transition(field=status, source=INSPECTED, target=SHIPPED_TO_BUYER)
    def mark_shipped_to_buyer(self):
        pass

    @transition(field=status, source=SHIPPED_TO_BUYER, target=DELIVERED)
    def mark_delivered(self):
        self.delivered_at = timezone.now()

    @transition(field=status, source=DELIVERED, target=PAYOUT_RELEASED)
    def release_payout(self):
        pass

    @transition(field=status, source=[AWARDED, PAID, SHIPPED_TO_WAREHOUSE], target=CANCELLED)
    def cancel(self):
        pass


# ---------------------------------------------------------------------------
# OrderLine
# ---------------------------------------------------------------------------

class OrderLine(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", _("Pending")
        RECEIVED = "received", _("Received")
        PASSED = "passed", _("Passed")
        FAILED_INSPECTION = "failed_inspection", _("Failed Inspection")
        SHIPPED = "shipped", _("Shipped")
        REFUNDED = "refunded", _("Refunded")

    id = models.UUIDField(primary_key=True, default=generate_uuid, editable=False)
    supplier_order = models.ForeignKey(
        SupplierOrder,
        on_delete=models.PROTECT,
        related_name="lines",
    )
    award = models.OneToOneField(
        "bidding.Award",
        on_delete=models.PROTECT,
        related_name="order_line",
    )
    listing_line = models.ForeignKey(
        "listings.ListingLine",
        on_delete=models.PROTECT,
        related_name="order_lines",
    )
    quantity = models.PositiveIntegerField()
    unit_price = models.DecimalField(max_digits=14, decimal_places=4)
    line_total = models.DecimalField(max_digits=14, decimal_places=2)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    refund = models.ForeignKey(
        "payments.Refund",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="order_lines",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Order Line"
        verbose_name_plural = "Order Lines"

    def __str__(self):
        return f"OrderLine {self.id} — {self.listing_line} x{self.quantity}"


# ---------------------------------------------------------------------------
# OrderStatusLog — insert-only
# ---------------------------------------------------------------------------

class OrderStatusLog(models.Model):
    class ActorKind(models.TextChoices):
        USER = "user", _("User")
        STAFF = "staff", _("Staff")
        SYSTEM = "system", _("System")
        WEBHOOK = "webhook", _("Webhook")

    id = models.UUIDField(primary_key=True, default=generate_uuid, editable=False)
    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="status_logs",
    )
    supplier_order = models.ForeignKey(
        SupplierOrder,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="status_logs",
    )
    from_status = models.CharField(max_length=50, blank=True)
    to_status = models.CharField(max_length=50)
    actor = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="order_status_logs",
    )
    actor_kind = models.CharField(max_length=10, choices=ActorKind.choices, default=ActorKind.SYSTEM)
    reason = models.TextField(blank=True)
    at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Order Status Log"
        verbose_name_plural = "Order Status Logs"
        ordering = ["-at"]

    def __str__(self):
        return f"{self.order or self.supplier_order}: {self.from_status} → {self.to_status}"


# ---------------------------------------------------------------------------
# Receipt
# ---------------------------------------------------------------------------

class Receipt(models.Model):
    id = models.UUIDField(primary_key=True, default=generate_uuid, editable=False)
    order = models.OneToOneField(
        Order,
        on_delete=models.PROTECT,
        related_name="receipt",
    )
    number = models.CharField(max_length=30, unique=True)
    issued_at = models.DateTimeField(auto_now_add=True)
    lines = models.JSONField(default=list)
    totals = models.JSONField(default=dict)
    pdf = models.CharField(max_length=500, blank=True)  # S3 key

    class Meta:
        verbose_name = "Receipt"
        verbose_name_plural = "Receipts"

    def __str__(self):
        return self.number
