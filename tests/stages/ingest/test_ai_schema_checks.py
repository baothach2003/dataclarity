"""Fixes from the 1C doubt review: bounded size, known figures, names, re-runs."""

import json
from pathlib import Path
from typing import Any

import anthropic
import httpx2
import pytest

from shared.ai_client import AIClient, AIUnavailable, RetryBudget
from stages.ingest.ai_input import build_prompt_variables
from stages.ingest.ai_schema import (
    SchemaInferenceAnswer,
    check_answer,
    infer_schema_run,
)
from stages.ingest.contract_files import StaleInputError
from stages.ingest.profiling import profile_csv, read_csv_text
from tests.ai_fakes import FakeMessages
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


# --- doubt review fixes (1C) ---------------------------------------------------------


def test_long_values_are_cut_before_they_reach_the_ai() -> None:
    long_name = "x" * 500
    raw = f"sku,name\nA1,{long_name}\nB2,{long_name}\n".encode()
    profile = profile_csv(raw, now=NOW)

    variables = build_prompt_variables(profile, read_csv_text(raw).frame)

    # The mark counts toward the 100 characters, so nothing sent is longer.
    cut = "x" * 88 + "…[truncated]"
    sent_profile = json.loads(variables["profile_json"])
    name_profile = sent_profile["columns"][1]
    assert name_profile["top_values"][0]["value"] == cut
    assert name_profile["sample_values"] == [cut, cut]
    assert json.loads(variables["sample_rows"])["rows"][0]["values"][1] == cut
    assert long_name not in variables["profile_json"] + variables["sample_rows"]


def test_values_at_the_limit_are_sent_whole() -> None:
    raw = f"sku,name\nA1,{'y' * 100}\n".encode()
    profile = profile_csv(raw, now=NOW)

    variables = build_prompt_variables(profile, read_csv_text(raw).frame)

    assert json.loads(variables["sample_rows"])["rows"][0]["values"][1] == "y" * 100


# The CSV: "name" has 1 missing cell of 4 (null_pct 25.0), 1 duplicate row.
@pytest.mark.parametrize(
    ("issue", "message"),
    [
        ({"code": "missing_values", "count": 2, "pct": 25.0, "examples": []},
         "name: missing_values count 2, but the profile has 1"),
        ({"code": "missing_values", "count": 1, "pct": 40.0, "examples": []},
         "name: missing_values pct 40.0, but the profile has 25.0"),
        ({"code": "all_null_column", "count": 1, "pct": None, "examples": []},
         "name: all_null_column, but the profile counts 1 missing of 4 rows"),
    ],
    ids=["missing-count", "missing-pct", "all-null-count"],
)
def test_column_figures_the_profile_holds_are_checked(
    tmp_path: Path, issue: dict[str, Any], message: str
) -> None:
    run_id = profiled_run(tmp_path)
    columns = [column(n, CANONICAL[n]) for n in COLUMNS]
    columns[1]["issues"] = [issue]
    messages = FakeMessages(answer(columns), good_answer())

    run(tmp_path, run_id, messages)

    assert message in messages.calls[1]["messages"][0]["content"]


def test_a_rounded_pct_is_accepted() -> None:
    # 1 of 3 rows missing: null_pct 33.333...; the AI may write 33.3.
    profile = profile_csv(b"sku,name\nA1,Mug\nB2,\nC3,Cup\n", now=NOW)

    answer_model = SchemaInferenceAnswer.model_validate({
        "domain_confidence": 0.9, "domain_reasoning": "r", "dataset_issues": [],
        "columns": [column("sku", "sku"),
                    column("name", "product_name", issues=[
                        {"code": "missing_values", "count": 1, "pct": 33.3,
                         "examples": []}])],
    })

    check_answer(answer_model, profile)  # no error


