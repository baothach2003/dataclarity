"""Session 2E-h (Thach), one date rule for every stage, written before the
change: shared date parsing ALWAYS keeps the wall-clock date and time as
written (1F's rule), whatever the cleaning plan did - parse_transactions read
every date as UTC and dropped the zone, so 1F held only when the plan happened
to parse the date column. With it comes the rest of 1F's cell rule: "now", a
bare time and a year outside 1900-2100 are not dates. Lines with no readable
date are counted in metrics.json with a reason, never dropped silently.
Also here, 2E-f review cycle 4 F2: an id with no sale line is judged on its
counted lines. metrics.json 8.0, diagnosis.json 7.0.
"""

from datetime import date, timedelta

import pandas as pd
import pytest

from contracts.cleaning import OrderConfirmations
from contracts.diagnosis import DiagnosisContract
from contracts.metrics import MetricsContract
from shared.orders import IdCheck
from shared.order_checks import order_id_spanning
from shared.transactions import parse_transactions
from stages.analyze.assemble import SCHEMA_VERSION
from tests.stages.diagnose.diagnose_fixtures import row, run_data

# The user's Yes to Review's fill question (2E-e2), explicit although an
# unanswered question fills too (test_2ee2_review.py).
# And the Yes to the receipt question: these files name one customer, which
# leaves the check on dates only (2E-e2 review cycle 2 F4).
FIRST_LINE = OrderConfirmations(order_id_is_receipt=True, customer_on_first_line_only=True)


def _sydney_shop() -> list[dict]:
    """A +10:00 shop sells one item at 100 at 09:00 every day, 1 June to 31
    August 2026, closed Sundays."""
    rows, day = [], date(2026, 6, 1)
    while day <= date(2026, 8, 31):
        if day.weekday() != 6:
            rows.append({**row(day, price=100.0), "Date": f"{day}T09:00+10:00"})
        day += timedelta(days=1)
    return rows


def test_a_shop_with_an_offset_is_read_on_its_own_clock() -> None:
    """Thach's reproduction. Wall clock: current month 2026-08 against
    2026-07, 2,600 (26 trading days) against 2,700 (27): -3.7%; no May; no
    sale on a Sunday, sales on Saturdays - in stage 2 and stage 3 alike.
    Read as UTC it was 2026-07 +3.8%, a phantom May of 100, and the closed
    day Saturday."""
    data = run_data(_sydney_shop())
    metrics = data.metrics

    assert (metrics.period.current, metrics.period.previous) == ("2026-08", "2026-07")
    assert (metrics.core.revenue_current, metrics.core.revenue_previous) == (
        pytest.approx(2600.0), pytest.approx(2700.0))
    assert metrics.core.revenue_change_pct == pytest.approx((2600 / 2700 - 1) * 100)
    assert [m.period for m in metrics.core.revenue_by_month] == ["2026-06", "2026-07", "2026-08"]
    assert sorted(data.months.unique()) == ["2026-06", "2026-07", "2026-08"]
    weekdays = set(data.parsed.dates[data.parsed.sale].dt.dayofweek)
    assert 6 not in weekdays and 5 in weekdays


def test_a_receipt_across_seven_in_the_morning_is_one_order() -> None:
    """At +07:00, 06:59 and 07:01 are one local day but two UTC days: the
    receipt was two orders, its unnamed line unfilled, and stage 1's check
    saw it span days."""
    mapping = {"Date": "transaction_date", "Qty": "quantity", "Price": "unit_price",
               "Cust": "customer", "Inv": "order_id"}
    df = pd.DataFrame([("2026-08-03T06:59+07:00", "1", "10", "Ann", "100"),
                       ("2026-08-03T07:01+07:00", "1", "40", None, "100")],
                      columns=["Date", "Qty", "Price", "Cust", "Inv"])

    parsed = parse_transactions(df, mapping, FIRST_LINE)

    assert parsed.order_key.nunique() == 1
    assert parsed.customers.tolist() == ["ann", "ann"]
    assert order_id_spanning(df, mapping) == IdCheck(0, 1)


def test_mixed_offsets_keep_each_cells_own_clock() -> None:
    """1F: each cell keeps the date and time written in it. "GMT+7" was even
    read the wrong way round (13:59)."""
    df = pd.DataFrame({"Date": ["2026-08-01T09:00+10:00", "2026-08-01T09:00+02:00",
                                "2026-08-01 06:59 GMT+7", "2026-07-31T23:30-05:00"],
                       "Qty": "1", "Price": "10"})

    dates = parse_transactions(df, {"Date": "transaction_date", "Qty": "quantity",
                                    "Price": "unit_price"}).dates

    assert [str(d) for d in dates] == ["2026-08-01 09:00:00", "2026-08-01 09:00:00",
                                       "2026-08-01 06:59:00", "2026-07-31 23:30:00"]


