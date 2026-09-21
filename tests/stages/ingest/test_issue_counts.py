"""Pandas counts for the issue codes the profile holds no figure for
(stages/ingest/issue_counts.py, PROJECT_PLAN 1D). Every count is hand-checked.
"""

from typing import get_args

import pandas as pd
import pytest

from contracts.profile import IssueCode
from stages.ingest import column_kinds
from stages.ingest.issue_counts import (
    COMPUTED_COLUMN_CODES,
    COMPUTED_DATASET_CODES,
    PROFILED_CODES,
    count_column_issue,
    count_column_issues,
    count_duplicate_business_key,
)

NA = None


def column(*values: str | None) -> pd.Series:
    return pd.Series(list(values), dtype="str")


EMPTY = column()
ALL_NULL = column(NA, NA, NA)
EVERY_CODE = sorted(COMPUTED_COLUMN_CODES)


# --- coverage of the enum ---------------------------------------------------


def test_every_issue_code_has_a_source_for_its_count() -> None:
    covered = PROFILED_CODES | COMPUTED_COLUMN_CODES | COMPUTED_DATASET_CODES

    assert covered == set(get_args(IssueCode))


def test_the_three_groups_do_not_overlap() -> None:
    assert not PROFILED_CODES & COMPUTED_COLUMN_CODES
    assert not COMPUTED_DATASET_CODES & (PROFILED_CODES | COMPUTED_COLUMN_CODES)


@pytest.mark.parametrize("code", sorted(PROFILED_CODES))
def test_a_code_the_profile_measures_is_refused_here(code: IssueCode) -> None:
    # 1C checks these against profile.json; computing them again here would be
    # a second source of truth for the same number.
    with pytest.raises(KeyError, match="not computed here"):
        count_column_issue(code, column("1"))


# --- numbers ----------------------------------------------------------------


def test_negative_values_counts_the_numbers_below_zero() -> None:
    values = column("5", "-3", "0", "-0.5", "abc", NA)

    assert count_column_issue("negative_values", values) == 2


def test_zero_values_counts_every_spelling_of_zero() -> None:
    values = column("0", "0.0", "-0", "1", NA)

    assert count_column_issue("zero_values", values) == 3


def test_outliers_iqr_counts_the_values_outside_the_fence() -> None:
    # [1, 2, 3, 100]: fence [-36.5, 65.5] (see test_column_kinds).
    assert count_column_issue("outliers_iqr", column("1", "2", "3", "100")) == 1


def test_a_constant_numeric_column_has_no_outliers() -> None:
    # IQR 0: the fence collapses onto the value, and nothing is outside it.
    assert count_column_issue("outliers_iqr", column("5", "5", "5")) == 0


def test_non_numeric_in_numeric_counts_the_text_in_a_numeric_column() -> None:
    # 3 of 4 present values are numbers, so the column is numeric and "n/a" is
    # the problem.
    assert count_column_issue("non_numeric_in_numeric", column("1", "2", "3", "n/a", NA)) == 1


def test_a_text_column_is_not_a_numeric_column_with_a_problem() -> None:
    assert count_column_issue("non_numeric_in_numeric", column("Cafe", "Bar", "12")) == 0


def test_mixed_types_counts_the_minority_kind_from_either_side() -> None:
    assert count_column_issue("mixed_types", column("1", "2", "3", "n/a")) == 1
    assert count_column_issue("mixed_types", column("Cafe", "Bar", "Deli", "12")) == 1


def test_one_kind_only_is_not_a_mixture() -> None:
    assert count_column_issue("mixed_types", column("1", "2", NA)) == 0
    assert count_column_issue("mixed_types", column("Cafe", "Bar")) == 0


# --- text -------------------------------------------------------------------


def test_trailing_whitespace_counts_both_ends() -> None:
    assert count_column_issue("trailing_whitespace", column(" a", "b ", " c ", "d", NA)) == 3


def test_inconsistent_case_counts_the_cells_that_are_not_the_dominant_spelling() -> None:
    values = column("Cafe", "Cafe", "cafe", "CAFE", "Bar")

    assert count_column_issue("inconsistent_case", values) == 2


