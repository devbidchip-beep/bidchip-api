"""
Trust service tests.
"""

import hashlib
import json
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from django.utils import timezone


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

def _make_company(db, is_supplier=True, integrity_score=90, days_old=365):
    from accounts.models import Company
    created_at = timezone.now() - timezone.timedelta(days=days_old)
    company = Company.objects.create(
        legal_name="Test Co",
        display_name="Test Co",
        country="US",
        is_supplier=is_supplier,
        is_buyer=not is_supplier,
        integrity_score=Decimal(str(integrity_score)),
    )
    # Force created_at
    Company.objects.filter(pk=company.pk).update(created_at=created_at)
    company.refresh_from_db()
    return company


def _make_buyer_company(db):
    from accounts.models import Company
    return Company.objects.create(
        legal_name="Buyer Co",
        display_name="Buyer Co",
        country="US",
        is_buyer=True,
        integrity_score=Decimal("90"),
    )


def _make_user(db, company, is_staff=False, staff_role=None):
    from accounts.models import User, CompanyMember
    user = User.objects.create_user(
        email=f"user_{company.pk}_{is_staff}@test.com",
        password="pass",
        full_name="Test User",
        is_staff=is_staff,
        staff_role=staff_role,
    )
    CompanyMember.objects.create(
        user=user,
        company=company,
        role=CompanyMember.Role.BUYER,
        status=CompanyMember.Status.ACTIVE,
    )
    return user


def _make_listing(db, buyer_company):
    from listings.models import Listing
    return Listing.objects.create(
        buyer_company=buyer_company,
        title="Test Listing",
        kind=Listing.Kind.REVERSE,
        status=Listing.Status.AWARDED,
    )


def _make_address(db, company):
    from accounts.models import Address
    return Address.objects.create(
        company=company,
        line1="123 Main St",
        city="Anytown",
        postal_code="12345",
        country="US",
    )


def _make_order(db, buyer_company, listing, address, placed_by):
    from orders.models import Order
    return Order.objects.create(
        number=f"BC-2026-{Order.objects.count():06d}",
        buyer_company=buyer_company,
        placed_by=placed_by,
        listing=listing,
        status=Order.Status.PAID,
        ship_to=address,
        principal_total=Decimal("1000.00"),
        grand_total=Decimal("1100.00"),
    )


def _make_supplier_order(db, order, supplier_company, principal=Decimal("1000.00"),
                         status="delivered"):
    import random
    import string
    from orders.models import SupplierOrder
    anon_id = "S-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=4)) + \
              "-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=4))
    so = SupplierOrder.objects.create(
        order=order,
        supplier_company=supplier_company,
        anonymous_supplier_id=anon_id,
        status=status,
        risk_tier="green",
        principal=principal,
        seller_fee=Decimal("50.00"),
        payout_amount=principal - Decimal("50.00"),
        hold_days=5,
    )
    return so


def _make_payout(db, supplier_order):
    from payments.models import Payout
    from accounts.models import StripeAccount
    stripe_acc = StripeAccount.objects.create(
        company=supplier_order.supplier_company,
        stripe_account_id=f"acct_{supplier_order.pk}",
        country="US",
        status=StripeAccount.Status.ACTIVE,
    )
    return Payout.objects.create(
        supplier_order=supplier_order,
        stripe_account=stripe_acc,
        amount=supplier_order.payout_amount,
        idempotency_key=f"payout-{supplier_order.pk}",
        source_charge="ch_test",
        status=Payout.Status.SCHEDULED,
    )


# ---------------------------------------------------------------------------
# assess_risk tests
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_assess_risk_new_supplier_high_value_is_red():
    """New supplier (< 6 months) + high value (> $50k) → red tier."""
    from trust.services import assess_risk

    buyer_co = _make_buyer_company(None)
    supplier_co = _make_company(None, days_old=30)  # < 6 months
    buyer_user = _make_user(None, buyer_co)
    listing = _make_listing(None, buyer_co)
    address = _make_address(None, buyer_co)
    order = _make_order(None, buyer_co, listing, address, buyer_user)

    so = _make_supplier_order(
        None, order, supplier_co,
        principal=Decimal("60000.00"),  # > $50k
        status="awarded",
    )

    assessment = assess_risk(so)

    # Score: +20 (age) + 30 (0 completed orders) + 25 (>$50k) = 75 → red
    assert assessment.tier == "red"
    assert assessment.score >= Decimal("60")
    assert so.requires_manual_release is True


