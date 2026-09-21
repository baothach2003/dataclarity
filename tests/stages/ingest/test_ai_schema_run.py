import json
from pathlib import Path
from typing import Any

import anthropic
import httpx2
import pytest

from contracts import SchemaInferenceContract
from shared.ai_client import AIClient, AIUnavailable, RetryBudget
from shared.run_registry import create_run
from stages.ingest.ai_input import build_prompt_variables
from stages.ingest.ai_schema import (
    infer_schema_run,
)
from stages.ingest.profiling import profile_csv, read_csv_text
from tests.ai_fakes import FakeMessages, FakeResponse
from tests.stages.ingest.schema_answers import (
    CANONICAL,
    COLUMNS,
    CSV,
    NOW,
    answer,
    column,
    good_answer,
    profiled_run,
    run,
    written,
)


# --- happy path ------------------------------------------------------------------


def test_writes_a_valid_contract_with_our_header_fields(tmp_path: Path) -> None:
    run_id = profiled_run(tmp_path)

    returned = run(tmp_path, run_id, FakeMessages(good_answer()))

    on_disk = SchemaInferenceContract.model_validate_json(
        written(tmp_path, run_id).read_text(encoding="utf-8"))
    assert on_disk == returned
    assert returned.schema_version == "1.0"
    assert returned.generated_at == NOW
    assert returned.model_used == "claude-served"  # the model that answered
    assert returned.columns[1].canonical_field == "product_name"


def test_columns_follow_the_file_order_whatever_order_the_ai_used(tmp_path: Path) -> None:
    run_id = profiled_run(tmp_path)
    shuffled = answer([column(n, CANONICAL[n]) for n in reversed(COLUMNS)])

    returned = run(tmp_path, run_id, FakeMessages(shuffled))

    assert [c.source_name for c in returned.columns] == COLUMNS


def test_the_real_template_is_rendered_completely(tmp_path: Path) -> None:
    run_id = profiled_run(tmp_path)
    messages = FakeMessages(good_answer())

    run(tmp_path, run_id, messages)

    prompt = messages.calls[0]["messages"][0]["content"]
    assert "{profile_json}" not in prompt and "{sample_rows}" not in prompt
    assert '"name": "qty"' in prompt       # the profile
    assert '"row": 2' in prompt            # a sample row
    assert messages.calls[0]["max_tokens"] == 3000


# --- the bounded input (AI_PIPELINE section 1) -----------------------------------------


def test_input_is_bounded_to_25_columns_and_30_rows() -> None:
    header = ",".join(f"c{i}" for i in range(75))
    body = "\n".join(",".join(str(r) for _ in range(75)) for r in range(100))
    raw = f"{header}\n{body}\n".encode()
    profile = profile_csv(raw, now=NOW)

    variables = build_prompt_variables(profile, read_csv_text(raw).frame)

    sent_profile = json.loads(variables["profile_json"])
    sent_rows = json.loads(variables["sample_rows"])
    # 25, not 60: an answer for more columns does not fit in 3000 tokens.
    assert len(sent_profile["columns"]) == 25
    assert "schema_version" not in sent_profile  # header fields are noise for the AI
    assert sent_rows["columns"] == [f"c{i}" for i in range(25)]
    assert len(sent_rows["rows"]) == 30
    assert all(len(r["values"]) == 25 for r in sent_rows["rows"])


def test_columns_beyond_25_are_marked_not_inferred(tmp_path: Path) -> None:
    header = ",".join(f"c{i}" for i in range(26))
    raw = f"{header}\n{','.join('1' for _ in range(26))}\n".encode()
    run_id = profiled_run(tmp_path, raw)
    first_25 = answer([column(f"c{i}") for i in range(25)], dataset_issues=[])

    returned = run(tmp_path, run_id, FakeMessages(first_25))

    last = returned.columns[25]
    assert len(returned.columns) == 26
    assert (last.source_name, last.semantic_type, last.canonical_field) == ("c25", "text", "ignore")
    assert last.confidence == 0.0  # below 0.7: the review screen flags it for the user


