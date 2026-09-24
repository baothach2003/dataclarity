"""Session 2E-c (Thach, rule C), written before the change: a customer is NEW
in a month when their first purchase - first sale row - falls in it AND
their history does not open with a refund. A refund proves a purchase before
the file started. The same rule in stage 2's new_vs_returning and in stage
3's customer bridge; it supersedes 3C's "a first activity that is a return
changes no term" (an evidence note only).

The file: Regular buys every day from September 2025 to August 2026. In
August 2026 (the current month; July is the previous one):
- Fresh buys once (10) - their first activity anywhere: NEW.
- RefundOnly returns one unit (-10) and does nothing else: they bought before
  the file, so NOT new.
- Opener returns two units (-20) on 3 August and buys one (10) on the 20th:
  their history opens with a refund, so NOT new.
Before the change all three were new: first counted row in August.
"""

from datetime import date

import pytest

from stages.diagnose.bridge import customer_classes
from tests.stages.diagnose.diagnose_fixtures import daily_rows, row, run_data
from tests.stages.diagnose.test_hypotheses import step7


def _file() -> list[dict]:
    rows = daily_rows(date(2025, 9, 1), date(2026, 8, 31), customer="Regular")
    rows += [row(date(2026, 8, 7), qty=1.0, price=10.0, customer="Fresh"),
             row(date(2026, 8, 5), qty=-1.0, price=10.0, customer="RefundOnly"),
             row(date(2026, 8, 3), qty=-2.0, price=10.0, customer="Opener"),
             row(date(2026, 8, 20), qty=1.0, price=10.0, customer="Opener"),
             row(date(2026, 9, 1), customer="Regular")]
    return rows


def test_stage_2_counts_only_a_first_purchase_as_new() -> None:
    """By hand, August: new = Fresh (10). Returning = Regular (31 x 10 =
    310), RefundOnly (-10), Opener (-20 + 10 = -10): 3 customers, 290.
    Before: 3 new with -10 of new revenue, 1 returning."""
    split = run_data(_file()).metrics.customers.new_vs_returning

    assert split.new_customers == 1
    assert split.new_revenue == pytest.approx(10.0)
    assert split.returning_customers == 3
    assert split.returning_revenue == pytest.approx(290.0)


def test_the_bridge_calls_a_refund_opening_customer_resurrected_not_new() -> None:
    """None of the three was active in July. Fresh is new; RefundOnly and
    Opener existed before the file, so they come back: resurrected. The
    bridge still adds up - moving a customer between new and resurrected
    changes no total."""
    classes = customer_classes(run_data(_file()))

    assert classes["fresh"] == "new"
    assert classes["refundonly"] == "resurrected"
    assert classes["opener"] == "resurrected"
    assert classes["regular"] == "retained"


def test_the_bridge_terms_follow_the_classes() -> None:
    """new = Fresh's 10; resurrected = RefundOnly's -10 + Opener's -10 = -20.
    Before: new = 10 - 10 - 10 = -10, resurrected 0."""
    lens = step7(run_data(_file())).tree.customers

    assert lens.new == pytest.approx(10.0)
    assert lens.resurrected == pytest.approx(-20.0)


def _deduction_before_first_purchase() -> list[dict]:
    """2E-c doubt-review F2. Base buys every day from September 2025 to
    August 2026. Newbie gets a free sample (1 @ 0) in July and first buys in
    August (2 @ 50); Couponer has a coupon line (1 @ -5) in July and first
    buys in August (2 @ 50)."""
    rows = daily_rows(date(2025, 9, 1), date(2026, 8, 31), price=30.0, customer="Base")
    rows += [row(date(2026, 7, 10), qty=1.0, price=0.0, product="Sample", customer="Newbie"),
             row(date(2026, 8, 12), qty=2.0, price=50.0, customer="Newbie"),
             row(date(2026, 7, 10), qty=1.0, price=-5.0, product="Coupon", customer="Couponer"),
             row(date(2026, 8, 12), qty=2.0, price=50.0, customer="Couponer"),
             row(date(2026, 9, 1), price=30.0, customer="Base")]
    return rows


def test_a_deduction_last_month_does_not_stop_a_first_purchase_being_new() -> None:
    """Both first bought in August and neither history opens with a refund, so
    both are new in stage 2 (new_customers 2, new_revenue 200) - and the
    bridge must agree. It called them retained: their July deduction rows
    made them present in July, and only absent customers could be new."""
    data = run_data(_deduction_before_first_purchase())
    classes = customer_classes(data)

    assert data.metrics.customers.new_vs_returning.new_customers == 2
    assert (classes["newbie"], classes["couponer"]) == ("new", "new")


def test_a_new_customer_brings_their_change_not_only_their_level() -> None:
    """The bridge's `new` term is each new customer's change: Newbie 100 - 0,
    Couponer 100 - (-5) = 105; new = 205, so the six terms still sum to the
    change. Before, both sat in expansion (+205) and new was 0."""
    lens = step7(run_data(_deduction_before_first_purchase())).tree.customers

    assert lens.new == pytest.approx(205.0)
    assert lens.expansion == pytest.approx(0.0)


def test_every_arrival_without_a_first_purchase_is_counted() -> None:
    """August arrivals with no purchase in the file: RefundOnly and Opener
    (histories opening with a refund) - 2 in `_file()`. Adding a coupon-only
    and a free-item-only arrival makes 4 (cycle 2: they came back NaN and
    the count said 2)."""
    rows = _file() + [row(date(2026, 8, 9), qty=1.0, price=-5.0, customer="CouponOnly"),
                      row(date(2026, 8, 9), qty=2.0, price=0.0, customer="FreeOnly")]

    lens = step7(run_data(rows)).tree.customers

    assert lens.evidence["arrivals_with_no_first_purchase_in_the_file"] == 4
