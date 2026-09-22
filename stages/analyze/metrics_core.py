"""Stage 2 Analyze - the `period` and `core` blocks of metrics.json
(docs/CONTRACTS.md section 6). Pure pandas; no AI call exists anywhere in
this stage (docs/adr/0002-pandas-computes-ai-interprets.md). Assembling the
full metrics.json contract (the `customers`, `products` and `by_dimension`
blocks) and writing it to disk are later sub-phases (2B-2D); this module only
computes these two blocks from cleaned.csv.

Design decisions (Thach, Phase 2A - `transaction_type` is stock movement
direction only, docs/AI_PIPELINE.md section 5, never a returns concept):
- A row counts toward revenue only when its transaction_type is "out" (a
  sale); "in" rows (stock coming back, e.g. a supplier restock) are excluded
  from revenue entirely, never subtracted. A row with no transaction_type
  column mapped at all, or an unrecognised per-row value, defaults to "out"
  (docs/SPECS.md section 9: "in|out, default out").
- A return is a counted row with negative quantity (the common POS
  convention of a negative-quantity sale line). The canonical schema has no
  dedicated returns field, so this is the one signal available, and it does
  not depend on transaction_type being mapped.
- Zero-denominator metrics (revenue_change_pct with no previous revenue; aov
  and return_rate with no orders) report 0.0.
"""

import calendar
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

import pandas as pd

from contracts.cleaning import CleaningReportContract
from contracts.metrics import CoreMetrics, MonthlyRevenue, Period
from shared.run_registry import run_file

CLEANED_FILENAME = "cleaned.csv"
CLEANING_REPORT_FILENAME = "cleaning_report.json"


class RequiredColumnMissingError(ValueError):
    """cleaned.csv has no column mapped to a canonical field this module
    needs. transaction_date and quantity are stage 1 required fields, so this
    is defensive for them; unit_price is not required by stage 1
    (docs/AI_PIPELINE.md section 11), so it is the realistic case."""


@dataclass(frozen=True)
class ParsedTransactions:
    """cleaned.csv's transaction columns, parsed once and typed. Every other
    module in this stage that needs revenue-scoped rows (metrics_customers,
    later metrics_products) builds on this instead of re-parsing cleaned.csv
    or re-deciding what counts as a sale - same stage package, so importing
    it is not a cross-stage dependency (CLAUDE.md 3.1)."""

    reverse: dict[str, str]  # canonical field -> source column name
    dates: pd.Series  # tz-naive datetime64, NaT where unparseable
    quantities: pd.Series  # float, NaN where unparseable
    prices: pd.Series  # float, NaN where unparseable
    revenue_amounts: pd.Series  # quantities * prices
    # date/quantity/price all present, regardless of transaction_type.
    valid: pd.Series
    # `valid` AND counts toward revenue per 2A's decision (below): excludes
    # only rows explicitly "in". `valid & ~counted` is every explicit "in"
    # row (metrics_products.py's stock-in side).
    counted: pd.Series


def parse_transactions(df: pd.DataFrame, column_mapping: dict[str, str]) -> ParsedTransactions:
    """`column_mapping` is cleaning_report.json's mapping of source column
    name -> canonical field. Raises RequiredColumnMissingError if
    transaction_date, quantity or unit_price has no mapped column."""
    reverse = {field: source for source, field in column_mapping.items()}

    date_col = require_column(reverse, "transaction_date")
    quantity_col = require_column(reverse, "quantity")
    price_col = require_column(reverse, "unit_price")

    # utc=True avoids a crash on a file mixing offset and offset-less
    # datetimes (pandas otherwise refuses to build one Series from both); the
    # result is dropped back to naive for period/month grouping.
    dates = pd.to_datetime(df[date_col], format="mixed", errors="coerce", utc=True).dt.tz_localize(None)
    quantities = pd.to_numeric(df[quantity_col], errors="coerce")
    prices = pd.to_numeric(df[price_col], errors="coerce")

    # A row with no parseable date, quantity or price cannot be measured or
    # placed in a period; it is left out rather than guessed at.
    valid = dates.notna() & quantities.notna() & prices.notna()

    type_col = reverse.get("transaction_type")
    if type_col is None:
        counts_as_sale = pd.Series(True, index=df.index)
    else:
        # astype(object): an empty or all-missing column can read back as
        # float64, and .str only works on an object/string dtype. NaN (a
        # per-row missing type) compares False to "in", so it also defaults
        # to "out", matching the column-level default.
        counts_as_sale = ~df[type_col].astype(object).str.strip().str.lower().eq("in")

    return ParsedTransactions(
        reverse=reverse,
        dates=dates,
        quantities=quantities,
        prices=prices,
        revenue_amounts=quantities * prices,
        valid=valid,
        counted=valid & counts_as_sale,
    )


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


def require_column(reverse: dict[str, str], canonical_field: str) -> str:
    column = reverse.get(canonical_field)
    if column is None:
        raise RequiredColumnMissingError(
            f"cleaned.csv has no column mapped to '{canonical_field}'; "
            "stage 2 core metrics cannot be computed without it"
        )
    return column


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
    values = df.loc[mask, customer_col]
    return int(values[~is_blank(values)].nunique())


def is_blank(values: pd.Series) -> pd.Series:
    """True where a cell is missing or holds only whitespace - the same
    definition of "missing" docs/AI_PIPELINE.md section 6 uses for
    drop_rows_missing, applied here to an optional column (`customer`) stage
    1 has no reason to have trimmed. Shared with metrics_customers.py so both
    blocks agree on who counts as an identified customer."""
    return values.isna() | (values.astype(object).str.strip() == "")


def _safe_divide(numerator: float, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def pct_change(current: float, previous: float) -> float:
    return (current - previous) / previous * 100 if previous else 0.0


def _revenue_by_month(months: pd.Series, amounts: pd.Series) -> list[MonthlyRevenue]:
    if months.empty:
        return []
    # "YYYY-MM" zero-padded sorts identically as a string or chronologically.
    totals = amounts.groupby(months).sum().sort_index()
    return [MonthlyRevenue(period=period, revenue=float(total)) for period, total in totals.items()]
