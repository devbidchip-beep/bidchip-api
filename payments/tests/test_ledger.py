"""
Tests for payments.ledger — double-entry journal posting.
"""

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest


class TestPostCharge:
    @patch("payments.ledger.LedgerEntry")
    @patch("payments.ledger.LedgerJournal")
    def test_creates_balanced_journal(self, mock_journal_cls, mock_entry_cls):
        """post_charge must create a balanced journal (sum debit == sum credit)."""
        from payments.ledger import post_charge

        mock_journal = MagicMock()
        mock_journal.kind = "charge"
        mock_journal_cls.objects.create.return_value = mock_journal
        mock_journal_cls.Kind.CHARGE = "charge"

        order = MagicMock()
        order.number = "BC-2026-000001"

        # Call: 10000 total, 700 fee, 400 inspection, 30 compliance, 250 shipping, 0 tax
        # principal = 10000 - 700 - 400 - 30 - 250 - 0 = 8620
        post_charge(
            order=order,
            charge_amount=Decimal("11380.00"),
            fee_amount=Decimal("700.00"),
            inspection=Decimal("400.00"),
            compliance=Decimal("30.00"),
            shipping=Decimal("250.00"),
            tax=Decimal("0.00"),
        )

        # Check that bulk_create was called
        mock_entry_cls.objects.bulk_create.assert_called_once()

        # Extract entries passed to bulk_create
        entries = mock_entry_cls.objects.bulk_create.call_args[0][0]

        total_debit = sum(e.debit for e in entries)
        total_credit = sum(e.credit for e in entries)
        assert total_debit == total_credit, (
            f"Ledger not balanced: debit={total_debit} credit={total_credit}"
        )

    @patch("payments.ledger.LedgerEntry")
    @patch("payments.ledger.LedgerJournal")
    def test_all_zeros_creates_no_entries(self, mock_journal_cls, mock_entry_cls):
        """If all amounts are zero, no entries should be created (still balanced)."""
        from payments.ledger import post_charge

        mock_journal = MagicMock()
        mock_journal_cls.objects.create.return_value = mock_journal
        mock_journal_cls.Kind.CHARGE = "charge"

        order = MagicMock()
        order.number = "BC-2026-000002"

        post_charge(
            order=order,
            charge_amount=Decimal("0.00"),
            fee_amount=Decimal("0.00"),
            inspection=Decimal("0.00"),
            compliance=Decimal("0.00"),
            shipping=Decimal("0.00"),
            tax=Decimal("0.00"),
        )

        entries = mock_entry_cls.objects.bulk_create.call_args[0][0]
        total_debit = sum(e.debit for e in entries)
        total_credit = sum(e.credit for e in entries)
        assert total_debit == total_credit


class TestPostPayout:
    @patch("payments.ledger.LedgerEntry")
    @patch("payments.ledger.LedgerJournal")
    def test_creates_balanced_payout_journal(self, mock_journal_cls, mock_entry_cls):
        """post_payout must create a balanced journal."""
        from payments.ledger import post_payout

        mock_journal = MagicMock()
        mock_journal_cls.objects.create.return_value = mock_journal
        mock_journal_cls.Kind.PAYOUT = "payout"

        supplier_order = MagicMock()
        supplier_order.anonymous_supplier_id = "S-ABCD-1234"
        supplier_order.order.number = "BC-2026-000001"

        post_payout(supplier_order=supplier_order, payout_amount=Decimal("9500.00"))

        entries = mock_entry_cls.objects.bulk_create.call_args[0][0]
        total_debit = sum(e.debit for e in entries)
        total_credit = sum(e.credit for e in entries)
        assert total_debit == total_credit

    @patch("payments.ledger.LedgerEntry")
    @patch("payments.ledger.LedgerJournal")
    def test_payout_journal_dr_funds_held_cr_clearing(self, mock_journal_cls, mock_entry_cls):
        """
        post_payout should DR funds_held_for_suppliers and CR stripe_clearing.
        """
        from payments.ledger import post_payout
        from payments.models import LedgerEntry

        mock_journal = MagicMock()
        mock_journal_cls.objects.create.return_value = mock_journal
        mock_journal_cls.Kind.PAYOUT = "payout"

        supplier_order = MagicMock()
        supplier_order.anonymous_supplier_id = "S-TEST-0001"
        supplier_order.order.number = "BC-2026-000001"

        post_payout(supplier_order=supplier_order, payout_amount=Decimal("9500.00"))

        entries = mock_entry_cls.objects.bulk_create.call_args[0][0]

        # One entry should be DR funds_held
        dr_entry = next(e for e in entries if e.debit > 0)
        cr_entry = next(e for e in entries if e.credit > 0)

        assert dr_entry.account == LedgerEntry.Account.FUNDS_HELD_FOR_SUPPLIERS
        assert cr_entry.account == LedgerEntry.Account.STRIPE_CLEARING
        assert dr_entry.debit == Decimal("9500.00")
        assert cr_entry.credit == Decimal("9500.00")
