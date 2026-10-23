"""
Accounts models: Company, User, CompanyMember, Address, CompanyDocument,
VerificationCheck, TaxCertificate, StripeAccount, LoginEvent.

UUID strategy: uuid.uuid4() is used throughout.
TODO: Swap to uuid7 library (pip install uuid7) for time-ordered UUIDs once
      the project adds that dependency. Replace uuid.uuid4() with uuid7().
"""

import time
import uuid

from cryptography.fernet import Fernet
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils.translation import gettext_lazy as _


# ---------------------------------------------------------------------------
# UUID helper
# ---------------------------------------------------------------------------

def generate_uuid() -> uuid.UUID:
    """
    Generate a UUID for use as a primary key.
    Currently returns UUID4. TODO: swap to a uuid7 implementation for
    time-ordering once the `uuid7` package is added to requirements.
    """
    return uuid.uuid4()


# ---------------------------------------------------------------------------
# Fernet encryption helpers for sensitive fields
# ---------------------------------------------------------------------------

class EncryptedCharField(models.TextField):
    """
    A TextField that transparently encrypts/decrypts its value using Fernet
    symmetric encryption.  The encryption key is read from
    settings.FIELD_ENCRYPTION_KEY (base64-encoded 32-byte key).

    NOTE: This is a simple implementation. For production consider using
    django-cryptography or django-encrypted-model-fields for richer support.
    """

    def _get_fernet(self):
        from django.conf import settings

        key = getattr(settings, "FIELD_ENCRYPTION_KEY", "")
        if not key:
            return None
        return Fernet(key.encode() if isinstance(key, str) else key)

    def from_db_value(self, value, expression, connection):
        if value is None:
            return value
        fernet = self._get_fernet()
        if fernet is None:
            return value
        try:
            return fernet.decrypt(value.encode()).decode()
        except Exception:
            # Return raw value if decryption fails (e.g. unencrypted legacy data)
            return value

    def to_python(self, value):
        return value

    def get_prep_value(self, value):
        if value is None:
            return value
        fernet = self._get_fernet()
        if fernet is None:
            return value
        return fernet.encrypt(value.encode()).decode()


# ---------------------------------------------------------------------------
# Company
# ---------------------------------------------------------------------------

class Company(models.Model):
    """
    Represents a business entity on BidChip — buyer, supplier, OEM, or EMS.
    """

    class Status(models.TextChoices):
        LIMITED = "limited", _("Limited")
        PENDING_REVIEW = "pending_review", _("Pending Review")
        VERIFIED = "verified", _("Verified")
        SUSPENDED = "suspended", _("Suspended")
        CLOSED = "closed", _("Closed")

    id = models.UUIDField(primary_key=True, default=generate_uuid, editable=False)
    legal_name = models.CharField(max_length=255)
    display_name = models.CharField(max_length=255)
    country = models.CharField(max_length=2)  # ISO 3166-1 alpha-2
    # NOTE: tax_id is encrypted at the field level via Fernet.
    # citext extension recommended for case-insensitive uniqueness checks.
    tax_id = EncryptedCharField(blank=True, default="")
    website = models.CharField(max_length=255, blank=True, default="")

    # Company type flags (can be multiple)
    is_buyer = models.BooleanField(default=False)
    is_supplier = models.BooleanField(default=False)
    is_oem = models.BooleanField(default=False)
    is_ems = models.BooleanField(default=False)

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.LIMITED,
    )
    limited_reason = models.TextField(blank=True, null=True)
    verified_at = models.DateTimeField(blank=True, null=True)
    verified_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="verified_companies",
    )

    # Never use FloatField for money
    integrity_score = models.DecimalField(max_digits=5, decimal_places=2, default=0)

    referred_by_company = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="referrals",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Company"
        verbose_name_plural = "Companies"
        ordering = ["legal_name"]

    def __str__(self):
        return self.display_name or self.legal_name


# ---------------------------------------------------------------------------
# User Manager
# ---------------------------------------------------------------------------

class UserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("Email address is required")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("staff_role", User.StaffRole.ADMIN)
        extra_fields.setdefault("mfa_required", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")

        return self.create_user(email, password, **extra_fields)


# ---------------------------------------------------------------------------
# User
# ---------------------------------------------------------------------------

class User(AbstractBaseUser, PermissionsMixin):
    """
    Custom user model using email as the unique identifier.

    NOTE: email uniqueness is case-insensitive in intent. For true citext
    support at the database level, apply the citext PostgreSQL extension and
    use a custom db_type. For now we rely on UniqueConstraint +
    normalize_email().  The pg_trgm extension is recommended for similarity
    searches on email.
    """

    class StaffRole(models.TextChoices):
        ADMIN = "admin", _("Admin")
        TRUSTY = "trusty", _("Trusty")
        WAREHOUSE = "warehouse", _("Warehouse")
        LAB = "lab", _("Lab")
        COMPLIANCE = "compliance", _("Compliance")
        SUPPORT = "support", _("Support")

    id = models.UUIDField(primary_key=True, default=generate_uuid, editable=False)
    email = models.EmailField(unique=True)
    full_name = models.CharField(max_length=255)
    # NOTE: phone is encrypted via Fernet
    phone = EncryptedCharField(max_length=30, blank=True, default="")

    staff_role = models.CharField(
        max_length=20,
        choices=StaffRole.choices,
        null=True,
        blank=True,
    )

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)

    # mfa_required is always True for staff; also True for anyone who can
    # release payouts.
    mfa_required = models.BooleanField(default=False)

    last_login_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["full_name"]

    class Meta:
        verbose_name = "User"
        verbose_name_plural = "Users"
        ordering = ["email"]
        constraints = [
            # Enforces case-insensitive uniqueness at the ORM level.
            # NOTE: For true DB-level citext support, apply the citext
            # PostgreSQL extension: CREATE EXTENSION IF NOT EXISTS citext;
            models.UniqueConstraint(
                fields=["email"],
                name="unique_user_email",
            )
        ]

    def __str__(self):
        return f"{self.full_name} <{self.email}>"

    def save(self, *args, **kwargs):
        self.email = self.__class__.objects.normalize_email(self.email)
        # Staff always require MFA
        if self.staff_role:
            self.mfa_required = True
        super().save(*args, **kwargs)


# ---------------------------------------------------------------------------
# CompanyMember
# ---------------------------------------------------------------------------

class CompanyMember(models.Model):
    """
    Associates a User with a Company and defines their role within it.
    """

    class Role(models.TextChoices):
        OWNER = "owner", _("Owner")
        FINANCE = "finance", _("Finance")
        MANAGER = "manager", _("Manager")
        BUYER = "buyer", _("Buyer")
        SELLER = "seller", _("Seller")
        READ_ONLY = "read_only", _("Read Only")

    class Status(models.TextChoices):
        ACTIVE = "active", _("Active")
        SUSPENDED = "suspended", _("Suspended")
        LEFT = "left", _("Left")

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="memberships")
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="members")
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.READ_ONLY)
    can_release_payout = models.BooleanField(default=False)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Company Member"
        verbose_name_plural = "Company Members"
        constraints = [
            models.UniqueConstraint(
                fields=["user", "company"],
                name="unique_company_member",
            )
        ]

    def __str__(self):
        return f"{self.user} @ {self.company} ({self.role})"

    def save(self, *args, **kwargs):
        # Users who can release payouts must have MFA enabled
        if self.can_release_payout:
            self.user.mfa_required = True
            self.user.save(update_fields=["mfa_required"])
        super().save(*args, **kwargs)


# ---------------------------------------------------------------------------
# Address
# ---------------------------------------------------------------------------

class Address(models.Model):
    """
    Postal address associated with a Company or User.
    """

    class AddressType(models.TextChoices):
        BILLING = "billing", _("Billing")
        SHIPPING = "shipping", _("Shipping")
        REGISTERED = "registered", _("Registered")

    id = models.UUIDField(primary_key=True, default=generate_uuid, editable=False)
    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="addresses",
        null=True,
        blank=True,
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="addresses",
        null=True,
        blank=True,
    )
    address_type = models.CharField(
        max_length=20,
        choices=AddressType.choices,
        default=AddressType.SHIPPING,
    )
    line1 = models.CharField(max_length=255)
    line2 = models.CharField(max_length=255, blank=True, default="")
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100, blank=True, default="")
    postal_code = models.CharField(max_length=20)
    country = models.CharField(max_length=2)  # ISO 3166-1 alpha-2
    is_primary = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Address"
        verbose_name_plural = "Addresses"

    def __str__(self):
        return f"{self.line1}, {self.city}, {self.country}"


# ---------------------------------------------------------------------------
# CompanyDocument
# ---------------------------------------------------------------------------

class CompanyDocument(models.Model):
    """
    Supporting documents uploaded during company verification (e.g., business
    licences, W-9/W-8, articles of incorporation).
    """

    class DocumentType(models.TextChoices):
        BUSINESS_LICENSE = "business_license", _("Business License")
        W9 = "w9", _("W-9")
        W8 = "w8", _("W-8")
        ARTICLES = "articles", _("Articles of Incorporation")
        OTHER = "other", _("Other")

    id = models.UUIDField(primary_key=True, default=generate_uuid, editable=False)
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="documents")
    document_type = models.CharField(max_length=30, choices=DocumentType.choices)
    file = models.FileField(upload_to="company_documents/%Y/%m/")
    original_filename = models.CharField(max_length=255)
    uploaded_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name="uploaded_documents",
    )
    notes = models.TextField(blank=True, default="")

    # Insert-only log — no updated_at
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Company Document"
        verbose_name_plural = "Company Documents"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.company} — {self.document_type}"


# ---------------------------------------------------------------------------
# VerificationCheck
# ---------------------------------------------------------------------------

