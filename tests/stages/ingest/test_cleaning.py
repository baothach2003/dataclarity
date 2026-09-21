"""Applying a plan to a frame (stages/ingest/cleaning.apply_plan) and writing the
result as CSV text (cleaned_csv_text). Every expected value is worked out by hand
from `cleaning_fixtures.RAW_CSV`."""

from io import StringIO

import pandas as pd
import pytest

from stages.ingest import transforms
from stages.ingest.cleaning import CleaningError, apply_plan, cleaned_csv_text
from stages.ingest.profiling import read_csv_text
from tests.stages.ingest.cleaning_fixtures import (
    RAW_CSV,
    column_action,
    dataset_action,
    make_plan,
)


def raw_frame(csv: bytes = RAW_CSV) -> pd.DataFrame:
    return read_csv_text(csv).frame


DEDUPLICATING = make_plan(dataset_actions=[dataset_action("remove_exact_duplicates")])


# --- the fixed order and the change log --------------------------------------------------


def test_the_change_log_lists_every_action_once_in_the_fixed_order() -> None:
    # remove_exact_duplicates, then trimming (sku, name in the plan's order), then
    # parse_datetime, then imputation, then fix_negative - not the order the plan
    # lists them in, which is columns first.
    _, changes = apply_plan(raw_frame(), DEDUPLICATING)

    assert [(c.action, c.column) for c in changes] == [
        ("remove_exact_duplicates", None),
        ("trim_whitespace", "sku"),
        ("trim_whitespace", "name"),
        ("parse_datetime", "day"),
        ("impute_median", "price"),
        ("fix_negative", "qty"),
    ]


def test_each_entry_counts_what_that_action_really_did() -> None:
    _, changes = apply_plan(raw_frame(), DEDUPLICATING)

    # (cells_affected, rows_affected): row 3 dropped as a copy of row 1; the only
    # padded name left is row 1's; 3 of 4 dates parsed and 1 flagged; one missing
    # price filled; one negative quantity flagged.
    assert [(c.cells_affected, c.rows_affected) for c in changes] == [
        (0, 1), (0, 0), (1, 0), (3, 1), (1, 0), (0, 1)]


def test_the_cleaned_file_is_what_the_plan_says_and_nothing_else() -> None:
    cleaned, _ = apply_plan(raw_frame(), DEDUPLICATING)

    assert cleaned_csv_text(cleaned) == (
        "sku,name,qty,price,day,__flag_invalid_date__day,__flag_negative__qty\n"
        "A1,Mug,3,9.99,2024-01-05,False,False\n"
        "B2,Cup,-1,9.99,2024-01-15,False,True\n"      # median of 9.99, 12.50, 7.00
        "C3,,5,12.50,2024-01-07,False,False\n"          # the missing name stays missing
        "D4,Plate,4,7.00,,True,False\n"                 # not a date: empty and flagged
    )


def test_the_input_frame_is_not_modified() -> None:
    before = raw_frame()

    apply_plan(before, DEDUPLICATING)

    pd.testing.assert_frame_equal(before, raw_frame())


def test_dropped_rows_keep_their_place_in_the_index() -> None:
    cleaned, _ = apply_plan(raw_frame(), DEDUPLICATING)

    assert cleaned.index.tolist() == [0, 1, 3, 4]  # row 3 (index 2) is the dropped copy


def test_an_action_that_changes_nothing_is_still_in_the_log() -> None:
    _, changes = apply_plan(raw_frame(), make_plan())

    assert ("trim_whitespace", "sku") in [(c.action, c.column) for c in changes]
    assert next(c for c in changes if c.column == "sku").cells_affected == 0


def test_a_column_marked_only_for_the_record_is_logged_last() -> None:
    plan = make_plan([column_action(n, "flag_only") for n in ("sku", "name", "qty", "price", "day")],
                     [dataset_action("remove_exact_duplicates")])

    _, changes = apply_plan(raw_frame(), plan)

    assert [c.action for c in changes] == ["remove_exact_duplicates", *["flag_only"] * 5]


# --- the order changes results, so it is fixed ---------------------------------------------


def frame_where_a_dropped_row_has_a_large_price() -> pd.DataFrame:
    # b has no price. d has no name, so it is dropped - and its price is 1000.
    return raw_frame(
        b"sku,name,qty,price,day\n"
        b"a,Mug,1,10,2024-01-05\n"
        b"b,Cup,1,,2024-01-05\n"
        b"c,Pen,1,20,2024-01-05\n"
        b"d,,1,1000,2024-01-05\n"
    )


@pytest.mark.parametrize("price_first", [True, False], ids=["price-listed-first", "name-listed-first"])
def test_rows_are_dropped_before_a_median_is_taken_whatever_the_column_order(
    price_first: bool,
) -> None:
    price = column_action("price", "impute_median")
    name = column_action("name", "drop_rows_missing")
    rest = [column_action("sku", "flag_only"), column_action("qty", "flag_only"),
            column_action("day", "flag_only")]
    plan = make_plan([price, name, *rest] if price_first else [name, price, *rest])

    cleaned, _ = apply_plan(frame_where_a_dropped_row_has_a_large_price(), plan)

    # The median of the rows that stay (10 and 20) is 15. Taken before the drop it
    # would be 20, and it would depend on which column the plan listed first.
    assert cleaned.loc[1, "price"] == 15.0
    assert cleaned.index.tolist() == [0, 1, 2]


