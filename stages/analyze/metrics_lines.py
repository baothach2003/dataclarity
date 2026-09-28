"""Stage 2 Analyze - metrics.json's line-taxonomy blocks (Thach, session
2E-t2; docs/LINE_TAXONOMY.md sections 3 and 5; docs/CONTRACTS.md section 6):
the report of `shared/line_report.py` for the whole file and the two
compared months, and the identity of each month. Review shows the same
report for the whole file (stage 1, 2E-t3), from the same functions.
"""

import pandas as pd

from contracts.lines import FigureNote, OutsideRevenueLines, RevenueIdentity, UnmeasurableLines
from contracts.metrics import Period
from shared import line_report
from shared.transactions import ParsedTransactions


def scopes(months: pd.Series, period: Period) -> line_report.Scopes:
    return {"file": pd.Series(True, index=months.index), "current": months == period.current,
            "previous": months == period.previous}


def revenue_identity(parsed: ParsedTransactions, months: pd.Series, period: Period) -> RevenueIdentity:
    return RevenueIdentity(current=line_report.identity_terms(parsed, months == period.current),
                           previous=line_report.identity_terms(parsed, months == period.previous))


def outside_revenue(parsed: ParsedTransactions, months: pd.Series, period: Period) -> list[OutsideRevenueLines]:
    return line_report.outside_revenue(parsed, scopes(months, period))


def unmeasurable(parsed: ParsedTransactions, months: pd.Series, period: Period) -> list[UnmeasurableLines]:
    return line_report.unmeasurable(parsed, scopes(months, period))


def notes(df: pd.DataFrame, parsed: ParsedTransactions, months: pd.Series, period: Period) -> list[FigureNote]:
    return line_report.notes(df, parsed, scopes(months, period))
