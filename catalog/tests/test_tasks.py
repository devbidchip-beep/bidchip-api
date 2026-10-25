"""
Tests for catalog Celery tasks — bid matching and inventory import.
"""

from unittest.mock import MagicMock, patch

import pytest
from django.test import TestCase
from django.utils import timezone

from accounts.models import Company, CompanyMember, User
from catalog.models import InventoryItem, Manufacturer, Part
from listings.models import Listing, ListingLine


def make_company(name, is_buyer=False, is_supplier=False):
    return Company.objects.create(
        legal_name=name,
        display_name=name,
        country="US",
        is_buyer=is_buyer,
        is_supplier=is_supplier,
    )


def make_user(email, company=None, role=CompanyMember.Role.SELLER):
    user = User.objects.create_user(
        email=email, password="pass", full_name="Test User"
    )
    if company:
        CompanyMember.objects.create(
            user=user, company=company, role=role, status="active"
        )
    return user


def make_manufacturer(name="TI"):
    normalized = name.upper().replace(" ", "")
    return Manufacturer.objects.create(name=name, name_normalized=normalized)


def make_part(mpn="LM317T", manufacturer=None):
    if not manufacturer:
        manufacturer = make_manufacturer()
    from catalog.utils import normalize_mpn
    return Part.objects.create(
        mpn=mpn, mpn_normalized=normalize_mpn(mpn), manufacturer=manufacturer
    )


def make_listing(buyer_company, created_by, status=Listing.Status.PUBLISHED):
    listing = Listing.objects.create(
        kind=Listing.Kind.REVERSE,
        status=status,
        buyer_company=buyer_company,
        created_by=created_by,
        source=Listing.Source.MANUAL,
        title="Test Listing",
        duration_minutes=4320,
        published_at=timezone.now() if status == Listing.Status.PUBLISHED else None,
    )
    return listing


class TestMatchNewListingsToInventory(TestCase):
    """Tests for match_new_listings_to_inventory Celery task."""

    def test_sends_notification_to_matching_inventory_owners(self):
        """Seller with matching inventory receives notification for new listing."""
        from catalog.tasks import match_new_listings_to_inventory

        buyer_co = make_company("BuyerCo", is_buyer=True)
        supplier_co = make_company("SupplierCo", is_supplier=True)

        buyer_user = make_user("buyer@test.com", buyer_co, role=CompanyMember.Role.BUYER)
        seller_user = make_user("seller@test.com", supplier_co, role=CompanyMember.Role.SELLER)

        part = make_part("LM317T")

        listing = make_listing(buyer_co, buyer_user)
        ListingLine.objects.create(
            listing=listing,
            line_no=1,
            part=part,
            mpn_raw="LM317T",
            quantity=100,
        )

        InventoryItem.objects.create(
            company=supplier_co,
            part=part,
            mpn_raw="LM317T",
            manufacturer_raw="TI",
            quantity=500,
            source=InventoryItem.Source.CSV,
            is_active=True,
        )

        # Patch cache (returns None = not yet notified) and notify
        with patch("django.core.cache.cache.get", return_value=None), \
             patch("django.core.cache.cache.set"), \
             patch("notify.service.notify") as mock_notify:
            match_new_listings_to_inventory()

        mock_notify.assert_called_once_with(
            seller_user,
            "new_listing_match",
            {
                "listing_number": listing.number,
                "listing_id": str(listing.pk),
                "part_mpn": "LM317T",
            },
        )

    def test_no_duplicate_notifications_for_same_listing_company(self):
        """Same (listing, company) pair is not notified twice — Redis dedup."""
        from catalog.tasks import match_new_listings_to_inventory

        buyer_co = make_company("BuyerCo2", is_buyer=True)
        supplier_co = make_company("SupplierCo2", is_supplier=True)

        buyer_user = make_user("buyer2@test.com", buyer_co, role=CompanyMember.Role.BUYER)
        make_user("seller2@test.com", supplier_co, role=CompanyMember.Role.SELLER)

        part = make_part("NE555P", make_manufacturer("Philips"))

        listing = make_listing(buyer_co, buyer_user)
        ListingLine.objects.create(
            listing=listing, line_no=1, part=part, mpn_raw="NE555P", quantity=50
        )
        InventoryItem.objects.create(
            company=supplier_co,
            part=part,
            mpn_raw="NE555P",
            manufacturer_raw="Philips",
            quantity=200,
            source=InventoryItem.Source.CSV,
            is_active=True,
        )

        # Cache returns "1" = already notified for this key
        with patch("django.core.cache.cache.get", return_value="1"), \
             patch("notify.service.notify") as mock_notify:
            match_new_listings_to_inventory()

        # notify should NOT be called because cache.get returned "1" (already notified)
        mock_notify.assert_not_called()

    def test_buyer_company_not_notified_for_own_listing(self):
        """Buyer's own company inventory is excluded from notifications."""
        from catalog.tasks import match_new_listings_to_inventory

        buyer_co = make_company("BuyerOwner", is_buyer=True, is_supplier=True)
        buyer_user = make_user("buyerowner@test.com", buyer_co, role=CompanyMember.Role.BUYER)

        part = make_part("ABC123", make_manufacturer("Acme"))

        listing = make_listing(buyer_co, buyer_user)
        ListingLine.objects.create(
            listing=listing, line_no=1, part=part, mpn_raw="ABC123", quantity=10
        )
        # Buyer company also has inventory — should NOT notify itself
        InventoryItem.objects.create(
            company=buyer_co,
            part=part,
            mpn_raw="ABC123",
            manufacturer_raw="Acme",
            quantity=100,
            source=InventoryItem.Source.CSV,
            is_active=True,
        )

        with patch("django.core.cache.cache.get", return_value=None), \
             patch("django.core.cache.cache.set"), \
             patch("notify.service.notify") as mock_notify:
            match_new_listings_to_inventory()

        mock_notify.assert_not_called()
