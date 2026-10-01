"""Session 3E2: a customer column mapped but blank for a month (Thach,
2026-09-29, deciding 5A review 3 #2). "Ruled out" claims the cause did not
happen, while the data only failed to show the customers - so the customer
causes are NOT TESTABLE, with that reason, as they are when no column is
mapped. Written before the code (method C7).

Months read (review 1 #2; review 3 #1 withdrew review 2's look-back
window): C1 and C3 every month up to the current one - who is new or
returning is decided by earlier months, and a window let an older blank
month turn returning customers into new ones again; C2 the compared months
and the month before them; B1 and C4 the compared months. A month is
blank when it has sale lines and none names a customer (review 1 #3).
The signals follow stage 2's figure by figure (review 2 #1): active
customers missing when no counted line names one, frequency when sales
have no named buyer.
"""

import pytest

from contracts.cleaning import OrderConfirmations
from contracts.diagnosis import Signal
from stages.diagnose.assemble import diagnose
from tests.stages.diagnose.diagnose_fixtures import MAPPING, NOW, daily_rows, month_span, run_data

CUSTOMER_CAUSES = ("C1", "C2", "C3", "C4", "B1")


def _shop(blank: tuple[str, ...] = (), *, half: str | None = None, written: str = "",
          months: int = 14) -> list[dict]:
    """Four customers buying every day, 2023-01 .. 2024-02 (current 2024-02);
    `months` 26 runs to 2025-02."""
    start, end = month_span("2023-01", months)
    rows = []
    for index, customer in enumerate(("Ann", "Bo", "Cy", "Di")):
        rows += daily_rows(start, end, customer=customer, product=f"P{index}", price=10.0 + index)
    for number, row in enumerate(rows):
        if row["Date"][:7] in blank or (row["Date"][:7] == half and number % 2):
            row["Cust"] = written
    return rows


def _verdicts(rows: list[dict], **kwargs: object) -> dict[str, tuple[str, object]]:
    diagnosis = diagnose(run_data(rows, **kwargs), NOW)  # type: ignore[arg-type]  # MAPPING or confirmations
    return {h.id: (h.verdict, h.evidence.get("reason")) for h in diagnosis.hypotheses}


def _blank(month: str) -> tuple[str, str]:
    return ("not_testable", f"the customer column is mapped but blank for {month}: no sale line names a customer")


@pytest.mark.parametrize("month", ["2024-02", "2024-01"])
def test_a_blank_compared_month_makes_every_customer_cause_not_testable(month: str) -> None:
    verdicts = _verdicts(_shop((month,)))
    assert {i: verdicts[i] for i in CUSTOMER_CAUSES} == dict.fromkeys(CUSTOMER_CAUSES, _blank(month))


def test_a_blank_month_before_the_previous_reaches_the_bridge_differences_only() -> None:
    # C1-C3 subtract the previous transition (2023-12 -> 2024-01); B1 and C4
    # read the two compared months only.
    verdicts = _verdicts(_shop(("2023-12",)))
    assert {i: verdicts[i] for i in ("C1", "C2", "C3")} == dict.fromkeys(("C1", "C2", "C3"), _blank("2023-12"))
    assert verdicts["B1"][0] != "not_testable" and verdicts["C4"][0] != "not_testable"


def test_an_older_blank_month_decides_who_is_new_or_returning() -> None:
    # Review 1 #2: six customers bought only in 2023-10 and come back in the
    # current month. With October blank they read as new - C1 "supported",
    # C3 "ruled out", a false cause in the headline. C1 and C3 classify by
    # every earlier month; C2, B1 and C4 never read October.
    start, end = month_span("2024-02", 1)
    returning = [row for index in range(6) for row in daily_rows(start, end, customer=f"Back{index}",
                                                                  product="P0", price=10.0)]
    october_start, october_end = month_span("2023-10", 1)
    october = [row for index in range(6) for row in daily_rows(october_start, october_end,
                                                                customer=f"Back{index}", product="P0", price=10.0)]
    for row in october:
        row["Cust"] = ""
    rows = _shop() + october + returning
    for row in rows:
        if row["Date"][:7] == "2023-10":
            row["Cust"] = ""
    verdicts = _verdicts(rows)
    assert {i: verdicts[i] for i in ("C1", "C3")} == dict.fromkeys(("C1", "C3"), _blank("2023-10"))
    assert all(verdicts[i][0] != "not_testable" for i in ("C2", "B1", "C4"))


def test_a_month_whose_sale_lines_are_blank_is_blank_beside_a_named_return() -> None:
    # Review 1 #3: one named RETURN line kept the month "named"; frequency
    # per buyer (sale lines) then read 0 and charted "below", C2 "ruled out".
    # Review 2 #1: the signals say what stage 2 says - one active customer
    # (Ann, by her return: layer 1 shows 1), and no frequency (no buyer).
    rows = _shop(("2024-02",)) + [{"Date": "2024-02-20", "Qty": "-1", "Price": "10.0", "Product": "P0",
                                   "Cust": "Ann"}]
    assert _verdicts(rows)["C2"] == _blank("2024-02")
    signals = _signals(rows)
    assert signals[("active_customers", "level")].value_cur == 1.0
    assert signals[("frequency", "level")].insufficient_reason == "no_current_value"
    metrics = run_data(rows).metrics
    assert (metrics.core.active_customers_current, metrics.core.buyers_current) == (1, 0)


