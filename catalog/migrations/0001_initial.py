# Generated migration for catalog app.
# Run: python manage.py migrate catalog
# Requires PostgreSQL extension: CREATE EXTENSION IF NOT EXISTS pg_trgm;

import uuid

import django.contrib.postgres.indexes
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("accounts", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="Manufacturer",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("name", models.CharField(max_length=255)),
                ("name_normalized", models.CharField(max_length=255, unique=True)),
                ("logo", models.CharField(blank=True, max_length=500)),
                ("website", models.CharField(blank=True, max_length=255)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Manufacturer",
                "verbose_name_plural": "Manufacturers",
                "ordering": ["name"],
            },
        ),
        migrations.CreateModel(
            name="ManufacturerAlias",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                (
                    "manufacturer",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="aliases",
                        to="catalog.manufacturer",
                    ),
                ),
                ("alias_normalized", models.CharField(max_length=255, unique=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "verbose_name": "Manufacturer Alias",
                "verbose_name_plural": "Manufacturer Aliases",
            },
        ),
        migrations.CreateModel(
            name="InventoryImport",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                (
                    "company",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="inventory_imports",
                        to="accounts.company",
                    ),
                ),
                (
                    "source",
                    models.CharField(
                        choices=[("csv", "CSV"), ("email", "Email"), ("api", "API")],
                        max_length=20,
                    ),
                ),
                ("file", models.CharField(blank=True, max_length=500)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("queued", "Queued"),
                            ("processing", "Processing"),
                            ("done", "Done"),
                            ("failed", "Failed"),
                        ],
                        default="queued",
                        max_length=20,
                    ),
                ),
                ("rows_total", models.IntegerField(default=0)),
                ("rows_ok", models.IntegerField(default=0)),
                ("rows_failed", models.IntegerField(default=0)),
                ("error_report", models.CharField(blank=True, max_length=500)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Inventory Import",
                "verbose_name_plural": "Inventory Imports",
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="Part",
            fields=[
                ("id", models.BigAutoField(primary_key=True, serialize=False)),
                ("mpn", models.CharField(max_length=80)),
                ("mpn_normalized", models.CharField(max_length=80)),
                (
                    "manufacturer",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="parts",
                        to="catalog.manufacturer",
                    ),
                ),
                ("description", models.TextField(blank=True)),
                ("category", models.CharField(blank=True, max_length=120)),
                (
                    "lifecycle",
                    models.CharField(
                        blank=True,
                        choices=[
                            ("active", "Active"),
                            ("nrnd", "Not Recommended for New Designs"),
                            ("eol", "End of Life"),
                            ("obsolete", "Obsolete"),
                        ],
                        max_length=20,
                        null=True,
                    ),
                ),
                ("eccn", models.CharField(blank=True, max_length=20, null=True)),
                ("is_itar", models.BooleanField(default=False)),
                ("hts_code", models.CharField(blank=True, max_length=12, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Part",
                "verbose_name_plural": "Parts",
            },
        ),
        migrations.AddConstraint(
            model_name="part",
            constraint=models.UniqueConstraint(
                fields=["mpn_normalized", "manufacturer"],
                name="unique_part_mpn_manufacturer",
            ),
        ),
        migrations.AlterUniqueTogether(
            name="part",
            unique_together={("mpn_normalized", "manufacturer")},
        ),
        migrations.AddIndex(
            model_name="part",
            index=django.contrib.postgres.indexes.GinIndex(
                fields=["mpn_normalized"],
                name="part_mpn_gin",
                opclasses=["gin_trgm_ops"],
            ),
        ),
        migrations.AddIndex(
            model_name="part",
            index=models.Index(fields=["manufacturer", "mpn_normalized"], name="catalog_par_manufac_idx"),
        ),
        migrations.CreateModel(
            name="InventoryItem",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                (
                    "company",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="inventory_items",
                        to="accounts.company",
                    ),
                ),
                (
                    "part",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="inventory_items",
                        to="catalog.part",
                    ),
                ),
                ("mpn_raw", models.CharField(max_length=120)),
                ("manufacturer_raw", models.CharField(max_length=255)),
                (
                    "manufacturer",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="inventory_items",
                        to="catalog.manufacturer",
                    ),
                ),
                ("quantity", models.PositiveIntegerField()),
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
                    ),
                ),
                ("unit_price", models.DecimalField(blank=True, decimal_places=2, max_digits=14, null=True)),
                ("currency", models.CharField(default="USD", max_length=3)),
                ("ship_from_country", models.CharField(blank=True, max_length=2)),
                (
                    "source",
                    models.CharField(
                        choices=[
                            ("csv", "CSV"),
                            ("email", "Email"),
                            ("api", "API"),
                            ("manual", "Manual"),
                        ],
                        max_length=20,
                    ),
                ),
                (
                    "import_job",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="items",
                        to="catalog.inventoryimport",
                    ),
                ),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Inventory Item",
                "verbose_name_plural": "Inventory Items",
            },
        ),
        migrations.AddIndex(
            model_name="inventoryitem",
            index=models.Index(fields=["part"], name="catalog_inv_part_id_idx"),
        ),
        migrations.AddIndex(
            model_name="inventoryitem",
            index=models.Index(fields=["company", "is_active"], name="catalog_inv_company_active_idx"),
        ),
    ]
