"""Tests for SalesDataLoader: parsing, validation, error policy.

Skeleton: every test calls pytest.skip("TODO") until implemented.
"""

import pytest

from sales_analytics.loader import SalesDataLoader  # noqa: F401


def test_loads_valid_file(write_csv: object) -> None:
    """A small valid CSV loads every record with correct types."""
    pytest.skip("TODO")


def test_missing_file_raises_sales_file_not_found(tmp_path: object) -> None:
    """A missing path raises SalesFileNotFoundError (also a FileNotFoundError)."""
    pytest.skip("TODO")


def test_directory_path_raises_sales_file_not_found(tmp_path: object) -> None:
    """A directory path raises SalesFileNotFoundError."""
    pytest.skip("TODO")


def test_empty_file_raises_malformed(write_csv: object) -> None:
    """A zero-byte file raises MalformedCSVError with line_number None."""
    pytest.skip("TODO")


def test_header_only_returns_empty_result(write_csv: object) -> None:
    """A header with no rows gives no records and no errors."""
    pytest.skip("TODO")


def test_missing_required_column_raises_malformed(write_csv: object) -> None:
    """The message names every missing column."""
    pytest.skip("TODO")


def test_header_spellings_are_normalized(write_csv: object) -> None:
    """camelCase, 'Transaction ID' and a UTF-8 BOM on the first header all load."""
    pytest.skip("TODO")


def test_quoted_comma_in_field_is_parsed(write_csv: object) -> None:
    """salesperson '"Lee, Dana"' parses as Lee, Dana."""
    pytest.skip("TODO")


def test_lenient_mode_reports_line_numbers(write_csv: object) -> None:
    """Bad rows are skipped; each RowError has the right physical line number."""
    pytest.skip("TODO")


def test_strict_mode_raises_on_first_bad_row(write_csv: object) -> None:
    """strict=True raises MalformedCSVError with line_number of the first bad row."""
    pytest.skip("TODO")


def test_duplicate_transaction_id_reported(write_csv: object) -> None:
    """The second occurrence is a RowError; the first is kept."""
    pytest.skip("TODO")


def test_short_and_long_rows_reported(write_csv: object) -> None:
    """Too few fields and too many fields are both RowErrors."""
    pytest.skip("TODO")


def test_non_finite_amount_reported(write_csv: object) -> None:
    """NaN and Infinity money values are RowErrors."""
    pytest.skip("TODO")


def test_invalid_dates_reported(write_csv: object) -> None:
    """2026-02-30 and 01/14/2026 are RowErrors."""
    pytest.skip("TODO")


def test_line_numbers_correct_after_multiline_quoted_field(write_csv: object) -> None:
    """A quoted field containing a newline does not shift later line numbers."""
    pytest.skip("TODO")


def test_malformed_sample_file_matches_documented_errors() -> None:
    """data/sales_malformed.csv gives 2 records and errors on lines
    3,4,5,6,7,9,10,11,12,13.
    """
    pytest.skip("TODO")


def test_sample_file_loads_cleanly() -> None:
    """data/sales_sample.csv gives 120 records and zero errors."""
    pytest.skip("TODO")