def test_known_limit_a_month_with_one_named_sale_line_is_read_as_that_customer() -> None:
    # KNOWN LIMIT (review 1 #3 case B; PROJECT_PLAN 8D "From 3E2"): Thach's
    # decision names a month BLANK; one named line among thousands leaves it
    # named, read as one customer (frequency from that one buyer). Where a
    # mostly-blank month stops being readable needs a threshold of its own.
    rows = _shop(("2024-02",))
    for row in rows:
        if row["Date"] == "2024-02-10" and row["Product"] == "P0":
            row["Cust"] = "Ann"
    verdicts, signals = _verdicts(rows), _signals(rows)
    assert verdicts["C2"][0] != "not_testable"
    assert signals[("active_customers", "level")].value_cur == 1.0


def test_two_blank_months_are_both_named() -> None:
    verdicts = _verdicts(_shop(("2024-01", "2024-02")))
    assert verdicts["C2"] == _blank("2024-01 and 2024-02")


def test_a_month_with_some_blank_lines_keeps_todays_reading() -> None:
    # Half the lines named: the bridge carries the rest as unattributed (2E-f).
    verdicts = _verdicts(_shop(half="2024-02"))
    assert all(verdicts[i][0] != "not_testable" for i in CUSTOMER_CAUSES)


def test_a_named_line_that_is_not_counted_names_no_customer_of_the_month() -> None:
    # Customer figures read counted lines: an unpriced line naming a
    # customer leaves the month's counted lines as blank as they were.
    rows = _shop(("2024-02",)) + [{"Date": "2024-02-15", "Qty": "1", "Price": "n/a", "Product": "P0",
                                   "Cust": "Zed"}]
    assert _verdicts(rows)["C2"] == _blank("2024-02")


def test_no_column_mapped_keeps_its_own_reason_first() -> None:
    mapping = {key: value for key, value in MAPPING.items() if value != "customer"}
    verdicts = _verdicts(_shop(("2024-02",)), mapping=mapping)
    assert {verdicts[i] for i in CUSTOMER_CAUSES} == {("not_testable", "no column is mapped to customer")}


def test_a_month_of_confirmed_walk_ins_is_blank_too() -> None:
    # A confirmed placeholder is no customer (2E-k).
    verdicts = _verdicts(_shop(("2024-02",), written="Guest"),
                         confirmations=OrderConfirmations(customer_placeholders=["Guest"]))
    assert verdicts["C2"] == _blank("2024-02")


def test_unconfirmed_placeholder_text_is_a_customer() -> None:
    verdicts = _verdicts(_shop(("2024-02",), written="Guest"))
    assert verdicts["C2"][0] != "not_testable"


# --- the customer signals: the same reasoning (method C7) -----------------------------------------


def _signals(rows: list[dict]) -> dict[tuple[str, str], Signal]:
    diagnosis = diagnose(run_data(rows), NOW)
    assert diagnosis.signals is not None
    return {(s.series, s.mode): s for s in diagnosis.signals}


def test_a_blank_current_month_has_no_customer_count_to_chart() -> None:
    # It read 0 customers and charted "below" (5A review 3 #2).
    signals = _signals(_shop(("2024-02",)))
    for series in ("active_customers", "frequency"):
        row = signals[(series, "level")]
        assert (row.signal, row.insufficient_reason, row.value_cur) == (
            "insufficient_history", "no_current_value", None)
    assert signals[("orders", "level")].value_cur is not None


def test_a_blank_history_month_never_teaches_zero_customers() -> None:
    # The baseline is the other months: 4 customers each, and their own
    # frequencies (orders per buyer follow the month's days).
    from stages.diagnose.frame import history_window
    from stages.diagnose.signals import monthly_series

    data = run_data(_shop())
    history = [month for month in history_window(data) if month != "2023-06"]
    plain = monthly_series(data).reindex(history)
    holed = _signals(_shop(("2023-06",)))
    assert holed[("active_customers", "level")].center == 4.0
    assert holed[("frequency", "level")].center == pytest.approx(plain["frequency"].mean())


def test_a_blank_year_ago_month_has_no_year_ago_value() -> None:
    # Review 1 #9: "unusable_year_ago_base" says the month netted too little
    # to divide by - a business event; a month whose customers were never
    # recorded has no year-ago value. Current 2025-02, year ago 2024-02.
    signals = _signals(_shop(("2024-02",), months=26))
    for series in ("active_customers", "frequency"):
        assert signals[(series, "level")].mode_fallback == "no_year_ago_value"
    assert signals[("orders", "yoy")].mode == "yoy"