@pytest.mark.django_db
def test_assess_risk_established_supplier_low_value_is_green():
    """Established supplier (> 6 months, many orders) + low value → green tier."""
    from orders.models import SupplierOrder
    from trust.services import assess_risk

    buyer_co = _make_buyer_company(None)
    supplier_co = _make_company(None, days_old=400, integrity_score=95)
    buyer_user = _make_user(None, buyer_co)
    listing = _make_listing(None, buyer_co)
    address = _make_address(None, buyer_co)
    order = _make_order(None, buyer_co, listing, address, buyer_user)

    # Create 10 completed (payout_released) past orders
    for i in range(10):
        past_so = _make_supplier_order(
            None, order, supplier_co,
            principal=Decimal("500.00"),
            status="payout_released",
        )

    # New order with low value
    so = _make_supplier_order(
        None, order, supplier_co,
        principal=Decimal("500.00"),  # < $10k
        status="awarded",
    )

    assessment = assess_risk(so)

    # Score: 0 (age ok) + 0 (history ok, >5 orders) + 0 (value ok) = 0 → green
    assert assessment.tier == "green"
    assert assessment.score < Decimal("30")
    assert so.requires_manual_release is False
    assert so.hold_days is not None


# ---------------------------------------------------------------------------
# open_dispute / payout pausing
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_open_dispute_pauses_payout():
    """Opening a dispute sets payout to awaiting_release."""
    from trust.services import open_dispute

    buyer_co = _make_buyer_company(None)
    supplier_co = _make_company(None)
    buyer_user = _make_user(None, buyer_co)
    listing = _make_listing(None, buyer_co)
    address = _make_address(None, buyer_co)
    order = _make_order(None, buyer_co, listing, address, buyer_user)

    so = _make_supplier_order(None, order, supplier_co, status="delivered")
    payout = _make_payout(None, so)

    assert payout.status == "scheduled"

    dispute = open_dispute(
        supplier_order=so,
        opened_by=buyer_user,
        reason="not_as_described",
        description="Parts do not match description.",
    )

    payout.refresh_from_db()
    so.refresh_from_db()

    assert dispute.status == "open"
    assert so.status == "disputed"
    assert payout.status == "awaiting_release"


@pytest.mark.django_db
def test_open_dispute_wrong_status_raises():
    """Opening dispute on awarded order should raise ValueError."""
    from trust.services import open_dispute

    buyer_co = _make_buyer_company(None)
    supplier_co = _make_company(None)
    buyer_user = _make_user(None, buyer_co)
    listing = _make_listing(None, buyer_co)
    address = _make_address(None, buyer_co)
    order = _make_order(None, buyer_co, listing, address, buyer_user)

    so = _make_supplier_order(None, order, supplier_co, status="awarded")

    with pytest.raises(ValueError, match="delivered"):
        open_dispute(
            supplier_order=so,
            opened_by=buyer_user,
            reason="other",
            description="Test.",
        )


# ---------------------------------------------------------------------------
# resolve_dispute — payout resumed for resolved_seller
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_resolve_dispute_seller_resumes_payout():
    """Resolving dispute as resolved_seller resumes the payout."""
    from trust.models import Dispute
    from trust.services import open_dispute, resolve_dispute

    buyer_co = _make_buyer_company(None)
    supplier_co = _make_company(None)
    buyer_user = _make_user(None, buyer_co)
    staff_user = _make_user(None, buyer_co, is_staff=True)
    listing = _make_listing(None, buyer_co)
    address = _make_address(None, buyer_co)
    order = _make_order(None, buyer_co, listing, address, buyer_user)

    so = _make_supplier_order(None, order, supplier_co, status="delivered")
    payout = _make_payout(None, so)

    dispute = open_dispute(
        supplier_order=so,
        opened_by=buyer_user,
        reason="other",
        description="Test.",
    )

    resolved = resolve_dispute(
        dispute=dispute,
        resolved_by=staff_user,
        status=Dispute.Status.RESOLVED_SELLER,
        resolution_note="Confirmed genuine.",
    )

    payout.refresh_from_db()
    assert resolved.status == "resolved_seller"
    assert resolved.resolved_by == staff_user
    assert payout.status == "scheduled"


