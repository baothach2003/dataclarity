"""Session 4B (ninth run): the strategy step end to end with the AI faked -
no real call (Thach's rule for this run; the network guard fails any).
The answer is checked (strategy_checks), retried once with its problems
named (the run's shared budget), then degraded: AIUnavailable, the caller
keeps the forecast (docs/CONTRACTS.md section 8). Written before the code.
"""

import json
import re
from pathlib import Path
from typing import Any

import anthropic
import httpx
import pytest

from contracts.diagnosis import DiagnosisContract
from contracts.forecast import ForecastBlock
from contracts.metrics import MetricsContract
from shared.ai_client import AIClient, AIUnavailable, RetryBudget
from stages.predict.ai_strategy import (
    BLOCKED,
    MAX_TOKENS,
    NOT_COMPARABLE,
    PROMPT_NAME,
    StrategyAnswer,
    not_asked,
    recommend,
)
from tests.ai_fakes import FakeMessages, FakeResponse
from tests.contracts.test_diagnosis import diagnosis_payload
from tests.contracts.test_forecast import forecast_payload
from tests.contracts.test_metrics import metrics_payload

PROMPT = Path(__file__).resolve().parents[3] / "prompts" / "strategy.md"
# Every figure is cited by path from the example files: revenue 1,150,000
# from 1,290,000 (-10.9%), orders 1,820 from 1,950, 118 Champions at
# £3,320.50, 812 active customers, an order £631.90, the top product £38,400.
# Code computes each impact: 118 x 3,320.50 x 5% = 19,590.95; 38,400 x 10% =
# 3,840; 118 x 631.90 x 10% = 7,456.42.
CHAMPIONS = "metrics.customers.segments[Champions]"
ANSWER: dict[str, Any] = {
    "recommendations": [
        {"priority": 1,
         "insight": "Revenue fell {metrics.core.revenue_change_pct} to £{metrics.core.revenue_current} from "
                    "£{metrics.core.revenue_previous}.",
         "cause": "Orders fell from {metrics.core.orders_previous} to {metrics.core.orders_current}.",
         "action": "Send a replenishment reminder to the Champions within {window:14 days}.",
         "expected_impact": "{" + CHAMPIONS + ".customers} customers x £{" + CHAMPIONS + ".avg_monetary} x "
                            "{assume:5%}",
         "how_to_measure": "Orders from the Champions over {window:30 days}.", "confidence": 0.6},
        {"priority": 2, "insight": "The top product took £{metrics.products.top_products[0].revenue}.",
         "cause": "Orders fell from {metrics.core.orders_previous} to {metrics.core.orders_current}.",
         "action": "Bundle it with weaker products for {window:30 days}.",
         "expected_impact": "£{metrics.products.top_products[0].revenue} x {assume:10%}",
         "how_to_measure": "Its revenue over {window:30 days}.", "confidence": 0.5},
        {"priority": 3, "insight": "The average order was £{metrics.core.aov_current}.",
         "cause": "{metrics.core.active_customers_current} customers were active.",
         "action": "Early access for the Champions for {window:30 days}.",
         "expected_impact": "{" + CHAMPIONS + ".customers} x £{metrics.core.aov_current} x {assume:10%}",
         "how_to_measure": "Champions' orders over {window:30 days}.", "confidence": 0.4},
    ],
    "do_not_do": [{"tempting_action": "A {offer:20%} discount to every customer",
                   "why_wrong_here": "Revenue fell {metrics.core.revenue_change_pct}, and the Champions buy "
                                     "without one."}],
}


def _files() -> tuple[MetricsContract, DiagnosisContract, ForecastBlock]:
    return (MetricsContract.model_validate(metrics_payload()), DiagnosisContract.model_validate(diagnosis_payload()),
            ForecastBlock.model_validate(forecast_payload()["forecast"]))


def _run(*outcomes: dict | Exception, budget: RetryBudget | None = None) -> tuple[Any, FakeMessages]:
    messages = FakeMessages(*[FakeResponse(json.dumps(o)) if isinstance(o, dict) else o for o in outcomes])
    strategy = recommend(*_files(), AIClient(messages), "test-model-reasoning", budget or RetryBudget())
    return strategy, messages


def test_a_checked_answer_is_the_strategy_and_the_model_that_answered_is_kept() -> None:
    strategy, messages = _run(ANSWER)
    assert [r.priority for r in strategy.recommendations] == [1, 2, 3]
    assert strategy.recommendations[0].insight == "Revenue fell 10.9% to £1,150,000 from £1,290,000."
    assert strategy.recommendations[0].expected_impact == "118 customers x £3,320.50 x 5% (assumed) = 19,591"
    assert [d.tempting_action for d in strategy.do_not_do] == ["A 20% discount to every customer"]
    assert strategy.model == "served-model"  # the fake's served model, for model_used
    (call,) = messages.calls
    assert (call["model"], call["max_tokens"]) == ("test-model-reasoning", MAX_TOKENS) and PROMPT_NAME == "strategy"


