"""
Tests for orders.service — order creation and FSM transitions.
"""

import re
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_award(unit_price, qty, supplier=None, listing=None):
    """Create a mock Award."""
    award = MagicMock()
    award.unit_price = Decimal(str(unit_price))
    award.quantity_awarded = qty
    award.id = "award-1"

    if supplier is None:
        supplier = MagicMock()
        supplier.id = "supplier-1"

    award.bid.supplier_company = supplier

    if listing is None:
        listing = MagicMock()
        listing.id = "listing-1"

    line = MagicMock()
    line.listing = listing
    line.compliance_status = "clear"
    award.line = line

    return award


# ---------------------------------------------------------------------------
# create_order_from_awards
# ---------------------------------------------------------------------------

class TestCreateOrderFromAwards:
    @patch("orders.service.OEMEMSLink")
    @patch("orders.service.OrderStatusLog")
    @patch("orders.service.OrderLine")
    @patch("orders.service.SupplierOrder")
    @patch("orders.service.Order")
    @patch("orders.service.price_order")
    @patch("orders.service._get_platform_setting")
    def test_creates_order_supplier_orders_and_lines(
        self,
        mock_setting,
        mock_price_order,
        mock_order_cls,
        mock_so_cls,
        mock_line_cls,
        mock_log_cls,
        mock_oem_link,
    ):
        """create_order_from_awards creates Order, SupplierOrder, and OrderLine."""
        from orders.service import create_order_from_awards

        mock_setting.return_value = 5

        # Mock pricing result
        pricing = MagicMock()
        pricing.principal = Decimal("10000.00")
        pricing.buyer_fee = Decimal("700.00")
        pricing.seller_fee = Decimal("500.00")
        pricing.inspection_fee = Decimal("400.00")
        pricing.compliance_fee = Decimal("0.00")
        pricing.shipping_estimate = Decimal("250.00")
        pricing.oem_uplift = Decimal("0.00")
        pricing.tax_total = Decimal("0.00")
        pricing.card_surcharge = Decimal("0.00")
        pricing.card_surcharge_rate = Decimal("0.00")
        pricing.grand_total = Decimal("11350.00")
        pricing.pricing_snapshot = {}
        mock_price_order.return_value = pricing

        # Mock Order.objects
        mock_order_obj = MagicMock()
        mock_order_obj.number = "BC-2026-000001"
        mock_order_cls.objects.count.return_value = 0
        mock_order_cls.objects.create.return_value = mock_order_obj
        mock_order_cls.Status.PAYMENT_PENDING = "payment_pending"

        # Mock SupplierOrder
        mock_so_obj = MagicMock()
        mock_so_cls.objects.filter.return_value.exists.return_value = False
        mock_so_cls.objects.create.return_value = mock_so_obj

        mock_oem_link.objects.filter.return_value.first.return_value = None

        buyer_company = MagicMock()
        buyer_company.id = "buyer-1"
        placed_by = MagicMock()
        ship_to = MagicMock()
        ship_to.id = "addr-1"
        ship_to.line1 = "123 Main St"
        ship_to.line2 = ""
        ship_to.city = "Boston"
        ship_to.state = "MA"
        ship_to.postal_code = "02101"
        ship_to.country = "US"

        awards = [_make_award("100.00", 100)]

        result = create_order_from_awards(
            awards=awards,
            buyer_company=buyer_company,
            placed_by=placed_by,
            ship_to=ship_to,
            shipping_estimate=Decimal("250.00"),
        )

        # Verify Order was created
        mock_order_cls.objects.create.assert_called_once()
        # Verify SupplierOrder was created
        mock_so_cls.objects.create.assert_called_once()
        # Verify OrderLine was created
        mock_line_cls.objects.create.assert_called_once()
        # Verify status log was created
        mock_log_cls.objects.create.assert_called_once()

        assert result == mock_order_obj

    @patch("orders.service.OEMEMSLink")
    @patch("orders.service.OrderStatusLog")
    @patch("orders.service.OrderLine")
    @patch("orders.service.SupplierOrder")
    @patch("orders.service.Order")
    @patch("orders.service.price_order")
    @patch("orders.service._get_platform_setting")
    def test_anonymous_supplier_id_format(
        self,
        mock_setting,
        mock_price_order,
        mock_order_cls,
        mock_so_cls,
        mock_line_cls,
        mock_log_cls,
        mock_oem_link,
    ):
        """anonymous_supplier_id should match S-XXXX-XXXX pattern."""
        from orders.service import _generate_anonymous_supplier_id

        anon_id = _generate_anonymous_supplier_id()
        pattern = r"^S-[A-Z0-9]{4}-[A-Z0-9]{4}$"
        assert re.match(pattern, anon_id), f"Unexpected format: {anon_id}"


# ---------------------------------------------------------------------------
# FSM transitions
# ---------------------------------------------------------------------------

