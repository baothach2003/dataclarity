"""Session 2E-t3's second review (#2): a file whose every order id is refused
as a receipt stopped the parse under pandas 3 - an empty datetime mapper is
cast to float and raises. Older than 2E-t3; Review's whole-file summary made
it reachable, the receipt question answered Yes. Worked by hand: O1's refund
is dated before its sale, so O1 is no receipt, no line is filled, and each
line is its order's."""

import pandas as pd

from contracts.cleaning import OrderConfirmations
from shared.transactions import parse_transactions

MAPPING = {"Day": "transaction_date", "Order": "order_id", "Who": "customer", "Sku": "sku", "Qty": "quantity",
           "Price": "unit_price"}


def test_a_file_with_no_receipt_parses_when_the_ids_are_receipts() -> None:
    df = pd.DataFrame({"Day": ["2026-08-03", "2026-07-15"], "Order": ["O1", "O1"], "Who": ["Ann", "Ann"],
                       "Sku": ["A1", "A1"], "Qty": ["2", "-1"], "Price": ["10", "10"]})

    parsed = parse_transactions(df, MAPPING, OrderConfirmations(order_id_is_receipt=True))

    assert parsed.orders_basis == "order_id"
    assert not parsed.receipt_fillable.any()
    assert parsed.order_key.nunique() == 2  # one day each: two orders
