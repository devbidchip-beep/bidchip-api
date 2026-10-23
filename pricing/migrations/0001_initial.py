import uuid

import django.db.models.deletion
import simple_history.models
from django.conf import settings
from django.db import migrations, models
from django.db.models import F, Q


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("accounts", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="FeeSchedule",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("name", models.CharField(max_length=100)),
                (
                    "kind",
                    models.CharField(
                        choices=[("standard", "Standard"), ("byos", "BYOS"), ("high_risk", "High Risk")],
                        default="standard",
                        max_length=20,
                    ),
                ),
                (
                    "side",
                    models.CharField(
                        choices=[("buyer", "Buyer"), ("seller", "Seller")],
                        default="buyer",
                        max_length=10,
                    ),
                ),
                ("min_fee", models.DecimalField(blank=True, decimal_places=2, max_digits=14, null=True)),
                ("effective_from", models.DateField()),
                ("effective_to", models.DateField(blank=True, null=True)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "company",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="fee_schedules",
                        to="accounts.company",
                    ),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="created_fee_schedules",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Fee Schedule",
                "verbose_name_plural": "Fee Schedules",
                "ordering": ["-effective_from"],
            },
        ),
        migrations.CreateModel(
            name="HistoricalFeeSchedule",
            fields=[
                ("id", models.UUIDField(db_index=True, default=uuid.uuid4, editable=False)),
                ("name", models.CharField(max_length=100)),
                (
                    "kind",
                    models.CharField(
                        choices=[("standard", "Standard"), ("byos", "BYOS"), ("high_risk", "High Risk")],
                        default="standard",
                        max_length=20,
                    ),
                ),
                (
                    "side",
                    models.CharField(
                        choices=[("buyer", "Buyer"), ("seller", "Seller")],
                        default="buyer",
                        max_length=10,
                    ),
                ),
                ("min_fee", models.DecimalField(blank=True, decimal_places=2, max_digits=14, null=True)),
                ("effective_from", models.DateField()),
                ("effective_to", models.DateField(blank=True, null=True)),
                ("is_active", models.BooleanField(default=True)),
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
                    "company",
                    models.ForeignKey(
                        blank=True,
                        db_constraint=False,
                        null=True,
                        on_delete=django.db.models.deletion.DO_NOTHING,
                        related_name="+",
                        to="accounts.company",
                    ),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        db_constraint=False,
                        null=True,
                        on_delete=django.db.models.deletion.DO_NOTHING,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
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
                "verbose_name": "historical fee schedule",
                "verbose_name_plural": "historical fee schedules",
                "ordering": ("-history_date", "-history_id"),
                "get_latest_by": ("history_date", "history_id"),
            },
            bases=(simple_history.models.HistoricalChanges, models.Model),
        ),
        migrations.CreateModel(
            name="FeeBracket",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("lower_bound", models.DecimalField(decimal_places=2, max_digits=14)),
                ("upper_bound", models.DecimalField(blank=True, decimal_places=2, max_digits=14, null=True)),
                ("rate", models.DecimalField(decimal_places=4, help_text="0.0700 = 7%", max_digits=6)),
                (
                    "schedule",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="brackets",
                        to="pricing.feeschedule",
                    ),
                ),
            ],
            options={
                "verbose_name": "Fee Bracket",
                "verbose_name_plural": "Fee Brackets",
                "ordering": ["schedule", "lower_bound"],
            },
        ),
        migrations.AlterUniqueTogether(
            name="feebracket",
            unique_together={("schedule", "lower_bound")},
        ),
        migrations.CreateModel(
            name="VolumeDiscountTier",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("lower_bound", models.DecimalField(decimal_places=2, max_digits=14)),
                ("upper_bound", models.DecimalField(blank=True, decimal_places=2, max_digits=14, null=True)),
                ("points_off", models.DecimalField(decimal_places=4, help_text="0.0050 = 0.5 points off the rate", max_digits=6)),
                ("negotiated", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "verbose_name": "Volume Discount Tier",
                "verbose_name_plural": "Volume Discount Tiers",
                "ordering": ["lower_bound"],
            },
        ),
        migrations.CreateModel(
            name="CompanyVolume",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("as_of", models.DateField()),
                ("volume_12m_buyer", models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ("volume_12m_seller", models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ("dispute_rate", models.DecimalField(decimal_places=4, default=0, max_digits=6)),
                ("discount_points", models.DecimalField(decimal_places=4, default=0, max_digits=6)),
                ("eligible", models.BooleanField(default=True)),
                ("reason", models.CharField(blank=True, max_length=200)),
                (
                    "company",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="volume_snapshots",
                        to="accounts.company",
                    ),
                ),
            ],
            options={
                "verbose_name": "Company Volume",
                "verbose_name_plural": "Company Volumes",
                "ordering": ["-as_of"],
            },
        ),
        migrations.AlterUniqueTogether(
            name="companyvolume",
            unique_together={("company", "as_of")},
        ),
        migrations.CreateModel(
            name="OEMEMSLink",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                (
                    "origin",
                    models.CharField(
                        choices=[("ems_referred", "EMS Referred"), ("oem_added", "OEM Added")],
                        max_length=20,
                    ),
                ),
                ("commission_rate", models.DecimalField(decimal_places=4, help_text="Copied from PlatformSetting at link creation time", max_digits=6)),
                (
                    "status",
                    models.CharField(
                        choices=[("pending", "Pending"), ("active", "Active"), ("ended", "Ended")],
                        default="pending",
                        max_length=10,
                    ),
                ),
                ("oem_approved_at", models.DateTimeField(blank=True, null=True)),
                ("ems_approved_at", models.DateTimeField(blank=True, null=True)),
                ("ended_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "ems_company",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="ems_links",
                        to="accounts.company",
                    ),
                ),
                (
                    "oem_company",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="oem_links",
                        to="accounts.company",
                    ),
                ),
            ],
            options={
                "verbose_name": "OEM/EMS Link",
                "verbose_name_plural": "OEM/EMS Links",
            },
        ),
        migrations.AddConstraint(
            model_name="oemEMSlink",
            constraint=models.UniqueConstraint(
                condition=models.Q(status="active"),
                fields=["oem_company", "ems_company"],
                name="unique_active_oem_ems_link",
            ),
        ),
    ]
