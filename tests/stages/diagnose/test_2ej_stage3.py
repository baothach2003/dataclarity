"""Session 2E-j (Thach, Q1 of 2E-h), stage 3, written before the change: a
month-grain file records months, not days, so the day-level steps do not
apply and say so.

- D1 (days of data missing): not applicable, "the file records months, not
  days" - it read "Coverage matches this store's normal trading pattern", a
  check that never ran. Not "inconclusive": that would badge every monthly
  file "caution" (review cycle 1 #11). The D1 hypothesis: not_testable.
- T2's zero-day guard and B1's missing-day refusal are day-level too: they
  do not apply, and seasonality reads the months (review cycle 1 #3).
- The calendar: method "not_applicable", no effect - its weekday weights
  were all 0 (every day but the 1st holds nothing), and T1 "ruled out" the
  calendar on no evidence. T1: not_testable.
- R3 (a stockout: a run of days without a sale): not_testable.
- The file's last month is compared (stage 2), and every month of it is a
  complete month for the history.
- diagnosis.json 15.0.
"""

import pytest
from pydantic import ValidationError

from contracts.diagnosis import Calendar, DiagnosisContract
from datetime import date

from stages.diagnose.calendar_effect import compute_calendar
from stages.diagnose.frame import build_frame, history_window
from stages.diagnose.hypotheses import evaluate_hypotheses
from stages.diagnose.lever import month_revenue
from stages.diagnose.localization import compute_localization
from stages.diagnose.signals import compute_signals
from stages.diagnose.step7_inputs import Step7Inputs
from stages.diagnose.tree import compute_tree
from stages.diagnose.trust import evaluate_trust
from tests.stages.analyze.test_2ej_stage2 import month_grain_rows
from tests.stages.diagnose.diagnose_fixtures import daily_rows, month_span, run_data

MONTHS = "the file records months, not days"


def _steps(rows: list[dict]):
    data = run_data(rows)
    history = history_window(data)
    trust = evaluate_trust(data, history)
    period = data.metrics.period
    calendar = compute_calendar(data, history)
    inputs = Step7Inputs(
        data, history, build_frame(data), trust, calendar, compute_signals(data, history),
        compute_tree(data, history),
        compute_localization(data, month_revenue(data, period.current)
                             - month_revenue(data, period.previous)))
    return data, trust, calendar, {h.id: h for h in evaluate_hypotheses(inputs)}


def test_every_month_of_a_month_grain_file_is_complete() -> None:
    data = run_data(month_grain_rows())

    assert data.complete_months[0] == "2024-01"
    assert data.complete_months[-1] == "2025-12"
    assert len(data.complete_months) == 24


def test_d1_does_not_apply_and_says_so() -> None:
    _, trust, _, hypotheses = _steps(month_grain_rows())
    d1 = next(check for check in trust.checks if check.id == "D1")

    assert d1.status == "not_applicable"
    assert d1.message is not None and MONTHS in d1.message
    assert trust.verdict == "trusted"
    assert hypotheses["D1"].verdict == "not_testable"
    assert MONTHS in hypotheses["D1"].rule


def test_the_calendar_does_not_apply_and_says_so() -> None:
    data, _, calendar, hypotheses = _steps(month_grain_rows())
    change = data.metrics.core.revenue_current - data.metrics.core.revenue_previous

    assert calendar.method == "not_applicable"
    assert (calendar.expected_cur, calendar.expected_prev) == (None, None)
    assert calendar.calendar_effect == 0.0
    assert calendar.calendar_adjusted_change == change == -420.0
    assert MONTHS in str(calendar.evidence["reason"])
    assert hypotheses["T1"].verdict == "not_testable"
    assert MONTHS in hypotheses["T1"].rule


def test_a_stockout_run_does_not_apply_and_says_so() -> None:
    _, _, _, hypotheses = _steps(month_grain_rows())

    assert hypotheses["R3"].verdict == "not_testable"
    assert MONTHS in hypotheses["R3"].rule


def test_a_daily_file_keeps_its_day_level_steps() -> None:
    start, end = month_span("2025-01", 14)
    _, trust, calendar, hypotheses = _steps(daily_rows(start, end, products=3))

    assert next(c for c in trust.checks if c.id == "D1").status == "ok"
    assert calendar.method == "weekday_weights"
    assert hypotheses["T1"].verdict != "not_testable"
    assert hypotheses["R3"].verdict != "not_testable"


def test_diagnosis_json_is_15() -> None:
    assert DiagnosisContract.supported_major == 15


def test_the_calendar_contract_ties_null_expectations_to_not_applicable() -> None:
    fields = {"calendar_effect": 0.0, "calendar_adjusted_change": -420.0, "evidence": {}}
    with pytest.raises(ValidationError, match="null exactly when"):
        Calendar(method="weekday_weights", expected_cur=None, expected_prev=None, **fields)
    with pytest.raises(ValidationError, match="null exactly when"):
        Calendar(method="not_applicable", expected_cur=1.0, expected_prev=1.0, **fields)
    with pytest.raises(ValidationError, match="no effect"):
        Calendar(method="not_applicable", expected_cur=None, expected_prev=None,
                 **(fields | {"calendar_effect": 5.0}))


def seasonal_month_grain_rows() -> list[dict]:
    """36 months, 2023-01 to 2025-12, on the 1st: three products x ten
    customers x one unit at 2 = 60 a month; every December doubles it (120)."""
    rows = []
    for index in range(36):
        year, month = 2023 + index // 12, index % 12 + 1
        qty = 2 if month == 12 else 1
        for product in range(3):
            for customer in range(10):
                rows.append({"Date": date(year, month, 1).isoformat(), "Qty": str(qty),
                             "Price": "2", "Product": f"P{product}", "Cust": f"C{customer}"})
    return rows


def test_seasonality_reads_the_months_of_a_month_grain_file() -> None:
    """2025-11 -> 2025-12 is 60 -> 120; a year earlier 60 -> 120 too, so
    seasonality is +60 of +60. Refused before on "days with no
    sales beyond this store's pattern" (review cycle 1 #3)."""
    data, _, _, hypotheses = _steps(seasonal_month_grain_rows())

    assert (data.metrics.core.revenue_previous, data.metrics.core.revenue_current) == (60.0, 120.0)
    t2 = hypotheses["T2"]
    assert t2.verdict == "supported"
    assert t2.contribution == 60.0
    assert MONTHS in str(t2.evidence["zero_day_guard"])
    assert "a day with no sales" not in hypotheses["B1"].rule
