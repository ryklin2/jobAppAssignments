"""Tests for SaleRecord and the other sales value types."""

import dataclasses
import datetime as dt
from decimal import Decimal

import pytest

from sales_analytics.models import SaleRecord, SalesStats

VALID_FIELDS = {
    "transaction_id": "T1",
    "date": dt.date(2026, 1, 5),
    "region": "West",
    "salesperson": "Ana Silva",
    "product_category": "Electronics",
    "quantity": 2,
    "unit_price": Decimal("49.99"),
    "total_amount": Decimal("99.98"),
}


def record(**overrides: object) -> SaleRecord:
    """Build a valid record, replacing the named fields."""
    return SaleRecord(**{**VALID_FIELDS, **overrides})  # type: ignore[arg-type]


def test_valid_record_is_created() -> None:
    """A record with valid fields keeps every value unchanged."""
    sale = record()
    assert sale.transaction_id == "T1"
    assert sale.date == dt.date(2026, 1, 5)
    assert sale.region == "West"
    assert sale.salesperson == "Ana Silva"
    assert sale.product_category == "Electronics"
    assert sale.quantity == 2
    assert sale.unit_price == Decimal("49.99")
    assert sale.total_amount == Decimal("99.98")


def test_record_is_immutable(sales_records: list[SaleRecord]) -> None:
    """Assigning to a field raises FrozenInstanceError."""
    sale = sales_records[0]
    with pytest.raises(dataclasses.FrozenInstanceError):
        sale.region = "East"  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        sale.total_amount = Decimal("1.00")  # type: ignore[misc]


@pytest.mark.parametrize("quantity", [0, -1])
def test_rejects_non_positive_quantity(quantity: int) -> None:
    """Parametrize quantity 0 and -1: ValueError."""
    with pytest.raises(ValueError, match="quantity"):
        record(quantity=quantity, total_amount=Decimal("49.99") * quantity)


def test_rejects_bool_quantity() -> None:
    """quantity=True raises TypeError."""
    with pytest.raises(TypeError, match="quantity"):
        record(quantity=True, total_amount=Decimal("49.99"))


def test_rejects_float_money() -> None:
    """unit_price=2.5 (a float) raises TypeError; it is never silently converted."""
    with pytest.raises(TypeError, match="unit_price"):
        record(quantity=2, unit_price=2.5, total_amount=Decimal("5.00"))
    with pytest.raises(TypeError, match="total_amount"):
        record(quantity=2, unit_price=Decimal("2.50"), total_amount=5.0)


@pytest.mark.parametrize("bad", [Decimal("NaN"), Decimal("Infinity")])
def test_rejects_non_finite_money(bad: Decimal) -> None:
    """Parametrize Decimal('NaN') and Decimal('Infinity'): ValueError."""
    with pytest.raises(ValueError, match="finite"):
        record(unit_price=bad)
    with pytest.raises(ValueError, match="finite"):
        record(total_amount=bad)


def test_rejects_total_mismatch() -> None:
    """total_amount off by more than 0.01 raises ValueError."""
    with pytest.raises(ValueError, match="total_amount"):
        record(quantity=2, unit_price=Decimal("100.00"), total_amount=Decimal("250.00"))
    # Just outside the tolerance: 2 x 100.00 = 200.00, so 200.02 is 0.02 off.
    with pytest.raises(ValueError, match="total_amount"):
        record(quantity=2, unit_price=Decimal("100.00"), total_amount=Decimal("200.02"))


def test_accepts_total_within_tolerance() -> None:
    """3 x 3.333 = 9.999 with total 10.00 is accepted (within 0.01)."""
    sale = record(
        quantity=3, unit_price=Decimal("3.333"), total_amount=Decimal("10.00")
    )
    assert sale.total_amount == Decimal("10.00")


@pytest.mark.parametrize(
    "field", ["transaction_id", "region", "salesperson", "product_category"]
)
def test_rejects_blank_text_fields(field: str) -> None:
    """Parametrize each text field set to '   ': ValueError."""
    with pytest.raises(ValueError, match=field):
        record(**{field: "   "})


def test_sales_stats_from_amounts(sales_records: list[SaleRecord]) -> None:
    """Matches the hand-computed statistics in the sales_records docstring."""
    stats = SalesStats.from_amounts(sale.total_amount for sale in sales_records)
    assert stats.count == 8
    assert stats.total == Decimal("1299.00")
    assert stats.mean == Decimal("162.375")
    assert stats.median == Decimal("174.995")
    assert stats.minimum == Decimal("25.00")
    assert stats.maximum == Decimal("350.00")
    # Compared with a tolerance rather than to the full 28-digit value, so
    # the test does not depend on how statistics.stdev rounds internally.
    assert stats.stdev is not None
    assert abs(stats.stdev - Decimal("110.3393306383280798733460532")) < Decimal(
        "0.0001"
    )


def test_sales_stats_empty_and_single_value() -> None:
    """Empty: count 0, total 0, others None. One value: stdev None, others set."""
    empty = SalesStats.from_amounts([])
    assert empty.count == 0
    assert empty.total == Decimal("0")
    assert (empty.mean, empty.median, empty.minimum, empty.maximum) == (
        None,
        None,
        None,
        None,
    )
    assert empty.stdev is None

    single = SalesStats.from_amounts([Decimal("42.50")])
    assert single.count == 1
    assert single.total == Decimal("42.50")
    assert single.mean == Decimal("42.50")
    assert single.median == Decimal("42.50")
    assert single.minimum == Decimal("42.50")
    assert single.maximum == Decimal("42.50")
    assert single.stdev is None


def test_sales_stats_accepts_a_one_shot_generator() -> None:
    """A generator is materialized first, so every field is computed from it."""
    amounts = (Decimal(value) for value in ("10.00", "20.00", "30.00"))
    stats = SalesStats.from_amounts(amounts)
    assert (stats.count, stats.total, stats.mean) == (
        3,
        Decimal("60.00"),
        Decimal("20.00"),
    )


def test_rejects_non_date_and_datetime_dates() -> None:
    """A string date, and a datetime, both raise TypeError.

    A datetime is a date subclass, so it would pass a bare isinstance check
    while comparing unequal to the plain dates every other record holds.
    """
    with pytest.raises(TypeError, match="date"):
        record(date="2026-01-05")
    with pytest.raises(TypeError, match="date"):
        record(date=dt.datetime(2026, 1, 5))


def test_rejects_non_positive_unit_price() -> None:
    """A zero unit price raises ValueError even when the total agrees."""
    with pytest.raises(ValueError, match="unit_price"):
        record(quantity=2, unit_price=Decimal("0.00"), total_amount=Decimal("0.00"))


@pytest.mark.parametrize(
    "field", ["transaction_id", "region", "salesperson", "product_category"]
)
def test_rejects_non_string_text_fields(field: str) -> None:
    """A number where text belongs raises TypeError, not a blank-value error."""
    with pytest.raises(TypeError, match=field):
        record(**{field: 42})
