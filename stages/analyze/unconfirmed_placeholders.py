"""Walk-in candidates left unanswered in Review (2E-u3; Thach, 2026-10-02, 2E-u
F3): stage 1 records them (cleaning_report.json `unconfirmed_placeholders`);
they stay customers in every figure - the data cannot tell "Guest" the
walk-in default from a customer named Guest, and only the user's Yes changes
the figures (2E-k; CLAUDE.md 3.3a) - and are marked "suggested, not
confirmed", like Q17's suggested classes."""

from collections.abc import Sequence

import pandas as pd

from contracts.metrics import Period, UnconfirmedPlaceholder
from shared.text import customer_identity
from shared.transactions import ParsedTransactions


NAMED = 5


def unconfirmed_placeholders(parsed: ParsedTransactions, period: Period, values: Sequence[str]) -> dict:
    """One row per value with a counted line left, by customer identity as
    every customer figure reads it (a receipt's filled lines included), and
    the reason - null exactly when no row."""
    months = parsed.dates.dt.to_period("M").astype(str)
    rows = []
    for value, identity in zip(values, customer_identity(pd.Series(list(values), dtype=object))):
        lines = parsed.counted & parsed.customers.eq(identity)
        if lines.any():
            rows.append(UnconfirmedPlaceholder(
                value=value, lines=int(lines.sum()), lines_current=int((lines & months.eq(period.current)).sum()),
                lines_previous=int((lines & months.eq(period.previous)).sum())))
    if not rows:
        return {"unconfirmed_placeholders": [], "unconfirmed_placeholders_reason": None}
    # Five named, the rest counted: 400 numbered guests made a 16,604-character
    # sentence (review 1, #5).
    parts = [f'"{row.value}" ({row.lines:,} {"line" if row.lines == 1 else "lines"}, {row.lines_current:,} in '
             f"{period.current})" for row in rows[:NAMED]]
    if len(rows) > NAMED:
        parts.append(f"{len(rows) - NAMED:,} more ({sum(row.lines for row in rows[NAMED:]):,} lines)")
    named = parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " and " + parts[-1]
    if len(rows) == 1:
        what, lines, them = "is a placeholder", "its lines stay one customer's", "it"
    else:
        what, lines, them = "are placeholders", "their lines stay one customer's each", "them"
    # "The file suggests": Review may not have shown a value - a customer
    # column remapped is asked from its top values (review 1, #4).
    return {"unconfirmed_placeholders": rows,
            "unconfirmed_placeholders_reason": (
                f"The file suggests {named} {what} for walk-ins - suggested, not confirmed: {lines} in every "
                f"customer figure and cause. Confirm {them} in Review to count those lines with no customer.")}
