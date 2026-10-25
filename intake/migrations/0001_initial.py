import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("accounts", "0001_initial"),
        ("listings", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="IntakeMessage",
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
                    "channel",
                    models.CharField(
                        choices=[
                            ("email", "Email"),
                            ("upload", "Upload"),
                            ("api", "API"),
                        ],
                        max_length=20,
                    ),
                ),
                ("from_email", models.EmailField(blank=True, max_length=254, null=True)),
                (
                    "company",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="intake_messages",
                        to="accounts.company",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="intake_messages",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                ("subject", models.CharField(blank=True, max_length=500)),
                ("raw_s3_key", models.CharField(blank=True, max_length=500)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("received", "Received"),
                            ("extracting", "Extracting"),
                            ("needs_review", "Needs Review"),
                            ("draft_created", "Draft Created"),
                            ("failed", "Failed"),
                            ("rejected_sender", "Rejected Sender"),
                        ],
                        default="received",
                        max_length=20,
                    ),
                ),
                ("received_at", models.DateTimeField(auto_now_add=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Intake Message",
                "verbose_name_plural": "Intake Messages",
                "ordering": ["-received_at"],
            },
        ),
        migrations.AddIndex(
            model_name="intakemessage",
            index=models.Index(
                fields=["company", "status"], name="intake_msg_company_status_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="intakemessage",
            index=models.Index(
                fields=["status", "-received_at"], name="intake_msg_status_received_idx"
            ),
        ),
        migrations.CreateModel(
            name="IntakeFile",
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
                    "message",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="files",
                        to="intake.intakemessage",
                    ),
                ),
                ("filename", models.CharField(max_length=255)),
                ("mime", models.CharField(max_length=100)),
                ("s3_key", models.CharField(max_length=500)),
                (
                    "kind",
                    models.CharField(
                        choices=[
                            ("xlsx", "Excel (xlsx)"),
                            ("csv", "CSV"),
                            ("pdf", "PDF"),
                            ("image", "Image"),
                            ("body_text", "Body Text"),
                        ],
                        max_length=20,
                    ),
                ),
                ("text_extracted", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "verbose_name": "Intake File",
                "verbose_name_plural": "Intake Files",
                "ordering": ["created_at"],
            },
        ),
        migrations.CreateModel(
            name="IntakeExtraction",
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
                    "message",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="extractions",
                        to="intake.intakemessage",
                    ),
                ),
                ("model", models.CharField(max_length=100)),
                ("prompt_version", models.CharField(max_length=20)),
                ("result", models.JSONField(default=dict)),
                (
                    "confidence",
                    models.DecimalField(
                        blank=True, decimal_places=3, max_digits=4, null=True
                    ),
                ),
                ("line_count", models.SmallIntegerField(default=0)),
                (
                    "listing",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="extractions",
                        to="listings.listing",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "verbose_name": "Intake Extraction",
                "verbose_name_plural": "Intake Extractions",
                "ordering": ["-created_at"],
            },
        ),
    ]
