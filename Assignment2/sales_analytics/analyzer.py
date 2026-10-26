"""Functional analytics over an immutable collection of sale records."""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable, Iterable
from decimal import Decimal
from typing import TypeVar

from sales_analytics.models import SaleRecord, SalesStats, SummaryReport

# Suggested imports for the implementation:
#   import operator
#   from collections import Counter
#   from functools import reduce
#   from itertools import groupby
#   from operator import attrgetter

GROUPABLE_DIMENSIONS: frozenset[str] = frozenset(
    {"region", "salesperson", "product_category"}
)

K = TypeVar("K")


class SalesAnalyzer:
    """Read-only analytics over sale records, written in a functional style.

    Every method uses comprehensions, generator expressions, ``map`` /
    ``filter``, ``functools.reduce``, ``itertools.groupby`` or ``Counter``
    over an immutable tuple; none mutates shared state or builds results
    with an append loop. Filters return a NEW analyzer, so calls compose::

        analyzer.filter_by(regions={"West"}).get_top_salespersons(3)

    Money stays ``Decimal`` at full precision; rounding happens only when a
    report is formatted.

    Thread safety:
        Immutable after construction; safe for concurrent use from any
        number of threads.
    """

    def __init__(self, records: Iterable[SaleRecord]) -> None:
        """Store ``records`` as a tuple.

        Materializing matters: a generator passed in would be exhausted by
        the first method call, and every later call would see no data.

        Raises:
            TypeError: If any element is not a ``SaleRecord``.
        """
        raise NotImplementedError

    @property
    def records(self) -> tuple[SaleRecord, ...]:
        """The records being analysed, in their original order."""
        raise NotImplementedError

    def __len__(self) -> int:
        """Number of records."""
        raise NotImplementedError

    # ------------------------------------------------------------------ filtering

    def get_sales_by_date_range(self, start: dt.date, end: dt.date) -> list[SaleRecord]:
        """Return sales with ``start <= date <= end`` (inclusive), sorted by date.

        Raises:
            ValueError: If ``start`` is after ``end``.
        """
        raise NotImplementedError

    def filter_by(
        self,
        *,
        start: dt.date | None = None,
        end: dt.date | None = None,
        regions: Iterable[str] | None = None,
        categories: Iterable[str] | None = None,
        salespersons: Iterable[str] | None = None,
    ) -> SalesAnalyzer:
        """Return a new analyzer holding only records that match every criterion.

        ``None`` means "no constraint". Build one predicate per criterion and
        combine them with ``all()``; the original analyzer is unchanged.

        Raises:
            ValueError: If both dates are given and ``start`` is after ``end``.
        """
        raise NotImplementedError

    # ---------------------------------------------------------------- aggregation

    def get_total_sales_by_region(self) -> dict[str, Decimal]:
        """Return revenue per region, highest first (ties by region name)."""
        raise NotImplementedError

    def get_average_sale_by_category(self) -> dict[str, Decimal]:
        """Return the mean ``total_amount`` per transaction for each category.

        Keys are ordered by category name. Values are unrounded Decimals.
        """
        raise NotImplementedError

    def group_totals(self, *dimensions: str) -> dict[tuple[str, ...], Decimal]:
        """Return revenue grouped by one or more dimensions.

        Example: ``group_totals("region", "product_category")`` maps
        ``("West", "Electronics")`` to that pair's revenue. Use
        ``operator.attrgetter(*dimensions)`` as the key; wrap a single
        dimension's value in a 1-tuple so the key shape is always a tuple.

        Raises:
            ValueError: If no dimension is given, or one is not in
                ``GROUPABLE_DIMENSIONS``.
        """
        raise NotImplementedError

    def get_statistics(self) -> SalesStats:
        """Return statistics over every ``total_amount``."""
        raise NotImplementedError

    # ----------------------------------------------------------- rankings, trends

    def get_top_salespersons(self, n: int) -> list[tuple[str, Decimal]]:
        """Return the ``n`` salespersons with the highest revenue.

        Sorted by revenue descending, ties broken by name ascending, so the
        order is deterministic. If ``n`` exceeds the number of salespersons,
        return all of them.

        Raises:
            TypeError: If ``n`` is not an int (bools rejected).
            ValueError: If ``n`` < 1.
        """
        raise NotImplementedError

    def get_monthly_sales_trend(
        self, *, fill_gaps: bool = True
    ) -> list[tuple[str, Decimal]]:
        """Return revenue per month as ``("YYYY-MM", total)``, chronological.

        Group on ``(year, month)``, never on month alone, or January 2025
        and January 2026 merge. With ``fill_gaps``, months between the first
        and last sale that had no sales appear with ``Decimal("0")``.
        """
        raise NotImplementedError

    def generate_summary_report(self, top_n: int = 3) -> SummaryReport:
        """Compute a ``SummaryReport`` by reusing the methods above.

        The busiest category is the one with the most transactions
        (``Counter(...).most_common``; ties broken by name). Works on an
        empty analyzer: dates and optional fields become ``None``.
        """
        raise NotImplementedError

    # -------------------------------------------------------------------- helpers

    def _group(self, key: Callable[[SaleRecord], K]) -> dict[K, tuple[SaleRecord, ...]]:
        """Group records by ``key`` using ``sorted`` + ``itertools.groupby``.

        ``groupby`` only merges ADJACENT equal keys, so the input must be
        sorted by the very same key function first; otherwise one key comes
        back as several groups. Keys must be mutually comparable.
        """
        raise NotImplementedError

    @staticmethod
    def _sum_amounts(amounts: Iterable[Decimal]) -> Decimal:
        """Sum with ``reduce(operator.add, amounts, Decimal("0"))``.

        The initializer is required: without it ``reduce`` raises
        ``TypeError`` on empty input, and the result would not be a Decimal.
        """
        raise NotImplementedError
