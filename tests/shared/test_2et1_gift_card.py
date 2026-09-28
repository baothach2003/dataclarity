"""Session 2E-t1 (Thach, 2026-09-28): "gift_card" joins the line classes a user
can answer in Review (the line taxonomy's decision 4: a voucher sold is a
liability until redeemed - outside revenue, not counted, reported). Every
consumer of the widened enum reads it in the same session (CONTRACTS section
10): until stages 2 and 3 read cleaned.csv's classes (2E-t2), a gift-card
answer is left out exactly as a fee is. Written before the change."""

from datetime import UTC, datetime

import pandas as pd

from contracts.cleaning import LineClassAnswer, OrderConfirmations
from shared.products import product_keys
from shared.transactions import parse_transactions
from stages.analyze.metrics_core import compute_core_metrics

MAPPING = {"Day": "transaction_date", "Qty": "quantity", "Price": "unit_price", "Sku": "sku",
           "Name": "product_name", "Order": "order_id", "Who": "customer"}
GIFT = OrderConfirmations(line_classes=[LineClassAnswer(value="GIFT_10", field="sku", line_class="gift_card")])


def _lines() -> pd.DataFrame:
    rows = [("2026-07-03", "A1", "Mug", "2", "5", "O1", "Ann"),
            ("2026-08-03", "A1", "Mug", "3", "5", "O2", "Ann"),
            ("2026-08-04", "GIFT_10", "Gift voucher 10", "1", "10", "O3", "Bo"),
            ("2026-08-05", "GIFT_10", "Gift voucher 10", "-1", "10", "O4", "Bo"),
            # A September sale: the file covers August to its end.
            ("2026-09-02", "A1", "Mug", "1", "5", "O5", "Ann")]
    return pd.DataFrame(rows, columns=["Day", "Sku", "Name", "Qty", "Price", "Order", "Who"])


def test_a_confirmed_gift_card_is_left_out_of_revenue_as_a_fee_is() -> None:
    parsed = parse_transactions(_lines(), MAPPING, GIFT)

    assert parsed.counted.tolist() == [True, True, False, False, True]
    assert parsed.left_out.tolist() == [False, False, True, True, False]
    assert parsed.sale.tolist() == [True, True, False, False, True]
    assert parsed.returned.tolist() == [False, False, False, False, False]
    assert product_keys(_lines(), parsed).isna().tolist() == [False, False, True, True, False]


def test_it_is_reported_in_non_product_with_its_money() -> None:
    _, core = compute_core_metrics(_lines(), MAPPING, datetime(2026, 9, 26, tzinfo=UTC), GIFT)

    # August: 3 x 5 of the mug; the voucher sold and refunded is no revenue.
    assert core.revenue_current == 15.0
    row = next(r for r in core.non_product if r.line_class == "gift_card")
    assert (row.lines, row.amount, row.amount_current) == (2, 0.0, 0.0)
    assert row.reason.startswith("2 lines classed in Review as gift cards are left out of revenue")
