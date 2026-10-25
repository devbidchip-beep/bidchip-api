"""
Trust app initial migration.

Note: SellerChainEvent is insert-only — rows must never be updated or deleted.
The admin enforces this via has_add_permission=False, has_change_permission=False,
has_delete_permission=False. At the DB level, row-level security or triggers
should be added in production to enforce immutability.
"""

import uuid

import django.core.validators
import django.db.models.deletion
import django.db.models.expressions
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("accounts", "0001_initial"),
        ("listings", "0001_initial"),
        ("orders", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # -----------------------------------------------------------------
        # RiskAssessment
        # -----------------------------------------------------------------
        migrations.CreateModel(
            name="RiskAssessment",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("score", models.DecimalField(decimal_places=2, max_digits=5)),
                ("tier", models.CharField(
                    choices=[("green", "Green"), ("yellow", "Yellow"), ("red", "Red")],
                    max_length=10,
                )),
                ("factors", models.JSONField(default=dict)),
                ("override_tier", models.CharField(
                    blank=True,
                    choices=[("green", "Green"), ("yellow", "Yellow"), ("red", "Red")],
                    max_length=10,
                    null=True,
                )),
                ("override_reason", models.TextField(blank=True)),
                ("assessed_at", models.DateTimeField(auto_now_add=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("supplier_order", models.OneToOneField(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="risk_assessment",
                    to="orders.supplierorder",
                )),
                ("overridden_by", models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="risk_overrides",
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                "verbose_name": "Risk Assessment",
                "verbose_name_plural": "Risk Assessments",
                "ordering": ["-assessed_at"],
            },
        ),
        # -----------------------------------------------------------------
        # Dispute
        # -----------------------------------------------------------------
        migrations.CreateModel(
            name="Dispute",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("reason", models.CharField(
                    choices=[
                        ("not_as_described", "Not as Described"),
                        ("quantity", "Quantity"),
                        ("counterfeit_suspected", "Counterfeit Suspected"),
                        ("damaged", "Damaged"),
                        ("not_received", "Not Received"),
                        ("other", "Other"),
                    ],
                    max_length=30,
                )),
                ("description", models.TextField()),
                ("status", models.CharField(
                    choices=[
                        ("open", "Open"),
                        ("awaiting_return", "Awaiting Return"),
                        ("under_review", "Under Review"),
                        ("resolved_buyer", "Resolved \u2014 Buyer"),
                        ("resolved_seller", "Resolved \u2014 Seller"),
                        ("split", "Split"),
                        ("withdrawn", "Withdrawn"),
                    ],
                    default="open",
                    max_length=20,
                )),
                ("resolution_note", models.TextField(blank=True)),
                ("opened_at", models.DateTimeField(auto_now_add=True)),
                ("resolved_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("supplier_order", models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="disputes",
                    to="orders.supplierorder",
                )),
                ("opened_by", models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="opened_disputes",
                    to=settings.AUTH_USER_MODEL,
                )),
                ("resolved_by", models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="resolved_disputes",
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                "verbose_name": "Dispute",
                "verbose_name_plural": "Disputes",
                "ordering": ["-opened_at"],
            },
        ),
        # -----------------------------------------------------------------
        # DisputeFile
        # -----------------------------------------------------------------
        migrations.CreateModel(
            name="DisputeFile",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("file", models.CharField(max_length=500)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("dispute", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="files",
                    to="trust.dispute",
                )),
                ("uploaded_by", models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="dispute_files",
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                "verbose_name": "Dispute File",
                "verbose_name_plural": "Dispute Files",
                "ordering": ["-created_at"],
            },
        ),
        # -----------------------------------------------------------------
        # Rating
        # -----------------------------------------------------------------
        migrations.CreateModel(
            name="Rating",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("legacy_ref", models.CharField(blank=True, max_length=100, null=True)),
                ("direction", models.CharField(
                    choices=[
                        ("buyer_to_supplier", "Buyer to Supplier"),
                        ("supplier_to_buyer", "Supplier to Buyer"),
                    ],
                    max_length=20,
                )),
                ("quality", models.SmallIntegerField(validators=[
                    django.core.validators.MinValueValidator(1),
                    django.core.validators.MaxValueValidator(5),
                ])),
                ("communication", models.SmallIntegerField(validators=[
                    django.core.validators.MinValueValidator(1),
                    django.core.validators.MaxValueValidator(5),
                ])),
                ("shipping", models.SmallIntegerField(validators=[
                    django.core.validators.MinValueValidator(1),
                    django.core.validators.MaxValueValidator(5),
                ])),
                ("documentation", models.SmallIntegerField(validators=[
                    django.core.validators.MinValueValidator(1),
                    django.core.validators.MaxValueValidator(5),
                ])),
                ("comment", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("supplier_order", models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="ratings",
                    to="orders.supplierorder",
                )),
                ("rater_company", models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="given_ratings",
                    to="accounts.company",
                )),
                ("ratee_company", models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="received_ratings",
                    to="accounts.company",
                )),
            ],
            options={
                "verbose_name": "Rating",
                "verbose_name_plural": "Ratings",
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddConstraint(
            model_name="rating",
            constraint=models.UniqueConstraint(
                condition=models.Q(supplier_order__isnull=False),
                fields=["supplier_order", "direction"],
                name="unique_rating_per_order_direction",
            ),
        ),
        migrations.AddIndex(
            model_name="rating",
            index=models.Index(fields=["ratee_company", "direction"], name="trust_ratin_ratee_c_idx"),
        ),
        # -----------------------------------------------------------------
        # MessageThread
        # -----------------------------------------------------------------
        migrations.CreateModel(
            name="MessageThread",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("status", models.CharField(
                    choices=[("open", "Open"), ("closed", "Closed")],
                    default="open",
                    max_length=10,
                )),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("listing", models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="message_threads",
                    to="listings.listing",
                )),
                ("supplier_order", models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="message_threads",
                    to="orders.supplierorder",
                )),
                ("buyer_company", models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="buyer_threads",
                    to="accounts.company",
                )),
                ("supplier_company", models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="supplier_threads",
                    to="accounts.company",
                )),
            ],
            options={
                "verbose_name": "Message Thread",
                "verbose_name_plural": "Message Threads",
                "ordering": ["-updated_at"],
            },
        ),
        # -----------------------------------------------------------------
        # Message
        # -----------------------------------------------------------------
        migrations.CreateModel(
            name="Message",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("body", models.TextField()),
                ("moderation_status", models.CharField(
                    choices=[
                        ("pending", "Pending"),
                        ("approved", "Approved"),
                        ("blocked", "Blocked"),
                    ],
                    default="pending",
                    max_length=10,
                )),
                ("moderation_flags", models.JSONField(default=dict)),
                ("sent_at", models.DateTimeField(auto_now_add=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("thread", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="messages",
                    to="trust.messagethread",
                )),
                ("sender", models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="sent_messages",
                    to=settings.AUTH_USER_MODEL,
                )),
                ("moderated_by", models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="moderated_messages",
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                "verbose_name": "Message",
                "verbose_name_plural": "Messages",
                "ordering": ["sent_at"],
            },
        ),
        # -----------------------------------------------------------------
        # SellerChainEvent — INSERT-ONLY, tamper-evident hash chain.
        # Never issue UPDATE or DELETE on this table.
        # In production, enforce immutability with DB-level row security or
        # a trigger: CREATE RULE no_update_chain AS ON UPDATE TO trust_sellerChainevent DO INSTEAD NOTHING;
        # -----------------------------------------------------------------
        migrations.CreateModel(
            name="SellerChainEvent",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("seq", models.BigIntegerField()),
                ("event_type", models.CharField(
                    choices=[
                        ("bid_committed", "Bid Committed"),
                        ("award", "Award"),
                        ("shipped", "Shipped"),
                        ("inspected", "Inspected"),
                        ("delivered", "Delivered"),
                        ("payout_release_requested", "Payout Release Requested"),
                        ("payout_released", "Payout Released"),
                        ("bank_changed", "Bank Changed"),
                        ("login_strong", "Login Strong"),
                        ("chain_frozen", "Chain Frozen"),
                    ],
                    max_length=30,
                )),
                ("ref_type", models.CharField(blank=True, max_length=50)),
                ("ref_id", models.CharField(blank=True, max_length=36)),
                ("payload_hash", models.CharField(max_length=64)),
                ("prev_hash", models.CharField(max_length=64)),
                ("hash", models.CharField(max_length=64)),
                ("kms_sig", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("supplier_company", models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="chain_events",
                    to="accounts.company",
                )),
            ],
            options={
                "verbose_name": "Seller Chain Event",
                "verbose_name_plural": "Seller Chain Events",
                "ordering": ["supplier_company", "seq"],
                "unique_together": {("supplier_company", "seq")},
            },
        ),
        migrations.AddIndex(
            model_name="sellerChainevent",
            index=models.Index(fields=["supplier_company", "seq"], name="trust_selle_supplie_idx"),
        ),
    ]
