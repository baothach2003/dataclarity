"""Real counts, in pandas, for the issue codes the profile holds no figure for
(PROJECT_PLAN 1D, handed over from 1C).

Why this exists: `schema_inference.json` carries a `count` per issue, and the
AI is the one that writes it. 1C can only check the three codes `profile.json`
already measures (`missing_values`, `all_null_column`, `duplicate_rows`); for
every other code the AI's number is an estimate from at most 30 sample rows.
CLAUDE.md 3.2 says no number in the report may come from the AI, so this module
computes the other twelve over the whole file.

How `ai_schema.py` will use it (a later session, 1E): after the answer passes
`check_answer`, walk the accepted issues and replace `count` with
`count_column_issue(...)` / `count_duplicate_business_key(...)` for every code
in `COMPUTED_COLUMN_CODES` / `COMPUTED_DATASET_CODES`, leaving the codes in
`PROFILED_CODES` as 1C already checks them. The AI then contributes the
judgement (which issues matter, how severe) and pandas contributes every
number. `pct` is not touched here: the 1C rule (a percentage only where the
profile holds one, otherwise null) still stands.

`duplicate_business_key` needs the key columns, which only exist once the AI has
named the canonical fields, so it takes them as an argument.

Every count is a number of cells (`duplicate_business_key`: rows), matching the
`count` field's meaning in docs/CONTRACTS.md section 3.
"""

import re

import pandas as pd

from contracts.profile import IssueCode
from stages.ingest import column_kinds

# Already measured by profiling.py and checked in ai_schema.check_answer.
PROFILED_CODES: frozenset[IssueCode] = frozenset(
    {"missing_values", "all_null_column", "duplicate_rows"}
)
COMPUTED_COLUMN_CODES: frozenset[IssueCode] = frozenset(
    {
        "invalid_dates",
        "mixed_date_formats",
        "negative_values",
        "zero_values",
        "inconsistent_case",
        "trailing_whitespace",
        "near_duplicate_labels",
        "outliers_iqr",
        "mixed_types",
        "constant_column",
        "non_numeric_in_numeric",
    }
)
COMPUTED_DATASET_CODES: frozenset[IssueCode] = frozenset({"duplicate_business_key"})

# Everything a label can differ by and still mean the same product: case,
# surrounding and inner spacing, and punctuation ("Coca-Cola", "coca cola").
_PUNCTUATION = re.compile(r"[^\w\s]+")
_SPACES = re.compile(r"\s+")


def count_column_issues(values: pd.Series, dayfirst: bool = False) -> dict[IssueCode, int]:
    """Every computable column code for one column, in one pass over the codes.
    Codes with nothing to report are left out, so the result reads like the
    issue list it feeds."""
    counts = {
        code: count_column_issue(code, values, dayfirst) for code in sorted(COMPUTED_COLUMN_CODES)
    }
    return {code: count for code, count in counts.items() if count > 0}


def count_column_issue(code: IssueCode, values: pd.Series, dayfirst: bool = False) -> int:
    """The number of cells in `values` that `code` describes.

    Raises KeyError for a code this module does not compute, so a caller can
    never quietly turn an AI estimate into a computed-looking zero.
    """
    if code not in COMPUTED_COLUMN_CODES:
        raise KeyError(f"{code} is not computed here; see PROFILED_CODES")
    return _COUNTERS[code](values, dayfirst)


def count_duplicate_business_key(frame: pd.DataFrame, keys: list[str]) -> int:
    """Rows sharing their business key with another row - every one of them,
    not only the later ones, because a collision is about the group.

    The keys are the columns the AI mapped to the canonical fields that
    identify a transaction; with none of them the count is 0, not an error,
    because a file without a key simply has no such issue.
    """
    present = [key for key in keys if key in frame.columns]
    if not present or frame.empty:
        return 0
    return int(frame.duplicated(subset=present, keep=False).sum())


# --- one counter per code ---------------------------------------------------


def _negative_values(values: pd.Series, dayfirst: bool) -> int:
    return int((column_kinds.as_numbers(values) < 0).sum())


