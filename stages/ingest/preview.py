"""The before/after preview of a plan (docs/SPECS.md section 4.2 C and section 8).

The same engine as execution (`cleaning.apply_plan`), run on a bounded sample
so it stays inside the 3 s budget on a 50 MB file (SPECS section 11):

* a file of up to 500 rows is previewed whole, and then the result is exactly
  what `execute_run` writes;
* a larger file gets a deterministic 500-row sample: its problem rows (found in
  the first 50,000 rows, which is what keeps the cost small) plus rows spread
  evenly over the whole file, first and last included.

Anything computed from the data (a median, exact-duplicate detection) is the
sample's, so on a large file the numbers are indicative; execution is what counts.

Of the sample, 20 rows are shown, chosen so every kind of effect appears (each
changed column, a dropped row) before any repeats, then the other affected rows,
then unaffected rows spread over the sample. Never `head()`.
"""

from pathlib import Path

import pandas as pd
from pydantic import BaseModel

from contracts.cleaning import CleaningPlanContract
from shared.run_registry import run_file
from stages.ingest import problem_rows
from stages.ingest.ai_input import TRUNCATION_MARK
from stages.ingest.cleaning import apply_plan, iso_dates
from stages.ingest.plan_validation import validate_final_plan
from stages.ingest.profiling import RAW_FILENAME, read_csv_text

PREVIEW_SAMPLE_MAX = 500  # SPECS section 8
PREVIEW_ROWS = 20  # SPECS section 4.2 C
PROBLEM_WINDOW = 50_000  # rows searched for problem rows; 0.14 s where all rows cost 1.4 s
# The search costs by the cell, so a wide file gets a shorter window: 400 columns
# of 50,000 rows took 11 s. About 0.6 s at this budget.
PROBLEM_CELL_BUDGET = 2_000_000
PROBLEM_ROWS_PER_KIND = 40
MAX_CELL_CHARS = 200  # a shown cell is cut here; a change beyond the cut is still seen
_DROPPED = "\0dropped"  # a tag no column name can equal


class PreviewRow(BaseModel):
    row: int  # 1 is the first data row of the file
    before: dict[str, str | None]
    after: dict[str, str | None] | None  # None: the plan drops this row
    changed: list[str]  # columns whose cell differs, or whose flag is set


class ColumnDelta(BaseModel):
    """None where there is nothing to measure: a flag column the run adds has no
    before, a dropped column no after (and no rows left, no percentage)."""

    column: str
    null_pct_before: float | None
    null_pct_after: float | None
    unique_before: int | None
    unique_after: int | None


class PreviewResult(BaseModel):
    rows_in_file: int
    sample_rows: int
    sampled: bool  # False: the whole file was previewed
    rows_after: int  # rows of the sample the plan leaves
    columns_after: list[str]
    rows: list[PreviewRow]
    deltas: list[ColumnDelta]


