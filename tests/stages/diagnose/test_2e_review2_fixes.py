"""The 2E doubt-review cycle 2 findings, each written from the reviewer's
reproduction before the fix (Thach's decisions, 2E).

F1  B1 on a month that netted zero or below: AOV is not positive, so the
    Shapley frequency term changes sign - "customers bought MORE often" was
    headlined while they bought three times less often.
F2  stage 3 judges residue against the money that moved, as stage 2 does:
    a change stage 2 calls residue has no best explanation in stage 3.
F3  a segment share over whole-file residue is null (stage 2).
F5  a tiny real base is not called "floating-point residue".
F7  D1's blocked evidence writes null, not the string "None", when no sale
    exists; an incomplete month's list reasons are never null.
"""

from datetime import date, timedelta

import pandas as pd
import pytest
from pydantic import ValidationError

from contracts.metrics import MetricsContract
from shared.transactions import pct_change
from stages.analyze.assemble import assemble_metrics
from stages.diagnose.headline import choose_headline
from stages.diagnose.hypotheses import evaluate_hypotheses
from stages.diagnose.step7_inputs import changes
from tests.contracts.test_metrics import REASON, metrics_payload
from tests.stages.diagnose.diagnose_fixtures import MAPPING, row, run_data
from tests.stages.diagnose.test_hypotheses import by_id, step7


def _month(year: int, month: int):
    day = date(year, month, 1)
    while day.month == month:
        yield day
        day += timedelta(days=1)


def _history(rows: list[dict], price: float = 100.0, **extra) -> None:
    for year, month in [(2025, m) for m in range(9, 13)] + [(2026, m) for m in range(1, 7)]:
        rows += [dict(row(day, qty=1.0, price=price, customer=f"C{day.day % 10}"), **extra)
                 for day in _month(year, month)]


def _diagnose(rows, mapping=MAPPING):
    data = run_data(rows, mapping)
    inputs = step7(data)
    results = evaluate_hypotheses(inputs)
    headline = choose_headline(inputs.trust, results, inputs.tree, changes(inputs))
    return data, by_id(results), headline


# --- F1 ------------------------------------------------------------------------------------


def test_b1_refuses_a_month_that_netted_below_zero() -> None:
    """f1b: July 93 orders at 100 and a 30,000 refund (-20,700); August 31
    orders at 500 and a 30,000 refund (-14,500). Frequency fell 9.3 -> 3.1,
    and B1 headlined "customers bought more often (+21,400)"."""
    rows: list[dict] = []
    _history(rows)
    for day in _month(2026, 7):
        rows += [row(day, qty=1.0, price=100.0, customer=f"C{day.day % 10}") for _ in range(3)]
    rows.append(row(date(2026, 7, 15), qty=-1.0, price=30000.0, customer="C0"))
    rows += [row(day, qty=1.0, price=500.0, customer=f"C{day.day % 10}") for day in _month(2026, 8)]
    rows.append(row(date(2026, 8, 15), qty=-1.0, price=30000.0, customer="C0"))
    rows.append(row(date(2026, 9, 1), qty=1.0, price=100.0, customer="C1"))

    _, verdicts, headline = _diagnose(rows)

    assert verdicts["B1"].verdict == "inconclusive"
    assert "zero or below" in verdicts["B1"].rule
    assert headline.hypothesis_id != "B1"


# --- F2 ------------------------------------------------------------------------------------


def test_a_change_stage_2_calls_residue_has_no_best_explanation_in_stage_3() -> None:
    """f2: both months net to residue (every sale refunded; July also 0.1 +
    0.2 - 0.3). Stage 2 said "the total change is nothing"; stage 3 headlined
    "like-for-like prices changed" on a +0.00 change."""
    mapping = {**MAPPING, "Cat": "category"}
    rows: list[dict] = []
    _history(rows, Cat="A")
    for day in _month(2026, 7):
        rows += [dict(row(day, qty=q, price=10.0, customer=f"C{day.day % 10}"), Cat="A")
                 for q in (1.0, -1.0)]
    rows += [dict(row(date(2026, 7, d), qty=q, price=p, customer="C3"), Cat="A")
             for d, q, p in ((3, 1.0, 0.1), (4, 1.0, 0.2), (5, -1.0, 0.3))]
    for day in _month(2026, 8):
        rows += [dict(row(day, qty=q, price=20.0, customer=f"C{day.day % 10}"), Cat="A")
                 for q in (1.0, -1.0)]
    rows.append(dict(row(date(2026, 9, 1), qty=1.0, price=100.0, customer="C1"), Cat="A"))

    data, verdicts, headline = _diagnose(rows, mapping)

    assert data.metrics.by_dimension.contribution_reason is not None  # stage 2: nothing
    assert headline.rule == 7 and headline.hypothesis_id is None
    assert all(v.share is None or abs(v.share) < 1e6 for v in verdicts.values())


