"""Stage 2 Analyze - the `products` block of metrics.json
(docs/CONTRACTS.md section 6): Pareto concentration, top products, biggest
decliners, the suggested classes of the products named. Pure pandas; no AI
call in this stage (docs/adr/0002-pandas-computes-ai-interprets.md). Reuses
`stages.analyze.metrics_core`'s row parsing, revenue-scope and
zero-denominator conventions (2A) instead of redefining them - same stage
package, so the import is not a cross-stage dependency (CLAUDE.md 3.1).

Design decisions (Thach, Phase 2C onwards):
- Stock (Thach, the line taxonomy's v1 scope cut, 2E-t2): `velocity` is null
  on every file with the reason that stock figures are not supported in v1.
  2C derived stock on hand from the file's stock-in lines against every
  counted line; most POS exports carry none (both demo files read "0 days to
  stockout" for every product before 2E-g made it null), and the formula
  read a zero-amount -20 write-off as 20 back in stock (57 days where 17 was
  true). The stock ledger is a v2 item (PROJECT_PLAN's Backlog).
- `top_products` and `biggest_decliners` are each capped at the 10
  highest-ranked entries (revenue descending / revenue_change ascending
  respectively), ties broken by product name for a deterministic,
  hand-checkable order.
- Product identity and the displayed name come from shared/products.py
  (Thach, 2E-g), so stage 3 names every product as this block does: the SKU
  when a line has one, else the name (a name-only line takes the one SKU
  its name is sold under); the label is the name the product's sale lines
  carry most over the whole file. A line with neither SKU nor name is the
  "(no product name)" data gap: in no table (it was ranked as a product).
- Units sold (`top_products.units`) count sale lines only (2E-g).
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

from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from contracts.cleaning import CleaningReportContract, OrderConfirmations
from contracts.metrics import Pareto, Period, ProductDecline, ProductMetrics, TopProduct
from shared.numbers import is_negligible, pct_change
from shared.products import product_keys, product_labels, product_suggestions
from shared.run_registry import run_file
from shared.transactions import parse_transactions, require_column
from stages.analyze.metrics_core import (
    CLEANED_FILENAME,
    CLEANING_REPORT_FILENAME,
    choose_period,
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
    parsed = parse_transactions(frame, report.column_mapping, report.applied_confirmations())
    period, _ = choose_period(parsed, now or datetime.now(UTC))
    return compute_product_metrics(frame, report.column_mapping, period, report.applied_confirmations())


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

    if period.previous_complete:
        decliners, decliners_reason = _biggest_decliners(current, previous, names), None
    else:
        decliners, decliners_reason = None, period.previous_incomplete_reason
    top = _top_products(current, names)
    # Stock figures are not supported in v1 (Thach, the line taxonomy's scope
    # cut, 2E-t2): a stock balance needs a stock ledger the export rarely
    # carries, and a figure that can be wrong is worse than none - 2C's
    # derivation read a -20 write-off as 20 back in stock.
    return ProductMetrics(
        pareto=_pareto(current, period.current),
        top_products=top,
        biggest_decliners=decliners,
        biggest_decliners_reason=decliners_reason,
        velocity=None,
        velocity_reason=NOT_SUPPORTED_IN_V1,
        suggested_classes=_suggested(product_suggestions(df, parsed, identity), names,
                                     [p.product for p in top] + [d.product for d in decliners or []]),
    )


NOT_SUPPORTED_IN_V1 = ("stock figures are not supported in v1: DataClarity v1 analyses sales, not "
                       "inventory, so no product has a units-a-day or days-to-stockout figure")


def _suggested(by_key: dict[str, str], names: pd.Series, named: list[str]) -> dict[str, str]:
    """The products this block names whose own key carries a line-class
    suggestion nobody confirmed, by label, with that class (Thach's Q17)."""
    by_label = {names[key]: line_class for key, line_class in by_key.items()}
    return {label: by_label[label] for label in named if label in by_label}


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
