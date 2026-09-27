"""Session 2E-j (Thach), the shared date reader, written before the change.

- Day first or month first is decided, never guessed: a cell written
  day-month-year or month-day-year (two numbers of one or two digits and a
  year, one separator repeated) is read in the ORDER given, and a cell that
  order cannot hold (a month 13) is no date. Every other cell - ISO, a month
  name, a time - is read as before, so a day-first decision never re-reads
  "2026-01-05" as 1 May (pandas' `dayfirst` did, 2E-h).
- The evidence: a first number 13-31 proves day first, a second number 13-31
  month first; both or neither, the user answers (stage 1).
- Placeholder dates are no date (Thach, Q2 of 2E-h): 1899-12-30, 1900-01-01
  and 1970-01-01, at any time of day.
- A month-grain file (every dated line at midnight on the 1st, over two
  months or more) is recognised (Thach, Q1 of 2E-h).
- An offset after a basic ISO time ("20240330T101500+1100") is cut like any
  other, with an explicit format too (moved from 2E-h).
"""

from datetime import date, timedelta

import pandas as pd
import pytest

from shared.date_evidence import applied_order, month_grain, order_evidence
from shared.dates import as_dates
from stages.ingest.column_kinds import has_utc_offset


def _text(values: list[str | None]) -> pd.Series:
    return pd.Series(values, dtype="str")


def _days(parsed: pd.Series) -> list[str | None]:
    return [None if pd.isna(value) else value.strftime("%Y-%m-%d %H:%M") for value in parsed]


# --- the evidence ------------------------------------------------------------------


def test_a_first_number_above_12_proves_day_first() -> None:
    evidence = order_evidence(_text(["13/01/2026", "05/01/2026", "2026-01-05", None, "Mar 2024"]))

    assert (evidence.shaped, evidence.day_first, evidence.month_first) == (2, 1, 0)
    assert evidence.day_first_example == "13/01/2026"
    assert evidence.month_first_example is None
    assert evidence.decision == "day_first"


def test_a_second_number_above_12_proves_month_first() -> None:
    evidence = order_evidence(_text(["01/13/2026", "05/01/2026 10:30"]))

    assert (evidence.shaped, evidence.day_first, evidence.month_first) == (2, 0, 1)
    assert evidence.month_first_example == "01/13/2026"
    assert evidence.decision == "month_first"


@pytest.mark.parametrize("values", [
    ["13/01/2026", "01/13/2026"],          # both prove: a mixed file
    ["05/01/2026", "06/02/2026"],          # neither proves
    ["32/01/2026", "05/01/2026"],          # 32 is no day: proves nothing, 05/01 is either
])
def test_both_or_neither_asks(values: list[str]) -> None:
    assert order_evidence(_text(values)).decision == "ask"


def test_no_day_month_year_cell_asks_nothing() -> None:
    evidence = order_evidence(_text(["2026-01-05", "2026/01/13", "Mar 2024", "45000", "130/01/2026",
                                     "2026-01-05 10:30", "20260105T1015", None]))

    assert evidence.shaped == 0
    assert evidence.decision is None


@pytest.mark.parametrize("values", [
    ["01/01/2026", "05/05/2026", "2026-01-07"],   # the two numbers equal: one date either way
    ["13/13/2026"],                               # no order holds it
])
def test_a_cell_that_reads_the_same_either_way_asks_nothing(values: list[str]) -> None:
    """An ISO column with one "01/01/2026" was refused at execute and blocked
    Review, though both readings give one date (2E-j review cycle 1 #10)."""
    evidence = order_evidence(_text(values))

    assert (evidence.ambiguous, evidence.decision) == (0, None)


@pytest.mark.parametrize("cell", ["13.01.2026", "13-01-2026", "13/01/26", " 13/1/2026", "13/01/2026T10:00",
                                  "Tue 13/01/2026", "10:30 13/01/2026", "'13/01/2026", "13 01 2026",
                                  "13 / 01 / 2026", "13/01-2026"])
def test_the_date_is_found_anywhere_in_the_cell(cell: str) -> None:
    """Anchored at the start, the pattern missed a weekday, a time or an
    apostrophe in front, spaces and mixed separators (2E-j review cycle 1 #2)."""
    evidence = order_evidence(_text([cell]))

    assert (evidence.shaped, evidence.day_first) == (1, 1)
    assert evidence.day_first_example is not None and evidence.day_first_example.startswith("13")


