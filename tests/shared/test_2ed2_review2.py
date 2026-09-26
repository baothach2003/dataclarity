"""Session 2E-d2 doubt-review cycle 2, written before the fixes.

- #7: the "(not a product)" member was flagged `is_data_gap`, which the
  contract calls a data-completeness signal - postage, Online Retail II's
  second-largest product member of 2011-11, would read as missing data to the
  first reader of the flag. It gets its own flag, `is_not_a_product`, and is
  still kept out of the new/removed lists and of recommendations.
- #1 (a recorded consequence, not a change): a discount booked -1 @ +price is
  a return line unanswered, so a first receipt carrying one "opened with a
  refund"; classed a discount it is a deduction (2E-c), and the customer is
  new. The class corrects that - it follows from 2E-c's rule.
"""

from datetime import UTC, datetime

import pandas as pd
import pytest

from contracts.cleaning import LineClassAnswer, OrderConfirmations
from contracts.diagnosis import Member
from stages.analyze.assemble import assemble_metrics
from stages.diagnose.inputs import build_run_data
from stages.diagnose.members import build_dimension, product_totals

NOW = datetime(2026, 9, 26, 12, 0, tzinfo=UTC)
MAPPING = {"Date": "transaction_date", "Qty": "quantity", "Price": "unit_price", "Cust": "customer",
           "Sku": "sku", "Name": "product_name"}


def _frame(rows: list[tuple]) -> pd.DataFrame:
    return pd.DataFrame([dict(zip(("Date", "Cust", "Sku", "Name", "Qty", "Price"), row, strict=True))
                         for row in rows])


def test_the_not_a_product_member_is_flagged_as_such_not_as_missing_data() -> None:
    charge = OrderConfirmations(line_classes=[LineClassAnswer(value="POST", field="sku", line_class="charge")])
    df = _frame([("2026-07-03", "Ann", "M1", "MUG", "2", "10"), ("2026-08-03", "Ann", "M1", "MUG", "1", "10"),
                 ("2026-08-03", "Ann", "POST", "POSTAGE", "1", "8"), ("2026-09-01", "Ann", "M1", "MUG", "1", "10")])
    metrics = assemble_metrics(df, MAPPING, NOW, charge)
    totals = product_totals(build_run_data(df, MAPPING, metrics, charge))

    dimension = build_dimension("product", totals, delta_total=-2.0)

    [bucket] = [m for m in dimension.members if m.name == "(not a product)"]
    assert (bucket.is_not_a_product, bucket.is_data_gap) == (True, False)
    # Postage appears only in August - still no "new product".
    assert dimension.new_members == []


def test_a_member_is_not_both() -> None:
    with pytest.raises(ValueError, match="is_not_a_product"):
        Member(name="x", rev_prev=0.0, rev_cur=1.0, delta=1.0, share_of_change=1.0, is_data_gap=True,
               is_not_a_product=True)


def test_a_classed_discount_on_a_first_receipt_leaves_the_customer_new() -> None:
    """Zed's first receipt: CUP 3 @ 30 and a discount booked -1 @ 2. Read as
    a return line his history opened with a refund; a discount it is not."""
    discount = OrderConfirmations(line_classes=[LineClassAnswer(value="D", field="sku", line_class="discount")])
    df = _frame([("2026-07-03", "Ann", "M1", "MUG", "2", "10"), ("2026-08-05", "Zed", "C1", "CUP", "3", "30"),
                 ("2026-08-05", "Zed", "D", "Discount", "-1", "2"), ("2026-09-01", "Ann", "M1", "MUG", "1", "10")])

    unanswered = assemble_metrics(df, MAPPING, NOW).customers.new_vs_returning
    classed = assemble_metrics(df, MAPPING, NOW, discount).customers.new_vs_returning

    assert (unanswered.new_customers, classed.new_customers) == (0, 1)
    assert classed.new_revenue == pytest.approx(88.0)
