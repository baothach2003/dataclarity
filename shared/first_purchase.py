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
it nets their quantities (the rule 3C's bridge already used): a same-day
buy-and-refund is not an opening refund, but returning more than was bought
that day is. A coupon or a free item is not part of the purchase history:
taken as the opening day, a coupon on the 3rd hid a refund on the 4th
(2E-c doubt-review F4). A net that is floating-point residue is not a refund:
0.3 - 0.1 - 0.2 read as one in one row order and not in the other (F5).
"""

import pandas as pd

from shared.numbers import is_negligible


def first_purchase_months(
    customers: pd.Series, dates: pd.Series, quantities: pd.Series,
    sale: pd.Series, returned: pd.Series,
) -> pd.Series:
    """Per customer key: the "YYYY-MM" of their first purchase, or None when
    the file holds none (only refunds, only deductions, or a history that
    opens with a refund). The caller passes the rows it identifies customers
    on, keyed as it groups them."""
    frame = pd.DataFrame({"customer": customers, "day": dates.dt.normalize(),
                          "quantity": quantities, "sale": sale, "returned": returned})
    customers_seen = pd.Index(frame["customer"].unique())
    if frame.empty:
        return pd.Series([], index=customers_seen, dtype=object)

    history = frame[frame["sale"] | frame["returned"]]
    opening = history[history["day"] == history.groupby("customer")["day"].transform("min")]
    net = opening.groupby("customer")["quantity"].sum()
    moved = opening["quantity"].abs().groupby(opening["customer"]).sum()
    opens_with_refund = pd.Series(
        [value < 0 and not is_negligible(value, scale) for value, scale in zip(net, moved)],
        index=net.index, dtype=bool)

    first_sale = frame[frame["sale"]].groupby("customer")["day"].min()
    months = first_sale.dt.to_period("M").astype(str).to_dict()
    refunders = set(opens_with_refund[opens_with_refund].index)
    # Built value by value: `pd.Series(None, dtype=object)` fills with NaN,
    # not None, and callers test `is None` (2E-c doubt-review cycle 2: the
    # coupon-only and free-item-only customers came back NaN).
    return pd.Series([None if name in refunders else months.get(name) for name in customers_seen],
                     index=customers_seen, dtype=object)
