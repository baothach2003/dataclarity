"""prompts/root_cause.md must keep the narration-only limits.

Created in the Stage 3 SPECS UPDATE session, which rewrote the prompt from
"the AI picks and rules out hypotheses" to "the AI narrates hypotheses the
engine already decided". The brief for that session assumed a prompt test
already existed; it did not (only cleaning_plan and schema_inference had one),
so the rewritten prompt would otherwise have landed unpinned.

Why a prompt-content test rather than a behaviour test: the rule lives in the
wording, there is no code path to exercise, and CLAUDE.md forbids spending real
tokens in the suite. The step 8 validator (docs/AI_PIPELINE.md section 7.9)
enforces the same limits against a real answer at runtime; these tests only
guarantee the instructions never quietly go missing. Same pattern as
tests/stages/ingest/test_schema_inference_prompt.py.
"""

import re
from pathlib import Path

PROMPT = (Path(__file__).resolve().parents[3] / "prompts" / "root_cause.md").read_text(
    encoding="utf-8")


def section(name: str) -> str:
    """The text from a heading line to the next all-caps heading."""
    match = re.search(rf"^{name}[^\n]*\n(.*?)(?=^[A-Z][A-Z ]+(?: \(|$)|\Z)", PROMPT,
                      re.DOTALL | re.MULTILINE)
    assert match, f"no {name} section in the prompt"
    return match.group(1)


def test_the_prompt_has_a_hard_limits_section() -> None:
    assert section("HARD LIMITS").strip()


def test_the_ai_may_not_choose_or_re_rank_hypotheses() -> None:
    limits = section("HARD LIMITS").lower()

    assert "may not choose" in limits
    assert "re-rank" in limits
    assert "fixed" in limits


def test_the_ai_may_not_upgrade_a_verdict() -> None:
    limits = section("HARD LIMITS").lower()

    assert "upgrade a verdict" in limits
    # The two verdicts that must never be narrated as an explanation.
    assert "inconclusive" in limits
    assert "ruled_out" in limits


def test_the_ai_may_not_invent_numbers() -> None:
    limits = section("HARD LIMITS").lower()

    assert "only numbers present in the input" in limits
    assert "never invent" in limits


def test_contribution_is_not_stated_as_causation() -> None:
    limits = section("HARD LIMITS").lower()

    assert "consistent with" in limits
    assert "never" in limits and "caused" in limits


def test_a_possible_stockout_must_be_worded_as_needing_verification() -> None:
    limits = section("HARD LIMITS").lower()

    assert "stockout" in limits
    assert "verified on the shelf" in limits


def test_the_not_tested_sentence_is_mandatory() -> None:
    limits = section("HARD LIMITS").lower()

    assert "not-tested sentence is mandatory" in limits


def test_the_output_schema_matches_the_contract_block() -> None:
    schema = section("OUTPUT SCHEMA")

    # docs/CONTRACTS.md section 7: ai_findings = {summary,
    # headline_explanation, hypothesis_notes: [{id, text}], not_tested_note}.
    for field in ("summary", "headline_explanation", "hypothesis_notes", "not_tested_note"):
        assert f'"{field}"' in schema, f"{field} missing from the output schema"


def test_the_prompt_takes_the_whole_computed_diagnosis_as_its_input() -> None:
    # Never raw rows: the AI sees only what steps 1-7 computed.
    assert "{diagnosis_json}" in PROMPT
    assert "{metrics_json}" not in PROMPT
    assert "{decomposition_json}" not in PROMPT
