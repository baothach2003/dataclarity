"""Thach, Q70 (2026-10-09): R1's and R3's sentences name the check's row as
the page and report.html name their technical part, "Technical details" -
never "the technical section". Written before the fix."""

import copy

from contracts.diagnosis import DiagnosisContract
from contracts.metrics import MetricsContract
from stages.predict.claims import select_claims
from tests.stages.report.real_runs import files


def _claim(kind: str, **changes: object):  # noqa: ANN202 - a Claim, private to stage 4's claims module
    data = files("kaggle")
    diagnosis = copy.deepcopy(data["diagnosis.json"])
    diagnosis["schema_version"] = "18.8"
    diagnosis["headline"] |= {"rule": 6, "hypothesis_id": kind, "lens": None, "named": [kind], "hedge": None,
                              "offsetting": False}
    hypothesis = next(h for h in diagnosis["hypotheses"] if h["id"] == kind)
    hypothesis |= {"verdict": "supported", "against_the_change": False} | changes
    claims = select_claims(MetricsContract.model_validate(data["metrics.json"]),
                           DiagnosisContract.model_validate(diagnosis), None)
    return next(c for c in claims if c.hypothesis_id == kind)


def test_r3_names_its_row_in_technical_details() -> None:
    claim = _claim("R3", contribution=-900.0, share=0.5)
    label = next(h for h in files("kaggle")["diagnosis.json"]["hypotheses"] if h["id"] == "R3")["statement"]

    assert claim.action == f'Check the shelf and the stock records for the products in the row "{label}" in ' \
                           "Technical details."
    assert claim.watch == f'Next month, check: whether the products in the row "{label}" in Technical details ' \
                          "sell again."


def test_r1_without_a_member_names_its_row_in_technical_details() -> None:
    claim = _claim("R1")

    assert claim.action == ('Look at the product named in the row "The change is concentrated in one product or '
                            'category" in Technical details and see what changed there.')
    assert "technical section" not in claim.action + claim.why + claim.watch
