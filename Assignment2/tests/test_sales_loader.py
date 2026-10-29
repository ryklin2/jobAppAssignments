"""Tests for SalesDataLoader: parsing, validation, error policy."""

import datetime as dt
from collections.abc import Callable
from decimal import Decimal
from pathlib import Path

import pytest

from sales_analytics.exceptions import (
    MalformedCSVError,
    SalesFileNotFoundError,
)
from sales_analytics.loader import SalesDataLoader

DATA_DIR = Path(__file__).resolve().parents[1] / "data"

HEADER = (
    "transaction_id,date,region,salesperson,product_category,"
    "quantity,unit_price,total_amount\n"
)

WriteCsv = Callable[..., Path]


def csv_text(*rows: str) -> str:
    """Join ``rows`` under the canonical header, one per line."""
    return HEADER + "".join(f"{row}\n" for row in rows)


def test_loads_valid_file(write_csv: WriteCsv) -> None:
    """A small valid CSV loads every record with correct types."""
    path = write_csv(
        csv_text(
            "T1,2026-01-05,West,Ana Silva,Electronics,2,49.99,99.98",
            "T2,2026-01-06,East,Ben Ortiz,Furniture,1,350.00,350.00",
        )
    )
    result = SalesDataLoader().load(path)

    assert not result.has_errors
    assert [sale.transaction_id for sale in result.records] == ["T1", "T2"]
    first = result.records[0]
    assert first.date == dt.date(2026, 1, 5)
    assert first.quantity == 2
    assert isinstance(first.quantity, int)
    assert first.unit_price == Decimal("49.99")
    assert isinstance(first.unit_price, Decimal)
    assert first.total_amount == Decimal("99.98")


def test_missing_file_raises_sales_file_not_found(tmp_path: Path) -> None:
    """A missing path raises SalesFileNotFoundError (also a FileNotFoundError)."""
    with pytest.raises(SalesFileNotFoundError) as caught:
        SalesDataLoader().load(tmp_path / "absent.csv")
    assert isinstance(caught.value, FileNotFoundError)


def test_directory_path_raises_sales_file_not_found(tmp_path: Path) -> None:
    """A directory path raises SalesFileNotFoundError."""
    with pytest.raises(SalesFileNotFoundError):
        SalesDataLoader().load(tmp_path)


def test_empty_file_raises_malformed(write_csv: WriteCsv) -> None:
    """A zero-byte file raises MalformedCSVError with line_number None."""
    path = write_csv("")
    with pytest.raises(MalformedCSVError) as caught:
        SalesDataLoader().load(path)
    assert caught.value.line_number is None


def test_header_only_returns_empty_result(write_csv: WriteCsv) -> None:
    """A header with no rows gives no records and no errors."""
    result = SalesDataLoader().load(write_csv(HEADER))
    assert result.records == ()
    assert result.errors == ()
    assert not result.has_errors


def test_missing_required_column_raises_malformed(write_csv: WriteCsv) -> None:
    """The message names every missing column."""
    path = write_csv("transaction_id,date,region,salesperson,quantity\n")
    with pytest.raises(MalformedCSVError) as caught:
        SalesDataLoader().load(path)

    message = str(caught.value)
    assert "product_category" in message
    assert "unit_price" in message
    assert "total_amount" in message
    assert caught.value.line_number is None


def test_header_spellings_are_normalized(write_csv: WriteCsv) -> None:
    """camelCase, 'Transaction ID' and a UTF-8 BOM on the first header all load."""
    path = write_csv(
        "﻿Transaction ID,Date,Region,Sales Person,productCategory,"
        "Quantity,Unit Price,totalAmount\n"
        "T1,2026-01-05,West,Ana Silva,Electronics,2,49.99,99.98\n"
    )
    result = SalesDataLoader().load(path)
    assert not result.has_errors
    # A BOM left in place would make the first header "﻿Transaction ID",
    # which no longer normalizes to transaction_id.
    assert result.records[0].transaction_id == "T1"
    assert result.records[0].salesperson == "Ana Silva"


