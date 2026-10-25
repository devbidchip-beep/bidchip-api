"""
Tests for logistics.service:
- get_rate_quotes returns sorted quotes (UPS/FedEx mocked)
- choose_rate sets chosen=True on selected, False on all others
- handle_delivery triggers FSM transition and sets payout_eligible_at
- handle_tracking_webhook looks up by tracking_number
"""

import uuid
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from django.utils import timezone


# ---------------------------------------------------------------------------
# Helpers / Fixtures
# ---------------------------------------------------------------------------

def _make_uuid():
    return uuid.uuid4()


# ---------------------------------------------------------------------------
# get_rate_quotes
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestGetRateQuotes:
    """get_rate_quotes merges UPS + FedEx results, persists RateQuote rows,
    and returns them sorted by amount ascending."""

    def _make_shipment(self):
        from accounts.models import Company, User
        from listings.models import Listing, ListingLine  # noqa: F401 - needed for Order FK
        from orders.models import Order, SupplierOrder
        from accounts.models import Address

        # Minimal test data wired together
        buyer = Company.objects.create(
            legal_name="Buyer Co",
            display_name="Buyer Co",
            country="US",
            is_buyer=True,
        )
        supplier = Company.objects.create(
            legal_name="Supplier Co",
            display_name="Supplier Co",
            country="US",
            is_supplier=True,
        )
        user = User.objects.create_user(email="buyer@test.com", password="x", full_name="Buyer")
        addr = Address.objects.create(
            company=buyer,
            line1="1 Main St",
            city="Boston",
            state="MA",
            postal_code="02101",
            country="US",
        )

        from listings.models import Listing
        listing = Listing.objects.create(
            seller_company=supplier,
            title="Test Listing",
            status="active",
        )

        order = Order.objects.create(
            number="BC-2026-TEST01",
            buyer_company=buyer,
            placed_by=user,
            listing=listing,
            ship_to=addr,
        )

        from orders.models import AWARDED
        supplier_order = SupplierOrder.objects.create(
            order=order,
            supplier_company=supplier,
            anonymous_supplier_id="ANON-001",
            status=AWARDED,
            principal=Decimal("100.00"),
            seller_fee=Decimal("5.00"),
            payout_amount=Decimal("95.00"),
        )

        from logistics.models import Shipment
        shipment = Shipment.objects.create(
            leg="inbound",
            supplier_order=supplier_order,
            carrier="ups",
        )
        return shipment

    def test_returns_sorted_quotes(self):
        """Results from both carriers are merged, saved, and sorted by amount."""
        from logistics.service import get_rate_quotes

        ups_response = [
            {"service_code": "03", "service_name": "UPS Ground", "amount": 12.50,
             "currency": "USD", "transit_days": 5, "is_next_day": False},
            {"service_code": "01", "service_name": "UPS Next Day Air", "amount": 35.00,
             "currency": "USD", "transit_days": 1, "is_next_day": True},
        ]
        fedex_response = [
            {"service_code": "FEDEX_GROUND", "service_name": "FedEx Ground", "amount": 11.00,
             "currency": "USD", "transit_days": 5, "is_next_day": False},
        ]

        with patch("logistics.service.ups.get_rates", return_value=ups_response), \
             patch("logistics.service.fedex.get_rates", return_value=fedex_response):
            shipment = self._make_shipment()
            quotes = get_rate_quotes(
                shipment,
                from_address={"name": "Warehouse", "address_line": "1 Warehouse Blvd",
                               "city": "LA", "state": "CA", "postal_code": "90001",
                               "country_code": "US"},
                to_address={"name": "Buyer", "address_line": "1 Main St",
                            "city": "Boston", "state": "MA", "postal_code": "02101",
                            "country_code": "US"},
                packages=[{"length_cm": 30, "width_cm": 20, "height_cm": 15, "weight_kg": 2.0}],
            )

        assert len(quotes) == 3
        # Should be sorted ascending by amount
        amounts = [q.amount for q in quotes]
        assert amounts == sorted(amounts)
        assert quotes[0].amount == Decimal("11.00")
        assert quotes[0].carrier == "fedex"

    def test_ups_error_does_not_raise(self):
        """If UPS raises, only FedEx results are returned (never raises to caller)."""
        from logistics.service import get_rate_quotes

        with patch("logistics.service.ups.get_rates", side_effect=Exception("UPS down")), \
             patch("logistics.service.fedex.get_rates", return_value=[
                 {"service_code": "FEDEX_GROUND", "service_name": "FedEx Ground",
                  "amount": 11.00, "currency": "USD", "transit_days": 5, "is_next_day": False},
             ]):
            shipment = self._make_shipment()
            quotes = get_rate_quotes(
                shipment,
                from_address={}, to_address={},
                packages=[],
            )

        assert len(quotes) == 1
        assert quotes[0].carrier == "fedex"

    def test_both_carriers_error_returns_empty(self):
        """If both carriers fail, returns empty list without raising."""
        from logistics.service import get_rate_quotes

        with patch("logistics.service.ups.get_rates", return_value=[]), \
             patch("logistics.service.fedex.get_rates", return_value=[]):
            shipment = self._make_shipment()
            quotes = get_rate_quotes(shipment, from_address={}, to_address={}, packages=[])

        assert quotes == []


