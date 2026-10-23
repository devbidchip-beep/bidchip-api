import uuid

import django.db.models.deletion
import django_fsm
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("accounts", "0001_initial"),
        ("bidding", "0001_initial"),
        ("listings", "0001_initial"),
        ("pricing", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Order",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("number", models.CharField(max_length=20, unique=True)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("payment_pending", "Payment Pending"),
                            ("paid", "Paid"),
                            ("in_fulfillment", "In Fulfillment"),
                            ("partially_shipped", "Partially Shipped"),
                            ("shipped", "Shipped"),
                            ("delivered", "Delivered"),
                            ("completed", "Completed"),
                            ("cancelled", "Cancelled"),
                            ("refunded", "Refunded"),
                        ],
                        default="payment_pending",
                        max_length=30,
                    ),
                ),
                ("po_number", models.CharField(blank=True, max_length=60, null=True)),
                ("po_file", models.CharField(blank=True, max_length=500)),
                ("ship_to_snapshot", models.JSONField(default=dict)),
                ("currency", models.CharField(default="USD", max_length=3)),
                ("principal_total", models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ("buyer_fee_total", models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ("inspection_fee_total", models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ("compliance_fee_total", models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ("shipping_estimate", models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ("shipping_final", models.DecimalField(blank=True, decimal_places=2, max_digits=14, null=True)),
                ("oem_uplift_total", models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ("tax_total", models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ("card_surcharge", models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ("card_surcharge_rate", models.DecimalField(decimal_places=4, default=0, max_digits=6)),
                ("grand_total", models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ("pricing_snapshot", models.JSONField(default=dict)),
                ("paid_at", models.DateTimeField(blank=True, null=True)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "buyer_company",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="orders",
                        to="accounts.company",
                    ),
                ),
                (
                    "placed_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="placed_orders",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "listing",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="orders",
                        to="listings.listing",
                    ),
                ),
                (
                    "ship_to",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="orders",
                        to="accounts.address",
                    ),
                ),
                (
                    "tax_certificate",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="orders",
                        to="accounts.taxcertificate",
                    ),
                ),
            ],
            options={
                "verbose_name": "Order",
                "verbose_name_plural": "Orders",
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="order",
            index=models.Index(fields=["buyer_company", "paid_at"], name="orders_order_buyer_paid_idx"),
        ),
        migrations.AddIndex(
            model_name="order",
            index=models.Index(fields=["po_number"], name="orders_order_po_number_idx"),
        ),
        migrations.CreateModel(
            name="SupplierOrder",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("anonymous_supplier_id", models.CharField(max_length=16, unique=True)),
                ("status", django_fsm.FSMField(default="awarded", max_length=50, protected=True)),
                (
                    "risk_tier",
                    models.CharField(
                        choices=[("green", "Green"), ("yellow", "Yellow"), ("red", "Red")],
                        default="green",
                        max_length=10,
                    ),
                ),
                ("principal", models.DecimalField(decimal_places=2, max_digits=14)),
                ("seller_fee", models.DecimalField(decimal_places=2, max_digits=14)),
                ("payout_amount", models.DecimalField(decimal_places=2, max_digits=14)),
                ("hold_days", models.SmallIntegerField(blank=True, null=True)),
                ("requires_manual_release", models.BooleanField(default=False)),
                ("delivered_at", models.DateTimeField(blank=True, null=True)),
                (
                    "delivered_source",
                    models.CharField(
                        blank=True,
                        choices=[("carrier_scan", "Carrier Scan"), ("buyer_confirmation", "Buyer Confirmation")],
                        max_length=20,
                        null=True,
                    ),
                ),
                ("payout_eligible_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "order",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="supplier_orders",
                        to="orders.order",
                    ),
                ),
                (
                    "supplier_company",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="supplier_orders",
                        to="accounts.company",
                    ),
                ),
                (
                    "ems_link",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="supplier_orders",
                        to="pricing.oemEMSlink",
                    ),
                ),
            ],
            options={
                "verbose_name": "Supplier Order",
                "verbose_name_plural": "Supplier Orders",
            },
        ),
        migrations.AddIndex(
            model_name="supplierorder",
            index=models.Index(fields=["status", "payout_eligible_at"], name="orders_supplierorder_status_payout_idx"),
        ),
        migrations.AddIndex(
            model_name="supplierorder",
            index=models.Index(fields=["supplier_company", "status"], name="orders_supplierorder_company_status_idx"),
        ),
        migrations.AddConstraint(
            model_name="supplierorder",
            constraint=models.CheckConstraint(
                check=models.Q(payout_amount__gte=0),
                name="payout_amount_non_negative",
            ),
        ),
        migrations.CreateModel(
            name="OrderLine",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("quantity", models.PositiveIntegerField()),
                ("unit_price", models.DecimalField(decimal_places=4, max_digits=14)),
                ("line_total", models.DecimalField(decimal_places=2, max_digits=14)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Pending"),
                            ("received", "Received"),
                            ("passed", "Passed"),
                            ("failed_inspection", "Failed Inspection"),
                            ("shipped", "Shipped"),
                            ("refunded", "Refunded"),
                        ],
                        default="pending",
                        max_length=20,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "supplier_order",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="lines",
                        to="orders.supplierorder",
                    ),
                ),
                (
                    "award",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="order_line",
                        to="bidding.award",
                    ),
                ),
                (
                    "listing_line",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="order_lines",
                        to="listings.listingline",
                    ),
                ),
            ],
            options={
                "verbose_name": "Order Line",
                "verbose_name_plural": "Order Lines",
            },
        ),
        migrations.CreateModel(
            name="OrderStatusLog",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("from_status", models.CharField(blank=True, max_length=50)),
                ("to_status", models.CharField(max_length=50)),
                (
                    "actor_kind",
                    models.CharField(
                        choices=[
                            ("user", "User"),
                            ("staff", "Staff"),
                            ("system", "System"),
                            ("webhook", "Webhook"),
                        ],
                        default="system",
                        max_length=10,
                    ),
                ),
                ("reason", models.TextField(blank=True)),
                ("at", models.DateTimeField(auto_now_add=True)),
                (
                    "order",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="status_logs",
                        to="orders.order",
                    ),
                ),
                (
                    "supplier_order",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="status_logs",
                        to="orders.supplierorder",
                    ),
                ),
                (
                    "actor",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="order_status_logs",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Order Status Log",
                "verbose_name_plural": "Order Status Logs",
                "ordering": ["-at"],
            },
        ),
        migrations.CreateModel(
            name="Receipt",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("number", models.CharField(max_length=30, unique=True)),
                ("issued_at", models.DateTimeField(auto_now_add=True)),
                ("lines", models.JSONField(default=list)),
                ("totals", models.JSONField(default=dict)),
                ("pdf", models.CharField(blank=True, max_length=500)),
                (
                    "order",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="receipt",
                        to="orders.order",
                    ),
                ),
            ],
            options={
                "verbose_name": "Receipt",
                "verbose_name_plural": "Receipts",
            },
        ),
    ]
