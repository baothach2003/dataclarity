"""Stage 2 Analyze - the `customers` block of metrics.json
(docs/CONTRACTS.md section 6): RFM scoring + segment assignment. Pure
pandas; no AI call in this stage (docs/adr/0002-pandas-computes-ai-interprets.md).
Reuses `stages.analyze.metrics_core`'s row parsing and revenue-scope
convention (2A) instead of redefining them - same stage package, so the
import is not a cross-stage dependency (CLAUDE.md 3.1).

Design decisions (Thach, Phase 2B):
- RFM is one whole-file snapshot per docs/SPECS.md section 7.3 ("quintiles on
  the run's own data"; reference date = max(transaction_date) + 1 day), not
  scoped to the current/previous period - reuses metrics_core's
  `Period.data_end` directly (docs/CONTRACTS.md section 6's own worked
  example: data_end 2011-12-09 -> rfm_reference_date 2011-12-10), so both
  blocks agree on the same date.
- Segment rules (R = Recency score, F = Frequency score, both quintiles 1-5,
  5 = best): Champions R>=4&F>=4, Loyal R>=3&F>=3, At-risk R<=2&F>=3,
  Hibernating R<=2&F<=2, New R>=4&F<=1, and "Needs Attention" for the 4 of 25
  R x F combinations the five rules above leave unclassified ((3,1), (3,2),
  (4,2), (5,2) - a customer who is reasonably recent but low-to-middling
  frequency). `segment` is a plain string in the contract, so a sixth value
  validates fine (contracts/metrics.py).
- Quintiles are rank-based (ties broken by `rank(method="first")` before
  `qcut`), so a genuine quintile (five equal-sized groups) survives even with
  many tied Recency/Frequency values - verified empirically that this also
  spreads 2, 3 or 4 distinct customers across 1-5 without error. A single
  customer has no one to rank against and scores 5 and 5 (best available):
  a sample of one cannot be meaningfully placed on a 1-5 scale otherwise.
- A return-only customer (their only revenue-counted row has negative
  quantity, 2A's return convention) is scored and segmented like any other
  customer; Monetary is honestly negative, no special case.
- `customers_previous` re-runs the same snapshot truncated to transactions
  through the end of the previous period, anchored the day after it, so it
  shows real segment migration (matches the worked example: 129 Champions
  last period -> 118 now).
- No mapped `customer` column: the whole block degrades to empty
  (`segments: []`, `new_vs_returning` all zero) rather than raise, since
  `customer` is not a stage 1 required field (mirrors 2A's
  active_customers = 0 in the same situation).
- No mapped `unit_price`, by contrast, is NOT degraded here: `parse_transactions`
  raises `RequiredColumnMissingError` and this module lets it propagate,
  unchanged from 2A. Monetary cannot be computed without a price any more
  than core.revenue_current can (docs/adr/0002), and a "customers" block with
  every Monetary fabricated as 0 would be actively wrong, not merely
  incomplete - unlike the customer-identity gap above, there is no honest
  degraded shape to fall back to.
"""

import calendar
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pandas as pd

from contracts.cleaning import CleaningReportContract
from contracts.metrics import CustomerMetrics, NewVsReturning, Period, SegmentSummary
from shared.run_registry import run_file
from shared.transactions import customer_identity, is_blank, parse_transactions
from stages.analyze.metrics_core import (
    CLEANED_FILENAME,
    CLEANING_REPORT_FILENAME,
    select_period,
)

NEEDS_ATTENTION = "Needs Attention"


def _empty_new_vs_returning() -> NewVsReturning:
    # A fresh instance every call: ContractModel is not frozen, so a single
    # module-level constant returned by reference from three call sites would
    # let an in-place mutation on one "empty" result (e.g. a caller rounding
    # or annotating a response before serializing) leak into every other
    # degraded run for the rest of the process's life.
    return NewVsReturning(new_customers=0, returning_customers=0, new_revenue=0.0, returning_revenue=0.0)


