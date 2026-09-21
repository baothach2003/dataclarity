"""prompts/cleaning_plan.md must say what the code enforces. The template is
prose, so these tests tie it to the catalog data: if an action or a param is
added or renamed there and the prompt is forgotten, the AI would be asked for
something the checks reject, and the run's single retry would be spent on it.
"""

import re
from pathlib import Path
from typing import get_args

import pytest

from contracts.cleaning import TransformAction
from stages.ingest.transform_catalog import (
    CASE_MODES,
    CAST_TARGETS,
    NEGATIVE_STRATEGIES,
    OPTIONAL_PARAMS,
    REQUIRED_PARAMS,
)

PROMPT = (Path(__file__).resolve().parents[3] / "prompts" / "cleaning_plan.md").read_text(
    encoding="utf-8")


def section(name: str) -> str:
    """The text from a heading line to the next all-caps heading."""
    match = re.search(rf"^{name}[^\n]*\n(.*?)(?=^[A-Z][A-Z ]+(?: \(|$)|\Z)", PROMPT,
                      re.DOTALL | re.MULTILINE)
    assert match, f"no {name} section in the prompt"
    return match.group(1)


def test_the_catalog_line_lists_every_action_and_nothing_else() -> None:
    listed = set(re.findall(r"[a-z_]+", section("CATALOG")))

    assert listed == set(get_args(TransformAction))


def test_the_template_has_the_two_placeholders_the_step_fills() -> None:
    assert set(re.findall(r"\{([a-z_]+)\}", PROMPT)) == {"profile_json", "schema_inference_json"}


PARAM_LINES = {
    match.group(1): match.group(2)
    for match in re.finditer(r"^- ([a-z_]+): (.+)$", section("PARAMS"), re.MULTILINE)
}


@pytest.mark.parametrize("action", sorted(set(REQUIRED_PARAMS) | set(OPTIONAL_PARAMS)))
def test_every_param_is_described_with_whether_it_is_required(action: TransformAction) -> None:
    line = PARAM_LINES[action]

    for name in REQUIRED_PARAMS.get(action, frozenset()):
        assert re.search(rf"\b{name} \(required", line), (action, name)
    for name in OPTIONAL_PARAMS.get(action, frozenset()):
        assert re.search(rf"\b{name} \(optional", line), (action, name)


def test_no_action_without_params_is_given_a_params_line() -> None:
    with_params = set(REQUIRED_PARAMS) | set(OPTIONAL_PARAMS)

    assert set(PARAM_LINES) == with_params


@pytest.mark.parametrize(
    "values", [CAST_TARGETS, CASE_MODES, NEGATIVE_STRATEGIES], ids=["cast", "case", "negative"]
)
def test_every_allowed_value_of_an_enum_param_is_in_the_prompt(values: frozenset[str]) -> None:
    for value in values:
        assert re.search(rf"\b{value}\b", section("PARAMS")), value


@pytest.mark.parametrize(
    "rule",
    [
        "legal_actions",            # the whitelist is given per column
        "dataset_legal_actions",
        "business_key",
        "never flag_only",          # CONTRACTS section 4's old example, ruled out by the matrix
        "exactly as given",         # source names are copied, never tidied
        "never compute",            # no AI arithmetic (AI_PIPELINE section 1)
    ],
)
def test_the_prompt_states_the_rules_the_checks_enforce(rule: str) -> None:
    assert rule in PROMPT
