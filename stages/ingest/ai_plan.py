"""Stage 1, AI step B: cleaning plan proposal -> plan_proposed.json
(docs/AI_PIPELINE.md sections 2-4 and 6, docs/CONTRACTS.md section 4).

The AI sees the bounded profile and the schema inference result, and only
recommends. Its answer is untrusted until it passes `plan_checks.check_plan`; the
user still reviews and edits the plan before anything runs (CLAUDE.md 3.3).

What the AI does not decide, because the schema step already did: each column's
semantic type and canonical field. They are copied from `schema_inference.json`
into the plan, whatever the answer says.
"""

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from contracts.cleaning import CleaningPlanContract, ColumnAction, DatasetAction
from contracts.profile import ColumnInference, ProfileContract, SchemaInferenceContract
from shared.ai_client import AIClient, AIUnavailable, RetryBudget
from shared.run_registry import run_file
from stages.ingest.ai_input import MAX_AI_COLUMNS, build_plan_variables
from stages.ingest.ai_schema import OUTPUT_FILENAME as SCHEMA_FILENAME
from stages.ingest.ai_schema import resolve_name
from stages.ingest.contract_files import write_contract
from stages.ingest.plan_checks import (
    CleaningPlanAnswer,
    ColumnActionAnswer,
    check_plan,
    tidy_alternatives,
)
from stages.ingest.profiling import PROFILE_FILENAME

MAX_TOKENS = 3000  # AI_PIPELINE section 2
PROMPT_NAME = "cleaning_plan"  # prompts/cleaning_plan.md
OUTPUT_FILENAME = "plan_proposed.json"  # CONTRACTS.md section 1
SCHEMA_VERSION = "1.0"
























def propose_plan_run(
    runs_root: Path,
    run_id: str,
    client: AIClient,
    model: str,
    retry_budget: RetryBudget,
    now: datetime | None = None,
) -> CleaningPlanContract:
    """runs/<run_id>/profile.json + schema_inference.json -> plan_proposed.json.

    Raises AIUnavailable when no answer is accepted; no proposal exists then (an
    earlier one is removed, the user's plan_final.json is not touched), and the
    caller takes the degraded path: the user builds the plan by hand
    (AI_PIPELINE section 9).
    """
    # CONTRACTS.md section 1: fail fast, before any AI call, on a missing input.
    for filename in (PROFILE_FILENAME, SCHEMA_FILENAME):
        if not run_file(runs_root, run_id, filename).exists():
            raise FileNotFoundError(f"{filename} is missing for run {run_id}")
    profile = ProfileContract.model_validate_json(
        run_file(runs_root, run_id, PROFILE_FILENAME).read_text(encoding="utf-8"))
    schema = SchemaInferenceContract.model_validate_json(
        run_file(runs_root, run_id, SCHEMA_FILENAME).read_text(encoding="utf-8"))
    if [c.name for c in profile.columns] != [c.source_name for c in schema.columns]:
        # Stale: the file was profiled again after the schema was inferred.
        raise ValueError(
            f"{SCHEMA_FILENAME} does not match {PROFILE_FILENAME}; infer the schema again")
    sent = schema.columns[:MAX_AI_COLUMNS]

    output_path = run_file(runs_root, run_id, OUTPUT_FILENAME)
    try:
        result = client.call_structured(
            PROMPT_NAME,
            build_plan_variables(profile, schema),
            CleaningPlanAnswer,
            model=model,
            max_tokens=MAX_TOKENS,
            retry_budget=retry_budget,
            validate=lambda answer: check_plan(answer, sent),
        )
    except AIUnavailable:
        # Only an AI failure clears an earlier proposal; a programming error
        # must not destroy a good one.
        output_path.unlink(missing_ok=True)
        raise
    answer = result.value
    sent_names = [c.source_name for c in sent]
    # Stored under the file's exact names, even where the AI trimmed them.
    planned = {
        name: a for a in answer.column_actions
        if (name := resolve_name(a.source_name, sent_names)) is not None
    }
    contract = CleaningPlanContract(
        schema_version=SCHEMA_VERSION,
        generated_at=now or datetime.now(UTC),
        source="ai",
        dataset_actions=[
            DatasetAction.model_validate({
                **a.model_dump(),
                "alternatives": tidy_alternatives(a.action, a.alternatives),
                "edited_by_user": False,
            })
            for a in answer.dataset_actions
        ],
        # File order, whatever order the AI used; then the columns it never saw.
        column_actions=[_column_action(c, planned.get(c.source_name)) for c in schema.columns],
    )
    write_contract(output_path, contract)
    return contract




def _column_action(column: ColumnInference, planned: ColumnActionAnswer | None) -> ColumnAction:
    """The plan entry for one column: the AI's, with the type and mapping the
    schema step settled. A column the AI never saw (beyond the first 25) gets an
    action that changes nothing and says why, so the user takes it from there."""
    if planned is None:
        chosen: dict[str, Any] = {
            "action": "flag_only",
            "params": {"note": "not analyzed by the AI"},
            "rationale": (f"Not analyzed: only the first {MAX_AI_COLUMNS} columns are sent to "
                          f"the AI. Choose an action for this column by hand."),
            "alternatives": [],
        }
    else:
        chosen = planned.model_dump(exclude={"source_name"})
        chosen["alternatives"] = tidy_alternatives(planned.action, planned.alternatives)
    return ColumnAction.model_validate({
        **chosen,
        "source_name": column.source_name,
        "semantic_type": column.semantic_type,
        "canonical_field": column.canonical_field,
        "edited_by_user": False,
    })
