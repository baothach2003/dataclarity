"""Plan-time param validation (stages/ingest/transform_params.params_problem).

The plan is checked before anything runs (docs/CONTRACTS.md section 4), so a
params mistake must be caught here rather than when the user has already
confirmed. `test_it_agrees_with_what_the_transforms_enforce` ties this check
to `transforms.py`, so the two cannot drift apart.
"""

import re
import warnings
from typing import Any

import pandas as pd
import pytest

from contracts.cleaning import TransformAction
from stages.ingest import transforms
from stages.ingest.transform_catalog import ALL_ACTIONS, OPTIONAL_PARAMS, REQUIRED_PARAMS
from stages.ingest.transform_params import params_problem

VALID: list[tuple[TransformAction, dict[str, Any]]] = [
    ("impute_median", {}),
    ("impute_mean", {}),
    ("impute_mode", {}),
    ("drop_rows_missing", {}),
    ("trim_whitespace", {}),
    ("impute_constant", {"value": "Unknown"}),
    ("impute_constant", {"value": 0}),
    ("impute_constant", {"value": False}),
    ("cast_type", {"target": "integer"}),
    ("normalize_case", {"mode": "lower"}),
    ("standardize_categories", {"mapping": {"cafe": "Cafe"}}),
    ("standardize_categories", {"mapping": {}}),  # merges nothing; harmless, not invalid
    ("flag_duplicate_keys", {"keys": ["sku", "day"]}),
    ("parse_datetime", {}),
    ("parse_datetime", {"format": "%Y-%m-%d", "dayfirst": True}),
    ("fix_negative", {}),
    ("fix_negative", {"strategy": "abs"}),
    ("clip_outliers_iqr", {}),
    ("clip_outliers_iqr", {"k": 3}),
    ("clip_outliers_iqr", {"k": 1.5}),
    ("flag_only", {}),
    ("flag_only", {"note": "no action needed"}),
    ("drop_column", {}),
    ("remove_exact_duplicates", {}),
]

INVALID: list[tuple[TransformAction, dict[str, Any], str]] = [
    ("impute_median", {"why": 1}, "takes no params"),
    ("drop_column", {"why": "x"}, "takes no params"),
    ("fix_negative", {"mode": "abs"}, "['strategy']"),
    ("impute_constant", {}, "needs the param ['value']"),
    ("impute_constant", {"value": None}, "value"),
    ("impute_constant", {"value": float("nan")}, "value"),
    ("impute_constant", {"value": ["a"]}, "value"),
    ("cast_type", {}, "needs the param ['target']"),
    ("cast_type", {"target": "decimal"}, "target"),
    ("normalize_case", {}, "needs the param ['mode']"),
    ("normalize_case", {"mode": "camel"}, "mode"),
    ("normalize_case", {"mode": ["lower"]}, "mode"),
    ("standardize_categories", {}, "needs the param ['mapping']"),
    ("standardize_categories", {"mapping": "a to b"}, "mapping"),
    ("standardize_categories", {"mapping": {"a": 1}}, "mapping"),
    ("flag_duplicate_keys", {}, "needs the param ['keys']"),
    ("flag_duplicate_keys", {"keys": []}, "keys"),
    ("flag_duplicate_keys", {"keys": "sku"}, "keys"),
    ("flag_duplicate_keys", {"keys": [1]}, "keys"),
    ("flag_duplicate_keys", {"keys": ["sku", "sku"]}, "keys"),
    ("fix_negative", {"strategy": "round"}, "strategy"),
    ("clip_outliers_iqr", {"k": -1}, "k"),
    ("clip_outliers_iqr", {"k": True}, "k"),
    ("clip_outliers_iqr", {"k": "3"}, "k"),
    ("clip_outliers_iqr", {"k": float("nan")}, "k"),
    ("parse_datetime", {"format": 5}, "format"),
    ("parse_datetime", {"format": ""}, "format"),
    ("parse_datetime", {"format": "   "}, "format"),
    ("clip_outliers_iqr", {"k": 10**400}, "k"),
    ("clip_outliers_iqr", {"k": -(10**400)}, "k"),
    ("parse_datetime", {"dayfirst": "yes"}, "dayfirst"),
    ("flag_only", {"note": 3}, "note"),
]


@pytest.mark.parametrize(("action", "params"), VALID)
def test_valid_params_pass(action: TransformAction, params: dict[str, Any]) -> None:
    assert params_problem(action, params) is None


@pytest.mark.parametrize(("action", "params", "fragment"), INVALID)
def test_invalid_params_name_the_action_and_the_problem(
    action: TransformAction, params: dict[str, Any], fragment: str
) -> None:
    problem = params_problem(action, params)

    assert problem is not None and problem.startswith(action) and fragment in problem


def test_every_action_the_catalog_lists_has_a_passing_params_case() -> None:
    # A new action must come with a case here, or its params go unchecked.
    assert {action for action, _ in VALID} == ALL_ACTIONS


