"""When is the previous month a base the current one can be compared with?

One definition for stage 2 (which then reports every comparison as
unavailable) and stage 3 (whose trust gate then blocks the diagnosis), so
the two can never disagree about which files hold a comparable pair (Thach,
session 2E). Infrastructure in the same sense as `transactions.py`: it
decides what the data covers, not what any KPI means.

The rule is 3E1's: stage 2's elapsed-month period selection compares a whole
month with half of one when a file starts mid-month, and an export starting
on 15 January headlined "customers bought more often (100%)" on identical
daily trading. A previous month is complete when it has a counted row and
fewer than `PREVIOUS_MIN_MISSING_DAYS` days precede its first counted row -
one closed New Year's Day is not a cut export. Coverage is judged on SALE rows since the 2E
doubt-review (F3): a month holding only refund lines was "complete" while
every order figure read it as empty, and a product sold for nineteen months
was headlined as launched. The rule applies from the FILE's first sale;
a leading gap in the middle of the history is D1's to catch in stage 3 -
tested on the month's own first sale, it falsely flagged 15-35% of sparse
shops and 13-17% of shops closed three days a week (measured, 2E), so the
pattern-aware version belongs to 3E1b, inside this one definition. (D1 also
cautions at 10% of a
month. As a second condition on a complete month it could never bind: the
largest whole count "fewer than 3" allows is 2, and 2 days is under 10% of
every month, 2.8 to 3.1 days. The 2E mutation check showed dropping it
changes no result, so it is not written.) The caller passes SALE dates: neither a stock-in row nor
a refund line is a sale (3E1 doubt-review cycle 4; 2E doubt-review F3).
"""

from dataclasses import dataclass
from datetime import date

import pandas as pd

# Equal to stage 3's D1 caution size (D1_CAUTION_DAYS): a leading gap that
# would caution as missing days blocks as a partial month.
PREVIOUS_MIN_MISSING_DAYS = 3


@dataclass(frozen=True)
class PreviousCoverage:
    leading_days_missing: int  # days before the file's first sale, capped at the month
    has_rows: bool
    complete: bool
    first_counted: date | None  # the file's first sale row, anywhere
    reason: str | None  # why the month is not a base; None when complete


def previous_coverage(sale_dates: pd.Series, previous: str) -> PreviousCoverage:
    year, month = (int(part) for part in previous.split("-"))
    start = date(year, month, 1)
    days = (date(year + month // 12, month % 12 + 1, 1) - start).days
    valid = sale_dates.dropna()
    first = None if valid.empty else valid.min().date()
    in_month = valid[valid.dt.to_period("M").astype(str) == previous]
    has_rows = not in_month.empty
    leading = days if first is None else min(days, max(0, (first - start).days))
    complete = has_rows and leading < PREVIOUS_MIN_MISSING_DAYS
    if complete:
        reason = None
    else:
        where = (f"the file has no sales in {previous}, the month the current one is "
                 "compared with" if not has_rows else
                 f"the file's first sale is on {first.isoformat()}, {leading} days into "
                 f"{previous}, the month the current one is compared with, so that month "
                 "is incomplete")
        reason = (f"{where[0].upper()}{where[1:]}. If the export was cut short, re-export "
                  f"the file from {previous}-01; if the shop opened then, there is no "
                  "full month to compare with yet.")
    return PreviousCoverage(leading, has_rows, complete, first, reason)
