from typing import Any

import pytest
from pydantic import ValidationError

from contracts.profile import ProfileContract, SchemaInferenceContract


def profile_payload() -> dict[str, Any]:
    # The example from docs/CONTRACTS.md section 2, verbatim.
    return {
        "schema_version": "1.0",
        "generated_at": "2026-09-18T04:12:00Z",
        "dataset": {
            "rows": 152430,
            "columns": 9,
            "duplicate_rows": 12,
            "missing_cells_pct": 2.7,
            "encoding_used": "utf-8",
            "delimiter": ",",
        },
        "columns": [
            {
                "name": "Unit Price",
                "dtype": "float64",
                "null_count": 6402,
                "null_pct": 4.2,
                "unique_count": 812,
                "min": -3.5,
                "max": 4500.0,
                "mean": 12.84,
                "median": 8.5,
                "q1": 3.2,
                "q3": 18.9,
                "top_values": [{"value": "9.99", "count": 3201}],
                "sample_values": ["9.99", "12.50", None, "-3.50"],
            }
        ],
    }


def inference_payload() -> dict[str, Any]:
    # The example from docs/CONTRACTS.md section 3 ("..." replaced by a timestamp).
    return {
        "schema_version": "2.0",  # 2E-e: order_id widened the enum (major)
        "generated_at": "2026-09-18T04:12:05Z",
        "model_used": "claude-sonnet-5",
        "domain_confidence": 0.93,
        "domain_reasoning": "columns resemble product / date / quantity / price",
        "dataset_issues": [
            {
                "code": "duplicate_rows",
                "count": 12,
                "severity": "medium",
                "detail": "12 exact duplicate rows",
            }
        ],
        "columns": [
            {
                "source_name": "Prod Name",
                "semantic_type": "text",
                "canonical_field": "product_name",
                "confidence": 0.95,
                "issues": [
                    {
                        "code": "missing_values",
                        "count": 142,
                        "pct": 3.1,
                        "examples": ["row 88", "row 105"],
                    }
                ],
            }
        ],
    }


def inference_column(source_name: str, canonical_field: str) -> dict[str, Any]:
    return {
        "source_name": source_name,
        "semantic_type": "text",
        "canonical_field": canonical_field,
        "confidence": 0.8,
        "issues": [],
    }


# --- profile.json ---------------------------------------------------------


def test_profile_accepts_documented_example() -> None:
    profile = ProfileContract.model_validate(profile_payload())

    assert profile.dataset.rows == 152430
    assert profile.columns[0].median == 8.5
    assert profile.columns[0].sample_values[2] is None


def test_profile_accepts_null_numeric_stats_for_text_column() -> None:
    payload = profile_payload()
    column = payload["columns"][0]
    column.update(
        {"name": "Prod Name", "dtype": "object", "min": None, "max": None,
         "mean": None, "median": None, "q1": None, "q3": None}
    )

    profile = ProfileContract.model_validate(payload)

    assert profile.columns[0].mean is None


def test_profile_accepts_empty_dataset() -> None:
    payload = profile_payload()
    payload["dataset"].update({"rows": 0, "duplicate_rows": 0, "missing_cells_pct": 0.0})
    payload["columns"] = []

    profile = ProfileContract.model_validate(payload)

    assert profile.columns == []


def test_profile_rejects_missing_dataset_block() -> None:
    payload = profile_payload()
    del payload["dataset"]

    with pytest.raises(ValidationError, match="dataset"):
        ProfileContract.model_validate(payload)


def test_profile_rejects_more_than_ten_top_values() -> None:
    payload = profile_payload()
    payload["columns"][0]["top_values"] = [
        {"value": str(i), "count": 1} for i in range(11)
    ]

    with pytest.raises(ValidationError, match="top_values"):
        ProfileContract.model_validate(payload)


def test_profile_rejects_negative_null_count() -> None:
    payload = profile_payload()
    payload["columns"][0]["null_count"] = -1

    with pytest.raises(ValidationError, match="null_count"):
        ProfileContract.model_validate(payload)


def test_profile_rejects_null_pct_above_100() -> None:
    payload = profile_payload()
    payload["columns"][0]["null_pct"] = 100.1

    with pytest.raises(ValidationError, match="null_pct"):
        ProfileContract.model_validate(payload)