def test_now_a_bare_time_and_the_year_1200_are_not_dates() -> None:
    """"now" read as the moment of the run - the same file analysed on two
    days gave two answers - "10:30" as today, "1200-01-01" as the year 1200.
    None is a date: those lines are in no month."""
    df = pd.DataFrame({"Date": ["now", "10:30", "1200-01-01", "2026-08-01"], "Qty": "1",
                       "Price": "10"})

    dates = parse_transactions(df, {"Date": "transaction_date", "Qty": "quantity",
                                    "Price": "unit_price"}).dates

    assert dates.isna().tolist() == [True, True, True, False]


def test_mixed_offsets_the_pattern_misses_are_read_not_a_crash() -> None:
    """2E-h doubt-review F1: a 12-hour clock or a one-digit hour before its
    offset, or a lowercase "z", escaped the offset pattern; the cells still
    mixed zones and pandas raised - stage 1's check, stage 2 and stage 3 all
    failed on a file the UTC reader had read. Each keeps its own clock."""
    df = pd.DataFrame({"Date": ["2024-03-30 09:15 AM +11:00", "2024-04-08 09:15 AM +10:00",
                                "1/6/2024 9:15 +10:00", "2024-01-06T01:00:00z"],
                       "Qty": "1", "Price": "10", "Inv": ["a", "b", "c", "d"]})
    mapping = {"Date": "transaction_date", "Qty": "quantity", "Price": "unit_price",
               "Inv": "order_id"}

    dates = parse_transactions(df, mapping).dates

    assert [str(d) for d in dates] == ["2024-03-30 09:15:00", "2024-04-08 09:15:00",
                                       "2024-01-06 09:15:00", "2024-01-06 01:00:00"]
    assert order_id_spanning(df, mapping) == IdCheck(0, 4)


def test_a_bare_time_with_an_offset_or_dotted_am_is_not_a_date() -> None:
    """2E-h doubt-review F2: "10:30Z", "10:30+10:00", "10:30 a.m." and their
    kind were dated the day of the run - one such cell moved a whole report
    into an empty month."""
    cells = ["10:30Z", "10:30+10:00", "10:30:00 +10:00", "10:30 UTC", "10:30 +10", "10:30 GMT+2",
             "10:30:00.000Z", "10:30 a.m.", "9:05 p.m.", "2026-08-01 10:30Z"]
    df = pd.DataFrame({"Date": cells, "Qty": "1", "Price": "10"})

    dates = parse_transactions(df, {"Date": "transaction_date", "Qty": "quantity",
                                    "Price": "unit_price"}).dates

    assert dates.isna().tolist() == [True] * 9 + [False]


def test_a_bare_time_with_a_one_letter_am_or_pm_is_not_a_date() -> None:
    """2E-h doubt-review cycle 2 F1: "10:30p" and "9:05a" were still dated the
    day of the run (160 of 2,400 bare-time spellings)."""
    df = pd.DataFrame({"Date": ["10:30p", "9:05P", "10:30 a", "10:30:00 p", "11:59p +10:00",
                                "2026-08-01"], "Qty": "1", "Price": "10"})

    dates = parse_transactions(df, {"Date": "transaction_date", "Qty": "quantity",
                                    "Price": "unit_price"}).dates

    assert dates.isna().tolist() == [True, True, True, True, True, False]


def test_a_receipt_header_line_with_no_quantity_still_names_its_receipt() -> None:
    """2E-h doubt-review cycle 2 F3: invoice exports with a header line (the
    customer, no quantity or price) before unnamed item lines. Only a
    stock-in line is excluded from naming a receipt - excluding every
    uncounted line lost these customers."""
    mapping = {"Date": "transaction_date", "Qty": "quantity", "Price": "unit_price",
               "Cust": "customer", "Inv": "order_id"}
    df = pd.DataFrame([("2026-08-03", "", "", "Ann", "100"), ("2026-08-03", "1", "10", None, "100"),
                       ("2026-08-03", "2", "10", None, "100")],
                      columns=["Date", "Qty", "Price", "Cust", "Inv"])

    parsed = parse_transactions(df, mapping, FIRST_LINE)

    assert parsed.customers.tolist()[1:] == ["ann", "ann"]


def test_a_column_with_one_stray_zone_reads_every_cell_on_its_own_clock() -> None:
    """2E-h doubt-review cycle 2 F4: one cell whose offset the pattern misses
    sent every cell through a one-by-one parse (290-360x slower). Only the
    zoned cells are read alone now; every cell still reads as written, in
    its place."""
    cells = [f"2026-08-{day:02d} 10:{day:02d}:00" for day in range(1, 29)]
    cells.insert(5, "2026-08-29 9:15 AM +10:00")
    cells.insert(9, "2026-08-30T01:00:00z")
    df = pd.DataFrame({"Date": cells, "Qty": "1", "Price": "10"})

    dates = parse_transactions(df, {"Date": "transaction_date", "Qty": "quantity",
                                    "Price": "unit_price"}).dates

    expected = [f"2026-08-{day:02d} 10:{day:02d}:00" for day in range(1, 29)]
    expected.insert(5, "2026-08-29 09:15:00")
    expected.insert(9, "2026-08-30 01:00:00")
    assert [str(d) for d in dates] == expected


