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
- Quintiles are rank-based: positions scored by `qcut` over
  `rank(method="first")` into five equal groups. 2B broke ties by that
  position; SUPERSEDED (Thach, 2E-c): identical customers get identical
  scores - a tied group takes the mean of its positions' scores, exact
  halves rounded down (stages/analyze/rfm.py `score_quintile`). A single
  customer has no one to rank against and scores 5 and 5 (best available):
  a sample of one cannot be meaningfully placed on a 1-5 scale otherwise.
- A customer who never bought (only refunds) is counted, with Monetary
  honestly negative, but SUPERSEDING 2B's "no special case" and "quintiles on
  the run's own data" for R and F (Thach, 2E-b): R and F are cut from BUYERS
  only, and a never-buyer scores 1/1 by rule in their own segment, "Returns
  only" - not Hibernating, which describes buyers who stopped. Ranked among
  buyers, 20 refunders pushed 10 lapsed one-time buyers up to Champions, and
  a tie-break lifted one refunder there too. Monetary is never quintiled (it
  feeds only avg_monetary and revenue_share_pct), so it has no population.
- Frequency counts the customer's ORDERS - sale rows (shared/transactions.py,
  Thach, session 2E) - not every counted row: three refund lines made a
  one-purchase customer look four times as frequent.
- Recency counts the last PURCHASE - a sale row - too (Thach, session 2E-b):
  a refund is not a purchase, and a customer who bought in January and
  refunded in November read as bought yesterday. A never-buyer's recency is
  one day beyond the file's oldest row. Monetary stays net.
- `customers_previous` re-runs the same snapshot truncated to transactions
  through the end of the previous period, anchored the day after it, so it
  shows real segment migration (matches the worked example: 129 Champions
  last period -> 118 now). It exists only to compare the two periods, so it
  is null, with the period's reason in `customers_previous_reason`, when the
  previous month is incomplete (Thach, 2E).
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
from shared.first_purchase import first_purchase_months
from shared.numbers import is_negligible
from shared.transactions import customer_identity, is_blank, parse_transactions
from stages.analyze.metrics_core import (
    CLEANED_FILENAME,
    CLEANING_REPORT_FILENAME,
    select_period,
)
from stages.analyze.rfm import rfm_snapshot

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
    period = select_period(parsed.dates, now or datetime.now(UTC), parsed.dates[parsed.sale])
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
    previous_reason = None if period.previous_complete else period.previous_incomplete_reason

    if customer_col is None:
        return CustomerMetrics(
            rfm_reference_date=reference_date,
            segments=[],
            new_vs_returning=_empty_new_vs_returning(),
            customers_previous_reason=previous_reason,
            revenue_share_reason=None,
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
            "sale": parsed.sale[identified],
            "returned": parsed.returned[identified],
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

    rows, share_reason = _segment_summary(snapshot, float(table["revenue"].abs().sum()))
    segments = [
        SegmentSummary(
            segment=name,
            customers=customers,
            revenue_share_pct=share_pct,
            avg_monetary=avg_monetary,
            customers_previous=(int(previous_counts.get(name, 0))
                                if previous_reason is None else None),
        )
        for name, customers, share_pct, avg_monetary in rows
    ]

    return CustomerMetrics(
        rfm_reference_date=reference_date,
        segments=segments,
        new_vs_returning=_new_vs_returning(table, period),
        customers_previous_reason=previous_reason,
        revenue_share_reason=share_reason,
    )


def _segment_summary(
    snapshot: pd.DataFrame, moved: float = 0.0,
) -> tuple[list[tuple[str, int, float | None, float]], str | None]:
    """Per segment: name, customers, share of whole-file monetary, average
    monetary; and why the shares are null, when they are. A whole file whose
    monetary nets to zero or residue has no whole to share (2E, superseding
    2A's 0.0; residue by shared/numbers.is_negligible, judged against `moved`,
    the whole file's gross money - per-customer nets that are themselves
    residue gave a segment "-100%" of it, 2E doubt-review cycle 2 F3)."""
    if snapshot.empty:
        return [], None
    total_monetary = float(snapshot["monetary"].sum())
    nothing = is_negligible(total_monetary, *snapshot["monetary"].abs(), moved)
    # abs(): a whole-file total that is net negative (a return-heavy dataset)
    # would otherwise flip every segment's sign - a small revenue-positive
    # segment showing a negative "share" while the dominant loss-making one
    # shows over 100%. Dividing by the magnitude keeps each segment's own
    # sign meaningful (a shrinking/negative segment still reads as negative)
    # while a share still means "this segment's part of the whole".
    denominator = abs(total_monetary)
    rows: list[tuple[str, int, float | None, float]] = []
    for segment, group in snapshot.groupby("segment"):
        segment_monetary = float(group["monetary"].sum())
        customers = int(len(group))
        share_pct = None if nothing else segment_monetary / denominator * 100
        rows.append((str(segment), customers, share_pct, segment_monetary / customers))
    reason = ("whole-file monetary is nothing (zero, or floating-point residue), so no "
              "segment has a share of it") if nothing else None
    return rows, reason


def _new_vs_returning(table: pd.DataFrame, period: Period) -> NewVsReturning:
    """New = the first purchase falls in the current month and the history
    does not open with a refund (shared/first_purchase.py, Thach, 2E-c): a
    refund proves a purchase before the file, so a refund-only customer is
    returning, with their negative money in returning_revenue. The first row
    of any kind called them new with negative "new revenue"."""
    if table.empty:
        return _empty_new_vs_returning()

    months = table["date"].dt.to_period("M").astype(str)
    current_rows = table[months == period.current]
    if current_rows.empty:
        return _empty_new_vs_returning()

    first_purchase = first_purchase_months(table["customer"], table["date"],
                                           table["sale"], table["returned"])
    current_customers = current_rows["customer"].unique()
    is_first_period = first_purchase.loc[current_customers] == period.current
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
