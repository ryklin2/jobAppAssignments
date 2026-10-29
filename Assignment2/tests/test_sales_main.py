"""Smoke tests for the Assignment 2 demo."""

from pathlib import Path

import pytest

from sales_analytics.main import EXIT_DATA_ERROR, EXIT_OK, run

DATA_DIR = Path(__file__).resolve().parents[1] / "data"

SECTION_HEADINGS = (
    "Total Sales by Region",
    "Average Sale by Category",
    "Top 3 Salespersons",
    "Monthly Sales Trend",
    "Sales by Date Range",
    "Filtered Sales",
    "Totals by Region and Category",
    "Overall Statistics",
    "SALES SUMMARY REPORT",
)


def test_main_runs_on_sample_data(capsys: pytest.CaptureFixture[str]) -> None:
    """run([]) returns 0 and prints every section heading."""
    assert run([]) == EXIT_OK

    out = capsys.readouterr().out
    assert "Loaded 120 record(s)" in out
    for heading in SECTION_HEADINGS:
        assert heading in out


def test_main_missing_file_returns_data_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A missing path returns 2 and prints the error to stderr."""
    assert run([str(tmp_path / "absent.csv")]) == EXIT_DATA_ERROR

    captured = capsys.readouterr()
    assert "absent.csv" in captured.err
    assert captured.out == ""


def test_main_strict_mode_on_malformed_file_returns_data_error(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """run(['data/sales_malformed.csv', '--strict']) returns 2."""
    assert run([str(DATA_DIR / "sales_malformed.csv"), "--strict"]) == EXIT_DATA_ERROR
    assert "line 3" in capsys.readouterr().err


def test_main_lenient_mode_reports_each_bad_row(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Without --strict the demo loads what it can and lists the rejected rows."""
    assert run([str(DATA_DIR / "sales_malformed.csv")]) == EXIT_OK

    out = capsys.readouterr().out
    assert "Loaded 2 record(s)" in out
    assert "Skipped 10 malformed row(s):" in out
    assert "line 11: duplicate transaction_id 'M001'" in out


def test_main_honours_the_cli_filters(capsys: pytest.CaptureFixture[str]) -> None:
    """--start/--end, --region and --top all reach the printed sections."""
    exit_code = run(
        [
            "--start",
            "2026-01-01",
            "--end",
            "2026-03-31",
            "--region",
            "West",
            "--top",
            "5",
        ]
    )
    assert exit_code == EXIT_OK

    out = capsys.readouterr().out
    assert "Top 5 Salespersons" in out
    assert "2026-01-01 to 2026-03-31 (inclusive)" in out
    assert "region=West" in out


def test_main_rejects_an_inverted_date_range(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """--start after --end is a usage error, not an empty result."""
    exit_code = run(["--start", "2026-06-01", "--end", "2026-01-01"])
    assert exit_code == EXIT_DATA_ERROR
    assert "after" in capsys.readouterr().err


def test_main_on_a_header_only_file_reports_no_data(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A file with no rows is valid data, so the demo succeeds and says so."""
    path = tmp_path / "empty.csv"
    path.write_text(
        "transaction_id,date,region,salesperson,product_category,"
        "quantity,unit_price,total_amount\n",
        encoding="utf-8",
    )
    assert run([str(path)]) == EXIT_OK

    out = capsys.readouterr().out
    assert "Loaded 0 record(s)" in out
    for heading in SECTION_HEADINGS:
        assert heading in out
    assert "No sales data." in out


def test_main_rejects_an_unparseable_cli_date() -> None:
    """argparse turns a bad --start into a usage error, not a traceback."""
    with pytest.raises(SystemExit) as caught:
        run(["--start", "01/14/2026"])
    assert caught.value.code == 2
