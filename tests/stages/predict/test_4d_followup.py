"""Step 4's follow-up (Thach, Q61, Q62): R3's action names the technical
section's own label for its row; R1's action names stage 3's top member
(diagnosis 18.8 `hypotheses[].member`). Written before the code."""

import copy

from contracts.diagnosis import DiagnosisContract
from contracts.metrics import MetricsContract
from stages.predict.claims import select_claims
from tests.stages.report.real_runs import files


def _named(kind: str, **changes: object) -> list:
    data = files("kaggle")
    diagnosis = copy.deepcopy(data["diagnosis.json"])
    diagnosis["schema_version"] = "18.8"
    diagnosis["headline"] |= {"rule": 6, "hypothesis_id": kind, "lens": None, "named": [kind], "hedge": None,
                              "offsetting": False}
    hypothesis = next(h for h in diagnosis["hypotheses"] if h["id"] == kind)
    hypothesis |= {"verdict": "supported", "against_the_change": False} | changes
    if hypothesis.get("member") is not None:
        hypothesis["evidence"]["top_member"] = hypothesis["member"]  # the contract: the member is the top member
    return select_claims(MetricsContract.model_validate(data["metrics.json"]),
                         DiagnosisContract.model_validate(diagnosis), None)


def test_r3_names_the_technical_sections_row() -> None:
    claim = next(c for c in _named("R3", contribution=-900.0, share=0.5) if c.hypothesis_id == "R3")
    label = next(h for h in files("kaggle")["diagnosis.json"]["hypotheses"] if h["id"] == "R3")["statement"]

    # By its label alone: "R3" is a digit no action may hold (the scoped review, stop rule).
    assert claim.action == ("Check the shelf and the stock records for the products in the technical section's "
                            f'row "{label}".')
    assert claim.watch == f'Next month, check: whether the products in the technical section\'s row "{label}" sell ' \
                          "again."
    assert "stockout check" not in claim.action + claim.watch


def test_r1_names_stage_3s_top_member() -> None:
    claim = next(c for c in _named("R1", member="Blue Mug") if c.hypothesis_id == "R1")

    assert claim.action == "Look at Blue Mug and see what changed there."
    assert claim.why == "The change was concentrated in one product, so that is where to look first."


def test_r1_without_a_member_points_to_its_row() -> None:
    # A diagnosis before 18.8: the front says less - the row, never a guessed name.
    claim = next(c for c in _named("R1") if c.hypothesis_id == "R1")

    assert claim.action == ('Look at the product named in the technical section\'s row "The change is concentrated '
                            'in one product or category" and see what changed there.')
