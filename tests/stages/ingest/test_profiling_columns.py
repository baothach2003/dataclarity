import pandas as pd
import pytest

from stages.ingest.profiling import profile_column

NA = None  # a missing cell, as read_csv_text leaves it


def column(*values: str | None) -> pd.Series:
    return pd.Series(list(values), dtype="str")


# --- numeric statistics (hand-checked; quartiles use linear interpolation) ------


def test_numeric_column_one_to_ten() -> None:
    profile = profile_column("qty", column(*[str(i) for i in range(1, 11)]))

    assert profile.dtype == "int64"
    assert (profile.min, profile.max) == (1.0, 10.0)
    assert profile.mean == 5.5            # 55 / 10
    assert profile.median == 5.5          # position 4.5: 5 + 0.5 * (6 - 5)
    assert profile.q1 == 3.25             # position 2.25: 3 + 0.25 * (4 - 3)
    assert profile.q3 == 7.75             # position 6.75: 7 + 0.75 * (8 - 7)
    assert (profile.null_count, profile.null_pct, profile.unique_count) == (0, 0.0, 10)


def test_numeric_column_with_missing_values() -> None:
    profile = profile_column("price", column("4", NA, "1", "10", NA))

    # Numbers present: 1, 4, 10. pandas types a numeric column with gaps as float64.
    assert profile.dtype == "float64"
    assert profile.null_count == 2
    assert profile.null_pct == 40.0       # 2 of 5
    assert profile.mean == 5.0            # 15 / 3
    assert profile.median == 4.0          # position 1.0
    assert profile.q1 == 2.5              # position 0.5: 1 + 0.5 * (4 - 1)
    assert profile.q3 == 7.0              # position 1.5: 4 + 0.5 * (10 - 4)


def test_negative_and_decimal_values_are_numeric() -> None:
    profile = profile_column("unit_price", column("9.99", "12.50", "-3.50"))

    assert profile.dtype == "float64"
    assert profile.min == -3.5
    assert profile.max == 12.5
    assert profile.median == 9.99


def test_single_row_numeric_column() -> None:
    profile = profile_column("qty", column("5"))

    assert profile.dtype == "int64"
    assert [profile.min, profile.max, profile.mean, profile.median, profile.q1, profile.q3] == [5.0] * 6


def test_all_null_column_has_no_statistics() -> None:
    profile = profile_column("note", column(NA, NA, NA))

    assert profile.dtype == "str"
    assert (profile.null_count, profile.null_pct, profile.unique_count) == (3, 100.0, 0)
    assert [profile.min, profile.max, profile.mean, profile.median, profile.q1, profile.q3] == [None] * 6
    assert profile.top_values == []
    assert profile.sample_values == [None, None, None]


def test_mixed_type_column_is_text_without_statistics() -> None:
    profile = profile_column("qty", column("12", "abc", "7"))

    assert profile.dtype == "str"
    assert profile.mean is None and profile.median is None
    assert profile.unique_count == 3


def test_infinity_makes_a_column_non_numeric() -> None:
    # inf cannot round-trip through JSON, and is never a real quantity or price.
    profile = profile_column("price", column("1.5", "inf"))

    assert profile.dtype == "str"
    assert profile.max is None


def test_unique_count_compares_raw_text() -> None:
    # "8.5" and "8.50" are one number but two spellings in the file.
    profile = profile_column("price", column("8.5", "8.50", "8.5"))

    assert profile.unique_count == 2
    assert profile.median == 8.5


# --- top values -----------------------------------------------------------------


def test_top_values_sorted_by_count_then_value_and_capped_at_ten() -> None:
    values = ["b", "b", "a", "a", "a"] + [f"v{i:02d}" for i in range(9)]  # 11 distinct

    profile = profile_column("category", column(*values))

    assert [(t.value, t.count) for t in profile.top_values] == [
        ("a", 3), ("b", 2),
        ("v00", 1), ("v01", 1), ("v02", 1), ("v03", 1),
        ("v04", 1), ("v05", 1), ("v06", 1), ("v07", 1),
    ]


def test_top_values_keep_raw_text_and_skip_missing() -> None:
    profile = profile_column("price", column("9.99", "9.99", NA, "12.50"))

    assert [(t.value, t.count) for t in profile.top_values] == [("9.99", 2), ("12.50", 1)]


# --- sample values ----------------------------------------------------------------


def test_sample_values_come_from_five_evenly_spaced_rows() -> None:
    # 10 rows: positions i * 9 // 4 for i = 0..4 -> 0, 2, 4, 6, 9.
    profile = profile_column("sku", column(*[f"r{i}" for i in range(10)]))

    assert profile.sample_values == ["r0", "r2", "r4", "r6", "r9"]


def test_sample_values_keep_missing_cells_as_null() -> None:
    profile = profile_column("sku", column("r0", "r1", NA, "r3", "r4"))

    # 5 rows: positions 0, 1, 2, 3, 4.
    assert profile.sample_values == ["r0", "r1", None, "r3", "r4"]


def test_sample_values_of_a_short_column_list_each_row_once() -> None:
    # 3 rows: positions 0, 0, 1, 1, 2 -> 0, 1, 2.
    profile = profile_column("sku", column("r0", "r1", "r2"))

    assert profile.sample_values == ["r0", "r1", "r2"]


@pytest.mark.parametrize(
    ("values", "expected_pct"),
    [(("1",), 0.0), (("x", NA), 50.0), (("x", NA, NA), 200 / 3)],
)
def test_null_pct_of_tiny_columns(
    values: tuple[str | None, ...], expected_pct: float
) -> None:
    profile = profile_column("c", column(*values))

    assert profile.null_pct == pytest.approx(expected_pct)  # nulls / rows * 100


def test_a_non_number_far_down_the_column_still_makes_it_text() -> None:
    # The first 200 values are only a shortcut for text columns; a column whose
    # first 250 values are numbers but whose last one is not is still text.
    profile = profile_column("qty", column(*[str(i) for i in range(250)], "n/a pending"))

    assert profile.dtype == "str"
    assert profile.mean is None