def select_sample(frame: pd.DataFrame, limit: int = PREVIEW_SAMPLE_MAX) -> pd.DataFrame:
    """The whole frame when it fits, otherwise at most `limit` rows in file order
    (the index labels are kept, so a row is still found by its number)."""
    count = len(frame)
    if count <= limit:
        return frame
    if limit <= 1:
        return frame.iloc[: max(limit, 0)]
    grid = [i * (count - 1) // (limit - 1) for i in range(limit)]  # first and last included
    if limit < 4:  # too small to share between problem rows and the spread
        return frame.iloc[grid]
    problems: set[int] = set()
    window = frame.head(search_window(frame.shape[1], limit))
    for mask in problem_rows.problem_masks(window, ()):
        problems.update(problem_rows.first_positions(mask, PROBLEM_ROWS_PER_KIND))
    problems = set(sorted(problems)[: limit // 2])  # half the budget at most
    room = limit - len(problems)
    chosen = problems | {grid[j * (limit - 1) // (room - 1)] for j in range(room)}
    for position in grid:  # a problem row that sat on a grid point left a slot free
        if len(chosen) >= limit:
            break
        chosen.add(position)
    return frame.iloc[sorted(chosen)]


def search_window(columns: int, limit: int) -> int:
    """How many rows to search for problem rows: `PROBLEM_WINDOW`, fewer when the
    file is wide (the cost is per cell), and never fewer than the sample itself."""
    return max(min(PROBLEM_WINDOW, PROBLEM_CELL_BUDGET // max(columns, 1)), limit)


def preview_frame(
    frame: pd.DataFrame,
    plan: CleaningPlanContract,
    *,
    rows: int = PREVIEW_ROWS,
    sample_max: int = PREVIEW_SAMPLE_MAX,
) -> PreviewResult:
    """The preview of `plan` on `frame`, which is assumed to be the whole file
    as `read_csv_text` returns it and the plan valid (`validate_final_plan`)."""
    sample = select_sample(frame, sample_max)
    after, _ = apply_plan(sample, plan)
    before_view, after_view = _display(sample), _display(after)
    tags = _tags(before_view, after_view)
    shown = _choose_rows(list(sample.index), tags, rows)
    return PreviewResult(
        rows_in_file=len(frame),
        sample_rows=len(sample),
        sampled=len(sample) < len(frame),
        rows_after=len(after),
        columns_after=[str(name) for name in after.columns],
        rows=[_row(label, before_view, after_view, tags[label]) for label in shown],
        deltas=_deltas(before_view, after_view),
    )


def preview_run(runs_root: Path, run_id: str, plan: CleaningPlanContract) -> PreviewResult:
    """runs/<run_id>/raw.csv + a plan -> the preview. Nothing is written. The plan
    is checked like execute checks it, except that the required fields need not
    be mapped yet: the preview refreshes while the user is still mapping."""
    raw_path = run_file(runs_root, run_id, RAW_FILENAME)
    if not raw_path.exists():
        raise FileNotFoundError(f"{RAW_FILENAME} is missing for run {run_id}")
    frame = read_csv_text(raw_path.read_bytes()).frame
    validate_final_plan(plan, [str(name) for name in frame.columns], for_execution=False)
    return preview_frame(frame, plan)


# --- what is shown ---------------------------------------------------------------------


def _display(frame: pd.DataFrame) -> pd.DataFrame:
    """Every cell as the text `cleaned.csv` would hold, or None when missing."""
    out = frame.copy(deep=False)
    for name in out.columns:
        values = out[name]
        if pd.api.types.is_datetime64_any_dtype(values):
            values = iso_dates(values)
        out[name] = pd.Series(
            [None if pd.isna(v) else str(v) for v in values], index=values.index, dtype=object)
    return out


def _tags(before: pd.DataFrame, after: pd.DataFrame) -> dict[int, list[str]]:
    """For every sample row, what the plan did to it: the columns whose cell
    differs, a set flag, or `_DROPPED` (the tag `changed` never shows). Compared a
    column at a time, not a cell at a time: 500 rows of 400 columns is 200,000
    cells."""
    kept = before.index.intersection(after.index)
    tags: dict[int, list[str]] = {label: [_DROPPED] for label in before.index.difference(after.index)}
    shared = [name for name in after.columns if name in before.columns]
    added = [name for name in after.columns if name not in before.columns]
    was, now = before.loc[kept, shared], after.loc[kept, shared]
    differs = (was.ne(now) & ~(was.isna() & now.isna())).to_numpy()  # None equals None
    flags = after.loc[kept, added]
    set_flags = (flags.notna() & flags.ne("False")).to_numpy()  # a flag column the run added, and set
    names = [str(name) for name in shared] + [str(name) for name in added]
    for i, label in enumerate(kept):
        row = list(differs[i]) + list(set_flags[i])
        tags[label] = [name for name, hit in zip(names, row, strict=True) if hit]
    return tags


def _choose_rows(index: list[int], tags: dict[int, list[str]], limit: int) -> list[int]:
    affected = [label for label in index if tags[label]]
    picked: list[int] = []
    covered: set[str] = set()
    for label in affected:  # a row that shows an effect not yet on screen
        if len(picked) >= limit:
            break
        if set(tags[label]) - covered:
            picked.append(label)
            covered.update(tags[label])
    for label in affected:  # then the other affected rows, in file order
        if len(picked) >= limit:
            break
        if label not in picked:
            picked.append(label)
    quiet = [label for label in index if not tags[label]]
    room = limit - len(picked)
    if room > 0 and quiet:
        if room >= len(quiet):
            picked += quiet
        elif room == 1:
            picked.append(quiet[0])
        else:  # spread over the sample, first and last included
            picked += [quiet[i * (len(quiet) - 1) // (room - 1)] for i in range(room)]
    return sorted(picked)


def _row(label: int, before: pd.DataFrame, after: pd.DataFrame, tag: list[str]) -> PreviewRow:
    dropped = label not in after.index
    return PreviewRow(
        row=int(label) + 1,
        before={str(k): _cut(v) for k, v in before.loc[label].items()},
        after=None if dropped else {str(k): _cut(v) for k, v in after.loc[label].items()},
        changed=[] if dropped else tag,
    )


def _cut(value: str | None) -> str | None:
    if value is None or len(value) <= MAX_CELL_CHARS:
        return value
    return value[: MAX_CELL_CHARS - len(TRUNCATION_MARK)] + TRUNCATION_MARK


def _deltas(before: pd.DataFrame, after: pd.DataFrame) -> list[ColumnDelta]:
    names = list(before.columns) + [n for n in after.columns if n not in before.columns]
    return [
        ColumnDelta(
            column=str(name),
            null_pct_before=_null_pct(before[name]) if name in before.columns else None,
            null_pct_after=_null_pct(after[name]) if name in after.columns else None,
            unique_before=int(before[name].nunique()) if name in before.columns else None,
            unique_after=int(after[name].nunique()) if name in after.columns else None,
        )
        for name in names
    ]


def _null_pct(values: pd.Series) -> float | None:
    """The share of missing cells, in percent; None for a column with no rows."""
    return int(values.isna().sum()) * 100 / len(values) if len(values) else None
