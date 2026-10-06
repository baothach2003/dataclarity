"""The scoped review of step 1's cycle-3 fix (Thach, 2026-10-05, item 1c):
what it found, pinned. docs/REPORT_REDESIGN.md section 12."""

from datetime import date

import numpy as np
import pytest
from pydantic import ValidationError

from contracts.diagnosis import DiagnosisContract, Lever
from contracts.lever_bridge import BridgeBar, allocate_cents
from stages.diagnose.assemble import diagnose
from stages.diagnose.lever import PeriodTotals, lever_from_totals
from tests.stages.diagnose.diagnose_fixtures import NOW, daily_months, daily_rows, row, run_data
from tests.stages.diagnose.test_redesign_year_ago_hedge import FOURTEEN

DEC = PeriodTotals(revenue=100.0, orders=12, customers=10, units=20.0)


# --- #1: rule A's tolerance, pinned on the case that splits the two readings -----------------------


@pytest.mark.parametrize("orders,customers", [(23, 21), (29, 7)])
def test_a_month_printing_zero_whose_product_prints_a_cent_is_not_positive(orders: int, customers: int) -> None:
    # Revenue 0.004999999999999999 prints 0.00, while level 1's product is exactly 0.005 and prints 0.01:
    # stage 3 reads the revenue; the contract must accept it (the cycle-3 crash, then failed_checks).
    previous = PeriodTotals(revenue=0.004999999999999999, orders=orders, customers=customers, units=float(orders))

    lever = lever_from_totals(previous, DEC, has_customers=True, typical=50.0, refunds=False)

    assert (lever.bridge, lever.bridge_withheld) == (None, "month_not_positive")


def test_the_reviews_end_to_end_month_is_not_positive_not_failed_checks() -> None:
    rows = [row(date(2024, 10, day), qty=1.0, price=10.0, customer=f"C{day % 5}") for day in range(1, 32)]
    rows += [row(date(2024, 11, 1 + index), qty=1.0, price=0.001, customer=f"C{index % 21}") for index in range(23)]
    rows += [row(date(2024, 11, 30), qty=-1.0, price=0.018, customer="C0")]

    found = diagnose(run_data(rows), NOW)

    assert found.tree.lever.bridge_withheld == "month_not_positive"


# --- #2: the real cause is raised when the bridge was not it -----------------------------------------


def test_with_the_bridge_and_another_rule_broken_the_other_rule_is_raised(monkeypatch) -> None:
    # The B2 tie (the bridge's) is checked before the year-ago tie in the same validator: withholding the
    # bridge leaves the year-ago refusal, which is the real cause and is what is raised.
    from contracts.diagnosis import YearAgo
    from stages.diagnose import assemble
    from stages.diagnose import lever as lever_module

    monkeypatch.setattr(lever_module, "refund_lines", lambda data: {"prev": 1, "cur": 0})
    monkeypatch.setattr(assemble, "_year_ago", lambda frame, trust, hypotheses: {
        "year_ago": YearAgo(previous=frame.year_ago_previous, current=frame.year_ago_current,
                            revenue_previous=1.0, revenue_current=2.0), "year_ago_reason": None})

    with pytest.raises(ValidationError, match="pair T2 reads"):
        diagnose(run_data(daily_months(FOURTEEN)), NOW)


# --- #3: year_ago is T2's pair by construction ---------------------------------------------------------


def test_year_ago_is_t2s_own_evidence_exactly() -> None:
    found = diagnose(run_data(daily_months(FOURTEEN)), NOW)
    t2 = next(h for h in found.hypotheses if h.id == "T2")

    assert (found.year_ago.revenue_previous, found.year_ago.revenue_current) == (
        t2.evidence["ly_prev"], t2.evidence["ly_cur"])


def test_a_t2_that_rounds_its_evidence_does_not_take_the_diagnosis_down(monkeypatch) -> None:
    from stages.diagnose import hypothesis_evidence_time as time_evidence

    real = time_evidence.month_revenue
    monkeypatch.setattr(time_evidence, "month_revenue", lambda data, month: round(real(data, month), 1) + 0.04)

    found = diagnose(run_data(daily_months(FOURTEEN)), NOW)
    t2 = next(h for h in found.hypotheses if h.id == "T2")

    assert found.year_ago.revenue_previous == t2.evidence["ly_prev"]


# --- #4: what stage 3 writes after withholding the bridge reloads ------------------------------------


def test_a_file_written_without_its_bridge_reloads(monkeypatch) -> None:
    from stages.diagnose import lever as lever_module

    monkeypatch.setattr(lever_module, "refund_lines", lambda data: {"prev": 1, "cur": 0})
    found = diagnose(run_data(daily_months(FOURTEEN)), NOW)

    assert found.tree.lever.bridge_withheld == "failed_checks"
    assert DiagnosisContract.model_validate_json(found.model_dump_json()) == found


