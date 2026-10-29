"""Tests for report formatting."""

from decimal import Decimal

import pytest

from sales_analytics.analyzer import SalesAnalyzer
from sales_analytics.models import SaleRecord
from sales_analytics.report import format_currency, format_summary_report

SECTION_HEADINGS = (
    "SALES SUMMARY REPORT",
    "Statistics",
    "Revenue by Region",
    "Average Sale by Category",
    "Top Salespersons",
    "Monthly Trend",
    "Busiest Category",
)


def test_format_currency_rounds_half_up() -> None:
    """Decimal('2.675') -> '$2.68' (float rounding would give $2.67)."""
    assert format_currency(Decimal("2.675")) == "$2.68"
    # ROUND_HALF_EVEN, Decimal's default, would give $2.66 here.
    assert format_currency(Decimal("2.665")) == "$2.67"


def test_format_currency_thousands_separator() -> None:
    """Decimal('1234567.5') -> '$1,234,567.50'."""
    assert format_currency(Decimal("1234567.5")) == "$1,234,567.50"
    assert format_currency(Decimal("0")) == "$0.00"


@pytest.mark.parametrize("heading", SECTION_HEADINGS)
def test_format_summary_report_contains_every_section(
    sales_records: list[SaleRecord], heading: str
) -> None:
    """Each section heading and key figure appears in the text."""
    text = format_summary_report(
        SalesAnalyzer(sales_records).generate_summary_report(top_n=3)
    )
    assert heading in text


def test_format_summary_report_shows_the_key_figures(
    sales_records: list[SaleRecord],
) -> None:
    """The headline total, period, rankings and trend all reach the output."""
    text = format_summary_report(
        SalesAnalyzer(sales_records).generate_summary_report(top_n=3)
    )
    assert "Records analysed: 8" in text
    assert "2025-11-03 to 2026-03-30" in text
    assert "$1,299.00" in text
    assert "1. Ben" in text
    assert "$549.99" in text
    assert "2026-02" in text  # the gap-filled month
    assert "Electronics" in text


@pytest.mark.parametrize("heading", SECTION_HEADINGS)
def test_format_summary_report_handles_empty_data(heading: str) -> None:
    """A report from an empty analyzer renders without errors."""
    text = format_summary_report(SalesAnalyzer([]).generate_summary_report())
    assert heading in text
    assert "Records analysed: 0" in text
    assert "Period:           n/a" in text
    assert "$0.00" in text
    assert text.count("No sales data.") == 6