def customer_metrics_for_run(
    runs_root: Path, run_id: str, now: datetime | None = None
) -> CustomerMetrics:
    """Read runs/<run_id>/cleaned.csv and cleaning_report.json and compute
    `customers`. `period` is recomputed the same way metrics_core does (the
    same run always yields the same period), so this stays independently
    runnable without also computing `core`. Writes nothing."""
    report = CleaningReportContract.model_validate_json(
        run_file(runs_root, run_id, CLEANING_REPORT_FILENAME).read_text(encoding="utf-8")
    )
    frame = pd.read_csv(run_file(runs_root, run_id, CLEANED_FILENAME), dtype=str)
    parsed = parse_transactions(frame, report.column_mapping)
    period = select_period(parsed.dates, now or datetime.now(UTC))
    return compute_customer_metrics(frame, report.column_mapping, period)


def compute_customer_metrics(
    df: pd.DataFrame, column_mapping: dict[str, str], period: Period
) -> CustomerMetrics:
    """Pure computation. `period` is metrics_core's `Period` for this same
    run (docs/CONTRACTS.md section 6 has one `period` shared by every
    block)."""
    parsed = parse_transactions(df, column_mapping)
    reference_date = period.data_end + timedelta(days=1)
    customer_col = parsed.reverse.get("customer")

    if customer_col is None:
        return CustomerMetrics(
            rfm_reference_date=reference_date,
            segments=[],
            new_vs_returning=_empty_new_vs_returning(),
        )

    # A counted row with no customer value, or one holding only whitespace
    # (customer is not a required field, so stage 1 has no reason to have
    # trimmed it), cannot be attributed to anyone.
    identified = parsed.counted & ~is_blank(df[customer_col])
    table = pd.DataFrame(
        {
            # The normalised identity (3C2), so RFM, the segment counts and
            # new-vs-returning all rank one customer once. Keyed raw, a
            # customer written two ways was two customers with half the
            # frequency and half the monetary value each, which moves them
            # down the RFM quintiles and can invent a "Needs Attention"
            # segment member out of a loyal one.
            "customer": customer_identity(df.loc[identified, customer_col]),
            "date": parsed.dates[identified],
            "revenue": parsed.revenue_amounts[identified],
        }
    )

    snapshot = rfm_snapshot(table, reference_date)

    previous_end = _month_end(period.previous)
    previous_reference = previous_end + timedelta(days=1)
    previous_table = table[table["date"] < pd.Timestamp(previous_reference)]
    previous_snapshot = rfm_snapshot(previous_table, previous_reference)
    previous_counts = (
        previous_snapshot["segment"].value_counts() if not previous_snapshot.empty else pd.Series(dtype=int)
    )

    segments = [
        SegmentSummary(
            segment=name,
            customers=customers,
            revenue_share_pct=share_pct,
            avg_monetary=avg_monetary,
            customers_previous=int(previous_counts.get(name, 0)),
        )
        for name, customers, share_pct, avg_monetary in _segment_summary(snapshot)
    ]

    return CustomerMetrics(
        rfm_reference_date=reference_date,
        segments=segments,
        new_vs_returning=_new_vs_returning(table, period),
    )


def rfm_snapshot(table: pd.DataFrame, reference_date: date) -> pd.DataFrame:
    """One row per customer: last_purchase, frequency, monetary, recency_days,
    r_score, f_score, segment - over every row in `table` (already
    revenue-counted and customer-identified), anchored at `reference_date`."""
    if table.empty:
        return pd.DataFrame(
            columns=["last_purchase", "frequency", "monetary", "recency_days", "r_score", "f_score", "segment"]
        )
    grouped = table.groupby("customer").agg(
        last_purchase=("date", "max"),
        frequency=("date", "size"),
        monetary=("revenue", "sum"),
    )
    grouped["recency_days"] = (pd.Timestamp(reference_date) - grouped["last_purchase"]).dt.days
    grouped["r_score"] = score_quintile(grouped["recency_days"], ascending=False)
    grouped["f_score"] = score_quintile(grouped["frequency"], ascending=True)
    grouped["segment"] = [
        assign_segment(r, f) for r, f in zip(grouped["r_score"], grouped["f_score"], strict=True)
    ]
    return grouped


