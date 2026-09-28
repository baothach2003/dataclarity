"""Session 2E-t2 (Thach, 2026-09-28): stages 2 and 3 read each line's class -
written before the code. docs/LINE_TAXONOMY.md sections 3 and 5:

- one effects matrix (`shared/line_effects.py`) with a row for every class;
- `parse_transactions` reads cleaned.csv's `line_class` and `suggested_class`
  (a value outside the closed list is refused), and classifies a frame that
  has no stage 1 columns by the same function;
- THE SAME LINES: on a file with no amount too large to add and no confirmed
  gift card, every set of lines today's readers use is the set the sign rules
  gave before 2E-t2 - checked here against those rules, written out again.
"""

import io
import itertools

import numpy as np
import pandas as pd
import pytest

from contracts.cleaning import CLEANED_LINE_CLASSES, TAXONOMY_COLUMNS, LineClassAnswer, OrderConfirmations
from shared.date_evidence import answered_order
from shared.dates import as_dates
from shared.line_classes import line_classes
from shared.line_effects import EFFECTS
from shared.line_numbers import line_numbers
from shared.line_taxonomy import classify_lines
from shared.transactions import parse_transactions

MAPPING = {"Day": "transaction_date", "Qty": "quantity", "Price": "unit_price", "Sku": "sku",
           "Name": "product_name", "Type": "transaction_type"}


# --- the matrix --------------------------------------------------------------------------

def test_every_class_has_its_effects() -> None:
    assert set(EFFECTS) == set(CLEANED_LINE_CLASSES)


def test_every_class_counted_nowhere_is_reported_somewhere() -> None:
    # Review 3 #9: a new class written `Effect(False, None)` would have been
    # in no report of metrics.json.
    from shared.line_effects import OUTSIDE_REVENUE, Effect
    from stages.analyze.metrics_lines import _OUTSIDE_ORDER

    uncounted = {c for c, e in EFFECTS.items() if not e.counted}
    assert uncounted == OUTSIDE_REVENUE | {"unclassified", "unmeasurable"}
    assert set(_OUTSIDE_ORDER) == OUTSIDE_REVENUE
    with pytest.raises(ValueError, match="reported somewhere"):
        Effect(False, None)
    with pytest.raises(ValueError, match="reported somewhere"):
        Effect(True, "gross_sales", "outside_revenue")


@pytest.mark.parametrize(("line_class", "term", "counted"), [
    ("sale", "gross_sales", True), ("pooled_sale", "gross_sales", True),
    ("customer_return", "returns", True), ("pooled_return", "returns", True),
    ("allowance", "other_deductions", True), ("pooled_allowance", "other_deductions", True),
    ("discount", "discounts", True), ("charge", "other_revenue", True),
    ("no_money", None, True), ("pooled_no_money", None, True),
    ("gift_card_sale", None, False), ("gift_card_redemption", None, False), ("cost", None, False),
    ("adjustment", None, False), ("stock_in", None, False), ("unclassified", None, False),
    ("unmeasurable", None, False),
])
def test_each_class_is_in_one_term_of_the_identity(line_class: str, term: str | None, counted: bool) -> None:
    assert (EFFECTS[line_class].term, EFFECTS[line_class].counted) == (term, counted)


def test_the_item_is_the_users_answer_on_every_line_of_its_key() -> None:
    # Review 2 #1: read from the class, a charge's "in" line and its unpriced
    # line lost the item and became a product. A line with neither SKU nor
    # name is pooled by rule, no answer: no item.
    rows = [{"Sku": "POST", "Qty": "1", "Price": "5"}, {"Sku": "POST", "Qty": "1", "Price": "5", "Type": "in"},
            {"Sku": "POST", "Qty": "1", "Price": None}, {"Sku": "M", "Qty": "-1", "Price": "5", "Type": "in"},
            {"Sku": "G", "Qty": "-1", "Price": "20"}, {"Sku": "A1", "Qty": "1", "Price": "5"},
            {"Qty": "1", "Price": "5"}]
    answers = OrderConfirmations(line_classes=[
        LineClassAnswer(value="POST", field="sku", line_class="charge"),
        LineClassAnswer(value="M", field="sku", line_class="pooled"),
        LineClassAnswer(value="G", field="sku", line_class="gift_card")])
    parsed = parse_transactions(_frame(rows), MAPPING, answers)
    assert parsed.classes.tolist() == ["charge", "stock_in", "unmeasurable", "stock_in", "gift_card_redemption",
                                       "sale", "pooled_sale"]
    assert [None if pd.isna(v) else v for v in parsed.line_class] == [
        "charge", "charge", "charge", "pooled", "gift_card", None, None]


