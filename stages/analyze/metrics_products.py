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
- A product with net current-period units <= 0 (never sold, or returns
  outweighing sales) is omitted from `velocity` entirely: an undefined or
  negative days_to_stockout is neither meaningful nor valid under the
  contract's NonNegativeFloat. This also answers the "only ever an 'in'
  row" edge case - such a product never has current-period units at all, so
  it never enters this list.
- `top_products` and `biggest_decliners` are each capped at the 10
  highest-ranked entries (revenue descending / revenue_change_pct ascending
  respectively), ties broken by product name for a deterministic,
  hand-checkable order. `velocity` is unbounded and sorted soonest-to-run-out
  first: it is a stockout-risk inventory, not a leaderboard, so every
  product with measurable velocity appears.
- Product identity is the column mapped to `sku` when a given row has one,
  else `product_name` for that row - the same business-key precedent
  docs/AI_PIPELINE.md section 11 already uses for duplicate detection. The
  identity value is stripped and case-folded before grouping (the same
  strip+lower pattern metrics_core.py already uses for transaction_type),
  so "SKU1", " SKU1" and "sku1" are one product, not three; the sku-sourced
  and product_name-sourced halves are kept in separate namespaces
  (`sku:`/`name:` prefixes) so a SKU that happens to read the same as an
  unrelated product's name can never merge them. The displayed `product`
  name is that identity's first-seen product_name anywhere in the file
  (never the identity key itself), so every list names the same product the
  same, human-readable way regardless of which rows resolved it by SKU.
- `top_products` excludes a net-negative-revenue product (returns
  outweighing sales for that product this period): it is not a "top"
  performer. `biggest_decliners`' population is exactly the products with
  nonzero previous-period revenue (reusing metrics_core.pct_change's own
  zero-denominator convention - a product with no previous revenue cannot
  "decline"), further filtered to an actually negative revenue_change_pct.
"""

import calendar
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from contracts.cleaning import CleaningReportContract
from contracts.metrics import Pareto, Period, ProductDecline, ProductMetrics, ProductVelocity, TopProduct
from shared.run_registry import run_file
from stages.analyze.metrics_core import (
    CLEANED_FILENAME,
    CLEANING_REPORT_FILENAME,
    is_blank,
    parse_transactions,
    pct_change,
    require_column,
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
    parsed = parse_transactions(frame, report.column_mapping)
    period = select_period(parsed.dates, now or datetime.now(UTC))
    return compute_product_metrics(frame, report.column_mapping, period)


def compute_product_metrics(
    df: pd.DataFrame, column_mapping: dict[str, str], period: Period
) -> ProductMetrics:
    """Pure computation."""
    parsed = parse_transactions(df, column_mapping)
    product_name_col = require_column(parsed.reverse, "product_name")
    sku_col = parsed.reverse.get("sku")

    identity = _product_identity(df, product_name_col, sku_col)
    names = pd.DataFrame({"identity": identity, "name": df[product_name_col]}).groupby("identity")["name"].first()

    table = pd.DataFrame(
        {"identity": identity, "quantity": parsed.quantities, "revenue": parsed.revenue_amounts}
    )
    months = parsed.dates.dt.to_period("M").astype(str)

    current = table[parsed.counted & (months == period.current)]
    previous = table[parsed.counted & (months == period.previous)]
    all_in = table[parsed.valid & ~parsed.counted]
    all_out = table[parsed.counted]

    return ProductMetrics(
        pareto=_pareto(current),
        top_products=_top_products(current, names),
        biggest_decliners=_biggest_decliners(current, previous, names),
        velocity=_velocity(current, all_in, all_out, names, _days_in_month(period.current)),
    )


def _product_identity(df: pd.DataFrame, product_name_col: str, sku_col: str | None) -> pd.Series:
    normalized_name = "name:" + _normalize(df[product_name_col])
    if sku_col is None:
        return normalized_name
    sku = df[sku_col]
    normalized_sku = "sku:" + _normalize(sku)
    return normalized_sku.where(~is_blank(sku), normalized_name)


def _normalize(values: pd.Series) -> pd.Series:
    # astype(object): an all-missing column can read back as float64, and
    # .str only works on an object/string dtype (metrics_core.py hits the
    # same issue). NaN propagates through strip/lower/concat unharmed.
    return values.astype(object).str.strip().str.lower()


def _pareto(current: pd.DataFrame) -> Pareto:
    # Same population as _top_products (revenue > 0): a product that net
    # returned more than it sold this period isn't a revenue driver, and
    # counting it here while excluding it from top_products would make the
    # two numbers in the same contract object describe different products.
    by_product = current.groupby("identity")["revenue"].sum()
    by_product = by_product[by_product > 0]
    total_products = int(len(by_product))
    total_revenue = float(by_product.sum())
    if total_products == 0 or total_revenue <= 0:
        return Pareto(products_for_80pct_revenue=0, total_products=total_products, concentration_pct=0.0)

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
    )


def _top_products(current: pd.DataFrame, names: pd.Series) -> list[TopProduct]:
    grouped = current.groupby("identity").agg(revenue=("revenue", "sum"), units=("quantity", "sum"))
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

    declines: list[tuple[str, float]] = []
    for identity, previous_revenue in previous_by_product.items():
        change = pct_change(float(current_by_product.get(identity, 0.0)), float(previous_revenue))
        if change < 0:
            declines.append((str(identity), change))

    declines.sort(key=lambda item: (item[1], names.get(item[0], "")))
    return [
        ProductDecline(product=names[identity], revenue_change_pct=change)
        for identity, change in declines[:BIGGEST_DECLINERS_LIMIT]
    ]


def _velocity(
    current: pd.DataFrame,
    all_in: pd.DataFrame,
    all_out: pd.DataFrame,
    names: pd.Series,
    days_in_period: int,
) -> list[ProductVelocity]:
    units_current = current.groupby("identity")["quantity"].sum()
    units_current = units_current[units_current > 0]
    if units_current.empty:
        return []

    stock_in = all_in.groupby("identity")["quantity"].sum()
    stock_out = all_out.groupby("identity")["quantity"].sum()

    rows: list[tuple[str, float, float]] = []
    for identity, units in units_current.items():
        units_per_day = float(units) / days_in_period
        implied_stock = max(0.0, float(stock_in.get(identity, 0.0)) - float(stock_out.get(identity, 0.0)))
        rows.append((str(identity), units_per_day, implied_stock / units_per_day))

    rows.sort(key=lambda item: (item[2], names.get(item[0], "")))  # soonest stockout first
    return [
        ProductVelocity(product=names[identity], units_per_day=units_per_day, days_to_stockout=days_to_stockout)
        for identity, units_per_day, days_to_stockout in rows
    ]


def _days_in_month(year_month: str) -> int:
    year, month = int(year_month[:4]), int(year_month[5:7])
    return calendar.monthrange(year, month)[1]
