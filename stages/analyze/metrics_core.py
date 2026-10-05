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
only; a return is a counted row with negative quantity and, since 2E-c2, a
negative amount) are documented there.

Design decisions that stay here, because they are about this contract's own
fields:
- aov and return_rate with no orders are null with a reason. This SUPERSEDES
  2A's "a zero denominator reports 0.0" (Thach, 2E): "AOV 0" was a false
  statement about a month with no orders, not the absence of one, and 2.0
  lets the contract say "unavailable".
- An order is a sale row (shared/transactions.py, 2E) - or, with order_id
  mapped, a distinct order id with a sale row (shared/orders.py, 2E-e): aov =
  NET revenue / orders, so customers x frequency x aov is net revenue exactly
  (stage 3's lever); return_rate = returns / orders on the same basis, and can
  exceed 1.
- revenue_change_pct is null with a reason when the previous month is not a
  base: incomplete in the file (shared/periods.py), or a non-positive or
  residue base (shared/numbers.pct_change) - never 2A's 0.0, which said
  "nothing moved" when revenue appeared from nothing (2E).
"""

from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from contracts.cleaning import CleaningReportContract, OrderConfirmations
from contracts.metrics import CoreMetrics, MonthlyRevenue, NonProductLines, Period
from shared import line_report
from shared.date_evidence import month_grain
from shared.numbers import pct_change
from shared.orders import count_orders
from shared.periods import after_cutoff, upload_cutoff
from shared.run_registry import run_file
from shared.transactions import (
    # Re-exported deliberately: this error is part of what calling stage 2
    # can raise, and both the backend and this stage's tests catch it here.
    ParsedTransactions,
    RequiredColumnMissingError,
    parse_transactions,
)
from stages.analyze import metrics_lines
from stages.analyze.future_lines import future_lines
from stages.analyze.period_selection import select_period

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
    return compute_core_metrics(frame, report.column_mapping, now, report.applied_confirmations())


def choose_period(parsed: ParsedTransactions, now: datetime, uploaded_at: datetime | None = None
                  ) -> tuple[Period, pd.Series]:
    """The period, and the lines dated after the upload (2E-u6), for every
    block of stage 2 - one choice, whichever block runs. Such a line chooses
    nothing: not the dates the file covers, the month grain, the months
    compared or their coverage. The upload is the reference - for those
    lines and for a month-grain file's clock (`now` without one): a monthly
    export uploaded mid-month holds a month-to-date row whatever day it is
    analysed (2E-u6 review 1, #1: re-analysed after the month ended, the
    row was compared as a whole month, -36.7%)."""
    reference = uploaded_at or now
    cutoff = upload_cutoff(reference)
    future = after_cutoff(parsed.dates, cutoff)
    dated = parsed.dates.where(~future)
    period = select_period(dated, reference, dated[parsed.sale], grain=month_grain(dated[parsed.counted]))
    return period.model_copy(update={"upload_cutoff": cutoff}), future


def compute_core_metrics(
    df: pd.DataFrame, column_mapping: dict[str, str], now: datetime | None = None,
    confirmations: OrderConfirmations | None = None, *, uploaded_at: datetime | None = None,
) -> tuple[Period, CoreMetrics]:
    """Pure computation. `column_mapping` is cleaning_report.json's mapping of
    source column name -> canonical field, `confirmations` its answers from
    Review (2E-e2), `uploaded_at` the run's upload time (2E-u6; `now`
    without one)."""
    now = now or datetime.now(UTC)
    parsed = parse_transactions(df, column_mapping, confirmations)
    period, future = choose_period(parsed, now, uploaded_at)

    months = parsed.dates.dt.to_period("M").astype(str)
    current_mask = parsed.counted & (months == period.current)
    previous_mask = parsed.counted & (months == period.previous)

    revenue_current, orders_current, customers_current, returns_current = _bucket(
        parsed, current_mask
    )
    revenue_previous, orders_previous, customers_previous, returns_previous = _bucket(
        parsed, previous_mask
    )

    if period.previous_complete:
        # Residue judged against the money that moved in both months (F6).
        moved = float(parsed.revenue_amounts[current_mask | previous_mask].abs().sum())
        change = pct_change(revenue_current, revenue_previous, moved)
    else:
        change = (None, period.previous_incomplete_reason)
    # The amount needs no base, so only an incomplete previous month nulls it
    # (the report redesign, step 1): never compared (CONTRACTS 11).
    amount = ((revenue_current - revenue_previous, None) if period.previous_complete
              else (None, period.previous_incomplete_reason))
    core = CoreMetrics(
        revenue_current=revenue_current,
        revenue_previous=revenue_previous,
        revenue_change_pct=change[0],
        revenue_change_pct_reason=change[1],
        revenue_change=amount[0],
        revenue_change_reason=amount[1],
        orders_basis=parsed.orders_basis,
        orders_basis_reason=parsed.orders_basis_reason,
        orders_current=orders_current,
        orders_previous=orders_previous,
        active_customers_current=customers_current,
        active_customers_previous=customers_previous,
        buyers_current=_active_customers(parsed, current_mask & parsed.sale),
        buyers_previous=_active_customers(parsed, previous_mask & parsed.sale),
        **_per_order("aov_current", revenue_current, orders_current, period.current),
        **_per_order("aov_previous", revenue_previous, orders_previous, period.previous),
        **_per_order("return_rate_current", returns_current, orders_current, period.current),
        **_per_order("return_rate_previous", returns_previous, orders_previous,
                     period.previous),
        revenue_by_month=_revenue_by_month(months[parsed.counted], parsed.revenue_amounts[parsed.counted]),
        **_undated(parsed),
        **future_lines(parsed, future, period.upload_cutoff),
        non_product=_non_product(parsed, months, period),
        identity=metrics_lines.revenue_identity(parsed, months, period),
        outside_revenue=metrics_lines.outside_revenue(parsed, months, period),
        unclassified=line_report.unclassified(parsed),
        unmeasurable=metrics_lines.unmeasurable(parsed, months, period),
        notes=metrics_lines.notes(df, parsed, months, period),
    )
    return period, core


# Per class: the singular and plural of what happened to its lines (2E-d2).
_NON_PRODUCT_REASONS = {
    # No order since 2E-l (Thach): an invoice holding only charges is no purchase.
    "charge": ("1 line classed in Review as a charge paid by the customer stays in revenue, is "
               "no order, and is in no product table",
               "{n} lines classed in Review as charges paid by the customer stay in revenue, "
               "are no order, and are in no product table"),
    "discount": ("1 line classed in Review as a discount stays in revenue as a deduction: it is no "
                 "sale, no return, and in no product table",
                 "{n} lines classed in Review as discounts stay in revenue as deductions: they are "
                 "no sale, no return, and in no product table"),
    # Thach, 2E-l: Online Retail II's M "Manual", manually priced sales.
    "pooled": ("1 line classed in Review as pooled items (many items under one code) is a sale or "
               "return in every figure, but no product table ranks it",
               "{n} lines classed in Review as pooled items (many items under one code) are "
               "sales and returns in every figure, but no product table ranks them"),
    "cost": ("1 line classed in Review as a fee or cost is left out of revenue and of every figure",
             "{n} lines classed in Review as fees or costs are left out of revenue and of every "
             "figure"),
    # "Reported as a separate reconciling amount" (Thach). Not "the difference
    # between the file's total and the revenue shown": fees, "in" rows and
    # undated lines are out of revenue too (2E-d2 doubt-review F8).
    "adjustment": ("1 line classed in Review as an accounting adjustment is left out of revenue and "
                   "of every figure, and reported here as a reconciling amount",
                   "{n} lines classed in Review as accounting adjustments are left out of revenue and "
                   "of every figure, and reported here as a reconciling amount"),
    # Thach, the line taxonomy's decision 4 (2E-t1): a voucher sold is a
    # liability until redeemed, so neither revenue nor a sale.
    "gift_card": ("1 line classed in Review as a gift card is left out of revenue and of every figure: "
                  "a voucher sold is owed to the customer until it is redeemed",
                  "{n} lines classed in Review as gift cards are left out of revenue and of every "
                  "figure: a voucher sold is owed to the customer until it is redeemed"),
}


def _non_product(parsed: ParsedTransactions, months: pd.Series, period: Period) -> list[NonProductLines]:
    """The lines the user classed as not products, per class, over the dated
    lines of a counted type (Thach, 2E-d2): whether their money stayed in
    revenue or left it, a reader sees how much and where."""
    rows = []
    for line_class, (one, many) in _NON_PRODUCT_REASONS.items():
        mask = (parsed.counted | parsed.left_out) & parsed.line_class.eq(line_class)
        lines = int(mask.sum())
        if lines == 0:
            continue
        amounts = parsed.revenue_amounts[mask]
        rows.append(NonProductLines(
            line_class=line_class, lines=lines, amount=float(amounts.sum()),
            amount_current=float(amounts[months[mask] == period.current].sum()) + 0.0,
            amount_previous=float(amounts[months[mask] == period.previous].sum()) + 0.0,
            reason=one if lines == 1 else many.format(n=f"{lines:,}")))
    return rows


def _bucket(parsed: ParsedTransactions, mask: pd.Series) -> tuple[float, int, int, int]:
    """Net revenue and active customers over every counted row (3C: a
    returns-only customer is active); orders and returns over sale and return
    rows (2E)."""
    revenue = float(parsed.revenue_amounts[mask].sum())
    # Distinct orders (shared/orders.py, 2E-e): order ids when order_id is
    # mapped and trusted, else each line - so on lines these are line counts.
    orders = count_orders(parsed.order_key, mask & parsed.sale)
    customers = _active_customers(parsed, mask)
    returns = count_orders(parsed.order_key, mask & parsed.returned)
    return revenue, orders, customers, returns


def _active_customers(parsed: ParsedTransactions, mask: pd.Series) -> int:
    # The normalised identity, so one customer written several ways is one
    # active customer (3C2), filled from the receipt on header-style exports
    # (2E-f). Stage 3 reads the same series, which keeps the two stages'
    # active_customers figures equal. No customer column: all NaN, so 0.
    return int(parsed.customers[mask].nunique())


def _per_order(name: str, numerator: float, orders: int, month: str) -> dict:
    """`name` and `name_reason` for a figure per order: null with a reason
    when the month has no orders (orders are whole numbers, so no residue)."""
    if orders == 0:
        return {name: None, f"{name}_reason": f"no orders in {month}, so there is no "
                                              "per-order figure"}
    return {name: numerator / orders, f"{name}_reason": None}


def _undated(parsed: ParsedTransactions) -> dict:
    """How many lines have no readable date, and why (Thach, 2E-h): they are
    in no month and so in no figure, and a reader must see that rather than
    lose them silently. Blank cells and cells that are no date ("now", a bare
    time, a year outside 1900-2100, text that does not parse) are one count:
    a plan that parsed the date column has already turned every no-date
    blank, so a split between the two was wrong there (2E-h review F5).
    Since 2E-j a placeholder date and a day and month the file's date order
    cannot hold are no date too, and the reason names them."""
    # An unmeasurable line is reported once, there (Thach's Q24, 2E-t2).
    count = line_report.undated_lines(parsed)
    if count == 0:
        return {"undated_lines": 0, "undated_lines_reason": None}
    lines, rest = (("1 line has", "it belongs to no month and is") if count == 1 else
                   (f"{count:,} lines have", "they belong to no month and are"))
    return {"undated_lines": count,
            "undated_lines_reason": (
                f"{lines} no readable date - blank, or no date (such as \"now\", a time with "
                "no date, a year outside 1900-2100, a placeholder date such as 1900-01-01 or "
                "1970-01-01, a day and month the file's date order cannot hold, or text that "
                f"does not parse) - so {rest} left out of every month's figures (one outside revenue "
                "is still in the whole file's report of such lines)")}


def _revenue_by_month(months: pd.Series, amounts: pd.Series) -> list[MonthlyRevenue]:
    if months.empty:
        return []
    # "YYYY-MM" zero-padded sorts identically as a string or chronologically.
    totals = amounts.groupby(months).sum().sort_index()
    return [MonthlyRevenue(period=period, revenue=float(total)) for period, total in totals.items()]
