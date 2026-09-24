"""Session 2E-c2, stage 3 (Thach, after 2E-c's review), written before the
change.

1. B2's refusal on negative-amount lines was to be DROPPED on condition of
   proof that a deduction line cannot move B2 (Thach). The proof FAILED in
   review: a refund booked +1 at a negative price is a deduction, its units
   leave level 2, and B2 headlined "baskets got bigger" while each order
   kept fewer units. The clause stays until 3E3. Kept from the attempt: B2
   is also refused when a compared month nets zero or below, as B1 is.
2. The first-day rule: ANY return line on a customer's first day means their
   history opens with a refund - no same-day netting (reverses 2E-c D3's
   netting clause). Netting by quantity across products made a customer who
   bought 10 pens and returned a 500 chair bought before the file "new", and
   C1 headlined new-customer revenue collapsing (2E-c review cycle 3).
3. A zero-amount negative-quantity line is a stock write-off, not a return:
   it no longer refuses B2.
"""

from datetime import date, timedelta

import pytest

from stages.diagnose.bridge import customer_classes
from stages.diagnose.headline import choose_headline
from stages.diagnose.hypotheses import evaluate_hypotheses
from stages.diagnose.step7_inputs import changes
from tests.stages.diagnose.diagnose_fixtures import daily_rows, row, run_data
from tests.stages.diagnose.test_hypotheses import by_id, step7


def _month(year: int, month: int):
    day = date(year, month, 1)
    while day.month == month:
        yield day
        day += timedelta(days=1)


def _smaller_baskets(extra: list[dict]) -> list[dict]:
    """Ten months of 3-unit baskets at 30 (three a day), then August's baskets
    fall to 2 units at the same price: basket size is the real cause."""
    rows = []
    for year, month in [(2025, m) for m in range(10, 13)] + [(2026, m) for m in range(1, 8)]:
        rows += [row(d, qty=3.0, price=30.0, customer=f"C{(d.day + k) % 10}")
                 for d in _month(year, month) for k in range(3)]
    rows += [row(d, qty=2.0, price=30.0, customer=f"C{(d.day + k) % 10}")
             for d in _month(2026, 8) for k in range(3)]
    rows.append(row(date(2026, 9, 1), qty=3.0, price=30.0, customer="C1"))
    return rows + extra


def _b2_and_basket(rows):
    inputs = step7(run_data(rows))
    basket = next(f for f in inputs.tree.lever.level2.factors if f.name == "units_per_order")
    return by_id(evaluate_hypotheses(inputs))["B2"], basket


def test_a_coupon_leaves_the_basket_values_but_still_refuses_b2() -> None:
    """Without the coupon: units per order 3.0 -> 2.0, B2 supported. With one
    coupon (1 @ -5) the basket values are the same 3.0 -> 2.0 (since 2E-c a
    deduction is not a unit), but B2 is still refused: dropping the clause
    was decided on condition of proof, and the proof failed (refunds booked
    at a negative price - indistinguishable from a coupon - made B2 headline
    "baskets got bigger"). The coupon's cost is this SUPPRESS."""
    plain, plain_basket = _b2_and_basket(_smaller_baskets([]))
    coupon, coupon_basket = _b2_and_basket(_smaller_baskets(
        [row(date(2026, 8, 15), qty=1.0, price=-5.0, product="Coupon", customer="C1")]))

    assert (plain_basket.value_prev, plain_basket.value_cur) == (pytest.approx(3.0), pytest.approx(2.0))
    assert (coupon_basket.value_prev, coupon_basket.value_cur) == (pytest.approx(3.0), pytest.approx(2.0))
    assert plain.verdict == "supported"
    assert coupon.verdict == "inconclusive"


def test_a_stock_write_off_does_not_refuse_b2() -> None:
    """Three -1 @ 0 write-offs ("damaged") in August: no money, not a
    customer return, so B2 still reads the smaller baskets."""
    b2, _ = _b2_and_basket(_smaller_baskets(
        [row(date(2026, 8, 20 + i), qty=-1.0, price=0.0, customer="") for i in range(3)]))

    assert b2.verdict == "supported"


def _pens_and_a_chair(pens: bool) -> list[dict]:
    """2E-c review cycle 3's file: Regular buys daily from September 2025 to
    August 2026; a genuinely new customer buys once (40) every month; on 7
    August customer X returns a 500 chair bought before the file - and, in
    the variant, buys 10 pens at 1 the same day."""
    rows = daily_rows(date(2025, 9, 1), date(2026, 8, 31), customer="Regular")
    for index in range(12):
        year, month = (2025, 9 + index) if index < 4 else (2026, index - 3)
        rows.append(row(date(year, month, 15), qty=1.0, price=40.0, customer=f"N{index}"))
    if pens:
        rows.append(row(date(2026, 8, 7), qty=10.0, price=1.0, product="Pen", customer="X"))
    rows.append(row(date(2026, 8, 7), qty=-1.0, price=500.0, product="Chair", customer="X"))
    rows.append(row(date(2026, 9, 1), customer="Regular"))
    return rows


