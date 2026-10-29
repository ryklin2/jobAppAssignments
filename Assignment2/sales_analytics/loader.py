"""Load and validate sales records from CSV files."""

from __future__ import annotations

import csv
import datetime as dt
from collections.abc import Iterable, Iterator, Mapping, Sequence
from decimal import Decimal, InvalidOperation
from pathlib import Path

from sales_analytics.exceptions import (
    MalformedCSVError,
    SalesDataError,
    SalesFileNotFoundError,
)
from sales_analytics.models import LoadResult, RowError, SaleRecord

REQUIRED_COLUMNS: tuple[str, ...] = (
    "transaction_id",
    "date",
    "region",
    "salesperson",
    "product_category",
    "quantity",
    "unit_price",
    "total_amount",
)

CsvRow = Mapping[str | None, str | list[str] | None]
"""A row as ``csv.DictReader`` yields it.

Extra values beyond the header land under the ``None`` key as a list;
missing trailing values are ``None``. Both mean the row is malformed.
"""


def normalize_header(name: str) -> str:
    """Normalize a header for matching: trim, lowercase, drop spaces/underscores.

    ``"Transaction ID"``, ``"transactionId"`` and ``"transaction_id"`` all
    become ``"transactionid"``.
    """
    return name.strip().lower().replace(" ", "").replace("_", "")


CANONICAL_BY_NORMALIZED: Mapping[str, str] = {
    normalize_header(column): column for column in REQUIRED_COLUMNS
}
"""Normalized spelling -> canonical column name, for header matching."""


