"""Session 2E-l, doubt-review cycle 1 finding 5, written before the fix.

A name-only line takes the class of the one SKU its name is sold under when
the name itself is unanswered (2E-l). "A product" said for the NAME is an
answer: the user is the final authority (CLAUDE.md 3.3), so those lines stay
products - before the fix the frontend dropped that answer and the lines
became charges anyway.
"""

import pandas as pd

from contracts.cleaning import LineClassAnswer, OrderConfirmations
from shared.products import product_keys
from shared.transactions import parse_transactions

MAPPING = {"Date": "transaction_date", "Qty": "quantity", "Price": "unit_price", "Cust": "customer",
           "Sku": "sku", "Name": "product_name"}


def _postage() -> pd.DataFrame:
    # POST sold with its name; a refund of it rung by name alone.
    return pd.DataFrame([{"Date": "2026-08-03", "Cust": "Ann", "Sku": sku, "Name": "POSTAGE", "Qty": qty,
                          "Price": "5"} for sku, qty in (("POST", "1"), (None, "-1"))])


def test_a_product_answer_for_the_name_keeps_its_lines_products() -> None:
    answers = OrderConfirmations(line_classes=[
        LineClassAnswer(value="POST", field="sku", line_class="charge"),
        LineClassAnswer(value="POSTAGE", field="product_name", line_class="product"),
    ])

    parsed = parse_transactions(_postage(), MAPPING, answers)

    assert parsed.line_class.fillna("product").tolist() == ["charge", "product"]
    assert parsed.returned.tolist() == [False, True]
    # Its own name, not the classed SKU's key: a classed SKU names no product.
    assert product_keys(_postage(), parsed).fillna("none").tolist() == ["none", "name:postage"]


def test_unanswered_the_name_still_takes_the_class_of_its_one_sku() -> None:
    answers = OrderConfirmations(line_classes=[LineClassAnswer(value="POST", field="sku", line_class="charge")])

    parsed = parse_transactions(_postage(), MAPPING, answers)

    assert parsed.line_class.tolist() == ["charge", "charge"]
    assert parsed.returned.tolist() == [False, False]


def test_a_product_answer_for_a_sku_is_the_same_as_none() -> None:
    answers = OrderConfirmations(line_classes=[LineClassAnswer(value="POST", field="sku", line_class="product")])

    parsed = parse_transactions(_postage(), MAPPING, answers)

    assert parsed.line_class.isna().tolist() == [True, True]
    assert product_keys(_postage(), parsed).tolist() == ["sku:post", "sku:post"]
