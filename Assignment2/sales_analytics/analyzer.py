"""Functional analytics over an immutable collection of sale records."""

from __future__ import annotations

import datetime as dt
import operator
from collections import Counter
from collections.abc import Callable, Iterable
from decimal import Decimal
from functools import reduce
from itertools import groupby
from operator import attrgetter
from typing import TypeVar

from sales_analytics.models import SaleRecord, SalesStats, SummaryReport

GROUPABLE_DIMENSIONS: frozenset[str] = frozenset(
    {"region", "salesperson", "product_category"}
)

K = TypeVar("K")

YearMonth = tuple[int, int]
"""A calendar month as ``(year, month)``, which sorts chronologically."""


def month_sequence(first: YearMonth, last: YearMonth) -> list[YearMonth]:
    """Every month from ``first`` to ``last`` inclusive, chronologically.

    Months are counted as a single integer (``year * 12 + month - 1``) so
    that stepping across a year boundary needs no special case.
    """
    start = first[0] * 12 + first[1] - 1
    stop = last[0] * 12 + last[1] - 1
    return [
        (year, month + 1)
        for year, month in (divmod(index, 12) for index in range(start, stop + 1))
    ]


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
        materialized = tuple(records)
        wrong = next(
            (item for item in materialized if not isinstance(item, SaleRecord)), None
        )
        if wrong is not None:
            raise TypeError(
                f"every record must be a SaleRecord, got {type(wrong).__name__}"
            )
        self._records = materialized

    @property
    def records(self) -> tuple[SaleRecord, ...]:
        """The records being analysed, in their original order."""
        return self._records

    def __len__(self) -> int:
        """Number of records."""
        return len(self._records)

    def __repr__(self) -> str:
        """Short form naming the number of records held."""
        return f"SalesAnalyzer({len(self._records)} records)"

    # ------------------------------------------------------------------ filtering

    def get_sales_by_date_range(self, start: dt.date, end: dt.date) -> list[SaleRecord]:
        """Return sales with ``start <= date <= end`` (inclusive), sorted by date.

        Raises:
            ValueError: If ``start`` is after ``end``.
        """
        _check_range(start, end)
        return sorted(
            (record for record in self._records if start <= record.date <= end),
            key=attrgetter("date"),
        )

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
        if start is not None and end is not None:
            _check_range(start, end)

        predicates: list[Callable[[SaleRecord], bool]] = []
        if start is not None:
            predicates.append(lambda record, start=start: record.date >= start)
        if end is not None:
            predicates.append(lambda record, end=end: record.date <= end)
        for attribute, allowed in (
            ("region", regions),
            ("product_category", categories),
            ("salesperson", salespersons),
        ):
            if allowed is None:
                continue
            # Both values are bound as defaults: a plain closure over the
            # loop variables would see only the last pair once the loop ends.
            predicates.append(
                lambda record, attribute=attribute, wanted=frozenset(allowed): (
                    getattr(record, attribute) in wanted
                )
            )

        return SalesAnalyzer(
            record
            for record in self._records
            if all(predicate(record) for predicate in predicates)
        )

    # ---------------------------------------------------------------- aggregation

    def get_total_sales_by_region(self) -> dict[str, Decimal]:
        """Return revenue per region, highest first (ties by region name)."""
        return _rank_by_amount(self._totals_by(attrgetter("region")))

    def get_average_sale_by_category(self) -> dict[str, Decimal]:
        """Return the mean ``total_amount`` per transaction for each category.

        Keys are ordered by category name. Values are unrounded Decimals.
        """
        return {
            category: self._sum_amounts(record.total_amount for record in group)
            / len(group)
            for category, group in self._group(attrgetter("product_category")).items()
        }

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
        if not dimensions:
            raise ValueError("at least one dimension is required")
        unknown = sorted(set(dimensions) - GROUPABLE_DIMENSIONS)
        if unknown:
            raise ValueError(
                f"unknown dimension(s): {', '.join(unknown)}; "
                f"choose from {', '.join(sorted(GROUPABLE_DIMENSIONS))}"
            )

        getter = attrgetter(*dimensions)
        # attrgetter returns a bare value for one name and a tuple for
        # several, so a single dimension is wrapped to keep the key a tuple.
        key: Callable[[SaleRecord], tuple[str, ...]] = (
            getter if len(dimensions) > 1 else lambda record: (getter(record),)
        )
        return self._totals_by(key)

    def get_statistics(self) -> SalesStats:
        """Return statistics over every ``total_amount``."""
        return SalesStats.from_amounts(record.total_amount for record in self._records)

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
        if isinstance(n, bool) or not isinstance(n, int):
            raise TypeError(f"n must be an int, got {type(n).__name__}")
        if n < 1:
            raise ValueError(f"n must be at least 1, got {n}")
        ranked = _rank_by_amount(self._totals_by(attrgetter("salesperson")))
        return list(ranked.items())[:n]

    def get_monthly_sales_trend(
        self, *, fill_gaps: bool = True
    ) -> list[tuple[str, Decimal]]:
        """Return revenue per month as ``("YYYY-MM", total)``, chronological.

        Group on ``(year, month)``, never on month alone, or January 2025
        and January 2026 merge. With ``fill_gaps``, months between the first
        and last sale that had no sales appear with ``Decimal("0")``.
        """
        totals = self._totals_by(lambda record: (record.date.year, record.date.month))
        if not totals:
            return []
        # _totals_by groups through sorted(), so the keys are already
        # chronological; (year, month) tuples sort the way calendars do.
        observed = list(totals)
        months = month_sequence(observed[0], observed[-1]) if fill_gaps else observed
        return [
            (f"{year:04d}-{month:02d}", totals.get((year, month), Decimal("0")))
            for year, month in months
        ]

    def generate_summary_report(self, top_n: int = 3) -> SummaryReport:
        """Compute a ``SummaryReport`` by reusing the methods above.

        The busiest category is the one with the most transactions
        (``Counter(...).most_common``; ties broken by name). Works on an
        empty analyzer: dates and optional fields become ``None``.
        """
        dates = tuple(record.date for record in self._records)
        counts = Counter(record.product_category for record in self._records)
        # most_common() leaves ties in insertion order, which depends on the
        # file; re-sorting makes the winner reproducible.
        busiest = sorted(counts.most_common(), key=lambda pair: (-pair[1], pair[0]))

        return SummaryReport(
            record_count=len(self._records),
            period_start=min(dates) if dates else None,
            period_end=max(dates) if dates else None,
            stats=self.get_statistics(),
            total_by_region=tuple(self.get_total_sales_by_region().items()),
            average_by_category=tuple(self.get_average_sale_by_category().items()),
            top_salespersons=tuple(self.get_top_salespersons(top_n)),
            monthly_trend=tuple(self.get_monthly_sales_trend()),
            busiest_category=busiest[0][0] if busiest else None,
        )

    # -------------------------------------------------------------------- helpers

    def _totals_by(self, key: Callable[[SaleRecord], K]) -> dict[K, Decimal]:
        """Sum ``total_amount`` for each group ``key`` produces."""
        return {
            group_key: self._sum_amounts(record.total_amount for record in group)
            for group_key, group in self._group(key).items()
        }

    def _group(self, key: Callable[[SaleRecord], K]) -> dict[K, tuple[SaleRecord, ...]]:
        """Group records by ``key`` using ``sorted`` + ``itertools.groupby``.

        ``groupby`` only merges ADJACENT equal keys, so the input must be
        sorted by the very same key function first; otherwise one key comes
        back as several groups. Keys must be mutually comparable.

        Because the input is sorted, the returned dict's keys are in
        ascending key order, which the callers rely on.
        """
        return {
            group_key: tuple(group)
            for group_key, group in groupby(sorted(self._records, key=key), key=key)
        }

    @staticmethod
    def _sum_amounts(amounts: Iterable[Decimal]) -> Decimal:
        """Sum with ``reduce(operator.add, amounts, Decimal("0"))``.

        The initializer is required: without it ``reduce`` raises
        ``TypeError`` on empty input, and the result would not be a Decimal.
        """
        return reduce(operator.add, amounts, Decimal("0"))


def _check_range(start: dt.date, end: dt.date) -> None:
    """Raise ``ValueError`` if ``start`` is after ``end``."""
    if start > end:
        raise ValueError(f"start {start} must not be after end {end}")


def _rank_by_amount(totals: dict[K, Decimal]) -> dict[K, Decimal]:
    """Re-order ``totals`` by amount descending, ties by key ascending."""
    return dict(sorted(totals.items(), key=lambda pair: (-pair[1], pair[0])))
