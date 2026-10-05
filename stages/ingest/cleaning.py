"""Stage 1, the cleaning engine: apply a plan to a frame, and execute it on the
whole file (docs/SPECS.md section 5, docs/CONTRACTS.md section 5).

`apply_plan` is the one place a plan runs, so the preview (`preview.py`, on a
bounded sample) and the execution (`execute_run`, on the whole file) cannot
disagree about what a plan means: same fixed order (`transform_catalog.
EXECUTION_ORDER`), same transforms, same change log.

`execute_run` re-validates the plan against the file before anything runs
(`plan_validation.py`): what the user submits is never assumed to be what the AI
proposed, or still valid. It runs exactly that plan and builds the report from
what actually ran; the AI is not consulted again (CLAUDE.md 3.3).
"""

from datetime import UTC, datetime
from pathlib import Path
from typing import Any, NamedTuple

import pandas as pd

from contracts.cleaning import (
    TAXONOMY_COLUMNS,
    AppliedNumberFormat,
    ChangeLogEntry,
    CleaningPlanContract,
    CleaningReportContract,
    CleaningWarning,
    OrderConfirmations,
    TransformAction,
)
from shared.run_registry import run_file
from stages.ingest import transforms
from stages.ingest.changes import FLAG_PREFIX
from stages.ingest.cleaned_text import as_read, cleaned_csv_text
from stages.ingest.contract_files import write_files_atomically
from stages.ingest.currency import currency_finding
from stages.ingest.currency_apply import apply_currency
from stages.ingest.customer_placeholders import unanswered_placeholders
from stages.ingest.date_order import execution_order
from stages.ingest.number_apply import apply_number_formats
from shared.line_taxonomy import classify_lines
from stages.ingest.line_taxonomy import (
    is_classed,
    rename_warnings,
    renamed_plan,
    reserved_renames,
)
from stages.ingest.plan_validation import validate_final_plan
from stages.ingest.profiling import NA_TOKENS, RAW_FILENAME, read_csv_text
from stages.ingest.transform_catalog import execution_rank

CLEANED_FILENAME = "cleaned.csv"  # CONTRACTS.md section 1
PLAN_FINAL_FILENAME = "plan_final.json"
REPORT_FILENAME = "cleaning_report.json"
SCHEMA_VERSION = "4.3"  # 2E-e: order_id in the canonical enum; 2E-e2: confirmations; 2E-k: placeholders; 2E-d2: line classes; 2E-l: "pooled" (enum, major); 2E-j: the date order; 2E-t1: "gift_card" (enum, major) and the line taxonomy; 2E-u1: the number formats (optional); 2E-u3: the unconfirmed placeholders (optional); 4.3 (the report redesign, step 2): the currency (optional)

Step = tuple[TransformAction, str | None, dict[str, Any]]


class CleaningError(Exception):
    """The plan was valid but an action failed on this data (or the plan leaves
    nothing to write). Nothing was written. `action` and `column` say where; the
    caller (1G) reports the run as failed with this message."""

    def __init__(
        self, message: str, action: TransformAction | None = None, column: str | None = None
    ) -> None:
        super().__init__(message)
        self.action = action
        self.column = column


def plan_steps(plan: CleaningPlanContract) -> list[Step]:
    """Every action of the plan in the order it runs. The order is fixed by the
    catalog, not chosen by the plan (it changes results, AI_PIPELINE section 6);
    inside a group the plan's own order is kept, dataset actions first."""
    steps: list[Step] = [(a.action, None, a.params) for a in plan.dataset_actions]
    steps += [(a.action, a.source_name, a.params) for a in plan.column_actions]
    return sorted(steps, key=lambda step: execution_rank(step[0]))  # sorted() is stable


def apply_plan(
    frame: pd.DataFrame, plan: CleaningPlanContract
) -> tuple[pd.DataFrame, list[ChangeLogEntry]]:
    """The frame after every action of the plan, and one log entry per action in
    the order they ran. `frame` is not modified; the row index is kept, so a row
    that was dropped stays visible as a gap. The plan is assumed valid
    (`validate_final_plan`): a failure here is the data's, not the plan's."""
    current = frame
    changes: list[ChangeLogEntry] = []
    for action, column, params in plan_steps(plan):
        try:
            current, entry = transforms.apply_action(action, current, column, params)
        except (MemoryError, OSError):
            # Not this data's fault: another attempt, with more memory or a working
            # disk, can succeed. Wrapped as a CleaningError it would end the run.
            raise
        except Exception as error:
            # Any exception, not only ValueError: pandas can raise others on
            # data no plan check could see, and the caller needs to know which
            # action it was. The cause stays attached.
            where = f" on column {column!r}" if column is not None else ""
            raise CleaningError(f"{action}{where} failed: {error}", action, column) from error
        changes.append(entry)
    return _without_empty_flags(current, frame), changes


def _without_empty_flags(current: pd.DataFrame, original: pd.DataFrame) -> pd.DataFrame:
    """A flag column the run added is only worth keeping while some row is flagged
    (transforms.py adds one only then), but a later action can drop every flagged
    row. The log still says what happened at that step. A source column that
    happens to look like a flag is the user's data and stays."""
    empty = [
        name for name in current.columns
        if name not in original.columns and str(name).startswith(FLAG_PREFIX)
        and not bool(current[name].any())
    ]
    return current.drop(columns=empty) if empty else current