# --- answers that fail a stage check use the one retry ------------------------------------


@pytest.mark.parametrize(
    ("bad_columns", "message"),
    [
        ([column(n, CANONICAL[n]) for n in COLUMNS[:3]], "missing: ['price']"),
        ([column(n, CANONICAL[n]) for n in COLUMNS] + [column("ghost")], "unknown: ['ghost']"),
        ([column(n, CANONICAL[n]) for n in COLUMNS] + [column("qty")], "more than once: ['qty']"),
        ([column(n, "quantity" if n in {"qty", "price"} else CANONICAL[n]) for n in COLUMNS],
         "quantity"),
    ],
    ids=["missing-column", "unknown-column", "duplicate-column", "duplicate-canonical"],
)
def test_inconsistent_answer_is_retried_with_the_reason(
    tmp_path: Path, bad_columns: list[dict[str, Any]], message: str
) -> None:
    run_id = profiled_run(tmp_path)
    messages = FakeMessages(answer(bad_columns), good_answer())

    returned = run(tmp_path, run_id, messages)

    assert message in messages.calls[1]["messages"][0]["content"]
    assert [c.source_name for c in returned.columns] == COLUMNS


def test_an_issue_count_above_the_row_count_is_rejected(tmp_path: Path) -> None:
    # The file has 4 data rows; 142 missing values cannot be true.
    run_id = profiled_run(tmp_path)
    invented = [column(n, CANONICAL[n]) for n in COLUMNS]
    invented[1]["issues"] = [{"code": "missing_values", "count": 142, "pct": 3.1,
                              "examples": []}]
    messages = FakeMessages(answer(invented), good_answer())

    run(tmp_path, run_id, messages)

    assert "count 142 exceeds the 4 data rows" in messages.calls[1]["messages"][0]["content"]


def test_a_null_pct_is_accepted(tmp_path: Path) -> None:
    # Row 2 spells "mug" in lower case, so the case issue the AI reports is real
    # (pandas counts 1) and survives the recount; the rest is CSV as usual.
    run_id = profiled_run(
        tmp_path, b"sku,name,qty,price\nA1,Mug,3,9.99\nB2,mug,-1,12.50\nA1,Mug,3,9.99\nC3,,5,\n")
    columns = [column(n, CANONICAL[n]) for n in COLUMNS]
    columns[1]["issues"] = [{"code": "inconsistent_case", "count": 1, "pct": None,
                             "examples": ["row 2"]}]

    returned = run(tmp_path, run_id, FakeMessages(answer(columns)))

    assert returned.columns[1].issues[0].pct is None


# --- degraded mode: nothing is written -------------------------------------------------


def test_twice_invalid_raises_and_writes_nothing(tmp_path: Path) -> None:
    run_id = profiled_run(tmp_path)
    messages = FakeMessages(FakeResponse("sorry"), answer([column("sku", "sku")]))

    with pytest.raises(AIUnavailable) as caught:
        run(tmp_path, run_id, messages)

    assert caught.value.reason == "invalid_response"
    assert not written(tmp_path, run_id).exists()


def test_timeout_raises_writes_nothing_and_keeps_the_retry(tmp_path: Path) -> None:
    run_id = profiled_run(tmp_path)
    budget = RetryBudget()
    timeout = anthropic.APITimeoutError(
        request=httpx2.Request("POST", "https://api.anthropic.com/v1/messages"))

    with pytest.raises(AIUnavailable) as caught:
        run(tmp_path, run_id, FakeMessages(timeout), budget)

    assert caught.value.reason == "timeout"
    assert budget.remaining == 1
    assert not written(tmp_path, run_id).exists()


def test_missing_profile_is_a_clear_error_before_any_ai_call(tmp_path: Path) -> None:
    run = create_run(tmp_path)
    (run.path / "raw.csv").write_bytes(CSV)
    messages = FakeMessages()

    with pytest.raises(FileNotFoundError, match="profile.json"):
        infer_schema_run(tmp_path, run.run_id, AIClient(messages), model="m",
                         retry_budget=RetryBudget(), now=NOW)

    assert messages.calls == []
