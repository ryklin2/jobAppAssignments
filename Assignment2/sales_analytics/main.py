"""Demo: load sales data and print every analytical operation.

Run with ``python -m sales_analytics`` (``--help`` lists the options).
"""

import argparse
import datetime as dt
import sys
from collections.abc import Sequence
from decimal import Decimal
from pathlib import Path

from sales_analytics.analyzer import SalesAnalyzer
from sales_analytics.exceptions import SalesDataError
from sales_analytics.loader import SalesDataLoader
from sales_analytics.models import SaleRecord
from sales_analytics.report import format_currency, format_summary_report

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


DEMO_MONTHS = 3
"""How many months the date-range demo covers when no range is given."""


def run(argv: Sequence[str] | None = None) -> int:
    """Run the demo and return a process exit code.

    Loads the CSV, prints every analytical operation under its own heading,
    and finishes with the formatted summary report.

    Returns:
        ``EXIT_OK`` on success. ``EXIT_DATA_ERROR`` after printing the
        message to stderr for ``SalesFileNotFoundError`` or
        ``MalformedCSVError`` (strict mode, or a file-level problem) -- and
        for any other ``SalesDataError``, which is the base of both.
    """
    args = parse_args(argv)

    try:
        result = SalesDataLoader(strict=args.strict).load(args.path)
    except SalesDataError as error:
        print(f"Error: {error}", file=sys.stderr)
        return EXIT_DATA_ERROR

    print(f"Loaded {len(result.records)} record(s) from {_display_path(args.path)}")
    if result.has_errors:
        print(f"Skipped {len(result.errors)} malformed row(s):")
        for row_error in result.errors:
            print(f"  line {row_error.line_number}: {row_error.message}")

    analyzer = SalesAnalyzer(result.records)

    _print_pairs("Total Sales by Region", analyzer.get_total_sales_by_region().items())
    _print_pairs(
        "Average Sale by Category", analyzer.get_average_sale_by_category().items()
    )
    _print_pairs(
        f"Top {args.top} Salespersons", analyzer.get_top_salespersons(args.top)
    )
    _print_pairs("Monthly Sales Trend", analyzer.get_monthly_sales_trend())

    if _print_date_range(analyzer, args) == EXIT_DATA_ERROR:
        return EXIT_DATA_ERROR
    _print_filter_demo(analyzer, args)

    _heading("Totals by Region and Category")
    grouped = analyzer.group_totals("region", "product_category")
    if grouped:
        for (region, category), total in grouped.items():
            print(f"  {region} / {category}: {format_currency(total)}")
    else:
        print("  No sales data.")

    _heading("Overall Statistics")
    stats = analyzer.get_statistics()
    print(f"  Transactions: {stats.count}")
    if stats.count:
        print(f"  Total:        {format_currency(stats.total)}")
        print(f"  Mean:         {format_currency(stats.mean)}")
        print(f"  Median:       {format_currency(stats.median)}")
        spread = format_currency(stats.stdev) if stats.stdev is not None else "n/a"
        print(f"  Std dev:      {spread}")

    print()
    print(format_summary_report(analyzer.generate_summary_report(args.top)))
    return EXIT_OK


def _display_path(path: Path) -> str:
    """Show ``path`` relative to the current directory when it sits inside it.

    Keeps the demo's output the same wherever the repository is checked out,
    instead of printing one machine's absolute default path.
    """
    try:
        return str(path.resolve().relative_to(Path.cwd()))
    except ValueError:
        return str(path)


def _heading(title: str) -> None:
    """Print a blank line, the section title, and a rule under it."""
    print(f"\n{title}\n{'-' * len(title)}")


def _print_pairs(title: str, pairs: object) -> None:
    """Print a section of ``(label, amount)`` pairs, or a no-data note."""
    _heading(title)
    rows = list(pairs)  # type: ignore[call-overload]
    if not rows:
        print("  No sales data.")
        return
    width = max(len(str(label)) for label, _ in rows)
    for label, amount in rows:
        print(f"  {label!s:<{width}}  {format_currency(amount):>12}")


def _print_date_range(analyzer: SalesAnalyzer, args: argparse.Namespace) -> int:
    """Print the date-range query, defaulting to the last months of data.

    Returns ``EXIT_DATA_ERROR`` if the requested range is inverted, so the
    caller can stop; otherwise ``EXIT_OK``.
    """
    _heading("Sales by Date Range")
    if not analyzer.records:
        print("  No sales data.")
        return EXIT_OK

    default_start, default_end = _recent_months(analyzer.records, DEMO_MONTHS)
    start = args.start or default_start
    end = args.end or default_end
    if start > end:
        print(f"Error: start {start} is after end {end}", file=sys.stderr)
        return EXIT_DATA_ERROR

    matches = analyzer.get_sales_by_date_range(start, end)
    total = sum((record.total_amount for record in matches), Decimal("0"))
    print(f"  {start} to {end} (inclusive)")
    print(f"  {len(matches)} transaction(s), {format_currency(total)}")
    for record in matches[:5]:
        print(
            f"    {record.date}  {record.transaction_id:<6} "
            f"{record.salesperson:<14} {format_currency(record.total_amount):>10}"
        )
    if len(matches) > 5:
        print(f"    ... {len(matches) - 5} more")
    return EXIT_OK


def _print_filter_demo(analyzer: SalesAnalyzer, args: argparse.Namespace) -> None:
    """Print a multi-dimension filter, showing that filters return analyzers."""
    _heading("Filtered Sales")
    if not analyzer.records:
        print("  No sales data.")
        return

    region, category = args.region, args.category
    if region is None and category is None:
        # Nothing requested, so demonstrate on the first region in the file.
        region = analyzer.records[0].region

    criteria = ", ".join(
        label
        for label in (
            f"region={region}" if region else "",
            f"category={category}" if category else "",
        )
        if label
    )
    filtered = analyzer.filter_by(
        regions=[region] if region else None,
        categories=[category] if category else None,
    )
    print(f"  {criteria}")
    print(
        f"  {len(filtered)} of {len(analyzer)} transaction(s), "
        f"{format_currency(filtered.get_statistics().total)}"
    )
    for name, total in filtered.get_top_salespersons(args.top):
        print(f"    {name:<14} {format_currency(total):>10}")


def _recent_months(
    records: Sequence[SaleRecord], months: int
) -> tuple[dt.date, dt.date]:
    """Return the range covering the last ``months`` calendar months of data.

    The start is the first day of the month ``months - 1`` before the last
    sale's month, counted in whole months so a year boundary needs no case.
    """
    end = max(record.date for record in records)
    index = end.year * 12 + end.month - 1 - (months - 1)
    year, month = divmod(index, 12)
    return dt.date(year, month + 1, 1), end


def main() -> None:
    """Console entry point."""
    sys.exit(run())