def test_duplicate_headers_for_one_column_raise_malformed(
    write_csv: WriteCsv,
) -> None:
    """Two headers naming the same column are ambiguous, so the file is rejected."""
    path = write_csv(
        "transaction_id,transactionId,date,region,salesperson,"
        "product_category,quantity,unit_price,total_amount\n"
    )
    with pytest.raises(MalformedCSVError, match="transaction_id"):
        SalesDataLoader().load(path)


def test_quoted_comma_in_field_is_parsed(write_csv: WriteCsv) -> None:
    """salesperson '"Lee, Dana"' parses as Lee, Dana."""
    path = write_csv(
        csv_text('T1,2026-01-05,West,"Lee, Dana",Electronics,2,49.99,99.98')
    )
    result = SalesDataLoader().load(path)
    assert not result.has_errors
    assert result.records[0].salesperson == "Lee, Dana"


def test_lenient_mode_reports_line_numbers(write_csv: WriteCsv) -> None:
    """Bad rows are skipped; each RowError has the right physical line number."""
    path = write_csv(
        csv_text(
            "T1,2026-01-05,West,Ana Silva,Electronics,2,49.99,99.98",
            "T2,2026-02-30,East,Ben Ortiz,Furniture,1,350.00,350.00",
            "T3,2026-01-07,North,Cara Jones,Software,1,99.00,99.00",
            "T4,2026-01-08,South,Raj Patel,Software,three,99.00,99.00",
        )
    )
    result = SalesDataLoader().load(path)

    assert [sale.transaction_id for sale in result.records] == ["T1", "T3"]
    assert [error.line_number for error in result.errors] == [3, 5]
    assert "2026-02-30" in result.errors[0].message
    # The RowError carries the line number as a field, so repeating it in
    # the message would read as "line 3: line 3: ...".
    assert not result.errors[0].message.startswith("line ")


def test_strict_mode_raises_on_first_bad_row(write_csv: WriteCsv) -> None:
    """strict=True raises MalformedCSVError with line_number of the first bad row."""
    path = write_csv(
        csv_text(
            "T1,2026-01-05,West,Ana Silva,Electronics,2,49.99,99.98",
            "T2,2026-02-30,East,Ben Ortiz,Furniture,1,350.00,350.00",
            "T3,2026-01-07,North,Cara Jones,Software,three,99.00,99.00",
        )
    )
    loader = SalesDataLoader(strict=True)
    assert loader.strict

    with pytest.raises(MalformedCSVError) as caught:
        loader.load(path)
    assert caught.value.line_number == 3
    assert str(caught.value).startswith("line 3: ")


def test_duplicate_transaction_id_reported(write_csv: WriteCsv) -> None:
    """The second occurrence is a RowError; the first is kept."""
    path = write_csv(
        csv_text(
            "T1,2026-01-05,West,Ana Silva,Electronics,2,49.99,99.98",
            "T1,2026-01-06,East,Ben Ortiz,Furniture,1,350.00,350.00",
        )
    )
    result = SalesDataLoader().load(path)

    assert len(result.records) == 1
    assert result.records[0].date == dt.date(2026, 1, 5)
    assert [error.line_number for error in result.errors] == [3]
    assert "duplicate" in result.errors[0].message


def test_duplicate_transaction_id_raises_in_strict_mode(write_csv: WriteCsv) -> None:
    """A duplicate is a bad row too, so strict mode refuses the file."""
    path = write_csv(
        csv_text(
            "T1,2026-01-05,West,Ana Silva,Electronics,2,49.99,99.98",
            "T1,2026-01-06,East,Ben Ortiz,Furniture,1,350.00,350.00",
        )
    )
    with pytest.raises(MalformedCSVError, match="duplicate") as caught:
        SalesDataLoader(strict=True).load(path)
    assert caught.value.line_number == 3


def test_short_and_long_rows_reported(write_csv: WriteCsv) -> None:
    """Too few fields and too many fields are both RowErrors."""
    path = write_csv(
        csv_text(
            "T1,2026-01-05,West,Ana Silva",
            "T2,2026-01-06,East,Ben Ortiz,Furniture,1,350.00,350.00,EXTRA",
        )
    )
    result = SalesDataLoader().load(path)

    assert result.records == ()
    assert [error.line_number for error in result.errors] == [2, 3]
    assert "too few fields" in result.errors[0].message
    assert "too many fields" in result.errors[1].message


