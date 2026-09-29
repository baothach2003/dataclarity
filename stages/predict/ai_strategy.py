"""Stage 4 Predict - the strategy step (docs/AI_PIPELINE.md section 8): the
AI turns the metrics, the diagnosis and the forecast into 3 to 5 ranked
recommendations and a do-not-do list. The AI writes no number (CLAUDE.md
3.2 by construction): it cites the input's figures by path and proposes
bounded tokens, code renders them and computes every expected impact
(strategy_render.py); its answer is untrusted input, validated against a
strict schema and checked (strategy_checks.py);
one retry with the problems named (the run's shared budget), then
AIUnavailable - the caller keeps the computed forecast and writes the AI
blocks as null (CONTRACTS section 8). It writes nothing: 4C assembles
forecast.json.

It is not asked at all (`not_asked`) when the diagnosis is blocked - the
engine refuses to diagnose the data - or the previous month is not
complete, so nothing can be compared (CONTRACTS 11; 4B review 1 #11, #13).
"""

import json
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict

from contracts.diagnosis import DiagnosisContract
from contracts.forecast import DoNotDo, ForecastBlock, Recommendation
from contracts.metrics import MetricsContract
from shared.ai_client import AIClient, RetryBudget
from stages.predict.strategy_checks import check_answer, review
from stages.predict.strategy_input import strategy_input

PROMPT_NAME = "strategy"
MAX_TOKENS = 3000  # AI_PIPELINE section 2's budget for one answer
BLOCKED = "no recommendation: the diagnosis is blocked - the data cannot be diagnosed (its trust checks say why)"
NOT_COMPARABLE = "no recommendation: the previous month is not complete, so the months cannot be compared"


class RecommendationAnswer(Recommendation):
    """The AI's recommendation, strict: no field the contract does not name."""

    model_config = ConfigDict(extra="forbid")


class DoNotDoAnswer(DoNotDo):
    model_config = ConfigDict(extra="forbid")


class StrategyAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    recommendations: list[RecommendationAnswer]
    do_not_do: list[DoNotDoAnswer]


@dataclass(frozen=True)
class Strategy:
    recommendations: list[Recommendation]
    do_not_do: list[DoNotDo]
    model: str  # the model that answered, for `model_used`


def not_asked(metrics: MetricsContract, diagnosis: DiagnosisContract) -> str | None:
    """Why the AI is not asked for recommendations on this run, or None."""
    if diagnosis.trust.verdict == "blocked":
        return BLOCKED
    if not metrics.period.previous_complete:
        return NOT_COMPARABLE
    return None


def recommend(metrics: MetricsContract, diagnosis: DiagnosisContract, forecast: ForecastBlock, client: AIClient,
              model: str, retry_budget: RetryBudget) -> Strategy:
    """The AI's recommendations, checked and rendered by code; raises
    AIUnavailable when none is accepted. The caller asks `not_asked` first."""
    payload = strategy_input(metrics, diagnosis, forecast)
    # Both files' marks: a top product or a decliner is marked in metrics.json
    # (4B review 1 #5), a member or a hypothesis's product in diagnosis.json.
    suggested = dict(metrics.products.suggested_classes) | dict(diagnosis.suggested_classes)
    basis = metrics.core.orders_basis
    variables = {f"{part}_json": json.dumps(payload[part], indent=1, ensure_ascii=False)
                 for part in ("metrics", "diagnosis", "forecast")}
    result = client.call_structured(
        PROMPT_NAME, variables, StrategyAnswer, model=model, max_tokens=MAX_TOKENS, retry_budget=retry_budget,
        validate=lambda answer: check_answer(answer.recommendations, answer.do_not_do, payload, suggested, basis))
    rendered = review(result.value.recommendations, result.value.do_not_do, payload, suggested, basis)
    return Strategy([Recommendation(**r) for r in rendered.recommendations],
                    [DoNotDo(**d) for d in rendered.do_not_do], result.model)
