"""Lines dated after the upload (2E-u6; Thach, 2026-10-02, 2E-u F6): left out
of choosing the period, counted and reported. The cutoff and the mask are
shared/periods.py's, so stage 3 leaves out the same lines."""

from datetime import date

import pandas as pd

from shared.transactions import ParsedTransactions


def future_lines(parsed: ParsedTransactions, future: pd.Series, cutoff: date) -> dict:
    """The count of the lines after `cutoff`, of any class (any dated line
    moved the dates the file covers), the counted ones' revenue, and the
    reason - the figures keep them in their own month (the standing no-guess
    rule, CLAUDE.md 3.3a: 2042 may be 2024 or 2012 mistyped)."""
    count = int(future.sum())
    if count == 0:
        return {"future_lines": 0, "future_revenue": 0.0, "future_lines_reason": None}
    counted = future & parsed.counted
    revenue = float(parsed.revenue_amounts[counted].sum()) + 0.0
    latest = parsed.dates[future].max().date()
    lines, it, its, counts = (("1 line is", "it is", "its", "it counts") if count == 1 else
                              (f"{count:,} lines are", "they are", "their", "they count"))
    # The cutoff is the upload's day on the clock furthest ahead, so it can
    # be the day after the upload in UTC (2E-u6 review 1, #6).
    money = (f"{its} revenue ({revenue:,.2f}) stays in its own month, outside both compared months"
             if counted.any() else f"{counts} in no revenue figure")
    return {"future_lines": count, "future_revenue": revenue,
            "future_lines_reason": (
                f"{lines} dated after this file was uploaded - later than {cutoff} on any clock - the latest "
                f"{latest}, so {it} left out of choosing the months compared and the dates the file covers; "
                f"{money}.")}
