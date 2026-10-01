"""Review's view of the whole file (Thach, session 2E-t3;
docs/LINE_TAXONOMY.md section 5): the revenue identity of every counted line
for the plan and the answers as they stand, the lines outside revenue beside
it, the unclassified and unmeasurable counts, the notes, and the source
columns the run will write under another name (Q24).

Computed on the lines execute would write - the plan run on the whole file
by `clean_frame`, execute's own function, and read back as the text
cleaned.csv would hold - with the functions metrics.json's blocks come from
(`shared/line_report.py`), so Review and stage 2 cannot tell two stories
about one file. Nothing is written.
"""

from typing import NamedTuple

import numpy as np
import pandas as pd
from pydantic import ValidationError

from contracts.cleaning import CleaningPlanContract
from contracts.lines import DuplicatesRemoved, LineSummary, ReservedRename, refused_as_too_large
from shared import line_report
from shared.transactions import parse_transactions
from stages.ingest.cleaned_text import as_read
from stages.ingest.cleaning import clean_frame, planned_renames
from stages.ingest.date_order import DateQuestionUnanswered
from stages.ingest.number_apply import NumberQuestionUnanswered
from stages.ingest.line_taxonomy import HOLDS, is_classed
from stages.ingest.plan_validation import validate_final_plan

_WHAT = "to see the whole file's revenue by kind of line."
NOT_CLASSED = f"Map a quantity and a unit price, and keep both columns, {_WHAT}"
NO_DATE = f"Map a date, and keep its column, {_WHAT}"
DATE_QUESTION = f"Answer how the dates are written {_WHAT}"
NUMBER_QUESTION = f"Answer how the numbers are written {_WHAT}"
TOO_LARGE = "The file's amounts are too large to add up, so its revenue by kind of line cannot be shown."


class ReviewLines(NamedTuple):
    reserved_renames: list[ReservedRename]
    summary: LineSummary | None
    unavailable: str | None  # why `summary` is None


def line_summary(frame: pd.DataFrame, plan: CleaningPlanContract) -> ReviewLines:
    """`frame` is the whole file as `read_csv_text` returns it. Raises
    InvalidPlanError or CleaningError as the preview does: a plan that does
    not work is edited, not failed - checked first, whatever it maps (review
    1 #4)."""
    validate_final_plan(plan, [str(name) for name in frame.columns], for_execution=False)
    # Said whatever the figures can show: the run renames them all the same.
    renames = [ReservedRename(source=old, written_as=new, holds=HOLDS[old])
               for old, new in planned_renames(frame, plan).items()]
    # Execute classes only a plan that maps and keeps a quantity and a price
    # (2E-t1 review cycle 1 #3).
    if not is_classed(plan):
        return ReviewLines(renames, None, NOT_CLASSED)
    # Said before the whole plan runs: the date is read, never cleaned in.
    if not any(a.canonical_field == "transaction_date" and a.action != "drop_column" for a in plan.column_actions):
        return ReviewLines(renames, None, NO_DATE)
    try:
        cleaned = clean_frame(frame, plan, for_execution=False)
    except DateQuestionUnanswered:
        # Review asks it, and Confirm waits for it (review 1 #2).
        return ReviewLines(renames, None, DATE_QUESTION)
    except NumberQuestionUnanswered:
        # The same for the number question (2E-u1).
        return ReviewLines(renames, None, NUMBER_QUESTION)
    text = as_read(cleaned.frame, cleaned.mapping)
    parsed = parse_transactions(text, cleaned.mapping, cleaned.applied)
    whole: line_report.Scopes = {"file": pd.Series(True, index=text.index)}
    try:
        with np.errstate(over="ignore", invalid="ignore"):
            summary = LineSummary(
                lines=len(text),
                undated_lines=line_report.undated_lines(parsed),
                identity=line_report.identity_terms(parsed, whole["file"]),
                outside_revenue=line_report.outside_revenue(parsed, whole),
                unclassified=line_report.unclassified(parsed),
                unmeasurable=line_report.unmeasurable(parsed, whole),
                notes=line_report.notes(text, parsed, whole),
                duplicates_removed=_duplicates_removed(frame, plan, cleaned.frame),
            )
    except ValidationError as error:
        # A whole-file figure that overflows, and only that: a sum of undated
        # or opposite lines that adds up is shown (review 2 #4). metrics.json
        # adds up the compared months apart too (review 3 #1).
        if not refused_as_too_large(error):
            raise
        return ReviewLines(renames, None, TOO_LARGE)
    return ReviewLines(renames, summary, None)


def _duplicates_removed(frame: pd.DataFrame, plan: CleaningPlanContract, kept: pd.DataFrame
                        ) -> DuplicatesRemoved | None:
    """The rows the plan's exact-duplicate removal drops and their revenue
    (2E-u4): the plan run once more without that step - every other step
    drops the same rows both times, so the rows only that run keeps are the
    ones the removal takes. Only when the user added it: a second pass over
    the whole file."""
    if not any(a.action == "remove_exact_duplicates" for a in plan.dataset_actions):
        return None
    without = plan.model_copy(update={"dataset_actions": [
        a for a in plan.dataset_actions if a.action != "remove_exact_duplicates"]})
    every = clean_frame(frame, without, for_execution=False)
    text = as_read(every.frame, every.mapping)
    parsed = parse_transactions(text, every.mapping, every.applied)
    taken = pd.Series(~text.index.isin(kept.index), index=text.index)
    return DuplicatesRemoved(lines=int(taken.sum()),
                             revenue=float(parsed.revenue_amounts[taken & parsed.counted].sum()) + 0.0)
