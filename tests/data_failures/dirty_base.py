"""The clean file every dirty sample edits (docs/DATA_FAILURE_MODES.md;
session 2E-u). Standard library only - the generator modules add pandas at
most (a test parses every import): no engine figure can shape a sample.

Ann, Bo and Cy each buy one Mug (10.00) and one Tea (4.00) every day from
2023-01-01 to 2024-02-29 - 42.00 a day, 14 complete months, current month
2024-02 (1,218.00), previous 2024-01 (1,302.00). Each mode names the lines
it touches, so its check can work the figure by hand.

No case needs randomness: SEED is the spec's fixed seed, kept for a case
that will.
"""

import csv
import io
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, timedelta

SEED = 20261001
FIRST, LAST = date(2023, 1, 1), date(2024, 2, 29)
CUSTOMERS = ("Ann", "Bo", "Cy")
PRODUCTS = (("Mug", "10.0"), ("Tea", "4.0"))
DAY_REVENUE = 42.0
MAPPING = {"Date": "transaction_date", "Qty": "quantity", "Price": "unit_price", "Product": "product_name",
           "Cust": "customer"}


@dataclass
class Sample:
    """`rows` for the stages that read lines; `raw` for the file-level modes
    (and for the real flow, which starts from the file's bytes). `answers`
    are Review's (OrderConfirmations' fields, plain)."""
    rows: list[dict[str, str]] = field(default_factory=list)
    raw: bytes | None = None
    mapping: dict[str, str] = field(default_factory=lambda: dict(MAPPING))
    answers: dict[str, object] = field(default_factory=dict)


def base(first: date = FIRST, last: date = LAST, *, fmt: str = "%Y-%m-%d",
         products: tuple[tuple[str, str], ...] = PRODUCTS) -> list[dict[str, str]]:
    rows, day = [], first
    while day <= last:
        for customer in CUSTOMERS:
            for product, price in products:
                rows.append({"Date": day.strftime(fmt), "Qty": "1", "Price": price, "Product": product,
                             "Cust": customer})
        day += timedelta(days=1)
    return rows


def on(rows: list[dict[str, str]], day: str, product: str = "Mug", customer: str = "Ann") -> dict[str, str]:
    return next(row for row in rows if row["Date"] == day and row["Product"] == product and row["Cust"] == customer)


def as_csv(rows: list[dict[str, str]], delimiter: str = ",") -> bytes:
    """Quoted where a cell needs it ("10,5" in a comma file) - a CSV writer's
    file, as an export would be (2E-u review #11)."""
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=list(rows[0]), delimiter=delimiter, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return out.getvalue().encode("utf-8")


def edit(day: str, **cells: str) -> Callable[[], Sample]:
    """Ann's Mug on `day` with its cells replaced."""
    def build() -> Sample:
        rows = base()
        on(rows, day).update(cells)
        return Sample(rows)
    return build


def extra(*lines: dict[str, str], mapping: dict[str, str] | None = None,
          answers: dict[str, object] | None = None) -> Callable[[], Sample]:
    """The base file plus `lines` (each Ann's Mug unless it says otherwise)."""
    def build() -> Sample:
        added = [{"Qty": "1", "Price": "10.0", "Product": "Mug", "Cust": "Ann"} | line for line in lines]
        rows = base()
        if mapping:
            for row in rows:
                row.update(dict.fromkeys((name for name in mapping if name not in MAPPING), ""))
        return Sample(rows + added, mapping=MAPPING | (mapping or {}), answers=answers or {})
    return build


def invoiced(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    """One receipt per customer per day."""
    for row in rows:
        row["Invoice"] = f"{row['Date']}-{row['Cust']}"
    return rows
