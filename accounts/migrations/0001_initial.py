# Generated migration for accounts app.
# Run: python manage.py migrate accounts

import accounts.models
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Company",
            fields=[
                ("id", models.UUIDField(default=accounts.models.generate_uuid, editable=False, primary_key=True, serialize=False)),
                ("legal_name", models.CharField(max_length=255)),
                ("display_name", models.CharField(max_length=255)),
                ("country", models.CharField(max_length=2)),
                ("tax_id", accounts.models.EncryptedCharField(blank=True, default="")),
                ("website", models.CharField(blank=True, default="", max_length=255)),
                ("is_buyer", models.BooleanField(default=False)),
                ("is_supplier", models.BooleanField(default=False)),
                ("is_oem", models.BooleanField(default=False)),
                ("is_ems", models.BooleanField(default=False)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("limited", "Limited"),
                            ("pending_review", "Pending Review"),
                            ("verified", "Verified"),
                            ("suspended", "Suspended"),
                            ("closed", "Closed"),
                        ],
                        default="limited",
                        max_length=20,
                    ),
                ),
                ("limited_reason", models.TextField(blank=True, null=True)),
                ("verified_at", models.DateTimeField(blank=True, null=True)),
                ("integrity_score", models.DecimalField(decimal_places=2, default=0, max_digits=5)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Company",
                "verbose_name_plural": "Companies",
                "ordering": ["legal_name"],
            },
        ),
        migrations.CreateModel(
            name="User",
            fields=[
                ("id", models.UUIDField(default=accounts.models.generate_uuid, editable=False, primary_key=True, serialize=False)),
                ("password", models.CharField(max_length=128, verbose_name="password")),
                ("last_login", models.DateTimeField(blank=True, null=True, verbose_name="last login")),
                ("is_superuser", models.BooleanField(default=False, verbose_name="superuser status")),
                ("email", models.EmailField(max_length=254, unique=True)),
                ("full_name", models.CharField(max_length=255)),
                ("phone", accounts.models.EncryptedCharField(blank=True, default="", max_length=30)),
                (
                    "staff_role",
                    models.CharField(
                        blank=True,
                        choices=[
                            ("admin", "Admin"),
                            ("trusty", "Trusty"),
                            ("warehouse", "Warehouse"),
                            ("lab", "Lab"),
                            ("compliance", "Compliance"),
                            ("support", "Support"),
                        ],
                        max_length=20,
                        null=True,
                    ),
                ),
                ("is_active", models.BooleanField(default=True)),
                ("is_staff", models.BooleanField(default=False)),
                ("mfa_required", models.BooleanField(default=False)),
                ("last_login_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "User",
                "verbose_name_plural": "Users",
                "ordering": ["email"],
            },
            managers=[
                ("objects", accounts.models.UserManager()),
            ],
        ),
        # Add verified_by FK to Company after User exists
        migrations.AddField(
            model_name="company",
            name="verified_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="verified_companies",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="company",
            name="referred_by_company",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="referrals",
                to="accounts.company",
            ),
        ),
        migrations.AddConstraint(
            model_name="user",
            constraint=models.UniqueConstraint(fields=["email"], name="unique_user_email"),
        ),
        migrations.AddField(
            model_name="user",
            name="groups",
            field=models.ManyToManyField(
                blank=True,
                related_name="user_set",
                related_query_name="user",
                to="auth.group",
                verbose_name="groups",
            ),
        ),
        migrations.AddField(
            model_name="user",
            name="user_permissions",
            field=models.ManyToManyField(
                blank=True,
                related_name="user_set",
                related_query_name="user",
                to="auth.permission",
                verbose_name="user permissions",
            ),
        ),
        migrations.CreateModel(
            name="Address",
            fields=[
                ("id", models.UUIDField(default=accounts.models.generate_uuid, editable=False, primary_key=True, serialize=False)),
                (
                    "company",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="addresses",
                        to="accounts.company",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="addresses",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "address_type",
                    models.CharField(
                        choices=[
                            ("billing", "Billing"),
                            ("shipping", "Shipping"),
                            ("registered", "Registered"),
                        ],
                        default="shipping",
                        max_length=20,
                    ),
                ),
                ("line1", models.CharField(max_length=255)),
                ("line2", models.CharField(blank=True, default="", max_length=255)),
                ("city", models.CharField(max_length=100)),
                ("state", models.CharField(blank=True, default="", max_length=100)),
                ("postal_code", models.CharField(max_length=20)),
                ("country", models.CharField(max_length=2)),
                ("is_primary", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Address",
                "verbose_name_plural": "Addresses",
            },
        ),
        migrations.CreateModel(
            name="CompanyMember",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="memberships",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "company",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="members",
                        to="accounts.company",
                    ),
                ),
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
                ("can_release_payout", models.BooleanField(default=False)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("active", "Active"),
                            ("suspended", "Suspended"),
                            ("left", "Left"),
                        ],
                        default="active",
                        max_length=20,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Company Member",
                "verbose_name_plural": "Company Members",
            },
        ),
        migrations.AddConstraint(
            model_name="companymember",
            constraint=models.UniqueConstraint(fields=["user", "company"], name="unique_company_member"),
        ),
        migrations.CreateModel(
            name="CompanyDocument",
            fields=[
                ("id", models.UUIDField(default=accounts.models.generate_uuid, editable=False, primary_key=True, serialize=False)),
                (
                    "company",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="documents",
                        to="accounts.company",
                    ),
                ),
                (
                    "document_type",
                    models.CharField(
                        choices=[
                            ("business_license", "Business License"),
                            ("w9", "W-9"),
                            ("w8", "W-8"),
                            ("articles", "Articles of Incorporation"),
                            ("other", "Other"),
                        ],
                        max_length=30,
                    ),
                ),
                ("file", models.FileField(upload_to="company_documents/%Y/%m/")),
                ("original_filename", models.CharField(max_length=255)),
                (
                    "uploaded_by",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="uploaded_documents",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                ("notes", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "verbose_name": "Company Document",
                "verbose_name_plural": "Company Documents",
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="VerificationCheck",
            fields=[
                ("id", models.UUIDField(default=accounts.models.generate_uuid, editable=False, primary_key=True, serialize=False)),
                (
                    "company",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="verification_checks",
                        to="accounts.company",
                    ),
                ),
                (
                    "check_type",
                    models.CharField(
                        choices=[
                            ("ofac", "OFAC Sanctions"),
                            ("business_registry", "Business Registry"),
                            ("id_verification", "ID Verification"),
                            ("bank_account", "Bank Account"),
                            ("other", "Other"),
                        ],
                        max_length=30,
                    ),
                ),
                (
                    "result",
                    models.CharField(
                        choices=[
                            ("pass", "Pass"),
                            ("fail", "Fail"),
                            ("manual", "Manual Review"),
                            ("pending", "Pending"),
                        ],
                        default="pending",
                        max_length=20,
                    ),
                ),
                (
                    "performed_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="performed_checks",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                ("notes", models.TextField(blank=True, default="")),
                ("raw_response", models.JSONField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "verbose_name": "Verification Check",
                "verbose_name_plural": "Verification Checks",
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="TaxCertificate",
            fields=[
                ("id", models.UUIDField(default=accounts.models.generate_uuid, editable=False, primary_key=True, serialize=False)),
                (
                    "company",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="tax_certificates",
                        to="accounts.company",
                    ),
                ),
                ("state", models.CharField(help_text="US state abbreviation", max_length=2)),
                ("certificate_number", models.CharField(blank=True, default="", max_length=100)),
                ("file", models.FileField(upload_to="tax_certificates/%Y/%m/")),
                ("expiry_date", models.DateField(blank=True, null=True)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Pending"),
                            ("approved", "Approved"),
                            ("rejected", "Rejected"),
                            ("expired", "Expired"),
                        ],
                        default="pending",
                        max_length=20,
                    ),
                ),
                (
                    "reviewed_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="reviewed_tax_certificates",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                ("notes", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Tax Certificate",
                "verbose_name_plural": "Tax Certificates",
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="StripeAccount",
            fields=[
                ("id", models.UUIDField(default=accounts.models.generate_uuid, editable=False, primary_key=True, serialize=False)),
                (
                    "company",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="stripe_account",
                        to="accounts.company",
                    ),
                ),
                ("stripe_account_id", models.CharField(max_length=100, unique=True)),
                (
                    "account_type",
                    models.CharField(
                        choices=[
                            ("express", "Express"),
                            ("standard", "Standard"),
                            ("custom", "Custom"),
                        ],
                        default="express",
                        max_length=20,
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Pending"),
                            ("active", "Active"),
                            ("restricted", "Restricted"),
                            ("disabled", "Disabled"),
                        ],
                        default="pending",
                        max_length=20,
                    ),
                ),
                ("charges_enabled", models.BooleanField(default=False)),
                ("payouts_enabled", models.BooleanField(default=False)),
                ("details_submitted", models.BooleanField(default=False)),
                ("country", models.CharField(max_length=2)),
                ("default_currency", models.CharField(default="usd", max_length=3)),
                ("raw_data", models.JSONField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Stripe Account",
                "verbose_name_plural": "Stripe Accounts",
            },
        ),
        migrations.CreateModel(
            name="LoginEvent",
            fields=[
                ("id", models.UUIDField(default=accounts.models.generate_uuid, editable=False, primary_key=True, serialize=False)),
                (
                    "user",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="login_events",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                ("email_attempted", models.EmailField()),
                (
                    "outcome",
                    models.CharField(
                        choices=[
                            ("success", "Success"),
                            ("failed", "Failed"),
                            ("mfa_required", "MFA Required"),
                            ("mfa_failed", "MFA Failed"),
                            ("blocked", "Blocked"),
                        ],
                        max_length=20,
                    ),
                ),
                ("ip_address", models.GenericIPAddressField(blank=True, null=True)),
                ("user_agent", models.TextField(blank=True, default="")),
                ("mfa_used", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "verbose_name": "Login Event",
                "verbose_name_plural": "Login Events",
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="loginevent",
            index=models.Index(fields=["user", "-created_at"], name="accounts_log_user_idx"),
        ),
        migrations.AddIndex(
            model_name="loginevent",
            index=models.Index(fields=["ip_address", "-created_at"], name="accounts_log_ip_idx"),
        ),
    ]
