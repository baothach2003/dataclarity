"""The 2E doubt-review's stage 3 findings, written from the reviewer's
reproductions before the fix (Thach's decisions, 2E).

F1  the lever's level 1 counts BUYERS (customers with a sale row): a customer
    who only returned goods is active, but did not buy less often.
F2  D1's trading day is a day with a SALE: ten refund-only days hid ten
    missing days of sales.
F3  a previous month holding only refunds blocks, as a month with no sale.
"""

from datetime import date, timedelta

from stages.diagnose.headline import choose_headline
from stages.diagnose.hypotheses import evaluate_hypotheses
from stages.diagnose.lever import period_totals
from stages.diagnose.step7_inputs import changes
from tests.stages.diagnose.diagnose_fixtures import row, run_data
from tests.stages.diagnose.test_hypotheses import by_id, step7


def _days(start: date, end: date):
    day = start
    while day <= end:
        yield day
        day += timedelta(days=1)


def _run(rows):
    data = run_data(rows)
    inputs = step7(data)
    results = evaluate_hypotheses(inputs)
    headline = choose_headline(inputs.trust, results, inputs.tree, changes(inputs))
    return data, inputs, by_id(results), headline


def test_customers_who_only_returned_goods_do_not_make_buyers_rarer() -> None:
    """f1c: ten loyal customers buy daily at 10.00, then at 9.50 in August
    2026; twenty never-seen customers each return one unit. It headlined
    "customers bought less often (-3,892.22 against the change of -310.00)".
    Buyers 10 -> 10, orders 310 -> 310: frequency contributes exactly 0."""
    rows = []
    for day in _days(date(2025, 1, 1), date(2026, 8, 31)):
        price = 9.5 if day >= date(2026, 8, 1) else 10.0
        rows += [row(day, qty=1.0, price=price, customer=f"Loyal{c}") for c in range(10)]
    rows += [row(date(2026, 8, 2 + c), qty=-1.0, price=7.75, customer=f"Refunder{c}")
             for c in range(20)]

    data, inputs, verdicts, headline = _run(rows)
    frequency = next(f for f in inputs.tree.lever.level1.factors if f.name == "frequency")

    assert frequency.contribution == 0.0
    assert verdicts["B1"].verdict == "ruled_out"
    assert headline.hypothesis_id != "B1"
    assert data.metrics.core.active_customers_current == 30  # 3C: still active


def test_the_levers_customers_are_stage_2s_buyers() -> None:
    """The consistency pin for the number B1 rests on (Thach, 2E)."""
    rows = [row(day, qty=1.0, customer="Ann") for day in _days(date(2011, 9, 1), date(2011, 10, 31))]
    rows.append(row(date(2011, 10, 5), qty=-1.0, customer="Bob"))
    data = run_data(rows)

    totals = period_totals(data, data.metrics.period.current)

    assert totals.customers == data.metrics.core.buyers_current == 1
    assert data.metrics.core.active_customers_current == 2


def test_refund_only_days_are_days_without_sales() -> None:
    """f6: five customers buy daily; 10-19 August 2026 hold no sale, only one
    refund line a day. D1 saw 0 zero days and B1 headlined "bought less often
    (79%)". Ten days without a sale are ten zero days."""
    rows = []
    for day in _days(date(2025, 1, 1), date(2026, 8, 31)):
        if date(2026, 8, 10) <= day <= date(2026, 8, 19):
            rows.append(row(day, qty=-1.0, customer="C0"))
            continue
        rows += [row(day, qty=1.0, customer=f"C{c}") for c in range(5)]

    _, inputs, verdicts, headline = _run(rows)
    d1 = next(check for check in inputs.trust.checks if check.id == "D1")

    assert d1.evidence["zero_days_cur"] == 10
    assert headline.hypothesis_id != "B1"


def test_a_previous_month_of_refunds_only_blocks() -> None:
    """f7: July 2026 holds only refund lines. It headlined "products were
    launched or discontinued (100%)" for a product sold for nineteen months."""
    rows = []
    for day in _days(date(2025, 1, 1), date(2026, 8, 31)):
        if day.year == 2026 and day.month == 7:
            rows.append(row(day, qty=-1.0, customer="C0"))
            continue
        rows += [row(day, qty=1.0, customer=f"C{c}") for c in range(5)]

    _, inputs, _, headline = _run(rows)

    assert inputs.trust.verdict == "blocked"
    assert headline.rule == 1 and "no sales in 2026-07" in headline.message


def test_the_frequency_series_is_orders_per_buyer_like_the_lever() -> None:
    """Step 4's descriptive frequency divides by buyers, as level 1 does: Ann
    buys daily in October (31 orders), Bob only returns - 31 / 1 = 31, not
    31 / 2 (mutation check, 2E)."""
    from stages.diagnose.signals import monthly_series

    rows = [row(day, qty=1.0, customer="Ann") for day in _days(date(2011, 9, 1), date(2011, 10, 31))]
    rows.append(row(date(2011, 10, 5), qty=-1.0, customer="Bob"))

    table = monthly_series(run_data(rows))

    assert table.loc["2011-10", "frequency"] == 31.0
    assert table.loc["2011-10", "active_customers"] == 2.0
