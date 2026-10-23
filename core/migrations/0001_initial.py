# Generated migration for core app.
# Run: python manage.py migrate core

import core.models
import django.db.models.deletion
import simple_history.models
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("accounts", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="PlatformSetting",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ("key", models.CharField(max_length=255, unique=True)),
                ("value", models.JSONField()),
                ("description", models.TextField(blank=True, default="")),
                (
                    "updated_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="platform_settings_updated",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Platform Setting",
                "verbose_name_plural": "Platform Settings",
                "ordering": ["key"],
            },
        ),
        migrations.CreateModel(
            name="HistoricalPlatformSetting",
            fields=[
                ("id", models.BigIntegerField(blank=True, db_index=True)),
                ("key", models.CharField(db_index=True, max_length=255)),
                ("value", models.JSONField()),
                ("description", models.TextField(blank=True, default="")),
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
                    "history_user",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "updated_by",
                    models.ForeignKey(
                        blank=True,
                        db_constraint=False,
                        null=True,
                        on_delete=django.db.models.deletion.DO_NOTHING,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "historical Platform Setting",
                "verbose_name_plural": "historical Platform Settings",
                "ordering": ["-history_date", "-history_id"],
                "get_latest_by": ("history_date", "history_id"),
            },
            bases=(simple_history.models.HistoricalChanges, models.Model),
        ),
        migrations.CreateModel(
            name="AuditEvent",
            fields=[
                ("id", models.UUIDField(default=core.models.generate_uuid, editable=False, primary_key=True, serialize=False)),
                (
                    "event_type",
                    models.CharField(
                        choices=[
                            ("login", "Login"),
                            ("logout", "Logout"),
                            ("password_change", "Password Change"),
                            ("mfa_enabled", "MFA Enabled"),
                            ("mfa_disabled", "MFA Disabled"),
                            ("company_status_change", "Company Status Change"),
                            ("company_verified", "Company Verified"),
                            ("member_added", "Member Added"),
                            ("member_removed", "Member Removed"),
                            ("payout_released", "Payout Released"),
                            ("payout_held", "Payout Held"),
                            ("settings_changed", "Settings Changed"),
                            ("other", "Other"),
                        ],
                        max_length=40,
                    ),
                ),
                (
                    "actor",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="audit_events_as_actor",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "target_user",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="audit_events_as_target",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "target_company",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="audit_events",
                        to="accounts.company",
                    ),
                ),
                ("ip_address", models.GenericIPAddressField(blank=True, null=True)),
                ("description", models.TextField(blank=True, default="")),
                ("extra_data", models.JSONField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "verbose_name": "Audit Event",
                "verbose_name_plural": "Audit Events",
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="auditevent",
            index=models.Index(fields=["event_type", "-created_at"], name="core_audit_event_type_idx"),
        ),
        migrations.AddIndex(
            model_name="auditevent",
            index=models.Index(fields=["actor", "-created_at"], name="core_audit_actor_idx"),
        ),
        migrations.AddIndex(
            model_name="auditevent",
            index=models.Index(fields=["target_company", "-created_at"], name="core_audit_company_idx"),
        ),
        migrations.CreateModel(
            name="BusinessHoliday",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ("date", models.DateField(unique=True)),
                ("name", models.CharField(max_length=100)),
                (
                    "observed_for",
                    models.DateField(
                        blank=True,
                        help_text="The actual holiday date if this is an observed substitute.",
                        null=True,
                    ),
                ),
                (
                    "is_active",
                    models.BooleanField(
                        default=True,
                        help_text="Only active holidays are considered by the business clock.",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Business Holiday",
                "verbose_name_plural": "Business Holidays",
                "ordering": ["date"],
            },
        ),
    ]