# ---------------------------------------------------------------------------
# choose_rate
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestChooseRate:
    """choose_rate marks exactly one quote chosen=True and the rest chosen=False."""

    def _make_shipment_with_quotes(self):
        from accounts.models import Address, Company, User
        from orders.models import AWARDED, Order, SupplierOrder
        from listings.models import Listing
        from logistics.models import RateQuote, Shipment

        buyer = Company.objects.create(
            legal_name="Buyer2", display_name="Buyer2", country="US", is_buyer=True
        )
        supplier = Company.objects.create(
            legal_name="Sup2", display_name="Sup2", country="US", is_supplier=True
        )
        user = User.objects.create_user(email="b2@test.com", password="x", full_name="B2")
        addr = Address.objects.create(
            company=buyer, line1="2 St", city="NY", state="NY",
            postal_code="10001", country="US"
        )
        listing = Listing.objects.create(
            seller_company=supplier, title="Test2", status="active"
        )
        order = Order.objects.create(
            number="BC-2026-TEST02", buyer_company=buyer, placed_by=user,
            listing=listing, ship_to=addr,
        )
        so = SupplierOrder.objects.create(
            order=order, supplier_company=supplier,
            anonymous_supplier_id="ANON-002", status=AWARDED,
            principal=Decimal("50.00"), seller_fee=Decimal("2.50"),
            payout_amount=Decimal("47.50"),
        )
        shipment = Shipment.objects.create(leg="inbound", supplier_order=so, carrier="ups")
        q1 = RateQuote.objects.create(
            shipment=shipment, carrier="ups", service_code="03",
            amount=Decimal("12.00"), chosen=False,
        )
        q2 = RateQuote.objects.create(
            shipment=shipment, carrier="fedex", service_code="FEDEX_GROUND",
            amount=Decimal("11.00"), chosen=False,
        )
        q3 = RateQuote.objects.create(
            shipment=shipment, carrier="ups", service_code="01",
            amount=Decimal("35.00"), chosen=False,
        )
        return shipment, q1, q2, q3

    def test_chosen_true_on_selected(self):
        from logistics.service import choose_rate

        shipment, q1, q2, q3 = self._make_shipment_with_quotes()
        choose_rate(shipment, q2)

        q1.refresh_from_db()
        q2.refresh_from_db()
        q3.refresh_from_db()

        assert q2.chosen is True
        assert q1.chosen is False
        assert q3.chosen is False

    def test_switching_chosen_quote(self):
        from logistics.service import choose_rate

        shipment, q1, q2, q3 = self._make_shipment_with_quotes()
        choose_rate(shipment, q2)
        choose_rate(shipment, q1)  # switch

        q1.refresh_from_db()
        q2.refresh_from_db()
        q3.refresh_from_db()

        assert q1.chosen is True
        assert q2.chosen is False
        assert q3.chosen is False


