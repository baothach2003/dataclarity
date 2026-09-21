"""Rows with more fields than the header (stages/ingest/profiling.read_csv_text).

pandas answers a file whose data rows have one field more than the header by
quietly using the first column as the index, which shifts every value one column
to the left: names end up under "qty", dates under "day". Found by the 1F review,
after profiling had accepted such a file and execute had written the shifted data.

The files have 40 rows, like real ones: csv.Sniffer cannot settle on a delimiter
for two ragged rows, which is a safe PARSE_FAILED of its own.
"""

import pytest

from stages.ingest.profiling import CsvParseError, profile_csv, read_csv_text

ROWS = 40


def rows(extra: str = "", first_extra: str | None = None) -> bytes:
    lines = ["name,qty,day"]
    for i in range(ROWS):
        tail = first_extra if (i == 0 and first_extra is not None) else extra
        lines.append(f"widget{i},{i},2024-01-{1 + i % 28:02d}{tail}")
    return ("\n".join(lines) + "\n").encode()


def test_a_trailing_delimiter_on_every_row_does_not_shift_the_columns() -> None:
    frame = read_csv_text(rows(",")).frame

    assert list(frame.columns) == ["name", "qty", "day"]
    assert frame["name"].tolist()[:2] == ["widget0", "widget1"]
    assert frame["qty"].tolist()[:2] == ["0", "1"]
    assert frame["day"].tolist()[:2] == ["2024-01-01", "2024-01-02"]
    assert frame.index.tolist() == list(range(ROWS))  # a plain row number, not the first column


def test_the_profile_of_such_a_file_describes_the_real_columns() -> None:
    profile = profile_csv(rows(","))

    by_name = {c.name: c for c in profile.columns}
    assert by_name["qty"].max == 39.0  # not the dates' column, not the names'
    assert by_name["name"].unique_count == ROWS
    assert by_name["day"].null_count == 0


@pytest.mark.parametrize(
    "raw",
    [rows(",X"), rows("", first_extra=",X")],  # a real extra field: on every row, on the first only
    ids=["every-row", "first-row"],
)
def test_a_real_extra_field_is_rejected_not_dropped(raw: bytes) -> None:
    # Reading it with index_col=False would silently lose the "X".
    with pytest.raises(CsvParseError, match="more fields than the header"):
        read_csv_text(raw)


def test_a_later_row_with_too_many_fields_is_still_rejected() -> None:
    lines = rows().decode().splitlines()
    lines[-1] += ",X"

    with pytest.raises(CsvParseError):
        read_csv_text(("\n".join(lines) + "\n").encode())


def test_a_row_with_too_few_fields_is_still_read_with_a_gap() -> None:
    lines = rows().decode().splitlines()
    lines[1] = "widget0,0"

    frame = read_csv_text(("\n".join(lines) + "\n").encode()).frame

    assert frame["day"].isna().tolist() == [True] + [False] * (ROWS - 1)


def test_an_ordinary_file_is_untouched() -> None:
    frame = read_csv_text(rows()).frame

    assert frame["name"].tolist()[0] == "widget0" and frame.shape == (ROWS, 3)
