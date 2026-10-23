"""
LedgerJournalService — posts balanced double-entry journals.
"""

from decimal import Decimal


def post_charge(
    order,
    charge_amount: Decimal,
    fee_amount: Decimal,
    inspection: Decimal,
    compliance: Decimal,
    shipping: Decimal,
    tax: Decimal,
) -> "LedgerJournal":
    """
    Posts a balanced journal when the buyer pays.

    DR stripe_clearing / CR funds_held_for_suppliers (principal)
    DR stripe_clearing / CR platform_fee_revenue (fee)
    DR stripe_clearing / CR inspection_revenue
    DR stripe_clearing / CR compliance_revenue
    DR stripe_clearing / CR shipping_payable
    DR stripe_clearing / CR sales_tax_payable

    Each call creates one LedgerJournal + balanced LedgerEntry rows.
    Asserts sum(debit) == sum(credit) before saving.
    """
    from payments.models import LedgerEntry, LedgerJournal

    principal = charge_amount - fee_amount - inspection - compliance - shipping - tax

    entries_data = []

    if principal > 0:
        entries_data.append(
            (LedgerEntry.Account.STRIPE_CLEARING, principal, Decimal("0.00"))
        )
        entries_data.append(
            (LedgerEntry.Account.FUNDS_HELD_FOR_SUPPLIERS, Decimal("0.00"), principal)
        )

    if fee_amount > 0:
        entries_data.append(
            (LedgerEntry.Account.STRIPE_CLEARING, fee_amount, Decimal("0.00"))
        )
        entries_data.append(
            (LedgerEntry.Account.PLATFORM_FEE_REVENUE, Decimal("0.00"), fee_amount)
        )

    if inspection > 0:
        entries_data.append(
            (LedgerEntry.Account.STRIPE_CLEARING, inspection, Decimal("0.00"))
        )
        entries_data.append(
            (LedgerEntry.Account.INSPECTION_REVENUE, Decimal("0.00"), inspection)
        )

    if compliance > 0:
        entries_data.append(
            (LedgerEntry.Account.STRIPE_CLEARING, compliance, Decimal("0.00"))
        )
        entries_data.append(
            (LedgerEntry.Account.COMPLIANCE_REVENUE, Decimal("0.00"), compliance)
        )

    if shipping > 0:
        entries_data.append(
            (LedgerEntry.Account.STRIPE_CLEARING, shipping, Decimal("0.00"))
        )
        entries_data.append(
            (LedgerEntry.Account.SHIPPING_PAYABLE, Decimal("0.00"), shipping)
        )

    if tax > 0:
        entries_data.append(
            (LedgerEntry.Account.STRIPE_CLEARING, tax, Decimal("0.00"))
        )
        entries_data.append(
            (LedgerEntry.Account.SALES_TAX_PAYABLE, Decimal("0.00"), tax)
        )

    total_debit = sum(d for _, d, _ in entries_data)
    total_credit = sum(c for _, _, c in entries_data)
    assert total_debit == total_credit, (
        f"Ledger imbalance: debit={total_debit} credit={total_credit}"
    )

    journal = LedgerJournal.objects.create(
        kind=LedgerJournal.Kind.CHARGE,
        order=order,
        memo=f"Buyer payment for order {order.number}",
    )

    LedgerEntry.objects.bulk_create([
        LedgerEntry(journal=journal, account=account, debit=debit, credit=credit)
        for account, debit, credit in entries_data
    ])

    return journal


def post_payout(supplier_order, payout_amount: Decimal) -> "LedgerJournal":
    """
    DR funds_held_for_suppliers / CR stripe_clearing (payout transfer)
    """
    from payments.models import LedgerEntry, LedgerJournal

    entries_data = [
        (LedgerEntry.Account.FUNDS_HELD_FOR_SUPPLIERS, payout_amount, Decimal("0.00")),
        (LedgerEntry.Account.STRIPE_CLEARING, Decimal("0.00"), payout_amount),
    ]

    total_debit = sum(d for _, d, _ in entries_data)
    total_credit = sum(c for _, _, c in entries_data)
    assert total_debit == total_credit, (
        f"Ledger imbalance: debit={total_debit} credit={total_credit}"
    )

    journal = LedgerJournal.objects.create(
        kind=LedgerJournal.Kind.PAYOUT,
        supplier_order=supplier_order,
        order=supplier_order.order,
        memo=f"Payout for supplier order {supplier_order.anonymous_supplier_id}",
    )

    LedgerEntry.objects.bulk_create([
        LedgerEntry(journal=journal, account=account, debit=debit, credit=credit)
        for account, debit, credit in entries_data
    ])

    return journal