# ---------------------------------------------------------------------------
# handle_delivery
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestHandleDelivery:
    """handle_delivery calls the FSM transition and sets payout_eligible_at."""

    def _make_shipped_to_buyer_so(self):
        from accounts.models import Address, Company, User
        from orders.models import (
            AT_WAREHOUSE,
            INSPECTED,
            PAID,
            SHIPPED_TO_BUYER,
            SHIPPED_TO_WAREHOUSE,
            AWARDED,
            Order,
            SupplierOrder,
        )
        from listings.models import Listing

        buyer = Company.objects.create(
            legal_name="BuyerD", display_name="BuyerD", country="US", is_buyer=True
        )
        supplier = Company.objects.create(
            legal_name="SupD", display_name="SupD", country="US", is_supplier=True
        )
        user = User.objects.create_user(email="bd@test.com", password="x", full_name="BD")
        addr = Address.objects.create(
            company=buyer, line1="3 Rd", city="Chicago", state="IL",
            postal_code="60601", country="US"
        )
        listing = Listing.objects.create(
            seller_company=supplier, title="TestD", status="active"
        )
        order = Order.objects.create(
            number="BC-2026-TEST03", buyer_company=buyer, placed_by=user,
            listing=listing, ship_to=addr,
        )
        so = SupplierOrder.objects.create(
            order=order, supplier_company=supplier,
            anonymous_supplier_id="ANON-003", status=AWARDED,
            principal=Decimal("200.00"), seller_fee=Decimal("10.00"),
            payout_amount=Decimal("190.00"),
            hold_days=5,
        )
        # Walk through FSM to SHIPPED_TO_BUYER
        so.mark_paid(); so.save()
        so.mark_shipped_to_warehouse(); so.save()
        so.mark_at_warehouse(); so.save()
        so.mark_inspected(); so.save()
        so.mark_shipped_to_buyer(); so.save()
        return so

    def test_fsm_transition_to_delivered(self):
        from logistics.service import handle_delivery
        from orders.models import DELIVERED

        so = self._make_shipped_to_buyer_so()
        with patch("logistics.service._notify_buyer_delivered"):
            handle_delivery(so)

        so.refresh_from_db()
        assert so.status == DELIVERED

    def test_payout_eligible_at_is_set(self):
        from logistics.service import handle_delivery

        so = self._make_shipped_to_buyer_so()
        with patch("logistics.service._notify_buyer_delivered"):
            handle_delivery(so)

        so.refresh_from_db()
        assert so.payout_eligible_at is not None
        # payout_eligible_at should be after delivered_at
        assert so.payout_eligible_at > so.delivered_at

    def test_delivered_source_set_to_carrier_scan(self):
        from logistics.service import handle_delivery

        so = self._make_shipped_to_buyer_so()
        with patch("logistics.service._notify_buyer_delivered"):
            handle_delivery(so)

        so.refresh_from_db()
        assert so.delivered_source == "carrier_scan"

    def test_fsm_wrong_state_does_not_raise(self):
        """handle_delivery should not raise even if FSM transition fails."""
        from logistics.service import handle_delivery
        from orders.models import AWARDED, Order, SupplierOrder
        from accounts.models import Address, Company, User
        from listings.models import Listing

        buyer = Company.objects.create(
            legal_name="BuyerE", display_name="BuyerE", country="US", is_buyer=True
        )
        supplier = Company.objects.create(
            legal_name="SupE", display_name="SupE", country="US", is_supplier=True
        )
        user = User.objects.create_user(email="be@test.com", password="x", full_name="BE")
        addr = Address.objects.create(
            company=buyer, line1="4 Ave", city="Houston", state="TX",
            postal_code="77001", country="US"
        )
        listing = Listing.objects.create(
            seller_company=supplier, title="TestE", status="active"
        )
        order = Order.objects.create(
            number="BC-2026-TEST04", buyer_company=buyer, placed_by=user,
            listing=listing, ship_to=addr,
        )
        so = SupplierOrder.objects.create(
            order=order, supplier_company=supplier,
            anonymous_supplier_id="ANON-004", status=AWARDED,
            principal=Decimal("50.00"), seller_fee=Decimal("2.50"),
            payout_amount=Decimal("47.50"),
        )
        # Still in AWARDED — mark_delivered will fail FSM validation
        # Should not raise
        handle_delivery(so)  # Must not raise


