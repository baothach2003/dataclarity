"""diagnosis.json 18.8 (the report redesign, Thach Q62): `hypotheses[].member`,
the one product a check points to - R1's top member, the name as the file
writes it - so a reader names it without reading a hypothesis's evidence
keys (CONTRACTS 11). Additive: no verdict, statement or evidence changes.
Written before the code."""

import copy

import pytest
from pydantic import ValidationError

from contracts.diagnosis import DiagnosisContract
from stages.diagnose.assemble import SCHEMA_VERSION, diagnose
from tests.stages.diagnose.diagnose_fixtures import daily_rows, run_data
from tests.stages.report.real_runs import files


def test_r1_names_its_top_member_and_no_other_check_names_one() -> None:
    from datetime import date

    rows = daily_rows(date(2010, 1, 1), date(2011, 3, 31), products=3)
    found = diagnose(run_data(rows))
    by_id = {h.id: h for h in found.hypotheses}

    assert SCHEMA_VERSION == "18.8"
    assert by_id["R1"].member == by_id["R1"].evidence["top_member"]
    assert by_id["R1"].member is not None
    assert all(h.member is None for h in found.hypotheses if h.id != "R1")


def _payload(version: str = "18.8") -> dict:
    payload = copy.deepcopy(files("kaggle")["diagnosis.json"])
    payload["schema_version"] = version
    payload["headline"]["offsetting"] = False
    return payload


def test_an_18_8_file_carries_r1s_member_and_an_earlier_one_cannot() -> None:
    payload = _payload()
    r1 = next(h for h in payload["hypotheses"] if h["id"] == "R1")
    r1["member"] = r1["evidence"]["top_member"]
    DiagnosisContract.model_validate(payload)

    earlier = _payload("18.7")
    next(h for h in earlier["hypotheses"] if h["id"] == "R1")["member"] = "X"
    with pytest.raises(ValidationError, match="member"):
        DiagnosisContract.model_validate(earlier)

    other = copy.deepcopy(payload)
    next(h for h in other["hypotheses"] if h["id"] == "B1")["member"] = "X"
    with pytest.raises(ValidationError, match="member"):
        DiagnosisContract.model_validate(other)


@pytest.mark.parametrize(("member", "top"), [("Product 999", "Product 029"), ("   ", "   "), ("Product 029", None)])
def test_r1s_member_is_its_top_member_and_a_name(member: str, top: str | None) -> None:
    # The scoped review: a member unlike R1's evidence, a blank one, or one beside no top member passed.
    payload = _payload()
    r1 = next(h for h in payload["hypotheses"] if h["id"] == "R1")
    r1["member"], r1["evidence"]["top_member"] = member, top

    with pytest.raises(ValidationError, match="member"):
        DiagnosisContract.model_validate(payload)
