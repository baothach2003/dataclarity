"""diagnosis.json 18.6's headline.named (the report redesign, Thach Q33): the
hypotheses behind a rule 5 or rule 6 headline, in the order its message names
them, so stage 5 words sentence C from codes, never from the message. Additive:
no rule changes - the same headlines as before, the ids written beside them."""

import pytest
from pydantic import ValidationError

from contracts.diagnosis import Headline
from tests.stages.diagnose.test_2en_headline import _headline, _moved


def test_rule_6_names_its_one_cause() -> None:
    headline = _headline(_moved(1_000.0, 800.0), B1=("supported", -180.0), P3=("supported", -100.0))

    assert (headline.rule, headline.hypothesis_id, headline.named) == (6, "B1", ["B1"])


def test_rule_6_names_every_cause_of_an_exact_tie() -> None:
    headline = _headline(_moved(1_000.0, 800.0), B1=("supported", -180.0), P5=("supported", -180.0))

    assert (headline.rule, headline.hypothesis_id) == (6, None)
    assert sorted(headline.named) == ["B1", "P5"]


def test_rule_5_names_its_context_causes_in_the_messages_order() -> None:
    headline = _headline(_moved(1_000.0, 800.0), T1=("supported", -180.0), T2=("supported", -220.0))

    assert headline.rule == 5 and headline.hypothesis_id is None
    assert set(headline.named) == {"T1", "T2"}
    first, second = ("the calendar", "the same months a year earlier")
    order = ["T1", "T2"] if headline.message.index(first) < headline.message.index(second) else ["T2", "T1"]
    assert headline.named == order


def test_rule_5_naming_the_calendar_alone_names_t1() -> None:
    headline = _headline(_moved(1_000.0, 800.0), T1=("supported", -190.0))

    assert (headline.rule, headline.named) == (5, ["T1"])


def test_the_offsetting_case_names_the_largest_movement_each_way() -> None:
    headline = _headline(_moved(1_000.0, 800.0), P1=("supported", -600.0), P2=("ruled_out", 380.0))

    assert (headline.rule, headline.hypothesis_id, headline.named) == (6, None, ["P1", "P2"])


def test_rule_7_names_nothing() -> None:
    headline = _headline(_moved(1_000.0, 800.0), B1=("partial", -20.0))

    assert (headline.rule, headline.named) == (7, None)


@pytest.mark.parametrize(("rule", "hypothesis_id", "named"), [
    (7, None, ["B1"]), (4, None, ["B1"]), (6, "B1", ["B2"]), (6, None, []), (5, None, ["T1", "T1"])])
def test_the_contract_holds_named_to_its_rule(rule: int, hypothesis_id: str | None, named: list[str]) -> None:
    with pytest.raises(ValidationError, match="named"):
        Headline(rule=rule, hypothesis_id=hypothesis_id, lens=None, message="m", named=named)


def test_an_18_6_file_names_rule_5s_hypotheses_and_an_earlier_one_cannot() -> None:
    import copy

    from contracts.diagnosis import DiagnosisContract
    from tests.stages.report.real_runs import files

    payload = copy.deepcopy(files("kaggle")["diagnosis.json"])  # an 18.5 file, the Kaggle run's
    headline = payload["headline"] | {"rule": 5, "hypothesis_id": None, "lens": None}
    for version, named, refused in (("18.6", None, True), ("18.6", ["T1"], False), ("18.5", ["T1"], True),
                                    ("18.6", ["X9"], True)):
        candidate = payload | {"schema_version": version, "headline": headline | {"named": named}}
        if refused:
            with pytest.raises(ValidationError, match="named"):
                DiagnosisContract.model_validate(candidate)
        else:
            DiagnosisContract.model_validate(candidate)
