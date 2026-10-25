"""
Initial migration for the logistics app.

NOTE: The `dispute` FK on Shipment references 'trust.Dispute' via a string ref.
This FK will be fully resolved once the trust app is created and added to
INSTALLED_APPS. Until then, null=True prevents any integrity issue. Django will
issue a warning if the trust app is not in INSTALLED_APPS when this migration
runs, but it will not error provided the field remains nullable.

TODO: Once the trust app is created, ensure 'trust' is in INSTALLED_APPS and
      run `makemigrations` again to resolve the FK dependency properly.
"""

import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("accounts", "0001_initial"),
        ("orders", "0001_initial"),
        # NOTE: 'trust' app dependency is intentionally omitted here because
        # the trust app does not exist yet. The dispute FK is declared as
        # null=True with a string reference. Once trust is created:
        #   1. Add ("trust", "0001_initial") to this dependencies list, or
        #   2. Run makemigrations to auto-generate the dependency.
    ]

    operations = [
        # ----------------------------------------------------------------
        # Shipment
        # ----------------------------------------------------------------
        migrations.CreateModel(
            name="Shipment",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "leg",
                    models.CharField(
                        choices=[
                            ("inbound", "Inbound"),
                            ("outbound", "Outbound"),
                            ("return_to_bidchip", "Return to BidChip"),
                            ("return_to_owner", "Return to Owner"),
                        ],
                        max_length=20,
                    ),
                ),
                (
                    "carrier",
                    models.CharField(
                        choices=[
                            ("ups", "UPS"),
                            ("fedex", "FedEx"),
                            ("dhl", "DHL"),
                            ("other", "Other"),
                        ],
                        max_length=10,
                    ),
                ),
                ("service_code", models.CharField(blank=True, max_length=50)),
                ("tracking_number", models.CharField(blank=True, max_length=100)),
                ("label", models.CharField(blank=True, max_length=500)),
                ("po_number_on_label", models.CharField(blank=True, max_length=60)),
                (
                    "paid_by",
                    models.CharField(
                        blank=True,
                        choices=[
                            ("supplier", "Supplier"),
                            ("buyer", "Buyer"),
                            ("bidchip", "BidChip"),
                        ],
                        max_length=10,
                    ),
                ),
                (
                    "cost_estimated",
                    models.DecimalField(decimal_places=2, default=0, max_digits=14),
                ),
                (
                    "cost_actual",
                    models.DecimalField(decimal_places=2, default=0, max_digits=14),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("draft", "Draft"),
                            ("label_created", "Label Created"),
                            ("in_transit", "In Transit"),
                            ("delivered", "Delivered"),
                            ("exception", "Exception"),
                            ("returned", "Returned"),
                        ],
                        default="draft",
                        max_length=20,
                    ),
                ),
                ("shipped_at", models.DateTimeField(blank=True, null=True)),
                ("delivered_at", models.DateTimeField(blank=True, null=True)),
                ("is_partial", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                # FKs
                (
                    "order",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="shipments",
                        to="orders.order",
                    ),
                ),
                (
                    "supplier_order",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="shipments",
                        to="orders.supplierorder",
                    ),
                ),
                # TODO: The dispute FK to 'trust.Dispute' is intentionally
                # omitted from this initial migration because the trust app
                # does not yet exist. Once trust is created:
                #   1. Add 'trust' to INSTALLED_APPS in settings.
                #   2. Run `makemigrations logistics` — Django will generate a
                #      new migration that adds the dispute ForeignKey column.
                # The model declares the field with null=True so the Django ORM
                # correctly reflects the intended schema at runtime, but the DB
                # column is only added by that subsequent auto-generated migration.
            ],
            options={
                "verbose_name": "Shipment",
                "verbose_name_plural": "Shipments",
            },
        ),
        migrations.AddIndex(
            model_name="shipment",
            index=models.Index(fields=["tracking_number"], name="logistics_s_trackin_idx"),
        ),
        # ----------------------------------------------------------------
        # Package
        # ----------------------------------------------------------------
        migrations.CreateModel(
            name="Package",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "shipment",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="packages",
                        to="logistics.shipment",
                    ),
                ),
                ("length_cm", models.DecimalField(decimal_places=2, max_digits=6)),
                ("width_cm", models.DecimalField(decimal_places=2, max_digits=6)),
                ("height_cm", models.DecimalField(decimal_places=2, max_digits=6)),
                ("weight_kg", models.DecimalField(decimal_places=3, max_digits=6)),
                (
                    "sized_by",
                    models.CharField(
                        choices=[
                            ("ai", "AI"),
                            ("warehouse", "Warehouse"),
                            ("supplier", "Supplier"),
                        ],
                        max_length=10,
                    ),
                ),
                ("contents", models.JSONField(default=list)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "verbose_name": "Package",
                "verbose_name_plural": "Packages",
            },
        ),
        # ----------------------------------------------------------------
        # RateQuote
        # ----------------------------------------------------------------
        migrations.CreateModel(
            name="RateQuote",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "shipment",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="rate_quotes",
                        to="logistics.shipment",
                    ),
                ),
                (
                    "carrier",
                    models.CharField(
                        choices=[
                            ("ups", "UPS"),
                            ("fedex", "FedEx"),
                            ("dhl", "DHL"),
                        ],
                        max_length=10,
                    ),
                ),
                ("service_code", models.CharField(max_length=50)),
                ("service_name", models.CharField(blank=True, max_length=100)),
                ("amount", models.DecimalField(decimal_places=2, max_digits=14)),
                ("currency", models.CharField(default="USD", max_length=3)),
                ("transit_days", models.SmallIntegerField(blank=True, null=True)),
                ("is_next_day", models.BooleanField(default=False)),
                ("chosen", models.BooleanField(default=False)),
                ("quoted_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "verbose_name": "Rate Quote",
                "verbose_name_plural": "Rate Quotes",
                "ordering": ["amount"],
            },
        ),
        # ----------------------------------------------------------------
        # Inspection
        # ----------------------------------------------------------------
        migrations.CreateModel(
            name="Inspection",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "supplier_order",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="inspection",
                        to="orders.supplierorder",
                    ),
                ),
                (
                    "inspector",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="inspections",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "level",
                    models.CharField(
                        choices=[
                            ("standard", "Standard"),
                            ("extended", "Extended"),
                            ("full_lab", "Full Lab"),
                        ],
                        max_length=10,
                    ),
                ),
                ("result", models.CharField(blank=True, max_length=10)),
                ("notes", models.TextField(blank=True)),
                ("counted_quantity", models.PositiveIntegerField(blank=True, null=True)),
                ("inspected_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Inspection",
                "verbose_name_plural": "Inspections",
            },
        ),
        # ----------------------------------------------------------------
        # InspectionPhoto
        # ----------------------------------------------------------------
        migrations.CreateModel(
            name="InspectionPhoto",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "inspection",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="photos",
                        to="logistics.inspection",
                    ),
                ),
                ("file", models.CharField(max_length=500)),
                ("caption", models.CharField(blank=True, max_length=200)),
                (
                    "order_line",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="inspection_photos",
                        to="orders.orderline",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "verbose_name": "Inspection Photo",
                "verbose_name_plural": "Inspection Photos",
            },
        ),
        # ----------------------------------------------------------------
        # LabTest
        # ----------------------------------------------------------------
        migrations.CreateModel(
            name="LabTest",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "order_line",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="lab_tests",
                        to="orders.orderline",
                    ),
                ),
                (
                    "lab_user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="lab_tests",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                ("method", models.CharField(max_length=100)),
                ("price", models.DecimalField(decimal_places=2, max_digits=14)),
                ("result", models.CharField(blank=True, max_length=15)),
                ("report", models.CharField(blank=True, max_length=500)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Lab Test",
                "verbose_name_plural": "Lab Tests",
            },
        ),
    ]
