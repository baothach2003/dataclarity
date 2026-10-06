"""Step 4 as option (d), its review (cycle 1; docs/REPORT_REDESIGN.md section
12): each finding reproduced as a test before its fix."""

import copy
import re

import pytest

from contracts.diagnosis import DiagnosisContract
from contracts.metrics import MetricsContract
from stages.predict.catalog import ACTIONS
from stages.predict.claims import MOVED_OUT, NOT_A_LEVER, candidates, select_claims
from tests.stages.report.real_runs import files


def _texts(kind: str) -> list[str]:
    return [text for (k, _), pair in ACTIONS.items() if k == kind for text in pair]


# --- 1-3: a sentence never reads the figure as a behaviour it does not measure -----------------------------------


# --- 1-4: B1, B2 and P4 moved out of the claims (Thach's stop rule) ---------------------------------------------
# The scoped review of cycle 1's fixes still found their sentences untrue on
# common shapes (new or lapsed customers; a file with no order id; deduction
# lines nobody confirmed): the kinds leave the claims.


@pytest.mark.parametrize("kind", ["B1", "B2", "P4"])
def test_a_moved_out_kind_has_no_catalog_entry_and_is_never_a_claim(kind: str) -> None:
    assert kind in MOVED_OUT and not [k for k, _ in ACTIONS if k == kind]
    data = files("demo_classed")
    diagnosis = copy.deepcopy(data["diagnosis.json"])
    diagnosis["headline"] |= {"rule": 6, "hypothesis_id": kind, "lens": None, "named": [kind], "hedge": None}
    named = next(h for h in diagnosis["hypotheses"] if h["id"] == kind)
    named |= {"verdict": "supported", "against_the_change": False}
    claims = select_claims(MetricsContract.model_validate(data["metrics.json"]),
                           DiagnosisContract.model_validate(diagnosis), None)

    assert kind not in [c.hypothesis_id for c in claims]


def test_kaggles_report_lists_no_b1_or_b2_action() -> None:
    from stages.predict.assemble import predict
    from tests.stages.report.real_runs import build_real

    data = files("kaggle")
    forecast = predict(MetricsContract.model_validate(data["metrics.json"]),
                       DiagnosisContract.model_validate(data["diagnosis.json"])).contract.model_dump(mode="json")
    items = build_real("kaggle", forecast=forecast).front.next_steps.items

    assert [item.rests_on.split(":")[0] for item in items] == ["Inside the chart's average price per item (-2,646.13)"]


# --- 5: R3 may be several products ---------------------------------------------------------------------------------


def test_r3_never_says_the_best_selling_product_as_if_there_were_one() -> None:
    for text in _texts("R3"):
        assert "the best-selling product" not in text and "Its sales" not in text, text


def test_r3s_fact_line_says_at_least_one() -> None:
    data = files("kaggle")
    diagnosis = copy.deepcopy(data["diagnosis.json"])
    diagnosis["headline"] |= {"rule": 6, "hypothesis_id": "R3", "lens": None, "named": ["R3"], "hedge": None}
    r3 = next(h for h in diagnosis["hypotheses"] if h["id"] == "R3")
    r3 |= {"verdict": "supported", "contribution": -900.0, "share": 0.5, "against_the_change": False}
    claims = select_claims(MetricsContract.model_validate(data["metrics.json"]),
                           DiagnosisContract.model_validate(diagnosis), None)
    claim = next(c for c in claims if c.hypothesis_id == "R3")

    assert claim.fact.startswith("At least one best-selling product stopped selling")
    assert claim.watch == ('Next month, check: whether the products in the technical section\'s row "A top product '
                           'may have run out of stock" sell again.')  # Q61, by its label


# --- 6: R1 as stage 3 writes it (no amount) is a claim ---------------------------------------------------------------


def test_r1_as_stage_3_writes_it_is_a_claim_in_the_changes_direction() -> None:
    data = files("kaggle")
    diagnosis = copy.deepcopy(data["diagnosis.json"])
    diagnosis["headline"] |= {"rule": 6, "hypothesis_id": "R1", "lens": None, "named": ["R1"], "hedge": None}
    r1 = next(h for h in diagnosis["hypotheses"] if h["id"] == "R1")
    assert r1["contribution"] is None  # stage 3 writes R1 with no amount
    r1["verdict"] = "supported"
    claims = select_claims(MetricsContract.model_validate(data["metrics.json"]),
                           DiagnosisContract.model_validate(diagnosis), None)

    assert claims[0].hypothesis_id == "R1" and claims[0].direction == "up"  # Kaggle's sales rose
    # The Kaggle fixture is 18.6: no member, so the row is named (Q62).
    assert claims[0].action == ACTIONS[("R1", "up")][0].format(
        member='the product named in the technical section\'s row "The change is concentrated in one product or '
               'category"')


# --- 7: the excluded kinds are never candidates (not only absent from the catalog) ---------------------------------


def test_no_excluded_kind_is_ever_a_candidate() -> None:
    data = files("kaggle")
    diagnosis = copy.deepcopy(data["diagnosis.json"])
    for hypothesis in diagnosis["hypotheses"]:
        hypothesis |= {"verdict": "supported", "against_the_change": False}
    found = {h.id for h in candidates(MetricsContract.model_validate(data["metrics.json"]),
                                      DiagnosisContract.model_validate(diagnosis))}

    assert not found & NOT_A_LEVER
    assert NOT_A_LEVER == {"D1", "D2", "D3", "T1", "T2", "T3", "C4", "R2", "B1", "B2", "P4"}