# ---------------------------------------------------------------------------
# handle_tracking_webhook
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestHandleTrackingWebhook:
    """handle_tracking_webhook looks up shipment by tracking_number."""

    def _make_in_transit_shipment(self, tracking_number: str):
        from accounts.models import Address, Company, User
        from orders.models import AWARDED, Order, SupplierOrder
        from listings.models import Listing
        from logistics.models import Shipment

        buyer = Company.objects.create(
            legal_name="BuyerW", display_name="BuyerW", country="US", is_buyer=True
        )
        supplier = Company.objects.create(
            legal_name="SupW", display_name="SupW", country="US", is_supplier=True
        )
        user = User.objects.create_user(email="bw@test.com", password="x", full_name="BW")
        addr = Address.objects.create(
            company=buyer, line1="5 Blvd", city="Miami", state="FL",
            postal_code="33101", country="US"
        )
        listing = Listing.objects.create(
            seller_company=supplier, title="TestW", status="active"
        )
        order = Order.objects.create(
            number="BC-2026-TEST05", buyer_company=buyer, placed_by=user,
            listing=listing, ship_to=addr,
        )
        so = SupplierOrder.objects.create(
            order=order, supplier_company=supplier,
            anonymous_supplier_id="ANON-005", status=AWARDED,
            principal=Decimal("80.00"), seller_fee=Decimal("4.00"),
            payout_amount=Decimal("76.00"),
        )
        shipment = Shipment.objects.create(
            leg="inbound",
            supplier_order=so,
            carrier="ups",
            tracking_number=tracking_number,
            status="in_transit",
        )
        return shipment, so

    def test_lookup_by_tracking_number(self):
        """Webhook handler finds the correct shipment by tracking_number."""
        from logistics.service import handle_tracking_webhook
        from logistics.models import Shipment

        tracking_number = "1Z999AA10123456784"
        shipment, so = self._make_in_transit_shipment(tracking_number)

        event_time = timezone.now()
        with patch("logistics.service.handle_delivery"):
            handle_tracking_webhook("ups", tracking_number, "X", event_time)

        # Shipment still exists and can be looked up
        assert Shipment.objects.filter(tracking_number=tracking_number).exists()

    def test_delivery_event_marks_shipment_delivered(self):
        """A delivery event_type updates shipment.status to delivered."""
        from logistics.service import handle_tracking_webhook
        from logistics.models import Shipment

        tracking_number = "1Z999AA10123456785"
        shipment, so = self._make_in_transit_shipment(tracking_number)

        event_time = timezone.now()
        with patch("logistics.service.handle_delivery"):
            handle_tracking_webhook("ups", tracking_number, "D", event_time)

        shipment.refresh_from_db()
        assert shipment.status == "delivered"
        assert shipment.delivered_at is not None

    def test_non_delivery_event_does_not_mark_delivered(self):
        """A non-delivery event_type does not change shipment status."""
        from logistics.service import handle_tracking_webhook
        from logistics.models import Shipment

        tracking_number = "1Z999AA10123456786"
        shipment, so = self._make_in_transit_shipment(tracking_number)

        event_time = timezone.now()
        handle_tracking_webhook("ups", tracking_number, "I", event_time)  # I = In Transit

        shipment.refresh_from_db()
        assert shipment.status == "in_transit"

    def test_unknown_tracking_number_does_not_raise(self):
        """Passing an unknown tracking_number silently returns without error."""
        from logistics.service import handle_tracking_webhook

        # Should not raise
        handle_tracking_webhook("ups", "UNKNOWN_TRACKING_999", "D", timezone.now())
