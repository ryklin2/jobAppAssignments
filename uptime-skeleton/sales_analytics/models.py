"""Immutable value types for sales records, load results and reports.

Thread safety:
    Every type here is a frozen dataclass whose fields are themselves
    immutable (str, int, date, Decimal, tuples). Instances can be shared
    between threads freely. Collections are stored as tuples, never lists or
    dicts, because freezing a dataclass is shallow.
"""

from __future__ import annotations

# ``import datetime as dt`` rather than ``from datetime import date``: the
# spec requires a field named ``date``, which would shadow the type.
import datetime as dt
from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal

MONEY_TOLERANCE = Decimal("0.01")
"""Largest allowed gap between ``total_amount`` and ``quantity * unit_price``."""


@dataclass(frozen=True, slots=True)
class SaleRecord:
    """One validated sales transaction.

    Attributes:
        transaction_id: Unique, non-empty identifier.
        date: Calendar date of the sale.
        region: Non-empty sales region.
        salesperson: Non-empty salesperson name (assumed unique).
        product_category: Non-empty category name.
        quantity: Units sold; an int of at least 1 (bools rejected).
        unit_price: Price per unit; a finite ``Decimal`` greater than 0.
        total_amount: Sale value; a finite ``Decimal`` equal to
            ``quantity * unit_price`` within ``MONEY_TOLERANCE``.

    Thread safety:
        Immutable; safe to share between threads.
    """

    transaction_id: str
    date: dt.date
    region: str
    salesperson: str
    product_category: str
    quantity: int
    unit_price: Decimal
    total_amount: Decimal

    def __post_init__(self) -> None:
        """Enforce the domain rules, so a record built anywhere is valid.

        Raises:
            TypeError: If a field has the wrong type: text fields must be
                ``str``, ``date`` a ``datetime.date``, ``quantity`` an ``int``
                (not ``bool``), and both money fields ``Decimal`` (a float is
                rejected, never silently converted).
            ValueError: If a text field is blank after stripping, quantity
                < 1, a money value is not finite (NaN/Infinity) or unit_price
                <= 0, or ``total_amount`` differs from
                ``quantity * unit_price`` by more than ``MONEY_TOLERANCE``.
        """
        # TODO: implement the checks listed above. Leaving this as a no-op
        # (rather than raising NotImplementedError) keeps test fixtures that
        # build records working while the skeleton is filled in.


@dataclass(frozen=True, slots=True)
class RowError:
    """A CSV row that was rejected during lenient loading.

    Attributes:
        line_number: 1-based physical line of the row (header is line 1).
        message: Why the row was rejected.
    """

    line_number: int
    message: str


@dataclass(frozen=True, slots=True)
class LoadResult:
    """Records loaded from a CSV file plus any rejected rows.

    Attributes:
        records: Valid records, in file order.
        errors: Rejected rows, in file order (always empty in strict mode,
            because strict mode raises instead).
    """

    records: tuple[SaleRecord, ...]
    errors: tuple[RowError, ...]

    @property
    def has_errors(self) -> bool:
        """Whether any row was rejected."""
        return bool(self.errors)


@dataclass(frozen=True, slots=True)
class SalesStats:
    """Summary statistics over a collection of sale amounts.

    Attributes:
        count: Number of amounts.
        total: Sum of amounts (``Decimal("0")`` when empty).
        mean: Arithmetic mean, or ``None`` when empty.
        median: Median, or ``None`` when empty.
        minimum: Smallest amount, or ``None`` when empty.
        maximum: Largest amount, or ``None`` when empty.
        stdev: Sample standard deviation, or ``None`` when fewer than two
            amounts (``statistics.stdev`` raises for n < 2).
    """

    count: int
    total: Decimal
    mean: Decimal | None
    median: Decimal | None
    minimum: Decimal | None
    maximum: Decimal | None
    stdev: Decimal | None

    @classmethod
    def from_amounts(cls, amounts: Iterable[Decimal]) -> SalesStats:
        """Compute statistics with the ``statistics`` module (it supports Decimal).

        Materialize ``amounts`` to a tuple first: it may be a one-shot
        generator. Never raises for empty or single-value input.
        """
        raise NotImplementedError


@dataclass(frozen=True, slots=True)
class SummaryReport:
    """Everything ``generate_summary_report()`` computes, as plain data.

    Pair fields are tuples of ``(label, amount)`` in display order; dicts
    would make this "frozen" object mutable.

    Attributes:
        record_count: Number of records analysed.
        period_start: Earliest sale date, or ``None`` when empty.
        period_end: Latest sale date, or ``None`` when empty.
        stats: Statistics over every ``total_amount``.
        total_by_region: Revenue per region, highest first.
        average_by_category: Mean sale per category, by category name.
        top_salespersons: Top performers by revenue.
        monthly_trend: Revenue per ``YYYY-MM``, chronological.
        busiest_category: Category with the most transactions, or ``None``.
    """

    record_count: int
    period_start: dt.date | None
    period_end: dt.date | None
    stats: SalesStats
    total_by_region: tuple[tuple[str, Decimal], ...]
    average_by_category: tuple[tuple[str, Decimal], ...]
    top_salespersons: tuple[tuple[str, Decimal], ...]
    monthly_trend: tuple[tuple[str, Decimal], ...]
    busiest_category: str | None