def test_a_cell_that_starts_with_a_time_needs_a_year() -> None:
    """2E-h doubt-review cycle 3 F1: pandas takes the run day's date for any
    cell that STARTS with a time, whatever follows - "10:30," was today,
    "14:32 12 Aug" and "10:30 05/08" took this year. Such a cell is a date
    only when it carries a year."""
    cells = ["10:30,", "10:30.", "10:30 AM,", "10:30 at", "14:32 12 Aug", "10:30 05/08",
             "10:30 5th", "14:32 12 Aug 2024", "10:30:00 +1000"]
    df = pd.DataFrame({"Date": cells, "Qty": "1", "Price": "10"})

    dates = parse_transactions(df, {"Date": "transaction_date", "Qty": "quantity",
                                    "Price": "unit_price"}).dates

    assert dates.isna().tolist() == [True] * 7 + [False, True]
    assert str(dates.iloc[7]) == "2024-08-12 14:32:00"


def test_a_zone_inside_the_cell_beside_a_flagged_cell_does_not_crash() -> None:
    """2E-h doubt-review cycle 3 F2: "Sat Jan 06 01:00:00 +0000 2024" carries
    its zone inside; beside a cell the zone hint flags, the merge of a zoned
    and a plain column raised AttributeError - in stage 1's schema step too."""
    df = pd.DataFrame({"Date": ["Sat Jan 06 01:00:00 +0000 2024", "Sun Jan 07 02:00:00 +0000 2024",
                                "2024-01-05", "2024-01-08 9:15 AM +11:00", "2024-01-09 9:15 AM +10:00"],
                       "Qty": "1", "Price": "10"})

    dates = parse_transactions(df, {"Date": "transaction_date", "Qty": "quantity",
                                    "Price": "unit_price"}).dates

    assert [str(d) for d in dates] == ["2024-01-06 01:00:00", "2024-01-07 02:00:00",
                                       "2024-01-05 00:00:00", "2024-01-08 09:15:00",
                                       "2024-01-09 09:15:00"]


def test_a_hidden_zone_beside_a_date_only_cell_does_not_crash() -> None:
    """2E-h doubt-review cycle 3 F2, the reviewer's own cells (mutation check
    H11): the zoned cells and the date-only one cannot share a column parse,
    "2024-01-05" is read alone, and the rest came back zone-aware."""
    df = pd.DataFrame({"Date": ["Sat Jan 06 01:00:00 +0000 2024", "Sun Jan 07 02:00:00 +0000 2024",
                                "2024-01-05"], "Qty": "1", "Price": "10"})

    dates = parse_transactions(df, {"Date": "transaction_date", "Qty": "quantity",
                                    "Price": "unit_price"}).dates

    assert [str(d) for d in dates] == ["2024-01-06 01:00:00", "2024-01-07 02:00:00",
                                       "2024-01-05 00:00:00"]


def test_a_year_out_of_range_in_the_one_by_one_read_is_no_date_not_a_crash() -> None:
    """2E-h doubt-review cycle 3 F3: "9999-12-31" (a placeholder) or "Aug 5"
    (the year 1) read one by one overflowed the nanosecond column."""
    df = pd.DataFrame({"Date": ["Sat, 06 Jan 2024 01:00:00 +1100 (AEDT)",
                                "Sat, 08 Jun 2024 01:00:00 +1000 (AEST)", "9999-12-31", "Aug 5"],
                       "Qty": "1", "Price": "10"})

    dates = parse_transactions(df, {"Date": "transaction_date", "Qty": "quantity",
                                    "Price": "unit_price"}).dates

    assert [str(d) for d in dates] == ["2024-01-06 01:00:00", "2024-06-08 01:00:00", "NaT", "NaT"]


def test_a_dotnet_offset_column_is_read_as_a_column(monkeypatch: pytest.MonkeyPatch) -> None:
    """2E-h doubt-review cycle 3 F4: .NET's "1/6/2024 9:15:02 AM -05:00" (a
    12-hour clock, a one-digit hour) escaped the offset pattern, so a whole
    column across a daylight-saving change was read one cell at a time -
    about 280 s per read at 650,000 rows. Its offsets are cut before the
    column is parsed; the one-by-one read is not needed."""
    from shared import dates as shared_dates

    def refuse(*_args: object, **_kwargs: object) -> pd.Series:
        raise AssertionError("read one cell at a time")

    monkeypatch.setattr(shared_dates, "_each_on_its_own_clock", refuse)
    df = pd.DataFrame({"Date": ["1/6/2024 9:15:02 AM -05:00", "7/6/2024 9:15:02 PM -04:00"],
                       "Qty": "1", "Price": "10"})

    dates = parse_transactions(df, {"Date": "transaction_date", "Qty": "quantity",
                                    "Price": "unit_price"}).dates

    assert [str(d) for d in dates] == ["2024-01-06 09:15:02", "2024-07-06 21:15:02"]


