"""Session 2E-d2 doubt-review cycle 3 (the bound), the small local fixes,
written before them. F1 and F2 (headlines when the change sits in the classed
lines or the deductions) are split out under the stop rule, not patched here.

- F3 (FABRICATE): classing a SKU changed which SKU an unanswered name-only
  line takes (2E-f L4): the vote read sale lines only, and a classed fee is
  no sale, so "Manual" went from two SKUs to one and a 900 line joined WHITE
  HEART. The vote reads the lines as if nothing were classed; a classed SKU
  is still never taken.
- F4 (FABRICATE): classing only the charges made a new customer returning:
  a postage refund rung without a SKU no longer netted the classed POST sale.
  The first-day netting keys every line as it would be keyed unanswered.
- F5: two finite amounts whose sum overflows crashed the schema step.
- F6: which name is a key's commonest decided, on a tie, by row order - and
  so whether the key was asked. A tie goes to a name with a class word (a
  false question costs one answer), then to the first in order of text.
"""

from datetime import UTC, datetime

import pandas as pd
import pytest

from contracts.cleaning import LineClassAnswer, OrderConfirmations
from stages.analyze.assemble import assemble_metrics
from stages.ingest.non_product_lines import non_product_candidates

NOW = datetime(2026, 9, 26, 12, 0, tzinfo=UTC)
MAPPING = {"Date": "transaction_date", "Qty": "quantity", "Price": "unit_price", "Cust": "customer",
           "Sku": "sku", "Name": "product_name"}


def _frame(rows: list[tuple]) -> pd.DataFrame:
    return pd.DataFrame([dict(zip(("Date", "Cust", "Sku", "Name", "Qty", "Price"), row, strict=True))
                         for row in rows])


def test_classing_a_sku_does_not_move_an_unanswered_name_only_line() -> None:
    """August: M "Manual" 2 @ 20, 85123A "WHITE HEART" 1 @ 3, one 85123A
    line named "Manual" 1 @ 3, and a name-only "Manual" 1 @ 900. "Manual"
    names two SKUs, so the 900 line is its own product, classed M or not."""
    rows = [("2026-07-03", "Ann", "85123A", "WHITE HEART", "1", "3"),
            ("2026-08-03", "Ann", "M", "Manual", "2", "20"), ("2026-08-03", "Ann", "85123A", "WHITE HEART", "1", "3"),
            ("2026-08-04", "Bob", "85123A", "Manual", "1", "3"), ("2026-08-05", "Cy", None, "Manual", "1", "900"),
            ("2026-09-01", "Ann", "85123A", "WHITE HEART", "1", "3")]
    adjustment = OrderConfirmations(line_classes=[LineClassAnswer(value="M", field="sku", line_class="adjustment")])

    classed = assemble_metrics(_frame(rows), MAPPING, NOW, adjustment).products.top_products

    assert [(p.product, p.revenue) for p in classed] == [("Manual", 900.0), ("WHITE HEART", 6.0)]


def test_classing_only_the_charges_leaves_a_new_customer_new() -> None:
    """Bob's first day: MUG 2 @ 10, POST "POSTAGE" 1 @ 5, and the postage
    refunded -1 @ 5 on a line rung without a SKU."""
    rows = [("2026-07-03", "Ann", "M1", "MUG", "1", "10"), ("2026-08-05", "Bob", "M1", "MUG", "2", "10"),
            ("2026-08-05", "Bob", "POST", "POSTAGE", "1", "5"), ("2026-08-05", "Bob", None, "POSTAGE", "-1", "5"),
            ("2026-09-01", "Ann", "M1", "MUG", "1", "10")]
    charge = OrderConfirmations(line_classes=[LineClassAnswer(value="POST", field="sku", line_class="charge")])

    unanswered = assemble_metrics(_frame(rows), MAPPING, NOW).customers.new_vs_returning
    classed = assemble_metrics(_frame(rows), MAPPING, NOW, charge).customers.new_vs_returning

    assert (unanswered.new_customers, unanswered.new_revenue) == (1, pytest.approx(20.0))
    assert (classed.new_customers, classed.new_revenue) == (1, pytest.approx(20.0))


def test_a_sum_that_overflows_does_not_crash_the_candidates() -> None:
    mapping = {"Day": "transaction_date", "Qty": "quantity", "Price": "unit_price", "Sku": "sku",
               "Name": "product_name"}
    df = pd.DataFrame({"Day": "2026-08-03", "Sku": "POST", "Name": "POSTAGE", "Qty": ["1e154", "1e154"],
                       "Price": ["1e154", "1e154"]})

    assert non_product_candidates(df, mapping) == []


@pytest.mark.parametrize("order", [["POSTAGE", "MUG"], ["MUG", "POSTAGE"]])
def test_a_tie_for_the_commonest_name_does_not_depend_on_row_order(order: list[str]) -> None:
    mapping = {"Day": "transaction_date", "Qty": "quantity", "Price": "unit_price", "Sku": "sku",
               "Name": "product_name"}
    df = pd.DataFrame({"Day": "2026-08-03", "Sku": "S1", "Name": order, "Qty": "1", "Price": "5"})

    assert [(c.value, c.name, c.suggested) for c in non_product_candidates(df, mapping)] == [
        ("S1", "POSTAGE", "charge")]
