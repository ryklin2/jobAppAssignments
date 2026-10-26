"""Demo: load sales data and print every analytical operation.

Run with ``python -m sales_analytics`` (``--help`` lists the options).
"""

import argparse
import datetime as dt
import sys
from collections.abc import Sequence
from pathlib import Path

# Resolve data relative to this file, not the current working directory, so
# the demo works no matter which folder it is launched from.
DEFAULT_DATA_PATH = Path(__file__).resolve().parents[1] / "data" / "sales_sample.csv"

EXIT_OK = 0
EXIT_DATA_ERROR = 2


def _parse_cli_date(value: str) -> dt.date:
    """argparse type for ``YYYY-MM-DD`` dates (strict, via ``strptime``)."""
    try:
        return dt.datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as error:
        raise argparse.ArgumentTypeError(
            f"invalid date {value!r}; expected YYYY-MM-DD"
        ) from error


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse the demo's command-line options."""
    parser = argparse.ArgumentParser(description="Sales analytics demo.")
    parser.add_argument(
        "path", nargs="?", type=Path, default=DEFAULT_DATA_PATH, help="CSV file"
    )
    parser.add_argument(
        "--strict", action="store_true", help="fail on the first malformed row"
    )
    parser.add_argument("--top", type=int, default=3, help="top N salespersons")
    parser.add_argument("--start", type=_parse_cli_date, help="range start")
    parser.add_argument("--end", type=_parse_cli_date, help="range end")
    parser.add_argument("--region", help="region for the filter demo")
    parser.add_argument("--category", help="category for the filter demo")
    return parser.parse_args(argv)


def run(argv: Sequence[str] | None = None) -> int:
    """Run the demo and return a process exit code.

    Outline:
        1. Load with ``SalesDataLoader(strict=args.strict)``; print how many
           records loaded and each ``RowError`` with its line number.
        2. Build a ``SalesAnalyzer`` and print, each under its own heading:
           total sales by region; average sale by category; top N
           salespersons; monthly trend; sales in a date range (``--start`` /
           ``--end``, defaulting to the last three months of data); a
           region/category filter (``--region`` / ``--category``, defaulting
           to the first region); totals grouped by region and category;
           overall statistics.
        3. Print ``format_summary_report(analyzer.generate_summary_report())``.

    Returns:
        ``EXIT_OK`` on success. ``EXIT_DATA_ERROR`` after printing the
        message to stderr for ``SalesFileNotFoundError`` or
        ``MalformedCSVError`` (strict mode, or a file-level problem).
    """
    raise NotImplementedError


def main() -> None:
    """Console entry point."""
    sys.exit(run())
