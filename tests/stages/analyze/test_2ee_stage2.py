"""Session 2E-e, stage 2 (Thach), written before the change: with `order_id`
mapped, orders are distinct order ids with a sale row, AOV is net revenue per
order, return rate is orders with a return line per order with a sale line,
and RFM frequency counts a customer's orders; metrics.json names the basis.
"""

from datetime import date

import pandas as pd
import pytest
from pydantic import ValidationError

from contracts.metrics import MetricsContract
from stages.analyze.assemble import SCHEMA_VERSION, assemble_metrics
from stages.analyze.rfm import rfm_snapshot
from tests.stages.diagnose.diagnose_fixtures import MAPPING, NOW, row

WITH_ORDERS = {**MAPPING, "Inv": "order_id"}


def _invoiced() -> list[dict]:
    """July: five invoices of two lines at 10 (100). August: four invoices of
    three lines at 10 (120), and invoice R returns one unit (-10)."""
    rows = []
    for index in range(5):
        rows += [{**row(date(2026, 7, 1 + index), price=10.0, customer=f"C{index}"),
                  "Inv": f"J{index}"} for _ in range(2)]
    for index in range(4):
        rows += [{**row(date(2026, 8, 1 + index), price=10.0, customer=f"C{index}"),
                  "Inv": f"A{index}"} for _ in range(3)]
    rows.append({**row(date(2026, 8, 9), qty=-1.0, price=10.0, customer="C0"), "Inv": "R"})
    rows.append({**row(date(2026, 9, 1), price=10.0, customer="C0"), "Inv": "S"})
    return rows


def test_orders_aov_and_return_rate_count_invoices() -> None:
    """By hand, August: 4 orders (not 12 lines); AOV (120 - 10) / 4 = 27.5
    (not 110 / 12); return rate 1 order with a return line / 4 = 0.25 (not
    1 / 12). July: 5 orders, AOV 20."""
    core = assemble_metrics(pd.DataFrame(_invoiced()), WITH_ORDERS, now=NOW).core

    assert core.orders_basis == "order_id"
    assert (core.orders_current, core.orders_previous) == (4, 5)
    assert core.aov_current == pytest.approx(27.5)
    assert core.aov_previous == pytest.approx(20.0)
    assert core.return_rate_current == pytest.approx(0.25)


def test_without_order_id_the_figures_are_lines_and_say_so() -> None:
    """The same rows, order_id not mapped: 12 lines, 110 / 12, 1 / 12."""
    core = assemble_metrics(pd.DataFrame(_invoiced()), MAPPING, now=NOW).core

    assert (core.orders_basis, core.orders_basis_reason) == ("lines", None)
    assert core.orders_current == 12
    assert core.aov_current == pytest.approx(110 / 12)
    assert core.return_rate_current == pytest.approx(1 / 12)


def test_an_order_id_that_is_not_one_is_refused_with_a_reason() -> None:
    """The customer column mapped as order_id: every "order" spans days."""
    rows = [{**r, "Inv": r["Cust"]} for r in _invoiced()]

    core = assemble_metrics(pd.DataFrame(rows), WITH_ORDERS, now=NOW).core

    assert core.orders_basis == "lines"
    assert "several days or customers" in core.orders_basis_reason
    assert core.orders_current == 12


def test_rfm_frequency_counts_orders_not_lines() -> None:
    """Ann: two invoices of three lines = frequency 2, not 6."""
    table = pd.DataFrame({
        "customer": ["ann"] * 6,
        "date": pd.to_datetime(["2011-11-01"] * 3 + ["2011-11-20"] * 3),
        "revenue": [10.0] * 6, "sale": [True] * 6,
        "order": ["X"] * 3 + ["Y"] * 3,
    })

    assert rfm_snapshot(table, date(2011, 12, 1)).loc["ann", "frequency"] == 2


def test_metrics_json_is_major_version_5_or_the_current_one() -> None:
    # 5.0 in 2E-e; 6.0 in 2E-f; 7.0 in 2E-g; 8.0 in 2E-h; 9.0 since 2E-e2. A 4.x file is refused.
    assert SCHEMA_VERSION == "10.0"  # 9.0 in 2E-e2; 10.0 since 2E-k
    payload = assemble_metrics(pd.DataFrame(_invoiced()), WITH_ORDERS,
                               now=NOW).model_dump(mode="json")
    payload["schema_version"] = "4.0"

    with pytest.raises(ValidationError, match="re-analyse"):
        MetricsContract.model_validate(payload)


def test_a_return_order_counts_once_however_many_lines_it_holds() -> None:
    """Mutation check (2E-e): invoice R returns two lines. On basis order_id the
    return rate is orders holding a return line / orders = 1 / 4 = 0.25, not
    2 return lines / 4 = 0.5."""
    rows = _invoiced() + [{**row(date(2026, 8, 9), qty=-1.0, price=10.0, customer="C0"),
                           "Inv": "R"}]

    core = assemble_metrics(pd.DataFrame(rows), WITH_ORDERS, now=NOW).core

    assert core.return_rate_current == pytest.approx(0.25)
