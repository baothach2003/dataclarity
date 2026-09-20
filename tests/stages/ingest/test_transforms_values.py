"""The catalog actions that read a cell as a value: parse_datetime and
cast_type, fix_negative and clip_outliers_iqr, and the two flag actions
(docs/AI_PIPELINE.md sections 6 and 10). The text ones are in
test_transforms.py.

Every expectation is hand-calculated.
"""

import pandas as pd
import pytest

from stages.ingest import transforms

NA = None


def column(*values: str | None) -> pd.Series:
    return pd.Series(list(values), dtype="str")


def frame(**columns: pd.Series) -> pd.DataFrame:
    return pd.DataFrame(columns)


# --- types ------------------------------------------------------------------


def test_parse_datetime_parses_each_cell_and_flags_the_rest() -> None:
    values = column("2024-01-05", "Feb 1, 2024", "not a date", NA)

    result, entry = transforms.parse_datetime(frame(when=values), "when", {})

    assert [None if pd.isna(d) else d.date().isoformat() for d in result["when"]] == [
        "2024-01-05", "2024-02-01", None, None,
    ]
    assert (entry.cells_affected, entry.rows_affected) == (2, 1)
    flag = transforms.flag_column_name("invalid_date", "when")
    assert result[flag].tolist() == [False, False, True, False]


def test_parse_datetime_adds_no_flag_column_when_everything_parses() -> None:
    result, entry = transforms.parse_datetime(frame(when=column("2024-01-05")), "when", {})

    assert list(result.columns) == ["when"]
    assert (entry.cells_affected, entry.rows_affected) == (1, 0)


def test_parse_datetime_honours_dayfirst() -> None:
    result, _ = transforms.parse_datetime(
        frame(when=column("05/06/2024")), "when", {"dayfirst": True}
    )

    assert result["when"][0].date().isoformat() == "2024-06-05"


def test_parse_datetime_with_an_explicit_format_flags_everything_else() -> None:
    values = column("2024-01-05", "05/06/2024")

    result, entry = transforms.parse_datetime(frame(w=values), "w", {"format": "%Y-%m-%d"})

    assert (entry.cells_affected, entry.rows_affected) == (1, 1)
    assert result[transforms.flag_column_name("invalid_date", "w")].tolist() == [False, True]


@pytest.mark.parametrize(
    ("target", "expected"),
    [
        ("float", [1.0, 2.5]),
        ("integer", [1, 3]),
        ("string", ["1", "2.5"]),
        ("boolean", [True, False]),
    ],
)
def test_cast_type_converts_to_each_target(target: str, expected: list[object]) -> None:
    source = {"float": ("1", "2.5"), "integer": ("1", "3"),
              "string": ("1", "2.5"), "boolean": ("yes", "N")}[target]

    result, entry = transforms.cast_type(frame(v=column(*source)), "v", {"target": target})

    assert result["v"].tolist() == expected
    assert (entry.cells_affected, entry.rows_affected) == (2, 0)


def test_cast_type_flags_a_value_that_does_not_convert() -> None:
    result, entry = transforms.cast_type(frame(v=column("1", "abc", NA)), "v", {"target": "float"})

    assert result["v"].isna().tolist() == [False, True, True]
    assert (entry.cells_affected, entry.rows_affected) == (1, 1)
    assert result[transforms.flag_column_name("cast_failed", "v")].tolist() == [False, True, False]


def test_casting_to_integer_flags_a_fraction_instead_of_rounding_it() -> None:
    result, entry = transforms.cast_type(frame(v=column("3", "3.7")), "v", {"target": "integer"})

    assert result["v"].tolist()[0] == 3
    assert (entry.cells_affected, entry.rows_affected) == (1, 1)


def test_cast_type_refuses_an_unknown_target() -> None:
    with pytest.raises(ValueError, match="one of"):
        transforms.cast_type(frame(v=column("1")), "v", {"target": "decimal"})


# --- numbers ----------------------------------------------------------------


def test_fix_negative_flags_by_default_and_changes_nothing() -> None:
    values = column("5", "-3", NA, "-1")

    result, entry = transforms.fix_negative(frame(qty=values), "qty", {})

    assert result["qty"].tolist()[:2] == ["5", "-3"]  # the data is untouched
    assert (entry.cells_affected, entry.rows_affected) == (0, 2)
    assert result[transforms.flag_column_name("negative", "qty")].tolist() == [
        False, True, False, True,
    ]


