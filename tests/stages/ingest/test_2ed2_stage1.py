"""Session 2E-d2 (Thach), stage 1, written before the change.

Postage, fees, commissions, bank charges, discounts and accounting
adjustments are not products, yet a POS export books them as product lines
(Online Retail II: DOTCOM POSTAGE was the top "product" of 2011-11). Stage 1
PROPOSES which lines they may be - pandas, on the raw file, never the AI - and
the user confirms the class of each in Review (Thach, 2026-09-26):
- a charge paid by the customer (postage) stays in revenue, leaves the product
  tables;
- a fee or cost (bank charges, marketplace fees, commissions) leaves revenue;
- an accounting adjustment (bad debt, manual adjustments) leaves revenue and
  the product tables and is reported as a reconciling amount;
- a discount (2E-c: a deduction) stays in revenue, is no sale and no return.
A key is asked about when its SKU text or its commonest name has a class word
as its first or last word; "carriage" inside a name was 4 real products of
Online Retail II (FRENCH CARRIAGE LANTERN, BAROQUE CARRIAGE CLOCK).
"""

from pathlib import Path

import pandas as pd
import pytest

from contracts.cleaning import CleaningPlanContract, LineClassAnswer, OrderConfirmations
from contracts.profile import NonProductCandidate, SchemaInferenceContract
from stages.ingest import ai_plan, ai_schema, cleaning
from stages.ingest.non_product_lines import non_product_candidates
from tests.ai_fakes import FakeMessages
from tests.stages.ingest.cleaning_fixtures import NOW
from tests.stages.ingest.schema_answers import answer, column, profiled_run, run

MAPPING = {"Day": "transaction_date", "Qty": "quantity", "Price": "unit_price", "Sku": "sku",
           "Name": "product_name"}


def _lines(rows: list[tuple[str | None, str | None, str, str]]) -> pd.DataFrame:
    """(sku, name, quantity, price) per line, all on one day."""
    return pd.DataFrame({"Day": "2026-08-03", "Sku": [r[0] for r in rows], "Name": [r[1] for r in rows],
                         "Qty": [r[2] for r in rows], "Price": [r[3] for r in rows]})


def _found(df: pd.DataFrame, mapping: dict[str, str] = MAPPING) -> list[tuple]:
    return [(c.value, c.field, c.suggested) for c in non_product_candidates(df, mapping)]


@pytest.mark.parametrize(("name", "suggested"), [
    ("POSTAGE", "charge"), ("DOTCOM POSTAGE", "charge"), ("Next Day Carriage", "charge"),
    ("Shipping", "charge"), ("Delivery charge", "charge"), ("Phí vận chuyển", "charge"),
    ("AMAZON FEE", "cost"), ("Bank Charges", "cost"), ("CRUK Commission", "cost"),
    ("Adjust bad debt", "adjustment"), ("Manual", "adjustment"),
    ("Adjustment by john on 26/01/2010 16", "adjustment"), ("Write-off", "adjustment"),
    ("Discount", "discount"), ("Giảm giá", "discount"), ("SAMPLES", None),
    # Mutation checks N16 and N21: a charge before a fee in the class order,
    # and a plural at the start of a name.
    ("Shipping fee", "charge"), ("Bank charges Q3", "cost"),
])
def test_each_class_word_suggests_its_class(name: str, suggested: str | None) -> None:
    df = _lines([("X1", name, "1", "5"), ("85123A", "WHITE HANGING HEART", "2", "2.55")])

    assert _found(df) == [("X1", "sku", suggested)]


@pytest.mark.parametrize("name", ["FRENCH CARRIAGE LANTERN", "BLACK BAROQUE CARRIAGE CLOCK",
                                  "COFFEE MUG", "MONEY BANK", "POSTCARD SET", "ADJUSTABLE LAMP",
                                  # review F7: roses, not a commission
                                  "Hoa hồng đỏ", "Bó hoa hồng"])
def test_a_class_word_inside_a_product_name_is_not_asked(name: str) -> None:
    assert _found(_lines([("X1", name, "1", "5")])) == []


def test_the_sku_text_alone_can_carry_the_word() -> None:
    # No name column: the SKU "BANK CHARGES" is itself the text read.
    no_name = {k: v for k, v in MAPPING.items() if v != "product_name"}

    assert _found(_lines([("BANK CHARGES", None, "1", "-15")]), no_name) == [("BANK CHARGES", "sku", "cost")]


def test_a_line_without_a_sku_is_keyed_by_its_name() -> None:
    df = _lines([(None, "POSTAGE", "1", "18"), ("POST", "POSTAGE", "1", "18")])

    assert sorted(_found(df)) == [("POST", "sku", "charge"), ("POSTAGE", "product_name", "charge")]


