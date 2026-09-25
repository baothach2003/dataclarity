"""Stage 2 Analyze - the `products` block of metrics.json
(docs/CONTRACTS.md section 6): Pareto concentration, top products, biggest
decliners, velocity + stockout projection. Pure pandas; no AI call in this
stage (docs/adr/0002-pandas-computes-ai-interprets.md). Reuses
`stages.analyze.metrics_core`'s row parsing, revenue-scope and
zero-denominator conventions (2A) instead of redefining them - same stage
package, so the import is not a cross-stage dependency (CLAUDE.md 3.1).

Design decisions (Thach, Phase 2C):
- Stockout: Stage 2 has no "current stock" field at all (no canonical field
  for it, and docs/SPECS.md section 9's "net in minus out, floored at 0"
  formula is textually scoped to Phase 7's DB import). This module derives
  the same balance from cleaned.csv's own whole-file history instead: every
  "in" row (stock coming back, e.g. a supplier restock) adds, every
  counted/"out" row subtracts (a return's negative quantity nets back in
  automatically, the same sign logic as 2A's revenue), floored at 0.
- Velocity window: `period.current` (the same calendar month every other
  block already uses), not the Dashboard's own fixed 14-day window
  (docs/SPECS.md section 4.5) - that number is for a live, DB-backed surface
  querying real "now"; a static file upload has no "now" to anchor a rolling
  window to.
- A product that sold no units this period (sale lines, 2E-g) is omitted
  from `velocity` entirely: an undefined days_to_stockout is neither
  meaningful nor valid. A product only ever "in" never enters the list.
- SUPERSEDED in part (Thach, 2E-g): the stock derivation assumed files with
  inbound movements, while most POS exports are sales only. A file with no
  stock-in line has no `velocity` (null, `velocity_reason`); in a file that
  has some, a product with none has a null `days_to_stockout` with a
  reason. Floored at 0, both demo files read "0 days to stockout" for every
  product. Phase 7's Dashboard low-stock table rests on the same assumption.
- `top_products` and `biggest_decliners` are each capped at the 10
  highest-ranked entries (revenue descending / revenue_change ascending
  respectively), ties broken by product name for a deterministic,
  hand-checkable order. `velocity` is unbounded and sorted soonest-to-run-out
  first: it is a stockout-risk inventory, not a leaderboard, so every
  product with measurable velocity appears.
- Product identity and the displayed name come from shared/products.py
  (Thach, 2E-g), so stage 3 names every product as this block does: the SKU
  when a line has one, else the name (a name-only line takes the one SKU
  its name is sold under); the label is the name the product's sale lines
  carry most over the whole file. A line with neither SKU nor name is the
  "(no product name)" data gap: in no table (it was ranked as a product).
- Units sold (`top_products.units`, velocity's units a day) count sale
  lines only (2E-g).
- `top_products` excludes a net-negative-revenue product (returns
  outweighing sales for that product this period): it is not a "top"
  performer.
- `biggest_decliners` (Thach, session 2E): every product with previous-period
  revenue whose revenue FELL, ranked by the fall in money (`revenue_change`,
  most negative first). Ranking by percentage inverted the list for any
  product with a negative previous period: a loss that doubled (-100 -> -200)
  scored +100% and was dropped, and a recovery (-100 -> +500) scored -600% and
  was ranked the biggest decliner. The percentage is still reported beside
  the money, null with a reason where its base is not positive
  (shared/numbers.pct_change). The whole list is null, with the period's
  reason, when the previous month is incomplete: every entry compares it.
"""

import calendar
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from contracts.cleaning import CleaningReportContract, OrderConfirmations
from contracts.metrics import Pareto, Period, ProductDecline, ProductMetrics, ProductVelocity, TopProduct
from shared.numbers import is_negligible, pct_change
from shared.products import product_keys, product_labels
from shared.run_registry import run_file
from shared.transactions import ParsedTransactions, is_stock_in, parse_transactions, require_column
from stages.analyze.metrics_core import (
    CLEANED_FILENAME,
    CLEANING_REPORT_FILENAME,
    select_period,
)

TOP_PRODUCTS_LIMIT = 10
BIGGEST_DECLINERS_LIMIT = 10


def product_metrics_for_run(
    runs_root: Path, run_id: str, now: datetime | None = None
) -> ProductMetrics:
    """Read runs/<run_id>/cleaned.csv and cleaning_report.json and compute
    `products`. `period` is recomputed the same way metrics_core does (the
    same run always yields the same period), so this stays independently
    runnable without also computing `core`. Writes nothing."""
    report = CleaningReportContract.model_validate_json(
        run_file(runs_root, run_id, CLEANING_REPORT_FILENAME).read_text(encoding="utf-8")
    )
    frame = pd.read_csv(run_file(runs_root, run_id, CLEANED_FILENAME), dtype=str)
    parsed = parse_transactions(frame, report.column_mapping, report.confirmations)
    period = select_period(parsed.dates, now or datetime.now(UTC), parsed.dates[parsed.sale])
    return compute_product_metrics(frame, report.column_mapping, period, report.confirmations)