# ---------------------------------------------------------------------------
# submit_rating
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_submit_rating_validates_scores():
    """Submitting a rating with score < 1 raises ValueError."""
    from trust.services import submit_rating

    buyer_co = _make_buyer_company(None)
    supplier_co = _make_company(None)
    buyer_user = _make_user(None, buyer_co)
    listing = _make_listing(None, buyer_co)
    address = _make_address(None, buyer_co)
    order = _make_order(None, buyer_co, listing, address, buyer_user)
    so = _make_supplier_order(None, order, supplier_co, status="payout_released")

    with pytest.raises(ValueError, match="quality"):
        submit_rating(
            supplier_order=so,
            rater_company=buyer_co,
            direction="buyer_to_supplier",
            quality=0,  # invalid
            communication=4,
            shipping=4,
            documentation=4,
        )


@pytest.mark.django_db
def test_submit_rating_prevents_duplicate():
    """Duplicate rating for same (supplier_order, direction) raises ValueError."""
    from trust.models import Rating
    from trust.services import submit_rating

    buyer_co = _make_buyer_company(None)
    supplier_co = _make_company(None)
    buyer_user = _make_user(None, buyer_co)
    listing = _make_listing(None, buyer_co)
    address = _make_address(None, buyer_co)
    order = _make_order(None, buyer_co, listing, address, buyer_user)
    so = _make_supplier_order(None, order, supplier_co, status="payout_released")

    submit_rating(
        supplier_order=so,
        rater_company=buyer_co,
        direction="buyer_to_supplier",
        quality=4,
        communication=4,
        shipping=4,
        documentation=4,
    )

    with pytest.raises(ValueError, match="already exists"):
        submit_rating(
            supplier_order=so,
            rater_company=buyer_co,
            direction="buyer_to_supplier",
            quality=3,
            communication=3,
            shipping=3,
            documentation=3,
        )


# ---------------------------------------------------------------------------
# append_chain_event / verify_chain
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_append_chain_event_builds_correct_hash_chain():
    """Two events should form a valid hash chain."""
    from trust.services import append_chain_event, verify_chain

    supplier_co = _make_company(None)

    event1 = append_chain_event(
        supplier_company=supplier_co,
        event_type="bid_committed",
        ref_type="supplierorder",
        ref_id="aaaa-1111",
        payload={"amount": "1000.00"},
    )

    event2 = append_chain_event(
        supplier_company=supplier_co,
        event_type="award",
        ref_type="supplierorder",
        ref_id="aaaa-1111",
        payload={"award_id": "bbbb-2222"},
    )

    assert event1.seq == 1
    assert event2.seq == 2
    assert event2.prev_hash == event1.hash

    # Verify chain integrity
    valid, msg = verify_chain(supplier_co)
    assert valid is True
    assert msg == "OK"


@pytest.mark.django_db
def test_verify_chain_detects_tampering():
    """Tampering with a hash should be detected."""
    from trust.services import append_chain_event, verify_chain

    supplier_co = _make_company(None)

    event1 = append_chain_event(
        supplier_company=supplier_co,
        event_type="bid_committed",
        ref_type="supplierorder",
        ref_id="aaaa-1111",
        payload={"amount": "1000.00"},
    )

    event2 = append_chain_event(
        supplier_company=supplier_co,
        event_type="award",
        ref_type="supplierorder",
        ref_id="aaaa-1111",
        payload={"award_id": "bbbb-2222"},
    )

    # Tamper with event2's hash directly in DB
    from trust.models import SellerChainEvent
    SellerChainEvent.objects.filter(pk=event2.pk).update(hash="tampered" + "0" * 57)

    valid, msg = verify_chain(supplier_co)
    assert valid is False
    assert "seq=2" in msg


@pytest.mark.django_db
def test_verify_chain_freezes_payouts_on_broken_chain():
    """A broken chain should freeze all scheduled payouts for the supplier."""
    from trust.services import append_chain_event, verify_chain

    buyer_co = _make_buyer_company(None)
    supplier_co = _make_company(None)
    buyer_user = _make_user(None, buyer_co)
    listing = _make_listing(None, buyer_co)
    address = _make_address(None, buyer_co)
    order = _make_order(None, buyer_co, listing, address, buyer_user)

    so = _make_supplier_order(None, order, supplier_co, status="delivered")
    payout = _make_payout(None, so)

    event1 = append_chain_event(
        supplier_company=supplier_co,
        event_type="bid_committed",
        ref_type="supplierorder",
        ref_id=str(so.pk),
        payload={"amount": str(so.principal)},
    )

    # Tamper with the event
    from trust.models import SellerChainEvent
    SellerChainEvent.objects.filter(pk=event1.pk).update(hash="bad" + "0" * 61)

    valid, msg = verify_chain(supplier_co)
    assert valid is False

    payout.refresh_from_db()
    assert payout.status == "awaiting_release"
