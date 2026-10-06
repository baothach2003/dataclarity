"""The report redesign, step 4 (docs/REPORT_REDESIGN.md 4.1-4.3; Thach Q10,
Q11, Q52, Q54): code selects at most three claims and writes each one's fact
- the checklist's own sentence, one copy (shared/claim_lines) - and what to
watch next month, by kind, from the field the claim rests on. B1, B2 and P4
are no claims since step 4's scoped review (claims.MOVED_OUT, Thach's stop
rule): on Thach's Kaggle run only P2 remains (pulled the other way). Written
before the code."""

import copy

import pytest

from contracts.diagnosis import HEDGE_SENTENCES, DiagnosisContract
from contracts.metrics import MetricsContract
from stages.predict.claims import MOVED_OUT, Claim, select_claims
from tests.stages.report.real_runs import build_real, files


def _claims(run: str = "kaggle", code: str | None = None, *, metrics: dict | None = None,
            diagnosis: dict | None = None) -> list[Claim]:
    data = files(run)
    return select_claims(MetricsContract.model_validate(metrics or data["metrics.json"]),
                         DiagnosisContract.model_validate(diagnosis or data["diagnosis.json"]), code)


def test_kaggles_one_claim_after_b1_and_b2_moved_out() -> None:
    claims = _claims()

    assert [(c.id, c.hypothesis_id, c.direction) for c in claims] == [("K1", "P2", "down")]
    assert MOVED_OUT == {"B1", "B2", "P4"}


def test_each_fact_is_the_checklists_own_sentence() -> None:
    claims = _claims()
    lines = [line for group in build_real("kaggle").front.checklist for line in group.lines]

    assert claims[0].fact.startswith("Inside the chart's average price per item (-2,646.13): customers chose cheaper")
    assert all(claim.fact in lines for claim in claims)


def test_what_to_watch_reads_the_value_the_claim_rests_on() -> None:
    assert [c.watch for c in _claims()] == [
        "Next month, check: the average price per item (23.25 this month; 24.70 the month before)."]


def test_money_in_a_claim_carries_the_files_code() -> None:
    (claim,) = _claims(code="GBP")

    assert "about GBP -1,479.65" in claim.fact
    assert claim.watch == ("Next month, check: the average price per item (GBP 23.25 this month; GBP 24.70 "
                           "the month before).")


def test_the_subject_is_the_checks_plain_name() -> None:
    assert [c.subject for c in _claims()] == ["a shift to cheaper or pricier products"]


@pytest.mark.parametrize("run", ["demo_classed", "demo_unanswered"])
def test_no_claim_where_no_cause_is_named(run: str) -> None:
    # Rule 7 on both demo runs (Q10).
    assert _claims(run) == []


@pytest.mark.parametrize("rule", [1, 2, 3, 4, 7])
def test_no_claim_under_rules_other_than_5_and_6(rule: int) -> None:
    diagnosis = copy.deepcopy(files("kaggle")["diagnosis.json"])
    diagnosis["headline"] |= {"rule": rule, "hypothesis_id": None, "lens": None, "named": None,
                              "hedge": "plain" if rule == 4 else None,
                              "message": "m " + HEDGE_SENTENCES["plain"] if rule == 4 else "m"}

    assert _claims(diagnosis=diagnosis) == []


def test_no_claim_when_the_previous_month_is_incomplete() -> None:
    # The period alone changed (a copy: the rest of the file is not what is tested).
    data = files("kaggle")
    metrics = MetricsContract.model_validate(data["metrics.json"])
    metrics = metrics.model_copy(update={"period": metrics.period.model_copy(update={"previous_complete": False})})

    assert select_claims(metrics, DiagnosisContract.model_validate(data["diagnosis.json"]), None) == []


def test_no_excluded_kind_is_ever_a_claim_and_at_most_three() -> None:
    diagnosis = copy.deepcopy(files("demo_classed")["diagnosis.json"])
    diagnosis["headline"] |= {"rule": 6, "hypothesis_id": "C3", "lens": None, "named": ["C3"], "hedge": None}
    for hypothesis in diagnosis["hypotheses"]:
        if hypothesis["id"] in ("D1", "T1", "T2", "B1", "B2", "P4", "P1", "P5", "R3"):
            hypothesis |= {"verdict": "supported", "against_the_change": False, "contribution": 99_999.0}
    claims = _claims("demo_classed", diagnosis=diagnosis)

    assert len(claims) == 3 and claims[0].hypothesis_id == "C3"  # the headline's first, whatever the amounts
    assert not {c.hypothesis_id for c in claims} & {"D1", "D2", "D3", "T1", "T2", "T3", "C4", "R2", "B1", "B2", "P4"}
    assert [c.hypothesis_id for c in claims[1:]] == ["P1", "P5"]  # then by amount, the catalog's order on a tie


def test_against_the_change_only_from_the_supported_bar() -> None:
    diagnosis = copy.deepcopy(files("kaggle")["diagnosis.json"])
    next(h for h in diagnosis["hypotheses"] if h["id"] == "P2")["share"] = -0.19  # under SUPPORTED_MIN_SHARE

    assert "P2" not in [c.hypothesis_id for c in _claims(diagnosis=diagnosis)]


def test_a_tie_names_its_causes_first() -> None:
    diagnosis = copy.deepcopy(files("demo_classed")["diagnosis.json"])
    diagnosis["schema_version"] = "18.7"
    diagnosis["headline"] |= {"rule": 6, "hypothesis_id": None, "lens": None, "named": ["P3", "C3"],
                              "offsetting": False}

    assert [c.hypothesis_id for c in _claims("demo_classed", diagnosis=diagnosis)][:2] == ["P3", "C3"]


def test_a_file_with_no_order_id_never_says_order_in_a_claim() -> None:
    metrics = copy.deepcopy(files("kaggle")["metrics.json"])
    metrics["core"]["orders_basis"] = "lines"
    claims = _claims(metrics=metrics)

    assert claims and not any("order" in c.fact + c.watch + c.subject + c.action + c.why for c in claims)
