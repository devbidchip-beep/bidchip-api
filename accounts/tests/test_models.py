"""
Tests for accounts models.
"""

import pytest
from django.contrib.auth import get_user_model

from accounts.models import Company, CompanyMember

User = get_user_model()


@pytest.mark.django_db
class TestUserModel:
    def test_create_user(self):
        user = User.objects.create_user(
            email="test@example.com",
            password="SecureP@ss123",
            full_name="Test User",
        )
        assert user.pk is not None
        assert user.email == "test@example.com"
        assert user.full_name == "Test User"
        assert user.is_active is True
        assert user.is_staff is False
        assert user.mfa_required is False

    def test_create_superuser(self):
        admin = User.objects.create_superuser(
            email="admin@bidchip.com",
            password="AdminP@ss123",
            full_name="Admin User",
        )
        assert admin.is_staff is True
        assert admin.is_superuser is True
        assert admin.staff_role == User.StaffRole.ADMIN
        assert admin.mfa_required is True

    def test_email_normalised_to_lowercase(self):
        user = User.objects.create_user(
            email="MixedCase@Example.COM",
            password="pass",
            full_name="Case Test",
        )
        assert user.email == "MixedCase@example.com"

    def test_staff_role_forces_mfa_required(self):
        user = User.objects.create_user(
            email="staff@bidchip.com",
            password="pass",
            full_name="Staff Member",
            staff_role=User.StaffRole.WAREHOUSE,
        )
        assert user.mfa_required is True

    def test_str_representation(self):
        user = User(email="hello@example.com", full_name="Hello World")
        assert "hello@example.com" in str(user)
        assert "Hello World" in str(user)


@pytest.mark.django_db
class TestCompanyModel:
    def test_create_company(self):
        company = Company.objects.create(
            legal_name="ACME Electronics Inc.",
            display_name="ACME",
            country="US",
            is_buyer=True,
        )
        assert company.pk is not None
        assert company.status == Company.Status.LIMITED
        assert company.is_buyer is True
        assert company.is_supplier is False

    def test_str_representation(self):
        company = Company(legal_name="ACME Electronics Inc.", display_name="ACME")
        assert str(company) == "ACME"

    def test_str_falls_back_to_legal_name(self):
        company = Company(legal_name="ACME Electronics Inc.", display_name="")
        assert str(company) == "ACME Electronics Inc."


@pytest.mark.django_db
class TestCompanyMemberModel:
    def test_create_membership(self):
        user = User.objects.create_user(
            email="owner@example.com",
            password="pass",
            full_name="Owner",
        )
        company = Company.objects.create(
            legal_name="Test Corp",
            display_name="TestCo",
            country="US",
        )
        member = CompanyMember.objects.create(
            user=user,
            company=company,
            role=CompanyMember.Role.OWNER,
        )
        assert member.pk is not None
        assert member.status == CompanyMember.Status.ACTIVE

    def test_can_release_payout_sets_mfa_required(self):
        user = User.objects.create_user(
            email="finance@example.com",
            password="pass",
            full_name="Finance User",
        )
        company = Company.objects.create(
            legal_name="Test Corp",
            display_name="TestCo",
            country="US",
        )
        CompanyMember.objects.create(
            user=user,
            company=company,
            role=CompanyMember.Role.FINANCE,
            can_release_payout=True,
        )
        user.refresh_from_db()
        assert user.mfa_required is True

    def test_unique_user_company_constraint(self):
        from django.db import IntegrityError

        user = User.objects.create_user(
            email="dup@example.com",
            password="pass",
            full_name="Dup User",
        )
        company = Company.objects.create(
            legal_name="Dup Corp",
            display_name="DupCo",
            country="US",
        )
        CompanyMember.objects.create(user=user, company=company, role=CompanyMember.Role.BUYER)
        with pytest.raises(IntegrityError):
            CompanyMember.objects.create(
                user=user, company=company, role=CompanyMember.Role.SELLER
            )