def test_every_param_a_catalog_action_may_take_has_a_value_check() -> None:
    # An allowed name with no checker would raise KeyError on a real plan.
    for action in ALL_ACTIONS:
        for name in REQUIRED_PARAMS.get(action, frozenset()) | OPTIONAL_PARAMS.get(
            action, frozenset()
        ):
            assert params_problem(action, {name: object()}) is not None, (action, name)


def test_a_long_value_is_shortened_in_the_message() -> None:
    # The message goes back into the retry prompt; it must stay small.
    problem = params_problem("cast_type", {"target": "x" * 5000})

    assert problem is not None and len(problem) < 300


# --- agreement with the transforms -----------------------------------------------

FRAME = pd.DataFrame({"c": ["1", "2", "2"]}, dtype="str")


def _runs(action: TransformAction, params: dict[str, Any]) -> bool:
    column = None if action in {"remove_exact_duplicates", "flag_duplicate_keys"} else "c"
    try:
        transforms.apply_action(action, FRAME, column, params)
    except ValueError:
        return False
    return True


AGREE_VALID: list[tuple[TransformAction, dict[str, Any]]] = [
    ("impute_constant", {"value": "Unknown"}),
    ("cast_type", {"target": "integer"}),
    ("normalize_case", {"mode": "upper"}),
    ("standardize_categories", {"mapping": {"2": "two"}}),
    ("flag_duplicate_keys", {"keys": ["c"]}),
    ("fix_negative", {"strategy": "drop"}),
    ("clip_outliers_iqr", {"k": 3}),
    # The values do not match, so every cell is a flagged failure - still no error.
    ("parse_datetime", {"format": "%Y-%m-%d"}),
    ("flag_only", {"note": "fine"}),
]
AGREE_INVALID: list[tuple[TransformAction, dict[str, Any]]] = [
    ("impute_constant", {}),
    ("impute_constant", {"value": None}),
    ("cast_type", {}),
    ("cast_type", {"target": "decimal"}),
    ("normalize_case", {}),
    ("normalize_case", {"mode": "camel"}),
    ("standardize_categories", {}),
    ("standardize_categories", {"mapping": "a to b"}),
    ("standardize_categories", {"mapping": {"a": 1}}),
    ("flag_duplicate_keys", {}),
    ("flag_duplicate_keys", {"keys": []}),
    ("flag_duplicate_keys", {"keys": "c"}),
    ("flag_duplicate_keys", {"keys": [1]}),
    ("fix_negative", {"strategy": "round"}),
    ("clip_outliers_iqr", {"k": -1}),
    ("clip_outliers_iqr", {"k": True}),
    ("parse_datetime", {"format": 5}),
    ("flag_only", {"note": 3}),
]


@pytest.mark.parametrize(("action", "params"), AGREE_VALID)
def test_it_agrees_with_what_the_transforms_enforce(
    action: TransformAction, params: dict[str, Any]
) -> None:
    assert params_problem(action, params) is None
    assert _runs(action, params)


@pytest.mark.parametrize(("action", "params"), AGREE_INVALID)
def test_it_rejects_what_the_transforms_would_refuse(
    action: TransformAction, params: dict[str, Any]
) -> None:
    assert params_problem(action, params) is not None
    assert not _runs(action, params)


# --- a date format the transform cannot use (found in the 1E review) ----------
# errors="coerce" does not protect against a malformed format string, so a plan
# carrying one used to be accepted and then fail after the user confirmed.

BAD_FORMATS = ["%Y-%m-%d %Q", "%", "%Y%Y", "%(", "%Y-%m-%d %"]


@pytest.mark.parametrize("date_format", BAD_FORMATS)
def test_a_date_format_the_transform_chokes_on_is_rejected_at_plan_time(date_format: str) -> None:
    problem = params_problem("parse_datetime", {"format": date_format})

    assert problem is not None and "format" in problem
    with pytest.raises((ValueError, re.error)):
        transforms.apply_action("parse_datetime", FRAME, "c", {"format": date_format})


@pytest.mark.parametrize(
    "date_format",
    ["%Y-%m-%d", "%d/%m/%Y", "%d/%m/%y", "%Y-%m-%dT%H:%M:%S%z", "ISO8601"],
)
def test_a_usable_date_format_passes(date_format: str) -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("error")  # the probe itself must not leak a warning
        assert params_problem("parse_datetime", {"format": date_format}) is None


def test_an_empty_format_is_rejected_because_it_would_flag_every_date() -> None:
    # Unlike the others this one runs: pandas reads "" as a real format that
    # matches nothing, so every date in the column would be flagged invalid.
    parsed = transforms.apply_action("parse_datetime", FRAME, "c", {"format": ""})[1]

    assert parsed.rows_affected == 3  # the whole column flagged
    assert params_problem("parse_datetime", {"format": ""}) is not None