# --- reading the columns --------------------------------------------------------------------

def _frame(rows: list[dict]) -> pd.DataFrame:
    columns = ["Day", "Sku", "Name", "Qty", "Price", "Type"]
    defaults = {"Day": "2026-08-03", "Sku": None, "Name": None, "Qty": "1", "Price": "10", "Type": None}
    return pd.DataFrame([{c: row.get(c, defaults[c]) for c in columns} for row in rows], dtype=object)


def test_stage_1s_class_is_read_not_recomputed() -> None:
    # A line whose signs make it a sale, written by stage 1 as a discount: the
    # stages read the discount.
    df = _frame([{"Sku": "A1", "Qty": "2", "Price": "5"}]).assign(
        line_class="discount", class_source="user", suggested_class=np.nan)
    parsed = parse_transactions(df, MAPPING, None)
    assert (bool(parsed.sale.iloc[0]), bool(parsed.deduction.iloc[0])) == (False, True)
    assert parsed.classes.tolist() == ["discount"]


def test_a_class_outside_the_closed_list_is_refused() -> None:
    df = _frame([{"Sku": "A1"}]).assign(line_class="refund", class_source="rule", suggested_class=np.nan)
    with pytest.raises(ValueError, match="closed list"):
        parse_transactions(df, MAPPING, None)


def test_a_frame_without_stage_1s_columns_is_classed_by_the_same_function() -> None:
    rows = [{"Sku": "A1", "Qty": "2", "Price": "5"}, {"Sku": "POST", "Name": "POSTAGE", "Qty": "1", "Price": "9"},
            {"Sku": "DOT", "Name": "DOTCOM POSTAGE", "Qty": "1", "Price": "9"},
            {"Sku": "A1", "Qty": "-1", "Price": "5"}, {"Sku": "A1", "Qty": "3", "Price": "0"}]
    answers = OrderConfirmations(line_classes=[LineClassAnswer(value="POST", field="sku", line_class="charge")])
    df = _frame(rows)
    written = df.join(classify_lines(df, MAPPING, answers))

    fallback, read = parse_transactions(df, MAPPING, answers), parse_transactions(written, MAPPING, answers)

    for name in ("classes", "class_source", "suggested", "counted", "sale", "returned", "charge", "deduction",
                 "left_out", "units", "line_class"):
        assert getattr(fallback, name).equals(getattr(read, name)), name
    assert [None if pd.isna(v) else v for v in read.suggested] == [None, None, "charge", None, None]


# --- the same lines ---------------------------------------------------------------------------

def _before(df: pd.DataFrame, mapping: dict[str, str], answers: OrderConfirmations) -> dict[str, pd.Series]:
    """The sets as parse_transactions built them before 2E-t2, from the signs."""
    reverse = {f: s for s, f in mapping.items()}
    q, p, counts = line_numbers(df, reverse, reverse["quantity"], reverse["unit_price"])
    dates = as_dates(df[reverse["transaction_date"]], offsets="wall_clock",
                     order=answered_order(answers.dates_day_first))
    valid = dates.notna() & np.isfinite(q) & np.isfinite(p)
    amounts = q * p
    lc = line_classes(df, reverse, answers.line_classes, valid & counts & (q > 0) & (amounts > 0))
    left_out = valid & counts & lc.isin(("cost", "adjustment", "gift_card"))
    counted = valid & counts & ~left_out
    charge = counted & lc.eq("charge")
    priced = counted & ~lc.isin(("discount", "charge"))
    sale = priced & (q > 0) & (amounts > 0)
    returned = priced & (q < 0) & (amounts < 0)
    return {"counted": counted, "sale": sale, "returned": returned, "charge": charge,
            "deduction": counted & ~sale & ~returned & ~charge, "left_out": left_out,
            "units": q.where(sale | returned, 0.0), "line_class": lc, "not_filled": ~counts | left_out}


