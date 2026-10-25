"""
Logistics models: Shipment, Package, RateQuote, Inspection,
InspectionPhoto, LabTest.
"""

import uuid

from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _


def generate_uuid() -> uuid.UUID:
    return uuid.uuid4()


# ---------------------------------------------------------------------------
# Shipment
# ---------------------------------------------------------------------------

class Shipment(models.Model):
    class Leg(models.TextChoices):
        INBOUND = "inbound", _("Inbound")
        OUTBOUND = "outbound", _("Outbound")
        RETURN_TO_BIDCHIP = "return_to_bidchip", _("Return to BidChip")
        RETURN_TO_OWNER = "return_to_owner", _("Return to Owner")

    class Carrier(models.TextChoices):
        UPS = "ups", _("UPS")
        FEDEX = "fedex", _("FedEx")
        DHL = "dhl", _("DHL")
        OTHER = "other", _("Other")

    class PaidBy(models.TextChoices):
        SUPPLIER = "supplier", _("Supplier")
        BUYER = "buyer", _("Buyer")
        BIDCHIP = "bidchip", _("BidChip")

    class Status(models.TextChoices):
        DRAFT = "draft", _("Draft")
        LABEL_CREATED = "label_created", _("Label Created")
        IN_TRANSIT = "in_transit", _("In Transit")
        DELIVERED = "delivered", _("Delivered")
        EXCEPTION = "exception", _("Exception")
        RETURNED = "returned", _("Returned")

    id = models.UUIDField(primary_key=True, default=generate_uuid, editable=False)
    leg = models.CharField(max_length=20, choices=Leg.choices)

    # Exactly one of these must be set (enforced in clean())
    order = models.ForeignKey(
        "orders.Order",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="shipments",
    )
    supplier_order = models.ForeignKey(
        "orders.SupplierOrder",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="shipments",
    )
    # TODO: FK to trust.Dispute — will be resolved once the trust app is created.
    # Using string ref 'trust.Dispute'. null=True so migrations don't break before
    # trust app exists. Add trust app to INSTALLED_APPS before running migrations
    # if trust is not yet present; Django will warn but won't break.
    dispute = models.ForeignKey(
        "trust.Dispute",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="shipments",
    )

    carrier = models.CharField(max_length=10, choices=Carrier.choices)
    service_code = models.CharField(max_length=50, blank=True)
    tracking_number = models.CharField(max_length=100, blank=True)
    label = models.CharField(max_length=500, blank=True)  # S3 key
    po_number_on_label = models.CharField(max_length=60, blank=True)  # copied from Order.po_number
    paid_by = models.CharField(max_length=10, choices=PaidBy.choices, blank=True)
    cost_estimated = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    cost_actual = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    shipped_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    is_partial = models.BooleanField(default=False)  # partial BOM: more outbound shipments follow

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Shipment"
        verbose_name_plural = "Shipments"
        indexes = [
            models.Index(fields=["tracking_number"]),  # tracking webhooks look up by this
        ]

    def __str__(self):
        return f"Shipment {self.id} [{self.leg}] {self.tracking_number or '(no tracking)'}"

    def clean(self):
        """
        Validate that exactly one of order/supplier_order/dispute is set
        based on the leg value.
        """
        leg = self.leg

        if leg == self.Leg.INBOUND:
            if not self.supplier_order_id:
                raise ValidationError(
                    {"supplier_order": _("Inbound shipments require a supplier_order.")}
                )
            if self.order_id:
                raise ValidationError(
                    {"order": _("Inbound shipments must not have an order.")}
                )
            if self.dispute_id:
                raise ValidationError(
                    {"dispute": _("Inbound shipments must not have a dispute.")}
                )

        elif leg == self.Leg.OUTBOUND:
            if not self.order_id:
                raise ValidationError(
                    {"order": _("Outbound shipments require an order.")}
                )
            if self.supplier_order_id:
                raise ValidationError(
                    {"supplier_order": _("Outbound shipments must not have a supplier_order.")}
                )
            if self.dispute_id:
                raise ValidationError(
                    {"dispute": _("Outbound shipments must not have a dispute.")}
                )

        elif leg in (self.Leg.RETURN_TO_BIDCHIP, self.Leg.RETURN_TO_OWNER):
            if not self.dispute_id:
                raise ValidationError(
                    {"dispute": _("Return shipments require a dispute.")}
                )
            if self.order_id:
                raise ValidationError(
                    {"order": _("Return shipments must not have an order.")}
                )
            if self.supplier_order_id:
                raise ValidationError(
                    {"supplier_order": _("Return shipments must not have a supplier_order.")}
                )


# ---------------------------------------------------------------------------
# Package
# ---------------------------------------------------------------------------

