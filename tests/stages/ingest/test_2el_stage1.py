"""Session 2E-l (Thach, 2026-09-27), stage 1, written before the change.

M "Manual" on Online Retail II is not an adjustment - its positive lines on
invoices with products are manually priced sales, its negative lines on credit
notes refunds - but many unnamed items pooled under one code. A fifth class,
"pooled": sold, never ranked as a product. Stage 1 suggests it for "manual".
A closed enum widened, so stage 1's contracts go to 3.0 (CONTRACTS section
10: adding an enum value is always a major bump).
"""

import pandas as pd

from contracts.cleaning import CleaningPlanContract, CleaningReportContract, LineClassAnswer
from contracts.profile import SchemaInferenceContract
from stages.ingest import ai_plan, ai_schema, cleaning
from shared.line_words import non_product_candidates

MAPPING = {"Day": "transaction_date", "Qty": "quantity", "Price": "unit_price", "Sku": "sku", "Name": "product_name"}


def test_manual_suggests_pooled_items() -> None:
    df = pd.DataFrame({"Day": "2026-08-03", "Sku": ["M", "85123A"], "Name": ["Manual", "WHITE HEART"],
                       "Qty": "1", "Price": ["12", "2.55"]})

    assert [(c.value, c.suggested) for c in non_product_candidates(df, MAPPING)] == [("M", "pooled")]


def test_a_manual_adjustment_is_still_an_adjustment() -> None:
    df = pd.DataFrame({"Day": "2026-08-03", "Sku": ["ADJ"], "Name": ["Manual adjustment"], "Qty": "1",
                       "Price": ["-12"]})

    assert [c.suggested for c in non_product_candidates(df, MAPPING)] == ["adjustment"]


def test_pooled_is_an_answer() -> None:
    assert LineClassAnswer(value="M", field="sku", line_class="pooled").line_class == "pooled"


def test_stage_1_contracts_are_3_0() -> None:
    # 3.1 in 2E-j (optional fields: a minor bump); 4.0 since 2E-t1 ("gift_card").
    assert (ai_schema.SCHEMA_VERSION, ai_plan.SCHEMA_VERSION, cleaning.SCHEMA_VERSION) == ("4.2", "4.2", "4.2")
    assert (SchemaInferenceContract.supported_major, CleaningPlanContract.supported_major,
            CleaningReportContract.supported_major) == (4, 4, 4)
