"""Session 2E-e, stage 3 (Thach), written before the change: the lever,
step 4 and localization count orders by `order_id` when it is mapped; the
wording says "lines" when it is not (a lines basis is a correct reading, not
a refusal); the category AOV split is refused when an order spans
categories; diagnosis.json 4.0.
"""

from datetime import date, timedelta

import pytest
from pydantic import ValidationError

from contracts.diagnosis import DiagnosisContract
from stages.diagnose.frame import history_window
from stages.diagnose.headline import choose_headline
from stages.diagnose.hypotheses import evaluate_hypotheses
from stages.diagnose.lever import period_totals
from stages.diagnose.members import product_totals
from stages.diagnose.mix_rate import compute_mix_rate
from stages.diagnose.signals import compute_signals
from stages.diagnose.step7_inputs import Changes
from tests.contracts.test_diagnosis import diagnosis_payload
from tests.stages.diagnose.diagnose_fixtures import MAPPING, row, run_data
from tests.stages.diagnose.test_2ec2_stage3 import _smaller_baskets
from tests.stages.diagnose.test_headline import catalog, tree, trust
from tests.stages.diagnose.test_hypotheses import by_id, step7

WITH_ORDERS = {**MAPPING, "Inv": "order_id"}


def _invoiced() -> list[dict]:
    """July: five invoices of two lines (product W twice). August: four
    invoices of three lines."""
    rows = []
    for index in range(5):
        rows += [{**row(date(2026, 7, 1 + index), customer=f"C{index}"), "Inv": f"J{index}"}
                 for _ in range(2)]
    for index in range(4):
        rows += [{**row(date(2026, 8, 1 + index), customer=f"C{index}"), "Inv": f"A{index}"}
                 for _ in range(3)]
    rows.append({**row(date(2026, 9, 1), customer="C0"), "Inv": "S"})
    return rows


def test_the_lever_counts_invoices_as_stage_2_does() -> None:
    """August: 4 orders from 4 buyers (frequency 1), 12 units, so 3 units
    per order - and the same order count as metrics.json."""
    data = run_data(_invoiced(), WITH_ORDERS)
    totals = period_totals(data, "2026-08")

    assert totals.orders == data.metrics.core.orders_current == 4
    assert (totals.customers, totals.units) == (4, pytest.approx(12.0))


def test_a_product_counts_the_orders_that_contain_it() -> None:
    """Product Widget sits on every line: 4 August orders contain it, not
    12 lines."""
    totals = product_totals(run_data(_invoiced(), WITH_ORDERS))

    assert int(totals.orders_cur.sum()) == 4


def test_basket_wording_says_lines_when_there_is_no_order_id() -> None:
    """2E-c2's smaller baskets (3 -> 2 units), no order_id mapped: the
    same verdict, worded on what was measured - units per LINE."""
    b2 = by_id(evaluate_hypotheses(step7(run_data(_smaller_baskets([])))))["B2"]

    assert (b2.verdict, b2.statement) == ("supported", "Lines carried fewer units")


def test_basket_wording_says_baskets_when_order_id_is_mapped() -> None:
    """The same file with one invoice per line (the Kaggle shape): the
    figures are identical and the wording is about baskets."""
    rows = [{**r, "Inv": f"T{i}"} for i, r in enumerate(_smaller_baskets([]))]

    b2 = by_id(evaluate_hypotheses(step7(run_data(rows, WITH_ORDERS))))["B2"]

    assert (b2.verdict, b2.statement) == ("supported", "Baskets got smaller")


def test_rule_4_names_lines_or_orders_by_basis() -> None:
    lines = Changes(1000.0, 840.0, -160.0, -160.0, True)
    orders = Changes(1000.0, 840.0, -160.0, -160.0, True, orders_basis="order_id")

    on_lines = choose_headline(trust(), catalog(), tree(True, -480.0, 320.0), lines).message
    on_orders = choose_headline(trust(), catalog(), tree(True, -480.0, 320.0), orders).message

    assert "lines contributed -480.00" in on_lines
    assert "average line value +320.00" in on_lines
    assert "orders contributed -480.00" in on_orders
    assert "average order value +320.00" in on_orders


def _simpson(span: bool) -> list[dict]:
    """DIAGNOSE_DESIGN 1.3's case (test_localization): both categories' AOV
    rises while the overall AOV falls. Every line is its own invoice - except,
    with `span`, two November invoices each hold a cheap and a dear line."""
    rows = []

    def line(day, qty, price, category, invoice):
        rows.append({**row(day, qty=qty, price=price), "Cat": category, "Inv": invoice})

    for index in range(5):
        line(date(2011, 10, index + 1), 1, 20.0, "Cheap", f"OC{index}")
        line(date(2011, 10, index + 10), 5, 20.0, "Dear", f"OD{index}")
    for index in range(8):
        line(date(2011, 11, 30), 1, 22.0, "Cheap", f"NC{index}")
    for index in range(2):
        line(date(2011, 11, 30), 5, 21.0, "Dear", f"NC{index}" if span else f"ND{index}")
    return rows


