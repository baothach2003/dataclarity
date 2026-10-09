"""Thach, Q65 (2026-10-09): a product name in R1's action may hold digits ONLY
when it is inserted verbatim from stage 3's field, in quotes. The digit ban
stands against invented numbers; a name copied from the contract is data.
forecast.json 2.2 (additive): `actions[].name`, the name the action quotes,
R1 only. Written before the code."""

from typing import Any

import pytest
from pydantic import ValidationError

from contracts.forecast import ForecastContract
from tests.contracts.test_forecast_actions import _action, _forecast

R1 = "Look at \"SKU-1042\" and see what changed there."


def _named(action: str = R1, name: str | None = "SKU-1042", hypothesis_id: str = "R1",
           version: str = "2.2") -> dict[str, Any]:
    return _forecast("list", [_action(hypothesis_id=hypothesis_id, action=action) | {"name": name}], version=version)


def test_a_name_from_the_field_with_digits_passes_in_quotes() -> None:
    forecast = ForecastContract.model_validate(_named())

    assert forecast.actions is not None and forecast.actions[0].name == "SKU-1042"


def test_the_same_sentence_without_the_name_is_refused() -> None:
    with pytest.raises(ValidationError, match="digit"):
        ForecastContract.model_validate(_named(name=None))


@pytest.mark.parametrize("action", [
    "Look at \"SKU-1042\" and see what changed in 2 days.",  # a digit outside the name
    "Look at \"SKU-1042\" and see what changed there, about 10% more.",  # a sign outside the name
    "Look at SKU-1042 and see what changed there.",  # the name not quoted
    "Look at \"SKU-1042\" and \"SKU-1042\" and see what changed there.",  # quoted twice: one name, one place
])
def test_anything_else_in_the_sentence_is_still_held_to_no_number(action: str) -> None:
    with pytest.raises(ValidationError):
        ForecastContract.model_validate(_named(action=action))


def test_a_name_with_a_sign_is_still_refused() -> None:
    # Thach allowed digits only: a percent or a currency sign in the name stays refused.
    with pytest.raises(ValidationError, match="sign"):
        ForecastContract.model_validate(_named(action="Look at \"Mug 50%\" and see what changed there.",
                                               name="Mug 50%"))


def test_only_r1_names_a_product_and_only_from_2_2() -> None:
    with pytest.raises(ValidationError, match="R1"):
        ForecastContract.model_validate(_named(hypothesis_id="B1"))
    with pytest.raises(ValidationError, match="2.2"):
        ForecastContract.model_validate(_named(version="2.1"))
    with pytest.raises(ValidationError):
        ForecastContract.model_validate(_named(name="   ", action="Look at \"   \" and see what changed there."))


def test_a_name_holding_a_quote_mark_is_refused() -> None:
    # Its quotes could not be told from the sentence's own.
    with pytest.raises(ValidationError, match="no name"):
        ForecastContract.model_validate(_named(action='Look at "12" Mug" and see what changed there.', name='12" Mug'))
