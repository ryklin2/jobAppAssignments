"""Tests for report formatting.

Skeleton: every test calls pytest.skip("TODO") until implemented.
"""

import pytest

from sales_analytics.report import format_currency, format_summary_report  # noqa: F401


def test_format_currency_rounds_half_up() -> None:
    """Decimal('2.675') -> '$2.68' (float rounding would give $2.67)."""
    pytest.skip("TODO")


def test_format_currency_thousands_separator() -> None:
    """Decimal('1234567.5') -> '$1,234,567.50'."""
    pytest.skip("TODO")


def test_format_summary_report_contains_every_section(sales_records: object) -> None:
    """Each section heading and key figure appears in the text."""
    pytest.skip("TODO")


def test_format_summary_report_handles_empty_data() -> None:
    """A report from an empty analyzer renders without errors."""
    pytest.skip("TODO")
