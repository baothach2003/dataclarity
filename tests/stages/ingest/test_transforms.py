"""The catalog actions that work on text: the dispatcher, the four
imputations, drop_rows_missing, the two structural actions and the three
text ones (docs/AI_PIPELINE.md sections 6 and 10). The typed, numeric and
flag actions are in test_transforms_values.py.

Every expectation is hand-calculated. Frames are built the way `read_csv_text`
leaves them: every value text, missing cells NaN.
"""

import pandas as pd
import pytest

from stages.ingest import transforms
from stages.ingest.transform_catalog import ALL_ACTIONS

NA = None


def column(*values: str | None) -> pd.Series:
    return pd.Series(list(values), dtype="str")


def frame(**columns: pd.Series) -> pd.DataFrame:
    return pd.DataFrame(columns)


# --- the dispatcher ---------------------------------------------------------


def test_every_catalog_action_has_a_function() -> None:
    assert set(transforms.ACTIONS) == ALL_ACTIONS


def test_an_action_outside_the_catalog_is_refused() -> None:
    with pytest.raises(ValueError, match="not in the transform catalog"):
        transforms.apply_action("delete_everything", frame(a=column("1")), "a", {})  # type: ignore[arg-type]  # the whitelist is what this checks


def test_the_input_frame_is_never_modified() -> None:
    before = frame(qty=column("1", NA, "3"), shop=column(" Cafe", "cafe", NA))
    copy = before.copy(deep=True)

    transforms.impute_median(before, "qty", {})
    transforms.trim_whitespace(before, "shop", {})
    transforms.drop_column(before, "shop", {})
    transforms.fix_negative(before, "qty", {})

    pd.testing.assert_frame_equal(before, copy)


# --- imputation -------------------------------------------------------------


def test_impute_median_fills_with_the_median_of_the_numbers() -> None:
    # Numbers present: 1, 3, 10 -> median 3.
    result, entry = transforms.impute_median(frame(qty=column("1", NA, "3", "10")), "qty", {})

    assert result["qty"].tolist() == ["1", 3.0, "3", "10"]
    assert (entry.cells_affected, entry.rows_affected) == (1, 0)
    assert entry.detail == "filled 1 missing cells with 3"
    assert entry.action == "impute_median" and entry.column == "qty"


def test_impute_mean_fills_with_the_mean_of_the_numbers() -> None:
    # (2 + 4 + 6) / 3 = 4.
    result, entry = transforms.impute_mean(frame(qty=column("2", "4", NA, "6")), "qty", {})

    assert result["qty"].tolist() == ["2", "4", 4.0, "6"]
    assert entry.cells_affected == 2 - 1 and entry.detail == "filled 1 missing cells with 4"


def test_impute_mode_fills_with_the_most_frequent_label() -> None:
    values = column("Cafe", "Bar", "Cafe", NA)

    result, entry = transforms.impute_mode(frame(shop=values), "shop", {})

    assert result["shop"].tolist() == ["Cafe", "Bar", "Cafe", "Cafe"]
    assert (entry.cells_affected, entry.detail) == (1, "filled 1 missing cells with Cafe")


def test_impute_mode_breaks_a_tie_alphabetically() -> None:
    # "Bar" and "Cafe" occur once each; pandas returns the modes sorted.
    result, _ = transforms.impute_mode(frame(shop=column("Cafe", "Bar", NA)), "shop", {})

    assert result["shop"].tolist()[2] == "Bar"


def test_impute_constant_fills_with_the_given_value() -> None:
    params = {"value": "Unknown"}

    result, entry = transforms.impute_constant(frame(shop=column("Cafe", NA, NA)), "shop", params)

    assert result["shop"].tolist() == ["Cafe", "Unknown", "Unknown"]
    assert (entry.cells_affected, entry.params) == (2, {"value": "Unknown"})


def test_impute_constant_without_a_value_is_refused() -> None:
    with pytest.raises(ValueError, match="needs a value param"):
        transforms.impute_constant(frame(shop=column(NA)), "shop", {})


def test_impute_constant_refuses_a_missing_value() -> None:
    with pytest.raises(ValueError, match="not missing"):
        transforms.impute_constant(frame(shop=column(NA)), "shop", {"value": None})


