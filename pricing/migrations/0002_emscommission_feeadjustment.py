"""
Adds EMSCommission and FeeAdjustment models which depend on orders and payments.
Separate from 0001 to break circular dependency (orders depends on pricing for
OEMEMSLink, and EMSCommission/FeeAdjustment depend on orders/payments).
"""

import uuid

import django.db.models.deletion
import simple_history.models
from django.conf import settings
from django.db import migrations, models
from django.db.models import F, Q


class Migration(migrations.Migration):

    dependencies = [
        ("pricing", "0001_initial"),
        ("orders", "0002_orderline_refund"),
        ("payments", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="EMSCommission",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("amount", models.DecimalField(decimal_places=2, max_digits=14)),
                ("currency", models.CharField(default="USD", max_length=3)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Pending"),
                            ("payable", "Payable"),
                            ("paid", "Paid"),
                            ("cancelled", "Cancelled"),
                        ],
                        default="pending",
                        max_length=10,
                    ),
                ),
                ("stripe_transfer_id", models.CharField(blank=True, max_length=200, null=True, unique=True)),
                ("idempotency_key", models.CharField(max_length=200, unique=True)),
                ("paid_at", models.DateTimeField(blank=True, null=True)),
                ("tax_year", models.SmallIntegerField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "order",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="ems_commission",
                        to="orders.order",
                    ),
                ),
                (
                    "link",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="commissions",
                        to="pricing.oemEMSlink",
                    ),
                ),
            ],
            options={
                "verbose_name": "EMS Commission",
                "verbose_name_plural": "EMS Commissions",
            },
        ),
        migrations.CreateModel(
            name="FeeAdjustment",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                (
                    "side",
                    models.CharField(
                        choices=[("buyer", "Buyer"), ("seller", "Seller")],
                        max_length=10,
                    ),
                ),
                ("amount", models.DecimalField(decimal_places=2, max_digits=14)),
                ("reason", models.TextField()),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("requested", "Requested"),
                            ("approved", "Approved"),
                            ("rejected", "Rejected"),
                            ("applied", "Applied"),
                        ],
                        default="requested",
                        max_length=10,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "order",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="fee_adjustments",
                        to="orders.order",
                    ),
                ),
                (
                    "supplier_order",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="fee_adjustments",
                        to="orders.supplierorder",
                    ),
                ),
                (
                    "requested_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="fee_adjustment_requests",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "approved_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="fee_adjustment_approvals",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "refund",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="fee_adjustments",
                        to="payments.refund",
                    ),
                ),
            ],
            options={
                "verbose_name": "Fee Adjustment",
                "verbose_name_plural": "Fee Adjustments",
            },
        ),
        migrations.AddConstraint(
            model_name="feeadjustment",
            constraint=models.CheckConstraint(
                check=~models.Q(approved_by=models.F("requested_by")),
                name="fee_adjustment_two_person",
            ),
        ),
        migrations.CreateModel(
            name="HistoricalFeeAdjustment",
            fields=[
                ("id", models.UUIDField(db_index=True, default=uuid.uuid4, editable=False)),
                (
                    "side",
                    models.CharField(
                        choices=[("buyer", "Buyer"), ("seller", "Seller")],
                        max_length=10,
                    ),
                ),
                ("amount", models.DecimalField(decimal_places=2, max_digits=14)),
                ("reason", models.TextField()),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("requested", "Requested"),
                            ("approved", "Approved"),
                            ("rejected", "Rejected"),
                            ("applied", "Applied"),
                        ],
                        default="requested",
                        max_length=10,
                    ),
                ),
                ("created_at", models.DateTimeField(blank=True, editable=False)),
                ("updated_at", models.DateTimeField(blank=True, editable=False)),
                ("history_id", models.AutoField(primary_key=True, serialize=False)),
                ("history_date", models.DateTimeField(db_index=True)),
                ("history_change_reason", models.CharField(max_length=100, null=True)),
                (
                    "history_type",
                    models.CharField(
                        choices=[("+", "Created"), ("~", "Changed"), ("-", "Deleted")],
                        max_length=1,
                    ),
                ),
                (
                    "order",
                    models.ForeignKey(
                        blank=True,
                        db_constraint=False,
                        null=True,
                        on_delete=django.db.models.deletion.DO_NOTHING,
                        related_name="+",
                        to="orders.order",
                    ),
                ),
                (
                    "history_user",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "historical fee adjustment",
                "verbose_name_plural": "historical fee adjustments",
                "ordering": ("-history_date", "-history_id"),
                "get_latest_by": ("history_date", "history_id"),
            },
            bases=(simple_history.models.HistoricalChanges, models.Model),
        ),
    ]
