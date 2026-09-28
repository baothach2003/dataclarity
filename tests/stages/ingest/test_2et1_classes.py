"""Session 2E-t1 (Thach, 2026-09-28), the line classifier - written before the
code. docs/LINE_TAXONOMY.md section 4.2: every line gets exactly one class of
the closed list, by ordered rules, in stage 1:

 1. typed "in" -> stock_in (Q25: outside revenue whatever its sign or item)
 2. no finite quantity -> unmeasurable
 3. no finite price -> unmeasurable
 4. quantity x price not finite -> unmeasurable
 5. the user's item: charge / discount / cost / adjustment -> that class;
    gift_card -> gift_card_sale (amount >= 0) or gift_card_redemption
 6. a product or pooled item (P), amount 0 -> no_money / pooled_no_money
 7. P, quantity > 0 and amount > 0 -> sale / pooled_sale
 8. P, quantity < 0 and amount < 0 -> customer_return / pooled_return
 9. P otherwise -> allowance / pooled_allowance
P is pooled when the user answered "pooled", or the line has neither SKU nor
name. The date never decides the class. The suggestion is the pending
line-class candidate of the line's key (4.1), for keys nobody answered.
"""

import itertools
import math

import numpy as np
import pandas as pd
import pytest

from contracts.cleaning import CLEANED_LINE_CLASSES, LineClassAnswer, OrderConfirmations
from stages.ingest.line_taxonomy import classify_lines

MAPPING = {"Day": "transaction_date", "Qty": "quantity", "Price": "unit_price", "Sku": "sku",
           "Name": "product_name", "Type": "transaction_type"}


def _frame(rows: list[dict]) -> pd.DataFrame:
    """Text cells, as stages 2 and 3 read cleaned.csv; a missing key is a blank."""
    columns = ["Day", "Sku", "Name", "Qty", "Price", "Type"]
    defaults = {"Day": "2026-08-03", "Sku": None, "Name": None, "Qty": "1", "Price": "10", "Type": None}
    return pd.DataFrame([{c: row.get(c, defaults[c]) for c in columns} for row in rows], dtype=object)


def _answers(**classes: str) -> OrderConfirmations:
    return OrderConfirmations(line_classes=[LineClassAnswer(value=v, field="sku", line_class=c)
                                            for v, c in classes.items()])


def _classes(rows: list[dict], answers: OrderConfirmations | None = None) -> list[str]:
    return classify_lines(_frame(rows), MAPPING, answers or OrderConfirmations())["line_class"].tolist()


# --- rule 1: "in" first ---------------------------------------------------------

@pytest.mark.parametrize("row", [
    {"Sku": "A1", "Qty": "5", "Price": "4", "Type": "in"},        # a delivery at a price
    {"Sku": "A1", "Qty": "-30", "Price": "4", "Type": "in"},      # a receipt correction (review 5 #1)
    {"Sku": "A1", "Qty": "2", "Price": "5", "Type": " IN "},      # a customer return booked "in" (#2)
    {"Sku": "A1", "Qty": None, "Price": "4", "Type": "in"},       # no quantity: still stock received
    {"Sku": "A1", "Qty": "5", "Price": None, "Type": "in"},       # no price (2E-g F1)
    {"Sku": "POST", "Qty": "-1", "Price": "9", "Type": "in"},     # an item the user classed
])
def test_every_line_typed_in_is_stock_in(row: dict) -> None:
    assert _classes([row], _answers(POST="charge")) == ["stock_in"]


# --- rules 2-4: unmeasurable ------------------------------------------------------

@pytest.mark.parametrize("row", [
    {"Sku": "A1", "Qty": None}, {"Sku": "A1", "Qty": "two"}, {"Sku": "A1", "Qty": "inf"},
    {"Sku": "A1", "Price": None}, {"Sku": "A1", "Price": "-inf"},
    {"Sku": "A1", "Qty": "1e200", "Price": "1e200"},  # finite, but the amount overflows
    {"Sku": "POST", "Price": None},                     # before the user's item
])
def test_a_line_that_cannot_be_measured_is_unmeasurable(row: dict) -> None:
    assert _classes([row], _answers(POST="charge")) == ["unmeasurable"]