def test_a_credit_notes_customer_is_not_taken_from_a_restock_line() -> None:
    """2E-h doubt-review F4: credit note CN1's refund line carries no name; a
    stock-in line under CN1 the same day names "Warehouse". An "in" line is
    no part of the credit note, so it names no customer for it."""
    mapping = {"Date": "transaction_date", "Qty": "quantity", "Price": "unit_price",
               "Cust": "customer", "Inv": "order_id", "Type": "transaction_type"}
    rows = [("2026-08-10", "-1", "500", None, "CN1", "out"),
            ("2026-08-10", "1", "500", "Warehouse", "CN1", "in")]
    rows += [("2026-08-11", "1", "10", f"Pad{i}", f"p{i}", "out") for i in range(10)]
    df = pd.DataFrame(rows, columns=["Date", "Qty", "Price", "Cust", "Inv", "Type"])

    parsed = parse_transactions(df, mapping, FIRST_LINE)

    assert parsed.orders_basis == "order_id"
    assert pd.isna(parsed.customers.iloc[0])


def test_lines_with_no_readable_date_are_counted_with_a_reason() -> None:
    """Thach: never dropped silently. The shop plus a blank date, "now" and
    "10:30": 3 lines without a readable date, said so in metrics.json. The
    reason does not split blank from not-a-date: a plan that parsed the
    column has already turned every not-a-date blank (2E-h review F5)."""
    rows = _sydney_shop()
    rows += [{**row(date(2026, 8, 3)), "Date": value} for value in ("", "now", "10:30")]

    core = run_data(rows).metrics.core

    assert core.undated_lines == 3
    assert core.undated_lines_reason.startswith("3 lines have no readable date")


def test_one_undated_line_is_said_in_the_singular() -> None:
    rows = _sydney_shop() + [{**row(date(2026, 8, 3)), "Date": "now"}]

    core = run_data(rows).metrics.core

    assert core.undated_lines_reason.startswith("1 line has no readable date")


def test_a_file_whose_dates_all_read_has_no_undated_lines() -> None:
    core = run_data(_sydney_shop()).metrics.core

    assert (core.undated_lines, core.undated_lines_reason) == (0, None)


def test_undated_lines_and_their_reason_come_together() -> None:
    """The contract pairs the count with its reason: never a count with no
    reason, never a reason beside 0."""
    from pydantic import ValidationError

    from tests.contracts.test_metrics import metrics_payload

    for count, reason in ((3, None), (0, "why")):
        payload = metrics_payload()
        payload["core"].update({"undated_lines": count, "undated_lines_reason": reason})
        with pytest.raises(ValidationError, match="undated_lines"):
            MetricsContract.model_validate(payload)


def test_a_returns_only_id_is_judged_on_its_counted_lines() -> None:
    """2E-f review cycle 4 F2: a credit note C9 (return lines, the customer
    on its first) with a restock line "in" under C9 the next day was judged
    on every dated line, "spanned" two days and was not filled."""
    mapping = {"Date": "transaction_date", "Qty": "quantity", "Price": "unit_price",
               "Cust": "customer", "Inv": "order_id", "Type": "transaction_type"}
    rows = [("2026-08-05", "-1", "10", "Ann", "C9", "out"), ("2026-08-05", "-2", "10", None, "C9", "out"),
            ("2026-08-06", "3", "10", None, "C9", "in")]
    rows += [("2026-08-10", "1", "10", f"Pad{i}", f"p{i}", "out") for i in range(10)]
    df = pd.DataFrame(rows, columns=["Date", "Qty", "Price", "Cust", "Inv", "Type"])

    parsed = parse_transactions(df, mapping, FIRST_LINE)

    assert parsed.orders_basis == "order_id"
    assert parsed.customers.iloc[1] == "ann"


def test_versions() -> None:
    # 8.0 / 7.0 in 2E-h; 9.0 / 8.0 since 2E-e2 (test_2ee2_stage2.py).
    assert SCHEMA_VERSION == "11.0"  # 9.0 / 8.0 in 2E-e2; 10.0 / 9.0 in 2E-k; 11.0 / 10.0 since 2E-d2
    assert MetricsContract.supported_major == 11
    assert DiagnosisContract.supported_major == 10