class SalesDataLoader:
    """Loads sales records from CSV, validating every row.

    Error policy:
        Lenient (default): bad rows are skipped and reported in
        ``LoadResult.errors`` with their line numbers. Strict: the first bad
        row raises ``MalformedCSVError``. File-level problems (missing file,
        empty file, missing required column, undecodable bytes) always raise.

    Thread safety:
        Holds only immutable configuration, so one loader may be used from
        several threads at once; each ``load()`` call has its own state.
    """

    DATE_FORMAT = "%Y-%m-%d"
    """Strict ISO date. Use ``datetime.strptime``: since Python 3.11,
    ``date.fromisoformat`` also accepts forms like ``20250105``."""

    def __init__(self, *, strict: bool = False, encoding: str = "utf-8-sig") -> None:
        """Create a loader.

        Args:
            strict: Raise on the first bad row instead of skipping it.
            encoding: File encoding. ``utf-8-sig`` also strips the byte-order
                mark Excel writes, which would otherwise corrupt the first
                header name.
        """
        self._strict = strict
        self._encoding = encoding

    @property
    def strict(self) -> bool:
        """Whether the loader raises on the first bad row."""
        return self._strict

    def load(self, path: str | Path) -> LoadResult:
        """Load and validate every row of the CSV file at ``path``.

        Returns:
            A ``LoadResult``; a header-only file gives empty ``records``.

        Raises:
            SalesFileNotFoundError: The path is missing or not a file.
            MalformedCSVError: File-level problem, or any bad row in strict
                mode (``line_number`` is set for row problems).
            SalesDataError: Any other I/O failure.
        """
        file_path = Path(path)
        try:
            # newline="" is required: without it the csv module cannot tell a
            # line break inside a quoted field from the end of a record.
            handle = file_path.open(newline="", encoding=self._encoding)
        except OSError as error:
            raise self._open_failure(file_path, error) from error

        try:
            with handle:
                return self._read(handle, file_path)
        except UnicodeDecodeError as error:
            raise MalformedCSVError(
                f"{file_path} is not valid {self._encoding} text: {error}"
            ) from error
        except csv.Error as error:
            raise MalformedCSVError(f"cannot parse {file_path}: {error}") from error
        except OSError as error:
            raise SalesDataError(f"cannot read {file_path}: {error}") from error

    def parse_row(
        self, row: CsvRow, line_number: int, columns: Mapping[str, str]
    ) -> SaleRecord:
        """Convert one ``DictReader`` row into a validated ``SaleRecord``.

        Args:
            row: The raw row.
            line_number: Physical line of the row, for error messages.
            columns: Canonical column name -> actual header in this file,
                from ``_resolve_columns``.

        Raises:
            MalformedCSVError: Too many fields (a ``None`` key), too few
                (a ``None`` value), an unparseable value, or a domain-rule
                violation from ``SaleRecord`` (catch its ``ValueError`` /
                ``TypeError`` and re-raise with ``line_number``).
        """
        if None in row:
            raise MalformedCSVError(
                f"too many fields: expected {len(columns)} columns", line_number
            )

        values = {}
        for canonical, header in columns.items():
            raw = row.get(header)
            if raw is None:
                raise MalformedCSVError(
                    f"too few fields: {canonical} is missing", line_number
                )
            values[canonical] = raw

        try:
            return SaleRecord(
                transaction_id=self._parse_text(
                    values["transaction_id"], "transaction_id"
                ),
                date=self._parse_date(values["date"]),
                region=self._parse_text(values["region"], "region"),
                salesperson=self._parse_text(values["salesperson"], "salesperson"),
                product_category=self._parse_text(
                    values["product_category"], "product_category"
                ),
                quantity=self._parse_quantity(values["quantity"]),
                unit_price=self._parse_money(values["unit_price"], "unit_price"),
                total_amount=self._parse_money(values["total_amount"], "total_amount"),
            )
        except (ValueError, TypeError) as error:
            raise MalformedCSVError(str(error), line_number) from error

    def _read(self, handle: Iterable[str], file_path: Path) -> LoadResult:
        """Parse an open handle: resolve the header, then every row."""
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise MalformedCSVError(f"{file_path} is empty: no header row")
        columns = self._resolve_columns(reader.fieldnames)

        # reader.line_num must be read DURING iteration: it tracks the
        # physical lines consumed so far, so after the loop it would report
        # the last line of the file for every row. Both reads below happen
        # in the same step, with nothing advancing the reader between them.
        outcomes = (
            (reader.line_num, self._parse_or_error(row, reader.line_num, columns))
            for row in reader
        )
        return self._collect(outcomes)

    def _collect(
        self, outcomes: Iterator[tuple[int, SaleRecord | RowError]]
    ) -> LoadResult:
        """Split parsed rows into records and errors, rejecting duplicate ids.

        Duplicates can only be found here, where every earlier row is known,
        so this is the one check a row cannot make on its own.
        """
        records: list[SaleRecord] = []
        errors: list[RowError] = []
        seen: set[str] = set()

        for line_number, outcome in outcomes:
            if isinstance(outcome, RowError):
                errors.append(outcome)
            elif outcome.transaction_id in seen:
                message = f"duplicate transaction_id {outcome.transaction_id!r}"
                if self._strict:
                    raise MalformedCSVError(message, line_number)
                errors.append(RowError(line_number=line_number, message=message))
            else:
                seen.add(outcome.transaction_id)
                records.append(outcome)

        return LoadResult(records=tuple(records), errors=tuple(errors))

    def _parse_or_error(
        self, row: CsvRow, line_number: int, columns: Mapping[str, str]
    ) -> SaleRecord | RowError:
        """Return the parsed record, or a ``RowError`` in lenient mode.

        In strict mode the ``MalformedCSVError`` propagates instead. Catch
        only ``MalformedCSVError``; a broad ``except Exception`` would hide
        real bugs as "malformed data".
        """
        if self._strict:
            return self.parse_row(row, line_number, columns)
        try:
            return self.parse_row(row, line_number, columns)
        except MalformedCSVError as error:
            # str(error) would repeat the line number the RowError carries.
            return RowError(line_number=line_number, message=error.args[0])

    @staticmethod
    def _resolve_columns(fieldnames: Sequence[str]) -> dict[str, str]:
        """Map each required column to the file's header spelling.

        Uses ``normalize_header`` on both sides. Extra columns are ignored.

        Raises:
            MalformedCSVError: If a required column is missing (list every
                missing name in the message) or two headers normalize to the
                same required column.
        """
        resolved: dict[str, str] = {}
        for name in fieldnames:
            canonical = CANONICAL_BY_NORMALIZED.get(normalize_header(name))
            if canonical is None:
                continue
            if canonical in resolved:
                raise MalformedCSVError(
                    f"two headers both name the {canonical!r} column: "
                    f"{resolved[canonical]!r} and {name!r}"
                )
            resolved[canonical] = name

        missing = [column for column in REQUIRED_COLUMNS if column not in resolved]
        if missing:
            raise MalformedCSVError(f"missing required column(s): {', '.join(missing)}")
        return resolved

    @staticmethod
    def _parse_text(value: str, field: str) -> str:
        """Strip ``value``; raise ``ValueError`` naming ``field`` if blank."""
        text = value.strip()
        if not text:
            raise ValueError(f"{field} must not be blank")
        return text

    @classmethod
    def _parse_date(cls, value: str) -> dt.date:
        """Parse ``YYYY-MM-DD`` with ``strptime``; ``ValueError`` otherwise.

        Rejects impossible dates such as 2026-02-30 and other formats such
        as 01/14/2026.
        """
        try:
            return dt.datetime.strptime(value.strip(), cls.DATE_FORMAT).date()
        except ValueError as error:
            raise ValueError(
                f"date {value.strip()!r} is not a valid YYYY-MM-DD date"
            ) from error

    @staticmethod
    def _parse_quantity(value: str) -> int:
        """Parse a whole number; ``"3.5"`` or ``"three"`` raise ``ValueError``."""
        try:
            return int(value.strip())
        except ValueError as error:
            raise ValueError(
                f"quantity {value.strip()!r} is not a whole number"
            ) from error

    @staticmethod
    def _parse_money(value: str, field: str) -> Decimal:
        """Parse a money string into ``Decimal`` directly from the text.

        Never go through ``float``. ``Decimal("NaN")`` and
        ``Decimal("Infinity")`` parse successfully, so check ``is_finite()``.
        Convert ``decimal.InvalidOperation`` into ``ValueError`` naming
        ``field``.
        """
        text = value.strip()
        try:
            amount = Decimal(text)
        except InvalidOperation as error:
            raise ValueError(f"{field} {text!r} is not a number") from error
        if not amount.is_finite():
            raise ValueError(f"{field} must be finite, got {text!r}")
        return amount

    @staticmethod
    def _open_failure(file_path: Path, error: OSError) -> SalesDataError:
        """Classify a failure from ``open()`` into the right exception.

        A directory raises ``IsADirectoryError`` on POSIX but
        ``PermissionError`` on Windows, so ``is_dir()`` decides rather than
        the exception type.
        """
        if isinstance(error, FileNotFoundError) or file_path.is_dir():
            return SalesFileNotFoundError(f"not a readable CSV file: {file_path}")
        return SalesDataError(f"cannot open {file_path}: {error}")