# --- F3 ------------------------------------------------------------------------------------


def test_a_segment_share_of_whole_file_residue_is_null() -> None:
    """f6: Big buys and refunds 10 daily in July; Ann 0.1 + 0.2 - 0.3 and Bob
    0.3 - 0.1 - 0.2 in August. Whole-file monetary is residue next to ~620 of
    money moved, and a segment read -100% of it."""
    cells = []
    for day in _month(2026, 7):
        cells += [(day, 1, 10.0, "Big"), (day, -1, 10.0, "Big")]
    cells += [(date(2026, 8, 3), 1, 0.1, "Ann"), (date(2026, 8, 4), 1, 0.2, "Ann"),
              (date(2026, 8, 5), -1, 0.3, "Ann"), (date(2026, 8, 6), 1, 0.3, "Bob"),
              (date(2026, 8, 7), -1, 0.1, "Bob"), (date(2026, 8, 8), -1, 0.2, "Bob"),
              (date(2026, 9, 1), 1, 10.0, "Big"), (date(2026, 9, 1), -1, 10.0, "Big")]
    df = pd.DataFrame([{"Date": d.isoformat(), "Qty": str(q), "Price": repr(p),
                        "Product": "Widget", "Cust": c} for d, q, p, c in cells])

    customers = assemble_metrics(df, {"Date": "transaction_date", "Qty": "quantity",
                                      "Price": "unit_price", "Product": "product_name",
                                      "Cust": "customer"}).customers

    assert all(s.revenue_share_pct is None for s in customers.segments)
    assert customers.revenue_share_reason is not None


# --- F5 ------------------------------------------------------------------------------------


def test_a_tiny_real_base_is_not_called_residue() -> None:
    """July nets 0.01 (a real cent), August 31,000,000: no percentage. The
    reason states what the test measured - under a billionth of the money
    compared - rather than promising a base floor it does not apply (reworded
    by Thach's cycle-3 decision; the floor is a scheduled stage 2 item)."""
    change = pct_change(31_000_000.0, 0.01, 31_000_000.0 + 619.99)

    assert change.value is None
    assert "under a billionth" in change.reason and "too small" not in change.reason


# --- F7 ------------------------------------------------------------------------------------


def test_d1_block_evidence_writes_null_when_the_file_has_no_sale() -> None:
    """A file holding only a refund line: the block's first_sale is None."""
    data = run_data([row(date(2011, 1, 31), qty=-1.0)])
    d1 = next(c for c in step7(data).trust.checks if c.id == "D1")

    assert d1.status == "blocked"
    assert d1.evidence["first_sale"] is None


@pytest.mark.parametrize("field", ["contribution_reason", "customers_previous_reason"])
def test_an_incomplete_month_carries_its_reason_even_with_empty_lists(field) -> None:
    payload = metrics_payload()
    payload["period"].update(previous_complete=False, previous_incomplete_reason=REASON)
    payload["core"].update(revenue_change_pct=None, revenue_change_pct_reason=REASON)
    payload["products"].update(biggest_decliners=None, biggest_decliners_reason=REASON)
    payload["by_dimension"] = {"country": [], "category": [], "contribution_reason": REASON}
    payload["customers"].update(segments=[], customers_previous_reason=REASON)
    MetricsContract.model_validate(payload)  # the complete, consistent shape passes

    payload["by_dimension" if field == "contribution_reason" else "customers"][field] = None

    with pytest.raises(ValidationError, match="reason"):
        MetricsContract.model_validate(payload)


def test_b1_refuses_when_only_the_previous_month_netted_below_zero() -> None:
    """July: 93 orders at 100 and a 30,000 refund (-20,700); August: 31
    ordinary orders at 100 (3,100). The previous month alone has a negative
    AOV, which is enough to flip the frequency term (mutation check, 2E)."""
    rows: list[dict] = []
    _history(rows)
    for day in _month(2026, 7):
        rows += [row(day, qty=1.0, price=100.0, customer=f"C{day.day % 10}") for _ in range(3)]
    rows.append(row(date(2026, 7, 15), qty=-1.0, price=30000.0, customer="C0"))
    rows += [row(day, qty=1.0, price=100.0, customer=f"C{day.day % 10}") for day in _month(2026, 8)]
    rows.append(row(date(2026, 9, 1), qty=1.0, price=100.0, customer="C1"))

    data, verdicts, _ = _diagnose(rows)

    assert (data.metrics.core.revenue_previous, data.metrics.core.revenue_current) == (-20700.0, 3100.0)
    assert verdicts["B1"].verdict == "inconclusive"
