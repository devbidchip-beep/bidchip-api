# Generated migration for listings app.
# Run: python manage.py migrate listings
#
# NOTE: The `intake` FK on Listing references 'intake.IntakeMessage' which is
# not yet implemented. That field will be added in a later migration once the
# intake app is scaffolded (Phase 2). For now the column is omitted here.

import decimal
import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("accounts", "0001_initial"),
        ("catalog", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Listing",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("number", models.CharField(blank=True, max_length=20, unique=True)),
                (
                    "kind",
                    models.CharField(
                        choices=[
                            ("reverse", "Reverse Auction"),
                            ("bom", "BOM"),
                            ("rfq", "RFQ"),
                            ("forward", "Forward Auction"),
                        ],
                        max_length=20,
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("draft", "Draft"),
                            ("pending_approval", "Pending Approval"),
                            ("published", "Published"),
                            ("closed", "Closed"),
                            ("awarded", "Awarded"),
                            ("cancelled", "Cancelled"),
                            ("expired", "Expired"),
                        ],
                        default="draft",
                        max_length=20,
                    ),
                ),
                (
                    "buyer_company",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="listings",
                        to="accounts.company",
                    ),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="created_listings",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "source",
                    models.CharField(
                        choices=[
                            ("manual", "Manual"),
                            ("ai_intake", "AI Intake"),
                            ("nimble", "Nimble"),
                            ("api", "API"),
                        ],
                        default="manual",
                        max_length=20,
                    ),
                ),
                # NOTE: intake FK omitted — added in 0002 once the intake app exists
                ("title", models.CharField(max_length=200)),
                ("starts_at", models.DateTimeField(blank=True, null=True)),
                ("duration_minutes", models.PositiveIntegerField(default=4320)),
                ("ends_at", models.DateTimeField(blank=True, null=True)),
                ("invite_only", models.BooleanField(default=False)),
                ("anonymous", models.BooleanField(default=True)),
                (
                    "ship_to",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="listings",
                        to="accounts.address",
                    ),
                ),
                ("currency", models.CharField(default="USD", max_length=3)),
                ("published_at", models.DateTimeField(blank=True, null=True)),
                ("closed_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Listing",
                "verbose_name_plural": "Listings",
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="listing",
            index=models.Index(fields=["status", "ends_at"], name="listings_lis_status_ends_idx"),
        ),
        migrations.AddIndex(
            model_name="listing",
            index=models.Index(fields=["buyer_company", "status"], name="listings_lis_buyer_status_idx"),
        ),
        migrations.CreateModel(
            name="ListingLine",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                (
                    "listing",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="lines",
                        to="listings.listing",
                    ),
                ),
                ("line_no", models.SmallIntegerField()),
                (
                    "part",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="listing_lines",
                        to="catalog.part",
                    ),
                ),
                ("mpn_raw", models.CharField(max_length=120)),
                ("manufacturer_raw", models.CharField(blank=True, max_length=255)),
                (
                    "manufacturer",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="listing_lines",
                        to="catalog.manufacturer",
                    ),
                ),
                ("quantity", models.PositiveIntegerField()),
                ("target_unit_price", models.DecimalField(blank=True, decimal_places=4, max_digits=14, null=True)),
                ("date_code_year_min", models.SmallIntegerField(blank=True, null=True)),
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
                ("allow_exceptions", models.BooleanField(default=True)),
                ("allow_split", models.BooleanField(default=True)),
                ("require_as6081", models.BooleanField(default=False)),
                ("lab_method", models.CharField(blank=True, max_length=100)),
                ("docs_required", models.BooleanField(default=False)),
                ("ncnr", models.BooleanField(default=False)),
                (
                    "compliance_status",
                    models.CharField(
                        choices=[
                            ("clear", "Clear"),
                            ("flagged", "Flagged"),
                            ("officer_review", "Officer Review"),
                            ("approved", "Approved"),
                            ("rejected", "Rejected"),
                        ],
                        default="clear",
                        max_length=20,
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("open", "Open"),
                            ("awarded", "Awarded"),
                            ("partially_awarded", "Partially Awarded"),
                            ("no_award", "No Award"),
                        ],
                        default="open",
                        max_length=20,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Listing Line",
                "verbose_name_plural": "Listing Lines",
                "ordering": ["listing", "line_no"],
            },
        ),
        migrations.AlterUniqueTogether(
            name="listingline",
            unique_together={("listing", "line_no")},
        ),
        migrations.CreateModel(
            name="ListingInvite",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                (
                    "listing",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="invites",
                        to="listings.listing",
                    ),
                ),
                (
                    "supplier_company",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="listing_invites",
                        to="accounts.company",
                    ),
                ),
                ("email", models.EmailField(blank=True, null=True)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("sent", "Sent"),
                            ("joined", "Joined"),
                            ("bid", "Bid"),
                            ("declined", "Declined"),
                        ],
                        default="sent",
                        max_length=20,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Listing Invite",
                "verbose_name_plural": "Listing Invites",
            },
        ),
        migrations.AlterUniqueTogether(
            name="listinginvite",
            unique_together={("listing", "supplier_company")},
        ),
        migrations.CreateModel(
            name="ComplianceScreening",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                (
                    "line",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="compliance_screening",
                        to="listings.listingline",
                    ),
                ),
                ("ai_result", models.JSONField(default=dict)),
                ("ai_flagged", models.BooleanField(default=False)),
                (
                    "officer",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="compliance_decisions",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "decision",
                    models.CharField(
                        blank=True,
                        choices=[
                            ("clear", "Clear"),
                            ("approved", "Approved"),
                            ("rejected", "Rejected"),
                        ],
                        max_length=20,
                        null=True,
                    ),
                ),
                ("decision_note", models.TextField(blank=True)),
                ("authority_reference", models.CharField(blank=True, max_length=200)),
                (
                    "fee_amount",
                    models.DecimalField(
                        decimal_places=2,
                        default=decimal.Decimal("30.00"),
                        max_digits=14,
                    ),
                ),
                ("decided_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Compliance Screening",
                "verbose_name_plural": "Compliance Screenings",
            },
        ),
    ]
