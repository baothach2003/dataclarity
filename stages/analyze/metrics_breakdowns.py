"""Stage 2 Analyze - the dashboard's breakdowns: "sales by <column>" for the
two compared months (Thach's D5, 2026-10-14; docs/DASHBOARD_DESIGN.md
section 7). metrics.json 16.3 `by_dimension.breakdowns`. Pure pandas.

The columns are the ones the user kept in Review (cleaning_report.json
`breakdowns`); this module chooses none. Each is read exactly as the category
block reads its column - the lines counted in revenue, their net amounts, a
value read as stage 3 reads a category - except that a blank cell is a member
of its own, "(blank)", so the members are the whole of each month's revenue:
a split that leaves part of the month out would not add up to the sales tile
beside it. A split that cannot be drawn is withheld with its reason, never a
failure (suppress, never fabricate).

16.4 (Thach's Q3 and Q4, 2026-10-15): a line's value is
`shared/split_values.py`'s - with a trusted order id, a blank line takes its
order's one value (an order holding two is withheld: stage 1 refuses such a
column); above ALL_SHOWN values, the TOP_SHOWN largest by the two months'
sales together and one "Other (N values)" member holding the rest."""

import re
from collections.abc import Sequence

import pandas as pd

from contracts.cleaning import FLAG_PREFIX, TAXONOMY_COLUMNS, OrderConfirmations
from contracts.metrics import ALL_SHOWN, BLANK_LABEL, TOP_SHOWN, Breakdown, BreakdownMember, Period, other_label
from shared.split_values import split_values
from shared.text import category_text
from shared.transactions import ParsedTransactions, is_blank, parse_transactions
from shared.wording import month_name

__all__ = ["BLANK_LABEL", "compute_breakdowns"]


def compute_breakdowns(
    df: pd.DataFrame, column_mapping: dict[str, str], period: Period, columns: Sequence[str],
    confirmations: OrderConfirmations | None = None,
) -> list[Breakdown]:
    """One Breakdown per column, in the order given. `period` is
    metrics_core's own: the same two months as every other block."""
    if not columns:
        return []
    parsed = parse_transactions(df, column_mapping, confirmations)
    months = parsed.dates.dt.to_period("M").astype(str)
    current = parsed.counted & (months == period.current)
    previous = parsed.counted & (months == period.previous)
    return [_one(df, column, parsed, current, previous, period) for column in columns]


def _withheld(column: str, reason: str) -> Breakdown:
    return Breakdown(column=column, members=[], change_reason=None, withheld_reason=reason)


# A value read as the folded values' label: on the chart it could not be told
# from them.
_OTHER_LIKE = re.compile(r"^other \(\d+ values?\)$")


def _one(df: pd.DataFrame, column: str, parsed: ParsedTransactions, current: pd.Series, previous: pd.Series,
         period: Period) -> Breakdown:
    months = f"{month_name(period.previous)} and {month_name(period.current)}"
    if column not in df.columns:
        return _withheld(column, "the column is not in the cleaned file")
    if column in TAXONOMY_COLUMNS or column.startswith(FLAG_PREFIX):
        # Stage 1's own columns (review 1 F4): no column of the user's file.
        return _withheld(column, "the column was added by the cleaning, not read from your file")
    in_months = current | previous
    if not bool(in_months.any()):
        return _withheld(column, f"no line counted in revenue is dated in {month_name(period.previous)} or "
                                 f"{month_name(period.current)}")
    raw = df[column]
    split = split_values(raw, parsed.order_key, parsed.orders_basis == "order_id", parsed.counted)
    if split.conflicting_orders:
        # Stage 1 refuses such a column (Q4); a hand-edited file is withheld, never resolved.
        return _withheld(column, "an order holds two different values of this column")
    keys = split.keys
    blank = keys.isna()
    values = keys[in_months & ~blank].nunique()
    shown = category_text(raw)[in_months & ~is_blank(raw)]  # as shown: trimmed, invisible characters gone
    if bool(shown.str.casefold().eq(BLANK_LABEL).any()):
        # A value written like the empty cells' bucket (an Excel pivot's
        # "(blank)", review 1 F1) could not be told from it on the chart.
        return _withheld(column, f'a value is written "{BLANK_LABEL}", the label of the empty cells')
    if values < 2:
        return _withheld(column, f"the column has {'one value' if values == 1 else 'no value'} in {months}, so it "
                                 "splits nothing")
    if values > ALL_SHOWN and bool(shown.str.casefold().str.match(_OTHER_LIKE.pattern).any()):
        return _withheld(column, 'a value is written like "Other (N values)", the label of the folded values')
    amounts = parsed.revenue_amounts
    group = keys.fillna("")  # one key for every blank line
    now = amounts[current].groupby(group[current]).sum()
    was = amounts[previous].groupby(group[previous]).sum()
    comparable = period.previous_complete

    def member(name: str, now_: float, was_: float, *, is_blank: bool = False, folded: int | None = None
               ) -> BreakdownMember:
        return BreakdownMember(name=name, is_blank=is_blank, revenue_current=now_, revenue_previous=was_,
                               change=now_ - was_ if comparable else None, is_other=folded is not None,
                               values=folded)

    totals = {key: (float(now.get(key, 0.0)), float(was.get(key, 0.0))) for key in set(now.index) | set(was.index)}
    named = [key for key in totals if key != ""]
    # By the two months' sales together, largest first; equal ones by name (Q3).
    named.sort(key=lambda key: (-(totals[key][0] + totals[key][1]), key))
    shown_keys = named if len(named) <= ALL_SHOWN else named[:TOP_SHOWN]
    members = sorted((member(split.names[key], *totals[key]) for key in shown_keys), key=lambda m: m.name)
    folded = named[len(shown_keys):]
    if folded:
        members.append(member(other_label(len(folded)), sum(totals[key][0] for key in folded),
                              sum(totals[key][1] for key in folded), folded=len(folded)))
    if "" in totals:
        members.append(member(BLANK_LABEL, *totals[""], is_blank=True))
    return Breakdown(column=column, members=members,
                     change_reason=None if comparable else period.previous_incomplete_reason, withheld_reason=None)