@pytest.mark.parametrize("amount", ["NaN", "Infinity"])
def test_non_finite_amount_reported(write_csv: WriteCsv, amount: str) -> None:
    """NaN and Infinity money values are RowErrors."""
    path = write_csv(
        csv_text(f"T1,2026-01-05,West,Ana Silva,Electronics,1,{amount},{amount}")
    )
    result = SalesDataLoader().load(path)

    assert result.records == ()
    assert [error.line_number for error in result.errors] == [2]
    assert "finite" in result.errors[0].message


@pytest.mark.parametrize("bad_date", ["2026-02-30", "01/14/2026"])
def test_invalid_dates_reported(write_csv: WriteCsv, bad_date: str) -> None:
    """2026-02-30 and 01/14/2026 are RowErrors."""
    path = write_csv(
        csv_text(f"T1,{bad_date},West,Ana Silva,Electronics,2,49.99,99.98")
    )
    result = SalesDataLoader().load(path)

    assert result.records == ()
    assert [error.line_number for error in result.errors] == [2]
    assert bad_date in result.errors[0].message


def test_line_numbers_correct_after_multiline_quoted_field(
    write_csv: WriteCsv,
) -> None:
    """A quoted field containing a newline does not shift later line numbers."""
    path = write_csv(
        HEADER
        # This record occupies physical lines 2 AND 3.
        + 'T1,2026-01-05,West,"Lee,\nDana",Electronics,1,10.00,10.00\n'
        + "T2,2026-13-01,East,Ben Ortiz,Furniture,1,10.00,10.00\n"
        + "T3,2026-01-07,East,Ben Ortiz,Furniture,1,10.00,10.00\n"
    )
    result = SalesDataLoader().load(path)

    assert [sale.transaction_id for sale in result.records] == ["T1", "T3"]
    assert result.records[0].salesperson == "Lee,\nDana"
    # Counting rows with enumerate would have reported line 3 here.
    assert [error.line_number for error in result.errors] == [4]


def test_malformed_sample_file_matches_documented_errors() -> None:
    """data/sales_malformed.csv gives 2 records and errors on lines
    3,4,5,6,7,9,10,11,12,13.
    """
    result = SalesDataLoader().load(DATA_DIR / "sales_malformed.csv")

    assert [sale.transaction_id for sale in result.records] == ["M001", "M011"]
    assert [error.line_number for error in result.errors] == [
        3,
        4,
        5,
        6,
        7,
        9,
        10,
        11,
        12,
        13,
    ]


def test_malformed_sample_file_raises_in_strict_mode() -> None:
    """Strict mode stops at line 3, the first broken row in the sample."""
    with pytest.raises(MalformedCSVError) as caught:
        SalesDataLoader(strict=True).load(DATA_DIR / "sales_malformed.csv")
    assert caught.value.line_number == 3


def test_sample_file_loads_cleanly() -> None:
    """data/sales_sample.csv gives 120 records and zero errors."""
    result = SalesDataLoader().load(DATA_DIR / "sales_sample.csv")
    assert len(result.records) == 120
    assert result.errors == ()


def test_undecodable_bytes_raise_malformed(tmp_path: Path) -> None:
    """Bytes that are not valid UTF-8 are a file-level problem, not a bad row."""
    path = tmp_path / "latin1.csv"
    path.write_bytes(HEADER.encode() + b"T1,2026-01-05,West,Ana\xff,X,1,1.00,1.00\n")
    with pytest.raises(MalformedCSVError, match="not valid"):
        SalesDataLoader().load(path)


@pytest.mark.parametrize("field", ["unit_price", "total_amount"])
def test_unparseable_money_reported(write_csv: WriteCsv, field: str) -> None:
    """Text where an amount belongs is a RowError naming the field."""
    amounts = {"unit_price": "49.99", "total_amount": "99.98", field: "cheap"}
    path = write_csv(
        csv_text(
            "T1,2026-01-05,West,Ana Silva,Electronics,2,"
            f"{amounts['unit_price']},{amounts['total_amount']}"
        )
    )
    result = SalesDataLoader().load(path)

    assert result.records == ()
    assert [error.line_number for error in result.errors] == [2]
    assert f"{field} 'cheap' is not a number" == result.errors[0].message