def compute_product_metrics(
    df: pd.DataFrame, column_mapping: dict[str, str], period: Period,
    confirmations: OrderConfirmations | None = None,
) -> ProductMetrics:
    """Pure computation."""
    parsed = parse_transactions(df, column_mapping, confirmations)
    require_column(parsed.reverse, "product_name")

    # Keys and labels are stage 3's too (shared/products.py). A line with no
    # SKU and no name is the data gap: its money is in every total, but it is
    # no product, so no table ranks it (Thach, 2E-c2 and 2E-g) - it was the
    # top product and the biggest decliner of a file with unnamed lines.
    identity = product_keys(df, parsed)
    names = product_labels(df, parsed, identity)

    table = pd.DataFrame({
        "identity": identity,
        "quantity": parsed.quantities,
        # Units sold are sale lines' units (Thach, 2E-g, D1): a write-off or
        # a free item is not a unit sold (739 Online Retail II products read
        # differently in 2011-11).
        "sold": parsed.quantities.where(parsed.sale, 0.0),
        "revenue": parsed.revenue_amounts,
        "day": parsed.dates.dt.normalize(),
    })
    months = parsed.dates.dt.to_period("M").astype(str)
    product = identity.notna()

    current = table[parsed.counted & product & (months == period.current)]
    previous = table[parsed.counted & product & (months == period.previous)]
    stock_in = _stock_in(df, parsed)
    all_in = table[stock_in & product]
    all_out = table[parsed.counted & product]

    if period.previous_complete:
        decliners, decliners_reason = _biggest_decliners(current, previous, names), None
    else:
        decliners, decliners_reason = None, period.previous_incomplete_reason
    # Stock on hand is derived from stock-in lines (2C), which most POS
    # exports do not have: floored at 0, every product of both demo files read
    # "0 days to stockout" (2,832 of 2,858 on Online Retail II). No stock-in
    # line in the file, no velocity at all, with one reason (Thach, 2E-g).
    if stock_in.any():
        velocity = _velocity(current, all_in, all_out, names, _days_in_month(period.current))
        velocity_reason = None
    else:
        velocity, velocity_reason = None, NO_STOCK_IN_FILE
    return ProductMetrics(
        pareto=_pareto(current, period.current),
        top_products=_top_products(current, names),
        biggest_decliners=decliners,
        biggest_decliners_reason=decliners_reason,
        velocity=velocity,
        velocity_reason=velocity_reason,
    )


def _stock_in(df: pd.DataFrame, parsed: ParsedTransactions) -> pd.Series:
    """Stock-in lines: transaction type "in" (read as `parse_transactions`
    reads it) with a date and a quantity. No price is needed - goods received
    are often written without a sale price, and requiring one (a counted
    line's rule) made such a file read as having no stock-in line at all
    (2E-g doubt-review F1)."""
    column = parsed.reverse.get("transaction_type")
    if column is None:
        return pd.Series(False, index=df.index)
    # The one reading of "in" revenue scope uses too (cycle 2, F4).
    return is_stock_in(df[column]) & parsed.dates.notna() & np.isfinite(parsed.quantities)


NO_STOCK_IN_FILE = ("the file has no stock-in lines (transaction type \"in\"), so stock on hand "
                    "cannot be derived and no product has a days-to-stockout figure")
NO_STOCK_IN_PRODUCT = ("the file records no stock-in line for this product, so its stock on "
                       "hand is unknown")
INCOMPLETE_STOCK_HISTORY = ("more of this product went out than the file records coming in, so "
                            "its stock history is incomplete and its stock on hand is unknown")


def _pareto(current: pd.DataFrame, month: str) -> Pareto:
    # Same population as _top_products (revenue > 0): a product that net
    # returned more than it sold this period isn't a revenue driver, and
    # counting it here while excluding it from top_products would make the
    # two numbers in the same contract object describe different products.
    by_product = current.groupby("identity")["revenue"].sum()
    by_product = by_product[by_product > 0]
    total_products = int(len(by_product))
    total_revenue = float(by_product.sum())
    # Every product here has positive revenue, so total_revenue > 0 whenever
    # there is one. With none, the share is null with a reason (2E,
    # superseding 2A's 0.0 - "0% concentration" described a month with no
    # sales at all).
    if total_products == 0:
        return Pareto(products_for_80pct_revenue=0, total_products=0, concentration_pct=None,
                      concentration_reason=f"no product has positive revenue in {month}")

    cumulative = by_product.sort_values(ascending=False).cumsum()
    threshold = total_revenue * 0.8
    # The smallest prefix (highest-revenue products first) whose cumulative
    # revenue reaches the threshold: every product still strictly below it
    # is not enough on its own, plus the one that crosses it.
    count_for_80pct = min(int((cumulative < threshold).sum()) + 1, total_products)

    return Pareto(
        products_for_80pct_revenue=count_for_80pct,
        total_products=total_products,
        concentration_pct=count_for_80pct / total_products * 100,
        concentration_reason=None,
    )