# --- rule 5: the user's item ---------------------------------------------------------

@pytest.mark.parametrize(("answer", "qty", "price", "expected"), [
    ("charge", "1", "9", "charge"), ("charge", "-1", "9", "charge"), ("charge", "1", "0", "charge"),
    ("discount", "-1", "5", "discount"), ("discount", "1", "5", "discount"),
    ("cost", "1", "-12", "cost"), ("adjustment", "1", "-100", "adjustment"),
    ("gift_card", "1", "10", "gift_card_sale"), ("gift_card", "1", "0", "gift_card_sale"),
    ("gift_card", "-1", "10", "gift_card_redemption"),
])
def test_the_users_item_decides_at_any_sign(answer: str, qty: str, price: str, expected: str) -> None:
    assert _classes([{"Sku": "X", "Qty": qty, "Price": price}], _answers(X=answer)) == [expected]


# --- rules 6-9: products and pooled items by their signs --------------------------------

@pytest.mark.parametrize(("qty", "price", "product", "pooled"), [
    ("2", "5", "sale", "pooled_sale"),
    ("-2", "5", "customer_return", "pooled_return"),
    ("0", "5", "no_money", "pooled_no_money"),
    ("3", "0", "no_money", "pooled_no_money"),
    ("-3", "0", "no_money", "pooled_no_money"),
    ("1", "-5", "allowance", "pooled_allowance"),   # a refund or a coupon at a negative price
    ("-1", "-5", "allowance", "pooled_allowance"),  # a positive amount on a negative quantity
])
def test_a_product_and_a_pooled_item_by_their_signs(qty: str, price: str, product: str, pooled: str) -> None:
    rows = [{"Sku": "A1", "Qty": qty, "Price": price},           # a product (unanswered)
            {"Sku": "M", "Qty": qty, "Price": price},            # pooled, answered
            {"Sku": None, "Name": None, "Qty": qty, "Price": price}]  # neither SKU nor name: pooled by rule
    assert _classes(rows, _answers(M="pooled")) == [product, pooled, pooled]


def test_a_product_answered_a_product_is_a_product() -> None:
    answers = OrderConfirmations(line_classes=[LineClassAnswer(value="POSTAGE", field="product_name",
                                                               line_class="product")])
    assert _classes([{"Name": "POSTAGE", "Qty": "1", "Price": "3"}], answers) == ["sale"]


def test_the_date_never_decides_the_class() -> None:
    rows = [{"Sku": "A1", "Day": None}, {"Sku": "A1", "Day": "not a date"}, {"Sku": "A1", "Day": "now"}]
    assert _classes(rows) == ["sale", "sale", "sale"]


# --- every combination: exactly one class, the one the rules give --------------------------

def _oracle(typed_in: bool, qty: float, price: float, item: str | None, gap: bool) -> str:
    """Section 4.2 line by line, written independently of the vectorised code."""
    if typed_in:
        return "stock_in"
    if not math.isfinite(qty) or not math.isfinite(price):
        return "unmeasurable"
    with np.errstate(over="ignore"):
        amount = float(np.float64(qty) * np.float64(price))
    if not math.isfinite(amount):
        return "unmeasurable"
    if item in ("charge", "discount", "cost", "adjustment"):
        return item
    if item == "gift_card":
        return "gift_card_sale" if amount >= 0 else "gift_card_redemption"
    pooled = item == "pooled" or (item is None and gap)
    if amount == 0:
        base = "no_money"
    elif qty > 0 and amount > 0:
        base = "sale"
    elif qty < 0 and amount < 0:
        return "pooled_return" if pooled else "customer_return"
    else:
        base = "allowance"
    return f"pooled_{base}" if pooled else base


