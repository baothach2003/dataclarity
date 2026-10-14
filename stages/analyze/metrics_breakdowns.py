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
failure (suppress, never fabricate)."""

from collections.abc import Sequence

import pandas as pd

from contracts.cleaning import FLAG_PREFIX, TAXONOMY_COLUMNS, OrderConfirmations
from contracts.metrics import BLANK_LABEL, MAX_BREAKDOWN_VALUES, Breakdown, BreakdownMember, Period
from shared.text import category_key, category_text
from shared.transactions import is_blank, parse_transactions
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
    return [_one(df, column, parsed.revenue_amounts, current, previous, period) for column in columns]


def _withheld(column: str, reason: str) -> Breakdown:
    return Breakdown(column=column, members=[], change_reason=None, withheld_reason=reason)


def _one(df: pd.DataFrame, column: str, amounts: pd.Series, current: pd.Series, previous: pd.Series,
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
    blank = is_blank(raw)
    keys = category_key(raw).where(~blank, None)
    values = keys[in_months & ~blank].nunique()
    shown = category_text(raw)[in_months & ~blank]  # as shown: trimmed, invisible characters gone
    if bool(shown.str.casefold().eq(BLANK_LABEL).any()):
        # A value written like the empty cells' bucket (an Excel pivot's
        # "(blank)", review 1 F1) could not be told from it on the chart.
        return _withheld(column, f'a value is written "{BLANK_LABEL}", the label of the empty cells')
    if values < 2:
        return _withheld(column, f"the column has {'one value' if values == 1 else 'no value'} in {months}, so it "
                                 "splits nothing")
    if values > MAX_BREAKDOWN_VALUES:
        return _withheld(column, f"the column has {values} values in {months}; a split is drawn for "
                                 f"{MAX_BREAKDOWN_VALUES} at most")
    # The first spelling in the file, as the category block names a category.
    names = category_text(raw)[~blank].groupby(keys[~blank]).first()
    group = keys.fillna("")  # one key for every blank cell
    now = amounts[current].groupby(group[current]).sum()
    was = amounts[previous].groupby(group[previous]).sum()
    comparable = period.previous_complete
    members = []
    for key in set(now.index) | set(was.index):
        revenue_current, revenue_previous = float(now.get(key, 0.0)), float(was.get(key, 0.0))
        members.append(BreakdownMember(
            name=BLANK_LABEL if key == "" else str(names[key]), is_blank=key == "",
            revenue_current=revenue_current, revenue_previous=revenue_previous,
            change=revenue_current - revenue_previous if comparable else None))
    members.sort(key=lambda m: (m.is_blank, m.name))
    return Breakdown(column=column, members=members,
                     change_reason=None if comparable else period.previous_incomplete_reason, withheld_reason=None)
