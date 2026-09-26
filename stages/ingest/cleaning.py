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
from typing import Any

import pandas as pd

from contracts.cleaning import (
    ChangeLogEntry,
    CleaningPlanContract,
    CleaningReportContract,
    CleaningWarning,
    TransformAction,
)
from shared.run_registry import run_file
from stages.ingest import transforms
from stages.ingest.changes import FLAG_PREFIX
from stages.ingest.contract_files import write_files_atomically
from stages.ingest.plan_validation import validate_final_plan
from stages.ingest.profiling import NA_TOKENS, RAW_FILENAME, read_csv_text
from stages.ingest.transform_catalog import execution_rank

CLEANED_FILENAME = "cleaned.csv"  # CONTRACTS.md section 1
PLAN_FINAL_FILENAME = "plan_final.json"
REPORT_FILENAME = "cleaning_report.json"
SCHEMA_VERSION = "2.3"  # 2E-e: order_id in the canonical enum; 2E-e2: confirmations; 2E-k: placeholders; 2E-d2: line classes

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


def cleaned_csv_text(frame: pd.DataFrame) -> str:
    """The frame as the text of `cleaned.csv`: UTF-8 friendly, "\\n" line ends,
    the source column names, and dates in ISO 8601 (a date with no time as
    2024-01-05, otherwise 2024-01-05T10:30:00). Written here rather than left to
    pandas so the format is fixed and a test can check it by eye."""
    out = frame.copy(deep=False)  # only whole columns are replaced below
    for name in out.columns:
        if pd.api.types.is_datetime64_any_dtype(out[name]):
            out[name] = iso_dates(out[name])
    return out.to_csv(index=False, lineterminator="\n")


def iso_dates(values: pd.Series) -> pd.Series:
    """A datetime column as ISO 8601 text; the preview shows dates the same way."""
    present = values.dropna()
    if not present.empty and present.dt.microsecond.any():
        pattern = "%Y-%m-%dT%H:%M:%S.%f"
    elif not present.empty and (present.dt.hour | present.dt.minute | present.dt.second).any():
        pattern = "%Y-%m-%dT%H:%M:%S"
    else:
        pattern = "%Y-%m-%d"
    return values.dt.strftime(pattern)  # a missing date stays missing


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
    # `for_execution` switches on the required-field rules and nothing else.
    validate_final_plan(
        plan, [str(name) for name in frame.columns], for_execution=require_required_fields)

    cleaned, changes = apply_plan(frame, plan)
    if cleaned.empty:
        raise CleaningError(
            "The plan removes every row, so there is nothing left to write. "
            "Check the drop_rows_missing and duplicate actions.")

    dropped = {a.source_name for a in plan.column_actions if a.action == "drop_column"}
    report = CleaningReportContract(
        schema_version=SCHEMA_VERSION,
        generated_at=now or datetime.now(UTC),
        rows_in=len(frame),
        rows_out=len(cleaned),
        columns_in=frame.shape[1],
        columns_out=cleaned.shape[1],  # includes the flag columns the run added
        changes=changes,
        warnings=_warnings(parsed.encoding, cleaned),
        # The columns later stages look up: not an ignored one, and not one that
        # is no longer in cleaned.csv.
        column_mapping={
            a.source_name: a.canonical_field
            for a in plan.column_actions
            if a.canonical_field != "ignore" and a.source_name not in dropped
        },
        # The user's answers from Review, exactly as submitted: stages 2 and 3
        # read them here (2E-e2), and unanswered stays unconfirmed.
        confirmations=plan.confirmations,
    )
    write_files_atomically([
        (run_file(runs_root, run_id, CLEANED_FILENAME), cleaned_csv_text(cleaned).encode("utf-8")),
        (run_file(runs_root, run_id, PLAN_FINAL_FILENAME),
         plan.model_dump_json(indent=2).encode("utf-8")),
        (run_file(runs_root, run_id, REPORT_FILENAME),
         report.model_dump_json(indent=2).encode("utf-8")),
    ])
    return report