def test_drop_rows_missing_drops_the_rows_and_counts_them() -> None:
    data = frame(qty=column("1", NA, "3", NA), shop=column("a", "b", "c", "d"))

    result, entry = transforms.drop_rows_missing(data, "qty", {})

    assert result["qty"].tolist() == ["1", "3"]
    assert result["shop"].tolist() == ["a", "c"]  # the whole row goes
    assert (entry.cells_affected, entry.rows_affected) == (0, 2)


# --- structure --------------------------------------------------------------


def test_drop_column_removes_the_column_and_counts_its_cells() -> None:
    data = frame(qty=column("1", "2", "3"), note=column("x", NA, "z"))

    result, entry = transforms.drop_column(data, "note", {})

    assert list(result.columns) == ["qty"]
    assert (entry.cells_affected, entry.rows_affected) == (3, 0)
    assert entry.detail == "removed the column and its 3 cells"


def test_drop_column_refuses_a_column_that_is_not_there() -> None:
    with pytest.raises(ValueError, match="no such column"):
        transforms.drop_column(frame(qty=column("1")), "nope", {})


def test_remove_exact_duplicates_keeps_the_first_of_each_repeated_row() -> None:
    data = frame(a=column("1", "1", "2", "1"), b=column("x", "x", "y", "x"))

    result, entry = transforms.remove_exact_duplicates(data, None, {})

    assert result.index.tolist() == [0, 2]  # rows 1 and 3 repeat row 0
    assert (entry.rows_affected, entry.column) == (2, None)


def test_rows_equal_on_their_missing_cells_are_duplicates() -> None:
    data = frame(a=column("1", "1"), b=column(NA, NA))

    _, entry = transforms.remove_exact_duplicates(data, None, {})

    assert entry.rows_affected == 1


def test_a_dataset_action_refuses_a_column() -> None:
    with pytest.raises(ValueError, match="applies to the dataset"):
        transforms.remove_exact_duplicates(frame(a=column("1")), "a", {})


# --- text and categories ----------------------------------------------------


def test_trim_whitespace_strips_both_ends() -> None:
    values = column(" Cafe", "Bar ", " Tea ", "Deli", NA)

    result, entry = transforms.trim_whitespace(frame(shop=values), "shop", {})

    assert result["shop"].tolist()[:4] == ["Cafe", "Bar", "Tea", "Deli"]
    assert result["shop"].isna().tolist() == [False, False, False, False, True]
    assert entry.cells_affected == 3


def test_trim_whitespace_on_a_clean_column_is_still_logged() -> None:
    # Decided by Thach in 1D: an action that ran and changed nothing is a row
    # in the report, not a silent gap.
    result, entry = transforms.trim_whitespace(frame(shop=column("Cafe")), "shop", {})

    assert (entry.cells_affected, entry.rows_affected) == (0, 0)
    assert entry.action == "trim_whitespace"
    assert result["shop"].tolist() == ["Cafe"]


def test_trim_whitespace_cleans_a_padded_identifier() -> None:
    # Why identifier was added to the two string-shape actions (1D, Thach):
    # " A-1001 " and "A-1001" are the same SKU in every real system.
    data = frame(sku=column(" A-1001 ", "A-1002"))

    result, entry = transforms.trim_whitespace(data, "sku", {})

    assert result["sku"].tolist() == ["A-1001", "A-1002"]
    assert entry.cells_affected == 1


def test_normalize_case_cleans_a_mis_cased_identifier() -> None:
    data = frame(sku=column("ab-1", "AB-1"))

    result, entry = transforms.normalize_case(data, "sku", {"mode": "upper"})

    assert result["sku"].tolist() == ["AB-1", "AB-1"]
    assert entry.cells_affected == 1


def test_normalize_case_rewrites_only_the_cells_that_change() -> None:
    values = column("cafe bar", "Cafe Bar", "CAFE BAR", NA)

    result, entry = transforms.normalize_case(frame(shop=values), "shop", {"mode": "title"})

    assert result["shop"].tolist()[:3] == ["Cafe Bar", "Cafe Bar", "Cafe Bar"]
    assert entry.cells_affected == 2  # the already-title cell does not count


@pytest.mark.parametrize(
    ("mode", "expected"), [("lower", "cafe bar"), ("upper", "CAFE BAR"), ("title", "Cafe Bar")]
)
def test_normalize_case_modes(mode: str, expected: str) -> None:
    result, _ = transforms.normalize_case(frame(s=column("cAfE bAr")), "s", {"mode": mode})

    assert result["s"].tolist() == [expected]


