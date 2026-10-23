"""
Tests for listings models.
"""

import pytest
from django.db import IntegrityError
from django.utils import timezone

from listings.models import ComplianceScreening, Listing, ListingLine


# ---------------------------------------------------------------------------
# Listing number auto-generation
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestListingNumberAutoGeneration:
    def test_number_generated_on_save(self, listing):
        assert listing.number != ""
        assert listing.number is not None

    def test_number_format(self, listing):
        # e.g. RE-2026-000001
        parts = listing.number.split("-")
        assert len(parts) == 3
        assert len(parts[2]) == 6  # zero-padded to 6 digits

    def test_number_not_overwritten_on_update(self, listing):
        original_number = listing.number
        listing.title = "Updated Title"
        listing.save()
        listing.refresh_from_db()
        assert listing.number == original_number


# ---------------------------------------------------------------------------
# ListingLine unique_together (listing, line_no)
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestListingLineUniqueTogether:
    def test_duplicate_line_no_raises(self, listing):
        ListingLine.objects.create(
            listing=listing,
            line_no=1,
            mpn_raw="LM317T",
            quantity=100,
        )
        with pytest.raises(IntegrityError):
            ListingLine.objects.create(
                listing=listing,
                line_no=1,
                mpn_raw="LM317T",
                quantity=200,
            )

    def test_same_line_no_different_listing_allowed(self, listing, company, user):
        listing2 = Listing.objects.create(
            kind=Listing.Kind.REVERSE,
            status=Listing.Status.DRAFT,
            buyer_company=company,
            created_by=user,
            title="Listing 2",
        )
        line1 = ListingLine.objects.create(listing=listing, line_no=1, mpn_raw="LM317T", quantity=100)
        line2 = ListingLine.objects.create(listing=listing2, line_no=1, mpn_raw="LM317T", quantity=200)
        assert line1.listing != line2.listing


# ---------------------------------------------------------------------------
# ends_at computed on publish
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestEndsAtComputedOnPublish:
    def test_ends_at_computed_when_published(self, listing):
        assert listing.ends_at is None
        listing.status = Listing.Status.PUBLISHED
        listing.starts_at = timezone.now()
        listing.duration_minutes = 60
        listing.save()
        listing.refresh_from_db()
        assert listing.ends_at is not None

    def test_ends_at_not_overwritten_if_already_set(self, listing):
        fixed_ends_at = timezone.now() + timezone.timedelta(hours=10)
        listing.status = Listing.Status.PUBLISHED
        listing.starts_at = timezone.now()
        listing.ends_at = fixed_ends_at
        listing.save()
        listing.refresh_from_db()
        assert listing.ends_at == fixed_ends_at


# ---------------------------------------------------------------------------
# ComplianceScreening one-to-one with ListingLine
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestComplianceScreeningOneToOne:
    def test_create_screening_for_line(self, listing):
        line = ListingLine.objects.create(
            listing=listing,
            line_no=1,
            mpn_raw="LM317T",
            quantity=100,
        )
        screening = ComplianceScreening.objects.create(line=line)
        assert screening.line == line
        assert screening.ai_flagged is False

    def test_duplicate_screening_for_same_line_raises(self, listing):
        line = ListingLine.objects.create(
            listing=listing,
            line_no=1,
            mpn_raw="LM317T",
            quantity=100,
        )
        ComplianceScreening.objects.create(line=line)
        with pytest.raises(IntegrityError):
            ComplianceScreening.objects.create(line=line)
