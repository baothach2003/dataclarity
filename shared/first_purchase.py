"""Who is a new customer: one definition, shared by stage 2's
new_vs_returning and stage 3's customer bridge (Thach, session 2E-c, rule C).
Infrastructure in the same sense as `shared/transactions.py`: it decides what
a customer's history says, and both stages must agree on it exactly.

A customer's first purchase is their first SALE row (`ParsedTransactions.
sale`). A history that OPENS with a refund has no first purchase in the file:
the refund proves a purchase before the file started, so that customer is
never new. Measured on Online Retail II: counting the first row of any kind
called 172 refund-only customers new, with -91,486.72 of "new revenue"; the
first sale alone called 214 customers new whose history opened with a refund.

The opening day is the customer's first day with a sale or return line, and
each PRODUCT nets on its own there (Thach, 2E-f): the history opens with a
refund when, for any product, more units came back that day than were bought
that day - a product not bought that day, or returned beyond what was.
2E-c netted the whole day's units, and netting across products fabricated
"new": 10 pens bought and a 500 chair from before the file returned on the
first day netted +9, and C1 headlined new-customer revenue collapsing (2E-c
doubt-review cycle 3). 2E-c2 then took any return line on the first day as
an opening refund, which also took "new" from customers who returned part of
what they had just bought: 96 on Online Retail II get it back. Netting by
units, not by "was it bought at all", keeps 10 more out who returned more
than they bought that day. A return whose product is unknown cannot be
matched, so it opens with a refund. The day is the unit, not the time: a
return rung up before the purchase on the same day still nets (a known
limit - not every file has a time). A coupon or a free item is not part of
the purchase history: taken as the opening day, a coupon on the 3rd hid a
refund on the 4th (2E-c doubt-review F4).
"""

import pandas as pd

from shared.numbers import is_negligible
from shared.transactions import is_blank, normalize_text, product_identity


def product_keys(df: pd.DataFrame, reverse: dict[str, str]) -> pd.Series:
    """Each row's product for the opening-day netting: the shared
    `product_identity` (the sku, else the name), NaN where the row has
    neither - two nameless lines cannot be shown to be one product."""
    name_col, sku_col = reverse.get("product_name"), reverse.get("sku")
    unknown = pd.Series(float("nan"), index=df.index, dtype=object)
    if name_col is None:
        if sku_col is None:
            return unknown
        return ("sku:" + normalize_text(df[sku_col])).where(~is_blank(df[sku_col]))
    known = ~is_blank(df[name_col])
    if sku_col is not None:
        known |= ~is_blank(df[sku_col])
    return product_identity(df, name_col, sku_col).where(known)


def first_purchase_months(
    customers: pd.Series, dates: pd.Series, sale: pd.Series, returned: pd.Series,
    products: pd.Series, units: pd.Series,
) -> pd.Series:
    """Per customer key: the "YYYY-MM" of their first purchase, or None when
    the file holds none (only refunds, only deductions, or a history that
    opens with a refund). The caller passes the rows it identifies customers
    on, keyed as it groups them; `products` from `product_keys`, `units` the
    parsed units (positive on a sale line, negative on a return line)."""
    frame = pd.DataFrame({"customer": customers, "day": dates.dt.normalize(),
                          "sale": sale, "returned": returned, "product": products,
                          "bought": units.where(sale, 0.0), "back": (-units).where(returned, 0.0)})
    customers_seen = pd.Index(frame["customer"].unique())
    if frame.empty:
        return pd.Series([], index=customers_seen, dtype=object)

    history = frame[frame["sale"] | frame["returned"]]
    opening = history[history["day"] == history.groupby("customer")["day"].transform("min")]
    per_product = opening.groupby(["customer", "product"], dropna=False)[["bought", "back"]].sum()
    unknown = per_product.index.get_level_values("product").isna()
    # Residue is not a unit bought before the file: 0.1 + 0.2 kg returned
    # against 0.3 bought sums to 0.30000000000000004.
    uncovered = [
        back > 0 and (nameless or (back > bought and not is_negligible(back - bought, bought, back)))
        for nameless, bought, back in zip(unknown, per_product["bought"], per_product["back"],
                                          strict=True)
    ]
    opens_with_refund = pd.Series(uncovered, index=per_product.index).groupby(level="customer").any()

    first_sale = frame[frame["sale"]].groupby("customer")["day"].min()
    months = first_sale.dt.to_period("M").astype(str).to_dict()
    refunders = set(opens_with_refund[opens_with_refund].index)
    # Built value by value: `pd.Series(None, dtype=object)` fills with NaN,
    # not None, and callers test `is None` (2E-c doubt-review cycle 2: the
    # coupon-only and free-item-only customers came back NaN).
    return pd.Series([None if name in refunders else months.get(name) for name in customers_seen],
                     index=customers_seen, dtype=object)
