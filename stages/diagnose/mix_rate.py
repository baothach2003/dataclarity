"""Step 6, mix versus rate: the Simpson's-paradox guard
(docs/AI_PIPELINE.md section 7.7, docs/DIAGNOSE_DESIGN.md 5.6).

An average can fall while every single part of it rises. DIAGNOSE_DESIGN 1.3
has the worked case: a cheap category's AOV goes 20 -> 22, an expensive one's
100 -> 105, both up, and overall AOV falls 60 -> 38.6 because the order mix
moved towards the cheap one. A report that stops at "AOV fell 36%" sends the
shop owner to fix pricing, which is not what happened.

Splitting `sum_c(share_c * value_c)` into a share effect and a value effect
says which it was, and says it exactly: the two contributions sum to the
metric's whole change.
"""

import pandas as pd

from contracts.diagnosis import MixRate
from shared.transactions import is_blank, normalize_text
from stages.diagnose.inputs import RunData, period_mask
from stages.diagnose.members import UNCATEGORISED_KEY
from stages.diagnose.numbers import is_negligible
from stages.diagnose.shapley import Coalition, shapley

# Each metric as a weighted average: the value per category, and the weight
# whose share makes the weighted average equal the overall figure.
# AOV = revenue/orders, so orders are the weight; price per unit = revenue/
# units, so units are. Anything else would not reconcile.
METRICS = {"aov": "orders", "price_per_unit": "units"}


def compute_mix_rate(data: RunData) -> MixRate | None:
    """Split whichever of AOV or price per unit moved more, in relative terms.

    `None` when there is no category column to split by, and also when a
    denominator is zero or the chosen metric did not move - there is nothing
    to attribute then, and the alternative is a division no reader could
    check.
    """
    if data.parsed.reverse.get("category") is None:
        return None

    table = _by_category(data)
    if table is None:
        return None

    moves = {}
    for metric, weight in METRICS.items():
        # The DENOMINATOR has to be positive in both periods, not merely the
        # metric. Two negatives divide to a healthy-looking positive: a month
        # that sold 50 and refunded 165 had units go 20 -> -1, so price per
        # unit read -115/-1 = 115, a tidy +1050% rise, and won the "moved
        # most" contest outright. Guarding the metric's own sign does not
        # catch that; this is the lever lens's rule, worded the same way.
        if any(float(table[f"{weight}_{period}"].sum()) <= 0
               for period in ("prev", "cur")):
            continue
        # A category with revenue but no weight in a period has no value of
        # its own (revenue over nothing), so its revenue would drop out of the
        # weighted average and the split would stop reconciling to the overall
        # figure. Since 2E a category holding only refunds has 0 orders; the
        # split is refused rather than made inexact.
        if any(((table[f"{weight}_{period}"] == 0) & (table[f"rev_{period}"] != 0)).any()
               for period in ("prev", "cur")):
            continue
        previous = _weighted_average(table, metric, weight, "prev")
        current = _weighted_average(table, metric, weight, "cur")
        if previous is None or current is None:
            continue
        # A metric whose own denominator went negative is not a small metric,
        # it is a meaningless one - and selecting by "moved most" hands the
        # split to precisely that metric, because a sign flip produces the
        # largest relative move on the page. A month that sold 50 and refunded
        # 165 reported price per unit rising from 10 to 115, +1050%, with the
        # whole fabricated move attributed to sales mix (3D doubt-review R5).
        # The lever lens already refuses this case for the same reason.
        if previous <= 0 or current <= 0:
            continue
        if is_negligible(current - previous, previous, current):
            continue
        moves[metric] = abs((current - previous) / previous)
    if not moves:
        return None

    # Ties go to AOV, deliberately rather than alphabetically. On a file with
    # one unit per line - a very common shape - AOV and price per unit are the
    # same number and always tie, and AOV is the figure the lever tree already
    # reports and the one a shop owner reads without translation.
    metric = max(moves, key=lambda name: (moves[name], name == "aov"))
    return _split(table, metric, METRICS[metric])


def _split(table: pd.DataFrame, metric: str, weight: str) -> MixRate | None:
    """Two-player Shapley over `sum_c(share_c * value_c)`.

    The players are the whole share vector and the whole value vector, each
    switched as a unit - the same shape as the product lens's mix player, and
    the same `shapley` engine, so exactness comes from a construction already
    proved rather than from this function's own arithmetic.
    """
    shares, values = {}, {}
    for period in ("prev", "cur"):
        total = float(table[f"{weight}_{period}"].sum())
        # Relative, not `== 0`: fractional quantities that cancel (0.1 + 0.2 -
        # 0.3) leave residue rather than zero, and dividing by it gives shares
        # of ~1e16 (3D doubt-review R6).
        if is_negligible(total, float(table[f"rev_{period}"].abs().sum()), total):
            return None
        shares[period] = table[f"{weight}_{period}"] / total
        # A category absent from a period has share 0 there, so its value
        # cannot matter - but it must not be NaN, or 0 * NaN poisons the sum.
        values[period] = (table[f"rev_{period}"] / table[f"{weight}_{period}"]).fillna(0.0)
        values[period] = values[period].replace([float("inf"), float("-inf")], 0.0)

    def value(switched: Coalition) -> float:
        share = shares["cur"] if "mix" in switched else shares["prev"]
        rate = values["cur"] if "rate" in switched else values["prev"]
        return float((share * rate).sum())

    effects = shapley(("mix", "rate"), value)
    return MixRate(metric=metric, mix=effects["mix"], rate=effects["rate"])


def _weighted_average(
    table: pd.DataFrame, metric: str, weight: str, period: str
) -> float | None:
    total = float(table[f"{weight}_{period}"].sum())
    if is_negligible(total, float(table[f"rev_{period}"].abs().sum()), total):
        return None
    return float(table[f"rev_{period}"].sum()) / total


def _by_category(data: RunData) -> pd.DataFrame | None:
    """Revenue, orders and units per category, per period.

    Blank categories keep their own row here exactly as they do in the
    dimension (Thach, 3D): dropping them would make the weighted average
    stop equalling the overall figure, and the split would silently be of a
    different quantity from the one the report names.
    """
    column = data.parsed.reverse.get("category")
    keys = normalize_text(data.df[column]).where(~is_blank(data.df[column]), UNCATEGORISED_KEY)

    period = data.metrics.period
    columns = {}
    for label, month in (("prev", period.previous), ("cur", period.current)):
        mask = period_mask(data, month)
        grouped = keys[mask]
        columns[f"rev_{label}"] = data.parsed.revenue_amounts[mask].groupby(grouped).sum()
        # Sale rows (2E), so the weighted average is stage 2's AOV.
        sales = keys[mask & data.parsed.sale]
        columns[f"orders_{label}"] = sales.groupby(sales).size()
        # The lever's units (2E-c), so the weighted average reconciles to it.
        columns[f"units_{label}"] = data.parsed.units[mask].groupby(grouped).sum()
    table = pd.DataFrame(columns).fillna(0.0)
    return table if not table.empty else None
