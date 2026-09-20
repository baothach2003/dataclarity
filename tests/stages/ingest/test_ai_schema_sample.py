import pandas as pd
import pytest

from stages.ingest.ai_input import select_sample_rows


def frame(rows: list[list[str | None]], columns: list[str]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=columns, dtype="str")


def test_small_file_sends_every_row_numbered_from_one() -> None:
    data = frame([["A1", "3"], ["B2", "5"]], ["sku", "qty"])

    rows = select_sample_rows(data, numeric_columns={"qty"})

    assert rows == [
        {"row": 1, "values": {"sku": "A1", "qty": "3"}},
        {"row": 2, "values": {"sku": "B2", "qty": "5"}},
    ]


def test_missing_cells_are_sent_as_null() -> None:
    data = frame([["A1", None]], ["sku", "qty"])

    rows = select_sample_rows(data, numeric_columns={"qty"})

    assert rows[0]["values"] == {"sku": "A1", "qty": None}


def test_never_more_than_the_limit() -> None:
    data = frame([[f"S{i}", str(i)] for i in range(100)], ["sku", "qty"])

    rows = select_sample_rows(data, numeric_columns={"qty"}, limit=30)

    assert len(rows) == 30


def test_evenly_spaced_rows_when_nothing_is_problematic() -> None:
    # 100 clean rows, limit 5: positions i * 99 // 4 -> 0, 24, 49, 74, 99.
    data = frame([[f"S{i}", str(i)] for i in range(100)], ["sku", "qty"])

    rows = select_sample_rows(data, numeric_columns={"qty"}, limit=5)

    assert [r["row"] for r in rows] == [1, 25, 50, 75, 100]


def test_problem_rows_are_included_before_filler() -> None:
    # 100 rows; row 11 (index 10) has a missing qty, rows 21 and 22 (index 20,
    # 21) are exact duplicates, row 31 (index 30) has a negative qty.
    values = [[f"S{i}", str(i)] for i in range(100)]
    values[10][1] = None
    values[21] = list(values[20])
    values[30][1] = "-4"
    data = frame(values, ["sku", "qty"])

    rows = select_sample_rows(data, numeric_columns={"qty"}, limit=6)

    # Problems first (11, 21, 22, 31), then filler from 0, 19, 39, ... (i * 99 // 5)
    # until 6 rows: row 1 (index 0) and row 20 (index 19). Returned in file order.
    assert [r["row"] for r in rows] == [1, 11, 20, 21, 22, 31]


def test_each_problem_kind_is_capped_at_five() -> None:
    # 40 rows with a missing qty; limit 30 leaves room, but only 5 are taken
    # for that reason so other kinds and ordinary rows still fit.
    values = [[f"S{i}", None if i < 40 else str(i)] for i in range(100)]
    data = frame(values, ["sku", "qty"])

    rows = select_sample_rows(data, numeric_columns={"qty"}, limit=30)

    first_five_missing = [r["row"] for r in rows if r["values"]["qty"] is None][:5]
    assert first_five_missing == [1, 2, 3, 4, 5]
    assert len(rows) <= 30


def test_negative_check_ignores_text_columns() -> None:
    # "-" in a text column is not a negative number.
    values = [[f"S{i}", "-", str(i)] for i in range(50)]
    data = frame(values, ["sku", "note", "qty"])

    rows = select_sample_rows(data, numeric_columns={"qty"}, limit=3)

    assert [r["row"] for r in rows] == [1, 25, 50]  # i * 49 // 2 -> 0, 24, 49


def test_single_row_file() -> None:
    rows = select_sample_rows(frame([["A1", "3"]], ["sku", "qty"]), numeric_columns={"qty"})

    assert rows == [{"row": 1, "values": {"sku": "A1", "qty": "3"}}]


def test_all_null_column_file() -> None:
    data = frame([["A1", None], ["B2", None]], ["sku", "note"])

    rows = select_sample_rows(data, numeric_columns=set())

    assert [r["values"]["note"] for r in rows] == [None, None]


def test_a_limit_of_one_row() -> None:
    data = frame([[f"S{i}", str(i)] for i in range(10)], ["sku", "qty"])

    rows = select_sample_rows(data, numeric_columns={"qty"}, limit=1)

    assert [r["row"] for r in rows] == [1]


def test_problem_rows_never_exceed_the_limit() -> None:
    # 5 missing + 5 duplicated + 5 negative rows, but only 3 may be sent.
    values = [[f"S{i}", str(i)] for i in range(100)]
    for i in range(5):
        values[i][1] = None
        values[10 + i][1] = "-1"
        values[20 + i] = list(values[30 + i])
    data = frame(values, ["sku", "qty"])

    rows = select_sample_rows(data, numeric_columns={"qty"}, limit=3)

    assert len(rows) == 3


@pytest.mark.parametrize("limit", [0, -5])
def test_a_limit_of_zero_or_less_sends_nothing(limit: int) -> None:
    data = frame([["A1", "3"], ["B2", "4"]], ["sku", "qty"])

    assert select_sample_rows(data, numeric_columns={"qty"}, limit=limit) == []
