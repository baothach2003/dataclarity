"""Shared builders for the cleaning-plan tests (stages/ingest/ai_plan.py)."""

import json
from pathlib import Path
from typing import Any

from contracts import CleaningPlanContract
from contracts.profile import (
    ColumnInference,
    ColumnIssue,
    DatasetIssue,
    SchemaInferenceContract,
)
from shared.ai_client import AIClient, RetryBudget
from stages.ingest.ai_plan import propose_plan_run
from stages.ingest.contract_files import write_contract
from tests.ai_fakes import FakeMessages, FakeResponse
from tests.stages.ingest.schema_answers import CSV, NOW, profiled_run


def schema_column(
    name: str,
    semantic_type: Any,
    canonical: Any = "ignore",
    issues: list[ColumnIssue] | None = None,
    confidence: float = 0.9,
) -> ColumnInference:
    return ColumnInference(
        source_name=name, semantic_type=semantic_type, canonical_field=canonical,
        confidence=confidence, issues=issues or [],
    )


def issue(code: Any, count: int, pct: float | None = None) -> ColumnIssue:
    return ColumnIssue(code=code, count=count, pct=pct, examples=["row 2"])


# schema_answers.CSV: 4 rows; qty has one negative, price one gap (25.0 %).
SCHEMA_COLUMNS = [
    schema_column("sku", "identifier", "sku"),
    schema_column("name", "text", "product_name"),
    schema_column("qty", "numeric_discrete", "quantity", [issue("negative_values", 1)]),
    schema_column("price", "numeric_continuous", "unit_price",
                  [issue("missing_values", 1, pct=25.0)]),
]
COLUMNS = [c.source_name for c in SCHEMA_COLUMNS]


def make_schema(
    columns: list[ColumnInference] | None = None,
    dataset_issues: list[DatasetIssue] | None = None,
) -> SchemaInferenceContract:
    return SchemaInferenceContract(
        schema_version="2.0", generated_at=NOW, model_used="claude-served",
        domain_confidence=0.93, domain_reasoning="looks like sales data",
        dataset_issues=dataset_issues or [], columns=columns or SCHEMA_COLUMNS,
    )


def planned_run(
    runs_root: Path,
    csv: bytes = CSV,
    schema: SchemaInferenceContract | None = None,
) -> str:
    """A run with raw.csv, profile.json and schema_inference.json on disk."""
    run_id = profiled_run(runs_root, csv)
    write_contract(runs_root / run_id / "schema_inference.json", schema or make_schema())
    return run_id


def action(
    name: str, action_name: str = "flag_only", **overrides: Any
) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "source_name": name, "action": action_name, "params": {},
        "rationale": "no figure needed", "alternatives": [],
    }
    entry.update(overrides)
    return entry


def dataset_action(action_name: str, **overrides: Any) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "action": action_name, "params": {}, "rationale": "1 exact duplicate row",
        "alternatives": [],
    }
    entry.update(overrides)
    return entry


def good_actions() -> list[dict[str, Any]]:
    return [
        action("sku", "trim_whitespace", rationale="ids may be padded"),
        action("name", "trim_whitespace", rationale="1 missing name"),
        action("qty", "fix_negative", params={"strategy": "flag"},
               rationale="1 negative value", alternatives=["drop_rows_missing"]),
        action("price", "impute_median", rationale="25.0% missing",
               alternatives=["impute_mean", "drop_rows_missing"]),
    ]


def plan_answer(
    column_actions: list[dict[str, Any]] | None = None,
    dataset_actions: list[dict[str, Any]] | None = None,
) -> FakeResponse:
    body = {
        "dataset_actions": dataset_actions if dataset_actions is not None
        else [dataset_action("remove_exact_duplicates")],
        "column_actions": column_actions if column_actions is not None else good_actions(),
    }
    return FakeResponse(json.dumps(body), model="claude-served")


def good_plan() -> FakeResponse:
    return plan_answer()


def run_plan(
    runs_root: Path, run_id: str, messages: FakeMessages, budget: RetryBudget | None = None
) -> CleaningPlanContract:
    return propose_plan_run(runs_root, run_id, AIClient(messages), model="test-model",
                            retry_budget=budget or RetryBudget(), now=NOW)


def written(runs_root: Path, run_id: str) -> Path:
    return runs_root / run_id / "plan_proposed.json"
