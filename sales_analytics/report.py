"""Plain-text rendering of a SummaryReport."""

from decimal import Decimal

from sales_analytics.models import SummaryReport

# Suggested import for the implementation: from decimal import ROUND_HALF_UP

CENT = Decimal("0.01")


def format_currency(amount: Decimal) -> str:
    """Format ``amount`` as dollars, rounding half up to cents.

    Examples: ``Decimal("2.675")`` -> ``"$2.68"`` (float rounding would give
    $2.67), ``Decimal("1234567.5")`` -> ``"$1,234,567.50"``.
    """
    raise NotImplementedError


def format_summary_report(report: SummaryReport) -> str:
    """Render ``report`` as a multi-line text report.

    Sections, in order: overview (record count, period, total revenue),
    statistics, revenue by region, average sale by category, top
    salespersons, monthly trend, busiest category. Build lines with
    generator expressions and ``"\\n".join``. An empty report renders
    "No sales data." under each section instead of failing.
    """
    raise NotImplementedError
