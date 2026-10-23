import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("listings", "0001_initial"),
        ("accounts", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="NimbleSyncLog",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                (
                    "direction",
                    models.CharField(
                        choices=[("push", "Push"), ("pull", "Pull")],
                        max_length=10,
                    ),
                ),
                ("request_hash", models.CharField(blank=True, max_length=64)),
                ("status_code", models.SmallIntegerField(blank=True, null=True)),
                ("error", models.TextField(blank=True)),
                ("at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "verbose_name": "Nimble Sync Log",
                "verbose_name_plural": "Nimble Sync Logs",
                "ordering": ["-at"],
            },
        ),
        migrations.CreateModel(
            name="NimbleRFQ",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("nimble_rfq_id", models.CharField(max_length=100, unique=True)),
                (
                    "status",
                    models.CharField(
                        choices=[("pending", "Pending"), ("active", "Active"), ("closed", "Closed")],
                        default="pending",
                        max_length=20,
                    ),
                ),
                ("pushed_at", models.DateTimeField(auto_now_add=True)),
                ("last_pulled_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "listing",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="nimble_rfq",
                        to="listings.listing",
                    ),
                ),
            ],
            options={
                "verbose_name": "Nimble RFQ",
                "verbose_name_plural": "Nimble RFQs",
            },
        ),
        migrations.CreateModel(
            name="NimbleQuote",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("nimble_quote_id", models.CharField(max_length=100, unique=True)),
                ("supplier_name_raw", models.CharField(blank=True, max_length=255)),
                ("moq", models.PositiveIntegerField(default=1)),
                ("lead_time_days", models.SmallIntegerField(default=0)),
                ("date_code_year", models.SmallIntegerField(blank=True, null=True)),
                ("packaging", models.CharField(blank=True, max_length=50)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("received", "Received"),
                            ("awarded", "Awarded"),
                            ("rejected", "Rejected"),
                        ],
                        default="received",
                        max_length=20,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "rfq",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="quotes",
                        to="integrations.nimblerfq",
                    ),
                ),
                (
                    "line",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="nimble_quotes",
                        to="listings.listingline",
                    ),
                ),
                (
                    "supplier_company",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="nimble_quotes",
                        to="accounts.company",
                    ),
                ),
            ],
            options={
                "verbose_name": "Nimble Quote",
                "verbose_name_plural": "Nimble Quotes",
            },
        ),
        migrations.CreateModel(
            name="NimblePriceBreak",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("min_qty", models.PositiveIntegerField()),
                ("unit_price", models.DecimalField(decimal_places=4, max_digits=14)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "quote",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="price_breaks",
                        to="integrations.nimblequote",
                    ),
                ),
            ],
            options={
                "verbose_name": "Nimble Price Break",
                "verbose_name_plural": "Nimble Price Breaks",
                "unique_together": {("quote", "min_qty")},
            },
        ),
    ]
