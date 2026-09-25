"""R3: a product that sold steadily and then stopped while the store kept
trading (docs/AI_PIPELINE.md 7.8).

Point-of-sale rows cannot confirm a stockout - published POS-only detectors
catch roughly 63% of stockouts with about 15% false alerts - so the finding is
always worded "consistent with a stockout, verify on the shelf", never "caused
by". This module only finds the pattern; `hypotheses.py` judges it.
"""

from dataclasses import dataclass

import pandas as pd

from shared.products import product_keys
from shared.transactions import require_column
from stages.diagnose.inputs import RunData
from stages.diagnose.members import product_totals
from stages.diagnose.thresholds import (
    MEMBER_MIN_REVENUE_SHARE,
    R3_MIN_ACTIVE_DAY_RATE,
    R3_MIN_ZERO_RUN_DAYS,
)


@dataclass(frozen=True)
class Stockout:
    product: str
    active_day_rate_prev: float
    zero_run_days: int
    revenue_per_trading_day_prev: float
    contribution: float


def detect_stockouts(data: RunData) -> list[Stockout]:
    """Products whose active-day rate in `prev` was at least
    R3_MIN_ACTIVE_DAY_RATE and which then went R3_MIN_ZERO_RUN_DAYS
    consecutive TRADING days without a sale in `cur`.

    Days are counted over the days the store sold anything, not the calendar:
    a shop closed on Sundays would otherwise have every product "miss" every
    Sunday, and a product would need one fewer real zero day per week to reach
    the run. The contribution is minus the product's mean `prev` sales per
    trading day times the length of its longest run - what it would have sold
    on those days at last month's pace.
    """
    period = data.metrics.period
    # Sale rows (2E-c): a free item booked on the days a product was out
    # sold nothing, and it hid the run.
    sales = data.parsed.sale
    require_column(data.parsed.reverse, "product_name")
    # Stage 2's keys (shared/products.py, 2E-g): the data gap's key is NaN, so
    # it never becomes a candidate - unnamed lines that stopped read as a
    # stockout of a product "   ". R3 reads the sales pattern, never stock,
    # so the stock-in question of stage 2's velocity does not touch it.
    keys = product_keys(data.df, data.parsed)
    days = data.parsed.dates.dt.normalize()
    labels = product_totals(data).labels

    found: list[Stockout] = []
    prev_mask = sales & (data.months == period.previous)
    cur_mask = sales & (data.months == period.current)
    trading_prev = days[prev_mask].nunique()
    trading_cur = sorted(days[cur_mask].unique())
    if not trading_prev or not trading_cur:
        return found

    # One grouping pass per period, not a full-length mask per product: the
    # first version was O(products x rows) and took 68 s on 4,000 products
    # (3E1 doubt-review #6).
    prev = pd.DataFrame({"key": keys[prev_mask], "day": days[prev_mask],
                         "revenue": data.parsed.revenue_amounts[prev_mask]})
    active = prev.groupby("key")["day"].nunique()
    revenue = prev.groupby("key")["revenue"].sum()
    rates = active / trading_prev
    # A TOP product, as the statement says: at least MEMBER_MIN_REVENUE_SHARE
    # of previous sales, localization's own size bar. A rate test alone flagged
    # tail products at random - supported in 3 of 8 unchanged random shops
    # (Thach, 3E1).
    # The gap's money counts in the total the bar is measured against, as
    # localization's does: its NaN key dropped out of `revenue`, and a 1%
    # product passed a 2% bar (2E-g doubt-review F4).
    gap = float(data.parsed.revenue_amounts[prev_mask & keys.isna()].sum())
    total = float(revenue[revenue > 0].sum()) + max(gap, 0.0)
    top = (revenue >= MEMBER_MIN_REVENUE_SHARE * total if total > 0
           else pd.Series(False, index=revenue.index))
    candidates = sorted(rates[(rates >= R3_MIN_ACTIVE_DAY_RATE) & top].index)
    if not candidates:
        return found
    cur = pd.DataFrame({"key": keys[cur_mask], "day": days[cur_mask]})
    sold_by_key = cur[cur["key"].isin(candidates)].groupby("key")["day"].agg(set)

    for key in candidates:
        sold_cur = sold_by_key.get(key, set())
        if not sold_cur:
            # No sale at all this month is a discontinuation - R2's - not a
            # stockout; both claimed it, 181% of the change between them.
            continue
        run = longest = 0
        for day in trading_cur:
            run = 0 if day in sold_cur else run + 1
            longest = max(longest, run)
        if longest < R3_MIN_ZERO_RUN_DAYS:
            continue
        per_day = float(revenue[key]) / trading_prev
        found.append(Stockout(
            product=labels.get(key, str(key)),
            active_day_rate_prev=round(float(rates[key]), 4),
            zero_run_days=longest,
            revenue_per_trading_day_prev=per_day,
            contribution=-per_day * longest,
        ))
    return found
