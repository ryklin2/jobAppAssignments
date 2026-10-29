"""Tests for SalesAnalyzer against hand-computed values."""

import datetime as dt
from decimal import Decimal

import pytest

from sales_analytics.analyzer import SalesAnalyzer
from sales_analytics.models import SaleRecord


def test_accepts_generator_input(sales_records: list[SaleRecord]) -> None:
    """An analyzer built from a generator gives the same answers on repeated calls."""
    analyzer = SalesAnalyzer(sale for sale in sales_records)
    first = analyzer.get_total_sales_by_region()
    # A generator stored unmaterialized would be exhausted by now, so the
    # second call would see an empty collection.
    assert analyzer.get_total_sales_by_region() == first
    assert len(analyzer) == 8


def test_rejects_non_record_elements() -> None:
    """A non-SaleRecord element raises TypeError at construction."""
    with pytest.raises(TypeError, match="SaleRecord"):
        SalesAnalyzer(["not a record"])  # type: ignore[list-item]


def test_total_sales_by_region(sales_records: list[SaleRecord]) -> None:
    """West 600.00, East 450.01, North 248.99, in that order."""
    totals = SalesAnalyzer(sales_records).get_total_sales_by_region()
    assert list(totals) == ["West", "East", "North"]
    assert totals == {
        "West": Decimal("600.00"),
        "East": Decimal("450.01"),
        "North": Decimal("248.99"),
    }


def test_average_sale_by_category(sales_records: list[SaleRecord]) -> None:
    """Electronics 156.25, Furniture 300.00, Office 37.00."""
    averages = SalesAnalyzer(sales_records).get_average_sale_by_category()
    assert list(averages) == ["Electronics", "Furniture", "Office"]
    assert averages == {
        "Electronics": Decimal("156.25"),
        "Furniture": Decimal("300.00"),
        "Office": Decimal("37.00"),
    }


def test_top_salespersons_orders_by_revenue(sales_records: list[SaleRecord]) -> None:
    """get_top_salespersons(2) == [('Ben', 549.99), ('Cara', 400.00)]."""
    assert SalesAnalyzer(sales_records).get_top_salespersons(2) == [
        ("Ben", Decimal("549.99")),
        ("Cara", Decimal("400.00")),
    ]


def test_top_salespersons_breaks_ties_by_name() -> None:
    """Two salespersons with equal revenue are ordered by name."""
    records = [
        SaleRecord(
            transaction_id=f"T{index}",
            date=dt.date(2026, 1, 1 + index),
            region="West",
            salesperson=name,
            product_category="Electronics",
            quantity=1,
            unit_price=Decimal("100.00"),
            total_amount=Decimal("100.00"),
        )
        # Zoe first in the input, so a stable sort alone would keep her first.
        for index, name in enumerate(["Zoe", "Amy"])
    ]
    assert SalesAnalyzer(records).get_top_salespersons(2) == [
        ("Amy", Decimal("100.00")),
        ("Zoe", Decimal("100.00")),
    ]


def test_top_salespersons_n_larger_than_population(
    sales_records: list[SaleRecord],
) -> None:
    """n=10 returns all four salespersons."""
    top = SalesAnalyzer(sales_records).get_top_salespersons(10)
    assert [name for name, _ in top] == ["Ben", "Cara", "Ana", "Dev"]


@pytest.mark.parametrize(
    ("n", "expected"),
    [(0, ValueError), (-1, ValueError), (True, TypeError), (1.5, TypeError)],
)
def test_top_salespersons_rejects_invalid_n(
    sales_records: list[SaleRecord], n: object, expected: type[Exception]
) -> None:
    """Parametrize 0 and -1 (ValueError), True and 1.5 (TypeError)."""
    with pytest.raises(expected):
        SalesAnalyzer(sales_records).get_top_salespersons(n)  # type: ignore[arg-type]


def test_monthly_trend_fills_gaps_across_year_boundary(
    sales_records: list[SaleRecord],
) -> None:
    """Five months 2025-11 .. 2026-03 with 2026-02 == 0, chronological."""
    assert SalesAnalyzer(sales_records).get_monthly_sales_trend() == [
        ("2025-11", Decimal("550.00")),
        ("2025-12", Decimal("150.00")),
        ("2026-01", Decimal("224.99")),
        ("2026-02", Decimal("0")),
        ("2026-03", Decimal("374.01")),
    ]