QUANTITIES = {"3": 3.0, "-3": -3.0, "0": 0.0, "": math.nan, "inf": math.inf, "1e200": 1e200}
PRICES = {"2.5": 2.5, "-2.5": -2.5, "0": 0.0, "": math.nan, "1e200": 1e200}
ITEMS = [None, "product", "pooled", "charge", "discount", "cost", "adjustment", "gift_card", "gap"]


def test_every_combination_of_the_inputs_gets_exactly_the_class_its_rules_give() -> None:
    rows, expected = [], []
    answers = []
    for n, (typed_in, (q_text, q), (p_text, p), item) in enumerate(
            itertools.product([False, True], QUANTITIES.items(), PRICES.items(), ITEMS)):
        gap = item == "gap"
        sku = None if gap else f"K{n}"
        if item not in (None, "gap"):
            answers.append(LineClassAnswer(value=sku, field="sku", line_class=item))
        rows.append({"Sku": sku, "Name": None, "Qty": q_text or None, "Price": p_text or None,
                     "Type": "in" if typed_in else "out"})
        expected.append(_oracle(typed_in, q, p, None if item in ("product", "gap") else item, gap))
    got = classify_lines(_frame(rows), MAPPING, OrderConfirmations(line_classes=answers))

    assert got["line_class"].tolist() == expected
    assert got["line_class"].isin(CLEANED_LINE_CLASSES).all()
    assert got["line_class"].notna().all()


def test_the_closed_list_is_the_designs() -> None:
    assert set(CLEANED_LINE_CLASSES) == {
        "sale", "pooled_sale", "customer_return", "pooled_return", "allowance", "pooled_allowance",
        "discount", "charge", "no_money", "pooled_no_money", "gift_card_sale", "gift_card_redemption",
        "cost", "adjustment", "stock_in", "unclassified", "unmeasurable"}


def test_no_transaction_type_column_reads_nothing_as_in() -> None:
    mapping = {k: v for k, v in MAPPING.items() if v != "transaction_type"}
    got = classify_lines(_frame([{"Sku": "A1", "Type": "in"}]), mapping, OrderConfirmations())
    assert got["line_class"].tolist() == ["sale"]


# --- class_source ---------------------------------------------------------------------

def test_the_class_source_says_whether_an_answer_decided_it() -> None:
    rows = [{"Sku": "POST", "Qty": "1", "Price": "3"},            # answered charge
            {"Sku": "M", "Qty": "1", "Price": "3"},               # answered pooled
            {"Sku": "A1", "Qty": "1", "Price": "3"},              # unanswered product
            {"Sku": None, "Name": None, "Qty": "1", "Price": "3"},  # the gap, pooled by rule
            {"Sku": "POST", "Qty": "1", "Price": "3", "Type": "in"},  # "in" comes first
            {"Sku": "POST", "Qty": None, "Price": "3"}]           # unmeasurable comes first
    got = classify_lines(_frame(rows), MAPPING, _answers(POST="charge", M="pooled"))
    assert got["class_source"].tolist() == ["user", "user", "rule", "rule", "rule", "rule"]


# --- suggestions ------------------------------------------------------------------------

def _suggested(rows: list[dict], answers: OrderConfirmations | None = None) -> list:
    got = classify_lines(_frame(rows), MAPPING, answers or OrderConfirmations())["suggested_class"]
    return [None if pd.isna(v) else v for v in got]


def test_an_unanswered_candidate_key_carries_its_suggestion_on_every_line() -> None:
    rows = [{"Sku": "DOT", "Name": "DOTCOM POSTAGE", "Qty": "1", "Price": "9"},
            {"Sku": "DOT", "Name": "DOTCOM POSTAGE", "Qty": "1", "Price": "0"},
            {"Sku": "85123A", "Name": "WHITE HANGING HEART", "Qty": "2", "Price": "2.55"}]
    assert _suggested(rows) == ["charge", "charge", None]