def test_a_blank_month_after_the_current_one_is_not_read() -> None:
    # Review 2 #8: the partial month after the current one never decides it.
    rows = _shop() + [{"Date": "2024-03-05", "Qty": "1", "Price": "10.0", "Product": "P0", "Cust": ""}]
    verdicts = _verdicts(rows)
    assert all(verdicts[i][0] != "not_testable" for i in CUSTOMER_CAUSES)


def test_known_limit_an_old_blank_stretch_refuses_new_and_returning_for_good() -> None:
    """KNOWN LIMIT (8D "From 3E2", SUPPRESS): names recorded only from 2023-06
    on - capture switched on part way - and C1 and C3 are not testable on
    every later month (here 2025-02). Review 2 #7 tried accepting an old
    stretch as left-censoring accepts the file's start; review 3 #1 showed
    that window bringing the false "new customers" back (below). A refusal
    is kept over a false verdict."""
    verdicts = _verdicts(_shop(("2023-01", "2023-02", "2023-03", "2023-04", "2023-05"), months=26))
    assert {i: verdicts[i][0] for i in ("C1", "C3")} == dict.fromkeys(("C1", "C3"), "not_testable")
    assert all(verdicts[i][0] != "not_testable" for i in ("C2", "B1", "C4"))


def test_an_isolated_old_blank_month_never_turns_returning_customers_new() -> None:
    # Review 3 #1: six customers buy only in a blank 2023-08 and come back in
    # 2024-02. Read through a window, C1 came out "supported" and named in
    # the headline ("new customers brought in more revenue"), C3 "ruled out".
    start, end = month_span("2024-02", 1)
    back = [row for index in range(6) for row in daily_rows(start, end, customer=f"Back{index}",
                                                            product="P0", price=10.0)]
    august_start, august_end = month_span("2023-08", 1)
    august = [row for index in range(6) for row in daily_rows(august_start, august_end,
                                                              customer=f"Back{index}", product="P0", price=10.0)]
    rows = _shop() + august + back
    for row in rows:
        if row["Date"][:7] == "2023-08":
            row["Cust"] = ""
    verdicts = _verdicts(rows)
    assert {i: verdicts[i] for i in ("C1", "C3")} == dict.fromkeys(("C1", "C3"), _blank("2023-08"))


def test_a_customer_column_blank_on_every_line() -> None:
    # Review 2 #3, CLAUDE.md 5's all-null edge case: every customer cause
    # not testable with a reason that stays readable, and no customer chart
    # sent looking for more history ("too_few_points") that would not help.
    verdicts, signals = _verdicts(_shop(tuple(f"{y}-{m:02d}" for y, m in
                                              [(2023, n) for n in range(1, 13)] + [(2024, 1), (2024, 2)]))), None
    assert verdicts["C1"] == _blank("14 months between 2023-01 and 2024-02")
    assert verdicts["C2"] == _blank("3 months between 2023-12 and 2024-02")
    assert verdicts["B1"] == _blank("2024-01 and 2024-02")
    signals = _signals(_shop(tuple(f"{y}-{m:02d}" for y, m in
                                   [(2023, n) for n in range(1, 13)] + [(2024, 1), (2024, 2)])))
    assert [signals[(s, "level")].insufficient_reason for s in ("active_customers", "frequency")] == [
        "no_current_value", "no_current_value"]


def test_known_limit_a_month_with_no_lines_charts_zero_customers() -> None:
    """KNOWN LIMIT (3B's recorded defect, signals.py `_fallback_reason`): a
    month holding no line at all charts 0, as its revenue does, rather than
    missing. Only a month WITH lines but no named customer is unmeasured
    (3E2) - the empty month is a gap, which stage 3 does not yet chart as one."""
    from stages.diagnose.signals import monthly_series

    rows = [row for row in _shop() if row["Date"][:7] != "2023-06"]
    series = monthly_series(run_data(rows)).loc["2023-06"]
    assert (series["revenue"], series["active_customers"], series["frequency"]) == (0.0, 0.0, 0.0)


def test_a_year_ago_month_with_lines_but_no_named_customer_has_no_year_ago_value() -> None:
    # Review 3 #3: the fallback follows each figure, as the series do - a
    # year-ago month holding only an unnamed return line has no customer
    # figure, though it has lines and no sale line to be "blank" on.
    rows = [row for row in _shop(months=26) if row["Date"][:7] != "2024-02"]
    rows.append({"Date": "2024-02-10", "Qty": "-1", "Price": "10.0", "Product": "P0", "Cust": ""})
    signals = _signals(rows)
    assert signals[("active_customers", "level")].mode_fallback == "no_year_ago_value"


def test_the_reason_never_reads_as_a_run_of_months() -> None:
    # Review 3 #7: three blank months apart are not "2023-09 to 2024-02".
    verdicts = _verdicts(_shop(("2023-09", "2023-12", "2024-02")))
    assert verdicts["C1"] == _blank("3 months between 2023-09 and 2024-02")
