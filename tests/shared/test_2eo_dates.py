"""Session 2E-o (Thach, 2026-09-28), the shared date reading, written before
the change.

- Q5 #2: a date followed by a separator and its time ("05-01-2026-10:30")
  is still a day-month-year date - 2E-j's last fix took it out of the order.
- Q5 #3: a dotted time is not a date ("10.05.30 05-01-2026", "05 Jan 2026
  10.30.00"): every candidate in the cell is found, a four-digit year wins,
  a dotted candidate loses to any other, a month in words leaves the cell
  alone; the rest of the cell stays, a dotted time written with colons
  (review cycles 1 and 2).
- Q10: month grain covers a file whose every counted line falls at
  midnight on the last day of its month.
"""

from datetime import date

import pandas as pd
import pytest

from shared.date_evidence import month_grain, order_evidence
from shared.dates import as_dates


def _text(values: list[str | None]) -> pd.Series:
    return pd.Series(values, dtype="str")


@pytest.mark.parametrize("cell", ["05-01-2026-10:30", "05/01/2026-10:30", "05.01.2026.10:30:00",
                                  "5-1-2026-9:15"])
def test_a_date_followed_by_its_time_keeps_the_order(cell: str) -> None:
    parsed = as_dates(_text([cell]), order="day_first", offsets="wall_clock")

    assert order_evidence(_text([cell])).shaped == 1
    assert parsed.dt.date.tolist() == [date(2026, 1, 5)]


@pytest.mark.parametrize(("cell", "example"), [
    ("10.05.30 13-01-2026", "13-01-2026"),
    ("14.05.10 13-01-2026", "13-01-2026"),
    ("10.30 13 01 2026", "13 01 2026"),
])
def test_a_four_digit_year_wins_over_a_dotted_time(cell: str, example: str) -> None:
    evidence = order_evidence(_text([cell]))

    assert (evidence.day_first, evidence.day_first_example) == (1, example)


@pytest.mark.parametrize("cell", ["05 Jan 2026 10.30.00", "2026 Jan 05 10.30.00", "Jan 5, 2026 14.05.10"])
def test_a_dotted_time_beside_a_four_digit_year_is_no_date(cell: str) -> None:
    assert order_evidence(_text([cell])).shaped == 0


CELLS = ["10.05.30 05-01-2026", "10.30.05 05-01-2026", "10.30.00 05/01/26", "05-JAN-26 10.30.00 AM",
         "05/03/26 1830", "05/01/2026 10h30", "05/01/2026 10 AM", "10.30.00 AM"]


@pytest.mark.parametrize(("order", "expected"), [
    # The dotted times are kept as times since review cycle 2 #3 (they were dropped).
    ("day_first", ["2026-01-05 10:05", "2026-01-05 10:30", "2026-01-05 10:30", None,
                   "2026-03-05 18:30", "2026-01-05 10:30", "2026-01-05 10:00", None]),
    ("month_first", ["2026-05-01 10:05", "2026-05-01 10:30", "2026-05-01 10:30", None,
                     "2026-05-03 18:30", "2026-05-01 10:30", "2026-05-01 10:00", None]),
])
def test_a_dotted_time_never_becomes_a_date_and_a_time_is_kept(order: str, expected: list) -> None:
    """Hand-computed, both orders (review cycle 1 #1, #2, #4, #8; cycle 2 #3):
    a dotted time beside a date is a time, never read as 2030 or 2000; a month in
    words leaves the cell to pandas (no date, as before); "1830" is a time,
    not a year elsewhere; "10h30" and "10 AM" keep their time; a dotted time
    alone before AM/PM is no date."""
    parsed = as_dates(_text(CELLS), order=order, offsets="wall_clock")  # type: ignore[arg-type]  # a plain str for the Literal

    assert [None if pd.isna(v) else v.strftime("%Y-%m-%d %H:%M") for v in parsed] == expected


def test_an_oracle_style_column_stays_undated_rather_than_invented() -> None:
    """DD-MON-RR HH.MI.SS AM: the date is in words; every numeric triple is a
    time. Before this fix a whole such column read as 2000-2058."""
    cells = [f"{d:02d}-JAN-26 {h:02d}.{m:02d}.00 AM" for d in range(1, 29) for h, m in ((9, 15), (11, 45))]

    evidence = order_evidence(_text(cells))

    assert evidence.shaped == 0
    assert as_dates(_text(cells), order="month_first").isna().all()