def _zero_values(values: pd.Series, dayfirst: bool) -> int:
    return int((column_kinds.as_numbers(values) == 0).sum())


def _trailing_whitespace(values: pd.Series, dayfirst: bool) -> int:
    return int(column_kinds.whitespace_mask(values).sum())


def _outliers_iqr(values: pd.Series, dayfirst: bool) -> int:
    return int(column_kinds.outlier_mask(values).sum())


def _inconsistent_case(values: pd.Series, dayfirst: bool) -> int:
    return int(column_kinds.case_variant_mask(values).sum())


def _invalid_dates(values: pd.Series, dayfirst: bool) -> int:
    """Only a column that is mostly dates has invalid dates; in a product name
    column every cell would qualify, which says nothing."""
    if not column_kinds.is_mostly_dates(values, dayfirst):
        return 0
    return int(column_kinds.invalid_date_mask(values, dayfirst).sum())


def _mixed_date_formats(values: pd.Series, dayfirst: bool) -> int:
    """Date cells not written in the column's most common format. One format
    is not a mixture, so a tidy column counts 0."""
    if not column_kinds.is_mostly_dates(values, dayfirst):
        return 0
    labels = column_kinds.date_format_labels(values).dropna()
    counts = labels.value_counts()
    if len(counts) < 2:
        return 0
    return int(len(labels) - counts.iloc[0])


def _non_numeric_in_numeric(values: pd.Series, dayfirst: bool) -> int:
    """Text in a column that is otherwise numbers - the "n/a" in a quantity
    column. A text column is not a numeric column with a problem."""
    if not column_kinds.is_mostly_numeric(values):
        return 0
    return int(column_kinds.non_numeric_mask(values).sum())


def _mixed_types(values: pd.Series, dayfirst: bool) -> int:
    """Cells of the minority kind when a column holds both numbers and text.
    In a mostly-numeric column this is the same set of cells as
    `non_numeric_in_numeric`; the two codes describe it from either side."""
    numeric = int(column_kinds.numeric_mask(values).sum())
    other = int(column_kinds.non_numeric_mask(values).sum())
    return 0 if numeric == 0 or other == 0 else min(numeric, other)


def _constant_column(values: pd.Series, dayfirst: bool) -> int:
    """Every cell of a column with a single value. Nothing can be learned from
    such a column, so the whole column is the issue."""
    text = column_kinds.as_text(values).dropna()
    return len(text) if text.nunique() == 1 else 0


def _near_duplicate_labels(values: pd.Series, dayfirst: bool) -> int:
    """Cells whose label has a near-twin: the same text once case, spacing and
    punctuation are ignored ("Coca-Cola" and "coca cola"). Cells that differ by
    case alone belong to `inconsistent_case` and are not counted twice, so the
    two codes can be reported side by side.
    """
    counts = column_kinds.as_text(values).dropna().value_counts()
    groups: dict[str, dict[str, int]] = {}
    for spelling, count in sorted((str(v), int(c)) for v, c in counts.items()):
        folded = spelling.casefold()
        by_case = groups.setdefault(_normalize_label(spelling), {})
        by_case[folded] = by_case.get(folded, 0) + count
    total = 0
    for by_case in groups.values():
        if len(by_case) > 1:
            # Sorted by count, then by label, so the dominant spelling never
            # depends on the order the file happened to use.
            ranked = sorted(by_case.items(), key=lambda pair: (-pair[1], pair[0]))
            total += sum(count for _, count in ranked[1:])
    return total


def _normalize_label(value: str) -> str:
    return _SPACES.sub(" ", _PUNCTUATION.sub(" ", value.casefold())).strip()


_COUNTERS = {
    "negative_values": _negative_values,
    "zero_values": _zero_values,
    "trailing_whitespace": _trailing_whitespace,
    "outliers_iqr": _outliers_iqr,
    "inconsistent_case": _inconsistent_case,
    "invalid_dates": _invalid_dates,
    "mixed_date_formats": _mixed_date_formats,
    "non_numeric_in_numeric": _non_numeric_in_numeric,
    "mixed_types": _mixed_types,
    "constant_column": _constant_column,
    "near_duplicate_labels": _near_duplicate_labels,
}
