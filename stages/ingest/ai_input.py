"""The bounded input stage 1 sends to the AI (docs/AI_PIPELINE.md section 1).

Counts and sizes are both bounded: at most 25 columns, 30 stratified sample
rows, and 100 characters per value. Column names are never cut, because the
answer has to name them exactly.
"""

import json
from collections.abc import Collection
from typing import Any

import pandas as pd

from contracts.profile import ProfileContract, SchemaInferenceContract
from stages.ingest import problem_rows
from stages.ingest.issue_counts import business_key_columns
from stages.ingest.transform_catalog import legal_column_actions, legal_dataset_actions

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
    rows for each kind of dirt in `problem_rows.problem_masks` (a missing cell, an exact
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
        for mask in problem_rows.problem_masks(frame, numeric_columns):
            chosen.update(problem_rows.first_positions(mask, PER_PROBLEM_KIND))
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


def build_profile_json(profile: ProfileContract) -> str:
    """The profile cut to its first 25 columns (top values are already capped
    at 10), every value cut to 100 characters, so the size is bounded as well
    as the count. Column names are never cut: the answer must repeat them
    exactly. The contract header fields are left out as noise. Both AI steps
    send this, so they describe the file the same way."""
    sent = profile.columns[:MAX_AI_COLUMNS]
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
    return json.dumps({"dataset": dataset, "columns": columns}, ensure_ascii=False)


def build_prompt_variables(profile: ProfileContract, frame: pd.DataFrame) -> dict[str, str]:
    """Schema inference's input (AI_PIPELINE section 1): the bounded profile and
    at most 30 stratified rows of the same 25 columns, values cut to 100
    characters."""
    sent = profile.columns[:MAX_AI_COLUMNS]
    names = [c.name for c in sent]
    numeric = {c.name for c in sent if c.dtype in _NUMERIC_DTYPES}
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
        "profile_json": build_profile_json(profile),
        "sample_rows": json.dumps(sample, ensure_ascii=False),
    }


def build_plan_variables(
    profile: ProfileContract, schema: SchemaInferenceContract
) -> dict[str, str]:
    """The cleaning-plan step's input (AI_PIPELINE section 2): the profile and
    the schema inference result, for the same 25 columns.

    The schema result is trimmed to what a plan needs. Its `examples` (row
    references), `domain_reasoning` and header fields are left out: the plan
    step cannot use them, and AI text that may echo a cell of the uploaded file
    is not carried into a second call more than necessary. What stays of it,
    the issue `detail`, is cut like every other value.

    Two things are added that the AI could otherwise only guess: the actions
    the catalog allows for each column (so the whitelist is given, not
    inferred) and the business key `flag_duplicate_keys` has to use.
    """
    sent = schema.columns[:MAX_AI_COLUMNS]
    payload = {
        "dataset_issues": [
            {"code": i.code, "count": i.count, "severity": i.severity, "detail": _cut(i.detail)}
            for i in schema.dataset_issues
        ],
        "dataset_legal_actions": legal_dataset_actions(),
        "business_key": business_key_columns(sent),
        "columns": [
            {
                "source_name": c.source_name,
                "semantic_type": c.semantic_type,
                "canonical_field": c.canonical_field,
                "confidence": c.confidence,
                "issues": [{"code": i.code, "count": i.count, "pct": i.pct} for i in c.issues],
                "legal_actions": legal_column_actions(c.semantic_type, c.canonical_field),
            }
            for c in sent
        ],
    }
    return {
        "profile_json": build_profile_json(profile),
        "schema_inference_json": json.dumps(payload, ensure_ascii=False),
    }


def _cut(value: str) -> str:
    # The mark counts toward the limit, so nothing sent is longer than it.
    if len(value) <= MAX_VALUE_CHARS:
        return value
    return value[: MAX_VALUE_CHARS - len(TRUNCATION_MARK)] + TRUNCATION_MARK
