"""The scoped review of Q56-Q62 (2026-10-06), its fixes to R1's and R3's
actions: a name the actions contract cannot carry (a digit, a sign) or one
Review only suggested (CLAUDE.md 3.3a) is not printed in R1's action; R3's
row is named by its label alone - predict never fails on them (it did: "row
R3", a code like SKU-1042)."""

import copy

import pytest

from contracts.diagnosis import DiagnosisContract
from contracts.metrics import MetricsContract
from stages.predict.assemble import predict
from tests.stages.report.real_runs import files


def _diagnosis(kind: str, **changes: object) -> dict:
    diagnosis = copy.deepcopy(files("kaggle")["diagnosis.json"])
    diagnosis["schema_version"] = "18.8"
    diagnosis["headline"] |= {"rule": 6, "hypothesis_id": kind, "lens": None, "named": [kind], "hedge": None,
                              "offsetting": False}
    hypothesis = next(h for h in diagnosis["hypotheses"] if h["id"] == kind)
    hypothesis |= {"verdict": "supported", "against_the_change": False} | changes
    if hypothesis.get("member") is not None:
        hypothesis["evidence"]["top_member"] = hypothesis["member"]  # the contract: the member is the top member
    return diagnosis


def _actions(diagnosis: dict, metrics: dict | None = None) -> list:
    data = files("kaggle")
    contract = predict(MetricsContract.model_validate(metrics or data["metrics.json"]),
                       DiagnosisContract.model_validate(diagnosis)).contract
    return contract.actions or []


@pytest.mark.parametrize("member", ["SKU-1042", "SET OF 3 MUGS"])
def test_a_name_with_digits_is_printed_in_quotes_from_the_field(member: str) -> None:
    # Thach, Q65: the name copied verbatim from stage 3's field is data, not an invented number.
    diagnosis = _diagnosis("R1", member=member)
    r1 = next(a for a in _actions(diagnosis) if a.hypothesis_id == "R1")

    assert r1.action == f'Look at "{member}" and see what changed there.'
    assert r1.name == member


@pytest.mark.parametrize("member", ["Mug 50%", "Mug £5"])
def test_a_name_the_contract_cannot_carry_is_not_printed_and_predict_never_fails(member: str) -> None:
    # Q65 allows digits only: a sign in the name still points the action to the row.
    diagnosis = _diagnosis("R1", member=member)
    r1 = next(a for a in _actions(diagnosis) if a.hypothesis_id == "R1")

    assert member not in r1.action and r1.name is None
    assert r1.action == ('Look at the product named in the technical section\'s row "The change is concentrated in '
                         'one product or category" and see what changed there.')


def test_a_plain_name_is_printed() -> None:
    r1 = next(a for a in _actions(_diagnosis("R1", member="Blue Mug")) if a.hypothesis_id == "R1")

    assert r1.action == 'Look at "Blue Mug" and see what changed there.'  # Q65: the name in quotes
    assert r1.name == "Blue Mug"


def test_a_name_review_only_suggested_is_not_printed() -> None:
    # 3.3a: the appendix marks it "(suggested: charge, not confirmed)"; the action would call it a product.
    diagnosis = _diagnosis("R1", member="Postage")
    diagnosis["suggested_classes"] = {"Postage": "charge"}
    r1 = next(a for a in _actions(diagnosis) if a.hypothesis_id == "R1")

    assert "Postage" not in r1.action and r1.name is None


def test_r3s_row_is_named_by_its_label_and_predict_never_fails() -> None:
    diagnosis = _diagnosis("R3", contribution=-900.0, share=0.5)
    r3 = next(a for a in _actions(diagnosis) if a.hypothesis_id == "R3")

    assert r3.action == ('Check the shelf and the stock records for the products in the technical section\'s row '
                         '"A top product may have run out of stock".')
