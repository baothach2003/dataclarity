"""Session 2E-b, the two smaller items (Thach, after 2E), written before the
change.

1. RFM recency counts SALE rows, like frequency: a refund is not a purchase.
   A returns-only customer ranks lowest, as with F = 0. Monetary stays net.
2. B2 is refused on a refund booked as quantity +1 at a negative price too
   (2E doubt-review cycle 4): level 2 read it as a one-unit order, so baskets
   "shrank" while every real basket was identical.
"""

from datetime import date, timedelta

import pandas as pd
import pytest

from stages.analyze.metrics_customers import rfm_snapshot
from stages.diagnose.hypotheses import evaluate_hypotheses
from tests.stages.diagnose.diagnose_fixtures import row, run_data
from tests.stages.diagnose.test_hypotheses import by_id, step7


def test_recency_counts_the_last_purchase_not_the_last_refund() -> None:
    """Reference 1 December 2011. Ann bought on 1 January and refunded on 30
    November: her last PURCHASE is 334 days back, not 1. Bob bought on 1
    November: 30 days. Carol only refunded (15 November): she never bought,
    so she ranks below everyone. Monetary stays net: Ann 40 - 10 = 30."""
    table = pd.DataFrame({
        "customer": ["ann", "ann", "bob", "carol"],
        "date": pd.to_datetime(["2011-01-01", "2011-11-30", "2011-11-01", "2011-11-15"]),
        "revenue": [40.0, -10.0, 20.0, -5.0],
        "sale": [True, False, True, False],
    })

    snapshot = rfm_snapshot(table, date(2011, 12, 1))

    assert snapshot.loc["ann", "recency_days"] == 334
    assert snapshot.loc["bob", "recency_days"] == 30
    assert snapshot.loc["carol", "recency_days"] > 334
    assert snapshot.loc["carol", "r_score"] == snapshot["r_score"].min()
    assert snapshot.loc["ann", "monetary"] == 30.0


def _month(year: int, month: int):
    day = date(year, month, 1)
    while day.month == month:
        yield day
        day += timedelta(days=1)


def test_b2_is_refused_on_a_refund_booked_at_a_negative_price() -> None:
    """Every sale in both months is 3 units at 30; August adds twelve
    whole-basket refunds booked as quantity 1 at -90. B2 read "baskets got
    smaller" (units per order 3.0 -> 2.77) while every real basket was 3."""
    rows = []
    for year, month in [(2025, m) for m in range(9, 13)] + [(2026, m) for m in range(1, 7)]:
        rows += [row(d, qty=1.0, price=30.0, customer=f"C{d.day % 10}") for d in _month(year, month)]
    for year, month in ((2026, 7), (2026, 8)):
        for d in _month(year, month):
            rows += [row(d, qty=3.0, price=30.0, customer=f"C{(d.day + k) % 10}") for k in range(3)]
    rows += [row(date(2026, 8, 2 * d), qty=1.0, price=-90.0, customer=f"C{d % 10}")
             for d in range(1, 13)]
    rows.append(row(date(2026, 9, 1), qty=1.0, price=30.0, customer="C1"))

    b2 = by_id(evaluate_hypotheses(step7(run_data(rows))))["B2"]

    assert b2.verdict == "inconclusive"
    assert b2.evidence == {"refund_lines_prev": 0, "refund_lines_cur": 12}


def test_b2_is_refused_when_only_the_previous_month_has_negative_price_refunds() -> None:
    """The same twelve quantity-1, -90 refunds, booked in JULY this time: the
    previous month's baskets read smaller instead (mutation check, 2E-b)."""
    rows = []
    for year, month in [(2025, m) for m in range(9, 13)] + [(2026, m) for m in range(1, 7)]:
        rows += [row(d, qty=1.0, price=30.0, customer=f"C{d.day % 10}") for d in _month(year, month)]
    for year, month in ((2026, 7), (2026, 8)):
        for d in _month(year, month):
            rows += [row(d, qty=3.0, price=30.0, customer=f"C{(d.day + k) % 10}") for k in range(3)]
    rows += [row(date(2026, 7, 2 * d), qty=1.0, price=-90.0, customer=f"C{d % 10}")
             for d in range(1, 13)]
    rows.append(row(date(2026, 9, 1), qty=1.0, price=30.0, customer="C1"))

    b2 = by_id(evaluate_hypotheses(step7(run_data(rows))))["B2"]

    assert b2.verdict == "inconclusive"
    assert b2.evidence == {"refund_lines_prev": 12, "refund_lines_cur": 0}