def test_dataset_duplicate_count_is_checked(tmp_path: Path) -> None:
    run_id = profiled_run(tmp_path)
    wrong = answer([column(n, CANONICAL[n]) for n in COLUMNS],
                   dataset_issues=[{"code": "duplicate_rows", "count": 3,
                                    "severity": "low", "detail": "x"}])
    messages = FakeMessages(wrong, good_answer())

    run(tmp_path, run_id, messages)

    assert ("duplicate_rows count 3, but the profile has 1"
            in messages.calls[1]["messages"][0]["content"])


def test_a_name_the_ai_trimmed_is_matched_back_to_the_file(tmp_path: Path) -> None:
    run_id = profiled_run(tmp_path, b"sku, Qty \nA1,3\nB2,5\n")
    trimmed = answer([column("sku", "sku"), column("qty", "quantity")], dataset_issues=[])

    returned = run(tmp_path, run_id, FakeMessages(trimmed))

    assert [c.source_name for c in returned.columns] == ["sku", " Qty "]
    assert returned.columns[1].canonical_field == "quantity"


def test_an_ambiguous_trimmed_name_is_not_guessed(tmp_path: Path) -> None:
    # Both " qty" and "QTY " trim-and-fold to "qty": the AI must use the exact name.
    run_id = profiled_run(tmp_path, b"sku, qty,QTY \nA1,3,4\n")
    vague = answer([column("sku", "sku"), column("qty"), column("qty")], dataset_issues=[])
    exact = answer([column("sku", "sku"), column(" qty"), column("QTY ")], dataset_issues=[])
    messages = FakeMessages(vague, exact)

    returned = run(tmp_path, run_id, messages)

    assert "columns missing" in messages.calls[1]["messages"][0]["content"]
    assert [c.source_name for c in returned.columns] == ["sku", " qty", "QTY "]


def test_a_failed_rerun_removes_the_earlier_result(tmp_path: Path) -> None:
    # Otherwise a later step would read a valid-looking file for a degraded run.
    run_id = profiled_run(tmp_path)
    run(tmp_path, run_id, FakeMessages(good_answer()))
    timeout = anthropic.APITimeoutError(
        request=httpx2.Request("POST", "https://api.anthropic.com/v1/messages"))

    with pytest.raises(AIUnavailable):
        run(tmp_path, run_id, FakeMessages(timeout))

    assert not written(tmp_path, run_id).exists()


def test_missing_raw_csv_is_a_clear_error_before_any_ai_call(tmp_path: Path) -> None:
    run_id = profiled_run(tmp_path)
    (tmp_path / run_id / "raw.csv").unlink()
    messages = FakeMessages()

    with pytest.raises(FileNotFoundError, match="raw.csv"):
        run(tmp_path, run_id, messages)

    assert messages.calls == []


# --- doubt review cycle 2 -------------------------------------------------------------


def make_answer(columns: list[dict[str, Any]], dataset_issues: list[dict[str, Any]]
                ) -> SchemaInferenceAnswer:
    return SchemaInferenceAnswer.model_validate(
        {"domain_confidence": 0.9, "domain_reasoning": "r",
         "dataset_issues": dataset_issues, "columns": columns})


def test_a_dataset_issue_may_count_cells_not_only_rows() -> None:
    # 2 rows x 3 columns: 5 missing cells is more than the 2 rows, and true.
    profile = profile_csv(b"a,b,c\n,,\n,,1\n", now=NOW)
    answer_model = make_answer(
        [column("a"), column("b"), column("c")],
        [{"code": "missing_values", "count": 5, "severity": "high", "detail": "5 gaps"}],
    )

    check_answer(answer_model, profile)  # no error


def test_a_dataset_issue_above_the_cell_count_is_rejected() -> None:
    profile = profile_csv(b"a,b,c\n,,\n,,1\n", now=NOW)  # 6 cells
    answer_model = make_answer(
        [column("a"), column("b"), column("c")],
        [{"code": "missing_values", "count": 7, "severity": "high", "detail": "x"}],
    )

    with pytest.raises(ValueError, match="exceeds the 6 cells"):
        check_answer(answer_model, profile)


