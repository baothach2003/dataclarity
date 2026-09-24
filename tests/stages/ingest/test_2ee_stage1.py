"""Session 2E-e, stage 1 (Thach), written before the change: the canonical
field `order_id` - the id shared by every line of one order, invoice, receipt
or transaction.

- The AI may map it; stage 1 then CHECKS the mapping deterministically: a
  real order's lines share one day and one customer, so a column where more
  than 10% of the ids span several days or customers is flagged on the Review
  screen. Measured gap: 0.0% for Invoice and Transaction ID, 74-100% for
  every other column of both real files.
- It is never imputed: filling blank ids with one value would merge every
  blank line into one giant order.
- With it mapped, the duplicate check's business key includes it: the same
  product at the same minute on two invoices is not a duplicate (7,316 such
  rows on Online Retail II).
- Widening the canonical enum is a major bump for every contract carrying it
  (CONTRACTS section 10, Thach): schema_inference, plan and cleaning_report
  go to 2.0.
"""

from typing import Any

import pandas as pd
import pytest
from pydantic import ValidationError

from contracts.cleaning import CleaningReportContract
from contracts.profile import ColumnInference, ColumnIssue
from stages.ingest.issue_counts import business_key_columns
from stages.ingest.issue_recount import recount_issues
from stages.ingest.transform_catalog import is_legal, legal_column_actions


def column_of(name: str, canonical: Any = "ignore", semantic: Any = "text") -> ColumnInference:
    return ColumnInference(source_name=name, semantic_type=semantic, canonical_field=canonical,
                           confidence=0.9, issues=[])


COLUMNS = [column_of("Day", "transaction_date", "datetime"), column_of("Qty", "quantity", "numeric_discrete"),
           column_of("Price", "unit_price", "numeric_continuous"), column_of("Cust", "customer"),
           column_of("Item", "sku"), column_of("Inv", "order_id", "identifier")]


def _frame(invoices: list[str], days: list[str]) -> pd.DataFrame:
    n = len(invoices)
    return pd.DataFrame({"Day": days, "Qty": ["1"] * n, "Price": ["10"] * n, "Cust": ["k"] * n,
                         "Item": [f"P{i}" for i in range(n)], "Inv": invoices}, dtype="str")


def test_a_real_order_id_raises_no_issue() -> None:
    frame = _frame(["A", "A", "B", "B"], ["2026-08-03", "2026-08-03", "2026-08-04", "2026-08-04"])

    columns, _, _ = recount_issues(COLUMNS, [], frame)

    inv = next(c for c in columns if c.source_name == "Inv")
    assert inv.issues == []


def test_a_column_whose_ids_span_days_is_flagged_as_not_an_order_id() -> None:
    """Both ids cover two days (100% > 10%): flagged, with the count of ids
    that do - a figure pandas computed, not the AI."""
    frame = _frame(["A", "A", "B", "B"], ["2026-08-03", "2026-08-04", "2026-08-03", "2026-08-05"])

    columns, _, _ = recount_issues(COLUMNS, [], frame)

    inv = next(c for c in columns if c.source_name == "Inv")
    assert [(i.code, i.count) for i in inv.issues] == [("order_id_not_one_order", 2)]


def test_an_order_id_is_never_imputed() -> None:
    """Text and categorical columns allow imputation by type (a customer
    column may be filled), so only the order_id rule refuses it here."""
    for action in ("impute_mode", "impute_constant"):
        assert not is_legal(action, "text", "order_id")
        assert not is_legal(action, "categorical_nominal", "order_id")
        assert is_legal(action, "text", "customer")
    assert is_legal("drop_rows_missing", "identifier", "order_id")


def test_the_business_key_includes_the_order_id() -> None:
    assert business_key_columns(COLUMNS) == ["Item", "Day", "Inv"]


def _report(version: str) -> dict:
    return {"schema_version": version, "generated_at": "2026-09-24T00:00:00Z", "rows_in": 1,
            "rows_out": 1, "columns_in": 1, "columns_out": 1, "changes": [], "warnings": [],
            "column_mapping": {"Inv": "order_id"}}


def test_the_stage_1_contracts_are_major_version_2() -> None:
    assert CleaningReportContract.model_validate(_report("2.0")).column_mapping == {"Inv": "order_id"}
    with pytest.raises(ValidationError, match="re-"):
        CleaningReportContract.model_validate(_report("1.0"))


def test_the_ai_cannot_raise_the_order_id_flag_itself() -> None:
    """The flag is stage 1's measurement (CLAUDE.md 3.2): an AI-reported copy on
    a real order id column is dropped, and no flag is added."""
    claimed = ColumnIssue(code="order_id_not_one_order", count=9, pct=None, examples=["row 1"])
    columns = [c.model_copy(update={"issues": [claimed]}) if c.source_name == "Inv" else c
               for c in COLUMNS]
    frame = _frame(["A", "A", "B", "B"], ["2026-08-03", "2026-08-03", "2026-08-04", "2026-08-04"])

    result, _, _ = recount_issues(columns, [], frame)

    assert next(c for c in result if c.source_name == "Inv").issues == []


# --- 2E-e doubt-review, written before the fixes -----------------------------------


def test_an_order_id_is_never_cast() -> None:
    """F3: cast_type(float) on an Online-Retail-shaped Invoice column blanked
    every "C..." cancellation id, each return line became its own order, and
    the return rate read 1.25 instead of 0.25. An id is text, whatever its
    digits look like."""
    for semantic in ("identifier", "text", "numeric_discrete"):
        assert not is_legal("cast_type", semantic, "order_id")
    assert is_legal("cast_type", "numeric_discrete", "quantity")


def test_no_flag_when_the_raw_file_shows_no_sale_line_to_judge() -> None:
    """F6: raw prices written "L10.00" (a currency sign) parse to nothing before
    cleaning, so there is no sale line to judge the ids on - the flag said
    "not an order id" with a count of 0. No evidence, no flag."""
    frame = _frame(["A", "A", "B", "B"], ["2026-08-03"] * 4)
    frame["Price"] = "L10.00"

    columns, _, _ = recount_issues(COLUMNS, [], frame)

    assert next(c for c in columns if c.source_name == "Inv").issues == []


def test_no_action_rewrites_an_order_id() -> None:
    """Cycle 2 F3: on a numeric-typed order_id, clip_outliers_iqr wrote
    "1334.5" into 28 walk-in receipt ids (same-day receipts merged: orders 210
    -> 203) and fix_negative would rewrite "-5". Only actions that keep ids
    as they are stay legal: dropping, flagging, trimming whitespace."""
    legal = {"drop_rows_missing", "drop_column", "flag_only", "trim_whitespace"}
    for semantic in ("identifier", "text", "numeric_discrete", "categorical_nominal"):
        assert set(legal_column_actions(semantic, "order_id")) <= legal, semantic
    assert not is_legal("clip_outliers_iqr", "numeric_discrete", "order_id")
    assert not is_legal("fix_negative", "numeric_discrete", "order_id")
