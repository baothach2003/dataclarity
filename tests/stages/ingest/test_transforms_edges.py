"""The edge cases every transform has to survive (CLAUDE.md section 5,
docs/AI_PIPELINE.md section 10): an empty dataframe, a single row, an all-null
column, a zero denominator (an IQR of 0), and non-numeric text in a column a
numeric action is pointed at.

Every action is run against each of them, so a new action cannot be added
without meeting the same bar.
"""

import pandas as pd
import pytest

from contracts.cleaning import TransformAction
from stages.ingest import transforms
from stages.ingest.transform_catalog import ALL_ACTIONS, DATASET_ACTIONS

NA = None

# Params for every action, so one parametrized test can walk the whole catalog.
# The column is always "qty" (or None for a dataset action).
PARAMS: dict[TransformAction, dict[str, object]] = {
    "impute_median": {},
    "impute_mean": {},
    "impute_mode": {},
    "impute_constant": {"value": "Unknown"},
    "drop_rows_missing": {},
    "drop_column": {},
    "parse_datetime": {},
    "cast_type": {"target": "float"},
    "trim_whitespace": {},
    "normalize_case": {"mode": "title"},
    "standardize_categories": {"mapping": {"a": "b"}},
    "fix_negative": {},
    "remove_exact_duplicates": {},
    "flag_duplicate_keys": {"keys": ["qty"]},
    "clip_outliers_iqr": {},
    "flag_only": {"note": "checked"},
}

ACTIONS = sorted(ALL_ACTIONS)


def column(*values: str | None) -> pd.Series:
    return pd.Series(list(values), dtype="str")


def run(action: TransformAction, data: pd.DataFrame) -> tuple[pd.DataFrame, object]:
    target = None if action in DATASET_ACTIONS else "qty"
    return transforms.apply_action(action, data, target, PARAMS[action])


def test_every_action_has_params_for_these_cases() -> None:
    assert set(PARAMS) == ALL_ACTIONS


# --- the four mandatory edge cases, action by action ------------------------


@pytest.mark.parametrize("action", ACTIONS)
def test_an_empty_dataframe_changes_nothing(action: TransformAction) -> None:
    empty = pd.DataFrame({"qty": column()})

    result, entry = run(action, empty)

    assert (entry.cells_affected, entry.rows_affected) == (0, 0)
    assert len(result) == 0


@pytest.mark.parametrize("action", ACTIONS)
def test_a_single_row_survives_every_action(action: TransformAction) -> None:
    one = pd.DataFrame({"qty": column("5")})

    result, entry = run(action, one)

    # Only drop_column removes the column, and no action drops this row: 5 is
    # present, not negative, and has nothing to be a duplicate of. "5" is not a
    # date, so parse_datetime flags its one row - it still does not drop it.
    assert len(result) == 1
    assert entry.rows_affected == (1 if action == "parse_datetime" else 0)
    expected = {"drop_column": [], "parse_datetime": ["qty", "__flag_invalid_date__qty"]}
    assert list(result.columns) == expected.get(action, ["qty"])


@pytest.mark.parametrize("action", ACTIONS)
def test_an_all_null_column_is_never_invented_into(action: TransformAction) -> None:
    nulls = pd.DataFrame({"qty": column(NA, NA)})

    result, entry = run(action, nulls)

    if action == "impute_constant":
        # The only action with a value of its own: it fills, as asked.
        assert (entry.cells_affected, result["qty"].tolist()) == (2, ["Unknown", "Unknown"])
    elif action == "drop_rows_missing":
        assert (entry.rows_affected, len(result)) == (2, 0)
    elif action == "drop_column":
        assert (entry.cells_affected, list(result.columns)) == (2, [])
    elif action == "remove_exact_duplicates":
        assert entry.rows_affected == 1  # the two null rows are identical
    elif action == "flag_duplicate_keys":
        assert entry.rows_affected == 2  # both rows share the same empty key
    else:
        # Nothing can be computed from an empty column, and nothing is guessed.
        assert (entry.cells_affected, entry.rows_affected) == (0, 0)
        assert result["qty"].isna().tolist() == [True, True]


@pytest.mark.parametrize("action", ACTIONS)
def test_a_zero_variance_column_has_no_zero_division(action: TransformAction) -> None:
    # IQR = q3 - q1 = 0 is the denominator-free version of a divide by zero:
    # the fence collapses onto the single value.
    constant = pd.DataFrame({"qty": column("5", "5", "5", "5")})

    result, entry = run(action, constant)

    if action == "clip_outliers_iqr":
        assert (entry.cells_affected, entry.detail) == (
            0, "clipped 0 values into [5.0, 5.0] (k=1.5)"
        )
    assert len(result) == (1 if action == "remove_exact_duplicates" else 4)


