"""Generate the sample CSV files in ``data/`` reproducibly.

Usage:
    python scripts/generate_sample_data.py

Writes:
    data/sales_sample.csv     120 valid records, Jan 2025 - Jun 2026
                              (crosses a year boundary to exercise
                              year-month grouping).
    data/sales_malformed.csv  2 valid rows and 10 deliberately broken rows,
                              documented in MALFORMED_ROWS below.

The random generator is seeded, so every run produces identical files.
Money is computed with Decimal, so every total_amount equals
quantity * unit_price exactly.
"""

import csv
import datetime as dt
import random
from decimal import Decimal
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
SEED = 2026
RECORD_COUNT = 120
FIRST_DAY = dt.date(2025, 1, 1)
LAST_DAY = dt.date(2026, 6, 30)

HEADER = [
    "transaction_id",
    "date",
    "region",
    "salesperson",
    "product_category",
    "quantity",
    "unit_price",
    "total_amount",
]

# Each salesperson works one region, as in a real sales team.
SALESPEOPLE = {
    "Alice Chen": "North",
    "Marcus Reed": "North",
    "Priya Shah": "South",
    "Diego Alvarez": "South",
    "Hannah Kim": "East",
    "Omar Haddad": "East",
    "Sofia Rossi": "West",
    "Liam O'Brien": "West",
}

# Category -> (catalogue price points, (min qty, max qty)).
CATEGORIES = {
    "Electronics": (["49.99", "129.99", "349.00", "799.00", "1299.99"], (1, 4)),
    "Furniture": (["89.00", "149.50", "299.00", "649.00"], (1, 3)),
    "Office Supplies": (["2.49", "5.99", "12.75", "24.99"], (5, 40)),
    "Software": (["19.99", "59.00", "149.00", "499.00"], (1, 10)),
    "Accessories": (["9.99", "24.50", "39.99", "74.95"], (1, 12)),
}

# (row, reason). Line numbers assume the header is line 1 and the blank
# line written after M006 is line 8 (DictReader skips it but counts it).
MALFORMED_ROWS: list[tuple[list[str], str]] = [
    (
        [
            "M001",
            "2026-01-05",
            "West",
            "Lee, Dana",
            "Electronics",
            "2",
            "49.99",
            "99.98",
        ],
        "line 2: VALID (quoted comma in salesperson)",
    ),
    (
        [
            "M002",
            "2026-02-30",
            "East",
            "Ben Ortiz",
            "Furniture",
            "1",
            "350.00",
            "350.00",
        ],
        "line 3: impossible date",
    ),
    (
        [
            "M003",
            "2026-01-07",
            "North",
            "Ana Silva",
            "Office Supplies",
            "three",
            "2.50",
            "7.50",
        ],
        "line 4: quantity not a number",
    ),
    (
        [
            "M004",
            "2026-01-08",
            "South",
            "Raj Patel",
            "Software",
            "-1",
            "99.00",
            "-99.00",
        ],
        "line 5: negative quantity",
    ),
    (
        [
            "M005",
            "2026-01-09",
            "West",
            "Cara Jones",
            "Electronics",
            "2",
            "100.00",
            "250.00",
        ],
        "line 6: total does not equal quantity * unit_price",
    ),
    (
        ["M006", "2026-01-10", "East", "Ben Ortiz", "Furniture", "1", "NaN", "NaN"],
        "line 7: non-finite money",
    ),
    ([], "line 8: blank line (skipped by DictReader, still counted)"),
    (["M007", "2026-01-11", "North", "Ana Silva"], "line 9: too few fields"),
    (
        [
            "M008",
            "2026-01-12",
            "South",
            "Raj Patel",
            "Software",
            "1",
            "99.00",
            "99.00",
            "EXTRA",
        ],
        "line 10: too many fields",
    ),
    (
        [
            "M001",
            "2026-01-13",
            "West",
            "Cara Jones",
            "Accessories",
            "1",
            "19.99",
            "19.99",
        ],
        "line 11: duplicate transaction_id (first kept)",
    ),
    (
        [
            "M009",
            "01/14/2026",
            "East",
            "Ben Ortiz",
            "Furniture",
            "1",
            "350.00",
            "350.00",
        ],
        "line 12: wrong date format",
    ),
    (
        [
            "M010",
            "2026-01-15",
            "",
            "Ana Silva",
            "Office Supplies",
            "4",
            "2.50",
            "10.00",
        ],
        "line 13: blank region",
    ),
    (
        ["M011", "2026-01-16", "South", "Raj Patel", "Software", "1", "99.00", "99.00"],
        "line 14: VALID",
    ),
]


def generate_sample_rows(rng: random.Random) -> list[list[str]]:
    """Build ``RECORD_COUNT`` valid rows sorted by date."""
    span_days = (LAST_DAY - FIRST_DAY).days
    dates = sorted(
        FIRST_DAY + dt.timedelta(days=rng.randrange(span_days + 1))
        for _ in range(RECORD_COUNT)
    )
    people = sorted(SALESPEOPLE)
    categories = sorted(CATEGORIES)
    rows = []
    for number, sale_date in enumerate(dates, start=1):
        person = rng.choice(people)
        category = rng.choice(categories)
        prices, (low, high) = CATEGORIES[category]
        unit_price = Decimal(rng.choice(prices))
        quantity = rng.randint(low, high)
        rows.append(
            [
                f"T{number:04d}",
                sale_date.isoformat(),
                SALESPEOPLE[person],
                person,
                category,
                str(quantity),
                str(unit_price),
                str(quantity * unit_price),
            ]
        )
    return rows


def write_csv(path: Path, rows: list[list[str]]) -> None:
    """Write ``HEADER`` plus ``rows`` with standard CSV quoting."""
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(HEADER)
        writer.writerows(rows)


def main() -> None:
    """Regenerate both sample files."""
    DATA_DIR.mkdir(exist_ok=True)
    sample_rows = generate_sample_rows(random.Random(SEED))
    write_csv(DATA_DIR / "sales_sample.csv", sample_rows)
    write_csv(DATA_DIR / "sales_malformed.csv", [row for row, _ in MALFORMED_ROWS])
    print(f"Wrote {len(sample_rows)} sample records and")
    print(f"{len(MALFORMED_ROWS)} malformed-file test lines to {DATA_DIR}")


if __name__ == "__main__":
    main()
