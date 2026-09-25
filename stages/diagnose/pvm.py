"""Step 5, product lens: price, volume and mix on gross sales
(docs/AI_PIPELINE.md section 7.6, docs/DIAGNOSE_DESIGN.md 5.5.7).

"Sales fell" has three quite different causes that a single average hides:
the shop sold fewer things (volume), it sold a different blend of things
(mix), or the same things changed price (price). The third is actionable in a
way the second is not, and confusing them is exactly the Simpson's-paradox
trap in DIAGNOSE_DESIGN 1.3 - overall AOV can fall while every single product
got more expensive.

This lens runs on **gross** sales (positive-quantity rows). Returns are the
returns lens's subject; mixing them in would let a refund of last month's
order look like this month's price change.
"""

from dataclasses import dataclass

import pandas as pd

from contracts.diagnosis import ProductLens
from shared.products import product_keys
from shared.transactions import require_column
from stages.diagnose.inputs import RunData, period_mask
from stages.diagnose.shapley import Coalition, shapley


# Lines with neither SKU nor name (the gap). Product keys are namespaced
# `sku:`/`name:` and never empty after the prefix, so the bare "name:" can
# never be a real product's key.
UNIDENTIFIED_PRODUCT = "name:"


@dataclass(frozen=True)
class ProductPeriod:
    """Gross units and gross revenue per product identity for one month."""

    units: pd.Series
    revenue: pd.Series


def compute_products(data: RunData) -> ProductLens:
    previous = _gross_by_product(data, data.metrics.period.previous)
    current = _gross_by_product(data, data.metrics.period.current)

    # L: sold in both periods, so a like-for-like comparison exists. N and X
    # have no counterpart at all, and pretending otherwise would report a
    # product that did not exist last month as an infinite price rise.
    live = sorted(set(previous.units.index) & set(current.units.index))
    new_only = sorted(set(current.units.index) - set(previous.units.index))
    gone_only = sorted(set(previous.units.index) - set(current.units.index))

    volume, mix, price = _pvm(previous, current, live)
    return ProductLens(
        volume=volume,
        mix=mix,
        price=price,
        new_products=float(current.revenue.reindex(new_only).sum()),
        discontinued_products=-float(previous.revenue.reindex(gone_only).sum()),
    )


def _gross_by_product(data: RunData, month: str) -> ProductPeriod:
    """Only products with positive gross units count as present in a period:
    a product whose month nets to zero units has no meaningful price."""
    require_column(data.parsed.reverse, "product_name")
    # Stage 2's keys (shared/products.py, 2E-g). A line with neither SKU nor
    # name gets a NaN key - the data gap - and
    # `groupby` drops NaN keys silently - so those rows left the lens while
    # staying in the gross totals it reconciles against, and the lens reported
    # a rise where gross sales had fallen (3C doubt-review C1). Stage 1 can
    # legitimately produce such a file: `flag_only` leaves missing values in
    # place and the user is the final authority over the plan (CLAUDE.md 3.3).
    # They are one visible bucket rather than a silent omission; unnamed rows
    # are not a product, but they are revenue and the identity must close
    # (kept so by Thach, 2E-g).
    identity = product_keys(data.df, data.parsed).fillna(UNIDENTIFIED_PRODUCT)

    # Sale rows (shared/transactions.py, 2E-c), the same rows as the returns
    # lens's gross: a refund booked as quantity 1 at a negative price was a
    # "product sold at a lower price" here, and P1 headlined a price cut.
    mask = period_mask(data, month) & data.parsed.sale
    keys = identity[mask]
    units = data.parsed.quantities[mask].groupby(keys).sum()
    revenue = data.parsed.revenue_amounts[mask].groupby(keys).sum()
    positive = units[units > 0].index
    return ProductPeriod(units=units.reindex(positive), revenue=revenue.reindex(positive))


def _pvm(
    previous: ProductPeriod, current: ProductPeriod, live: list[str]
) -> tuple[float, float, float]:
    """Three-player Shapley over `gross_L = Q * sum_i(s_i * p_i)`.

    The players are not three numbers: `Q` is total units, but `s` is the whole
    share vector and `p` the whole price vector, each switched as one unit.
    That is why `shapley` takes a value function - the identity
    `Q * sum(s_i * p_i) = sum(q_i * p_i) = gross_L` holds for either period's
    values, so the three effects sum exactly to the change in gross sales for L.
    """
    if not live:
        # No like-for-like products at all. Gross sales for L is zero in both
        # periods, so all three effects are zero - and saying so is exact,
        # not a fallback.
        return 0.0, 0.0, 0.0

    units = {
        "prev": previous.units.reindex(live).astype(float),
        "cur": current.units.reindex(live).astype(float),
    }
    revenue = {
        "prev": previous.revenue.reindex(live).astype(float),
        "cur": current.revenue.reindex(live).astype(float),
    }
    totals = {period: float(column.sum()) for period, column in units.items()}
    shares = {period: units[period] / totals[period] for period in ("prev", "cur")}
    prices = {period: revenue[period] / units[period] for period in ("prev", "cur")}

    def value(switched: Coalition) -> float:
        quantity = totals["cur"] if "volume" in switched else totals["prev"]
        share = shares["cur"] if "mix" in switched else shares["prev"]
        price = prices["cur"] if "price" in switched else prices["prev"]
        return quantity * float((share * price).sum())

    effects = shapley(("volume", "mix", "price"), value)
    return effects["volume"], effects["mix"], effects["price"]
