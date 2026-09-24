"""Each evidence function's own decisions - the lever, product and returns
hypotheses, the product-lens share rule and the stockout boundary. Split from
test_hypothesis_evidence.py in 2E-b for file size; tests moved unchanged.
"""

from datetime import date, timedelta
from types import SimpleNamespace as NS

import pandas as pd
import pytest

from stages.diagnose.catalog import BY_ID
from stages.diagnose.hypotheses import share_verdict
from stages.diagnose.step7_inputs import Changes
from stages.diagnose.stockout import detect_stockouts
from tests.stages.diagnose.diagnose_fixtures import row, run_data
from tests.stages.diagnose.test_hypotheses import step7
from tests.stages.diagnose.test_hypothesis_evidence import CUSTOMER, evaluate
from tests.stages.diagnose.test_rule_one_reliability import months


# --- lever ----------------------------------------------------------------------


def test_b1_needs_the_three_factor_split() -> None:
    """A customer column is mapped, but a period had no identified customers,
    so level 1 fell back to orders x AOV: frequency cannot be read."""
    inputs = NS(data=NS(parsed=CUSTOMER), tree=NS(
        returns=NS(returns_prev=0.0, returns_cur=0.0),
        lever=NS(level1=NS(formula="orders*aov", factors=[]),
                 reasons={"level1_form": "no identified customers in one period"})),
                trust=NS(checks=[NS(id="D1", status="ok", evidence={
                    "excess_zero_days_cur": 0.0, "excess_zero_days_prev": 0.0})]))

    outcome = evaluate("B1", inputs)

    assert outcome.verdict == "inconclusive"
    assert "three-factor" in outcome.rule or "customers x frequency" in outcome.rule


def _lines(returned_prev: int, returned_cur: int) -> NS:
    """Stand-in data holding that many return lines per compared month (B2's
    refusal reads return LINES since the 2E doubt-review cycle 3)."""
    months = ["p"] * max(returned_prev, 1) + ["c"] * max(returned_cur, 1)
    returned = ([True] * returned_prev + [False] * (returned_prev == 0)
                + [True] * returned_cur + [False] * (returned_cur == 0))
    # Every row counted; a return line carries negative money, a sale positive
    # (B2 also reads negative amounts since 2E-b).
    return NS(parsed=NS(**vars(CUSTOMER), returned=pd.Series(returned),
                        counted=pd.Series([True] * len(returned)),
                        revenue_amounts=pd.Series([-1.0 if r else 1.0 for r in returned])),
              months=pd.Series(months), metrics=NS(period=NS(previous="p", current="c")))


def test_b2_reads_units_per_order_not_price() -> None:
    level2 = NS(factors=[NS(name="units_per_order", contribution=-70.0, value_prev=4.0, value_cur=3.5),
                         NS(name="price_per_unit", contribution=25.0, value_prev=10.0, value_cur=10.5)])
    inputs = NS(data=_lines(0, 0), tree=NS(lever=NS(level2=level2, reasons={}),
                                          returns=NS(returns_prev=0.0, returns_cur=0.0)))

    assert evaluate("B2", inputs).contribution == -70.0


@pytest.mark.parametrize("lines_prev,lines_cur", [(0, 1), (2, 0)])
def test_b2_is_inconclusive_on_any_return_line_until_level_2_separates_them(
    lines_prev, lines_cur,
) -> None:
    """INTERIM for B2 only since 2E (Thach): level 2 counts refunded units
    against the basket. Either period with any return LINE makes B2
    inconclusive - lines, not refunded money, since a zero-price write-off
    carries units and no money (2E doubt-review cycle 3).
    (B1 was refused here too until 2E; with orders = sale rows a refund cannot
    move frequency, so B1's cases left this test by that decision - see
    test_2e_stage3.test_refunds_alone_do_not_move_purchase_frequency.)"""
    inputs = NS(data=_lines(lines_prev, lines_cur), tree=NS(
        returns=NS(returns_prev=0.0, returns_cur=0.0)))

    assert evaluate("B2", inputs).verdict == "inconclusive"


# --- product and returns --------------------------------------------------------


def test_p3_is_minus_the_change_in_returns() -> None:
    """Returns grew from 100 to 150: 50 more refunded, -50 of change."""
    inputs = NS(tree=NS(returns=NS(returns_prev=100.0, returns_cur=150.0)))

    assert evaluate("P3", inputs).contribution == -50.0


def _two_products(october: dict, november: dict):
    rows = []
    for (month, day), basket in (((10, 1), october), ((11, 30), november)):
        for product, (qty, price) in basket.items():
            rows.append(row(date(2011, month, day), qty=qty, price=price, product=product))
    return run_data(rows)


