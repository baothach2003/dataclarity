"""Stage 1, AI step A: schema inference -> schema_inference.json
(docs/AI_PIPELINE.md sections 1-3, docs/CONTRACTS.md section 3).

The AI sees a bounded input only: the profile cut to its first 25 columns and
at most 30 sample rows. Its answer is untrusted until it passes the schema
and the checks in this module.
"""

from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

from pydantic import BaseModel, Field

from contracts.profile import (
    ColumnInference,
    DatasetIssue,
    ProfileContract,
    SchemaInferenceContract,
)
from shared.ai_client import AIClient, AIUnavailable, RetryBudget
from shared.run_registry import run_file
from shared.order_checks import order_checks
from stages.ingest.ai_input import MAX_AI_COLUMNS, build_prompt_variables
from stages.ingest.contract_files import StaleInputError, write_contract
from stages.ingest.issue_recount import recount_issues
from stages.ingest.profiling import PROFILE_FILENAME, RAW_FILENAME, read_csv_text

# A pct the AI copied from the profile may be rounded to one decimal.
PCT_TOLERANCE = 0.1
MAX_TOKENS = 3000  # AI_PIPELINE section 2
PROMPT_NAME = "schema_inference"  # prompts/schema_inference.md
OUTPUT_FILENAME = "schema_inference.json"  # CONTRACTS.md section 1
SCHEMA_VERSION = "2.1"  # 2E-e: order_id in the canonical enum; 2E-e2: receipt_fill_lines


class SchemaInferenceAnswer(BaseModel):
    """What the AI returns: the contract without the header fields, which
    are ours to set (schema_version, generated_at, model_used)."""

    domain_confidence: Annotated[float, Field(ge=0, le=1)]
    domain_reasoning: str
    dataset_issues: list[DatasetIssue]
    columns: list[ColumnInference]


def check_answer(answer: SchemaInferenceAnswer, profile: ProfileContract) -> None:
    """Stage checks the schema alone cannot express. Raising ValueError sends
    the reasons back to the AI for the one retry (shared/ai_client.py)."""
    expected = [c.name for c in profile.columns[:MAX_AI_COLUMNS]]
    rows = profile.dataset.rows
    problems: list[str] = []
    resolved = [resolve_name(c.source_name, expected) for c in answer.columns]
    names = Counter(resolved)
    missing = [n for n in expected if n not in names]
    unknown = sorted(
        c.source_name for c, name in zip(answer.columns, resolved, strict=True) if name is None
    )
    repeated = sorted(n for n, times in names.items() if n is not None and times > 1)
    if missing:
        problems.append(f"columns missing: {missing}")
    if unknown:
        problems.append(f"columns unknown: {unknown}")
    if repeated:
        problems.append(f"columns listed more than once: {repeated}")
    fields = Counter(c.canonical_field for c in answer.columns if c.canonical_field != "ignore")
    doubled = sorted(f for f, times in fields.items() if times > 1)
    if doubled:
        problems.append(f"canonical fields mapped by more than one column: {doubled}")
    # Counts the file cannot support ("never invent counts",
    # prompts/schema_inference.md). A column issue counts cells in one column,
    # so it is bounded by the rows; a dataset issue may count cells anywhere.
    cells = rows * profile.dataset.columns
    for count in sorted({i.count for c in answer.columns for i in c.issues if i.count > rows}):
        problems.append(f"issue count {count} exceeds the {rows} data rows")
    for count in sorted({i.count for i in answer.dataset_issues if i.count > cells}):
        problems.append(f"dataset issue count {count} exceeds the {cells} cells")
    problems += _figure_mismatches(answer, resolved, profile)
    if problems:
        raise ValueError("; ".join(problems))


def _figure_mismatches(
    answer: SchemaInferenceAnswer, resolved: list[str | None], profile: ProfileContract
) -> list[str]:
    """Issue figures the profile already holds must match it (a pct within the
    rounding tolerance): the AI reports them, pandas computed them (CLAUDE.md
    3.2). For every other code the profile holds no percentage, so `pct` must
    be null (CONTRACTS.md section 3); those counts are replaced by pandas'
    once the answer is accepted (issue_recount.py)."""
    problems: list[str] = []
    by_name = {c.name: c for c in profile.columns}
    rows = profile.dataset.rows
    for issue in answer.dataset_issues:
        if issue.code == "duplicate_rows" and issue.count != profile.dataset.duplicate_rows:
            problems.append(f"duplicate_rows count {issue.count}, but the profile has "
                            f"{profile.dataset.duplicate_rows}")
    for column, name in zip(answer.columns, resolved, strict=True):
        if name is None:
            continue
        stats = by_name[name]
        for issue in column.issues:
            if issue.code == "missing_values":
                if issue.count != stats.null_count:
                    problems.append(f"{name}: missing_values count {issue.count}, "
                                    f"but the profile has {stats.null_count}")
                if issue.pct is not None and abs(issue.pct - stats.null_pct) > PCT_TOLERANCE:
                    problems.append(f"{name}: missing_values pct {issue.pct}, "
                                    f"but the profile has {round(stats.null_pct, 1)}")
            elif issue.code == "all_null_column":
                if stats.null_count != rows:
                    problems.append(f"{name}: all_null_column, but the profile counts "
                                    f"{stats.null_count} missing of {rows} rows")
                elif issue.count != rows:
                    problems.append(f"{name}: all_null_column count {issue.count}, "
                                    f"but the file has {rows} data rows")
                # This code has a percentage too: the column's own null_pct.
                if issue.pct is not None and abs(issue.pct - stats.null_pct) > PCT_TOLERANCE:
                    problems.append(f"{name}: all_null_column pct {issue.pct}, "
                                    f"but the profile has {round(stats.null_pct, 1)}")
            elif issue.pct is not None:
                # The profile holds no percentage for this code, so any number
                # here would be invented.
                problems.append(f"{name}: {issue.code} pct must be null, got {issue.pct}")
    return problems


