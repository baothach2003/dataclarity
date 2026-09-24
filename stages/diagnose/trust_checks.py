"""Step 2's D2 and D3 checks (docs/AI_PIPELINE.md section 7.3), split out of
`trust.py` in 3E1 to keep both files under the size rule. Neither can block:
each describes something consistent with a data problem and equally with a
real business decision.
"""

import pandas as pd

from contracts.diagnosis import TrustCheck
from shared.transactions import is_blank, product_identity, require_column
from stages.diagnose.inputs import RunData
from stages.diagnose.numbers import is_negligible
from stages.diagnose.thresholds import (
    D2_CLUSTER_SHARE,
    D2_CLUSTER_WIDTH,
    D2_MIN_PRODUCTS,
    D2_MIN_ROWS,
    D2_NEUTRAL_BAND,
    D2_SMALL_CLUSTER_SHARE,
    D2_SMALL_MIN_PRODUCTS,
    D2_SMALL_RATIO_HIGH,
    D2_SMALL_RATIO_LOW,
    D3_MIN_SHARE,
    D3_RATIO,
)


# --- D2: uniform price-level shift --------------------------------------------


def d2_price_level(data: RunData) -> TrustCheck:
    """A whole catalogue repricing by the same factor is the signature of a
    unit or currency change in the data - or of a deliberate repricing. This
    check never blocks, because nothing in point-of-sale rows can tell those
    two apart."""
    ratios = _price_ratios(data)
    count = len(ratios)
    evidence: dict[str, object] = {"comparable_products": count}

    if count >= D2_MIN_PRODUCTS:
        median = float(ratios.median())
        within = float((ratios.sub(median).abs() <= D2_CLUSTER_WIDTH * median).mean())
        evidence |= {"median_ratio": round(median, 4), "share_in_cluster": round(within, 4),
                     "rule": "cluster"}
        low, high = D2_NEUTRAL_BAND
        if within >= D2_CLUSTER_SHARE and not (low <= median <= high):
            return TrustCheck(
                id="D2", status="caution", evidence=evidence,
                message=f"Prices moved by about the same factor ({median:.2f}x) across "
                        f"{within:.0%} of comparable products. Verify whether this is a unit "
                        "or currency change in the data, or a deliberate repricing.")
        return TrustCheck(id="D2", status="ok", evidence=evidence,
                          message="No uniform price-level shift across products.")

    if count >= D2_SMALL_MIN_PRODUCTS:
        # Small catalogue: only an order-of-magnitude move is evidence, since a
        # tight cluster among a handful of products happens by chance.
        extreme = float(((ratios >= D2_SMALL_RATIO_HIGH) | (ratios <= D2_SMALL_RATIO_LOW)).mean())
        median = float(ratios.median())
        evidence |= {"median_ratio": round(median, 4), "share_extreme": round(extreme, 4),
                     "rule": "small_catalog_order_of_magnitude"}
        if extreme >= D2_SMALL_CLUSTER_SHARE:
            return TrustCheck(
                id="D2", status="caution", evidence=evidence,
                message=f"Prices changed by an order of magnitude (about {median:.2f}x) across "
                        f"{extreme:.0%} of the {count} comparable products. That is the "
                        "signature of a unit or currency error rather than repricing; verify "
                        "the price column.")
        return TrustCheck(
            id="D2", status="ok", evidence=evidence,
            message=f"No order-of-magnitude price shift across the {count} comparable products.")

    return TrustCheck(
        id="D2", status="inconclusive", evidence=evidence,
        message=f"Only {count} products sold in both periods with enough rows to compare "
                "prices; too few to tell a uniform shift from coincidence.")


def _price_ratios(data: RunData) -> pd.Series:
    """Median unit price this period over median unit price last period, per
    product sold in both with at least D2_MIN_ROWS counted rows in each."""
    reverse = data.parsed.reverse
    name_col = require_column(reverse, "product_name")
    identity = product_identity(data.df, name_col, reverse.get("sku"))
    period = data.metrics.period

    frame = pd.DataFrame({
        "identity": identity,
        "month": data.months,
        "price": data.parsed.prices,
    })[data.parsed.counted]

    medians = {}
    for label, month in (("cur", period.current), ("prev", period.previous)):
        rows = frame[frame["month"] == month]
        grouped = rows.groupby("identity")["price"]
        medians[label] = grouped.median()[grouped.size() >= D2_MIN_ROWS]

    shared = medians["cur"].index.intersection(medians["prev"].index)
    previous = medians["prev"].reindex(shared)
    current = medians["cur"].reindex(shared)
    # A zero or negative previous price cannot produce a meaningful ratio.
    usable = previous > 0
    return (current[usable] / previous[usable]).dropna()


