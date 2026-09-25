"""Builders for the stage 3 tests.

`run_data` deliberately builds its `MetricsContract` by running stage 2 for
real rather than hand-writing one. Stage 3's whole contract with stage 2 is
that the two agree on the same rows (docs/AI_PIPELINE.md section 7.1), so the
tests should exercise the real handover, not a fixture's idea of it. Tests may
import both stages: tests/test_architecture.py guards `stages/`, `contracts/`,
`shared/` and `backend/app`, not the suite itself.
"""

from datetime import UTC, date, datetime, timedelta

import pandas as pd

from contracts.cleaning import OrderConfirmations

from stages.analyze.assemble import assemble_metrics
from stages.diagnose.inputs import RunData, build_run_data

NOW = datetime(2026, 9, 19, 12, 0, tzinfo=UTC)

MAPPING = {
    "Date": "transaction_date",
    "Qty": "quantity",
    "Price": "unit_price",
    "Product": "product_name",
    "Cust": "customer",
}


def row(day: date, *, qty: float = 1.0, price: float = 10.0,
        product: str = "Widget", customer: str = "Alice") -> dict:
    return {"Date": day.isoformat(), "Qty": str(qty), "Price": str(price),
            "Product": product, "Cust": customer}


def daily_rows(
    start: date,
    end: date,
    *,
    price: float = 10.0,
    qty: float = 1.0,
    closed_weekdays: tuple[int, ...] = (),
    skip: tuple[date, ...] = (),
    product: str = "Widget",
    customer: str = "Alice",
    products: int = 1,
) -> list[dict]:
    """One row per calendar date from `start` to `end` inclusive, minus any
    weekday the shop never trades and any explicitly skipped date.

    `products` > 1 spreads that many product rows across each date, which is
    what D2 needs to have anything to compare (a one-product shop is
    `inconclusive` by design).
    """
    names = [product] if products == 1 else [f"{product}{index}" for index in range(products)]
    rows = []
    day = start
    while day <= end:
        if day.weekday() not in closed_weekdays and day not in skip:
            for index, name in enumerate(names):
                rows.append(row(day, qty=qty, price=price + index, product=name,
                                customer=customer))
        day += timedelta(days=1)
    return rows


def month_span(first_month: str, months: int) -> tuple[date, date]:
    """First day of `first_month` to the last day of the month `months - 1`
    later, so every month in between is complete."""
    year, month = int(first_month[:4]), int(first_month[5:7])
    start = date(year, month, 1)
    index = year * 12 + (month - 1) + months
    end_year, end_month = index // 12, index % 12 + 1
    return start, date(end_year, end_month, 1) - timedelta(days=1)


def run_data(rows: list[dict], mapping: dict[str, str] | None = None,
             confirmations: OrderConfirmations | None = None) -> RunData:
    """`confirmations`: the Review answers, read by both stages (2E-e2)."""
    mapping = mapping or MAPPING
    df = pd.DataFrame(rows)
    metrics = assemble_metrics(df, mapping, now=NOW, confirmations=confirmations)
    return build_run_data(df, mapping, metrics, confirmations)


def daily_months(revenue_by_month: dict[str, float]) -> list[dict]:
    """One row on EVERY calendar day, each month's days sharing its revenue.

    For tests about a monthly total that also pass D1's coverage checks: a
    one-row-per-month file has ~30 zero-sale days a month, which D1 (and T2's
    year-ago check, 3E1) correctly reads as a pattern with fractional excess.
    """
    rows = []
    for month, value in revenue_by_month.items():
        year, number = int(month[:4]), int(month[5:7])
        days = (date(year + number // 12, number % 12 + 1, 1) - date(year, number, 1)).days
        for offset in range(days):
            rows.append(row(date(year, number, 1) + timedelta(days=offset), qty=1.0,
                            price=value / days))
    return rows


def full_months(revenue_by_month: dict[str, float], *, price: float = 10.0) -> list[dict]:
    """One row per month carrying that month's whole revenue.

    For tests about the monthly series itself (XmR limits), where daily
    coverage is irrelevant and controlling the exact monthly value is what
    matters. The first month's row sits on its first day and the last month's
    on its last, so `data_start` and `data_end` close both ends and every
    month in between counts as complete.
    """
    months = list(revenue_by_month)
    rows = []
    for month in months:
        year, number = int(month[:4]), int(month[5:7])
        if month == months[-1]:
            index = year * 12 + number
            day = date(index // 12, index % 12 + 1, 1) - timedelta(days=1)
        else:
            day = date(year, number, 1)
        rows.append(row(day, qty=revenue_by_month[month] / price, price=price))
    return rows