def test_near_duplicate_labels_ignores_punctuation_and_spacing() -> None:
    values = column("Coca Cola", "Coca Cola", "coca-cola", "Bar")

    assert count_column_issue("near_duplicate_labels", values) == 1


def test_near_duplicate_labels_does_not_count_a_case_difference_twice() -> None:
    # "cafe" is already `inconsistent_case`; the two codes stay disjoint.
    values = column("Cafe", "Cafe", "cafe")

    assert count_column_issue("near_duplicate_labels", values) == 0
    assert count_column_issue("inconsistent_case", values) == 1


def test_constant_column_counts_every_cell_holding_the_one_value() -> None:
    assert count_column_issue("constant_column", column("x", "x", "x", NA)) == 3
    assert count_column_issue("constant_column", column("x", "y")) == 0


# --- dates ------------------------------------------------------------------


def test_invalid_dates_counts_the_cells_that_do_not_parse() -> None:
    values = column("2024-01-05", "2024-01-06", "2024-01-07", "not a date", NA)

    assert count_column_issue("invalid_dates", values) == 1


def test_a_column_that_is_not_dates_has_no_invalid_dates() -> None:
    # Otherwise every product name column would report its whole length.
    assert count_column_issue("invalid_dates", column("Cafe", "Bar", "2024-01-05")) == 0


def test_mixed_date_formats_counts_the_cells_outside_the_common_format() -> None:
    values = column("2024-01-05", "2024-01-06", "2024-01-07", "05/06/2024")

    assert count_column_issue("mixed_date_formats", values) == 1


def test_one_date_format_is_not_a_mixture() -> None:
    assert count_column_issue("mixed_date_formats", column("2024-01-05", "2024-01-06")) == 0


# --- the whole column at once -----------------------------------------------


def test_count_column_issues_reports_only_what_it_found() -> None:
    values = column("1", "0", "-2", "n/a", NA)

    assert count_column_issues(values) == {
        "mixed_types": 1,           # "n/a" among three numbers
        "negative_values": 1,       # -2
        "non_numeric_in_numeric": 1,
        "zero_values": 1,           # 0
    }


def test_a_clean_column_reports_nothing() -> None:
    assert count_column_issues(column("1", "2", "3")) == {}


# --- duplicate business key -------------------------------------------------


def test_duplicate_business_key_marks_every_row_of_a_collision() -> None:
    frame = pd.DataFrame({"sku": column("A", "B", "A", "C"), "day": column("1", "2", "1", "3")})

    assert count_duplicate_business_key(frame, ["sku", "day"]) == 2


def test_the_whole_key_decides_a_collision() -> None:
    frame = pd.DataFrame({"sku": column("A", "A"), "day": column("1", "2")})

    assert count_duplicate_business_key(frame, ["sku", "day"]) == 0
    assert count_duplicate_business_key(frame, ["sku"]) == 2


def test_a_file_without_a_key_has_no_key_collisions() -> None:
    frame = pd.DataFrame({"sku": column("A", "A")})

    assert count_duplicate_business_key(frame, []) == 0
    assert count_duplicate_business_key(frame, ["not a column"]) == 0


# --- edge cases (CLAUDE.md section 5) ---------------------------------------


@pytest.mark.parametrize("code", EVERY_CODE)
def test_an_empty_column_counts_zero(code: IssueCode) -> None:
    assert count_column_issue(code, EMPTY) == 0


@pytest.mark.parametrize("code", EVERY_CODE)
def test_an_all_null_column_counts_zero(code: IssueCode) -> None:
    # Its one issue is all_null_column, which the profile already measures.
    assert count_column_issue(code, ALL_NULL) == 0


@pytest.mark.parametrize("code", EVERY_CODE)
def test_a_single_row_counts_at_most_itself(code: IssueCode) -> None:
    assert count_column_issue(code, column("5")) <= 1


@pytest.mark.parametrize("code", EVERY_CODE)
def test_a_zero_variance_column_needs_no_denominator(code: IssueCode) -> None:
    # The IQR is 0 here; nothing may divide by it.
    counted = count_column_issue(code, column("5", "5", "5", "5"))

    assert counted == (4 if code == "constant_column" else 0)


def test_an_empty_frame_has_no_key_collisions() -> None:
    empty = pd.DataFrame({"sku": EMPTY})

    assert count_duplicate_business_key(empty, ["sku"]) == 0