# --- Q10: month-end grain ----------------------------------------------------------------


@pytest.mark.parametrize(("cells", "expected"), [
    (["2024-01-31", "2024-02-29", "2024-03-31"], True),
    (["2024-01-31", "2024-02-29 10:00"], False),        # a time of day
    (["2024-01-31", "2024-02-28"], False),              # not February's last day in 2024
    (["2024-01-01", "2024-02-29"], False),              # the 1st and the last day mixed
    (["2024-01-31", "2024-01-31"], False),              # one month
])
def test_month_end_grain(cells: list[str], expected: bool) -> None:
    assert month_grain(pd.to_datetime(pd.Series(cells), format="mixed")) is expected


def test_a_date_before_a_dotted_time_keeps_its_date_and_time() -> None:
    """pandas cannot read "2026-01-05 10.30.00": the dotted time after the
    date is written with colons (mutation check; review cycle 2 #3)."""
    parsed = as_dates(_text(["05-01-2026 10.30.00", "05/01/26 14.05.10"]), order="day_first")

    assert [v.strftime("%Y-%m-%d %H:%M") for v in parsed] == ["2026-01-05 10:30", "2026-01-05 14:05"]


def test_a_dotted_time_before_am_pm_is_no_date_evidence() -> None:
    """A column of "HH.MM.SS AM" times proved month first (30 > 12) before
    the AM/PM rule (mutation check)."""
    assert order_evidence(_text(["10.30.00 AM", "11.45.00 PM"])).shaped == 0


@pytest.mark.parametrize(("cell", "expected"), [
    ("05/01/2026 10:30:45.12", "2026-01-05 10:30:45"),        # a fraction after a colon is no dotted time
    ("10:30:45.12 05/01/2026", "2026-01-05 10:30:45"),
    ("03/11/2026 11.45 PM", "2026-11-03 23:45:00"),           # "PM" keeps its time
    ("9.07 AM 05/01/2026", "2026-01-05 09:07:00"),
    ("05/01/2026 12.45 p.m.", "2026-01-05 12:45:00"),
    ("05/01/2026 10.30h", "2026-01-05 10:30:00"),
    ("05/01/2026-09h07", "2026-01-05 09:07:00"),              # a separator then an "h" time
    ("03/11/2026-11.45 PM", "2026-11-03 23:45:00"),           # a separator then a dotted time
])
def test_times_of_every_kind_stay_with_their_date(cell: str, expected: str) -> None:
    """Review cycle 2 #1, #3, #4: removing dotted times ate the seconds of
    "10:30:45.12" and orphaned "PM"; a date followed by a non-colon time
    bypassed the order."""
    parsed = as_dates(_text([cell]), order="day_first", offsets="wall_clock")

    assert parsed.iloc[0].strftime("%Y-%m-%d %H:%M:%S") == expected


def test_two_dotted_candidates_are_no_evidence() -> None:
    """"09.15.00 05.01.26": which is the time cannot be told, and the time
    proved month first (review cycle 2 #5)."""
    evidence = order_evidence(_text(["09.15.00 05.01.26", "14.20.00 06.01.26", "10.30.00 13.01.26"]))

    assert evidence.shaped == 0


@pytest.mark.parametrize(("cell", "day_first", "month_first"), [
    ("10.30 05.01.26", "2026-01-05 10:30", "2026-05-01 10:30"),   # "10.30 05" is no date (review cycle 3 #1)
    ("14.05 13.01.26", "2026-01-13 14:05", None),
    ("13 01 26 1030", "2026-01-13 10:30", None),                   # "1030" is no year (review cycle 3 #3)
    ("05 03 26 1830", "2026-03-05 18:30", "2026-05-03 18:30"),
])
def test_a_time_before_or_after_a_short_year_date_stays_a_time(cell: str, day_first: str | None,
                                                              month_first: str | None) -> None:
    got = {order: as_dates(_text([cell]), order=order, offsets="wall_clock").iloc[0]  # type: ignore[arg-type]
           for order in ("day_first", "month_first")}

    assert [None if pd.isna(v) else v.strftime("%Y-%m-%d %H:%M") for v in got.values()] == [day_first, month_first]
