"""What an ORDER is: one definition, shared by stage 1's check, stage 2 and
stage 3 (Thach, session 2E-e). Infrastructure in the sense of
`shared/transactions.py`, which builds on it.

The canonical schema had no order field, so every "order" was a LINE: on a
one-line-per-transaction file (the Kaggle demo) that is harmless, on Online
Retail II AOV was average line value (18.20 against 475.53 by invoice) and
frequency lines per customer (32.2 against 1.58). With the optional field
`order_id` mapped, orders are the distinct order keys - an id on one day for
one customer - that have a sale row; if any sale or return line has a blank
id, the file counts lines instead (Online Retail II has none). Without it,
every sale line is an order and the figures say "lines".

A real order is one order: its lines share one day and one customer. When
more than ORDER_ID_MAX_SPANNING_SHARE of a column's ids span several days or
customers, the column is not an order id - stage 1 flags it on the Review
screen and the figures fall back to lines with a reason, the safe side.
"""

from typing import Literal, NamedTuple

import pandas as pd

# Measured on both real files (scratchpad 2ee/order_id_guard.out): the real
# order ids - Online Retail II's Invoice, the Kaggle demo's Transaction ID -
# have 0.0% of ids spanning more than one day or customer; every other column
# (StockCode, Customer ID, Description, Country, Location, Payment Method)
# 74% to 100%. 10% sits in that gap and leaves room for a real order that
# crosses midnight or ships over two days (Thach, 2E-e).
ORDER_ID_MAX_SPANNING_SHARE = 0.10

OrdersBasis = Literal["order_id", "lines"]
# The order key of a line counted on its own (U+241E, the symbol for a record
# separator: printable, never in a POS export's order ids).
LINE_KEY_PREFIX = "\u241eline "
# Between an order id, its day and its customer in the order key (U+241F).
SEP = "\u241f"



class OrderBasis(NamedTuple):
    basis: OrdersBasis
    reason: str | None
    key: pd.Series  # per row: the order it belongs to


class IdCheck(NamedTuple):
    spanning: int   # ids covering more than one day or more than one customer
    total: int      # all ids


def spanning_ids(ids: pd.Series, days: pd.Series, customers: pd.Series) -> IdCheck:
    """The check's figures over the rows passed in with a non-blank id. A blank
    customer does not count as a second customer."""
    present = ids.notna()
    frame = pd.DataFrame({"id": ids[present], "day": days[present],
                          "customer": customers[present]})
    if frame.empty:
        return IdCheck(0, 0)
    grouped = frame.groupby("id")
    spans = (grouped["day"].nunique() > 1) | (grouped["customer"].nunique() > 1)
    return IdCheck(int(spans.sum()), int(len(spans)))


def looks_like_order_ids(check: IdCheck) -> bool:
    """At most ORDER_ID_MAX_SPANNING_SHARE of the ids span several days or
    customers (and there is at least one id). Known limit, for Thach (2E-e
    doubt-review F4): with no customer column only the day test is left, so a
    batch or Z-report id - one per trading day - passes; "no day holds two
    ids" would also refuse a real shop taking one order a day, and the data
    cannot tell the two apart."""
    return check.total > 0 and check.spanning / check.total <= ORDER_ID_MAX_SPANNING_SHARE


def refusal_reason(check: IdCheck) -> str:
    if check.total == 0:
        # Blank ids are refused before this, so no id means no sale line (F5).
        return "the file holds no sale line to count orders on"
    # Counts, and "more than": "10%" for 10.4% and "10.0%" for 10.04% both read
    # as a refusal AT the limit (2E-e doubt-review F9, cycle 2 F4).
    return (f"{check.spanning:,} of {check.total:,} order ids "
            f"({check.spanning / check.total:.1%}, more than {ORDER_ID_MAX_SPANNING_SHARE:.0%}) "
            "cover several days or customers, so the column does not look like an order id; "
            "the figures count lines")


def order_basis(ids: pd.Series | None, days: pd.Series, customers: pd.Series,
                sale: pd.Series, returned: pd.Series) -> OrderBasis:
    """`ids` is the mapped order_id column, stripped, blank as NaN - or None
    when order_id is not mapped. `days`, `customers`, `sale` and `returned`
    are aligned with it; the check runs over the sale rows."""
    # Every line its own order, under a key no real id takes. Not a leading
    # NUL: pandas' object-dtype `nunique` counts "\x00line 2" and "\x00line 3"
    # as ONE value (measured in 2E-e), so two blank-id lines became one order.
    by_line = pd.Series(LINE_KEY_PREFIX + days.index.astype(str), index=days.index)
    if ids is None:
        return OrderBasis("lines", None, by_line)
    # A blank id on a sale or return line leaves the file half on orders, half
    # on lines: ids blank until a POS upgrade made orders fall 279 -> 93 on an
    # unchanged business (2E-e doubt-review cycle 2, F1), and refunds rung up
    # without a receipt took the return rate 0.097 -> 0.387 (cycle 3, F1). Any
    # such line makes the file count lines - the safe side, superseding
    # decision 1's blank-id clause (Thach decides a tolerance).
    moved = sale | returned
    blank = int((moved & ids.isna()).sum())
    if blank:
        return OrderBasis("lines", f"{blank:,} of {int(moved.sum()):,} sale and return lines "
                                   "have no order id, so orders cannot be counted by id; the "
                                   "figures count lines", by_line)
    # A customer written on a receipt's first line only (ERP "invoice detail"
    # exports) is that receipt's customer on its other lines too: keyed as a
    # customer "", every order split in two (cycle 2, F2).
    customers = _one_customer_per_order(ids, days, customers)
    check = spanning_ids(ids[sale], days[sale], customers[sale])
    if not looks_like_order_ids(check):
        return OrderBasis("lines", refusal_reason(check), by_line)
    # An order is one order - one day, one customer: an id is keyed WITH its
    # day and customer, so an id reused elsewhere (two tills sharing a receipt
    # numbering) splits instead of merging. Merged, 27 reused ids in 310 took
    # orders 310 -> 283 and AOV +9.5% under the tolerance (2E-e review F5). A
    # blank id: the line is an order on its own.
    keyed = (ids + SEP + days.dt.strftime("%Y-%m-%d") + SEP
             + customers.fillna("").astype(str))
    return OrderBasis("order_id", None, keyed.where(ids.notna(), by_line))


def _one_customer_per_order(ids: pd.Series, days: pd.Series,
                            customers: pd.Series) -> pd.Series:
    """A blank customer takes the one named customer of its id on its day,
    when there is exactly one; otherwise it stays blank."""
    frame = pd.DataFrame({"id": ids, "day": days, "customer": customers})
    named = frame.dropna(subset=["id", "customer"])
    single = named.groupby(["id", "day"])["customer"].agg(
        lambda values: values.iloc[0] if values.nunique() == 1 else None)
    fill = pd.Series(list(zip(frame["id"], frame["day"])), index=frame.index).map(single)
    return customers.where(customers.notna(), fill)


def count_orders(order_key: pd.Series, mask: pd.Series) -> int:
    """Distinct orders among the rows in `mask` - pass a sale mask for
    orders, a return mask for orders holding a return line."""
    return int(order_key[mask].nunique())
