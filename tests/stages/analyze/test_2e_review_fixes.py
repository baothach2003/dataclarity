"""The 2E doubt-review's stage 2 findings, each written from the reviewer's
reproduction before the fix (Thach's decisions, 2E).

F1  a buyers count per period (customers with a sale row), beside
    active_customers (any counted row, 3C).
F3  the previous month is covered only by SALES: a month holding only refund
    lines is not a base.
F5  a contribution share over a residue total change - even when the net
    totals are themselves residue - is null (was 1.8e20).
F6  a percentage of a residue base next to a residue month is null (was -100%).
F7  a residue "decline" is not a decliner.
F8  the model ties the nullable fields to the facts that make them null.
F9  return_rate is never negative; reasons read correctly.
"""

from datetime import UTC, datetime

import pandas as pd
import pytest
from pydantic import ValidationError

from contracts.metrics import MetricsContract
from shared.transactions import pct_change
from stages.analyze.assemble import assemble_metrics
from tests.contracts.test_metrics import REASON, metrics_payload

NOW = datetime(2026, 9, 19, tzinfo=UTC)
MAP = {"Date": "transaction_date", "Qty": "quantity", "Price": "unit_price",
       "Product": "product_name", "Cust": "customer", "Cat": "category"}


def r(day, qty, price, product="Widget", cust="Alice", cat="A"):
    return {"Date": day, "Qty": str(qty), "Price": str(price), "Product": product,
            "Cust": cust, "Cat": cat}


def run(rows):
    return assemble_metrics(pd.DataFrame(rows), MAP, now=NOW)


# --- F1 --------------------------------------------------------------------------------


def test_buyers_counts_customers_with_a_sale_and_active_counts_anyone() -> None:
    """August: Alice buys, Bob only returns. Active 2 (3C: any counted row),
    buyers 1 (a sale row). July: Alice buys - 1 and 1."""
    core = run([r("2026-07-01", 1, 10), r("2026-08-01", 1, 10),
                r("2026-08-31", -1, 10, cust="Bob")]).core

    assert (core.active_customers_current, core.buyers_current) == (2, 1)
    assert (core.active_customers_previous, core.buyers_previous) == (1, 1)


# --- F3 --------------------------------------------------------------------------------


def test_a_previous_month_holding_only_refunds_is_not_a_base() -> None:
    """The reviewer's f7 shape: July holds one refund line a day and no sale.
    It was "complete" (counted rows from the 1st) with orders 0 -> 155."""
    rows = [r(f"2026-06-{d:02d}", 1, 10) for d in range(1, 31)]
    rows += [r(f"2026-07-{d:02d}", -1, 10) for d in range(1, 32)]
    rows += [r(f"2026-08-{d:02d}", 1, 10) for d in range(1, 32)]

    period = run(rows).period

    assert period.previous_complete is False
    assert "no sales in 2026-07" in period.previous_incomplete_reason


# --- F5, F6, F7: residue whose scale is itself residue -----------------------------------


def test_a_contribution_over_residue_is_null_even_when_both_nets_are_residue() -> None:
    """f2 case B: July A +100, B -100 (net 0); August A 0.1 + 0.2, B -0.3 (net
    residue). The total change is 5.55e-17, and the shares read 1.8e20."""
    metrics = run([r("2026-07-01", 1, 100.0, "P1", cat="A"),
                   r("2026-07-01", -1, 100.0, "P2", cat="B"),
                   r("2026-08-01", 1, 0.1, "P1", cat="A"), r("2026-08-02", 1, 0.2, "P1", cat="A"),
                   r("2026-08-31", -1, 0.3, "P2", cat="B")])

    assert all(c.contribution_pct is None for c in metrics.by_dimension.category)
    assert "total change" in metrics.by_dimension.contribution_reason


def test_a_percentage_is_null_when_both_months_net_to_residue() -> None:
    """f2 case A: each month sells 0.1 + 0.2 and refunds 0.3. It read -100%."""
    metrics = run([r("2026-07-01", 1, 0.1), r("2026-07-02", 1, 0.2), r("2026-07-03", -1, 0.3),
                   r("2026-08-01", 1, 0.1), r("2026-08-02", 1, 0.2), r("2026-08-03", -1, 0.3),
                   r("2026-08-31", 1, 0.7), r("2026-08-31", -1, 0.7)])

    assert metrics.core.revenue_change_pct is None
    assert "residue" in metrics.core.revenue_change_pct_reason


def test_pct_change_judges_residue_against_the_money_that_moved() -> None:
    """pct_change(0.0, 0.1 + 0.2 - 0.3) was -100%: the base was compared only
    with itself and a zero month. Against 0.6 of money moved it is residue."""
    change = pct_change(0.0, 0.1 + 0.2 - 0.3, 0.6)

    assert change.value is None and "residue" in change.reason


def test_a_residue_decline_is_not_a_decliner() -> None:
    """f2 case C: P1 sells 0.1 + 0.2 in July and 0.3 in August - the same 0.30.
    It was listed with revenue_change -5.55e-17."""
    decliners = run([r("2026-07-01", 1, 0.1, "P1"), r("2026-07-02", 1, 0.2, "P1"),
                     r("2026-07-03", 1, 100, "P9"),
                     r("2026-08-01", 1, 0.3, "P1"), r("2026-08-31", 1, 100, "P9")]
                    ).products.biggest_decliners

    assert [d.product for d in decliners] == []


# --- F8: the facts that make a field null -------------------------------------------------


def test_the_model_refuses_a_comparison_beside_an_incomplete_previous_month() -> None:
    payload = metrics_payload()
    payload["period"].update(previous_complete=False, previous_incomplete_reason=REASON)

    with pytest.raises(ValidationError, match="incomplete"):
        MetricsContract.model_validate(payload)


@pytest.mark.parametrize("orders,aov,reason", [(2, None, REASON), (0, 12.5, None)])
def test_the_model_ties_aov_to_whether_there_were_orders(orders, aov, reason) -> None:
    payload = metrics_payload()
    payload["core"].update(orders_current=orders, aov_current=aov, aov_current_reason=reason)

    with pytest.raises(ValidationError, match="orders"):
        MetricsContract.model_validate(payload)


# --- F9 --------------------------------------------------------------------------------------


def test_a_negative_return_rate_is_refused() -> None:
    payload = metrics_payload()
    payload["core"]["return_rate_current"] = -3.0

    with pytest.raises(ValidationError, match="return_rate_current"):
        MetricsContract.model_validate(payload)


def test_reasons_read_as_sentences() -> None:
    """A zero base read "the previous value is no previous value"; a negative
    residue base was called a loss."""
    zero = pct_change(50.0, 0.0)
    residue = pct_change(1000.0, -1.39e-17)

    assert "value is no previous value" not in zero.reason and "no previous value" in zero.reason
    assert "residue" in residue.reason and "negative" not in residue.reason


def test_buyers_are_counted_in_the_previous_month_too() -> None:
    """July: Alice buys, Carol only returns - active 2, buyers 1 (mutation
    check, 2E: the previous month's count was unpinned)."""
    core = run([r("2026-07-01", 1, 10), r("2026-07-15", -1, 10, cust="Carol"),
                r("2026-08-01", 1, 10), r("2026-08-31", 1, 10)]).core

    assert (core.active_customers_previous, core.buyers_previous) == (2, 1)