@pytest.mark.parametrize("cell", ["Mon 05/01/2026", "10:30 05/01/2026", "'05/01/2026", "05 01 2026",
                                  "05 / 01 / 2026", "05/01-2026"])
def test_dayfirst_reaches_the_date_wherever_it_is(cell: str) -> None:
    """With the anchored pattern these fell back to month first: 1 May where
    pandas' dayfirst had read 5 January (2E-j review cycle 1 #2)."""
    parsed = as_dates(_text([cell]), dayfirst=True, offsets="wall_clock")

    assert parsed.dt.date.tolist() == [date(2026, 1, 5)]


def test_the_example_is_the_date_not_the_cell() -> None:
    """A notes column starting with a date must not carry the rest of the
    note into the profile - or to the AI (2E-j review cycle 1 #5)."""
    evidence = order_evidence(_text(["13/01/2026 customer Jane Citizen; 12 Example St; card 4242"]))

    assert evidence.day_first_example == "13/01/2026"


def test_the_first_of_each_month_written_day_first_is_a_hint_not_a_proof() -> None:
    """A month-grain file written day first never proves it: every first
    number is 1. The hint is a suggestion the user confirms (2E-d2)."""
    day_first = order_evidence(_text(["01/03/2024", "01/04/2024", "01/05/2024"]))
    month_first = order_evidence(_text(["03/01/2024", "04/01/2024"]))
    no_hint = order_evidence(_text(["05/01/2026", "06/02/2026"]))

    assert (day_first.decision, day_first.hint) == ("ask", "day_first")
    assert (month_first.decision, month_first.hint) == ("ask", "month_first")
    assert no_hint.hint is None


def test_an_answer_wins_and_otherwise_the_proof_decides() -> None:
    ambiguous = order_evidence(_text(["05/01/2026"]))
    proven = order_evidence(_text(["13/01/2026", "05/01/2026"]))

    assert applied_order(ambiguous, None) is None
    assert applied_order(ambiguous, True) == "day_first"
    assert applied_order(ambiguous, False) == "month_first"
    assert applied_order(proven, None) == "day_first"
    assert applied_order(order_evidence(_text(["2026-01-05"])), None) is None


# --- reading in an order -------------------------------------------------------------


def test_the_australian_shop_reads_two_months_once_day_first_is_decided() -> None:
    """Thach's repro (2E-h): one sale a day, 1 July - 31 August 2026,
    DD/MM/YYYY. Month first by default, days 1-12 landed in January to
    December; day first, July and August hold 31 days each."""
    days = [date(2026, 7, 1) + timedelta(days=n) for n in range(62)]
    cells = _text([day.strftime("%d/%m/%Y") for day in days])

    parsed = as_dates(cells, order="day_first", offsets="wall_clock")

    assert parsed.dt.date.tolist() == days
    assert parsed.dt.to_period("M").astype(str).value_counts().to_dict() == {"2026-07": 31, "2026-08": 31}


@pytest.mark.parametrize("order", ["day_first", "month_first"])
def test_iso_cells_are_never_reordered(order: str) -> None:
    cells = _text(["2026-01-05", "2026-01-05 10:00", "2026-01-05T10:00:00", "20260105"])

    parsed = as_dates(cells, order=order)  # type: ignore[arg-type]  # a plain str for the Literal

    assert parsed.dt.date.tolist() == [date(2026, 1, 5)] * 4


def test_a_cell_the_order_cannot_hold_is_no_date() -> None:
    """pandas swapped it back silently: "01/13/2026" read day first was 13
    January. A file answered day first holds no 13th month."""
    day_first = as_dates(_text(["01/13/2026", "05/01/2026", "30/02/2026"]), order="day_first")
    month_first = as_dates(_text(["13/01/2026", "05/01/2026", "02/30/2026"]), order="month_first")

    assert _days(day_first) == [None, "2026-01-05 00:00", None]
    assert _days(month_first) == [None, "2026-05-01 00:00", None]


def test_other_shapes_times_and_offsets_keep_their_reading() -> None:
    cells = _text(["05.01.2026", "05-01-26", "5/1/2026 23:30+10:00", "Mar 2024", "2026-02-03"])

    parsed = as_dates(cells, order="day_first", offsets="wall_clock")

    assert _days(parsed) == ["2026-01-05 00:00", "2026-01-05 00:00", "2026-01-05 23:30",
                             "2024-03-01 00:00", "2026-02-03 00:00"]