def test_the_category_aov_split_is_refused_when_an_order_spans_categories() -> None:
    """Control: one invoice per line, the AOV split stands (as in
    test_localization). With two invoices holding both categories, category
    orders no longer add up to the total (10 against 8), so the AOV split
    would not reconcile to the lever's AOV: refused."""
    mapping = {**WITH_ORDERS, "Cat": "category"}

    control = compute_mix_rate(run_data(_simpson(span=False), mapping))
    spanning = compute_mix_rate(run_data(_simpson(span=True), mapping))

    assert control is not None and control.metric == "aov"
    assert spanning is None or spanning.metric != "aov"


def test_diagnosis_json_is_major_version_4_or_the_current_one() -> None:
    # 4.0 in 2E-e; 5.0 since 2E-f (test_2ef_stage3.py). A 3.x file is refused.
    payload = diagnosis_payload()
    assert DiagnosisContract.model_validate(payload).schema_version == "5.0"

    payload["schema_version"] = "3.0"
    with pytest.raises(ValidationError, match="re-analyse"):
        DiagnosisContract.model_validate(payload)


def test_step_4_counts_orders_by_invoice() -> None:
    """Mutation check (2E-e): one invoice of three lines a day from August 2025
    to August 2026. August 2026's orders series is 31 invoices, not 93 lines."""
    rows, day = [], date(2025, 8, 1)
    while day <= date(2026, 8, 31):
        rows += [{**row(day), "Inv": f"I{day.isoformat()}"} for _ in range(3)]
        day += timedelta(days=1)
    rows.append({**row(date(2026, 9, 1)), "Inv": "S"})
    data = run_data(rows, WITH_ORDERS)

    orders = next(s for s in compute_signals(data, history_window(data)) if s.series == "orders")

    assert orders.value_cur == pytest.approx(31.0)


def test_a_category_counts_each_order_once() -> None:
    """Mutation check (2E-e): the Simpson case with every cheap order holding
    TWO lines (2 x 10, then 2 x 11) on one invoice. Orders per category are
    distinct invoices, so the AOV split still reconciles to the lever's own
    change: (8 x 22 + 2 x 105) / 10 - (5 x 20 + 5 x 100) / 10 = 38.6 - 60."""
    rows = []

    def line(day, qty, price, category, invoice):
        rows.append({**row(day, qty=qty, price=price), "Cat": category, "Inv": invoice})

    for index in range(5):
        for _ in range(2):
            line(date(2011, 10, index + 1), 1, 10.0, "Cheap", f"OC{index}")
        line(date(2011, 10, index + 10), 5, 20.0, "Dear", f"OD{index}")
    for index in range(8):
        for _ in range(2):
            line(date(2011, 11, 30), 1, 11.0, "Cheap", f"NC{index}")
    for index in range(2):
        line(date(2011, 11, 30), 5, 21.0, "Dear", f"ND{index}")

    split = compute_mix_rate(run_data(rows, {**WITH_ORDERS, "Cat": "category"}))

    assert split is not None and split.metric == "aov"
    assert split.mix + split.rate == pytest.approx(38.6 - 60.0)


# --- 2E-e doubt-review, written before the fixes -----------------------------------


def test_a_blocked_run_keeps_the_lines_wording() -> None:
    """F7: the blocked path built B1/B2 with the order wording on a lines
    basis ("Purchase frequency changed"). The blocked-run file of
    test_hypotheses, no order_id mapped."""
    rows = []
    day = date(2011, 1, 1)
    while day <= date(2011, 11, 30):
        if day.month < 11 or day.day == 30:
            rows.append(row(day, qty=10, price=10.0))
        day += timedelta(days=1)

    results = by_id(evaluate_hypotheses(step7(run_data(rows))))

    assert results["B1"].statement == "Lines per customer changed"
    assert results["B2"].statement == "Units per line changed"


def test_an_order_crossing_the_month_boundary_does_not_refuse_the_split() -> None:
    """F8: an order with a Cheap line on 31 October and a Dear line on 1
    November spans two categories only ACROSS months; within each compared
    month every order sits in one category, so the AOV split stands."""
    rows = _simpson(span=False)
    rows.append({**row(date(2011, 10, 31), qty=1, price=20.0), "Cat": "Cheap", "Inv": "X1"})
    rows.append({**row(date(2011, 11, 1), qty=5, price=21.0), "Cat": "Dear", "Inv": "X1"})

    split = compute_mix_rate(run_data(rows, {**WITH_ORDERS, "Cat": "category"}))

    assert split is not None and split.metric == "aov"