def test_fix_negative_abs_replaces_the_negative_values() -> None:
    result, entry = transforms.fix_negative(
        frame(qty=column("5", "-3", NA)), "qty", {"strategy": "abs"}
    )

    assert result["qty"].tolist()[:2] == ["5", 3.0]
    assert (entry.cells_affected, entry.rows_affected) == (1, 0)


def test_fix_negative_drop_removes_the_rows() -> None:
    result, entry = transforms.fix_negative(
        frame(qty=column("5", "-3", NA)), "qty", {"strategy": "drop"}
    )

    assert result.index.tolist() == [0, 2]  # the missing cell is not negative
    assert (entry.cells_affected, entry.rows_affected) == (0, 1)


def test_fix_negative_refuses_an_unknown_strategy() -> None:
    with pytest.raises(ValueError, match="one of"):
        transforms.fix_negative(frame(q=column("1")), "q", {"strategy": "zero"})


def test_clip_outliers_iqr_pulls_values_to_the_fence() -> None:
    # [1, 2, 3, 100]: q1 = 1.75, q3 = 27.25, IQR = 25.5, fence = [-36.5, 65.5].
    values = column("1", "2", "3", "100")

    result, entry = transforms.clip_outliers_iqr(frame(qty=values), "qty", {})

    assert result["qty"].tolist() == ["1", "2", "3", 65.5]
    assert (entry.cells_affected, entry.rows_affected) == (1, 0)
    assert entry.detail == "clipped 1 values into [-36.5, 65.5] (k=1.5)"


def test_clip_outliers_iqr_takes_k_from_the_params() -> None:
    # Same quartiles, fence = 0.5 * 25.5 = 12.75: [-11.0, 40.0].
    values = column("1", "2", "3", "100")

    result, entry = transforms.clip_outliers_iqr(frame(qty=values), "qty", {"k": 0.5})

    assert result["qty"].tolist()[3] == 40.0
    assert entry.cells_affected == 1


def test_clip_outliers_iqr_refuses_a_k_that_is_not_a_number() -> None:
    with pytest.raises(ValueError, match="not negative"):
        transforms.clip_outliers_iqr(frame(q=column("1")), "q", {"k": -1})


# --- flags ------------------------------------------------------------------


def test_flag_duplicate_keys_marks_every_row_of_a_repeated_key() -> None:
    data = frame(sku=column("A", "B", "A", "C"), qty=column("1", "2", "9", "3"))

    result, entry = transforms.flag_duplicate_keys(data, None, {"keys": ["sku"]})

    assert result[transforms.flag_column_name("duplicate_key")].tolist() == [
        True, False, True, False,
    ]
    assert (entry.rows_affected, entry.column) == (2, None)
    assert len(result) == len(data)  # marked, never dropped


def test_flag_duplicate_keys_uses_every_key_column_together() -> None:
    data = frame(sku=column("A", "A"), day=column("1", "2"))

    _, entry = transforms.flag_duplicate_keys(data, None, {"keys": ["sku", "day"]})

    assert entry.rows_affected == 0  # the pairs differ


def test_flag_duplicate_keys_refuses_a_key_that_is_not_a_column() -> None:
    with pytest.raises(ValueError, match="no such column"):
        transforms.flag_duplicate_keys(frame(a=column("1")), None, {"keys": ["b"]})


def test_flag_duplicate_keys_refuses_an_empty_key_list() -> None:
    with pytest.raises(ValueError, match="non-empty list"):
        transforms.flag_duplicate_keys(frame(a=column("1")), None, {"keys": []})


def test_flag_only_records_the_note_and_changes_nothing() -> None:
    data = frame(qty=column("1", NA))

    result, entry = transforms.flag_only(data, "qty", {"note": "3 suspicious values"})

    assert result["qty"].isna().tolist() == [False, True]
    assert list(result.columns) == ["qty"]
    assert (entry.cells_affected, entry.rows_affected) == (0, 0)
    assert entry.detail == "3 suspicious values"


def test_flag_only_without_a_note_still_says_what_happened() -> None:
    _, entry = transforms.flag_only(frame(qty=column("1")), "qty", {})

    assert entry.detail == "recorded; nothing changed"