def test_dayfirst_no_longer_rereads_iso() -> None:
    """Stage 1's `parse_datetime` with dayfirst: "2026-01-05" was 1 May (2E-h)."""
    parsed = as_dates(_text(["2026-01-05", "05/01/2026", "01/13/2026"]), dayfirst=True)

    assert _days(parsed) == ["2026-01-05 00:00", "2026-01-05 00:00", None]


def test_no_order_reads_as_before() -> None:
    parsed = as_dates(_text(["13/01/2026", "05/01/2026", "2026-01-05"]))

    assert _days(parsed) == ["2026-01-13 00:00", "2026-05-01 00:00", "2026-01-05 00:00"]


def test_an_explicit_format_decides_whatever_the_order() -> None:
    parsed = as_dates(_text(["05/01/2026"]), "%m/%d/%Y", order="day_first")

    assert _days(parsed) == ["2026-05-01 00:00"]


# --- placeholder dates ---------------------------------------------------------------


@pytest.mark.parametrize("offsets", ["utc", "wall_clock"])
def test_placeholder_dates_are_no_date(offsets: str) -> None:
    cells = _text(["1900-01-01", "1970-01-01 00:00:05", "1899-12-30", "1900-01-01 10:30",
                   "01/01/1900", "1970-01-02", "1900-01-02", "12/31/1969 19:00", "1969-12-30"])

    parsed = as_dates(cells, offsets=offsets)  # type: ignore[arg-type]  # a plain str for the Literal

    # 1969-12-31: the epoch on a western clock (2E-j review cycle 1 #4).
    assert _days(parsed) == [None, None, None, None, None, "1970-01-02 00:00", "1900-01-02 00:00",
                             None, "1969-12-30 00:00"]


def test_placeholder_dates_are_no_date_with_a_format_too() -> None:
    parsed = as_dates(_text(["1900-01-01", "1970-01-01", "2024-01-01"]), "%Y-%m-%d")

    assert _days(parsed) == [None, None, "2024-01-01 00:00"]


# --- month grain ---------------------------------------------------------------------


@pytest.mark.parametrize(("cells", "expected"), [
    (["2024-01-01", "2024-02-01", None], True),
    (["2024-01-01", "2024-01-01"], False),             # one month: cannot tell
    (["2024-01-01", "2024-02-01 10:00"], False),       # a time of day
    (["2024-01-01", "2024-02-02"], False),             # a day other than the 1st
    ([None, None], False),
])
def test_month_grain(cells: list[str | None], expected: bool) -> None:
    assert month_grain(pd.to_datetime(pd.Series(cells), format="mixed")) is expected


# --- offsets after a basic ISO time (moved from 2E-h) ----------------------------------


@pytest.mark.parametrize("date_format", ["%Y%m%dT%H%M%S%z", "ISO8601"])
def test_basic_iso_offsets_are_cut_with_an_explicit_format(date_format: str) -> None:
    """Mixed offsets: the format with %z matched nothing once its offset was
    cut (every cell no date), and "ISO8601" raised at execute."""
    cells = _text(["20240330T101500+1100", "20240407T101500+1000", "20240408T1015-0500"])

    parsed = as_dates(cells, date_format, offsets="wall_clock")

    assert _days(parsed)[:2] == ["2024-03-30 10:15", "2024-04-07 10:15"]
    if date_format == "ISO8601":
        assert _days(parsed)[2] == "2024-04-08 10:15"


def test_the_change_log_sees_a_basic_offset() -> None:
    assert has_utc_offset(_text(["20240330T101500+1100"]))
    assert not has_utc_offset(_text(["20240330", "2024-01-05"]))


@pytest.mark.parametrize(("pattern", "order"), [
    ("%d/%m/%Y %H:%M", "day_first"), ("%m/%d/%Y %H:%M", "month_first"),
    ("%d.%m.%y", "day_first"), ("%m-%d-%Y %I:%M %p", "month_first")])