def infer_schema_run(
    runs_root: Path,
    run_id: str,
    client: AIClient,
    model: str,
    retry_budget: RetryBudget,
    now: datetime | None = None,
) -> SchemaInferenceContract:
    """runs/<run_id>/profile.json + raw.csv -> schema_inference.json.

    Raises AIUnavailable when no answer is accepted; no file exists then (an
    earlier one is removed first), and the caller takes the degraded path
    (AI_PIPELINE section 9).
    """
    # CONTRACTS.md section 1: fail fast, before any AI call, on a missing input.
    for filename in (PROFILE_FILENAME, RAW_FILENAME):
        if not run_file(runs_root, run_id, filename).exists():
            raise FileNotFoundError(f"{filename} is missing for run {run_id}")
    profile = ProfileContract.model_validate_json(
        run_file(runs_root, run_id, PROFILE_FILENAME).read_text(encoding="utf-8"))
    frame = read_csv_text(run_file(runs_root, run_id, RAW_FILENAME).read_bytes()).frame
    sent = [c.name for c in profile.columns[:MAX_AI_COLUMNS]]
    if (
        [c.name for c in profile.columns] != [str(name) for name in frame.columns]
        or profile.dataset.rows != len(frame)
    ):
        # Stale profile: its figures would be checked against different data.
        raise StaleInputError(f"{PROFILE_FILENAME} does not match {RAW_FILENAME}; profile again")

    # Resolved before the call: looking it up in the failure path could raise
    # its own error and hide the AIUnavailable the caller must see.
    output_path = run_file(runs_root, run_id, OUTPUT_FILENAME)
    try:
        result = client.call_structured(
            PROMPT_NAME,
            build_prompt_variables(profile, frame),
            SchemaInferenceAnswer,
            model=model,
            max_tokens=MAX_TOKENS,
            retry_budget=retry_budget,
            validate=lambda answer: check_answer(answer, profile),
        )
    except AIUnavailable:
        # Only an AI failure clears an earlier result, so a degraded run leaves
        # no valid-looking file. A programming error (a broken template, say)
        # must not destroy a good inference.
        output_path.unlink(missing_ok=True)
        raise
    answer = result.value
    # Stored under the file's exact names, even where the AI trimmed them.
    by_name = {
        name: c.model_copy(update={"source_name": name})
        for c in answer.columns
        if (name := resolve_name(c.source_name, sent)) is not None
    }
    # The AI's counts are estimates for every code the profile holds no figure
    # for; pandas replaces them (CLAUDE.md 3.2, issue_recount.py).
    # Stage 1's own order checks on the raw file and this mapping - never the
    # AI's: the order_id check (2E-e) and the measure for Review's fill
    # question (2E-e2), from one parse.
    answered = [by_name[name] for name in sent]
    checks = order_checks(frame, {c.source_name: c.canonical_field for c in answered
                                  if c.canonical_field != "ignore"})
    columns, dataset_issues, _ = recount_issues(
        answered, answer.dataset_issues, frame, order_check=checks.spanning)
    contract = SchemaInferenceContract(
        schema_version=SCHEMA_VERSION,
        generated_at=now or datetime.now(UTC),
        model_used=result.model,
        domain_confidence=answer.domain_confidence,
        domain_reasoning=answer.domain_reasoning,
        dataset_issues=dataset_issues,
        # File order, whatever order the AI used; then the columns it never saw.
        columns=columns + [_not_inferred(c.name) for c in profile.columns[MAX_AI_COLUMNS:]],
        receipt_fill_lines=checks.fill_lines,
    )
    write_contract(output_path, contract)
    return contract


def resolve_name(given: str, expected: list[str]) -> str | None:
    """The file's column name the AI meant: an exact match, else the one name
    equal after trimming and case-folding (models tidy " Qty " into "Qty").
    Ambiguous or unknown names resolve to None and fail the check."""
    if given in expected:
        return given
    key = given.strip().casefold()
    matches = [name for name in expected if name.strip().casefold() == key]
    return matches[0] if len(matches) == 1 else None


def _not_inferred(name: str) -> ColumnInference:
    # Beyond the 25 columns the AI sees. Confidence 0 is below the 0.7 mark at
    # which the review screen flags a column (SPECS 4.2), so the user maps it.
    return ColumnInference(
        source_name=name, semantic_type="text", canonical_field="ignore",
        confidence=0.0, issues=[],
    )