# --- cost: a column is probed before it is converted in full (1E review) ------


def test_a_text_column_is_never_converted_to_dates_in_full(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # 2,000 product names. Converting them all as dates cost about 4 s per 200k
    # rows per code, and the AI may list a date code on any column.
    seen: list[int] = []
    real = column_kinds.as_dates

    def spy(values: pd.Series, date_format: str | None = None, dayfirst: bool = False) -> pd.Series:
        seen.append(len(values))
        return real(values, date_format, dayfirst)

    monkeypatch.setattr(column_kinds, "as_dates", spy)
    names = column(*[f"Product {i}" for i in range(2000)])

    assert count_column_issue("invalid_dates", names) == 0
    assert count_column_issue("mixed_date_formats", names) == 0
    assert max(seen) <= column_kinds.PROBE_ROWS


def test_a_date_column_still_gets_its_full_count_after_the_probe() -> None:
    dates = column(*["2024-01-05"] * 600, "not a date", "never")

    assert count_column_issue("invalid_dates", dates) == 2


def test_a_column_whose_first_rows_are_not_dates_counts_zero_even_if_later_ones_are() -> None:
    # The accepted cost of probing (the same trade-off as profiling's numeric
    # probe): a column that only turns into dates after PROBE_ROWS rows is
    # treated as text, so it reports no date issue.
    late = column(*["free text"] * column_kinds.PROBE_ROWS, *["2024-01-05"] * 1500)

    assert count_column_issue("invalid_dates", late) == 0


def test_dates_written_with_different_utc_offsets_are_counted_not_a_crash() -> None:
    offsets = column("2024-01-05T10:00:00Z", "2024-01-05 10:00:00+01:00", "later")

    assert count_column_issue("invalid_dates", offsets) == 1
    assert count_column_issue("mixed_date_formats", offsets) >= 0


# --- labels with no letters or digits (found in the 1E review) ------------------


@pytest.mark.parametrize(
    "labels",
    [["$", "€", "$"], ["+", "-", "+", "-", "-"], ["😀", "😂", "😀"], ["#", "%", "&"]],
    ids=["currencies", "signs", "emoji", "symbols"],
)
def test_labels_made_only_of_punctuation_are_not_each_others_near_duplicates(
    labels: list[str],
) -> None:
    # Ignoring punctuation turned every one of these into the empty string, and
    # the empty string is a group of its own: "$" and "€" became "duplicates".
    assert count_column_issue("near_duplicate_labels", column(*labels)) == 0


def test_the_documented_punctuation_rule_still_holds_for_real_labels() -> None:
    assert count_column_issue("near_duplicate_labels", column("Coca-Cola", "coca cola")) == 1


# --- what counts as punctuation (cycle-3 review) -----------------------------------


def _nfd(*labels: str) -> pd.Series:
    import unicodedata

    return column(*[unicodedata.normalize("NFD", label) for label in labels])


def test_accents_written_as_combining_marks_are_part_of_the_word_not_punctuation() -> None:
    # "ma", "ma" + acute, ... are four different Vietnamese words. Decomposed
    # (what a macOS export writes), the accent is a combining mark, which the
    # old `\w` pattern deleted: all four became "ma".
    assert count_column_issue("near_duplicate_labels", _nfd("ma", "má", "mà", "mã")) == 0


def test_indic_and_thai_marks_are_not_punctuation_either() -> None:
    assert count_column_issue("near_duplicate_labels", column("कि", "की", "को", "के")) == 0
    assert count_column_issue("near_duplicate_labels", column("ที่", "ทื่")) == 0


def test_the_same_word_in_two_unicode_forms_is_a_near_duplicate() -> None:
    import unicodedata

    composed = "má"
    decomposed = unicodedata.normalize("NFD", composed)

    assert count_column_issue("near_duplicate_labels", column(composed, composed, decomposed)) == 1


def test_an_underscore_is_punctuation_like_a_hyphen() -> None:
    assert count_column_issue(
        "near_duplicate_labels", column("Wireless_Mouse", "Wireless Mouse")) == 1


def test_labels_of_nothing_but_separators_stay_apart() -> None:
    assert count_column_issue("near_duplicate_labels", column("_", "-_", "--")) == 0