def test_an_answered_key_carries_no_suggestion() -> None:
    rows = [{"Sku": "DOT", "Name": "DOTCOM POSTAGE", "Qty": "1", "Price": "9"},
            {"Sku": "M", "Name": "Manual", "Qty": "1", "Price": "9"}]
    answers = OrderConfirmations(line_classes=[
        LineClassAnswer(value="DOT", field="sku", line_class="charge"),
        LineClassAnswer(value="M", field="sku", line_class="product")])
    assert _suggested(rows, answers) == [None, None]


def test_a_key_that_moves_no_money_is_no_candidate_and_carries_none() -> None:
    # 23595 "re-adjustment" on Online Retail II: 5 @ 0 and -5 @ 0 (review 5 #5).
    rows = [{"Sku": "23595", "Name": "re-adjustment", "Qty": "5", "Price": "0"},
            {"Sku": "23595", "Name": "re-adjustment", "Qty": "-5", "Price": "0"}]
    assert _suggested(rows) == [None, None]


@pytest.mark.parametrize(("sku", "name", "suggested"), [
    ("gift_0001_10", "Dotcomgiftshop Gift Voucher £10.00", "gift_card"),
    ("G1", "Gift card 25", "gift_card"),
    ("G2", "Birthday gift voucher", "gift_card"),
    ("G3", "Gift certificate", "gift_card"),
    ("G4", "Discount voucher", "discount"),   # the discount words come first (review 5 #12)
    ("G5", "Promo voucher", None),            # no bare "voucher"
    ("G6", "GIFT BAG BIRTHDAY", None),        # "gift" alone is a product
])
def test_the_gift_card_words(sku: str, name: str, suggested: str | None) -> None:
    assert _suggested([{"Sku": sku, "Name": name, "Qty": "1", "Price": "10"}]) == [suggested]


def test_a_name_only_line_inherits_its_one_skus_suggestion() -> None:
    # "Handling X" is sold only under the SKU POSTAGE, a candidate; a line with
    # the name and no SKU takes the SKU's suggestion, as it would its class.
    rows = [{"Sku": "POSTAGE", "Name": "Handling X", "Qty": "1", "Price": "4"},
            {"Sku": None, "Name": "Handling X", "Qty": "-1", "Price": "4"}]
    assert _suggested(rows) == ["charge", "charge"]
    classed = classify_lines(_frame(rows), MAPPING, _answers(POSTAGE="charge"))
    assert classed["line_class"].tolist() == ["charge", "charge"]
    assert classed["suggested_class"].isna().all()


def test_the_name_only_vote_reads_dated_sale_lines_only() -> None:
    # E7 (mutation check M14): the SKU's only sale has no date, so the name is
    # sold under no SKU and the name-only line stays a product.
    rows = [{"Sku": "POST", "Name": "Handling", "Qty": "1", "Price": "4", "Day": "not a date"},
            {"Sku": None, "Name": "Handling", "Qty": "-1", "Price": "4"}]
    assert _classes(rows, _answers(POST="charge")) == ["charge", "customer_return"]


def test_a_line_typed_in_does_not_make_its_key_a_candidate() -> None:
    # Candidates are measured on the lines of a counted type, as stage 1's list.
    rows = [{"Sku": "DOT", "Name": "DOTCOM POSTAGE", "Qty": "1", "Price": "9", "Type": "in"}]
    assert _suggested(rows) == [None]


def test_no_product_column_means_no_suggestion() -> None:
    mapping = {k: v for k, v in MAPPING.items() if v not in ("sku", "product_name")}
    got = classify_lines(_frame([{"Qty": "1", "Price": "3"}]), mapping, OrderConfirmations())
    assert got["line_class"].tolist() == ["pooled_sale"]
    assert got["suggested_class"].isna().all()


def test_the_result_keeps_the_frames_index() -> None:
    df = _frame([{"Sku": "A1"}, {"Sku": "B2"}]).set_axis([7, 3])
    assert classify_lines(df, MAPPING, OrderConfirmations()).index.tolist() == [7, 3]
