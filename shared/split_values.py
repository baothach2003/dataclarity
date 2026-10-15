"""A line's value when sales are split by one of the file's columns (the
dashboard's breakdowns; Thach's Q4, 2026-10-15, his Q6 and Q7, 2026-10-16;
docs/DASHBOARD_DESIGN.md section 5.1). One definition for stage 1, which
decides whether a column can split sales, and stage 2, which computes the
split (CLAUDE.md 3.1).

A value is read as stage 3 reads a category (`category_key`): what no reader
can see removed, spaces collapsed, lower case. Each line is read alone: a
column whose values differ between the lines of one order (a vendor, a
product category, a size) is a LINE attribute, each line's sales its own
value's (Q6). Only one shape is filled: with a trusted order id
(`shared/orders.py`'s basis "order_id"), a column written on each order's
first line only (Shopify's order fields) - every line holding a value is
the first `scope` line of its order, and some order has a blank line under
its value. The data cannot tell such an order field from a line attribute
written on the first line only (a vendor on the shirt, nothing on the bag),
so it is filled only when the user said the column applies to the whole
order (`fill`, Q7; CLAUDE.md 3.3a: never guess) - then a blank line of an
order takes the order's one value. What an order holds is read on the
`scope` lines only - the lines that are split (counted in revenue)."""

from typing import NamedTuple

import pandas as pd

from shared.text import category_key, category_text, is_blank


class SplitValues(NamedTuple):
    # Each line's value key; None where the line has none (blank, and not
    # filled from its order).
    keys: pd.Series
    # Each key's first spelling in the file - the name a member is shown by.
    names: dict[str, str]
    # The column is written on each order's first line only, and a blank
    # line would take its order's value: the question Review asks (Q7).
    first_line_only: bool
    # Blank lines took their order's one value (first-line only, and the user
    # said it applies to the whole order).
    filled: bool


def split_values(values: pd.Series, order_key: pd.Series, by_order: bool, scope: pd.Series,
                 fill: bool = False) -> SplitValues:
    """`values`: the column as cleaned.csv holds it; `order_key`: each line's
    order (parse_transactions); `by_order`: the order id is trusted; `scope`:
    the lines whose values say what an order holds; `fill`: the user said the
    column applies to the whole order (Q7)."""
    blank = is_blank(values)
    keys = category_key(values).where(~blank, None).astype("object")
    names = {str(key): str(name) for key, name in
             category_text(values)[~blank].groupby(keys[~blank], sort=False).first().items()}
    if not by_order:
        return SplitValues(keys, names, False, False)
    held = keys[scope & ~blank]
    first_line = pd.Series(keys.index[scope], index=keys.index[scope]).groupby(order_key[scope]).min()
    if not bool((order_key[held.index].map(first_line) == held.index.to_series()).all()):
        return SplitValues(keys, names, False, False)
    # Every value on its order's first line, so each order holds one value at most: the blank scope lines of
    # an order holding one would take it.
    one_value = held.groupby(order_key[held.index]).first()
    takes = scope & blank & order_key.isin(one_value.index)
    if not bool(takes.any()):
        return SplitValues(keys, names, False, False)
    if not fill:
        return SplitValues(keys, names, True, False)
    filled = keys.where(~takes, order_key.map(one_value))
    filled = filled.where(filled.notna(), None).astype("object")
    return SplitValues(filled, names, True, True)
