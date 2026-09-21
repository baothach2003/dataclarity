"""Detectors shared by the transforms, the issue counts and the sample rows
(stages/ingest/column_kinds.py). Every expectation is hand-calculated."""

from typing import Any

import pandas as pd
import pytest

from stages.ingest.column_kinds import (
    Offsets,
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


# --- cells written with different UTC offsets (found in 1E) -----------------
# pandas refuses one column of mixed offsets even with errors="coerce", which
# used to crash the sample rows, the issue counts and parse_datetime.


MIXED_OFFSETS = column("2024-01-05T10:00:00Z", "2024-01-05 10:00:00+01:00", "not a date")


def test_dates_with_different_utc_offsets_parse_instead_of_raising() -> None:
    parsed = as_dates(MIXED_OFFSETS)

    # Both offsets are read: 10:00 UTC and 10:00 at +01:00 (= 09:00 UTC).
    assert parsed.notna().tolist() == [True, True, False]
    assert parsed.iloc[0].hour == 10 and parsed.iloc[1].hour == 9


def test_a_column_of_mixed_offsets_is_mostly_dates_and_the_text_is_the_invalid_cell() -> None:
    assert is_mostly_dates(MIXED_OFFSETS)
    assert invalid_date_mask(MIXED_OFFSETS).tolist() == [False, False, True]


def test_an_explicit_format_with_offsets_survives_too() -> None:
    offsets = column("2024-01-05 10:00 +0100", "2024-01-05 10:00 +0000")

    parsed = as_dates(offsets, "%Y-%m-%d %H:%M %z")

    assert parsed.notna().all()


def test_a_malformed_format_is_still_an_error_not_a_silent_utc_retry() -> None:
    with pytest.raises(ValueError, match="bad directive"):
        as_dates(column("2024-01-05"), "%Y-%m-%d %Q")


def test_mixed_offsets_can_be_refused_outright() -> None:
    with pytest.raises(ValueError, match="Mixed timezones"):
        as_dates(MIXED_OFFSETS, offsets="raise")


# --- offsets: UTC for detectors, wall-clock for what is written (decided by Thach in 1F) ---
# Reading "2024-01-06 01:00+10:00" as UTC gives 2024-01-05 15:00: the transaction
# date moves back a day. A store's own date, as written, is what a report by day
# needs, so a caller that writes dates into the data drops the offset instead.

SHIFTED = column("2024-01-06 01:00:00+10:00", "2024-01-05 10:00:00-05:00")


def test_a_detector_reads_offsets_as_utc_by_default() -> None:
    assert as_dates(SHIFTED).iloc[0].day == 5  # the shift wall-clock mode exists to avoid


def test_wall_clock_keeps_the_date_and_time_as_written() -> None:
    parsed = as_dates(SHIFTED, offsets="wall_clock")

    assert parsed.tolist() == [pd.Timestamp("2024-01-06 01:00"), pd.Timestamp("2024-01-05 10:00")]
    assert parsed.dt.tz is None


def test_wall_clock_reads_z_fractions_and_a_bad_cell_next_to_each_other() -> None:
    cells = column("2024-01-05T10:00:00Z", "2024-01-05 10:00:00.250+01:00", "2024-01-05 10:00-0500",
                   "not a date", NA)

    parsed = as_dates(cells, offsets="wall_clock")

    assert parsed.iloc[0] == pd.Timestamp("2024-01-05 10:00:00")
    assert parsed.iloc[1] == pd.Timestamp("2024-01-05 10:00:00.250")
    assert parsed.iloc[2] == pd.Timestamp("2024-01-05 10:00:00")
    assert parsed.isna().tolist() == [False, False, False, True, True]


def test_wall_clock_on_one_shared_offset_also_drops_the_zone() -> None:
    parsed = as_dates(column("2024-01-05 10:00+01:00", "2024-01-06 11:30+01:00"), offsets="wall_clock")

    assert parsed.dt.tz is None
    assert parsed.tolist() == [pd.Timestamp("2024-01-05 10:00"), pd.Timestamp("2024-01-06 11:30")]


def test_wall_clock_never_eats_the_day_of_a_plain_date() -> None:
    # "-05" at the end of "2024-01-05" looks like an offset and is not one.
    plain = column("2024-01-05", "2024-03-04", "05/01/2024")

    assert as_dates(plain, offsets="wall_clock").tolist() == as_dates(plain).tolist()


def test_wall_clock_with_an_explicit_format_that_has_an_offset() -> None:
    cells = column("2024-01-05 10:00 +0100", "2024-01-05 10:00 +0000")

    parsed = as_dates(cells, "%Y-%m-%d %H:%M %z", offsets="wall_clock")

    assert parsed.tolist() == [pd.Timestamp("2024-01-05 10:00")] * 2


def test_has_utc_offset_finds_offsets_and_only_offsets() -> None:
    from stages.ingest.column_kinds import has_utc_offset

    assert has_utc_offset(column("2024-01-05 10:00+01:00"))
    assert has_utc_offset(column("2024-01-05T10:00:00Z"))
    assert has_utc_offset(column("2024-01-05 10:00:00.5-0500"))
    assert not has_utc_offset(column("2024-01-05", "05/01/2024 10:00", "2024-01-05 10:00:00", NA))


def test_parse_datetime_keeps_the_written_date_and_says_so() -> None:
    from stages.ingest import transforms

    result, entry = transforms.apply_action("parse_datetime", SHIFTED.to_frame("d"), "d", {})

    assert result["d"].tolist() == [pd.Timestamp("2024-01-06 01:00"), pd.Timestamp("2024-01-05 10:00")]
    assert "UTC offsets dropped" in entry.detail
    assert (entry.cells_affected, entry.rows_affected) == (2, 0)


def test_parse_datetime_does_not_mention_offsets_when_there_are_none() -> None:
    from stages.ingest import transforms

    _, entry = transforms.apply_action("parse_datetime", column("2024-01-05").to_frame("d"), "d", {})

    assert "offset" not in entry.detail


# --- what is not a date (found in the 1F review) ---------------------------------------------
# pandas reads "now" as the moment the run happens, "10:30" as 10:30 today and "Jan 5"
# as the year 1: the same plan on the same file gave a different cleaned.csv every
# run, or a date no report could use, with nothing flagged.

MODES = ["utc", "wall_clock"]


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize(
    "cell",
    ["now", "today", "Now", "TODAY", " now ", "10:30", "00:00", "10:30:15", "10:30:15.5", "9:05", "10:30 pm"],
)
def test_a_cell_with_no_date_in_it_is_not_a_date(cell: str, mode: Offsets) -> None:
    parsed = as_dates(column(cell, "2024-01-05"), offsets=mode)

    assert parsed.isna().tolist() == [True, False]


@pytest.mark.parametrize("cell", ["Jan 5", "5 Jan", "12/31", "1/2"])
def test_a_date_with_no_year_is_not_a_date(cell: str) -> None:
    assert as_dates(column(cell, "2024-01-05")).isna().tolist() == [True, False]


@pytest.mark.parametrize("cell", ["1850-01-01", "2150-01-01", "0099-01-05", "0001-01-01"])
def test_a_year_outside_1900_to_2100_is_not_a_date(cell: str) -> None:
    assert as_dates(column(cell, "2024-01-05")).isna().tolist() == [True, False]


def test_the_first_and_last_day_of_the_range_are_dates() -> None:
    parsed = as_dates(column("1900-01-01", "2100-12-31"))

    assert parsed.notna().all()


def test_a_detector_agrees_with_the_transform_that_these_are_invalid() -> None:
    assert invalid_date_mask(column("2024-01-05", "now", "10:30", "Jan 5")).tolist() == [
        False, True, True, True]


def test_the_same_column_read_twice_gives_the_same_dates() -> None:
    cells = column("2024-01-05", "now", "today", "10:30")

    assert as_dates(cells).equals(as_dates(cells))


# --- offsets written the way people write them ------------------------------------------------------


@pytest.mark.parametrize(
    "cells",
    [
        ["2024-01-06 01:00 +10", "2024-01-05 10:30 -5"],
        ["2024-01-06 01:00 UTC", "2024-01-05 10:30 +01:00"],
        ["2024-01-06 01:00 GMT+2", "2024-01-05 10:30Z"],
        ["2024-01-06 01:00 +05", "2024-01-05 10:30 -0530"],
        ["2024-01-06 01:00 UTC+1", "2024-01-05 10:30 GMT"],
    ],
    ids=["hour-only", "utc-word", "gmt-plus", "short-and-long", "utc-plus"],
)
def test_common_offset_forms_are_dropped_and_the_date_kept(cells: list[str]) -> None:
    parsed = as_dates(column(*cells), offsets="wall_clock")

    assert parsed.tolist() == [pd.Timestamp("2024-01-06 01:00"), pd.Timestamp("2024-01-05 10:30")]


def test_has_utc_offset_knows_the_same_forms() -> None:
    from stages.ingest.column_kinds import has_utc_offset

    for cell in ("2024-01-06 01:00 +10", "2024-01-05 10:30 -5", "2024-01-06 01:00 UTC",
                 "2024-01-06 01:00 GMT+2"):
        assert has_utc_offset(column(cell)), cell


def test_a_time_followed_by_text_that_is_not_an_offset_is_left_alone() -> None:
    from stages.ingest.column_kinds import has_utc_offset

    assert not has_utc_offset(column("2024-01-05 10:30 PM", "2024-01-05 10:30 sharp"))


# --- the change log only claims what happened ----------------------------------------------------------


def test_offsets_are_not_reported_dropped_when_a_format_made_every_offset_cell_fail() -> None:
    from stages.ingest import transforms

    cells = column("2024-01-05 10:30+10:00", "2024-01-06 01:00-05:00").to_frame("d")

    result, entry = transforms.apply_action("parse_datetime", cells, "d", {"format": "%Y-%m-%d %H:%M"})

    assert result["d"].isna().all() and entry.rows_affected == 2  # both flagged
    assert "offset" not in entry.detail


def test_offsets_are_reported_dropped_when_the_format_reads_them() -> None:
    from stages.ingest import transforms

    cells = column("2024-01-05 10:30 +1000", "2024-01-06 01:00 -0500").to_frame("d")

    _, entry = transforms.apply_action("parse_datetime", cells, "d", {"format": "%Y-%m-%d %H:%M %z"})

    assert "UTC offsets dropped" in entry.detail


# --- a column of words is not converted to dates (1F review: 400 columns cost seconds) ---------


def test_a_column_with_no_digit_in_it_is_never_tried_as_dates(monkeypatch: pytest.MonkeyPatch) -> None:
    # Every date has a digit. Converting 500 words to dates takes 5 ms on pandas'
    # slow path, per column, and a wide file has hundreds of columns.
    from stages.ingest import column_kinds

    tried: list[int] = []
    real = column_kinds.as_dates

    def spy(values: pd.Series, *args: object, **kwargs: Any) -> pd.Series:
        tried.append(len(values))
        return real(values, *args, **kwargs)

    monkeypatch.setattr(column_kinds, "as_dates", spy)

    assert column_kinds.probably_dates(column(*["apple", "pear", "plum"] * 200)) is False
    assert tried == []


def test_a_column_of_dates_and_a_column_with_digits_are_still_probed() -> None:
    from stages.ingest.column_kinds import probably_dates

    assert probably_dates(column(*["2024-01-05"] * 50)) is True
    assert probably_dates(column(*["Item 5", "Item 6"] * 50)) is False  # probed, and not dates
    assert probably_dates(column(*[None, None, "2024-01-05"] * 40)) is True  # gaps do not hide a date


def test_a_date_after_many_words_is_still_found_when_it_is_in_the_first_hundred_cells() -> None:
    from stages.ingest.column_kinds import probably_dates

    assert probably_dates(column(*["n/a"] * 3, *["2024-01-05"] * 200)) is True
