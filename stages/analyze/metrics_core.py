"""Stage 2 Analyze - the `period` and `core` blocks of metrics.json
(docs/CONTRACTS.md section 6). Pure pandas; no AI call exists anywhere in
this stage (docs/adr/0002-pandas-computes-ai-interprets.md). Assembling the
full metrics.json contract (the `customers`, `products` and `by_dimension`
blocks) and writing it to disk are later sub-phases (2B-2D); this module only
computes these two blocks from cleaned.csv.

What a row *is* - whether it parses, and whether it counts towards revenue -
is not decided here: `shared/transactions.py` owns that, so stage 3 can
recompute the same figures without importing this stage (CLAUDE.md 3.1). The
Phase 2A decisions behind it (transaction_type is stock movement direction
only; a return is a negative-quantity counted row) are documented there.

Design decision that stays here, because it is about this contract's own
fields: zero-denominator metrics (revenue_change_pct with no previous
revenue; aov and return_rate with no orders) report 0.0.
"""

import calendar
from datetime import UTC, date, datetime
from pathlib import Path

import pandas as pd

from contracts.cleaning import CleaningReportContract
from contracts.metrics import CoreMetrics, MonthlyRevenue, Period
from shared.run_registry import run_file
from shared.transactions import (
    # Re-exported deliberately: this error is part of what calling stage 2
    # can raise, and both the backend and this stage's tests catch it here.
    RequiredColumnMissingError,
    customer_identity,
    is_blank,
    parse_transactions,
    pct_change,
)

__all__ = [
    "CLEANED_FILENAME",
    "CLEANING_REPORT_FILENAME",
    "RequiredColumnMissingError",
    "compute_core_metrics",
    "core_metrics_for_run",
    "select_period",
]

CLEANED_FILENAME = "cleaned.csv"
CLEANING_REPORT_FILENAME = "cleaning_report.json"


def core_metrics_for_run(
    runs_root: Path, run_id: str, now: datetime | None = None
) -> tuple[Period, CoreMetrics]:
    """Read runs/<run_id>/cleaned.csv and cleaning_report.json and compute
    `period` and `core`. Writes nothing."""
    report = CleaningReportContract.model_validate_json(
        run_file(runs_root, run_id, CLEANING_REPORT_FILENAME).read_text(encoding="utf-8")
    )
    # Every value as raw text, like stage 1's own read (profiling.py): this
    # module converts exactly the columns it needs itself, rather than trust
    # pandas' column-by-column type inference on a file stage 1 need not have
    # cast (AI_PIPELINE.md section 12: a plan cannot require transaction_date
    # to be parsed).
    frame = pd.read_csv(run_file(runs_root, run_id, CLEANED_FILENAME), dtype=str)
    return compute_core_metrics(frame, report.column_mapping, now)


def compute_core_metrics(
    df: pd.DataFrame, column_mapping: dict[str, str], now: datetime | None = None
) -> tuple[Period, CoreMetrics]:
    """Pure computation. `column_mapping` is cleaning_report.json's mapping of
    source column name -> canonical field."""
    now = now or datetime.now(UTC)
    parsed = parse_transactions(df, column_mapping)
    period = select_period(parsed.dates, now)

    months = parsed.dates.dt.to_period("M").astype(str)
    current_mask = parsed.counted & (months == period.current)
    previous_mask = parsed.counted & (months == period.previous)

    revenue_current, orders_current, customers_current, returns_current = _bucket(
        df, parsed.reverse, current_mask, parsed.revenue_amounts, parsed.quantities
    )
    revenue_previous, orders_previous, customers_previous, returns_previous = _bucket(
        df, parsed.reverse, previous_mask, parsed.revenue_amounts, parsed.quantities
    )

    core = CoreMetrics(
        revenue_current=revenue_current,
        revenue_previous=revenue_previous,
        revenue_change_pct=pct_change(revenue_current, revenue_previous),
        orders_current=orders_current,
        orders_previous=orders_previous,
        active_customers_current=customers_current,
        active_customers_previous=customers_previous,
        aov_current=_safe_divide(revenue_current, orders_current),
        aov_previous=_safe_divide(revenue_previous, orders_previous),
        return_rate_current=_safe_divide(returns_current, orders_current),
        return_rate_previous=_safe_divide(returns_previous, orders_previous),
        revenue_by_month=_revenue_by_month(months[parsed.counted], parsed.revenue_amounts[parsed.counted]),
    )
    return period, core


def select_period(dates: pd.Series, now: datetime) -> Period:
    """`current` is the latest calendar month fully elapsed by the data's
    last date (docs/CONTRACTS.md section 6's worked example: data_end
    2011-12-09 -> current 2011-11, the partial December excluded); `previous`
    is the month before it. Whether an earlier month has any data of its own
    does not matter, only whether that month's own last day has passed.
    Falls back to `now`'s month when the data holds no parseable date at
    all."""
    valid = dates.dropna()
    if valid.empty:
        data_start = data_end = now.date()
    else:
        data_start = valid.min().date()
        data_end = valid.max().date()

    current = _last_complete_month(data_end)
    previous = _month_before(*current)
    return Period(
        current=_format_year_month(current),
        previous=_format_year_month(previous),
        data_start=data_start,
        data_end=data_end,
    )


def _last_complete_month(data_end: date) -> tuple[int, int]:
    year, month = data_end.year, data_end.month
    if data_end.day < calendar.monthrange(year, month)[1]:
        return _month_before(year, month)
    return year, month


def _month_before(year: int, month: int) -> tuple[int, int]:
    return (year - 1, 12) if month == 1 else (year, month - 1)


def _format_year_month(year_month: tuple[int, int]) -> str:
    year, month = year_month
    return f"{year:04d}-{month:02d}"


def _bucket(
    df: pd.DataFrame,
    reverse: dict[str, str],
    mask: pd.Series,
    revenue_amounts: pd.Series,
    quantities: pd.Series,
) -> tuple[float, int, int, int]:
    revenue = float(revenue_amounts[mask].sum())
    orders = int(mask.sum())
    customers = _active_customers(df, reverse, mask)
    returns = int((quantities[mask] < 0).sum())
    return revenue, orders, customers, returns


def _active_customers(df: pd.DataFrame, reverse: dict[str, str], mask: pd.Series) -> int:
    customer_col = reverse.get("customer")
    if customer_col is None:
        return 0
    # Keyed on the normalised identity, so one customer written several ways
    # is one active customer (3C2). Stage 3 keys the same way, which is what
    # keeps the two stages' active_customers figures equal.
    values = customer_identity(df.loc[mask, customer_col])
    return int(values[~is_blank(values)].nunique())


def _safe_divide(numerator: float, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def _revenue_by_month(months: pd.Series, amounts: pd.Series) -> list[MonthlyRevenue]:
    if months.empty:
        return []
    # "YYYY-MM" zero-padded sorts identically as a string or chronologically.
    totals = amounts.groupby(months).sum().sort_index()
    return [MonthlyRevenue(period=period, revenue=float(total)) for period, total in totals.items()]