# --- D3: flagged rows concentrated in the current period ----------------------


def d3_flagged_rows(data: RunData) -> TrustCheck:
    """Stage 1 marks cells it could not trust with `__flag_*` columns. A jump
    in their share between the periods means the current month's rows are of a
    different quality from the ones it is compared with."""
    uncategorised = _uncategorised_share(data)
    flag_columns = [column for column in data.df.columns if str(column).startswith("__flag_")]
    if not flag_columns:
        return TrustCheck(id="D3", status="ok",
                          evidence={"flag_columns": 0, **uncategorised},
                          message="Stage 1 flagged no rows in this file.")

    flagged = _any_flag_set(data.df[flag_columns])
    period = data.metrics.period
    shares = {}
    for label, month in (("cur", period.current), ("prev", period.previous)):
        in_month = data.parsed.counted & (data.months == month)
        rows = int(in_month.sum())
        shares[label] = float(flagged[in_month].mean()) if rows else 0.0

    evidence = {"flag_columns": len(flag_columns),
                "flagged_share_cur": round(shares["cur"], 4),
                "flagged_share_prev": round(shares["prev"], 4),
                **uncategorised}
    if shares["cur"] >= D3_RATIO * shares["prev"] and shares["cur"] >= D3_MIN_SHARE:
        return TrustCheck(
            id="D3", status="caution", evidence=evidence,
            message=f"{shares['cur']:.1%} of this month's rows carry a data-quality flag, "
                    f"against {shares['prev']:.1%} last month.")
    return TrustCheck(id="D3", status="ok", evidence=evidence,
                      message="Flagged rows are not concentrated in the current period.")


def _uncategorised_share(data: RunData) -> dict[str, float | None]:
    """How much of each period's revenue carries no category.

    Reported as D3 evidence because it is a data-completeness fact, not a
    business one (Thach, 3D): step 6 shows "(uncategorised)" as a member so
    the dimension still adds up, and this is what tells a reader whether that
    member is a rounding detail or most of the shop. Absent when no category
    column is mapped - there is nothing incomplete about a file that never
    claimed to have categories.

    Three things the first version got wrong (3D doubt-review R10). It
    measured the current month only, so a file whose category column went
    blank *last* month reported 0.0 while step 6 showed a large `rev_prev`
    for the gap bucket. It divided absolute revenue while step 6's member
    reports net, so the two numbers a reader would naturally compare did not
    match. And it returned 0.0 for a month with no revenue at all, which
    reads as "nothing uncategorised" rather than "nothing to measure" -
    `None` says the second.
    """
    column = data.parsed.reverse.get("category")
    if column is None:
        return {}
    blank = is_blank(data.df[column])
    period = data.metrics.period
    shares: dict[str, float | None] = {}
    for label, month in (("cur", period.current), ("prev", period.previous)):
        mask = data.parsed.counted & (data.months == month)
        revenue = data.parsed.revenue_amounts[mask]
        total = float(revenue.sum())
        # Net, matching the member step 6 reports, and relative rather than
        # `== 0` so a month whose sales and refunds cancel is reported as
        # unmeasurable instead of dividing by residue.
        if is_negligible(total, float(revenue.abs().sum()), total):
            shares[f"uncategorised_revenue_share_{label}"] = None
            continue
        shares[f"uncategorised_revenue_share_{label}"] = round(
            float(revenue[blank[mask]].sum()) / total, 4)
    return shares


def _any_flag_set(flags: pd.DataFrame) -> pd.Series:
    """cleaned.csv is read as text, so a flag arrives as "True"/"False"."""
    truthy = flags.apply(lambda column: column.astype(object).str.strip().str.lower().isin(
        ("true", "1")))
    return truthy.any(axis=1)