@pytest.mark.parametrize("action", ACTIONS)
def test_non_numeric_text_never_becomes_a_number_by_accident(
    action: TransformAction,
) -> None:
    # A numeric action pointed at a dirty column (the legality matrix forbids
    # this, but a transform may not corrupt data when it is reached anyway).
    dirty = pd.DataFrame({"qty": column("1", "n/a value", "3")})

    result, entry = run(action, dirty)

    if action in {"impute_median", "impute_mean"}:
        # Computed from 1 and 3 only; nothing is missing, so nothing is filled.
        assert (entry.cells_affected, result["qty"].tolist()) == (0, ["1", "n/a value", "3"])
    elif action == "cast_type":
        assert (entry.cells_affected, entry.rows_affected) == (2, 1)
    elif action == "clip_outliers_iqr":
        # Fence over [1, 3]: q1 = 1.5, q3 = 2.5, IQR = 1, fence = [0.0, 4.0].
        assert (entry.cells_affected, result["qty"].tolist()) == (0, ["1", "n/a value", "3"])
    elif action == "fix_negative":
        assert entry.rows_affected == 0  # text is not a negative number


# --- a column that is not there ---------------------------------------------


@pytest.mark.parametrize("action", [a for a in ACTIONS if a not in DATASET_ACTIONS])
def test_a_column_action_refuses_a_missing_column(action: TransformAction) -> None:
    data = pd.DataFrame({"qty": column("1")})

    with pytest.raises(ValueError, match="no such column"):
        transforms.apply_action(action, data, "not here", PARAMS[action])


@pytest.mark.parametrize("action", [a for a in ACTIONS if a not in DATASET_ACTIONS])
def test_a_column_action_refuses_no_column_at_all(action: TransformAction) -> None:
    data = pd.DataFrame({"qty": column("1")})

    with pytest.raises(ValueError, match="needs a column"):
        transforms.apply_action(action, data, None, PARAMS[action])


@pytest.mark.parametrize("action", sorted(DATASET_ACTIONS))
def test_a_dataset_action_refuses_a_column(action: TransformAction) -> None:
    data = pd.DataFrame({"qty": column("1")})

    with pytest.raises(ValueError, match="applies to the dataset"):
        transforms.apply_action(action, data, "qty", PARAMS[action])


# --- flag columns -----------------------------------------------------------


@pytest.mark.parametrize("action", ACTIONS)
def test_a_clean_column_gains_no_flag_column(action: TransformAction) -> None:
    # Clean for every action but parse_datetime, for which a quantity is dirt
    # by definition; that column gets dates instead.
    values = column("2024-01-05", "2024-01-06") if action == "parse_datetime" \
        else column("1", "2", "3")

    result, _ = run(action, pd.DataFrame({"qty": values}))

    assert [c for c in result.columns if str(c).startswith(transforms.FLAG_PREFIX)] == []


def test_a_flag_column_is_named_after_its_kind_and_column() -> None:
    assert transforms.flag_column_name("negative", "Unit Price") == "__flag_negative__Unit Price"
    assert transforms.flag_column_name("duplicate_key") == "__flag_duplicate_key"


def test_casting_whole_numbers_beyond_int64_to_integer_is_a_flagged_failure_not_a_crash() -> None:
    # "1e30" and 20 nines are whole numbers but do not fit an int64. pandas
    # raised "cannot safely cast" instead of leaving the cell missing.
    data = pd.DataFrame({"c": ["5", "1e30", "99999999999999999999", "2.5", NA]}, dtype="str")

    result, entry = transforms.apply_action("cast_type", data, "c", {"target": "integer"})

    assert result["c"].tolist()[0] == 5
    assert result["c"].isna().tolist() == [False, True, True, True, True]
    assert (entry.cells_affected, entry.rows_affected) == (1, 3)  # 1 converted, 3 flagged
    assert result["__flag_cast_failed__c"].tolist() == [False, True, True, True, False]


def test_the_int64_limits_themselves_are_flagged_never_a_crash_or_a_wrong_number() -> None:
    # Numbers are read as float64, which cannot hold 19-digit integers exactly
    # (-2**63 is read as -9.223372036854778e18), so a cell at the very edge of
    # int64 is a flagged failure. What matters is that nothing raises and no
    # cell receives a value it did not have.
    data = pd.DataFrame({"c": ["-9223372036854775808", "9223372036854775808"]}, dtype="str")

    result, entry = transforms.apply_action("cast_type", data, "c", {"target": "integer"})

    assert result["c"].isna().tolist() == [True, True]
    assert entry.rows_affected == 2
