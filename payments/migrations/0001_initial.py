import uuid

import django.db.models.deletion
import simple_history.models
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("accounts", "0001_initial"),
        ("orders", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Payment",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                (
                    "method",
                    models.CharField(
                        choices=[("card", "Card"), ("ach", "ACH"), ("wire", "Wire")],
                        max_length=10,
                    ),
                ),
                (
                    "card_funding",
                    models.CharField(
                        blank=True,
                        choices=[
                            ("credit", "Credit"),
                            ("debit", "Debit"),
                            ("prepaid", "Prepaid"),
                            ("unknown", "Unknown"),
                        ],
                        max_length=10,
                        null=True,
                    ),
                ),
                ("billing_state", models.CharField(blank=True, max_length=2)),
                ("surcharge_amount", models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ("ach_account_holder_type", models.CharField(blank=True, help_text="Must be 'company'", max_length=20)),
                ("ach_verified", models.BooleanField(default=False)),
                ("cleared_at", models.DateTimeField(blank=True, null=True)),
                ("stripe_payment_intent", models.CharField(blank=True, max_length=200, null=True, unique=True)),
                ("stripe_charge", models.CharField(blank=True, max_length=200, null=True, unique=True)),
                ("amount", models.DecimalField(decimal_places=2, max_digits=14)),
                ("currency", models.CharField(default="USD", max_length=3)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Pending"),
                            ("succeeded", "Succeeded"),
                            ("failed", "Failed"),
                            ("refunded", "Refunded"),
                            ("partially_refunded", "Partially Refunded"),
                        ],
                        default="pending",
                        max_length=20,
                    ),
                ),
                ("wire_reference", models.CharField(blank=True, max_length=100, null=True)),
                ("confirmed_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "order",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="payments",
                        to="orders.order",
                    ),
                ),
                (
                    "confirmed_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="confirmed_payments",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Payment",
                "verbose_name_plural": "Payments",
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="StripeEvent",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("event_id", models.CharField(max_length=200, unique=True)),
                ("type", models.CharField(max_length=100)),
                ("payload", models.JSONField()),
                ("signature_verified", models.BooleanField(default=False)),
                ("received_at", models.DateTimeField(auto_now_add=True)),
                ("processed_at", models.DateTimeField(blank=True, null=True)),
                ("error", models.TextField(blank=True)),
            ],
            options={
                "verbose_name": "Stripe Event",
                "verbose_name_plural": "Stripe Events",
                "ordering": ["-received_at"],
            },
        ),
        migrations.CreateModel(
            name="Refund",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("amount", models.DecimalField(decimal_places=2, max_digits=14)),
                (
                    "reason",
                    models.CharField(
                        choices=[
                            ("failed_inspection", "Failed Inspection"),
                            ("dispute", "Dispute"),
                            ("cancelled", "Cancelled"),
                            ("fee_adjustment", "Fee Adjustment"),
                            ("shipping_adjustment", "Shipping Adjustment"),
                        ],
                        max_length=25,
                    ),
                ),
                ("stripe_refund_id", models.CharField(blank=True, max_length=200, null=True, unique=True)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Pending"),
                            ("approved", "Approved"),
                            ("processed", "Processed"),
                            ("failed", "Failed"),
                        ],
                        default="pending",
                        max_length=10,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "payment",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="refunds",
                        to="payments.payment",
                    ),
                ),
                (
                    "order_line",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="refund_records",
                        to="orders.orderline",
                    ),
                ),
                (
                    "requested_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="requested_refunds",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "approved_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="approved_refunds",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Refund",
                "verbose_name_plural": "Refunds",
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="Payout",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("amount", models.DecimalField(decimal_places=2, max_digits=14)),
                ("currency", models.CharField(default="USD", max_length=3)),
                ("idempotency_key", models.CharField(max_length=200, unique=True)),
                ("stripe_transfer_id", models.CharField(blank=True, max_length=200, null=True, unique=True)),
                ("source_charge", models.CharField(max_length=200)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("scheduled", "Scheduled"),
                            ("awaiting_release", "Awaiting Release"),
                            ("released", "Released"),
                            ("failed", "Failed"),
                            ("reversed", "Reversed"),
                        ],
                        default="scheduled",
                        max_length=20,
                    ),
                ),
                ("released_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "supplier_order",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="payout",
                        to="orders.supplierorder",
                    ),
                ),
                (
                    "stripe_account",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="payouts",
                        to="accounts.stripeaccount",
                    ),
                ),
                (
                    "released_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="released_payouts",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "release_login",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="payout_releases",
                        to="accounts.loginevent",
                    ),
                ),
                (
                    "approved_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="approved_payouts",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Payout",
                "verbose_name_plural": "Payouts",
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="HistoricalPayout",
            fields=[
                ("id", models.UUIDField(db_index=True, default=uuid.uuid4, editable=False)),
                ("amount", models.DecimalField(decimal_places=2, max_digits=14)),
                ("currency", models.CharField(default="USD", max_length=3)),
                ("idempotency_key", models.CharField(db_index=True, max_length=200)),
                ("stripe_transfer_id", models.CharField(blank=True, db_index=True, max_length=200, null=True)),
                ("source_charge", models.CharField(max_length=200)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("scheduled", "Scheduled"),
                            ("awaiting_release", "Awaiting Release"),
                            ("released", "Released"),
                            ("failed", "Failed"),
                            ("reversed", "Reversed"),
                        ],
                        default="scheduled",
                        max_length=20,
                    ),
                ),
                ("released_at", models.DateTimeField(blank=True, null=True)),
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
                    "supplier_order",
                    models.ForeignKey(
                        blank=True,
                        db_constraint=False,
                        null=True,
                        on_delete=django.db.models.deletion.DO_NOTHING,
                        related_name="+",
                        to="orders.supplierorder",
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
                "verbose_name": "historical payout",
                "verbose_name_plural": "historical payouts",
                "ordering": ("-history_date", "-history_id"),
                "get_latest_by": ("history_date", "history_id"),
            },
            bases=(simple_history.models.HistoricalChanges, models.Model),
        ),
        migrations.CreateModel(
            name="LedgerJournal",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                (
                    "kind",
                    models.CharField(
                        choices=[
                            ("charge", "Charge"),
                            ("fee_earned", "Fee Earned"),
                            ("inspection_earned", "Inspection Earned"),
                            ("payout", "Payout"),
                            ("refund", "Refund"),
                            ("ems_commission", "EMS Commission"),
                            ("tax_collected", "Tax Collected"),
                            ("shipping", "Shipping"),
                        ],
                        max_length=25,
                    ),
                ),
                ("memo", models.TextField(blank=True)),
                ("posted_at", models.DateTimeField(auto_now_add=True)),
                (
                    "order",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="ledger_journals",
                        to="orders.order",
                    ),
                ),
                (
                    "supplier_order",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="ledger_journals",
                        to="orders.supplierorder",
                    ),
                ),
            ],
            options={
                "verbose_name": "Ledger Journal",
                "verbose_name_plural": "Ledger Journals",
                "ordering": ["-posted_at"],
            },
        ),
        migrations.CreateModel(
            name="LedgerEntry",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                (
                    "account",
                    models.CharField(
                        choices=[
                            ("stripe_clearing", "Stripe Clearing"),
                            ("funds_held_for_suppliers", "Funds Held for Suppliers"),
                            ("platform_fee_revenue", "Platform Fee Revenue"),
                            ("inspection_revenue", "Inspection Revenue"),
                            ("compliance_revenue", "Compliance Revenue"),
                            ("shipping_payable", "Shipping Payable"),
                            ("shipping_revenue", "Shipping Revenue"),
                            ("sales_tax_payable", "Sales Tax Payable"),
                            ("ems_commission_payable", "EMS Commission Payable"),
                            ("refunds", "Refunds"),
                        ],
                        max_length=30,
                    ),
                ),
                ("debit", models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ("credit", models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ("currency", models.CharField(default="USD", max_length=3)),
                (
                    "journal",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="entries",
                        to="payments.ledgerjournal",
                    ),
                ),
            ],
            options={
                "verbose_name": "Ledger Entry",
                "verbose_name_plural": "Ledger Entries",
            },
        ),
    ]
