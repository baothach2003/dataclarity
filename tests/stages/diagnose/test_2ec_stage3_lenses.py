"""Session 2E-c, stage 3 (Thach), written before the change: every lens reads
the ONE sale-row definition (quantity > 0 AND a positive amount). The product
lens, the level-1 gross/returns split and the stockout detector tested
quantity > 0 on their own, so a negative-price line was a product sale and a
free item a day's sale. A line that is neither a sale nor a return (a coupon,
a discount, a bad-debt write-off) is a DEDUCTION: its money stays in net
revenue and lands in the returns lens's own deductions term (Thach, option A;
diagnosis.json 2.0)."""

from datetime import date, timedelta

import pytest
from pydantic import ValidationError

from contracts.diagnosis import DiagnosisContract
from stages.diagnose.frame import history_window
from stages.diagnose.headline import choose_headline
from stages.diagnose.mix_rate import compute_mix_rate
from stages.diagnose.signals import compute_signals
from stages.diagnose.hypotheses import decomposition_gross, evaluate_hypotheses
from stages.diagnose.step7_inputs import changes
from stages.diagnose.stockout import detect_stockouts
from stages.diagnose.trust import evaluate_trust
from tests.contracts.test_diagnosis import diagnosis_payload
from tests.stages.diagnose.diagnose_fixtures import MAPPING, daily_rows, month_span, row, run_data
from tests.stages.diagnose.test_hypotheses import by_id, step7


def _month(year: int, month: int):
    day = date(year, month, 1)
    while day.month == month:
        yield day
        day += timedelta(days=1)


def _history() -> list[dict]:
    rows = []
    for year, month in [(2025, m) for m in range(9, 13)] + [(2026, m) for m in range(1, 7)]:
        rows += [row(d, qty=1.0, price=30.0, customer=f"C{d.day % 10}") for d in _month(year, month)]
    return rows


def _refunds_at_a_negative_price() -> list[dict]:
    """Every real basket in July and August is 3 units at 30 (three a day);
    August adds twelve refunds booked as quantity 1 at -90. By hand: July
    8,370; August 8,370 - 1,080 = 7,290; no price changed."""
    rows = _history()
    for month in (7, 8):
        for d in _month(2026, month):
            rows += [row(d, qty=3.0, price=30.0, customer=f"C{(d.day + k) % 10}") for k in range(3)]
    rows += [row(date(2026, 8, 2 * d), qty=1.0, price=-90.0, customer=f"C{d % 10}")
             for d in range(1, 13)]
    rows.append(row(date(2026, 9, 1), qty=1.0, price=30.0, customer="C1"))
    return rows


def test_a_negative_price_refund_is_not_a_price_cut() -> None:
    """2E-b review P1: P1 headlined "like-for-like prices changed" (-1,410.31
    against -1,080, share -1.31) while no price changed."""
    inputs = step7(run_data(_refunds_at_a_negative_price()))
    results = evaluate_hypotheses(inputs)
    headline = choose_headline(inputs.trust, results, inputs.tree, changes(inputs))

    assert by_id(results)["P1"].verdict != "supported"
    assert headline.hypothesis_id != "P1"


def test_a_negative_price_line_is_a_deduction_not_gross_sales() -> None:
    """Gross sales are the sale rows: 8,370 in both months. The twelve lines
    are deductions: 1,080 in August. Returns (quantity < 0) stay 0. The
    identity delta_net = delta_gross - delta_returns - delta_deductions is
    -1,080 = 0 - 0 - 1,080."""
    tree = step7(run_data(_refunds_at_a_negative_price())).tree

    assert tree.returns.gross_prev == pytest.approx(8370.0)
    assert tree.returns.gross_cur == pytest.approx(8370.0)
    assert tree.returns.returns_cur == pytest.approx(0.0)
    assert tree.returns.deductions_prev == pytest.approx(0.0)
    assert tree.returns.deductions_cur == pytest.approx(1080.0)


