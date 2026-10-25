"""
Initial migration for the corporate app.
"""

import uuid

import django.db.models.deletion
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
        # ------------------------------------------------------------------
        # Invitation
        # ------------------------------------------------------------------
        migrations.CreateModel(
            name="Invitation",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("email", models.EmailField(max_length=254)),
                (
                    "role",
                    models.CharField(
                        choices=[
                            ("owner", "Owner"),
                            ("finance", "Finance"),
                            ("manager", "Manager"),
                            ("buyer", "Buyer"),
                            ("seller", "Seller"),
                            ("read_only", "Read Only"),
                        ],
                        default="read_only",
                        max_length=20,
                    ),
                ),
                ("token_hash", models.CharField(max_length=64)),
                ("expires_at", models.DateTimeField()),
                ("accepted_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "company",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="invitations",
                        to="accounts.company",
                    ),
                ),
                (
                    "invited_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="sent_invitations",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Invitation",
                "verbose_name_plural": "Invitations",
            },
        ),
        migrations.AddIndex(
            model_name="invitation",
            index=models.Index(fields=["company", "email"], name="corporate_invitation_company_email_idx"),
        ),

        # ------------------------------------------------------------------
        # Budget
        # ------------------------------------------------------------------
        migrations.CreateModel(
            name="Budget",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("period_start", models.DateField()),
                (
                    "period",
                    models.CharField(
                        choices=[("month", "Month"), ("quarter", "Quarter")],
                        default="month",
                        max_length=10,
                    ),
                ),
                ("amount", models.DecimalField(decimal_places=2, max_digits=14)),
                ("currency", models.CharField(default="USD", max_length=3)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "member",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="budgets",
                        to="accounts.companymember",
                    ),
                ),
            ],
            options={
                "verbose_name": "Budget",
                "verbose_name_plural": "Budgets",
            },
        ),
        migrations.AlterUniqueTogether(
            name="budget",
            unique_together={("member", "period_start")},
        ),

        # ------------------------------------------------------------------
        # OrderLimit
        # ------------------------------------------------------------------
        migrations.CreateModel(
            name="OrderLimit",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("max_order_amount", models.DecimalField(decimal_places=2, max_digits=14)),
                ("currency", models.CharField(default="USD", max_length=3)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "member",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="order_limit",
                        to="accounts.companymember",
                    ),
                ),
            ],
            options={
                "verbose_name": "Order Limit",
                "verbose_name_plural": "Order Limits",
            },
        ),

        # ------------------------------------------------------------------
        # ApprovalRequest
        # ------------------------------------------------------------------
        migrations.CreateModel(
            name="ApprovalRequest",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                (
                    "subject_type",
                    models.CharField(
                        choices=[("listing_publish", "Listing Publish"), ("checkout", "Checkout")],
                        max_length=20,
                    ),
                ),
                ("amount", models.DecimalField(blank=True, decimal_places=2, max_digits=14, null=True)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Pending"),
                            ("approved", "Approved"),
                            ("rejected", "Rejected"),
                        ],
                        default="pending",
                        max_length=10,
                    ),
                ),
                ("decided_at", models.DateTimeField(blank=True, null=True)),
                ("note", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "company",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="approval_requests",
                        to="accounts.company",
                    ),
                ),
                (
                    "requested_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="approval_requests_made",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "approver",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="approval_requests_decided",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "listing",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="approval_requests",
                        to="listings.listing",
                    ),
                ),
                (
                    "order",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="approval_requests",
                        to="orders.order",
                    ),
                ),
            ],
            options={
                "verbose_name": "Approval Request",
                "verbose_name_plural": "Approval Requests",
                "ordering": ["-created_at"],
            },
        ),

        # ------------------------------------------------------------------
        # ShipToAssignment
        # ------------------------------------------------------------------
        migrations.CreateModel(
            name="ShipToAssignment",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "member",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="ship_to_assignments",
                        to="accounts.companymember",
                    ),
                ),
                (
                    "address",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="ship_to_assignments",
                        to="accounts.address",
                    ),
                ),
            ],
            options={
                "verbose_name": "Ship-To Assignment",
                "verbose_name_plural": "Ship-To Assignments",
            },
        ),
        migrations.AlterUniqueTogether(
            name="shiptoassignment",
            unique_together={("member", "address")},
        ),
    ]