def _with_line_classes(cleaned: pd.DataFrame, mapping: dict[str, str],
                       applied: OrderConfirmations) -> pd.DataFrame:
    """cleaned.csv with each line's `line_class`, `class_source` and
    `suggested_class` (2E-t1). The classes are read from the file as stages 2
    and 3 will read it - the text cleaned.csv holds - so the two cannot
    differ."""
    classes = classify_lines(as_read(cleaned, mapping), mapping, applied)
    cleaned = cleaned.copy(deep=False)
    for name in TAXONOMY_COLUMNS:
        cleaned[name] = classes[name].to_numpy()
    return cleaned


def _warnings(encoding: str, cleaned: pd.DataFrame) -> list[CleaningWarning]:
    found: list[CleaningWarning] = []
    if encoding == "latin-1":
        # Read from the decode just done, which is where profile.json's
        # `encoding_used` comes from too.
        found.append(CleaningWarning(code="encoding_fallback", detail="file decoded as latin-1"))
    reads_as_missing = _text_that_reads_back_as_missing(cleaned)
    if reads_as_missing:
        names = list(reads_as_missing)
        shown = ", ".join(names[:5]) + (f" and {len(names) - 5} more" if len(names) > 5 else "")
        found.append(CleaningWarning(
            code="text_reads_as_missing",
            detail=(f"{sum(reads_as_missing.values())} cells hold text that reads back as missing "
                    f"(an empty text, NA, N/A, NULL...) in {shown}")))
    return found


def _text_that_reads_back_as_missing(frame: pd.DataFrame) -> dict[str, int]:
    """Cells whose text is a missing-value token (profiling.NA_TOKENS): in the run
    they are text, but read cleaned.csv again and they are gaps. A trimmed " N/A "
    and a trimmed "   " (now empty) are the ways a run makes one; nothing can stop
    it at plan time, so the report says how many there are."""
    found: dict[str, int] = {}
    for name in frame.columns:
        column = frame[name]
        if column.dtype == object or pd.api.types.is_string_dtype(column):
            count = int(column.isin(NA_TOKENS).sum())
            if count:
                found[str(name)] = count
    return found


class Cleaned(NamedTuple):
    """What a plan makes of the whole file, before anything is written:
    execute's cleaned frame (the classes not yet added) and what its report
    records. Review's whole-file summary reads the same (2E-t3)."""

    frame: pd.DataFrame
    changes: list[ChangeLogEntry]
    renames: dict[str, str]  # a source column named like a class column -> its name in cleaned.csv
    mapping: dict[str, str]  # the columns later stages look up -> their canonical field
    applied: OrderConfirmations  # the answers, with the date order applied
    date_order: str | None
    number_formats: dict[str, AppliedNumberFormat]  # per quantity and price column (2E-u1)
    read: pd.DataFrame  # the raw file with its numbers read, before the plan ran (2E-u3)


def planned_renames(frame: pd.DataFrame, plan: CleaningPlanContract) -> dict[str, str]:
    """A source column named like one of the three columns stage 1 adds is
    kept under another name - before the plan runs, so its flags, the change
    log and the mapping carry that name by themselves (Thach's Q24; 2E-t1
    review cycle 2 #2-#4). `plan_final.json` keeps the plan as submitted."""
    if not is_classed(plan):
        return {}
    dropped_raw = {a.source_name for a in plan.column_actions if a.action == "drop_column"}
    return reserved_renames([str(name) for name in frame.columns], dropped_raw)


def clean_frame(frame: pd.DataFrame, plan: CleaningPlanContract, *, for_execution: bool) -> Cleaned:
    """The plan checked against the file and run on it, as `execute_run`
    runs it. `for_execution` switches on the required-field rules and nothing
    else. Raises InvalidPlanError, or CleaningError (an action failed, or no
    row is left)."""
    validate_final_plan(plan, [str(name) for name in frame.columns], for_execution=for_execution)
    # On the raw file, before anything runs: a plan dropping the rows that
    # prove the order must not lose the proof (2E-j).
    date_order = execution_order(plan, frame)
    # So are numbers written for people (2E-u1): the cells' proof, else the
    # answer, on the raw file; the plan's own steps (a cast, a clip) then
    # read plain numbers. Unanswered and unproven: refused, never a default.
    dropped_raw = {a.source_name for a in plan.column_actions if a.action == "drop_column"}
    frame, number_formats = apply_number_formats(
        frame, {a.source_name: a.canonical_field for a in plan.column_actions if a.source_name not in dropped_raw},
        plan.confirmations.number_formats)
    renames = planned_renames(frame, plan)
    run_plan = renamed_plan(plan, renames)

    try:
        cleaned, changes = apply_plan(frame.rename(columns=renames), run_plan)
    except CleaningError as error:
        # The failure names the column as the user wrote it (review cycle 3 #7).
        written = {new: old for old, new in renames.items()}.get(error.column or "")
        if written is None:
            raise
        raise CleaningError(str(error).replace(repr(error.column), repr(written)), error.action,
                            written) from error
    if cleaned.empty:
        raise CleaningError(
            "The plan removes every row, so there is nothing left to write. "
            "Check the drop_rows_missing and duplicate actions.")

    dropped = {a.source_name for a in run_plan.column_actions if a.action == "drop_column"}
    # The columns later stages look up: not an ignored one, and not one that
    # is no longer in cleaned.csv.
    mapping = {a.source_name: a.canonical_field for a in run_plan.column_actions
               if a.canonical_field != "ignore" and a.source_name not in dropped}
    # Each line's class is decided in the date order that was applied.
    applied = plan.confirmations.model_copy(
        update={"dates_day_first": None if date_order is None else date_order == "day_first"})
    return Cleaned(cleaned, changes, renames, mapping, applied, date_order, number_formats, frame)


