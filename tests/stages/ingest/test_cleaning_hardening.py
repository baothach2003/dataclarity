"""Defects the 1F review found in the transforms and the engine, each with the
input that showed it (stages/ingest/changes.py, column_kinds.py, cleaning.py)."""

import pandas as pd
import pytest

from stages.ingest import transforms
from stages.ingest.cleaning import apply_plan
from stages.ingest.column_kinds import as_numbers, non_numeric_mask
from stages.ingest.profiling import read_csv_text
from tests.stages.ingest.cleaning_fixtures import column_action, make_plan


def column(*values: str | None) -> pd.Series:
    return pd.Series(list(values), dtype="str")


def frame_of(csv: str) -> pd.DataFrame:
    return read_csv_text(csv.encode()).frame


# --- a source column is never overwritten by a flag ----------------------------------------


def test_a_flag_column_never_overwrites_a_source_column_of_the_same_name() -> None:
    # What a re-uploaded cleaned.csv looks like: it already has the flag column.
    df = pd.DataFrame({"__flag_negative__amt": ["keepme", "keepme2"], "amt": ["-1", "2"]})

    result, entry = transforms.fix_negative(df, "amt", {})

    assert result["__flag_negative__amt"].tolist() == ["keepme", "keepme2"]
    assert result["__flag_negative__amt_2"].tolist() == [True, False]
    assert "flagged in __flag_negative__amt_2" in entry.detail


def test_the_next_free_name_is_taken_when_several_are_used() -> None:
    df = pd.DataFrame({"__flag_negative__amt": ["a"], "__flag_negative__amt_2": ["b"], "amt": ["-1"]})

    result, _ = transforms.fix_negative(df, "amt", {})

    assert result["__flag_negative__amt_3"].tolist() == [True]
    assert result["__flag_negative__amt_2"].tolist() == ["b"]


def test_the_duplicate_key_flag_does_not_overwrite_a_column_either() -> None:
    df = pd.DataFrame({"__flag_duplicate_key": ["hello", "world"], "a": ["1", "1"]})

    result, _ = transforms.flag_duplicate_keys(df, None, {"keys": ["a"]})

    assert result["__flag_duplicate_key"].tolist() == ["hello", "world"]
    assert result["__flag_duplicate_key_2"].tolist() == [True, True]


# --- a flag column that ends up empty is not left behind -------------------------------------


CSV = "sku,name,qty,price,day\nA1,Mug,3,9.99,2024-01-05\nB2,Cup,4,,not a date\nC3,Pen,5,1.50,2024-01-07\n"


def test_a_flag_whose_rows_a_later_action_drops_leaves_no_all_false_column() -> None:
    # Row 2's date fails to parse and is flagged; then its missing price drops the
    # row. The flag is False everywhere that is left.
    plan = make_plan([column_action("sku"), column_action("name"), column_action("qty"),
                      column_action("price", "drop_rows_missing"),
                      column_action("day", "parse_datetime")])

    cleaned, changes = apply_plan(frame_of(CSV), plan)

    assert list(cleaned.columns) == ["sku", "name", "qty", "price", "day"]
    # The log still says what happened at that step.
    assert next(c for c in changes if c.action == "parse_datetime").rows_affected == 1


def test_a_flag_that_is_still_set_stays() -> None:
    plan = make_plan([column_action("sku"), column_action("name"), column_action("qty"),
                      column_action("price"), column_action("day", "parse_datetime")])

    cleaned, _ = apply_plan(frame_of(CSV), plan)

    assert cleaned["__flag_invalid_date__day"].tolist() == [False, True, False]


def test_a_source_column_that_looks_like_a_flag_is_never_pruned() -> None:
    csv = "sku,name,qty,price,day,__flag_mine\nA1,Mug,3,1.00,2024-01-05,False\n"
    plan = make_plan([column_action(n) for n in ("sku", "name", "qty", "price", "day")]
                     + [column_action("sku", source_name="__flag_mine")])

    cleaned, _ = apply_plan(frame_of(csv), plan)

    assert "__flag_mine" in cleaned.columns  # the user's own data, all False


# --- infinity is not a number (profiling already says so) --------------------------------------------


@pytest.mark.parametrize(
    "cell",
    ["inf", "-inf", "Infinity", "1e999", "-1e999", pytest.param("9" * 400, id="400-nines")],
)
def test_a_non_finite_value_is_not_a_number(cell: str) -> None:
    assert as_numbers(column(cell, "5")).isna().tolist() == [True, False]
    assert non_numeric_mask(column(cell, "5")).tolist() == [True, False]  # text in a column of numbers


def test_a_mean_is_not_dragged_to_infinity_by_an_inf_cell() -> None:
    df = pd.DataFrame({"n": ["inf", "4", None, "6"]})

    result, entry = transforms.impute_mean(df, "n", {})

    assert result["n"].tolist()[2] == 5.0  # the mean of 4 and 6
    assert "filled 1 missing cells with 5" in entry.detail


def test_abs_does_not_turn_a_huge_negative_into_infinity() -> None:
    df = pd.DataFrame({"n": ["-1e999", "-2"]})

    result, _ = transforms.fix_negative(df, "n", {"strategy": "abs"})

    assert result["n"].tolist() == ["-1e999", 2.0]


# --- a blank required field is dropped like a missing one (Q3, decided in 1F) ---------------------


def test_a_row_whose_required_cell_is_only_spaces_is_dropped_by_the_plan() -> None:
    raw = frame_of("sku,name,qty,price,day\nA1,Mug,3,1.00,2024-01-05\nB2,   ,4,2.00,2024-01-06\n")
    plan = make_plan([column_action("sku"), column_action("name", "drop_rows_missing"),
                      column_action("qty"), column_action("price"), column_action("day")])

    cleaned, changes = apply_plan(raw, plan)

    assert cleaned["sku"].tolist() == ["A1"]
    dropped = next(c for c in changes if c.action == "drop_rows_missing")
    assert dropped.rows_affected == 1 and "only spaces" in dropped.detail