# --- schema_inference.json ------------------------------------------------


def test_inference_accepts_documented_example() -> None:
    inference = SchemaInferenceContract.model_validate(inference_payload())

    assert inference.columns[0].canonical_field == "product_name"
    assert inference.dataset_issues[0].severity == "medium"


def test_inference_rejects_unknown_semantic_type() -> None:
    payload = inference_payload()
    payload["columns"][0]["semantic_type"] = "currency"

    with pytest.raises(ValidationError, match="semantic_type"):
        SchemaInferenceContract.model_validate(payload)


def test_inference_rejects_unknown_canonical_field() -> None:
    payload = inference_payload()
    payload["columns"][0]["canonical_field"] = "price"

    with pytest.raises(ValidationError, match="canonical_field"):
        SchemaInferenceContract.model_validate(payload)


def test_inference_rejects_unknown_issue_code() -> None:
    payload = inference_payload()
    payload["dataset_issues"][0]["code"] = "bad_vibes"

    with pytest.raises(ValidationError, match="code"):
        SchemaInferenceContract.model_validate(payload)


def test_inference_rejects_unknown_severity() -> None:
    payload = inference_payload()
    payload["dataset_issues"][0]["severity"] = "critical"

    with pytest.raises(ValidationError, match="severity"):
        SchemaInferenceContract.model_validate(payload)


@pytest.mark.parametrize("confidence", [-0.01, 1.01])
def test_inference_rejects_column_confidence_outside_unit_interval(
    confidence: float,
) -> None:
    payload = inference_payload()
    payload["columns"][0]["confidence"] = confidence

    with pytest.raises(ValidationError, match="confidence"):
        SchemaInferenceContract.model_validate(payload)


@pytest.mark.parametrize("confidence", [0.0, 1.0])
def test_inference_accepts_confidence_at_bounds(confidence: float) -> None:
    payload = inference_payload()
    payload["domain_confidence"] = confidence

    inference = SchemaInferenceContract.model_validate(payload)

    assert inference.domain_confidence == confidence


def test_inference_rejects_missing_model_used() -> None:
    payload = inference_payload()
    del payload["model_used"]

    with pytest.raises(ValidationError, match="model_used"):
        SchemaInferenceContract.model_validate(payload)


def test_inference_rejects_two_columns_mapped_to_one_canonical_field() -> None:
    payload = inference_payload()
    payload["columns"] = [
        inference_column("Prod Name", "product_name"),
        inference_column("Item", "product_name"),
    ]

    with pytest.raises(ValidationError, match="product_name"):
        SchemaInferenceContract.model_validate(payload)


def test_inference_allows_several_ignored_columns() -> None:
    payload = inference_payload()
    payload["columns"] = [
        inference_column("Notes 1", "ignore"),
        inference_column("Notes 2", "ignore"),
    ]

    inference = SchemaInferenceContract.model_validate(payload)

    assert len(inference.columns) == 2


def test_inference_rejects_duplicate_source_name() -> None:
    payload = inference_payload()
    payload["columns"] = [
        inference_column("Qty", "quantity"),
        inference_column("Qty", "ignore"),
    ]

    with pytest.raises(ValidationError, match="Qty"):
        SchemaInferenceContract.model_validate(payload)


def test_inference_accepts_an_issue_without_a_percentage() -> None:
    # CONTRACTS section 3: pct is null when the profile has no figure for the
    # issue (e.g. inconsistent_case); the AI must not invent one.
    payload = inference_payload()
    payload["columns"][0]["issues"][0]["pct"] = None

    inference = SchemaInferenceContract.model_validate(payload)

    assert inference.columns[0].issues[0].pct is None


def test_inference_still_requires_the_pct_key() -> None:
    payload = inference_payload()
    del payload["columns"][0]["issues"][0]["pct"]

    with pytest.raises(ValidationError, match="pct"):
        SchemaInferenceContract.model_validate(payload)


def test_inference_still_rejects_a_pct_above_100() -> None:
    payload = inference_payload()
    payload["columns"][0]["issues"][0]["pct"] = 150.0

    with pytest.raises(ValidationError, match="pct"):
        SchemaInferenceContract.model_validate(payload)
