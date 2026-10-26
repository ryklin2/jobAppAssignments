"""Shared pytest fixtures for the sales analytics tests."""

import datetime as dt
from collections.abc import Callable
from decimal import Decimal
from pathlib import Path

import pytest

from sales_analytics.models import SaleRecord


@pytest.fixture
def write_csv(tmp_path: Path) -> Callable[..., Path]:
    """Return a helper that writes exact CSV text to a temporary file.

    Text is written verbatim (``newline=""``), so each test controls quoting,
    blank lines, byte-order marks and line endings precisely.
    """

    def _write(text: str, name: str = "sales.csv", encoding: str = "utf-8") -> Path:
        path = tmp_path / name
        path.write_text(text, encoding=encoding, newline="")
        return path

    return _write


def _record(
    transaction_id: str,
    day: str,
    region: str,
    salesperson: str,
    category: str,
    quantity: int,
    unit_price: str,
    total: str,
) -> SaleRecord:
    return SaleRecord(
        transaction_id=transaction_id,
        date=dt.date.fromisoformat(day),
        region=region,
        salesperson=salesperson,
        product_category=category,
        quantity=quantity,
        unit_price=Decimal(unit_price),
        total_amount=Decimal(total),
    )


@pytest.fixture
def sales_records() -> list[SaleRecord]:
    """Eight records whose analytics were worked out by hand.

    Expected values (assert against these, never against the code's output):

    Total revenue: 1299.00

    By region:       West 600.00 | East 450.01 | North 248.99
    By salesperson:  Ben 549.99 | Cara 400.00 | Ana 225.00 | Dev 124.01
    Average sale by category:
                     Electronics 156.25 (625.00 / 4)
                     Furniture   300.00 (600.00 / 2)
                     Office       37.00 ( 74.00 / 2)
    Monthly trend (gaps filled):
                     2025-11 550.00 | 2025-12 150.00 | 2026-01 224.99
                     2026-02   0    | 2026-03 374.01
    Date range 2025-12-05 .. 2026-01-21 (inclusive): T3, T4, T5
    Region x category:
                     (East, Electronics) 75.01   (East, Furniture) 350.00
                     (East, Office) 25.00        (North, Electronics) 199.99
                     (North, Office) 49.00       (West, Electronics) 350.00
                     (West, Furniture) 250.00
    Statistics over total_amount:
                     count 8, mean 162.375, median 174.995, min 25.00,
                     max 350.00, sample stdev ~110.3393 (exact Decimal from
                     statistics.stdev: 110.3393306383280798733460532)
    Busiest category by transaction count: Electronics (4)
    """
    r = _record
    return [
        r("T1", "2025-11-03", "West", "Ana", "Electronics", 2, "100.00", "200.00"),
        r("T2", "2025-11-17", "East", "Ben", "Furniture", 1, "350.00", "350.00"),
        r("T3", "2025-12-05", "West", "Cara", "Electronics", 3, "50.00", "150.00"),
        r("T4", "2026-01-09", "East", "Ana", "Office", 10, "2.50", "25.00"),
        r("T5", "2026-01-21", "North", "Ben", "Electronics", 1, "199.99", "199.99"),
        r("T6", "2026-03-02", "West", "Cara", "Furniture", 2, "125.00", "250.00"),
        r("T7", "2026-03-15", "North", "Dev", "Office", 4, "12.25", "49.00"),
        r("T8", "2026-03-30", "East", "Dev", "Electronics", 1, "75.01", "75.01"),
    ]