class TestSupplierOrderFSM:
    """Tests for SupplierOrder state machine transitions."""

    def _make_supplier_order(self, status="awarded"):
        from orders.models import SupplierOrder
        so = SupplierOrder.__new__(SupplierOrder)
        so.status = status
        so.payout_amount = Decimal("9500.00")
        return so

    def test_awarded_to_paid(self):
        """awarded → paid is valid."""
        from orders.models import SupplierOrder
        so = SupplierOrder(
            status="awarded",
            principal=Decimal("10000.00"),
            seller_fee=Decimal("500.00"),
            payout_amount=Decimal("9500.00"),
        )
        so.mark_paid()
        assert so.status == "paid"

    def test_paid_to_shipped_to_warehouse(self):
        from orders.models import SupplierOrder
        so = SupplierOrder(
            status="paid",
            principal=Decimal("10000.00"),
            seller_fee=Decimal("500.00"),
            payout_amount=Decimal("9500.00"),
        )
        so.mark_shipped_to_warehouse()
        assert so.status == "shipped_to_warehouse"

    def test_shipped_to_warehouse_to_at_warehouse(self):
        from orders.models import SupplierOrder
        so = SupplierOrder(
            status="shipped_to_warehouse",
            principal=Decimal("10000.00"),
            seller_fee=Decimal("500.00"),
            payout_amount=Decimal("9500.00"),
        )
        so.mark_at_warehouse()
        assert so.status == "at_warehouse"

    def test_at_warehouse_to_inspected(self):
        from orders.models import SupplierOrder
        so = SupplierOrder(
            status="at_warehouse",
            principal=Decimal("10000.00"),
            seller_fee=Decimal("500.00"),
            payout_amount=Decimal("9500.00"),
        )
        so.mark_inspected()
        assert so.status == "inspected"

    def test_at_warehouse_to_failed_inspection(self):
        from orders.models import SupplierOrder
        so = SupplierOrder(
            status="at_warehouse",
            principal=Decimal("10000.00"),
            seller_fee=Decimal("500.00"),
            payout_amount=Decimal("9500.00"),
        )
        so.mark_failed_inspection()
        assert so.status == "failed_inspection"

    def test_inspected_to_shipped_to_buyer(self):
        from orders.models import SupplierOrder
        so = SupplierOrder(
            status="inspected",
            principal=Decimal("10000.00"),
            seller_fee=Decimal("500.00"),
            payout_amount=Decimal("9500.00"),
        )
        so.mark_shipped_to_buyer()
        assert so.status == "shipped_to_buyer"

    def test_shipped_to_buyer_to_delivered(self):
        from orders.models import SupplierOrder
        so = SupplierOrder(
            status="shipped_to_buyer",
            principal=Decimal("10000.00"),
            seller_fee=Decimal("500.00"),
            payout_amount=Decimal("9500.00"),
        )
        so.mark_delivered()
        assert so.status == "delivered"
        assert so.delivered_at is not None

    def test_delivered_to_payout_released(self):
        from orders.models import SupplierOrder
        so = SupplierOrder(
            status="delivered",
            principal=Decimal("10000.00"),
            seller_fee=Decimal("500.00"),
            payout_amount=Decimal("9500.00"),
        )
        so.release_payout()
        assert so.status == "payout_released"

    def test_cannot_skip_from_awarded_to_inspected(self):
        """Skipping states should raise TransitionNotAllowed."""
        from django_fsm import TransitionNotAllowed
        from orders.models import SupplierOrder

        so = SupplierOrder(
            status="awarded",
            principal=Decimal("10000.00"),
            seller_fee=Decimal("500.00"),
            payout_amount=Decimal("9500.00"),
        )
        with pytest.raises(TransitionNotAllowed):
            so.mark_inspected()

    def test_cannot_skip_from_paid_to_delivered(self):
        """Cannot jump from paid to delivered."""
        from django_fsm import TransitionNotAllowed
        from orders.models import SupplierOrder

        so = SupplierOrder(
            status="paid",
            principal=Decimal("10000.00"),
            seller_fee=Decimal("500.00"),
            payout_amount=Decimal("9500.00"),
        )
        with pytest.raises(TransitionNotAllowed):
            so.mark_delivered()

    def test_cancel_from_awarded(self):
        from orders.models import SupplierOrder
        so = SupplierOrder(
            status="awarded",
            principal=Decimal("10000.00"),
            seller_fee=Decimal("500.00"),
            payout_amount=Decimal("9500.00"),
        )
        so.cancel()
        assert so.status == "cancelled"

    def test_cancel_from_paid(self):
        from orders.models import SupplierOrder
        so = SupplierOrder(
            status="paid",
            principal=Decimal("10000.00"),
            seller_fee=Decimal("500.00"),
            payout_amount=Decimal("9500.00"),
        )
        so.cancel()
        assert so.status == "cancelled"