# --- hostile values: the check answers, it never raises -------------------------
# A non-ValueError from a stage check skips the retry and the degraded path
# (shared/ai_client only catches ValueError), so any JSON the AI can send must
# come back as a message or None.


def _nested(depth: int) -> Any:
    value: Any = []
    for _ in range(depth):
        value = [value]
    return value


HOSTILE: list[Any] = [
    None, True, False, 0, -1, 10**400, -(10**400), 10**4000, float("nan"), float("inf"),
    float("-inf"), 1e308, "", "x" * 10_000, "%" * 50, "\x00", [], [[]], [[1], [2]], [None],
    ["a", ["b"]], {}, {"a": None}, {"a": {"b": [1]}}, {"": ""}, _nested(900), [0] * 5000,
    {str(i): str(i) for i in range(2000)},
]
EVERY_PARAM = sorted(
    (action, name)
    for action in ALL_ACTIONS
    for name in REQUIRED_PARAMS.get(action, frozenset()) | OPTIONAL_PARAMS.get(action, frozenset())
)


@pytest.mark.parametrize(("action", "name"), EVERY_PARAM)
def test_no_value_can_make_the_param_check_raise(action: TransformAction, name: str) -> None:
    for value in HOSTILE:
        problem = params_problem(action, {name: value})

        assert problem is None or len(problem) < 400, (action, name, repr(value)[:40])


def test_hostile_param_names_do_not_flood_the_message() -> None:
    problem = params_problem("drop_column", {"n" * 6000: 1})

    assert problem is not None and len(problem) < 300


# A format with no year is accepted by pandas, and gives every date the year
# 1900 (or, for text such as "abc", parses nothing): the column would be
# rewritten into nonsense while the plan looked fine.
MEANINGLESS_FORMATS = ["abc", "%d", "%H", "%%", "%m/%d", "%H:%M:%S.%f", "%B"]


@pytest.mark.parametrize("date_format", MEANINGLESS_FORMATS)
def test_a_date_format_with_no_year_is_rejected(date_format: str) -> None:
    problem = params_problem("parse_datetime", {"format": date_format})

    assert problem is not None and "year" in problem


def test_a_format_with_no_year_is_refused_before_pandas_is_asked_to_parse_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A format without a year is the one case pandas warns about (a leap-day
    # deprecation), and the check used to silence that warning with
    # warnings.catch_warnings, which swaps process-wide state that two requests
    # checking plans in worker threads would race on. Refusing it first means
    # pandas is never called for it, and this module no longer imports warnings.
    from stages.ingest import column_kinds, transform_params

    called: list[str] = []
    monkeypatch.setattr(column_kinds, "as_dates", lambda *args, **kwargs: called.append("x"))

    assert params_problem("parse_datetime", {"format": "%d/%m"}) is not None
    assert called == []
    assert not hasattr(transform_params, "warnings")


# --- a fill that is not a fill (cycle-3 review) -----------------------------------
# profiling reads these tokens as missing, so a cell filled with one would turn
# back into a gap the next time cleaned.csv is read; "" fills nothing at all.


@pytest.mark.parametrize("value", ["", "   ", "N/A", "NA", "NULL", "null", "nan", "None", "n/a", "<NA>"])
def test_a_fill_value_that_reads_back_as_missing_is_rejected(value: str) -> None:
    problem = params_problem("impute_constant", {"value": value})

    assert problem is not None and "missing" in problem


@pytest.mark.parametrize("value", ["Unknown", "Not stated", "0", 0, 12.5, False])
def test_an_ordinary_fill_value_is_accepted(value: object) -> None:
    assert params_problem("impute_constant", {"value": value}) is None


def test_the_mixed_keyword_is_not_a_format() -> None:
    # It is what parse_datetime does when no format is given, minus dayfirst,
    # which is dropped whenever a format is: {"format": "mixed", "dayfirst": true}
    # and {"dayfirst": true} give different dates.
    problem = params_problem("parse_datetime", {"format": "mixed"})

    assert problem is not None and "leave format out" in problem


# --- a label mapped to something that reads back as missing (1F review) ---------------------
# profiling reads "", "NA", "N/A", "NULL"... as missing, so a category merged into one
# of them would turn back into a gap the next time cleaned.csv is read.


@pytest.mark.parametrize("target", ["", "  ", "NA", "N/A", "NULL", "null", "nan", "None"])
def test_a_mapping_may_not_send_a_label_to_a_missing_value_token(target: str) -> None:
    problem = params_problem("standardize_categories", {"mapping": {"foo": target}})

    assert problem is not None and "read back as missing" in problem


def test_a_mapping_to_ordinary_labels_and_from_any_text_is_fine() -> None:
    # Only what a label becomes matters; the labels being replaced can be anything.
    assert params_problem("standardize_categories", {"mapping": {"NA": "Unknown", "": "Unknown", "cafe": "Cafe"}}) is None
