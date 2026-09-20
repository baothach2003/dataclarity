"""Detectors shared by the transforms, the issue counts and the sample rows
(stages/ingest/column_kinds.py). Every expectation is hand-calculated."""

import pandas as pd

from stages.ingest.column_kinds import (
    as_dates,
    as_numbers,
    case_variant_mask,
    date_format_labels,
    dominant_spelling,
    invalid_date_mask,
    iqr_bounds,
    is_mostly_dates,
    is_mostly_numeric,
    non_numeric_mask,
    outlier_mask,
    share,
    whitespace_mask,
)

NA = None  # a missing cell, as read_csv_text leaves it


def column(*values: str | None) -> pd.Series:
    return pd.Series(list(values), dtype="str")


EMPTY = pd.Series([], dtype="str")


# --- numbers ----------------------------------------------------------------


def test_numbers_convert_and_text_becomes_nan() -> None:
    numbers = as_numbers(column("1", "2.5", "-3", "abc", NA))

    assert numbers.tolist()[:3] == [1.0, 2.5, -3.0]
    assert numbers.isna().tolist() == [False, False, False, True, True]


def test_non_numeric_mask_excludes_missing_cells() -> None:
    assert non_numeric_mask(column("1", "abc", NA)).tolist() == [False, True, False]


def test_a_column_is_mostly_numeric_above_half_of_its_present_values() -> None:
    # 2 of 3 present values are numbers (the missing cell does not count).
    assert is_mostly_numeric(column("1", "2", "abc", NA)) is True
    # 2 of 4: exactly half is not a majority.
    assert is_mostly_numeric(column("1", "2", "abc", "def")) is False


def test_share_of_an_empty_column_is_zero_not_a_division_by_zero() -> None:
    assert share(non_numeric_mask(EMPTY), EMPTY) == 0.0
    assert is_mostly_numeric(EMPTY) is False


def test_share_of_an_all_null_column_is_zero() -> None:
    all_null = column(NA, NA)

    assert share(non_numeric_mask(all_null), all_null) == 0.0


# --- dates ------------------------------------------------------------------


def test_dates_parse_per_cell_and_unparseable_cells_become_nat() -> None:
    dates = as_dates(column("2024-01-05", "Feb 1, 2024", "nope", NA))

    assert [None if pd.isna(d) else d.date().isoformat() for d in dates] == [
        "2024-01-05", "2024-02-01", None, None,
    ]


def test_dayfirst_decides_an_ambiguous_date() -> None:
    assert as_dates(column("05/06/2024"), dayfirst=True)[0].date().isoformat() == "2024-06-05"
    assert as_dates(column("05/06/2024"), dayfirst=False)[0].date().isoformat() == "2024-05-06"


def test_an_explicit_format_rejects_everything_else() -> None:
    dates = as_dates(column("2024-01-05", "05/06/2024"), date_format="%Y-%m-%d")

    assert dates.isna().tolist() == [False, True]


def test_invalid_date_mask_excludes_missing_cells() -> None:
    assert invalid_date_mask(column("2024-01-05", "nope", NA)).tolist() == [False, True, False]


def test_a_column_is_mostly_dates_above_half_of_its_present_values() -> None:
    assert is_mostly_dates(column("2024-01-05", "2024-01-06", "nope")) is True
    assert is_mostly_dates(column("2024-01-05", "nope", "also nope")) is False


def test_date_format_labels_name_the_written_shape() -> None:
    labels = date_format_labels(
        column("2024-01-05", "05/06/2024", "Feb 1, 2024", "2024-01-05 10:30:00", "nope", NA)
    )

    # A time part does not change the date's format; a non-date has no label.
    assert labels.tolist()[:4] == ["iso", "slash", "month_name", "iso"]
    assert labels.isna().tolist() == [False, False, False, False, True, True]


# --- whitespace and case ----------------------------------------------------


def test_whitespace_mask_finds_leading_and_trailing_space() -> None:
    values = column(" a", "b ", " c ", "d", "e f", NA)

    assert whitespace_mask(values).tolist() == [True, True, True, False, False, False]


def test_dominant_spelling_picks_the_most_frequent_of_a_folded_label() -> None:
    assert dominant_spelling(column("Cafe", "cafe", "CAFE", "Cafe")) == {"cafe": "Cafe"}


def test_dominant_spelling_breaks_a_tie_alphabetically() -> None:
    # "CAFE" and "cafe" occur once each; "CAFE" sorts first.
    assert dominant_spelling(column("cafe", "CAFE")) == {"cafe": "CAFE"}


def test_case_variants_are_the_cells_that_are_not_the_dominant_spelling() -> None:
    values = column("Cafe", "cafe", "CAFE", "Cafe", NA)

    assert case_variant_mask(values).tolist() == [False, True, True, False, False]


def test_case_variants_are_counted_per_label_not_per_column() -> None:
    values = column("Cafe", "Cafe", "cafe", "Bar", "BAR", "Bar", "Bar")

    # One stray "cafe" and one stray "BAR".
    assert case_variant_mask(values).tolist() == [False, False, True, False, True, False, False]


# --- IQR --------------------------------------------------------------------


def test_iqr_bounds_are_hand_calculated() -> None:
    # [1, 2, 3, 100]: q1 = 1 + 0.75 * (2 - 1) = 1.75, q3 = 3 + 0.25 * (100 - 3)
    # = 27.25, IQR = 25.5, fence = 1.5 * 25.5 = 38.25.
    assert iqr_bounds(column("1", "2", "3", "100")) == (-36.5, 65.5)
    assert outlier_mask(column("1", "2", "3", "100")).tolist() == [False, False, False, True]


def test_a_smaller_k_makes_the_fence_tighter() -> None:
    # Same quartiles, fence = 1.0 * 25.5: [1.75 - 25.5, 27.25 + 25.5].
    assert iqr_bounds(column("1", "2", "3", "100"), k=1.0) == (-23.75, 52.75)


def test_a_constant_column_has_a_zero_width_fence_and_no_outliers() -> None:
    # Zero variance: q1 = q3 = 5, IQR = 0. Nothing lies outside [5, 5].
    assert iqr_bounds(column("5", "5", "5")) == (5.0, 5.0)
    assert outlier_mask(column("5", "5", "5")).tolist() == [False, False, False]


def test_a_zero_width_fence_still_marks_a_different_value() -> None:
    # [1, 1, 1, 1, 9]: q1 = q3 = 1, so 9 is outside [1, 1].
    assert outlier_mask(column("1", "1", "1", "1", "9")).tolist()[-1] is True


def test_a_column_with_no_numbers_has_no_bounds_and_no_outliers() -> None:
    assert iqr_bounds(column("abc", NA)) is None
    assert outlier_mask(column("abc", NA)).tolist() == [False, False]


def test_a_single_row_is_its_own_quartiles() -> None:
    assert iqr_bounds(column("7")) == (7.0, 7.0)
    assert outlier_mask(column("7")).tolist() == [False]


# --- empty dataframe column -------------------------------------------------


def test_every_detector_survives_an_empty_column() -> None:
    assert as_numbers(EMPTY).empty
    assert as_dates(EMPTY).empty
    assert whitespace_mask(EMPTY).empty
    assert case_variant_mask(EMPTY).empty
    assert outlier_mask(EMPTY).empty
    assert date_format_labels(EMPTY).empty
    assert iqr_bounds(EMPTY) is None