def score_quintile(values: pd.Series, *, ascending: bool) -> pd.Series:
    """Rank-based quintiles (1-5, 5 is always "best" given `ascending`): ties
    are broken by `rank(method="first")` so a genuine quintile (five
    equal-sized groups) survives even when many customers share the same
    Recency or Frequency value. `ascending=False` scores the smallest raw
    value as 5 (Recency: fewest days since purchase is best);
    `ascending=True` scores the largest raw value as 5 (Frequency: most
    orders is best). A single customer has no one to rank against and scores
    5 (Thach's decision, Phase 2B)."""
    if len(values) == 1:
        return pd.Series([5], index=values.index)
    ranks = values.rank(method="first", ascending=ascending)
    return pd.qcut(ranks, 5, labels=[1, 2, 3, 4, 5]).astype(int)


def assign_segment(r_score: int, f_score: int) -> str:
    if r_score >= 4 and f_score >= 4:
        return "Champions"
    if r_score >= 3 and f_score >= 3:
        return "Loyal"
    if r_score <= 2 and f_score >= 3:
        return "At-risk"
    if r_score <= 2 and f_score <= 2:
        return "Hibernating"
    if r_score >= 4 and f_score <= 1:
        return "New"
    return NEEDS_ATTENTION


def _segment_summary(snapshot: pd.DataFrame) -> list[tuple[str, int, float, float]]:
    if snapshot.empty:
        return []
    total_monetary = float(snapshot["monetary"].sum())
    # abs(): a whole-file total that is net negative (a return-heavy dataset)
    # would otherwise flip every segment's sign - a small revenue-positive
    # segment showing a negative "share" while the dominant loss-making one
    # shows over 100%. Dividing by the magnitude keeps each segment's own
    # sign meaningful (a shrinking/negative segment still reads as negative)
    # while a share still means "this segment's part of the whole".
    denominator = abs(total_monetary)
    rows: list[tuple[str, int, float, float]] = []
    for segment, group in snapshot.groupby("segment"):
        segment_monetary = float(group["monetary"].sum())
        customers = int(len(group))
        share_pct = (segment_monetary / denominator * 100) if denominator else 0.0
        rows.append((str(segment), customers, share_pct, segment_monetary / customers))
    return rows


def _new_vs_returning(table: pd.DataFrame, period: Period) -> NewVsReturning:
    if table.empty:
        return _empty_new_vs_returning()

    months = table["date"].dt.to_period("M").astype(str)
    current_rows = table[months == period.current]
    if current_rows.empty:
        return _empty_new_vs_returning()

    first_purchase_month = table.groupby("customer")["date"].min().dt.to_period("M").astype(str)
    current_customers = current_rows["customer"].unique()
    is_first_period = first_purchase_month.loc[current_customers] == period.current
    new_customers = set(is_first_period[is_first_period].index)

    revenue_by_customer = current_rows.groupby("customer")["revenue"].sum()
    new_revenue = float(revenue_by_customer.loc[revenue_by_customer.index.isin(new_customers)].sum())
    total_revenue = float(revenue_by_customer.sum())

    return NewVsReturning(
        new_customers=len(new_customers),
        returning_customers=len(current_customers) - len(new_customers),
        new_revenue=new_revenue,
        returning_revenue=total_revenue - new_revenue,
    )


def _month_end(year_month: str) -> date:
    year, month = int(year_month[:4]), int(year_month[5:7])
    return date(year, month, calendar.monthrange(year, month)[1])