def test_coupon_lines_do_not_make_customers_buy_more_often() -> None:
    """2E-b review F1: July 10 customers, 3 orders a day; August 20 customers,
    6 orders a day - frequency 9.3 in both. Forty coupon lines (1 @ -30) in
    August took frequency to 11.3 and B1 to "Customers bought more often",
    supported. They are not orders: frequency stays 93/10 = 186/20 = 9.3."""
    rows = _history()
    rows += [row(d, qty=1.0, price=30.0, customer=f"C{(d.day + k) % 10}")
             for d in _month(2026, 7) for k in range(3)]
    rows += [row(d, qty=1.0, price=30.0, customer=f"C{(d.day + k) % 20}")
             for d in _month(2026, 8) for k in range(6)]
    rows += [row(date(2026, 8, 1 + (i % 28)), qty=1.0, price=-30.0, customer=f"C{i % 20}")
             for i in range(40)]
    rows.append(row(date(2026, 9, 1), qty=1.0, price=30.0, customer="C1"))

    inputs = step7(run_data(rows))
    frequency = next(f for f in inputs.tree.lever.level1.factors if f.name == "frequency")

    assert frequency.value_prev == pytest.approx(9.3)
    assert frequency.value_cur == pytest.approx(9.3)
    assert by_id(evaluate_hypotheses(inputs))["B1"].verdict != "supported"


def _stockout_shop(free_items_while_out: bool) -> list[dict]:
    """test_stockout.py's shop: B sells every day of October and November
    2011; A sells every October day and 1-20 November, then stops. Here the
    till also books A as a FREE item (1 @ 0) on 21-30 November."""
    rows = []
    day = date(2011, 10, 1)
    while day <= date(2011, 11, 30):
        rows.append(row(day, qty=1, price=10.0, product="B"))
        if day.month == 10 or day.day <= 20:
            rows.append(row(day, qty=1, price=100.0, product="A"))
        elif free_items_while_out:
            rows.append(row(day, qty=1, price=0.0, product="A"))
        day += timedelta(days=1)
    return rows


def test_a_free_item_is_not_a_sale_to_the_stockout_detector() -> None:
    """Without the free lines A is flagged: a 10-day run, contribution
    -(3,100 / 31) x 10 = -1,000. A free item sells nothing, so the same run
    is found with them."""
    found = detect_stockouts(run_data(_stockout_shop(free_items_while_out=True)))

    assert [item.product for item in found] == ["A"]
    assert found[0].zero_run_days == 10
    assert found[0].contribution == pytest.approx(-1000.0)


def _d1_evidence(free_items_on_the_gap: bool) -> dict:
    """A shop trading every day from August 2025 to August 2026 misses 10-14
    August 2026 - five days with no sale. The variant books a free item (1 @
    0) on each of those days."""
    start, end = month_span("2025-08", 13)
    gap = tuple(date(2026, 8, d) for d in range(10, 15))
    rows = daily_rows(start, end, skip=gap)
    if free_items_on_the_gap:
        rows += [row(day, qty=1.0, price=0.0) for day in gap]
    rows.append(row(date(2026, 9, 1)))
    data = run_data(rows)
    check = next(c for c in evaluate_trust(data, history_window(data)).checks if c.id == "D1")
    return check.evidence


def test_a_day_with_only_a_free_item_is_not_a_trading_day() -> None:
    """D1's trading days are sale days: the free items must not hide the
    five missing days."""
    plain = _d1_evidence(free_items_on_the_gap=False)

    assert plain["excess_zero_days_cur"] > 0
    assert _d1_evidence(free_items_on_the_gap=True) == plain


def test_b2_names_deductions_in_its_refusal() -> None:
    """D6: B2 still refuses on negative-amount lines until 3E3, and names them
    for what they are (2E-c2: dropping the clause failed its proof)."""
    b2 = by_id(evaluate_hypotheses(step7(run_data(_refunds_at_a_negative_price()))))["B2"]

    assert b2.verdict == "inconclusive"
    assert "deduction" in b2.rule


def test_diagnosis_json_requires_the_deductions_term() -> None:
    # 2.0 in 2E-c; 3.0 in 2E-c2 (the bridge's `new`); 4.0 in 2E-e (orders by
    # basis); 5.0 in 2E-f (first-day netting per product, customer fill);
    # 6.0 in 2E-g (product keys and labels, the gap never R3 or D2); 7.0 in
    # 2E-h (wall-clock dates); 8.0 since 2E-e2 (answers from Review).
    payload = diagnosis_payload()
    assert DiagnosisContract.model_validate(payload).schema_version == "9.0"  # 9.0 since 2E-k

    del payload["tree"]["returns"]["deductions_cur"]
    with pytest.raises(ValidationError, match="deductions_cur"):
        DiagnosisContract.model_validate(payload)


def test_a_1x_diagnosis_json_is_refused() -> None:
    payload = diagnosis_payload()
    payload["schema_version"] = "1.0"

    with pytest.raises(ValidationError, match="re-analyse"):
        DiagnosisContract.model_validate(payload)


