"""
Money field definitions and Decimal utilities for BidChip.

IMPORTANT: Never use FloatField for money. Always use DecimalField with
max_digits=14 and decimal_places=2, or the MoneyField shortcut defined here.
"""

from __future__ import annotations

import decimal
from decimal import ROUND_HALF_UP, Decimal

from django.db import models

# ---------------------------------------------------------------------------
# Standard monetary precision
# ---------------------------------------------------------------------------

MONEY_MAX_DIGITS = 14
MONEY_DECIMAL_PLACES = 2
MONEY_QUANTIZE = Decimal("0.01")  # two decimal places

# ---------------------------------------------------------------------------
# MoneyField
# ---------------------------------------------------------------------------


class MoneyField(models.DecimalField):
    """
    Convenience DecimalField for monetary amounts.

    # Never use FloatField for money

    Usage:
        price = MoneyField()
        price = MoneyField(null=True, blank=True, default=None)
        price = MoneyField(default=Decimal("0.00"))
    """

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("max_digits", MONEY_MAX_DIGITS)
        kwargs.setdefault("decimal_places", MONEY_DECIMAL_PLACES)
        super().__init__(*args, **kwargs)

    def deconstruct(self):
        name, path, args, kwargs = super().deconstruct()
        # Remove defaults so migrations stay clean
        if kwargs.get("max_digits") == MONEY_MAX_DIGITS:
            del kwargs["max_digits"]
        if kwargs.get("decimal_places") == MONEY_DECIMAL_PLACES:
            del kwargs["decimal_places"]
        return name, path, args, kwargs


# ---------------------------------------------------------------------------
# Decimal utilities
# ---------------------------------------------------------------------------


def to_money(value) -> Decimal:
    """
    Convert any numeric value to a Decimal rounded to 2 decimal places using
    ROUND_HALF_UP.

    Raises
    ------
    decimal.InvalidOperation
        If `value` cannot be converted to Decimal (e.g. NaN, ±Inf).
    TypeError
        If `value` is a float (use str(value) or pass a Decimal/int/str).
    """
    if isinstance(value, float):
        raise TypeError(
            "Never pass a float to to_money(). "
            "Convert to str or Decimal first to avoid floating-point errors. "
            # Never use FloatField for money
        )
    d = Decimal(str(value)) if not isinstance(value, Decimal) else value
    return d.quantize(MONEY_QUANTIZE, rounding=ROUND_HALF_UP)


def add_money(*values) -> Decimal:
    """Sum multiple money values, returning a 2dp Decimal."""
    return to_money(sum(Decimal(str(v)) for v in values))


def multiply_money(amount, factor) -> Decimal:
    """
    Multiply a monetary amount by a factor (e.g. tax rate, quantity).
    Factor may be a Decimal, int, or str — not float.
    """
    if isinstance(factor, float):
        raise TypeError(
            "Never pass a float to multiply_money(). "
            # Never use FloatField for money
        )
    return to_money(Decimal(str(amount)) * Decimal(str(factor)))


def split_money(total, n: int) -> list[Decimal]:
    """
    Split `total` into `n` parts that sum exactly to `total`.
    The remainder from rounding is added to the last part.

    Example: split_money(Decimal("10.00"), 3) → [3.33, 3.33, 3.34]
    """
    if n <= 0:
        raise ValueError("n must be a positive integer")
    base = to_money(Decimal(str(total)) / n)
    parts = [base] * n
    diff = to_money(total) - add_money(*parts)
    parts[-1] = to_money(parts[-1] + diff)
    return parts


def format_money(amount, currency: str = "USD") -> str:
    """Return a human-readable money string, e.g. 'USD 1,234.56'."""
    return f"{currency} {to_money(amount):,.2f}"
