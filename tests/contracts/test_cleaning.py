from typing import Any, get_args

import pytest
from pydantic import ValidationError

from contracts.cleaning import (
    CleaningPlanContract,
    CleaningReportContract,
    TransformAction,
)


def plan_payload() -> dict[str, Any]:
    # The example from docs/CONTRACTS.md section 4, with `source` resolved to one
    # of its three documented values.
    return {
        "schema_version": "1.0",
        "generated_at": "2026-09-18T04:13:00Z",
        "source": "user_edited",
        "dataset_actions": [
            {
                "action": "remove_exact_duplicates",
                "params": {},
                "rationale": "12 exact duplicate rows found",
                "alternatives": ["flag_only"],
                "edited_by_user": False,
            }
        ],
        "column_actions": [
            {
                "source_name": "Unit Price",
                "semantic_type": "numeric_continuous",
                "canonical_field": "unit_price",
                "action": "impute_median",
                "params": {},
                "rationale": "4.2% missing; median robust given IQR outliers",
                "alternatives": ["impute_mean", "drop_rows_missing"],
                "edited_by_user": True,
            }
        ],
    }


def report_payload() -> dict[str, Any]:
    # The example from docs/CONTRACTS.md section 5.
    return {
        "schema_version": "1.0",
        "generated_at": "2026-09-18T04:14:00Z",
        "rows_in": 152430,
        "rows_out": 151988,
        "columns_in": 9,
        "columns_out": 8,
        "changes": [
            {
                "action": "impute_median",
                "column": "Unit Price",
                "cells_affected": 6402,
                "rows_affected": 0,
                "params": {},
                "detail": "filled with 8.5",
            },
            {
                "action": "drop_rows_missing",
                "column": "transaction_date",
                "cells_affected": 0,
                "rows_affected": 430,
                "params": {},
                "detail": "dropped rows with unparseable dates",
            },
        ],
        "warnings": [{"code": "encoding_fallback", "detail": "file decoded as latin-1"}],
        "column_mapping": {"Prod Name": "product_name", "Qty": "quantity"},
    }


# --- plan_proposed.json / plan_final.json ---------------------------------


def test_catalog_has_the_sixteen_documented_actions() -> None:
    # docs/AI_PIPELINE.md section 6 lists 16 actions.
    assert len(get_args(TransformAction)) == 16


def test_plan_accepts_documented_example() -> None:
    plan = CleaningPlanContract.model_validate(plan_payload())

    assert plan.source == "user_edited"
    assert plan.column_actions[0].alternatives == ["impute_mean", "drop_rows_missing"]
    assert plan.column_actions[0].edited_by_user is True


@pytest.mark.parametrize("source", ["ai", "user_edited", "manual"])
def test_plan_accepts_each_documented_source(source: str) -> None:
    payload = plan_payload()
    payload["source"] = source

    plan = CleaningPlanContract.model_validate(payload)

    assert plan.source == source


def test_plan_rejects_unknown_source() -> None:
    payload = plan_payload()
    payload["source"] = "imported"

    with pytest.raises(ValidationError, match="source"):
        CleaningPlanContract.model_validate(payload)


def test_plan_rejects_off_catalog_column_action() -> None:
    payload = plan_payload()
    payload["column_actions"][0]["action"] = "run_python"

    with pytest.raises(ValidationError, match="action"):
        CleaningPlanContract.model_validate(payload)


def test_plan_rejects_off_catalog_dataset_action() -> None:
    payload = plan_payload()
    payload["dataset_actions"][0]["action"] = "drop_table"

    with pytest.raises(ValidationError, match="action"):
        CleaningPlanContract.model_validate(payload)


def test_plan_rejects_off_catalog_alternative() -> None:
    payload = plan_payload()
    payload["column_actions"][0]["alternatives"] = ["impute_mean", "impute_ai_guess"]

    with pytest.raises(ValidationError, match="alternatives"):
        CleaningPlanContract.model_validate(payload)


def test_plan_rejects_missing_edited_by_user() -> None:
    payload = plan_payload()
    del payload["column_actions"][0]["edited_by_user"]

    with pytest.raises(ValidationError, match="edited_by_user"):
        CleaningPlanContract.model_validate(payload)


def test_plan_rejects_unknown_canonical_field() -> None:
    payload = plan_payload()
    payload["column_actions"][0]["canonical_field"] = "price"

    with pytest.raises(ValidationError, match="canonical_field"):
        CleaningPlanContract.model_validate(payload)


def test_plan_accepts_several_actions_on_one_column() -> None:
    # The fixed execution order (AI_PIPELINE.md section 6) runs e.g.
    # trim_whitespace then normalize_case on the same column.
    payload = plan_payload()
    trim = dict(payload["column_actions"][0], action="trim_whitespace", alternatives=[])
    case = dict(trim, action="normalize_case", params={"mode": "title"})
    payload["column_actions"] = [trim, case]

    plan = CleaningPlanContract.model_validate(payload)

    assert [a.action for a in plan.column_actions] == ["trim_whitespace", "normalize_case"]


def test_plan_accepts_empty_manual_plan() -> None:
    payload = plan_payload()
    payload.update({"source": "manual", "dataset_actions": [], "column_actions": []})

    plan = CleaningPlanContract.model_validate(payload)

    assert plan.column_actions == []


# --- cleaning_report.json -------------------------------------------------


def test_report_accepts_documented_example() -> None:
    report = CleaningReportContract.model_validate(report_payload())

    assert report.rows_in - report.rows_out == 442
    assert report.changes[1].rows_affected == 430
    assert report.column_mapping["Qty"] == "quantity"


def test_report_accepts_dataset_level_change_without_column() -> None:
    payload = report_payload()
    payload["changes"] = [
        {
            "action": "remove_exact_duplicates",
            "column": None,
            "cells_affected": 0,
            "rows_affected": 12,
            "params": {},
            "detail": "12 exact duplicate rows removed",
        }
    ]

    report = CleaningReportContract.model_validate(payload)

    assert report.changes[0].column is None


def test_report_rejects_off_catalog_change_action() -> None:
    payload = report_payload()
    payload["changes"][0]["action"] = "ai_rewrite"

    with pytest.raises(ValidationError, match="action"):
        CleaningReportContract.model_validate(payload)


def test_report_rejects_negative_rows_affected() -> None:
    payload = report_payload()
    payload["changes"][1]["rows_affected"] = -1

    with pytest.raises(ValidationError, match="rows_affected"):
        CleaningReportContract.model_validate(payload)


def test_report_rejects_mapping_to_unknown_canonical_field() -> None:
    payload = report_payload()
    payload["column_mapping"]["Qty"] = "amount"

    with pytest.raises(ValidationError, match="column_mapping"):
        CleaningReportContract.model_validate(payload)


def test_report_rejects_missing_rows_out() -> None:
    payload = report_payload()
    del payload["rows_out"]

    with pytest.raises(ValidationError, match="rows_out"):
        CleaningReportContract.model_validate(payload)


def test_report_accepts_run_with_no_changes() -> None:
    payload = report_payload()
    payload.update({"rows_out": 152430, "columns_out": 9, "changes": [], "warnings": []})

    report = CleaningReportContract.model_validate(payload)

    assert report.changes == []