def test_p1_and_p2_read_their_own_pvm_term() -> None:
    data = _two_products({"A": (10, 10.0)}, {"A": (10, 8.0)})
    inputs = step7(data)
    products = inputs.tree.products

    assert evaluate("P1", inputs).contribution == products.price
    assert evaluate("P2", inputs).contribution == products.mix
    assert products.price != products.mix


def test_p1_needs_a_product_sold_in_both_periods() -> None:
    """A sold only in October, B only in November: no like-for-like set."""
    data = _two_products({"A": (10, 10.0)}, {"B": (10, 10.0)})

    assert evaluate("P1", step7(data)).verdict == "inconclusive"


def test_r2_adds_launches_and_discontinuations() -> None:
    inputs = NS(tree=NS(products=NS(new_products=300.0, discontinued_products=-450.0)))

    assert evaluate("R2", inputs).contribution == -150.0


def test_r1_needs_concentration_and_the_top_product_moving_with_the_total() -> None:
    """A fell 900 while the total fell: concentrated and moving with it ->
    supported. Same data under a `mixed` breadth -> ruled_out. And with the
    total RISING, A's fall is against it -> ruled_out."""
    data = _two_products({"A": (100, 10.0), "B": (10, 10.0)}, {"A": (10, 10.0), "B": (10, 10.0)})

    def r1(classification: str, moved: Changes):
        inputs = NS(data=data, localization=NS(breadth=NS(classification=classification,
                                                           top_member_share=0.9)))
        return evaluate("R1", inputs, moved).verdict

    fell = Changes(1100.0, 200.0, -900.0, -900.0, False)
    rose = Changes(1100.0, 1300.0, 200.0, 200.0, False)
    assert r1("concentrated", fell) == "supported"
    assert r1("mixed", fell) == "ruled_out"
    assert r1("concentrated", rose) == "ruled_out"


# --- the share rule on the product lens -----------------------------------------


def test_the_product_lens_is_judged_against_gross_sales() -> None:
    """Revenue fell 200 but GROSS sales rose 50 (returns grew by 250). A price
    effect of -30 is against the gross change the product lens decomposes:
    ruled_out, share -30 / 50 = -0.6. Judged against revenue it would have
    been a partial -0.15."""
    moved = Changes(1000.0, 800.0, -200.0, 50.0, False)

    verdict, share, _ = share_verdict(BY_ID["P1"], -30.0, NS(tree=None), moved)

    assert (verdict, share) == ("ruled_out", pytest.approx(-0.6))


# --- stockout rate boundary ------------------------------------------------------


def test_a_rate_of_exactly_one_half_qualifies() -> None:
    """Sundays closed: October 2011 has 26 trading days. A sells on the first
    13 of them (rate 0.50 = R3_MIN_ACTIVE_DAY_RATE, which qualifies), every
    trading day of November up to the 16th, then stops: from Thursday 17 to
    Wednesday 30 is 12 trading days."""
    rows, trading = [], []
    day = date(2011, 10, 1)
    while day <= date(2011, 11, 30):
        if day.weekday() != 6:
            rows.append(row(day, qty=1, price=10.0, product="B"))
            trading.append(day)
        day += timedelta(days=1)
    october = [d for d in trading if d.month == 10]
    assert len(october) == 26
    for d in october[:13] + [d for d in trading if d.month == 11 and d.day <= 16]:
        rows.append(row(d, qty=1, price=100.0, product="A"))

    found = detect_stockouts(run_data(rows))

    assert [(item.product, item.active_day_rate_prev) for item in found] == [("A", 0.5)]


def test_c4_refuses_when_a_segment_has_emptied() -> None:
    """3E1 doubt-review #7. Stage 2 lists only the segments present NOW, so a
    segment that emptied vanishes from BOTH totals. True previous: Champions
    30, Loyal 20, Hibernating 20, Needs Attention 30; true current: Champions
    30, Loyal 20, At-risk 5, Needs Attention 45 - a 15-point FAVOURABLE move.
    Without Hibernating in the list the previous total is 80, not 100, and C4
    came out supported at 17.5 unfavourable points. When any of stage 2's six
    segments is missing, the previous total cannot be trusted: inconclusive."""
    segments = [NS(segment="Champions", customers=30, customers_previous=30),
                NS(segment="Loyal", customers=20, customers_previous=20),
                NS(segment="At-risk", customers=5, customers_previous=0),
                NS(segment="Needs Attention", customers=45, customers_previous=30)]
    inputs = NS(data=NS(parsed=CUSTOMER, metrics=NS(customers=NS(segments=segments))))

    assert evaluate("C4", inputs).verdict == "inconclusive"
