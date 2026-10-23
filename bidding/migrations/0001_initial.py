import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("listings", "0001_initial"),
        ("catalog", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Bid",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("unit_price", models.DecimalField(decimal_places=4, max_digits=14)),
                ("quantity_offered", models.PositiveIntegerField()),
                ("date_code_year", models.SmallIntegerField(blank=True, null=True)),
                (
                    "packaging",
                    models.CharField(
                        blank=True,
                        choices=[
                            ("reel", "Reel"),
                            ("cut_tape", "Cut Tape"),
                            ("tray", "Tray"),
                            ("tube", "Tube"),
                            ("bulk", "Bulk"),
                            ("other", "Other"),
                        ],
                        max_length=20,
                        null=True,
                    ),
                ),
                ("lead_time_days", models.SmallIntegerField(default=0)),
                ("is_exact_match", models.BooleanField(default=False)),
                ("exception_reasons", models.JSONField(default=list)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("active", "Active"),
                            ("withdrawn", "Withdrawn"),
                            ("won", "Won"),
                            ("partially_won", "Partially Won"),
                            ("lost", "Lost"),
                        ],
                        default="active",
                        max_length=20,
                    ),
                ),
                ("commitment_hash", models.CharField(blank=True, max_length=64)),
                ("supplier_net_shown", models.DecimalField(blank=True, decimal_places=2, max_digits=14, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "inventory_item",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="bids",
                        to="catalog.inventoryitem",
                    ),
                ),
                (
                    "line",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="bids",
                        to="listings.listingline",
                    ),
                ),
                (
                    "placed_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="placed_bids",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "supplier_company",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="bids",
                        to="accounts.company",
                    ),
                ),
            ],
            options={
                "verbose_name": "Bid",
                "verbose_name_plural": "Bids",
            },
        ),
        migrations.CreateModel(
            name="Award",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("quantity_awarded", models.PositiveIntegerField()),
                ("unit_price", models.DecimalField(decimal_places=4, max_digits=14)),
                ("rank", models.SmallIntegerField(default=1)),
                ("awarded_at", models.DateTimeField(auto_now_add=True)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("awarded", "Awarded"),
                            ("converted", "Converted"),
                            ("cancelled", "Cancelled"),
                        ],
                        default="awarded",
                        max_length=20,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "awarded_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="awards_made",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "bid",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="awards",
                        to="bidding.bid",
                    ),
                ),
                (
                    "line",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="awards",
                        to="listings.listingline",
                    ),
                ),
            ],
            options={
                "verbose_name": "Award",
                "verbose_name_plural": "Awards",
                "ordering": ["rank"],
            },
        ),
        migrations.AddIndex(
            model_name="bid",
            index=models.Index(
                fields=["line", "status", "is_exact_match", "unit_price"],
                name="bidding_bid_line_id_status_idx",
            ),
        ),
        migrations.AddConstraint(
            model_name="bid",
            constraint=models.UniqueConstraint(
                condition=models.Q(status="active"),
                fields=["line", "supplier_company"],
                name="unique_active_bid_per_supplier_per_line",
            ),
        ),
    ]