def test_monthly_trend_without_gap_filling(sales_records: list[SaleRecord]) -> None:
    """fill_gaps=False omits 2026-02."""
    trend = SalesAnalyzer(sales_records).get_monthly_sales_trend(fill_gaps=False)
    assert [month for month, _ in trend] == [
        "2025-11",
        "2025-12",
        "2026-01",
        "2026-03",
    ]


def test_monthly_trend_keeps_the_same_month_of_different_years_apart() -> None:
    """Grouping on month alone would merge January 2025 with January 2026."""
    records = [
        SaleRecord(
            transaction_id=f"T{year}",
            date=dt.date(year, 1, 15),
            region="West",
            salesperson="Ana",
            product_category="Electronics",
            quantity=1,
            unit_price=Decimal("100.00"),
            total_amount=Decimal("100.00"),
        )
        for year in (2025, 2026)
    ]
    trend = SalesAnalyzer(records).get_monthly_sales_trend()
    assert len(trend) == 13  # 2025-01 .. 2026-01 inclusive
    assert trend[0] == ("2025-01", Decimal("100.00"))
    assert trend[-1] == ("2026-01", Decimal("100.00"))
    assert all(total == Decimal("0") for _, total in trend[1:-1])


def test_date_range_is_inclusive(sales_records: list[SaleRecord]) -> None:
    """2025-12-05 .. 2026-01-21 returns T3, T4, T5 (both ends included)."""
    matches = SalesAnalyzer(sales_records).get_sales_by_date_range(
        dt.date(2025, 12, 5), dt.date(2026, 1, 21)
    )
    assert [sale.transaction_id for sale in matches] == ["T3", "T4", "T5"]


def test_date_range_rejects_start_after_end(sales_records: list[SaleRecord]) -> None:
    """start > end raises ValueError."""
    with pytest.raises(ValueError, match="after"):
        SalesAnalyzer(sales_records).get_sales_by_date_range(
            dt.date(2026, 3, 1), dt.date(2026, 1, 1)
        )


def test_filter_by_composes(sales_records: list[SaleRecord]) -> None:
    """filter_by(regions={'West'}).get_total_sales_by_region() == {'West': 600.00}."""
    analyzer = SalesAnalyzer(sales_records)
    assert analyzer.filter_by(regions={"West"}).get_total_sales_by_region() == {
        "West": Decimal("600.00")
    }
    # Several criteria at once: West AND Electronics AND the first two months.
    narrowed = analyzer.filter_by(
        regions={"West"},
        categories={"Electronics"},
        start=dt.date(2025, 11, 1),
        end=dt.date(2025, 12, 31),
    )
    assert [sale.transaction_id for sale in narrowed.records] == ["T1", "T3"]


def test_filter_by_returns_new_analyzer(sales_records: list[SaleRecord]) -> None:
    """The original analyzer still has all eight records afterwards."""
    analyzer = SalesAnalyzer(sales_records)
    filtered = analyzer.filter_by(regions={"West"})
    assert filtered is not analyzer
    assert len(filtered) == 3
    assert len(analyzer) == 8


def test_filter_by_rejects_start_after_end(sales_records: list[SaleRecord]) -> None:
    """An inverted range is a mistake, not an empty result."""
    with pytest.raises(ValueError, match="after"):
        SalesAnalyzer(sales_records).filter_by(
            start=dt.date(2026, 3, 1), end=dt.date(2026, 1, 1)
        )


def test_group_totals_by_two_dimensions(sales_records: list[SaleRecord]) -> None:
    """Matches the region x category table in the fixture docstring."""
    assert SalesAnalyzer(sales_records).group_totals("region", "product_category") == {
        ("East", "Electronics"): Decimal("75.01"),
        ("East", "Furniture"): Decimal("350.00"),
        ("East", "Office"): Decimal("25.00"),
        ("North", "Electronics"): Decimal("199.99"),
        ("North", "Office"): Decimal("49.00"),
        ("West", "Electronics"): Decimal("350.00"),
        ("West", "Furniture"): Decimal("250.00"),
    }


