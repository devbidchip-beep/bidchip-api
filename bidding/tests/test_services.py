"""
Unit tests for bidding.services.
Uses pytest-django with factory-style helpers.
"""

import pytest
from decimal import Decimal
from django.core.exceptions import ValidationError
from django.utils import timezone


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def buyer_company(db):
    from accounts.models import Company
    return Company.objects.create(
        legal_name="Buyer Corp",
        display_name="Buyer Corp",
        country="US",
        is_buyer=True,
        status=Company.Status.VERIFIED,
    )


@pytest.fixture
def supplier_company(db):
    from accounts.models import Company
    return Company.objects.create(
        legal_name="Supplier Inc",
        display_name="Supplier Inc",
        country="US",
        is_supplier=True,
        status=Company.Status.VERIFIED,
    )


@pytest.fixture
def buyer_user(db, buyer_company):
    from accounts.models import CompanyMember, User
    user = User.objects.create_user(email="buyer@test.com", password="pass", full_name="Buyer User")
    CompanyMember.objects.create(
        user=user, company=buyer_company, role="owner", status="active"
    )
    return user


@pytest.fixture
def supplier_user(db, supplier_company):
    from accounts.models import CompanyMember, User
    user = User.objects.create_user(email="supplier@test.com", password="pass", full_name="Supplier User")
    CompanyMember.objects.create(
        user=user, company=supplier_company, role="seller", status="active"
    )
    return user


@pytest.fixture
def published_listing(db, buyer_company, buyer_user):
    from listings.models import Listing
    return Listing.objects.create(
        title="Test Listing",
        kind=Listing.Kind.REVERSE,
        status=Listing.Status.PUBLISHED,
        buyer_company=buyer_company,
        created_by=buyer_user,
        ends_at=timezone.now() + timezone.timedelta(hours=24),
    )


@pytest.fixture
def listing_line(db, published_listing):
    from listings.models import ListingLine
    return ListingLine.objects.create(
        listing=published_listing,
        line_no=1,
        mpn_raw="TEST-MPN-001",
        quantity=100,
        allow_exceptions=True,
    )


@pytest.fixture
def strict_listing_line(db, published_listing):
    """Line that does not allow exceptions."""
    from listings.models import ListingLine
    return ListingLine.objects.create(
        listing=published_listing,
        line_no=2,
        mpn_raw="TEST-MPN-002",
        quantity=100,
        allow_exceptions=False,
    )


# ---------------------------------------------------------------------------
# place_bid tests
# ---------------------------------------------------------------------------

class TestPlaceBid:
    def test_happy_path_exact_match(self, listing_line, supplier_company, supplier_user):
        from bidding.services import place_bid
        bid = place_bid(
            line=listing_line,
            supplier_company=supplier_company,
            placed_by=supplier_user,
            unit_price=Decimal("1.5000"),
            quantity_offered=100,
        )
        assert bid.pk is not None
        assert bid.is_exact_match is True
        assert bid.exception_reasons == []
        assert bid.status == "active"

    def test_exception_bid_qty_short(self, listing_line, supplier_company, supplier_user):
        from bidding.services import place_bid
        bid = place_bid(
            line=listing_line,
            supplier_company=supplier_company,
            placed_by=supplier_user,
            unit_price=Decimal("1.5000"),
            quantity_offered=50,  # less than 100 required
        )
        assert bid.is_exact_match is False
        assert "qty_short" in bid.exception_reasons

    def test_rejected_when_listing_closed(self, listing_line, supplier_company, supplier_user):
        from bidding.services import place_bid
        from listings.models import Listing
        listing = listing_line.listing
        listing.status = Listing.Status.CLOSED
        listing.save(update_fields=["status", "updated_at"])

        with pytest.raises(ValidationError, match="not published"):
            place_bid(
                line=listing_line,
                supplier_company=supplier_company,
                placed_by=supplier_user,
                unit_price=Decimal("1.0000"),
                quantity_offered=100,
            )

    def test_rejected_when_listing_expired(self, listing_line, supplier_company, supplier_user):
        from bidding.services import place_bid
        listing = listing_line.listing
        listing.ends_at = timezone.now() - timezone.timedelta(seconds=1)
        listing.save(update_fields=["ends_at", "updated_at"])

        with pytest.raises(ValidationError, match="expired"):
            place_bid(
                line=listing_line,
                supplier_company=supplier_company,
                placed_by=supplier_user,
                unit_price=Decimal("1.0000"),
                quantity_offered=100,
            )

    def test_rejected_when_bidding_own_listing(self, listing_line, buyer_company, buyer_user):
        from bidding.services import place_bid
        with pytest.raises(ValidationError, match="own listing"):
            place_bid(
                line=listing_line,
                supplier_company=buyer_company,
                placed_by=buyer_user,
                unit_price=Decimal("1.0000"),
                quantity_offered=100,
            )

    def test_rejected_when_exceptions_not_allowed(self, strict_listing_line, supplier_company, supplier_user):
        from bidding.services import place_bid
        with pytest.raises(ValidationError, match="does not allow exceptions"):
            place_bid(
                line=strict_listing_line,
                supplier_company=supplier_company,
                placed_by=supplier_user,
                unit_price=Decimal("1.0000"),
                quantity_offered=50,  # short — exception
            )