def execute_run(
    runs_root: Path,
    run_id: str,
    plan: CleaningPlanContract,
    now: datetime | None = None,
    *,
    require_required_fields: bool = True,
) -> CleaningReportContract:
    """runs/<run_id>/raw.csv + the submitted plan -> cleaned.csv, plan_final.json
    and cleaning_report.json.

    `require_required_fields=False` is for a file that is not inventory data (SPECS
    section 10, NOT_INVENTORY): generic cleaning has nothing to map to the canonical
    fields, so the rule that they are mapped and kept is waived. Every other check of
    the plan still applies.

    Raises InvalidPlanError (the plan is checked against the file first),
    CleaningError (an action failed, or no row is left), FileNotFoundError, or what
    reading the file raises (profiling's EmptyCsvError and CsvParseError, and the
    run registry's InvalidRunIdError and RunNotFoundError).
    Nothing is written unless every step succeeded: the three files are written
    together, the report last, so a report on disk means the run finished
    (`write_files_atomically`), and a failure while writing puts every file back.
    A failed run leaves any earlier result as it was.

    Not safe to call twice at once for the same run: nothing here locks it, so two
    concurrent executions can interleave their renames. The caller claims the run
    first (the run's status moves to "cleaning" in one atomic step, SPECS section 3,
    and a second call gets INVALID_STATE, 409).
    """
    raw_path = run_file(runs_root, run_id, RAW_FILENAME)
    if not raw_path.exists():
        raise FileNotFoundError(f"{RAW_FILENAME} is missing for run {run_id}")
    parsed = read_csv_text(raw_path.read_bytes())
    frame = parsed.frame
    cleaned, changes, renames, mapping, applied, date_order, number_formats, read = clean_frame(
        frame, plan, for_execution=require_required_fields)
    # The plan checked, before anything is written: the currency, read on the
    # RAW cells of the plan's money column and of a currency column (Thach,
    # Q26). More than one refuses the plan, whatever the answer (Q7 = A);
    # else the answer, the file's, or not stated. Generic cleaning sums
    # nothing, so it neither blocks nor records one.
    money = [action.source_name for action in plan.column_actions if action.canonical_field == "unit_price"]
    currency = (apply_currency(currency_finding(frame, money), plan.confirmations.currency)
                if require_required_fields else None)
    # Each line's class, decided once, here (2E-t1; docs/LINE_TAXONOMY.md
    # section 4).
    if is_classed(plan):
        cleaned = _with_line_classes(cleaned, mapping, applied)
    report = CleaningReportContract(
        schema_version=SCHEMA_VERSION,
        generated_at=now or datetime.now(UTC),
        rows_in=len(frame),
        rows_out=len(cleaned),
        columns_in=frame.shape[1],
        columns_out=cleaned.shape[1],  # includes the flag columns the run added
        changes=changes,
        warnings=_warnings(parsed.encoding, cleaned) + rename_warnings(renames),
        column_mapping=mapping,
        # The user's answers from Review, exactly as submitted: stages 2 and 3
        # read them here (2E-e2), and unanswered stays unconfirmed.
        confirmations=plan.confirmations,
        # The order the date column's day-month-year cells were read in: the
        # answer, else the raw file's proof (2E-j).
        date_order=date_order,
        # What stage 1's number reading did per quantity and price column
        # (2E-u1): what actually ran.
        number_formats=number_formats,
        # Review's walk-in candidates left unanswered (2E-u3): still customers,
        # marked "suggested, not confirmed" by stages 2 and 5.
        # Measured on the raw file as its numbers were read: "$5.00" was no
        # amount before, so no line was measured (2E-u3 review 1, #1).
        unconfirmed_placeholders=unanswered_placeholders(read, plan),
        currency=currency,
    )
    write_files_atomically([
        (run_file(runs_root, run_id, CLEANED_FILENAME), cleaned_csv_text(cleaned).encode("utf-8")),
        (run_file(runs_root, run_id, PLAN_FINAL_FILENAME),
         plan.model_dump_json(indent=2).encode("utf-8")),
        (run_file(runs_root, run_id, REPORT_FILENAME),
         report.model_dump_json(indent=2).encode("utf-8")),
    ])
    return report