def test_normalize_case_refuses_an_unknown_mode() -> None:
    with pytest.raises(ValueError, match="one of"):
        transforms.normalize_case(frame(s=column("a")), "s", {"mode": "sentence"})


def test_standardize_categories_merges_the_mapped_labels() -> None:
    values = column("cafe", "Cafe", "CAFE", "Bar", NA)
    params = {"mapping": {"cafe": "Cafe", "CAFE": "Cafe"}}

    result, entry = transforms.standardize_categories(frame(shop=values), "shop", params)

    assert result["shop"].tolist()[:4] == ["Cafe", "Cafe", "Cafe", "Bar"]
    assert entry.cells_affected == 2  # "Cafe" and "Bar" were already right
    assert entry.detail == "merged 2 cells into 1 labels"


def test_standardize_categories_leaves_unmapped_labels_alone() -> None:
    result, _ = transforms.standardize_categories(
        frame(s=column("Bar", NA)), "s", {"mapping": {"cafe": "Cafe"}}
    )

    assert result["s"].tolist()[0] == "Bar"
    assert result["s"].isna().tolist() == [False, True]


def test_standardize_categories_refuses_a_mapping_that_is_not_text_to_text() -> None:
    with pytest.raises(ValueError, match="mapping of text to text"):
        transforms.standardize_categories(frame(s=column("a")), "s", {"mapping": {"a": 1}})


# --- a cell of only spaces counts as missing here (decided by Thach in 1F) ---------------------
# A blank product name is no more a product name than an empty one, and trimming it
# (one action per column) would leave an empty cell in the file instead of dropping
# the row. Only this action reads it that way: profiling and the imputations still
# treat "missing" as the NA tokens.


def test_drop_rows_missing_also_drops_a_cell_of_only_spaces() -> None:
    data = frame(qty=column("1", "   ", NA, "3"), shop=column("a", "b", "c", "d"))

    result, entry = transforms.drop_rows_missing(data, "qty", {})

    assert result["qty"].tolist() == ["1", "3"]
    assert result["shop"].tolist() == ["a", "d"]  # the whole row goes
    assert (entry.cells_affected, entry.rows_affected) == (0, 2)
    assert entry.detail == "dropped 2 rows with no qty (1 of them only spaces)"


def test_every_kind_of_whitespace_counts_as_blank() -> None:
    data = frame(name=column("\t", " \n ", "\u00a0", "\u2003 ", "x"))

    result, entry = transforms.drop_rows_missing(data, "name", {})

    assert result["name"].tolist() == ["x"]
    assert entry.rows_affected == 4


def test_a_cell_with_spaces_around_a_value_is_not_blank() -> None:
    data = frame(name=column(" Mug ", "Cup", "  a b  "))

    result, entry = transforms.drop_rows_missing(data, "name", {})

    assert result["name"].tolist() == [" Mug ", "Cup", "  a b  "]  # left for trim_whitespace
    assert entry.rows_affected == 0


def test_the_detail_is_unchanged_when_no_cell_is_blank() -> None:
    _, entry = transforms.drop_rows_missing(frame(qty=column("1", NA, "3")), "qty", {})

    assert entry.detail == "dropped 1 rows with no qty"


def test_numbers_and_dates_are_never_mistaken_for_blank() -> None:
    # After parse_datetime or a cast the column is not text any more.
    data = pd.DataFrame({
        "day": pd.to_datetime(["2024-01-05", None]),
        "n": pd.array([1, None], dtype="Int64"),
        "f": [1.5, None],
        "b": pd.array([True, None], dtype="boolean"),
    })

    for name in data.columns:
        result, entry = transforms.drop_rows_missing(data, name, {})
        assert (len(result), entry.rows_affected) == (1, 1), name
        assert "only spaces" not in entry.detail


def test_a_whole_column_of_blanks_drops_every_row_and_an_empty_frame_is_fine() -> None:
    result, entry = transforms.drop_rows_missing(frame(qty=column(" ", "  ")), "qty", {})

    assert (len(result), entry.rows_affected) == (0, 2)
    empty, entry = transforms.drop_rows_missing(frame(qty=column()), "qty", {})
    assert (len(empty), entry.rows_affected) == (0, 0)
