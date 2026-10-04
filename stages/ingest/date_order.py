"""How the date column's day-month-year cells are read: decided at stage 1
(Thach, 2E-h; session 2E-j).

"05/01/2026" is 5 January or 1 May, and nothing in the cell says which.
Read month first by default, an Australian shop's days 1-12 landed in
January to December, and a parse step with pandas' `dayfirst` re-read ISO
dates the same way. So stage 1 decides, on the RAW file: the user's answer
in Review, else what the cells prove (a first number 13-31 can only be a
day). When both or neither prove it and nobody answered, the plan does not
run - either default fabricates dates. The order applied goes into
cleaning_report.json, where stages 2 and 3 read it.

A parse step on the date column must read the cells as the order does:
readings are compared, not flags, and only on the cells the order concerns,
so a step that happens to be right is never refused. profile.json's
measure of each column is profiling.py's (`date_order_measure`), for Review.
"""

import pandas as pd

from contracts.cleaning import CleaningPlanContract
from contracts.profile import DateOrder
from shared.date_evidence import OrderEvidence, applied_order, order_evidence, shaped_cells
from shared.dates import as_dates
from stages.ingest.plan_validation import InvalidPlanError

_WORDS: dict[DateOrder, str] = {"day_first": "day first", "month_first": "month first"}


class DateFormatMisreads(InvalidPlanError):
    """The plan's parse step would read the date column against the order
    decided for it: cleaning would write some dates wrong (2E-j). Its own
    class so a caller can say so by code (6A-6D review S1)."""


class DateQuestionUnanswered(InvalidPlanError):
    """The date column reads either way and nobody has said which: Review's
    question is open (2E-j). A plan in that state is not executed; Review's
    whole-file summary waits for the answer (2E-t3 review 1 #2)."""


def execution_order(plan: CleaningPlanContract, frame: pd.DataFrame) -> DateOrder | None:
    """The order the plan's date column is read in, on the raw `frame`: the
    user's answer, else the cells' proof; None when no cell needs one.
    Raises InvalidPlanError when nobody can say, or when the column's parse
    step reads some cell otherwise."""
    column = next((a.source_name for a in plan.column_actions
                   if a.canonical_field == "transaction_date" and a.action != "drop_column"), None)
    if column is None or column not in frame.columns:
        return None
    values = frame[column]
    answer = plan.confirmations.dates_day_first
    evidence = order_evidence(values)
    if evidence.shaped == 0:
        # No cell to read in an order: an answer changes nothing, and none is
        # recorded (CONTRACTS section 5; 2E-j review cycle 1 #9).
        return None
    if answer is None and evidence.decision == "ask":
        raise DateQuestionUnanswered([_unanswered(column, evidence)])
    order = applied_order(evidence, answer)
    if order is None:
        return None
    step = next(a for a in plan.column_actions if a.source_name == column)
    if step.action == "parse_datetime":
        problem = _misread(column, values, step.params, order, evidence, answer is not None)
        if problem is not None:
            raise DateFormatMisreads([problem])
    return order


def _unanswered(column: str, evidence: OrderEvidence) -> str:
    if evidence.day_first and evidence.month_first:
        why = (f"{evidence.day_first_example!r} can only be day first and "
               f"{evidence.month_first_example!r} only month first")
    else:
        why = f"such as {evidence.ambiguous_example!r}, which could be either"
    # A run profiled before 2E-j has no measure, so Review shows no question
    # (2E-j review cycle 1 #13).
    return (f"The dates in column {column!r} can be read day first or month first ({why}), "
            "and nobody said which: answer the date question in Review (if Review shows none, "
            "upload the file again)")


def _reads_day_month_year(date_format: str) -> bool:
    """Whether a format can read a day-month-year date: its day and month
    both before its year. "%y/%m/%d" reads "26/01/05" as 5 January 2026,
    which looks like a day-month-year cell (2E-j review cycle 2 #2)."""
    day, month = date_format.find("%d"), date_format.find("%m")
    year = max(date_format.find("%Y"), date_format.find("%y"))
    return day >= 0 and month >= 0 and year > max(day, month)


def _misread(column: str, values: pd.Series, params: dict, order: DateOrder,
             evidence: OrderEvidence, answered: bool) -> str | None:
    """The first cell the parse step reads other than `order` does - a date
    where the order reads none counts; a cell the step cannot read is
    flagged by the step itself, as any cell a format misses. A format that
    cannot read a day-month-year date says nothing about the order."""
    date_format = params.get("format")
    if isinstance(date_format, str) and not _reads_day_month_year(date_format):
        return None
    cells = values[shaped_cells(values)]
    if cells.empty:
        return None
    step = as_dates(cells, date_format if isinstance(date_format, str) else None,
                    bool(params.get("dayfirst", False)), offsets="wall_clock")
    decided = as_dates(cells, offsets="wall_clock", order=order)
    wrong = step.notna() & (decided.isna() | step.ne(decided))
    if not wrong.any():
        return None
    first = wrong.idxmax()
    want = "no date" if pd.isna(decided[first]) else f"{decided[first]:%Y-%m-%d}"
    # What would make the step read as the order does, from where it stands:
    # per cell, pandas reads a cell only day first can hold day first, so a
    # month-first order with such cells needs a format (2E-j review cycle 1 #9).
    if order == "day_first":
        fix = "set its dayfirst to true and leave out a format, or give one such as '%d/%m/%Y'"
    elif evidence.day_first:
        fix = ("give it a format such as '%m/%d/%Y' - per cell, pandas reads "
               f"{evidence.day_first_example!r} day first")
    else:
        fix = "leave dayfirst and a day-first format out, or give a format such as '%m/%d/%Y'"
    # The answer is named only when there was one; a proven order is
    # overridden in Review, not answered (2E-j review cycle 2 #2; 2E-o Q8).
    # Never advice to override a proof: it steered a user against the data
    # to fit the plan's step (2E-o review cycle 3 #5).
    also = ", or change the answer to the date question in Review" if answered else ""
    return (f"parse_datetime on column {column!r} reads {cells[first]!r} as "
            f"{step[first]:%Y-%m-%d}, but the dates are written {_WORDS[order]} ({want}): "
            f"{fix}{also}")
