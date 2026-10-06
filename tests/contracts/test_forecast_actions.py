"""forecast.json 2.1's structured actions (the report redesign, D4; Thach,
2026-10-05): three states - off, suppressed, list - and the AI's two
sentences held to "no number" by the contract whoever wrote the file.
contracts/forecast_actions.py; docs/CONTRACTS.md section 8."""

from typing import Any

import pytest
from pydantic import ValidationError

from contracts.forecast import ForecastContract
from tests.contracts.test_forecast import forecast_payload


def _action(claim: str = "K1", hypothesis_id: str = "B1", **changes: str) -> dict[str, Any]:
    return {"claim": claim, "hypothesis_id": hypothesis_id, "fact": "Customers ordered more often.",
            "action": "Keep the reminder emails going to regular customers.",
            "why": "Regular customers ordering again moved sales.", "watch": "Next month, check: orders per customer."
            } | changes


def _forecast(status: str | None, actions: list | None = None, model: str | None = None,
              version: str = "2.1") -> dict[str, Any]:
    return forecast_payload() | {"schema_version": version, "actions_status": status, "actions": actions,
                                 "actions_model": model}


def test_the_three_states_are_accepted() -> None:
    for payload in (_forecast("off"), _forecast("suppressed"), _forecast("list", []),
                    _forecast("list", [_action()], "claude-sonnet-5")):
        ForecastContract.model_validate(payload)


def test_a_forecast_from_before_2_1_carries_no_actions() -> None:
    ForecastContract.model_validate(forecast_payload() | {"schema_version": "2.0"})
    with pytest.raises(ValidationError, match="2.1"):
        ForecastContract.model_validate(_forecast("off", version="2.0"))


def test_a_2_1_forecast_says_its_state() -> None:
    with pytest.raises(ValidationError, match="actions_status"):
        ForecastContract.model_validate(_forecast(None))


@pytest.mark.parametrize(("status", "actions"), [("off", []), ("suppressed", [_action()]), ("list", None)])
def test_actions_are_listed_exactly_when_the_state_is_list(status: str, actions: list | None) -> None:
    with pytest.raises(ValidationError, match="list"):
        ForecastContract.model_validate(_forecast(status, actions, "claude-sonnet-5" if actions else None))


@pytest.mark.parametrize("text", ["Raise prices by 5 percent.", "Aim for ２ more orders.", "Offer a 10% discount.",
                                  "Offer a £ voucher.", "", " ".join(["word"] * 31)])
def test_the_ais_sentence_holds_no_number_no_sign_and_at_most_30_words(text: str) -> None:
    for field in ("action", "why"):
        with pytest.raises(ValidationError, match="refused"):
            ForecastContract.model_validate(_forecast("list", [_action(**{field: text})], "claude-sonnet-5"))


def test_the_claims_are_k1_k2_k3_in_order_each_on_its_own_hypothesis() -> None:
    for actions in ([_action("K2")], [_action("K1"), _action("K1", "B2")], [_action("K1"), _action("K2", "B1")],
                    [_action("K1", "B1"), _action("K2", "B2"), _action("K3", "T1"), _action("K3", "P2")]):
        with pytest.raises(ValidationError):
            ForecastContract.model_validate(_forecast("list", actions, "claude-sonnet-5"))


def test_listed_actions_name_their_model_and_no_other_state_does() -> None:
    with pytest.raises(ValidationError, match="model"):
        ForecastContract.model_validate(_forecast("list", [_action()], None))
    with pytest.raises(ValidationError, match="model"):
        ForecastContract.model_validate(_forecast("list", [], "claude-sonnet-5"))
    with pytest.raises(ValidationError, match="model"):
        ForecastContract.model_validate(_forecast("off", None, "claude-sonnet-5"))
