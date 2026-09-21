"""Plan-time validation of an action's params (docs/AI_PIPELINE.md section 11).

The plan is checked before anything runs (docs/CONTRACTS.md section 4), so a
params mistake must be caught here rather than when the user has already
confirmed. The rules are the ones `transforms.py` enforces when the action runs,
applied earlier; a test ties the two together so they cannot drift apart.

Split out of `transform_catalog.py`, which keeps the matrix, the order and the
param names these checks are written against.
"""

import math
import re
from collections.abc import Callable, Mapping
from typing import Any

import pandas as pd

from contracts.cleaning import TransformAction
from stages.ingest import column_kinds
from stages.ingest.profiling import NA_TOKENS
from stages.ingest.transform_catalog import (
    CASE_MODES,
    CAST_TARGETS,
    NEGATIVE_STRATEGIES,
    OPTIONAL_PARAMS,
    REQUIRED_PARAMS,
)

# How much of a rejected value the message repeats: it goes back into the AI's
# retry prompt, and a value can be as long as the answer.
_SHOWN_CHARS = 40


def _show(value: Any) -> str:
    try:
        text = repr(value)
    except (RecursionError, ValueError):
        # A list nested a thousand deep, or an integer too long to print: what
        # the AI sent must never be able to raise here.
        text = f"<{type(value).__name__}>"
    return text if len(text) <= _SHOWN_CHARS else text[: _SHOWN_CHARS - 3] + "..."


def _one_of(allowed: frozenset[str]) -> Callable[[Any], str | None]:
    def check(value: Any) -> str | None:
        # The type test comes first: a list would make `in` raise.
        if isinstance(value, str) and value in allowed:
            return None
        return f"must be one of {sorted(allowed)}, got {_show(value)}"

    return check


def _scalar(value: Any) -> str | None:
    if isinstance(value, str | int | float) and (
        not isinstance(value, float) or math.isfinite(value)
    ):
        return None  # a bool is an int here
    return f"must be text, a number or true/false, got {_show(value)}"


def _fill_value(value: Any) -> str | None:
    """A value that fills a gap. Text that profiling reads as missing ("N/A",
    "NULL", "") would turn back into a gap the next time cleaned.csv is read,
    and "" fills nothing: the change log would still say N cells were filled."""
    problem = _scalar(value)
    if problem is not None:
        return problem
    if isinstance(value, str) and (not value.strip() or value in NA_TOKENS):
        return (f"must not be empty or a missing-value token such as 'NA' or 'N/A' "
                f"(it would read back as missing), got {_show(value)}")
    return None


def _text(value: Any) -> str | None:
    return None if isinstance(value, str) else f"must be text, got {_show(value)}"


def _flag(value: Any) -> str | None:
    return None if isinstance(value, bool) else f"must be true or false, got {_show(value)}"


def _text_mapping(value: Any) -> str | None:
    if not (
        isinstance(value, dict)
        and all(isinstance(key, str) and isinstance(label, str) for key, label in value.items())
    ):
        return f"must map text to text, got {_show(value)}"
    for label in value.values():
        # Only what a label becomes matters. Merged into "NA" or an empty text it
        # would read back as missing the next time cleaned.csv is read.
        if not label.strip() or label in NA_TOKENS:
            return (f"must not map a label to text that would read back as missing "
                    f"(an empty text, NA, N/A, NULL...), got {_show(label)}")
    return None


def _key_list(value: Any) -> str | None:
    if (
        isinstance(value, list)
        and value
        and all(isinstance(key, str) for key in value)
        and len(set(value)) == len(value)
    ):
        return None
    return f"must be a non-empty list of distinct column names, got {_show(value)}"


def _non_negative_number(value: Any) -> str | None:
    if isinstance(value, int | float) and not isinstance(value, bool):
        try:
            # clip_outliers_iqr converts k with float(), so a number that
            # cannot be one (a 400-digit integer) would fail at execution.
            usable = math.isfinite(float(value)) and value >= 0
        except OverflowError:
            usable = False
        if usable:
            return None
    return f"must be a number that is not negative, got {_show(value)}"


