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
ANY return line on it opens the history with a refund (Thach, 2E-c2). 2E-c
netted the day's quantities (the rule 3C's bridge used), and netting units
across products fabricated "new": 10 pens bought and a 500 chair from before
the file returned on the first day netted +9, and C1 headlined new-customer
revenue collapsing (2E-c doubt-review cycle 3). With no sum there is no
residue and no row-order effect. A coupon or a free item is not part of the
purchase history: taken as the opening day, a coupon on the 3rd hid a refund
on the 4th (2E-c doubt-review F4).
"""

import pandas as pd


def first_purchase_months(
    customers: pd.Series, dates: pd.Series, sale: pd.Series, returned: pd.Series,
) -> pd.Series:
    """Per customer key: the "YYYY-MM" of their first purchase, or None when
    the file holds none (only refunds, only deductions, or a history that
    opens with a refund). The caller passes the rows it identifies customers
    on, keyed as it groups them."""
    frame = pd.DataFrame({"customer": customers, "day": dates.dt.normalize(),
                          "sale": sale, "returned": returned})
    customers_seen = pd.Index(frame["customer"].unique())
    if frame.empty:
        return pd.Series([], index=customers_seen, dtype=object)

    history = frame[frame["sale"] | frame["returned"]]
    opening = history[history["day"] == history.groupby("customer")["day"].transform("min")]
    opens_with_refund = opening.groupby("customer")["returned"].any()

    first_sale = frame[frame["sale"]].groupby("customer")["day"].min()
    months = first_sale.dt.to_period("M").astype(str).to_dict()
    refunders = set(opens_with_refund[opens_with_refund].index)
    # Built value by value: `pd.Series(None, dtype=object)` fills with NaN,
    # not None, and callers test `is None` (2E-c doubt-review cycle 2: the
    # coupon-only and free-item-only customers came back NaN).
    return pd.Series([None if name in refunders else months.get(name) for name in customers_seen],
                     index=customers_seen, dtype=object)