def _top_products(current: pd.DataFrame, names: pd.Series) -> list[TopProduct]:
    grouped = current.groupby("identity").agg(revenue=("revenue", "sum"), units=("sold", "sum"))
    grouped = grouped[grouped["revenue"] > 0]
    if grouped.empty:
        return []
    grouped = grouped.assign(product_name=names.reindex(grouped.index))
    ranked = grouped.sort_values(["revenue", "product_name"], ascending=[False, True]).head(TOP_PRODUCTS_LIMIT)
    return [
        # round(), not int(): quantity isn't guaranteed integral (no canonical
        # field forbids a fractional quantity), and int() truncates toward
        # zero, a systematic downward bias round() doesn't have.
        TopProduct(product=row.product_name, revenue=float(row.revenue), units=round(row.units))
        for row in ranked.itertuples()
    ]


def _biggest_decliners(current: pd.DataFrame, previous: pd.DataFrame, names: pd.Series) -> list[ProductDecline]:
    current_by_product = current.groupby("identity")["revenue"].sum()
    previous_by_product = previous.groupby("identity")["revenue"].sum()
    if previous_by_product.empty:
        return []

    # The money each product moved in the two months, the scale its residue
    # is judged against: 0.1 + 0.2 against 0.3 is the same 0.30, not a
    # decline of 5.55e-17 (2E doubt-review F7).
    moved = pd.concat([current, previous]).assign(size=lambda t: t["revenue"].abs()) \
        .groupby("identity")["size"].sum()
    declines: list[tuple[str, float, float, float]] = []
    for identity, previous_revenue in previous_by_product.items():
        current_revenue = float(current_by_product.get(identity, 0.0))
        change = current_revenue - float(previous_revenue)
        if change < 0 and not is_negligible(change, float(moved.get(identity, 0.0))):
            declines.append((str(identity), change, current_revenue, float(previous_revenue)))

    declines.sort(key=lambda item: (item[1], names.get(item[0], "")))
    ranked = []
    for identity, change, current_revenue, previous_revenue in declines[:BIGGEST_DECLINERS_LIMIT]:
        pct = pct_change(current_revenue, previous_revenue, float(moved.get(identity, 0.0)))
        ranked.append(ProductDecline(product=names[identity], revenue_change=change,
                                     revenue_change_pct=pct.value,
                                     revenue_change_pct_reason=pct.reason))
    return ranked


def _velocity(
    current: pd.DataFrame,
    all_in: pd.DataFrame,
    all_out: pd.DataFrame,
    names: pd.Series,
    days_in_period: int,
) -> list[ProductVelocity]:
    # Units sold a day: sale lines (2E-g). The stock balance stays every
    # counted line against every stock-in line (2C).
    units_current = current.groupby("identity")["sold"].sum()
    units_current = units_current[units_current > 0]
    if units_current.empty:
        return []

    stock_in = all_in.groupby("identity")["quantity"].sum()
    stock_out = all_out.groupby("identity")["quantity"].sum()
    lowest = _lowest_balance(all_in, all_out)

    rows: list[tuple[str, float, float | None, str | None]] = []
    for identity, units in units_current.items():
        units_per_day = float(units) / days_in_period
        if identity not in stock_in.index:
            rows.append((str(identity), units_per_day, None, NO_STOCK_IN_PRODUCT))
            continue
        received, left = float(stock_in[identity]), float(stock_out.get(identity, 0.0))
        # More went out than had come in, at any point of the file: the
        # history began with stock on hand, so the balance is unknown. Judged
        # at the end only, 50 sold before the first delivery and a later
        # delivery of 60 read "5 left, 31 days" - at least 55 were (2E-g
        # doubt-review cycle 3 F1); floored at 0, "0 days" (cycle 2 F2).
        low = float(lowest.get(identity, 0.0))
        if low < 0 and not is_negligible(low, received, left):
            rows.append((str(identity), units_per_day, None, INCOMPLETE_STOCK_HISTORY))
            continue
        rows.append((str(identity), units_per_day, max(0.0, received - left) / units_per_day, None))

    # Soonest stockout first; unknown stock last.
    rows.sort(key=lambda item: (item[2] is None, item[2] or 0.0, names.get(item[0], "")))
    return [
        ProductVelocity(product=names[identity], units_per_day=units_per_day,
                        days_to_stockout=days_to_stockout, days_to_stockout_reason=reason)
        for identity, units_per_day, days_to_stockout, reason in rows
    ]


def _lowest_balance(all_in: pd.DataFrame, all_out: pd.DataFrame) -> pd.Series:
    """Per product, the lowest its stock balance went through the file,
    starting from 0 and taken at the end of each day - so a delivery and a
    sale on one day are not ordered by the row they happen to sit on."""
    moves = pd.concat([all_in.assign(delta=all_in["quantity"]),
                       all_out.assign(delta=-all_out["quantity"])])
    daily = moves.groupby(["identity", "day"])["delta"].sum()
    return daily.groupby(level="identity").cumsum().groupby(level="identity").min()


def _days_in_month(year_month: str) -> int:
    year, month = int(year_month[:4]), int(year_month[5:7])
    return calendar.monthrange(year, month)[1]