def test_a_return_on_the_first_day_means_the_history_opens_with_a_refund() -> None:
    """X nets +9 units (10 pens - 1 chair) but returned something bought
    before the file: never new, whatever else they bought that day. Before:
    new with -490 of new revenue, and C1 supported ("new-customer revenue
    collapsed"). Now stage 2 counts only August's genuinely new customer
    (40), the bridge calls X resurrected, and C1 is not supported."""
    data = run_data(_pens_and_a_chair(pens=True))
    split = data.metrics.customers.new_vs_returning
    results = by_id(evaluate_hypotheses(step7(data)))

    assert (split.new_customers, split.new_revenue) == (1, pytest.approx(40.0))
    assert customer_classes(data)["x"] == "resurrected"
    assert results["C1"].verdict != "supported"


def _recall_month(recall_month: int = 8) -> list[dict]:
    """2E-c2 doubt-review F1: baskets grow from 1 to 2 units at 30 (three a
    day), and `recall_month` (August by default) also holds a recall booked in 2E-b's
    convention - 93 refunds of quantity +1 at -300. August nets -22,320."""
    rows = []
    for year, month in [(2025, m) for m in range(10, 13)] + [(2026, m) for m in range(1, 8)]:
        rows += [row(d, qty=1.0, price=30.0, product=f"P{k}", customer=f"C{(d.day + k) % 10}")
                 for d in _month(year, month) for k in range(3)]
    rows += [row(d, qty=2.0, price=30.0, product=f"P{k}", customer=f"C{(d.day + k) % 10}")
             for d in _month(2026, 8) for k in range(3)]
    rows += [row(d, qty=1.0, price=-300.0, product=f"P{k}", customer=f"C{(d.day + k) % 10}")
             for d in _month(2026, recall_month) for k in range(3)]
    rows.append(row(date(2026, 9, 1), qty=1.0, price=30.0, customer="C1"))
    return rows


def test_b2_is_refused_when_a_month_nets_zero_or_below() -> None:
    """The deductions took August net negative, so price per unit went
    30 -> -120 and B2's Shapley basket term changed sign: "partial, Baskets
    got smaller" - into the headline - while baskets grew 1 -> 2. B1 has
    refused such months since 2E; with the negative-amount clause dropped,
    B2 needs the same refusal."""
    inputs = step7(run_data(_recall_month()))
    results = evaluate_hypotheses(inputs)
    headline = choose_headline(inputs.trust, results, inputs.tree, changes(inputs))

    assert by_id(results)["B2"].verdict == "inconclusive"
    assert "smaller" not in headline.message


def test_b2_is_refused_when_the_previous_month_nets_below_zero() -> None:
    """Mutation check (2E-c2): the same recall in JULY, the previous month -
    July nets 2,790 - 27,900 = -25,110. Either compared month refuses."""
    b2 = by_id(evaluate_hypotheses(step7(run_data(_recall_month(recall_month=7)))))["B2"]

    assert b2.verdict == "inconclusive"


def test_refunds_booked_at_a_negative_price_do_not_make_baskets_bigger() -> None:
    """2E-c2 doubt-review cycle 2, which failed item 1's proof: ten orders a
    day at 3 units @ 30, then 4 units @ 40 with fifteen refunds a day booked
    +1 @ -40. Each order keeps 2.5 units (down from 3) and the price rose a
    third. With the negative-amount clause dropped, the refunds' units left
    level 2 and B2 headlined "baskets got bigger" (+8,525 against +3,100);
    booked as return lines (-1 @ 40) the same refunds refuse B2. A coupon and
    a refund at a negative price cannot be told apart, so both refuse B2
    until 3E3 gives refunds a factor - the clause is restored."""
    rows = []
    for year, month in [(2025, m) for m in range(10, 13)] + [(2026, m) for m in range(1, 8)]:
        rows += [row(d, qty=3.0, price=30.0, customer=f"C{(d.day + k) % 10}")
                 for d in _month(year, month) for k in range(10)]
    for d in _month(2026, 8):
        rows += [row(d, qty=4.0, price=40.0, customer=f"C{(d.day + k) % 10}") for k in range(10)]
        rows += [row(d, qty=1.0, price=-40.0, customer=f"C{(d.day + k) % 10}") for k in range(15)]
    rows.append(row(date(2026, 9, 1), qty=3.0, price=30.0, customer="C1"))

    inputs = step7(run_data(rows))
    results = evaluate_hypotheses(inputs)
    headline = choose_headline(inputs.trust, results, inputs.tree, changes(inputs))

    assert by_id(results)["B2"].verdict == "inconclusive"
    assert "bigger" not in headline.message
