"""A line's value when sales are split by one of the file's columns (the
dashboard's breakdowns; Thach's Q4, 2026-10-15; docs/DASHBOARD_DESIGN.md
section 5.1). One definition for stage 1, which decides whether a column can
split sales, and stage 2, which computes the split (CLAUDE.md 3.1).

A value is read as stage 3 reads a category (`category_key`): what no reader
can see removed, spaces collapsed, lower case. With a trusted order id
(`shared/orders.py`'s basis "order_id"), an order is one purchase: an export
that writes the order's fields on its first line only (Shopify) leaves the
order's other lines blank, and those lines are the same purchase - so a
blank line of an order holding exactly ONE value takes it. An order holding
two values cannot say which is its own: it is counted, never resolved (the
caller refuses the column). What an order holds is read on the `scope`
lines only - the lines that are split (counted in revenue).

Filled only when the column IS such a field by the data (the Q3-Q5 review's
F1): every line holding a value is the first scope line of its order. A
value on a later line shows a per-line attribute (a vendor, a size) - then
every line is read alone, and a blank line is a blank: filled, a bag's sales
went to the vendor of the shirt beside it."""

from typing import NamedTuple

import pandas as pd

from shared.text import category_key, category_text, is_blank


class SplitValues(NamedTuple):
    # Each line's value key; None where the line has none (blank, and not
    # filled from its order).
    keys: pd.Series
    # Each key's first spelling in the file - the name a member is shown by.
    names: dict[str, str]
    # The orders whose scope lines hold two or more values (0 without an
    # order id).
    conflicting_orders: int
    # Blank lines took their order's one value (the column is a first-line
    # field of a trusted order id).
    filled: bool


def split_values(values: pd.Series, order_key: pd.Series, by_order: bool, scope: pd.Series) -> SplitValues:
    """`values`: the column as cleaned.csv holds it; `order_key`: each line's
    order (parse_transactions); `by_order`: the order id is trusted; `scope`:
    the lines whose values say what an order holds."""
    blank = is_blank(values)
    keys = category_key(values).where(~blank, None).astype("object")
    names = {str(key): str(name) for key, name in
             category_text(values)[~blank].groupby(keys[~blank], sort=False).first().items()}
    if not by_order:
        return SplitValues(keys, names, 0, False)
    held = keys[scope & ~blank]
    per_order = held.groupby(order_key[held.index]).nunique()
    conflicting = int((per_order > 1).sum())
    first_line = pd.Series(keys.index[scope], index=keys.index[scope]).groupby(order_key[scope]).min()
    if not bool((order_key[held.index].map(first_line) == held.index.to_series()).all()):
        return SplitValues(keys, names, conflicting, False)
    single = per_order[per_order == 1].index
    one_value = held.groupby(order_key[held.index]).first().reindex(single)
    filled = keys.where(~blank, order_key.map(one_value))
    filled = filled.where(filled.notna(), None).astype("object")
    return SplitValues(filled, names, conflicting, True)
