"""Review's measure of the columns that might split sales (Thach's Q3-Q5,
2026-10-15): the plan run on the whole file by `clean_frame`, execute's own
function, then `stages/ingest/breakdown_lines.py` on its lines - as Review's
line summary does. A plan that cannot run yet measures nothing and says why:
no column is offered meanwhile (doubtful = not offered). Nothing is written."""

import pandas as pd

from contracts.cleaning import CleaningPlanContract
from stages.ingest.breakdown_lines import MeasuredLines, measure_cleaned
from stages.ingest.cleaning import CleaningError, clean_frame
from stages.ingest.date_order import DateQuestionUnanswered
from stages.ingest.line_taxonomy import is_classed
from stages.ingest.number_apply import NumberQuestionUnanswered
from stages.ingest.plan_validation import InvalidPlanError

_WHAT = "to see which columns can split sales."
NOT_CLASSED = f"Map a quantity and a unit price, and keep both columns, {_WHAT}"
NO_DATE = f"Map a date, and keep its column, {_WHAT}"
DATE_QUESTION = f"Answer how the dates are written {_WHAT}"
NUMBER_QUESTION = f"Answer how the numbers are written {_WHAT}"
NOT_RUNNABLE = f"Fix the plan's problems above {_WHAT}"


def measure_lines(frame: pd.DataFrame, plan: CleaningPlanContract) -> MeasuredLines:
    """Review's measure: `frame` is the whole raw file as `read_csv_text`
    returns it. A plan that cannot run yet measures nothing and says why -
    no column is offered meanwhile (doubtful = not offered)."""
    if not is_classed(plan):
        return MeasuredLines({}, NOT_CLASSED)
    if not any(a.canonical_field == "transaction_date" and a.action != "drop_column" for a in plan.column_actions):
        return MeasuredLines({}, NO_DATE)
    try:
        cleaned = clean_frame(frame, plan, for_execution=False)
    except DateQuestionUnanswered:
        return MeasuredLines({}, DATE_QUESTION)
    except NumberQuestionUnanswered:
        return MeasuredLines({}, NUMBER_QUESTION)
    except (InvalidPlanError, CleaningError):
        return MeasuredLines({}, NOT_RUNNABLE)
    return measure_cleaned(cleaned.frame, cleaned.read, cleaned.renames, cleaned.mapping, cleaned.applied, plan)