def test_every_set_is_the_one_the_sign_rules_gave() -> None:
    # WIDGET is sold under S1 (unanswered), GADGET under S2 (answered a
    # charge): a line carrying only such a name takes its SKU's item through
    # the name-only vote (review 1 #11 - no name-only line was compared).
    rows = [{"Sku": "S1", "Name": "WIDGET", "Qty": "1", "Price": "5"},
            {"Sku": "S2", "Name": "GADGET", "Qty": "1", "Price": "5"}]
    answers = [LineClassAnswer(value="S2", field="sku", line_class="charge")]
    items = [None, "product", "pooled", "charge", "discount", "cost", "adjustment", "gap", "WIDGET", "GADGET"]
    shapes = itertools.product(["out", "in", None], ["3", "-3", "0", None, "inf"], ["2.5", "-2.5", "0", None],
                               items, ["2026-08-03", None])
    for n, (kind, qty, price, item, day) in enumerate(shapes):
        sku = None if item in ("gap", "WIDGET", "GADGET") else f"K{n}"
        if item not in (None, "gap", "WIDGET", "GADGET"):
            answers.append(LineClassAnswer(value=sku, field="sku", line_class=item))
        rows.append({"Sku": sku, "Name": item if item in ("WIDGET", "GADGET") else None, "Qty": qty,
                     "Price": price, "Type": kind, "Day": day})
    df, conf = _frame(rows), OrderConfirmations(line_classes=answers)

    parsed, before = parse_transactions(df, MAPPING, conf), _before(df, MAPPING, conf)

    for name in ("counted", "sale", "returned", "charge", "deduction", "left_out"):
        assert parsed.__getattribute__(name).equals(before[name]), name
    assert np.allclose(parsed.units, before["units"])
    # The item on every line (review 2 #1).
    assert parsed.line_class.fillna("-").equals(before["line_class"].fillna("-"))
    # And the same through cleaned.csv's text, as stage 1 writes the classes
    # and stages 2 and 3 read them back (review 2 #9).
    text = io.StringIO()
    df.join(classify_lines(df, MAPPING, conf)).to_csv(text, index=False)
    text.seek(0)
    cleaned = pd.read_csv(text, dtype=str)
    assert set(TAXONOMY_COLUMNS) <= set(cleaned.columns)
    read = parse_transactions(cleaned, MAPPING, conf)
    for name in ("classes", "counted", "sale", "returned", "charge", "deduction", "left_out", "units"):
        assert getattr(read, name).equals(getattr(parsed, name)), name
    assert read.line_class.fillna("-").equals(parsed.line_class.fillna("-"))
    # The vote ran: a GADGET-only line is a charge, a WIDGET-only one a sale.
    name_only = df["Sku"].isna()
    assert parsed.charge[name_only & df["Name"].eq("GADGET")].any()
    assert parsed.sale[name_only & df["Name"].eq("WIDGET")].any()
    # The lines the receipt fill may not read (the parse hands order_basis
    # these): "in" rows and the left out.
    assert (parsed.classes.eq("stock_in") | parsed.left_out).equals(before["not_filled"])


def test_the_one_listed_change_an_amount_too_large_to_add_is_no_longer_counted() -> None:
    # docs/LINE_TAXONOMY.md section 6: counted before, its month's revenue
    # written as null; unmeasurable now.
    df = _frame([{"Sku": "A1", "Qty": "1e200", "Price": "1e200"}])
    parsed = parse_transactions(df, MAPPING, None)
    assert parsed.classes.tolist() == ["unmeasurable"]
    assert not parsed.counted.iloc[0]
    assert _before(df, MAPPING, OrderConfirmations())["counted"].iloc[0]


def test_a_frame_with_repeated_row_labels_is_classed_and_suggested() -> None:
    # A frame put together from others repeats its row labels; the candidate
    # search picked lines by label and broke (2E-t2).
    part = _frame([{"Sku": "DOT", "Name": "DOTCOM POSTAGE", "Qty": "1", "Price": "9"},
                   {"Sku": "A1", "Qty": "2", "Price": "5"}])
    df = pd.concat([part, part])
    got = classify_lines(df, MAPPING, OrderConfirmations())
    assert got["line_class"].tolist() == ["sale", "sale", "sale", "sale"]
    assert [None if pd.isna(v) else v for v in got["suggested_class"]] == ["charge", None, "charge", None]
