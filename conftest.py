"""
Root conftest.py — shared pytest fixtures for the BidChip test suite.
"""

import pytest
from django.contrib.auth import get_user_model

from accounts.models import Company, CompanyMember

User = get_user_model()


@pytest.fixture
def user(db):
    return User.objects.create_user(
        email="testuser@bidchip.com",
        password="TestP@ss123",
        full_name="Test User",
    )


@pytest.fixture
def company(db):
    return Company.objects.create(
        legal_name="Test Company LLC",
        display_name="Test Company",
        country="US",
        is_buyer=True,
        is_supplier=True,
        status=Company.Status.VERIFIED,
    )


@pytest.fixture
def company_member(db, user, company):
    return CompanyMember.objects.create(
        user=user,
        company=company,
        role=CompanyMember.Role.OWNER,
        status=CompanyMember.Status.ACTIVE,
    )


@pytest.fixture
def listing(db, company, user):
    from listings.models import Listing

    return Listing.objects.create(
        kind=Listing.Kind.REVERSE,
        status=Listing.Status.DRAFT,
        buyer_company=company,
        created_by=user,
        title="Test Listing",
    )
