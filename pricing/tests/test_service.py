"""
Tests for pricing.service — fee computation.
"""

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from pricing.service import (
    SURCHARGE_BANNED_STATES,
    OrderPricing,
    compute_marginal_fee,
    price_order,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_schedule(brackets_data):
    """
    Create a mock FeeSchedule with the given bracket data.
    brackets_data: list of (lower_bound, upper_bound, rate)
    """
    schedule = MagicMock()
    schedule.id = "test-schedule-id"
    schedule.min_fee = None

    brackets = []
    for lower, upper, rate in brackets_data:
        b = MagicMock()
        b.lower_bound = Decimal(str(lower))
        b.upper_bound = Decimal(str(upper)) if upper is not None else None
        b.rate = Decimal(str(rate))
        brackets.append(b)

    schedule.brackets.order_by.return_value = brackets
    return schedule


def _make_award(unit_price, qty, supplier_company=None, compliance_status="clear"):
    """Create a mock Award object."""
    award = MagicMock()
    award.unit_price = Decimal(str(unit_price))
    award.quantity_awarded = qty

    if supplier_company is None:
        supplier_company = MagicMock()
        supplier_company.id = "supplier-1"

    award.bid.supplier_company = supplier_company

    line = MagicMock()
    line.compliance_status = compliance_status
    award.line = line

    return award


# ---------------------------------------------------------------------------
# compute_marginal_fee
# ---------------------------------------------------------------------------

class TestComputeMarginalFee:
    def test_standard_example(self):
        """$50,000 with brackets [0→7%, 25k→6%, 100k→5%] = $3,250"""
        schedule = _make_schedule([
            (0, 25000, "0.0700"),
            (25000, 100000, "0.0600"),
            (100000, None, "0.0500"),
        ])
        result = compute_marginal_fee(Decimal("50000.00"), schedule)
        # 25000 * 0.07 = 1750, 25000 * 0.06 = 1500 → 3250
        assert result == Decimal("3250.00")

    def test_amount_in_first_bracket_only(self):
        """$10,000 stays entirely in the 0→7% bracket = $700"""
        schedule = _make_schedule([
            (0, 25000, "0.0700"),
            (25000, 100000, "0.0600"),
        ])
        result = compute_marginal_fee(Decimal("10000.00"), schedule)
        assert result == Decimal("700.00")

    def test_amount_spanning_all_brackets(self):
        """$200,000 with 3 brackets"""
        schedule = _make_schedule([
            (0, 25000, "0.0700"),
            (25000, 100000, "0.0600"),
            (100000, None, "0.0500"),
        ])
        # 25000*0.07 + 75000*0.06 + 100000*0.05 = 1750 + 4500 + 5000 = 11250
        result = compute_marginal_fee(Decimal("200000.00"), schedule)
        assert result == Decimal("11250.00")

    def test_empty_brackets_returns_zero(self):
        schedule = _make_schedule([])
        result = compute_marginal_fee(Decimal("50000.00"), schedule)
        assert result == Decimal("0.00")

    def test_min_fee_applied(self):
        """If computed fee is less than min_fee, min_fee is returned."""
        schedule = _make_schedule([(0, None, "0.0100")])
        schedule.min_fee = Decimal("500.00")
        # 1000 * 0.01 = 10 < 500 → return 500
        result = compute_marginal_fee(Decimal("1000.00"), schedule)
        assert result == Decimal("500.00")

    def test_no_float_used(self):
        """Ensure we only get Decimal results (never float)."""
        schedule = _make_schedule([(0, None, "0.0700")])
        result = compute_marginal_fee(Decimal("50000.00"), schedule)
        assert isinstance(result, Decimal)


# ---------------------------------------------------------------------------
# price_order
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_schedule():
    """Standard buyer schedule: 0→7%, 25k→6%"""
    return _make_schedule([
        (0, 25000, "0.0700"),
        (25000, None, "0.0600"),
    ])


@pytest.fixture
def mock_seller_schedule():
    """Seller schedule: flat 5%"""
    return _make_schedule([(0, None, "0.0500")])


class TestPriceOrder:
    @patch("pricing.service.CompanyVolume")
    @patch("pricing.service.OEMEMSLink")
    @patch("pricing.service.get_active_schedule")
    @patch("pricing.service._get_platform_setting")
    def test_grand_total_correct(
        self, mock_setting, mock_get_schedule, mock_oem_link, mock_company_vol,
        mock_schedule, mock_seller_schedule
    ):
        """price_order returns correct grand_total for a simple award."""
        # Setup
        mock_setting.return_value = None  # Use defaults
        mock_get_schedule.side_effect = lambda kind, side, company=None: (
            mock_schedule if side == "buyer" else mock_seller_schedule
        )
        mock_company_vol.objects.filter.return_value.order_by.return_value.first.return_value = None
        mock_oem_link.objects.filter.return_value.first.return_value = None

        buyer_company = MagicMock()
        buyer_company.id = "buyer-1"

        awards = [_make_award("100.00", 100)]  # 10,000 principal

        result = price_order(
            awards=awards,
            buyer_company=buyer_company,
            shipping_estimate=Decimal("250.00"),
            payment_method="card",
            card_funding="debit",
        )

        assert isinstance(result, OrderPricing)
        assert result.principal == Decimal("10000.00")
        # buyer_fee: 10000 * 0.07 = 700
        assert result.buyer_fee == Decimal("700.00")
        # seller_fee: 10000 * 0.05 = 500
        assert result.seller_fee == Decimal("500.00")
        # grand_total = principal + buyer_fee + inspection + compliance + shipping + oem + tax + surcharge
        # With default settings: inspection = 400, compliance = 0
        expected = (
            Decimal("10000.00")  # principal
            + Decimal("700.00")  # buyer_fee
            + Decimal("400.00")  # inspection_fee (default 400 * 1 supplier)
            + Decimal("0.00")    # compliance_fee
            + Decimal("250.00")  # shipping
            + Decimal("0.00")    # oem_uplift
            + Decimal("0.00")    # tax
            + Decimal("0.00")    # card_surcharge (debit)
        )
        assert result.grand_total == expected

    @patch("pricing.service.CompanyVolume")
    @patch("pricing.service.OEMEMSLink")
    @patch("pricing.service.get_active_schedule")
    @patch("pricing.service._get_platform_setting")
    def test_volume_discount_reduces_fee(
        self, mock_setting, mock_get_schedule, mock_oem_link, mock_company_vol,
        mock_schedule, mock_seller_schedule
    ):
        """Volume discount points reduce buyer fee."""
        mock_setting.return_value = None
        mock_get_schedule.return_value = mock_schedule

        # Buyer has 0.5 point discount
        vol = MagicMock()
        vol.discount_points = Decimal("0.0050")
        mock_company_vol.objects.filter.return_value.order_by.return_value.first.return_value = vol
        mock_oem_link.objects.filter.return_value.first.return_value = None

        buyer_company = MagicMock()
        buyer_company.id = "buyer-1"
        awards = [_make_award("100.00", 100)]  # 10,000 principal

        result = price_order(
            awards=awards,
            buyer_company=buyer_company,
            shipping_estimate=Decimal("0.00"),
        )

        # buyer_fee without discount: 10000 * 0.07 = 700
        # discount: 10000 * 0.005 = 50
        # buyer_fee with discount: 700 - 50 = 650
        assert result.buyer_fee == Decimal("650.00")

    @patch("pricing.service.CompanyVolume")
    @patch("pricing.service.OEMEMSLink")
    @patch("pricing.service.get_active_schedule")
    @patch("pricing.service._get_platform_setting")
    def test_card_surcharge_applied_for_credit(
        self, mock_setting, mock_get_schedule, mock_oem_link, mock_company_vol,
        mock_schedule, mock_seller_schedule
    ):
        """Card surcharge is applied for credit cards."""
        def setting_side_effect(key, default=None):
            if key == "card.surcharge_rate":
                return "0.0300"
            return default

        mock_setting.side_effect = setting_side_effect
        mock_get_schedule.return_value = mock_schedule
        mock_company_vol.objects.filter.return_value.order_by.return_value.first.return_value = None
        mock_oem_link.objects.filter.return_value.first.return_value = None

        buyer_company = MagicMock()
        buyer_company.id = "buyer-1"
        awards = [_make_award("100.00", 100)]  # 10,000 principal

        result = price_order(
            awards=awards,
            buyer_company=buyer_company,
            shipping_estimate=Decimal("0.00"),
            payment_method="card",
            card_funding="credit",
            billing_state="TX",  # not banned
        )

        assert result.card_surcharge_rate == Decimal("0.0300")
        assert result.card_surcharge > Decimal("0.00")

    @patch("pricing.service.CompanyVolume")
    @patch("pricing.service.OEMEMSLink")
    @patch("pricing.service.get_active_schedule")
    @patch("pricing.service._get_platform_setting")
    def test_card_surcharge_zero_for_debit(
        self, mock_setting, mock_get_schedule, mock_oem_link, mock_company_vol,
        mock_schedule, mock_seller_schedule
    ):
        """No surcharge for debit cards."""
        mock_setting.return_value = "0.0300"
        mock_get_schedule.return_value = mock_schedule
        mock_company_vol.objects.filter.return_value.order_by.return_value.first.return_value = None
        mock_oem_link.objects.filter.return_value.first.return_value = None

        buyer_company = MagicMock()
        buyer_company.id = "buyer-1"
        awards = [_make_award("100.00", 100)]

        result = price_order(
            awards=awards,
            buyer_company=buyer_company,
            shipping_estimate=Decimal("0.00"),
            payment_method="card",
            card_funding="debit",
        )

        assert result.card_surcharge == Decimal("0.00")
        assert result.card_surcharge_rate == Decimal("0.00")

    @patch("pricing.service.CompanyVolume")
    @patch("pricing.service.OEMEMSLink")
    @patch("pricing.service.get_active_schedule")
    @patch("pricing.service._get_platform_setting")
    def test_card_surcharge_zero_for_banned_state(
        self, mock_setting, mock_get_schedule, mock_oem_link, mock_company_vol,
        mock_schedule, mock_seller_schedule
    ):
        """No surcharge for credit cards when billing state bans surcharges (CT)."""
        def setting_side_effect(key, default=None):
            if key == "card.surcharge_rate":
                return "0.0300"
            return default

        mock_setting.side_effect = setting_side_effect
        mock_get_schedule.return_value = mock_schedule
        mock_company_vol.objects.filter.return_value.order_by.return_value.first.return_value = None
        mock_oem_link.objects.filter.return_value.first.return_value = None

        buyer_company = MagicMock()
        buyer_company.id = "buyer-1"
        awards = [_make_award("100.00", 100)]

        result = price_order(
            awards=awards,
            buyer_company=buyer_company,
            shipping_estimate=Decimal("0.00"),
            payment_method="card",
            card_funding="credit",
            billing_state="CT",  # banned state
        )

        assert result.card_surcharge == Decimal("0.00")

    def test_banned_states_includes_ct(self):
        assert "CT" in SURCHARGE_BANNED_STATES