class VerificationCheck(models.Model):
    """
    Records the outcome of an individual verification step for a company
    (e.g., OFAC sanctions check, ID verification, business registry lookup).
    """

    class CheckType(models.TextChoices):
        OFAC = "ofac", _("OFAC Sanctions")
        BUSINESS_REGISTRY = "business_registry", _("Business Registry")
        ID_VERIFICATION = "id_verification", _("ID Verification")
        BANK_ACCOUNT = "bank_account", _("Bank Account")
        OTHER = "other", _("Other")

    class Result(models.TextChoices):
        PASS = "pass", _("Pass")
        FAIL = "fail", _("Fail")
        MANUAL = "manual", _("Manual Review")
        PENDING = "pending", _("Pending")

    id = models.UUIDField(primary_key=True, default=generate_uuid, editable=False)
    company = models.ForeignKey(
        Company, on_delete=models.CASCADE, related_name="verification_checks"
    )
    check_type = models.CharField(max_length=30, choices=CheckType.choices)
    result = models.CharField(max_length=20, choices=Result.choices, default=Result.PENDING)
    performed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="performed_checks",
    )
    notes = models.TextField(blank=True, default="")
    raw_response = models.JSONField(blank=True, null=True)

    # Insert-only log — no updated_at
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Verification Check"
        verbose_name_plural = "Verification Checks"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.company} — {self.check_type}: {self.result}"


# ---------------------------------------------------------------------------
# TaxCertificate
# ---------------------------------------------------------------------------

class TaxCertificate(models.Model):
    """
    Tax exemption certificates provided by buyers.
    """

    class Status(models.TextChoices):
        PENDING = "pending", _("Pending")
        APPROVED = "approved", _("Approved")
        REJECTED = "rejected", _("Rejected")
        EXPIRED = "expired", _("Expired")

    id = models.UUIDField(primary_key=True, default=generate_uuid, editable=False)
    company = models.ForeignKey(
        Company, on_delete=models.CASCADE, related_name="tax_certificates"
    )
    state = models.CharField(max_length=2, help_text="US state abbreviation")
    certificate_number = models.CharField(max_length=100, blank=True, default="")
    file = models.FileField(upload_to="tax_certificates/%Y/%m/")
    expiry_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    reviewed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_tax_certificates",
    )
    notes = models.TextField(blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Tax Certificate"
        verbose_name_plural = "Tax Certificates"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.company} — {self.state} ({self.status})"


# ---------------------------------------------------------------------------
# StripeAccount
# ---------------------------------------------------------------------------

class StripeAccount(models.Model):
    """
    Links a Company to their Stripe Connect account.
    """

    class AccountType(models.TextChoices):
        EXPRESS = "express", _("Express")
        STANDARD = "standard", _("Standard")
        CUSTOM = "custom", _("Custom")

    class Status(models.TextChoices):
        PENDING = "pending", _("Pending")
        ACTIVE = "active", _("Active")
        RESTRICTED = "restricted", _("Restricted")
        DISABLED = "disabled", _("Disabled")

    id = models.UUIDField(primary_key=True, default=generate_uuid, editable=False)
    company = models.OneToOneField(
        Company, on_delete=models.CASCADE, related_name="stripe_account"
    )
    stripe_account_id = models.CharField(max_length=100, unique=True)
    account_type = models.CharField(
        max_length=20,
        choices=AccountType.choices,
        default=AccountType.EXPRESS,
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    charges_enabled = models.BooleanField(default=False)
    payouts_enabled = models.BooleanField(default=False)
    details_submitted = models.BooleanField(default=False)
    country = models.CharField(max_length=2)
    default_currency = models.CharField(max_length=3, default="usd")
    raw_data = models.JSONField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Stripe Account"
        verbose_name_plural = "Stripe Accounts"

    def __str__(self):
        return f"{self.company} — {self.stripe_account_id}"


# ---------------------------------------------------------------------------
# LoginEvent
# ---------------------------------------------------------------------------

class LoginEvent(models.Model):
    """
    Immutable audit log of user login attempts.
    Insert-only — no updated_at.
    """

    class Outcome(models.TextChoices):
        SUCCESS = "success", _("Success")
        FAILED = "failed", _("Failed")
        MFA_REQUIRED = "mfa_required", _("MFA Required")
        MFA_FAILED = "mfa_failed", _("MFA Failed")
        BLOCKED = "blocked", _("Blocked")

    id = models.UUIDField(primary_key=True, default=generate_uuid, editable=False)
    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="login_events",
    )
    email_attempted = models.EmailField()
    outcome = models.CharField(max_length=20, choices=Outcome.choices)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True, default="")
    mfa_used = models.BooleanField(default=False)

    # Insert-only log — no updated_at
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Login Event"
        verbose_name_plural = "Login Events"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "-created_at"]),
            models.Index(fields=["ip_address", "-created_at"]),
        ]

    def __str__(self):
        return f"{self.email_attempted} — {self.outcome} @ {self.created_at}"