def test_a_percentage_the_profile_cannot_hold_must_be_null() -> None:
    # The profile has no figure for negative_values, so a pct would be invented.
    profile = profile_csv(b"sku,qty\nA1,-3\n", now=NOW)
    answer_model = make_answer(
        [column("sku"), column("qty", issues=[{"code": "negative_values", "count": 1,
                                               "pct": 99.9, "examples": []}])], [])

    with pytest.raises(ValueError, match="qty: negative_values pct must be null"):
        check_answer(answer_model, profile)


def test_all_null_column_is_checked_against_the_profile() -> None:
    # "qty" has no missing values at all, so the claim cannot be true.
    profile = profile_csv(b"sku,qty\nA1,3\nB2,4\n", now=NOW)
    answer_model = make_answer(
        [column("sku"), column("qty", issues=[{"code": "all_null_column", "count": 2,
                                               "pct": None, "examples": []}])], [])

    with pytest.raises(ValueError, match="qty: all_null_column, but the profile counts 0"):
        check_answer(answer_model, profile)


def test_an_error_that_is_not_the_ai_keeps_the_earlier_result(tmp_path: Path) -> None:
    # A missing prompt template is a programming error, not an AI failure: it
    # must not destroy a valid inference from an earlier run.
    run_id = profiled_run(tmp_path)
    run(tmp_path, run_id, FakeMessages(good_answer()))
    broken = AIClient(FakeMessages(), prompts_dir=tmp_path / "no-prompts")

    with pytest.raises(FileNotFoundError):
        infer_schema_run(tmp_path, run_id, broken, model="m",
                         retry_budget=RetryBudget(), now=NOW)

    assert written(tmp_path, run_id).exists()


def test_a_profile_from_different_data_is_refused(tmp_path: Path) -> None:
    run_id = profiled_run(tmp_path)
    # Same headers, more rows: the profile's figures no longer describe the file.
    (tmp_path / run_id / "raw.csv").write_bytes(CSV + b"D4,Jug,1,5.00\n")
    messages = FakeMessages()

    with pytest.raises(ValueError, match="does not match"):
        run(tmp_path, run_id, messages)

    assert messages.calls == []


def test_sample_rows_are_sent_as_a_header_and_value_lists() -> None:
    # Column names once, not repeated in all 30 rows.
    raw = b"sku,name\nA1,Mug\nB2,Cup\n"
    profile = profile_csv(raw, now=NOW)

    variables = build_prompt_variables(profile, read_csv_text(raw).frame)

    sent = json.loads(variables["sample_rows"])
    assert sent["columns"] == ["sku", "name"]
    assert sent["rows"] == [{"row": 1, "values": ["A1", "Mug"]},
                            {"row": 2, "values": ["B2", "Cup"]}]


# --- doubt review cycle 3 -------------------------------------------------------------


def test_an_invented_pct_on_all_null_column_is_rejected() -> None:
    # The elif chain used to skip the pct rule for this code.
    profile = profile_csv(b"sku,note\nA1,\nB2,\n", now=NOW)
    answer_model = make_answer(
        [column("sku"), column("note", issues=[{"code": "all_null_column", "count": 2,
                                                "pct": 42.7, "examples": []}])], [])

    with pytest.raises(ValueError, match="note: all_null_column pct 42.7"):
        check_answer(answer_model, profile)


def test_all_null_column_accepts_the_profiles_own_percentage() -> None:
    profile = profile_csv(b"sku,note\nA1,\nB2,\n", now=NOW)
    for pct in (None, 100.0):
        answer_model = make_answer(
            [column("sku"), column("note", issues=[{"code": "all_null_column", "count": 2,
                                                    "pct": pct, "examples": []}])], [])

        check_answer(answer_model, profile)  # no error


def test_a_stale_profile_is_the_named_stale_input_error(tmp_path: Path) -> None:
    run_id = profiled_run(tmp_path)
    (tmp_path / run_id / "raw.csv").write_bytes(CSV + b"D4,Jug,1,5.00\n")

    with pytest.raises(StaleInputError):
        run(tmp_path, run_id, FakeMessages())