# ---------------------------------------------------------------------------
# auto_award_line tests
# ---------------------------------------------------------------------------

class TestAutoAwardLine:
    def test_picks_lowest_exact_match(self, listing_line, supplier_company, supplier_user, db):
        from accounts.models import Company, CompanyMember, User
        from bidding.services import auto_award_line, place_bid

        # Place two exact-match bids from different suppliers
        supplier2 = Company.objects.create(
            legal_name="Supplier Two", display_name="Supplier Two",
            country="US", is_supplier=True, status=Company.Status.VERIFIED,
        )
        user2 = User.objects.create_user(email="s2@test.com", password="p", full_name="S2")
        CompanyMember.objects.create(user=user2, company=supplier2, role="seller", status="active")

        place_bid(
            line=listing_line,
            supplier_company=supplier_company,
            placed_by=supplier_user,
            unit_price=Decimal("2.0000"),
            quantity_offered=100,
        )
        place_bid(
            line=listing_line,
            supplier_company=supplier2,
            placed_by=user2,
            unit_price=Decimal("1.5000"),
            quantity_offered=100,
        )

        awards = auto_award_line(listing_line)
        assert len(awards) == 1
        assert awards[0].unit_price == Decimal("1.5000")
        assert awards[0].bid.supplier_company == supplier2

    def test_fallback_to_exception_when_no_exact_match(self, listing_line, supplier_company, supplier_user):
        from bidding.services import auto_award_line, place_bid

        # Place only a short-qty bid (exception)
        place_bid(
            line=listing_line,
            supplier_company=supplier_company,
            placed_by=supplier_user,
            unit_price=Decimal("1.0000"),
            quantity_offered=50,  # short
        )

        awards = auto_award_line(listing_line)
        assert len(awards) == 1
        assert awards[0].bid.supplier_company == supplier_company

    def test_no_award_when_no_bids(self, listing_line):
        from bidding.services import auto_award_line
        from listings.models import ListingLine

        awards = auto_award_line(listing_line)
        assert awards == []
        listing_line.refresh_from_db()
        assert listing_line.status == ListingLine.Status.NO_AWARD


# ---------------------------------------------------------------------------
# award_line tests
# ---------------------------------------------------------------------------

class TestAwardLine:
    def test_enforces_quantity_constraint(self, listing_line, supplier_company, supplier_user):
        from bidding.services import award_line, place_bid

        bid = place_bid(
            line=listing_line,
            supplier_company=supplier_company,
            placed_by=supplier_user,
            unit_price=Decimal("1.0000"),
            quantity_offered=100,
        )

        # Try awarding more than the line quantity
        with pytest.raises(ValidationError, match="exceeds line quantity"):
            award_line(listing_line, [{"bid": bid, "quantity": 999}])

    def test_award_marks_bid_won(self, listing_line, supplier_company, supplier_user):
        from bidding.models import Bid
        from bidding.services import award_line, place_bid

        bid = place_bid(
            line=listing_line,
            supplier_company=supplier_company,
            placed_by=supplier_user,
            unit_price=Decimal("1.0000"),
            quantity_offered=100,
        )

        awards = award_line(listing_line, [{"bid": bid, "quantity": 100}])
        assert len(awards) == 1
        bid.refresh_from_db()
        assert bid.status == Bid.Status.WON