def test_the_prompt_carries_the_three_parts_and_nothing_else_of_the_files() -> None:
    metrics = metrics_payload()
    metrics["core"]["notes"][0]["text"] = "A SENTENCE THE FILE CARRIES"
    messages = FakeMessages(FakeResponse(json.dumps(ANSWER)))
    recommend(MetricsContract.model_validate(metrics), *_files()[1:], AIClient(messages), "m", RetryBudget())
    prompt = messages.calls[0]["messages"][0]["content"]
    assert '"revenue_current": 1150000.0' in prompt and '"headline"' in prompt and '"months_used": 24' in prompt
    assert "A SENTENCE THE FILE CARRIES" not in prompt and '"evidence"' not in prompt


def test_an_answer_that_fails_a_check_is_retried_once_with_its_problems_named() -> None:
    wrong = json.loads(json.dumps(ANSWER))
    wrong["recommendations"][0]["insight"] = "Revenue fell to £1,000,000."
    budget = RetryBudget()
    strategy, messages = _run(wrong, ANSWER, budget=budget)
    assert len(messages.calls) == 2 and budget.remaining == 0
    retry = messages.calls[1]["messages"][0]["content"]
    assert "Your previous response was rejected" in retry
    assert "recommendation 1 insight: 1,000,000 is a number you wrote" in retry
    assert strategy.recommendations[0].insight == "Revenue fell 10.9% to £1,150,000 from £1,290,000."


def test_two_answers_that_fail_are_unavailable_and_the_budget_is_the_runs() -> None:
    wrong = json.loads(json.dumps(ANSWER))
    wrong["do_not_do"] = []
    with pytest.raises(AIUnavailable) as caught:
        _run(wrong, wrong)
    assert caught.value.reason == "invalid_response"
    # The run's one retry already spent (by stage 1): no second call.
    messages = FakeMessages(FakeResponse(json.dumps(wrong)), FakeResponse(json.dumps(ANSWER)))
    with pytest.raises(AIUnavailable):
        recommend(*_files(), AIClient(messages), "m", RetryBudget(remaining=0))
    assert len(messages.calls) == 1


def test_a_field_the_schema_does_not_name_is_refused() -> None:
    extra = json.loads(json.dumps(ANSWER))
    extra["recommendations"][0]["stock_to_order"] = 40
    strategy, messages = _run(extra, ANSWER)
    assert len(messages.calls) == 2 and "stock_to_order" in messages.calls[1]["messages"][0]["content"]


def test_an_api_failure_is_unavailable() -> None:
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    with pytest.raises(AIUnavailable) as caught:
        _run(anthropic.APITimeoutError(request=request))
    assert caught.value.reason == "timeout"


def test_the_prompts_schema_is_the_answer_models() -> None:
    schema = PROMPT.read_text(encoding="utf-8").split("OUTPUT SCHEMA", 1)[1]
    keys = set(re.findall(r'"([a-z_]+)":', schema))
    fields = set(StrategyAnswer.model_fields)
    for name in ("recommendations", "do_not_do"):
        fields |= set(StrategyAnswer.model_fields[name].annotation.__args__[0].model_fields)  # list[Model]
    assert keys == fields


def test_a_product_marked_in_metrics_json_is_named_so_too() -> None:
    # 4B review 1 #5: only diagnosis.json's marks were checked; a top
    # product or a decliner is marked in metrics.json.
    metrics = metrics_payload()
    metrics["products"]["suggested_classes"] = {"WHITE HANGING HEART T-LIGHT HOLDER": "pooled"}
    wrong = json.loads(json.dumps(ANSWER))
    wrong["recommendations"][1]["action"] = ("Bundle WHITE HANGING HEART T-LIGHT HOLDER with weaker products "
                                             "for {window:30 days}.")
    messages = FakeMessages(FakeResponse(json.dumps(wrong)), FakeResponse(json.dumps(ANSWER)))
    recommend(MetricsContract.model_validate(metrics), *_files()[1:], AIClient(messages), "m", RetryBudget())
    assert "'WHITE HANGING HEART T-LIGHT HOLDER' is marked as possibly not a product" in (
        messages.calls[1]["messages"][0]["content"])


def test_the_ai_is_not_asked_on_a_blocked_diagnosis_or_an_incomplete_previous_month() -> None:
    # 4B review 1 #11 and #13: no recommendation on data the engine refuses
    # to diagnose, nor a comparison with part of a month (CONTRACTS 11).
    metrics, diagnosis, _ = _files()
    assert not_asked(metrics, diagnosis) is None
    blocked = diagnosis_payload()
    blocked["trust"]["verdict"] = "blocked"
    blocked.update({"calendar": None, "signals": None, "tree": None, "localization": None,
                    "headline": {"rule": 1, "hypothesis_id": None, "lens": None, "message": "m"}})
    assert not_asked(metrics, DiagnosisContract.model_validate(blocked)) == BLOCKED
    # Only the period's flag is read (a whole file with an incomplete
    # previous month carries a reason beside every comparison).
    incomplete = metrics.model_copy(update={"period": metrics.period.model_copy(update={"previous_complete": False})})
    assert not_asked(incomplete, diagnosis) == NOT_COMPARABLE