class Package(models.Model):
    class SizedBy(models.TextChoices):
        AI = "ai", _("AI")
        WAREHOUSE = "warehouse", _("Warehouse")
        SUPPLIER = "supplier", _("Supplier")

    id = models.UUIDField(primary_key=True, default=generate_uuid, editable=False)
    shipment = models.ForeignKey(Shipment, on_delete=models.CASCADE, related_name="packages")
    length_cm = models.DecimalField(max_digits=6, decimal_places=2)
    width_cm = models.DecimalField(max_digits=6, decimal_places=2)
    height_cm = models.DecimalField(max_digits=6, decimal_places=2)
    weight_kg = models.DecimalField(max_digits=6, decimal_places=3)
    sized_by = models.CharField(max_length=10, choices=SizedBy.choices)
    contents = models.JSONField(default=list)  # list of OrderLine ids
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Package"
        verbose_name_plural = "Packages"

    def __str__(self):
        return f"Package {self.id} for Shipment {self.shipment_id}"


# ---------------------------------------------------------------------------
# RateQuote
# ---------------------------------------------------------------------------

class RateQuote(models.Model):
    class Carrier(models.TextChoices):
        UPS = "ups", _("UPS")
        FEDEX = "fedex", _("FedEx")
        DHL = "dhl", _("DHL")

    id = models.UUIDField(primary_key=True, default=generate_uuid, editable=False)
    shipment = models.ForeignKey(Shipment, on_delete=models.CASCADE, related_name="rate_quotes")
    carrier = models.CharField(max_length=10, choices=Carrier.choices)
    service_code = models.CharField(max_length=50)
    service_name = models.CharField(max_length=100, blank=True)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    currency = models.CharField(max_length=3, default="USD")
    transit_days = models.SmallIntegerField(null=True, blank=True)
    is_next_day = models.BooleanField(default=False)
    chosen = models.BooleanField(default=False)
    quoted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Rate Quote"
        verbose_name_plural = "Rate Quotes"
        ordering = ["amount"]

    def __str__(self):
        return f"{self.carrier} {self.service_code} ${self.amount}"


# ---------------------------------------------------------------------------
# Inspection
# ---------------------------------------------------------------------------

class Inspection(models.Model):
    class Level(models.TextChoices):
        STANDARD = "standard", _("Standard")
        EXTENDED = "extended", _("Extended")
        FULL_LAB = "full_lab", _("Full Lab")

    class Result(models.TextChoices):
        PASSED = "passed", _("Passed")
        FAILED = "failed", _("Failed")
        PARTIAL = "partial", _("Partial")

    id = models.UUIDField(primary_key=True, default=generate_uuid, editable=False)
    supplier_order = models.OneToOneField(
        "orders.SupplierOrder",
        on_delete=models.PROTECT,
        related_name="inspection",
    )
    inspector = models.ForeignKey(
        "accounts.User",
        on_delete=models.PROTECT,
        related_name="inspections",
    )
    level = models.CharField(max_length=10, choices=Level.choices)
    result = models.CharField(max_length=10, choices=Result.choices, blank=True)
    notes = models.TextField(blank=True)
    counted_quantity = models.PositiveIntegerField(null=True, blank=True)
    inspected_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Inspection"
        verbose_name_plural = "Inspections"

    def __str__(self):
        return f"Inspection for {self.supplier_order} — {self.result or 'pending'}"


# ---------------------------------------------------------------------------
# InspectionPhoto
# ---------------------------------------------------------------------------

class InspectionPhoto(models.Model):
    id = models.UUIDField(primary_key=True, default=generate_uuid, editable=False)
    inspection = models.ForeignKey(
        Inspection,
        on_delete=models.CASCADE,
        related_name="photos",
    )
    file = models.CharField(max_length=500)  # S3 key
    caption = models.CharField(max_length=200, blank=True)
    order_line = models.ForeignKey(
        "orders.OrderLine",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="inspection_photos",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Inspection Photo"
        verbose_name_plural = "Inspection Photos"

    def __str__(self):
        return f"Photo {self.id} for Inspection {self.inspection_id}"


# ---------------------------------------------------------------------------
# LabTest
# ---------------------------------------------------------------------------

class LabTest(models.Model):
    class Result(models.TextChoices):
        PASS = "pass", _("Pass")
        FAIL = "fail", _("Fail")
        INCONCLUSIVE = "inconclusive", _("Inconclusive")

    id = models.UUIDField(primary_key=True, default=generate_uuid, editable=False)
    order_line = models.ForeignKey(
        "orders.OrderLine",
        on_delete=models.PROTECT,
        related_name="lab_tests",
    )
    lab_user = models.ForeignKey(
        "accounts.User",
        on_delete=models.PROTECT,
        related_name="lab_tests",
    )
    method = models.CharField(max_length=100)
    price = models.DecimalField(max_digits=14, decimal_places=2)
    result = models.CharField(max_length=15, choices=Result.choices, blank=True)
    report = models.CharField(max_length=500, blank=True)  # S3 key
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Lab Test"
        verbose_name_plural = "Lab Tests"

    def __str__(self):
        return f"LabTest {self.id} [{self.method}] — {self.result or 'pending'}"