def test_every_day_of_two_years_reads_back_in_its_order(pattern: str, order: str) -> None:
    """A sweep, not examples: every day of 2024 and 2025 at 21:45, written
    each way, reads back as itself - the four-digit years through ISO, the
    two-digit ones month first, AM/PM kept."""
    stamps = pd.Series(pd.date_range("2024-01-01 21:45", "2025-12-31 21:45", freq="D"))
    if "%H" not in pattern and "%I" not in pattern:
        stamps = stamps.dt.normalize()
    cells = stamps.dt.strftime(pattern).astype("str")

    parsed = as_dates(cells, order=order, offsets="wall_clock")  # type: ignore[arg-type]  # a plain str for the Literal

    assert parsed.tolist() == stamps.tolist()


def test_a_two_digit_year_cell_the_order_cannot_hold_is_no_date_too() -> None:
    """Such a cell is handed to pandas month first, and pandas swaps one it
    cannot read that way - so the order's own check has to catch it
    (mutation check)."""
    day_first = as_dates(_text(["01/13/26", "05/01/26"]), order="day_first")
    month_first = as_dates(_text(["13/01/26", "01/05/26"]), order="month_first")

    assert _days(day_first) == [None, "2026-01-05 00:00"]
    assert _days(month_first) == [None, "2026-01-05 00:00"]


def test_a_missing_cell_stays_missing_in_an_order() -> None:
    """Read per distinct value, a missing cell has no value of its own: it
    must not borrow another cell's date - a blank, or "now" (mutation
    check)."""
    parsed = as_dates(_text(["05/01/2026", None, "now", "13/01/2026"]), order="day_first")

    assert _days(parsed) == ["2026-01-05 00:00", None, None, "2026-01-13 00:00"]


@pytest.mark.parametrize(("cell", "decision"), [
    ("12/05/2026", "ask"), ("13/05/2026", "day_first"), ("31/05/2026", "day_first"), ("32/05/2026", None),
    ("05/12/2026", "ask"), ("05/13/2026", "month_first"), ("05/31/2026", "month_first"), ("05/32/2026", None)])
def test_the_proof_starts_at_13_and_ends_at_31(cell: str, decision: str | None) -> None:
    """12 can be a month, 32 is no day (mutation check); a cell no order
    holds needs no answer (review cycle 1 #10)."""
    assert order_evidence(_text([cell])).decision == decision


def test_no_hint_unless_every_first_number_is_1() -> None:
    """One date on the 1st among others is no month-grain file (mutation check)."""
    assert order_evidence(_text(["01/03/2024", "05/04/2024", "07/06/2024"])).hint is None
    assert order_evidence(_text(["03/01/2024", "04/05/2024"])).hint is None


@pytest.mark.parametrize("cell", ["2026-01-05 10.30.00", "2026/1/5 14.05.00", "2026-01-05 10 30 00"])
def test_a_cell_holding_a_year_first_date_is_not_day_month_year(cell: str) -> None:
    """A dotted time after an ISO date read as D.M.YY, and Review asked about
    it (2E-j review cycle 2 #2)."""
    assert order_evidence(_text([cell])).shaped == 0
    assert as_dates(_text([cell]), order="day_first").notna().tolist() == \
        as_dates(_text([cell])).notna().tolist()


def test_no_hint_when_the_cells_carry_times() -> None:
    """1-12 January with times of day is a short export, not monthly figures
    (2E-j review cycle 2 #3)."""
    cells = [f"1/{day}/2026 9:15" for day in range(1, 13)]

    assert order_evidence(_text(cells)).hint is None
    assert order_evidence(_text([f"1/{day}/2026" for day in range(1, 13)])).hint == "day_first"


def test_a_separator_and_a_digit_after_the_year_is_not_a_date_end() -> None:
    """"10.30 05-01-2026" read "10.30 05" as a date and proved month first
    (2E-j review cycle 3 #3): the date in it is 05-01-2026."""
    evidence = order_evidence(_text(["10.30 05-01-2026", "14.15 13-01-2026"]))

    assert (evidence.day_first, evidence.month_first) == (1, 0)
    assert evidence.day_first_example == "13-01-2026"


def test_no_hint_beside_a_proof() -> None:
    """January written month first proved month first yet hinted day first
    (2E-j review cycle 3 #9)."""
    evidence = order_evidence(_text(["01/13/2026", "01/14/2026", "01/02/2026"]))

    assert (evidence.decision, evidence.hint) == ("month_first", None)
