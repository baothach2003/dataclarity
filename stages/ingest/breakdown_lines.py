"""What the lines say of each column that might split sales (Thach's Q3, Q4
and Q5, 2026-10-15; docs/DASHBOARD_DESIGN.md section 5.1; method
C:/Users/Happy/dashboard-q345-method.txt). Measured on the lines execute
would write - the plan run on the whole file by `clean_frame`, read back as
cleaned.csv holds it, through the shared reading of lines and orders - so
Review, execute and stage 2 read one file the same way. Nothing is written.

A line's value is `shared/split_values.py`'s: each line its own (Thach's
Q6: a column whose values differ inside an order is a line attribute); a
column written on each order's first line only is measured as it would be
drawn if the user answers that it applies to the whole order (Q7) - its
blanks per order - and Review asks. The file's OWN blank cells count as
blank even when the plan fills them (an imputed "Unknown" is no value of the
file): Kaggle's Discount Applied is a third blank, imputed - offered, a third
of the split would be the plan's word."""

from typing import NamedTuple

import pandas as pd

from contracts.cleaning import CleaningPlanContract, OrderConfirmations
from shared.split_values import split_values
from shared.text import is_blank
from shared.transactions import ParsedTransactions, parse_transactions
from stages.ingest.cleaned_text import as_read

class ColumnLines(NamedTuple):
    """One column, over the lines counted in revenue."""

    first_line_only: bool   # written on each order's first line only (Q7): Review asks; blanks per order
    units: int              # orders (first_line_only) or lines - what the blanks are counted on
    values: int             # distinct values
    blank_units: int        # orders with no value of the file's (first_line_only); lines otherwise
    orders: bool            # a trusted order id: "nearly every order its own value" (Q3)
    purchases: int          # orders (a trusted order id) or lines - what the values are counted against
    sale_or_return: bool    # Q5: sale and return lines in the file, each value holding one kind only


class MeasuredLines(NamedTuple):
    columns: dict[str, ColumnLines]  # by the column's name in the file
    unavailable: str | None          # why nothing could be measured (then `columns` is empty)


def measure_cleaned(frame: pd.DataFrame, read: pd.DataFrame, renames: dict[str, str], mapping: dict[str, str],
                    applied: OrderConfirmations, plan: CleaningPlanContract) -> MeasuredLines:
    """The plan's cleaned lines (`clean_frame`'s frame, read, renames, mapping
    and applied answers) measured - execute's own, and Review's through
    `stages/ingest/breakdown_review.py`."""
    candidates = {a.source_name: renames.get(a.source_name, a.source_name) for a in plan.column_actions
                  if a.canonical_field == "ignore" and a.action != "drop_column"}
    present = {name: written for name, written in candidates.items() if written in frame.columns}
    text = as_read(frame, mapping | {written: "ignore" for written in present.values()})
    parsed = parse_transactions(text, mapping, applied)
    # The file's own cells, line by line beside cleaned.csv's (cleaning keeps the row index).
    return MeasuredLines({name: _column(text[written], read[name].loc[frame.index].reset_index(drop=True), parsed)
                          for name, written in present.items()}, None)


def _column(values: pd.Series, file_cells: pd.Series, parsed: ParsedTransactions) -> ColumnLines:
    counted = parsed.counted
    trusted = parsed.orders_basis == "order_id"
    # A first-line column is measured filled - as drawn once the user says it applies to the whole order (Q7;
    # unanswered it is not offered at all); any other column line by line (Q6).
    split = split_values(values, parsed.order_key, trusted, counted, fill=True)
    by_order = split.first_line_only
    keys = split.keys
    # Blank: no value after the fill, or the file's own cell blank on every line of its order (an imputed cell).
    file_blank = is_blank(file_cells.astype("object")).to_numpy()
    no_value = keys.isna().to_numpy() | file_blank
    purchases = int(parsed.order_key[counted].nunique()) if trusted else int(counted.sum())
    if by_order:
        orders = parsed.order_key[counted]
        has_value = pd.Series(~no_value, index=values.index)[counted].groupby(orders).any()
        units, blank_units = len(has_value), int((~has_value).sum())
    else:
        units, blank_units = int(counted.sum()), int((no_value & counted.to_numpy()).sum())
    distinct = int(keys[counted].dropna().nunique())
    group = keys.fillna("")[counted]
    sales = parsed.sale[counted].groupby(group).any()
    returns = parsed.returned[counted].groupby(group).any()
    both_kinds = bool(sales.any()) and bool(returns.any())
    return ColumnLines(first_line_only=by_order, units=units, values=distinct, blank_units=blank_units,
                       orders=trusted, purchases=purchases,
                       sale_or_return=both_kinds and not bool((sales & returns).any()))
