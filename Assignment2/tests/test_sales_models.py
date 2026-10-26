"""Tests for SaleRecord and the other sales value types.

Skeleton: every test calls pytest.skip("TODO") until implemented.
"""

import pytest

from sales_analytics.models import SaleRecord, SalesStats  # noqa: F401


def test_valid_record_is_created() -> None:
    """A record with valid fields keeps every value unchanged."""
    pytest.skip("TODO")


def test_record_is_immutable(sales_records: object) -> None:
    """Assigning to a field raises FrozenInstanceError."""
    pytest.skip("TODO")


def test_rejects_non_positive_quantity() -> None:
    """Parametrize quantity 0 and -1: ValueError."""
    pytest.skip("TODO")


def test_rejects_bool_quantity() -> None:
    """quantity=True raises TypeError."""
    pytest.skip("TODO")


def test_rejects_float_money() -> None:
    """unit_price=2.5 (a float) raises TypeError; it is never silently converted."""
    pytest.skip("TODO")


def test_rejects_non_finite_money() -> None:
    """Parametrize Decimal('NaN') and Decimal('Infinity'): ValueError."""
    pytest.skip("TODO")


def test_rejects_total_mismatch() -> None:
    """total_amount off by more than 0.01 raises ValueError."""
    pytest.skip("TODO")


def test_accepts_total_within_tolerance() -> None:
    """3 x 3.333 = 9.999 with total 10.00 is accepted (within 0.01)."""
    pytest.skip("TODO")


def test_rejects_blank_text_fields() -> None:
    """Parametrize each text field set to '   ': ValueError."""
    pytest.skip("TODO")


def test_sales_stats_from_amounts(sales_records: object) -> None:
    """Matches the hand-computed statistics in the sales_records docstring."""
    pytest.skip("TODO")


def test_sales_stats_empty_and_single_value() -> None:
    """Empty: count 0, total 0, others None. One value: stdev None, others set."""
    pytest.skip("TODO")
