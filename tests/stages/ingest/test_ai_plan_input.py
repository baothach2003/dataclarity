"""What the plan step sends to the AI (stages/ingest/ai_input.py,
docs/AI_PIPELINE.md sections 1 and 2): the profile and the schema inference
result, bounded in count and in size, and nothing else."""

import json
from typing import Any

from contracts.profile import DatasetIssue
from stages.ingest.ai_input import (
    MAX_AI_COLUMNS,
    MAX_VALUE_CHARS,
    build_plan_variables,
    build_profile_json,
    build_prompt_variables,
)
from stages.ingest.profiling import profile_csv, read_csv_text
from tests.stages.ingest.plan_answers import (
    SCHEMA_COLUMNS,
    make_schema,
    schema_column,
)
from tests.stages.ingest.schema_answers import CSV, NOW


def sent(schema_columns: list[Any] | None = None, **kwargs: Any) -> dict[str, Any]:
    profile = profile_csv(CSV, now=NOW)
    schema = make_schema(schema_columns, **kwargs)
    return json.loads(build_plan_variables(profile, schema)["schema_inference_json"])


def test_the_plan_gets_exactly_the_two_placeholders_of_its_template() -> None:
    profile = profile_csv(CSV, now=NOW)

    variables = build_plan_variables(profile, make_schema())

    assert set(variables) == {"profile_json", "schema_inference_json"}


def test_the_profile_is_the_one_the_schema_step_sends() -> None:
    # One definition of "the bounded profile", so the two steps cannot drift.
    profile = profile_csv(CSV, now=NOW)
    frame = read_csv_text(CSV).frame

    assert (build_plan_variables(profile, make_schema())["profile_json"]
            == build_prompt_variables(profile, frame)["profile_json"]
            == build_profile_json(profile))


def test_each_column_carries_the_actions_that_are_legal_for_it() -> None:
    columns = {c["source_name"]: c for c in sent()["columns"]}

    # quantity is a required field: no imputation is offered.
    assert columns["qty"]["legal_actions"] == [
        "drop_rows_missing", "drop_column", "cast_type", "fix_negative",
        "clip_outliers_iqr", "flag_only"]
    assert "impute_median" in columns["price"]["legal_actions"]
    assert "impute_median" not in columns["sku"]["legal_actions"]


def test_the_dataset_actions_and_the_business_key_are_given() -> None:
    columns = [*SCHEMA_COLUMNS,
               schema_column("day", "datetime", "transaction_date")]

    payload = sent(columns)

    assert payload["dataset_legal_actions"] == ["remove_exact_duplicates", "flag_duplicate_keys"]
    assert payload["business_key"] == ["sku", "day"]


def test_the_business_key_is_empty_when_the_file_has_none() -> None:
    assert sent()["business_key"] == []  # SCHEMA_COLUMNS has no transaction date


def test_issues_carry_code_count_and_pct_and_no_row_references() -> None:
    columns = {c["source_name"]: c for c in sent()["columns"]}

    assert columns["price"]["issues"] == [{"code": "missing_values", "count": 1, "pct": 25.0}]
    assert "examples" not in json.dumps(sent())


def test_the_ais_own_reasoning_and_the_header_fields_are_not_sent_back() -> None:
    text = json.dumps(sent())

    for noise in ("schema_version", "generated_at", "model_used", "domain_reasoning",
                  "domain_confidence", "looks like sales data"):
        assert noise not in text


def test_a_long_dataset_issue_detail_is_cut() -> None:
    # The detail is AI text that may echo a cell of the uploaded file; it must
    # not carry an arbitrarily long value into the second call.
    long_detail = "x" * 500
    issues = [DatasetIssue(code="duplicate_rows", count=1, severity="low", detail=long_detail)]

    detail = sent(dataset_issues=issues)["dataset_issues"][0]["detail"]

    assert len(detail) == MAX_VALUE_CHARS


def test_only_the_first_25_columns_are_sent_and_their_names_are_never_cut() -> None:
    long_name = "n" * 300
    columns = [schema_column(long_name, "text")] + [
        schema_column(f"c{i}", "text") for i in range(1, 30)]
    header = ",".join([long_name] + [f"c{i}" for i in range(1, 30)])
    raw = f"{header}\n{','.join('1' for _ in range(30))}\n".encode()
    profile = profile_csv(raw, now=NOW)

    payload = json.loads(
        build_plan_variables(profile, make_schema(columns))["schema_inference_json"])

    assert len(payload["columns"]) == MAX_AI_COLUMNS
    assert payload["columns"][0]["source_name"] == long_name