# --- #5: residue is under half a cent too ----------------------------------------------------------


def test_a_real_movement_beside_a_huge_term_is_not_residue() -> None:
    # 0.09 beside 1e8 is within a billionth of it, but 9 cents moved: it stays (the review's case).
    assert allocate_cents([1e8, 0.09], 10_000_000_009) == [10_000_000_000, 9]


def test_a_residue_term_shown_as_zero_passes_its_bar() -> None:
    for term in (1e-13, -1e-13, 0.004, -0.004):
        assert BridgeBar(factor="customers", value_prev=1.0, value_cur=1.0, contribution=term, shown=0.0)


def test_the_residue_boundary_is_a_billionth_of_the_largest_term() -> None:
    # 1e-9 x 1,000 = 1e-6. Beside 1,000.00 (remainder 0) the tiny term holds the larger remainder, so the
    # left cent goes to it - unless it is residue: at the boundary it never moves, twice it, it may.
    assert allocate_cents([1000.0, 1e-6], 100_001) == [100_001, 0]
    assert allocate_cents([1000.0, 2e-6], 100_001) == [100_000, 1]


# --- #6: never a crash on a numpy float --------------------------------------------------------------


def test_numpy_floats_allocate_like_floats() -> None:
    # 301 cents leaves one to place, so the remainders are read too.
    assert allocate_cents([np.float64(1.004), np.float64(2.0)], 301) == allocate_cents([1.004, 2.0], 301) == [101, 200]


# --- #7: each rule pinned alone ----------------------------------------------------------------------


@pytest.mark.parametrize("field", ["hedge", "year_ago_reason", "bridge_withheld"])
def test_an_18_3_file_carrying_any_one_new_field_is_refused(field: str) -> None:
    from contracts.diagnosis import HEDGE_SENTENCES

    found = diagnose(run_data(daily_months(FOURTEEN)), NOW).model_dump()
    found["schema_version"] = "18.3"
    found["year_ago"] = None
    found["tree"]["lever"]["bridge"] = None
    found["headline"]["named"] = None  # 18.6's field, not the one under test
    found["headline"]["offsetting"] = None  # 18.7's fields, not the ones under test
    for check in found["trust"]["checks"]:
        check["month"] = None
    if field == "hedge":
        found["headline"] = {"rule": 4, "hypothesis_id": None, "lens": None, "movement": None, "hedge": "plain",
                             "message": "x " + HEDGE_SENTENCES["plain"]}
    elif field == "year_ago_reason":
        found["year_ago_reason"] = "the year-ago pair is not in the data"
    else:
        found["tree"]["lever"]["bridge_withheld"] = "not_to_the_cent"

    with pytest.raises(ValidationError, match="before 18.4"):
        DiagnosisContract.model_validate(found)


def test_year_ago_current_other_than_t2s_is_refused() -> None:
    found = diagnose(run_data(daily_months(FOURTEEN)), NOW).model_dump()
    found["year_ago"]["revenue_current"] += 1.0

    with pytest.raises(ValidationError, match="pair T2 reads"):
        DiagnosisContract.model_validate(found)


def test_a_blocked_run_with_a_year_ago_pair_gives_the_blocked_reason() -> None:
    # Thirteen full months, then a February with sales on 6 of its 29 days: D1 blocks the current month
    # while the frame still finds last year's pair.
    rows = (daily_rows(date(2023, 1, 1), date(2024, 1, 31)) + daily_rows(date(2024, 2, 1), date(2024, 2, 5))
            + daily_rows(date(2024, 2, 29), date(2024, 2, 29)))
    found = diagnose(run_data(rows), NOW)

    assert found.trust.verdict == "blocked"
    assert found.frame.year_ago_previous is not None
    assert (found.year_ago, found.year_ago_reason) == (None, "the diagnosis is blocked")


# --- #8: the other withholding codes beside months level 1 shows at zero or below --------------------


@pytest.mark.parametrize("code", ["not_to_the_cent", "failed_checks"])
def test_another_withholding_beside_a_month_at_zero_or_below_is_refused(code: str) -> None:
    previous = PeriodTotals(revenue=-50.0, orders=10, customers=5, units=20.0)
    data = lever_from_totals(previous, DEC, has_customers=True, typical=50.0, refunds=False).model_dump()
    assert data["bridge_withheld"] == "month_not_positive"
    data["bridge_withheld"] = code

    with pytest.raises(ValidationError, match="month_not_positive"):
        Lever.model_validate(data)