def test_the_commonest_name_decides_not_a_stock_note() -> None:
    # SKU 23595 is a product whose one stock note reads "adjustment".
    df = _lines([("23595", "RED MUG", "1", "3"), ("23595", "RED MUG", "1", "3"), ("23595", "adjustment", "-1", "3")])

    assert _found(df) == []


def test_a_key_that_moves_no_money_is_not_asked() -> None:
    # Classed or not, zero-amount lines change no figure.
    assert _found(_lines([("23595", "adjustment", "5", "0"), ("23595", "adjustment", "-5", "0")])) == []


def test_the_candidate_carries_its_lines_and_money_split() -> None:
    """M on Online Retail II mixes both signs: 862 positive lines against
    564 negative; the user must see both, not only the net."""
    df = _lines([("M", "Manual", "1", "120"), ("M", "Manual", "1", "30.5"), ("M", "Manual", "-1", "200"),
                 ("M", "manual ", "1", "-10")])

    [found] = non_product_candidates(df, MAPPING)

    assert found == NonProductCandidate(value="M", field="sku", name="Manual", lines=4, positive=150.5,
                                        negative=-210.0, suggested="adjustment", word="manual")


def test_stock_in_lines_are_not_counted() -> None:
    df = _lines([("POST", "POSTAGE", "1", "18"), ("POST", "POSTAGE", "5", "18")]).assign(Type=["out", "in"])

    [found] = non_product_candidates(df, {**MAPPING, "Type": "transaction_type"})

    assert (found.lines, found.positive) == (1, 18.0)


def test_the_value_is_the_commonest_spelling() -> None:
    df = _lines([("post", "POSTAGE", "1", "18"), ("POST", "POSTAGE", "1", "18"), ("POST", "POSTAGE", "1", "18")])

    assert _found(df) == [("POST", "sku", "charge")]


def test_commonest_lines_first() -> None:
    df = _lines([("B", "Adjust bad debt", "1", "-900")] + [("POST", "POSTAGE", "1", "18")] * 3)

    assert [c.value for c in non_product_candidates(df, MAPPING)] == ["POST", "B"]


def test_no_product_column_measures_none() -> None:
    no_product = {k: v for k, v in MAPPING.items() if v not in ("sku", "product_name")}

    assert non_product_candidates(_lines([("POST", "POSTAGE", "1", "18")]), no_product) == []


def test_unmapped_price_is_not_measured() -> None:
    no_price = {k: v for k, v in MAPPING.items() if v != "unit_price"}

    assert non_product_candidates(_lines([("POST", "POSTAGE", "1", "18")]), no_price) is None


def test_a_file_of_stock_in_lines_only_is_not_measured() -> None:
    # Mutation check N18: nothing counts before the plan's cleaning.
    df = _lines([("POST", "POSTAGE", "5", "18")]).assign(Type="in")

    assert non_product_candidates(df, {**MAPPING, "Type": "transaction_type"}) is None


def test_the_schema_step_writes_the_candidates(tmp_path: Path) -> None:
    csv = b"Day,Qty,Price,Sku,Name\n2026-08-03,1,18,POST,POSTAGE\n2026-08-03,2,2.55,85123A,HEART\n"
    run_id = profiled_run(tmp_path, csv)

    schema = run(tmp_path, run_id, FakeMessages(answer(
        [column(n, MAPPING[n]) for n in MAPPING], dataset_issues=[])))

    assert [(c.value, c.suggested) for c in schema.non_product_candidates] == [("POST", "charge")]


def test_contracts_carry_the_line_classes_and_are_2_3() -> None:
    answered = OrderConfirmations(line_classes=[LineClassAnswer(value="POST", field="sku", line_class="charge")])
    plan = CleaningPlanContract(schema_version="2.3", generated_at=NOW, source="manual",
                                dataset_actions=[], column_actions=[], confirmations=answered)

    assert CleaningPlanContract.model_validate_json(plan.model_dump_json()).confirmations == answered
    assert OrderConfirmations().line_classes == []
    assert SchemaInferenceContract.model_fields["non_product_candidates"].default is None
    assert (ai_schema.SCHEMA_VERSION, ai_plan.SCHEMA_VERSION, cleaning.SCHEMA_VERSION) == ("2.3", "2.3", "2.3")


@pytest.mark.parametrize("line_class", ["product", "refund", ""])
def test_only_the_four_classes_are_answers(line_class: str) -> None:
    with pytest.raises(ValueError):
        LineClassAnswer(value="POST", field="sku", line_class=line_class)  # type: ignore[arg-type]
