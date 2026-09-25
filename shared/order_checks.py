"""Stage 1's checks of the order columns on the raw file (sessions 2E-e and
2E-e2), from one parse: whether a mapped order_id looks like one, and how many
lines the customer fill would give their receipt's customer - the measure
behind Review's fill question. Moved out of shared/transactions.py, which
reads a file for every stage, when it passed 300 lines. `parse_transactions`
is called through its module, so a test can watch the one parse.
"""

from typing import NamedTuple

import pandas as pd

from shared import transactions
from shared.orders import IdCheck, spanning_ids


class OrderChecks(NamedTuple):
    """Stage 1's two checks of the order columns on the raw file, from one
    parse (2E-e2 review M: two parses cost ~7 s more at 50 MB)."""

    # The order_id check's figures over the sale lines (2E-e); None when
    # order_id is not mapped or the file cannot be parsed into sale lines.
    spanning: IdCheck | None
    # How many lines the customer fill would give their receipt's customer,
    # for Review's question (2E-e2); None when the raw file cannot say: no
    # sale line parses before the plan's cleaning, or blank ids make it count
    # lines - the cleaning may still let the fill happen (cycle 2 F5, F6).
    fill_lines: int | None


def order_checks(df: pd.DataFrame, column_mapping: dict[str, str]) -> OrderChecks:
    if "order_id" not in column_mapping.values():
        return OrderChecks(None, 0)
    unmeasured = None if "customer" in column_mapping.values() else 0
    try:
        parsed = transactions.parse_transactions(df, column_mapping)
    except transactions.RequiredColumnMissingError:
        return OrderChecks(None, unmeasured)
    sale = parsed.sale
    ids = transactions.order_ids(df, parsed.reverse["order_id"])
    check = spanning_ids(ids[sale], parsed.dates.dt.normalize()[sale],
                         transactions.customers_of(df, parsed.reverse.get("customer"))[sale])
    if not sale.any() or ((sale | parsed.returned) & ids.isna()).any():
        return OrderChecks(check, unmeasured)
    return OrderChecks(check, int(parsed.receipt_fillable.sum()))


def receipt_fill_lines(df: pd.DataFrame, column_mapping: dict[str, str]) -> int | None:
    """`order_checks`' fill measure alone: 0 without parsing when order_id or
    customer is not mapped."""
    if not {"order_id", "customer"} <= set(column_mapping.values()):
        return 0
    return order_checks(df, column_mapping).fill_lines


def order_id_spanning(df: pd.DataFrame, column_mapping: dict[str, str]) -> IdCheck | None:
    """`order_checks`' order_id check alone."""
    return order_checks(df, column_mapping).spanning
