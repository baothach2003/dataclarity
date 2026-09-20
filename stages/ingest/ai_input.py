"""The bounded input stage 1 sends to the AI (docs/AI_PIPELINE.md section 1).

Counts and sizes are both bounded: at most 25 columns, 30 stratified sample
rows, and 100 characters per value. Column names are never cut, because the
answer has to name them exactly.
"""

import json
from collections.abc import Collection
from typing import Any

import pandas as pd

from contracts.profile import ProfileContract
from stages.ingest import column_kinds

# AI_PIPELINE section 1 allows up to 60; 25 because an answer for more columns
# does not fit in the 3000 output tokens (1C doubt review, decided by Thach).
MAX_AI_COLUMNS = 25
MAX_SAMPLE_ROWS = 30  # AI_PIPELINE section 1
# Bounds the size, not just the count, of what is sent (1C, decided by Thach).
MAX_VALUE_CHARS = 100
TRUNCATION_MARK = "…[truncated]"
# Six problem kinds share the 30 rows, so each takes at most three: a sample
# made only of dirt hides what an ordinary row of this file looks like, and
# the semantic types are inferred from ordinary rows.
PER_PROBLEM_KIND = 3
_NUMERIC_DTYPES = {"int64", "float64"}


def select_sample_rows(
    frame: pd.DataFrame, numeric_columns: Collection[str], limit: int = MAX_SAMPLE_ROWS
) -> list[dict[str, Any]]:
    """Up to `limit` rows, "stratified to include problematic rows" (the prompt).

    Deterministic, so tests can check it by hand: up to `PER_PROBLEM_KIND`
    rows for each kind of dirt in `_problem_masks` (a missing cell, an exact
    duplicate, a negative number, text in a column of numbers, padded
    whitespace, an unparseable date), then evenly spaced rows up to the limit
    (fewer when an evenly spaced row was already picked as a problem row).
    Returned in file order; `row` is 1 for the first data row, so the AI can
    cite rows as examples.
    """
    count = len(frame)
    if limit <= 0 or count == 0:
        chosen: set[int] = set()
    elif limit == 1:
        chosen = {0}
    elif count <= limit:
        chosen = set(range(count))
    else:
        chosen = set()
        for mask in _problem_masks(frame, numeric_columns):
            chosen.update(_first_positions(mask, PER_PROBLEM_KIND))
        # Three kinds of problem rows can already exceed the limit on their own.
        chosen = set(sorted(chosen)[:limit])
        for position in (i * (count - 1) // (limit - 1) for i in range(limit)):
            if len(chosen) >= limit:
                break
            chosen.add(position)
    return [
        {
            "row": position + 1,
            "values": {
                str(name): None if pd.isna(value) else _cut(str(value))
                for name, value in frame.iloc[position].items()
            },
        }
        for position in sorted(chosen)
    ]


def _problem_masks(frame: pd.DataFrame, numeric_columns: Collection[str]) -> list[pd.Series]:
    """One mask per kind of dirt worth showing the AI. The kinds match the
    issue codes it is asked to report (`issue_counts.py`), so the sample holds
    an example of what the schema answer has to describe.

    A column is scanned for numbers or for dates only when its head looks that
    way: converting all 25 columns both ways would cost more than the whole
    profiling step.
    """
    nothing = pd.Series(False, index=frame.index)
    negative, non_numeric, whitespace, bad_date = (nothing.copy() for _ in range(4))
    for name in frame.columns:
        values = frame[name]
        whitespace |= column_kinds.whitespace_mask(values)
        if name in numeric_columns or column_kinds.probably_numeric(values):
            negative |= column_kinds.as_numbers(values) < 0
            # Text in a column of numbers: the "n/a" the AI must not average.
            non_numeric |= column_kinds.non_numeric_mask(values)
        elif column_kinds.probably_dates(values):
            bad_date |= column_kinds.invalid_date_mask(values)
    return [
        frame.isna().any(axis=1),
        frame.duplicated(keep=False),
        negative,
        non_numeric,
        whitespace,
        bad_date,
    ]


def _first_positions(mask: pd.Series, limit: int) -> list[int]:
    return [int(p) for p in mask.to_numpy().nonzero()[0][:limit]]


def build_prompt_variables(profile: ProfileContract, frame: pd.DataFrame) -> dict[str, str]:
    """The bounded input (AI_PIPELINE section 1): the profile cut to its first
    25 columns (top values are already capped at 10), at most 30 rows of those
    columns, and every value cut to 100 characters, so the size is bounded as
    well as the count. Column names are never cut: the answer must repeat them
    exactly. The contract header fields are left out as noise."""
    sent = profile.columns[:MAX_AI_COLUMNS]
    names = [c.name for c in sent]
    numeric = {c.name for c in sent if c.dtype in _NUMERIC_DTYPES}
    columns = []
    for column in sent:
        dumped = column.model_dump(mode="json")
        for top in dumped["top_values"]:
            top["value"] = _cut(top["value"])
        dumped["sample_values"] = [
            None if v is None else _cut(v) for v in dumped["sample_values"]
        ]
        columns.append(dumped)
    dataset = profile.dataset.model_dump(mode="json")
    # The dataset figures cover the whole file; say how many columns are listed.
    dataset["columns_described_below"] = len(sent)
    profile_json = {"dataset": dataset, "columns": columns}
    # Header once plus a value list per row: repeating 25 column names in every
    # one of 30 rows would be a third of the prompt.
    sample = {
        "columns": names,
        "rows": [
            {"row": row["row"], "values": [row["values"][name] for name in names]}
            for row in select_sample_rows(frame[names], numeric)
        ],
    }
    return {
        "profile_json": json.dumps(profile_json, ensure_ascii=False),
        "sample_rows": json.dumps(sample, ensure_ascii=False),
    }


def _cut(value: str) -> str:
    # The mark counts toward the limit, so nothing sent is longer than it.
    if len(value) <= MAX_VALUE_CHARS:
        return value
    return value[: MAX_VALUE_CHARS - len(TRUNCATION_MARK)] + TRUNCATION_MARK