def test_the_returns_lens_gross_counts_deductions() -> None:
    """Mutation check (2E-c): under the masked-shift alert a returns-lens
    share is measured against the lens's own gross, |d gross| + |d returns| +
    |d deductions|. By hand on the negative-price file: 0 + 0 + 1,080 =
    1,080. Leaving deductions out gave D = 0 here, and in general a smaller D
    - a returns share inflated by money that was a write-off."""
    tree = step7(run_data(_refunds_at_a_negative_price())).tree

    assert decomposition_gross(tree, "returns") == pytest.approx(1080.0)


def test_a_free_gift_is_not_a_unit_in_the_basket() -> None:
    """2E-c doubt-review F1: July 3 sales a day of 3 units at 30; August the
    same baskets at 33 (+10%) plus one free gift line a day (3 @ 0). Units
    summed over every counted row, orders over sale rows only, so baskets
    went 3.0 -> 4.0 and B2 headlined "baskets got bigger" (+2,545.88 against
    +837). A deduction line's quantity is not a unit sold: units per order
    stays 9 x 31 / (3 x 31) = 3.0, and the price rise (P1, +837) is what
    moved."""
    rows = _history()
    rows += [row(d, qty=3.0, price=30.0, customer=f"C{(d.day + k) % 10}")
             for d in _month(2026, 7) for k in range(3)]
    rows += [row(d, qty=3.0, price=33.0, customer=f"C{(d.day + k) % 10}")
             for d in _month(2026, 8) for k in range(3)]
    rows += [row(d, qty=3.0, price=0.0, product="Gift", customer=f"C{d.day % 10}")
             for d in _month(2026, 8)]
    rows.append(row(date(2026, 9, 1), qty=1.0, price=30.0, customer="C1"))

    inputs = step7(run_data(rows))
    results = evaluate_hypotheses(inputs)
    basket = next(f for f in inputs.tree.lever.level2.factors if f.name == "units_per_order")
    headline = choose_headline(inputs.trust, results, inputs.tree, changes(inputs))

    assert (basket.value_prev, basket.value_cur) == (pytest.approx(3.0), pytest.approx(3.0))
    assert by_id(results)["B2"].verdict != "supported"
    assert headline.hypothesis_id != "B2"


def _gift_file() -> list[dict]:
    """July: 3 sales a day of 3 units at 30. August: 3 sales a day of 2 units
    at 40, plus a free gift line a day (3 @ 0). One category, X."""
    rows = _history()
    rows += [row(d, qty=3.0, price=30.0, customer=f"C{(d.day + k) % 10}")
             for d in _month(2026, 7) for k in range(3)]
    rows += [row(d, qty=2.0, price=40.0, customer=f"C{(d.day + k) % 10}")
             for d in _month(2026, 8) for k in range(3)]
    rows += [row(d, qty=3.0, price=0.0, product="Gift", customer=f"C{d.day % 10}")
             for d in _month(2026, 8)]
    rows.append(row(date(2026, 9, 1), qty=1.0, price=30.0, customer="C1"))
    return [{**r, "Cat": "X"} for r in rows]


def test_step_4_counts_the_same_units_as_the_lever() -> None:
    """Mutation check (2E-c): the units_per_order series uses sale and return
    lines' units. August: 2 x 93 / 93 = 2.0, not (186 + 93 x 3) / 93 = 5.0."""
    data = run_data(_gift_file(), {**MAPPING, "Cat": "category"})
    series = next(s for s in compute_signals(data, history_window(data))
                  if s.series == "units_per_order")

    assert series.value_cur == pytest.approx(2.0)


def test_the_category_split_reconciles_to_the_lever_price_per_unit() -> None:
    """Mutation check (2E-c): price per unit moved more than AOV (30 -> 40,
    +33%, against AOV 90 -> 80), so the category split takes it, and mix +
    rate must be the lever's own change: 40 - 30 = +10. Counting the gifts'
    units gave 7,440 / 465 = 16 - a split of a figure the lever never had."""
    data = run_data(_gift_file(), {**MAPPING, "Cat": "category"})
    split = compute_mix_rate(data)
    ppu = next(f for f in step7(data).tree.lever.level2.factors if f.name == "price_per_unit")

    assert split.metric == "price_per_unit"
    assert (ppu.value_prev, ppu.value_cur) == (pytest.approx(30.0), pytest.approx(40.0))
    assert split.mix + split.rate == pytest.approx(10.0)
