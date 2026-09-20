"""Shared builders for the schema inference tests."""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from contracts import SchemaInferenceContract
from shared.ai_client import AIClient, RetryBudget
from shared.run_registry import create_run
from stages.ingest.ai_schema import infer_schema_run
from stages.ingest.profiling import profile_run
from tests.ai_fakes import FakeMessages, FakeResponse

NOW = datetime(2026, 9, 19, 12, 0, tzinfo=UTC)
# 4 data rows; row 3 repeats row 1, row 2 has a negative qty, row 4 has gaps.
CSV = b"sku,name,qty,price\nA1,Mug,3,9.99\nB2,Cup,-1,12.50\nA1,Mug,3,9.99\nC3,,5,\n"
COLUMNS = ["sku", "name", "qty", "price"]
CANONICAL = {"sku": "sku", "name": "product_name", "qty": "quantity", "price": "unit_price"}


def profiled_run(runs_root: Path, content: bytes = CSV) -> str:
    run = create_run(runs_root)
    (run.path / "raw.csv").write_bytes(content)
    profile_run(runs_root, run.run_id, now=NOW)
    return run.run_id


def column(name: str, canonical: str = "ignore", **overrides: Any) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "source_name": name, "semantic_type": "text", "canonical_field": canonical,
        "confidence": 0.9, "issues": [],
    }
    entry.update(overrides)
    return entry


def answer(columns: list[dict[str, Any]], **overrides: Any) -> FakeResponse:
    body: dict[str, Any] = {
        "domain_confidence": 0.93,
        "domain_reasoning": "columns resemble product / quantity / price",
        "dataset_issues": [{"code": "duplicate_rows", "count": 1, "severity": "low",
                            "detail": "row 3 repeats row 1"}],
        "columns": columns,
    }
    body.update(overrides)
    return FakeResponse(json.dumps(body), model="claude-served")


def good_answer() -> FakeResponse:
    return answer([column(n, CANONICAL[n]) for n in COLUMNS])


def run(runs_root: Path, run_id: str, messages: FakeMessages,
        budget: RetryBudget | None = None) -> SchemaInferenceContract:
    return infer_schema_run(runs_root, run_id, AIClient(messages), model="test-model",
                            retry_budget=budget or RetryBudget(), now=NOW)


def written(runs_root: Path, run_id: str) -> Path:
    return runs_root / run_id / "schema_inference.json"