def test_group_totals_by_one_dimension_still_keys_on_a_tuple(
    sales_records: list[SaleRecord],
) -> None:
    """One dimension gives 1-tuple keys, so the key shape never varies."""
    assert SalesAnalyzer(sales_records).group_totals("region") == {
        ("East",): Decimal("450.01"),
        ("North",): Decimal("248.99"),
        ("West",): Decimal("600.00"),
    }


@pytest.mark.parametrize("dimensions", [(), ("quantity",), ("region", "unit_price")])
def test_group_totals_rejects_bad_dimensions(
    sales_records: list[SaleRecord], dimensions: tuple[str, ...]
) -> None:
    """No dimension, or an unknown one, raises ValueError."""
    with pytest.raises(ValueError):
        SalesAnalyzer(sales_records).group_totals(*dimensions)


def test_statistics_match_hand_computed_values(
    sales_records: list[SaleRecord],
) -> None:
    """count 8, total 1299.00, mean 162.375, median 174.995, min 25.00, max 350.00."""
    stats = SalesAnalyzer(sales_records).get_statistics()
    assert stats.count == 8
    assert stats.total == Decimal("1299.00")
    assert stats.mean == Decimal("162.375")
    assert stats.median == Decimal("174.995")
    assert stats.minimum == Decimal("25.00")
    assert stats.maximum == Decimal("350.00")


def test_empty_analyzer_returns_empty_results() -> None:
    """Every method on SalesAnalyzer([]) returns empty results or None fields, never
    raises.
    """
    analyzer = SalesAnalyzer([])
    assert len(analyzer) == 0
    assert analyzer.records == ()
    assert analyzer.get_total_sales_by_region() == {}
    assert analyzer.get_average_sale_by_category() == {}
    assert analyzer.get_top_salespersons(3) == []
    assert analyzer.get_monthly_sales_trend() == []
    assert analyzer.get_monthly_sales_trend(fill_gaps=False) == []
    assert analyzer.group_totals("region", "product_category") == {}
    assert (
        analyzer.get_sales_by_date_range(dt.date(2026, 1, 1), dt.date(2026, 12, 31))
        == []
    )
    assert len(analyzer.filter_by(regions={"West"})) == 0

    stats = analyzer.get_statistics()
    assert stats.count == 0
    assert stats.total == Decimal("0")
    assert stats.mean is None

    report = analyzer.generate_summary_report()
    assert report.record_count == 0
    assert report.period_start is None
    assert report.period_end is None
    assert report.busiest_category is None
    assert report.total_by_region == ()
    assert report.monthly_trend == ()


def test_summary_report_contents(sales_records: list[SaleRecord]) -> None:
    """Report fields match the hand-computed values; busiest category Electronics."""
    report = SalesAnalyzer(sales_records).generate_summary_report(top_n=3)

    assert report.record_count == 8
    assert report.period_start == dt.date(2025, 11, 3)
    assert report.period_end == dt.date(2026, 3, 30)
    assert report.stats.total == Decimal("1299.00")
    assert report.total_by_region == (
        ("West", Decimal("600.00")),
        ("East", Decimal("450.01")),
        ("North", Decimal("248.99")),
    )
    assert report.average_by_category == (
        ("Electronics", Decimal("156.25")),
        ("Furniture", Decimal("300.00")),
        ("Office", Decimal("37.00")),
    )
    assert report.top_salespersons == (
        ("Ben", Decimal("549.99")),
        ("Cara", Decimal("400.00")),
        ("Ana", Decimal("225.00")),
    )
    assert report.monthly_trend[0] == ("2025-11", Decimal("550.00"))
    assert len(report.monthly_trend) == 5
    # Electronics has 4 transactions; Furniture and Office have 2 each.
    assert report.busiest_category == "Electronics"


def test_repr_names_the_record_count(sales_records: list[SaleRecord]) -> None:
    """repr() is for debugging, so it says how much data is held."""
    assert repr(SalesAnalyzer(sales_records)) == "SalesAnalyzer(8 records)"