# pandas' keyword for ISO 8601 cells. "mixed" (each cell on its own) is not
# accepted: it is what parse_datetime does when no format is given, except that
# `dayfirst` is dropped whenever a format is passed, so {"format": "mixed",
# "dayfirst": true} and {"dayfirst": true} would give different dates.
_DATE_KEYWORDS = frozenset({"ISO8601"})


_YEAR_DIRECTIVE = re.compile(r"%[Yy]")


def _date_format(value: Any) -> str | None:
    """A format that turns the column into dates. `errors="coerce"` covers cells
    that do not match, not a format that is itself malformed ("%Q", "%", "%Y%Y"),
    which fails at execution; the probe below is the very call `parse_datetime`
    makes. Two formats pandas accepts are refused because they run and then
    rewrite the column into nonsense: an empty one (it matches nothing, so every
    date is flagged invalid) and one with no year ("%d", "%H", "abc": every date
    becomes the year 1900, or nothing parses).

    A year is checked first, so the leap-day warning pandas gives a format
    without one cannot arise, and no process-wide warning filter has to be
    changed (two requests checking plans in worker threads would race on it).
    """
    if not isinstance(value, str) or not value.strip():
        return f"must be a date format such as '%Y-%m-%d', got {_show(value)}"
    if value in _DATE_KEYWORDS:
        return None
    if not _YEAR_DIRECTIVE.search(value.replace("%%", "")):  # "%%" is a literal %
        return (f"must include a year (%Y or %y), got {_show(value)}; "
                f"leave format out to parse each cell on its own")
    try:
        column_kinds.as_dates(pd.Series(["2024-01-05"], dtype="str"), value)
    except (ValueError, re.error, OverflowError):
        return f"is not a date format pandas can use, got {_show(value)}"
    return None


# One check per param an action may take (a test walks REQUIRED_PARAMS and
# OPTIONAL_PARAMS, so a new param cannot go unchecked). These are the same rules
# `transforms.py` enforces when the action runs, applied before anything does.
_VALUE_CHECKS: dict[tuple[str, str], Callable[[Any], str | None]] = {
    ("impute_constant", "value"): _fill_value,
    ("cast_type", "target"): _one_of(CAST_TARGETS),
    ("normalize_case", "mode"): _one_of(CASE_MODES),
    ("standardize_categories", "mapping"): _text_mapping,
    ("flag_duplicate_keys", "keys"): _key_list,
    ("parse_datetime", "format"): _date_format,
    ("parse_datetime", "dayfirst"): _flag,
    ("fix_negative", "strategy"): _one_of(NEGATIVE_STRATEGIES),
    ("clip_outliers_iqr", "k"): _non_negative_number,
    ("flag_only", "note"): _text,
}


def params_problem(action: TransformAction, params: Mapping[str, Any]) -> str | None:
    """Why these params cannot run `action`, or None when they can: a name the
    action does not take, a required one that is missing, or a value the action
    would refuse. Checked when the plan is written, so nothing the user
    confirms can fail for its params.

    Whether a `keys` entry is a real column depends on the file, so it is the
    caller's check (`ai_plan.py`), not this one's.
    """
    required = REQUIRED_PARAMS.get(action, frozenset())
    allowed = required | OPTIONAL_PARAMS.get(action, frozenset())
    unknown = sorted(set(params) - allowed)
    if unknown:
        # A few names, each shortened: the AI chose them, and the message goes
        # back into its retry prompt.
        named = [_show(name).strip("'\"") for name in unknown[:3]]
        more = ["..."] if len(unknown) > 3 else []
        return f"{action} takes {sorted(allowed) or 'no params'}, not {named + more}"
    missing = sorted(required - set(params))
    if missing:
        return f"{action} needs the param {missing}"
    for name, value in params.items():
        problem = _VALUE_CHECKS[action, name](value)
        if problem is not None:
            return f"{action} param {name}: {problem}"
    return None
