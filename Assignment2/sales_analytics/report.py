"""Plain-text rendering of a SummaryReport."""

from collections.abc import Sequence
from decimal import ROUND_HALF_UP, Decimal

from sales_analytics.models import SalesStats, SummaryReport

CENT = Decimal("0.01")

INDENT = "  "
NO_DATA = "No sales data."
RULE = "=" * 60


def format_currency(amount: Decimal) -> str:
    """Format ``amount`` as dollars, rounding half up to cents.

    Examples: ``Decimal("2.675")`` -> ``"$2.68"`` (float rounding would give
    $2.67), ``Decimal("1234567.5")`` -> ``"$1,234,567.50"``.
    """
    # ROUND_HALF_UP is the rule people expect on an invoice; Decimal's
    # default is ROUND_HALF_EVEN, which would turn 2.675 into 2.67.
    return f"${amount.quantize(CENT, rounding=ROUND_HALF_UP):,.2f}"


def format_summary_report(report: SummaryReport) -> str:
    """Render ``report`` as a multi-line text report.

    Sections, in order: overview (record count, period, total revenue),
    statistics, revenue by region, average sale by category, top
    salespersons, monthly trend, busiest category. Build lines with
    generator expressions and ``"\\n".join``. An empty report renders
    "No sales data." under each section instead of failing.
    """
    sections = (
        ("Statistics", _stats_lines(report.stats)),
        ("Revenue by Region", _pair_lines(report.total_by_region)),
        ("Average Sale by Category", _pair_lines(report.average_by_category)),
        ("Top Salespersons", _pair_lines(report.top_salespersons, ranked=True)),
        ("Monthly Trend", _pair_lines(report.monthly_trend)),
        ("Busiest Category", [INDENT + (report.busiest_category or NO_DATA)]),
    )
    blocks = [_overview_lines(report)]
    blocks.extend([title, *lines] for title, lines in sections)
    return "\n".join("\n".join(block) for block in _interleave_blank(blocks))


def _overview_lines(report: SummaryReport) -> list[str]:
    """Render the title bar and the three headline figures."""
    period = (
        f"{report.period_start} to {report.period_end}"
        if report.period_start is not None and report.period_end is not None
        else "n/a"
    )
    return [
        RULE,
        "SALES SUMMARY REPORT",
        RULE,
        *_label_lines(
            (
                ("Records analysed", str(report.record_count)),
                ("Period", period),
                ("Total revenue", format_currency(report.stats.total)),
            ),
            indent="",
        ),
    ]


def _stats_lines(stats: SalesStats) -> list[str]:
    """Render the statistics block, or the placeholder when there is no data."""
    if stats.count == 0:
        return [INDENT + NO_DATA]
    return _label_lines(
        (
            ("Transactions", str(stats.count)),
            ("Mean sale", format_currency(stats.mean)),
            ("Median sale", format_currency(stats.median)),
            ("Smallest sale", format_currency(stats.minimum)),
            ("Largest sale", format_currency(stats.maximum)),
            (
                "Std deviation",
                # stdev needs at least two sales to mean anything.
                format_currency(stats.stdev) if stats.stdev is not None else "n/a",
            ),
        )
    )


def _label_lines(rows: Sequence[tuple[str, str]], *, indent: str = INDENT) -> list[str]:
    """Render ``label: value`` rows with the values aligned in one column."""
    width = max(len(label) for label, _ in rows) + 1
    return [f"{indent}{label + ':':<{width}} {value}" for label, value in rows]


def _pair_lines(
    pairs: Sequence[tuple[str, Decimal]], *, ranked: bool = False
) -> list[str]:
    """Render ``(label, amount)`` pairs as an aligned money column.

    With ``ranked``, each row is numbered, which is what makes a "top N"
    list read as a ranking rather than an unordered list.
    """
    if not pairs:
        return [INDENT + NO_DATA]
    labels = [
        f"{position}. {label}" if ranked else label
        for position, (label, _) in enumerate(pairs, start=1)
    ]
    width = max(len(label) for label in labels)
    return [
        f"{INDENT}{label:<{width}}  {format_currency(amount):>12}"
        for label, (_, amount) in zip(labels, pairs, strict=True)
    ]


def _interleave_blank(blocks: Sequence[Sequence[str]]) -> list[Sequence[str]]:
    """Put one blank line between blocks, and none at either end."""
    separated: list[Sequence[str]] = []
    for block in blocks:
        if separated:
            separated.append([""])
        separated.append(block)
    return separated