def test_flags_see_the_cleaned_values_not_the_raw_ones() -> None:
    raw = raw_frame(
        b"sku,name,qty,price,day\n"
        b"A1, Mug ,3,1,2024-01-05\n"
        b"A1,Mug,4,2,2024-01-05\n"
        b"B2,Cup,1,3,2024-01-06\n"
    )
    plan = make_plan(
        [column_action("sku"), column_action("name", "trim_whitespace"), column_action("qty"),
         column_action("price"), column_action("day")],
        [dataset_action("flag_duplicate_keys", {"keys": ["sku", "name", "day"]})],
    )

    cleaned, changes = apply_plan(raw, plan)

    # " Mug " and "Mug" are the same product once trimmed, so rows 1 and 2 collide.
    assert cleaned["__flag_duplicate_key"].tolist() == [True, True, False]
    assert next(c for c in changes if c.action == "flag_duplicate_keys").rows_affected == 2


def test_dates_written_with_different_offsets_keep_the_date_as_written() -> None:
    raw = raw_frame(
        b"sku,name,qty,price,day\n"
        b"A1,Mug,3,9.99,2024-01-06 01:00:00+10:00\n"
        b"B2,Cup,4,1.50,2024-01-05 10:00:00-05:00\n"
    )
    plan = make_plan([column_action("sku"), column_action("name"), column_action("qty"),
                      column_action("price"), column_action("day", "parse_datetime")])

    cleaned, changes = apply_plan(raw, plan)

    # Read as UTC the first would be 2024-01-05: the day a report groups by.
    assert cleaned_csv_text(cleaned).splitlines()[1:] == [
        "A1,Mug,3,9.99,2024-01-06T01:00:00", "B2,Cup,4,1.50,2024-01-05T10:00:00"]
    assert "UTC offsets dropped" in next(c for c in changes if c.action == "parse_datetime").detail


# --- a failure is reported with where it happened ------------------------------------------------


def test_a_transform_that_fails_becomes_a_cleaning_error_naming_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def boom(df: pd.DataFrame, column: str | None, params: object) -> object:
        raise ValueError("cannot flag this")

    monkeypatch.setitem(transforms.ACTIONS, "fix_negative", boom)

    with pytest.raises(CleaningError) as caught:
        apply_plan(raw_frame(), make_plan())

    assert (caught.value.action, caught.value.column) == ("fix_negative", "qty")
    assert "fix_negative on column 'qty' failed: cannot flag this" in str(caught.value)


def test_an_unexpected_exception_is_wrapped_too_with_its_cause_kept(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def boom(df: pd.DataFrame, column: str | None, params: object) -> object:
        raise TypeError("pandas said no")

    monkeypatch.setitem(transforms.ACTIONS, "remove_exact_duplicates", boom)

    with pytest.raises(CleaningError) as caught:
        apply_plan(raw_frame(), DEDUPLICATING)

    assert caught.value.column is None
    assert "remove_exact_duplicates failed" in str(caught.value)
    assert isinstance(caught.value.__cause__, TypeError)


# --- writing the frame as CSV ------------------------------------------------------------------------


def test_a_date_with_no_time_is_written_as_a_plain_date_and_a_missing_one_as_empty() -> None:
    frame = pd.DataFrame({"k": ["x", "y"], "d": pd.to_datetime(["2024-01-05", None])})

    assert cleaned_csv_text(frame) == "k,d\nx,2024-01-05\ny,\n"


def test_a_date_with_a_time_is_written_in_full_iso_8601() -> None:
    frame = pd.DataFrame({"k": ["x", "y", "z"], "d": pd.Series([
        pd.Timestamp("2024-01-05 10:30:00"), pd.Timestamp("2024-01-05 00:00:00"),
        pd.Timestamp("2024-01-05 10:30:00.250")])})

    assert cleaned_csv_text(frame) == (
        "k,d\nx,2024-01-05T10:30:00.000000\ny,2024-01-05T00:00:00.000000\n"
        "z,2024-01-05T10:30:00.250000\n")


def test_a_column_of_whole_seconds_gets_no_fraction() -> None:
    frame = pd.DataFrame({"k": ["x"], "d": pd.to_datetime(["2024-01-05 10:30:00"])})

    assert cleaned_csv_text(frame) == "k,d\nx,2024-01-05T10:30:00\n"


def test_booleans_and_whole_numbers_keep_their_gaps() -> None:
    frame = pd.DataFrame({
        "flag": pd.array([True, None, False], dtype="boolean"),
        "n": pd.array([1, None, 3], dtype="Int64"),
    })

    assert cleaned_csv_text(frame) == "flag,n\nTrue,1\n,\nFalse,3\n"


def test_text_with_commas_quotes_newlines_and_accents_survives() -> None:
    frame = pd.DataFrame({"a": ['say "hi", ok', "two\nlines", "Café"], "b": ["1", "2", "3"]})

    text = cleaned_csv_text(frame)

    assert text == 'a,b\n"say ""hi"", ok",1\n"two\nlines",2\nCafé,3\n'
    assert pd.read_csv(StringIO(text), dtype=str)["a"].tolist() == frame["a"].tolist()


def test_lines_end_with_a_line_feed_only() -> None:
    assert "\r" not in cleaned_csv_text(pd.DataFrame({"a": ["1"], "b": ["2"]}))