@pytest.mark.parametrize("returners,buyers", [(2, 0), (3, 1), (4, 2)])
def test_a_returns_only_customer_is_never_ranked_above_the_bottom(returners, buyers) -> None:
    """2E-b doubt-review: every returns-only customer shared one "never"
    recency and a frequency of 0, and the rank's tie-break by order lifted one
    of them to r=5, f=5 - Champions - when they were most of the snapshot.
    A customer who never bought scores 1 on both, whatever else is in the file,
    and has a segment of their own (Thach, 2E-b)."""
    customers = [f"ret{i}" for i in range(returners)] + [f"buy{i}" for i in range(buyers)]
    table = pd.DataFrame({
        "customer": customers,
        "date": pd.to_datetime(["2011-11-15"] * len(customers)),
        "revenue": [-5.0] * returners + [20.0] * buyers,
        "sale": [False] * returners + [True] * buyers,
    })

    snapshot = rfm_snapshot(table, date(2011, 12, 1))
    never = snapshot.loc[[f"ret{i}" for i in range(returners)]]

    assert (never["r_score"] == 1).all() and (never["f_score"] == 1).all()
    assert (never["segment"] == "Returns only").all()


@pytest.mark.parametrize("refunders", [3, 10, 20])
def test_refund_only_customers_do_not_move_any_buyer(refunders) -> None:
    """2E-b doubt-review cycle 2: never-buyers filled the bottom R quintiles
    and pushed every buyer up - 20 refunders turned 10 lapsed one-time buyers
    into Champions. The quintiles are cut from BUYERS only (Thach, 2E-b,
    superseding 2B's "the run's own data" for R and F): adding refund-only
    customers leaves every buyer's R, F and segment unchanged, and puts every
    refunder in "Returns only"."""
    buyers = pd.DataFrame({
        "customer": [f"b{i}" for i in range(10)],
        "date": [pd.Timestamp("2011-12-01") - pd.Timedelta(days=1 + 36 * i) for i in range(10)],
        "revenue": [10.0] * 10,
        "sale": [True] * 10,
    })
    refunds = pd.DataFrame({
        "customer": [f"r{i}" for i in range(refunders)],
        "date": [pd.Timestamp("2011-11-20")] * refunders,
        "revenue": [-5.0] * refunders,
        "sale": [False] * refunders,
    })
    alone = rfm_snapshot(buyers, date(2011, 12, 1))

    both = rfm_snapshot(pd.concat([buyers, refunds], ignore_index=True), date(2011, 12, 1))

    columns = ["r_score", "f_score", "segment"]
    assert both.loc[alone.index, columns].equals(alone[columns])
    assert (both.loc[[f"r{i}" for i in range(refunders)], "segment"] == "Returns only").all()


def _b2_file(refund_rows: list[dict]) -> list[dict]:
    """Baskets of 2 units in July, 3 in August (a real change B2 should read),
    plus the given refund rows."""
    rows = []
    for year, month in [(2025, m) for m in range(9, 13)] + [(2026, m) for m in range(1, 7)]:
        rows += [row(d, qty=1.0, price=30.0, customer=f"C{d.day % 10}") for d in _month(year, month)]
    rows += [row(d, qty=2.0, price=30.0, customer=f"C{d.day % 10}") for d in _month(2026, 7)]
    rows += [row(d, qty=3.0, price=30.0, customer=f"C{d.day % 10}") for d in _month(2026, 8)]
    rows.append(row(date(2026, 9, 1), qty=1.0, price=30.0, customer="C1"))
    return rows + refund_rows


def test_b2_counts_each_refund_line_once() -> None:
    """One return line (qty -1 at 30) and one negative-price line (qty 1 at
    -30) in August: two refund lines, not three (a return line is also a
    negative amount, and must not be counted twice). The evidence is line
    counts only: the returns lens's money ("returns_cur": 0.0 beside twelve
    negative-price lines) read as a contradiction (2E-b review cycle 2)."""
    b2 = by_id(evaluate_hypotheses(step7(run_data(_b2_file([
        row(date(2026, 8, 10), qty=-1.0, price=30.0, customer="C1"),
        row(date(2026, 8, 11), qty=1.0, price=-30.0, customer="C2"),
    ])))))["B2"]

    assert b2.verdict == "inconclusive"
    assert b2.evidence == {"refund_lines_prev": 0, "refund_lines_cur": 2}


def test_a_refund_outside_the_two_months_does_not_refuse_b2() -> None:
    """A negative-price refund in March, not in July or August: B2 reads the
    real basket change (2 -> 3 units) and is supported."""
    b2 = by_id(evaluate_hypotheses(step7(run_data(_b2_file([
        row(date(2026, 3, 10), qty=1.0, price=-30.0, customer="C1"),
    ])))))["B2"]

    assert (b2.verdict, b2.statement) == ("supported", "Baskets got bigger")
