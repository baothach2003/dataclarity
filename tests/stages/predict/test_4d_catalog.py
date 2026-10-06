"""The report redesign, step 4 as Thach's option (d) (docs/REPORT_REDESIGN.md
4.3): every suggested action and its why are code-written, picked from the
catalog by the claim's kind and the direction its own figure moved. Thach's
tests: every catalog sentence passes front_word_problems; "visits" and
"orders" never on a file with no order id (no catalog sentence holds them at
all); direction words always match the figure's own direction (a refund
that fell is never "rose"); no digit in a catalog sentence. Written before
the code."""

import copy
import re

import pytest

from contracts.diagnosis import DiagnosisContract
from contracts.forecast_actions import ai_text_problems, front_word_problems
from contracts.metrics import MetricsContract
from stages.predict.catalog import ACTIONS
from stages.predict.claims import select_claims
from tests.stages.report.real_runs import files

UP = re.compile(r"\b(?:rose|risen|grew|grown|increased|climbed|went up|more|higher|bigger|larger)\b", re.IGNORECASE)
DOWN = re.compile(r"\b(?:fell|fallen|dropped|declined|decreased|went down|fewer|less|lower|smaller)\b",
                  re.IGNORECASE)
# B1, B2 and P4 moved out of the claims by step 4's scoped review (Thach's stop rule).
LEVERS = ("C1", "C2", "C3", "P1", "P2", "P3", "P5")


def _sentences() -> list[tuple[str, str, str]]:
    return [(f"{kind} {direction}", field, text) for (kind, direction), pair in ACTIONS.items()
            for field, text in zip(("action", "why"), pair, strict=True)]


def test_each_lever_has_an_entry_each_way_and_r1_r3_one() -> None:
    assert {(k, d) for k, d in ACTIONS if k in LEVERS} == {(k, d) for k in LEVERS for d in ("up", "down")}
    assert {k for k, _ in ACTIONS} == {*LEVERS, "R1", "R3"}  # never D, T, C4, R2 (Q52), B1, B2 or P4


@pytest.mark.parametrize("where, field, text", _sentences())
def test_every_sentence_passes_the_front_words_and_holds_no_number(where: str, field: str, text: str) -> None:
    assert front_word_problems(text) == [], where
    assert ai_text_problems(text) == [], where  # no digit, sign or more than thirty words
    assert not any(char.isdigit() for char in text)


@pytest.mark.parametrize("where, field, text", _sentences())
def test_no_sentence_says_order_visit_or_basket(where: str, field: str, text: str) -> None:
    # True on a file with no order id too (the orders-basis rule).
    assert not re.search(r"\b(?:orders?|ordered|ordering|visits?|visited|visiting|baskets?)\b", text, re.IGNORECASE)


@pytest.mark.parametrize("where, field, text", _sentences())
def test_direction_words_match_the_entrys_direction(where: str, field: str, text: str) -> None:
    kind, direction = where.split()
    if direction == "up":
        assert not DOWN.search(text), (where, text)
    if direction == "down":
        assert not UP.search(text), (where, text)


def _claims(metrics: dict, diagnosis: dict, code: str | None = None):
    return select_claims(MetricsContract.model_validate(metrics), DiagnosisContract.model_validate(diagnosis), code)


def _named(run: str, hypothesis_id: str) -> tuple[dict, dict]:
    """The run's files with the headline naming one hypothesis (rule 6)."""
    data = files(run)
    diagnosis = copy.deepcopy(data["diagnosis.json"])
    diagnosis["headline"] |= {"rule": 6, "hypothesis_id": hypothesis_id, "lens": None, "named": [hypothesis_id],
                              "hedge": None}
    return copy.deepcopy(data["metrics.json"]), diagnosis


def test_a_refund_that_fell_is_never_said_to_have_risen() -> None:
    # demo_classed: refunds 41,074.29 -> 13,951.29 - P3 adds to sales ("up" for sales), its figure fell.
    metrics, diagnosis = _named("demo_classed", "P3")
    (claim,) = [c for c in _claims(metrics, diagnosis) if c.hypothesis_id == "P3"]

    assert claim.direction == "down"
    assert (claim.action, claim.why) == ACTIONS[("P3", "down")]
    assert "fell" in claim.fact and "fell" in claim.why and not UP.search(claim.action + " " + claim.why)


def test_kaggles_actions_by_kind_and_direction() -> None:
    claims = _claims(files("kaggle")["metrics.json"], files("kaggle")["diagnosis.json"])

    assert [(c.id, c.hypothesis_id, c.direction) for c in claims] == [("K1", "P2", "down")]
    assert claims[0].action == "Show a pricier alternative next to the cheaper products customers chose."
    assert claims[0].why == ("Customers chose cheaper products among those sold in both months; offering a step up "
                             "may win some of them back.")


def test_a_lost_customer_term_that_is_no_loss_has_no_entry_and_is_dropped() -> None:
    metrics, diagnosis = _named("demo_classed", "C2")
    diagnosis["tree"]["customers"]["lapsed"] = 500.0  # positive: no loss to word

    assert "C2" not in [c.hypothesis_id for c in _claims(metrics, diagnosis)]


def test_r2_is_never_a_claim() -> None:
    data = files("kaggle")
    diagnosis = copy.deepcopy(data["diagnosis.json"])
    next(h for h in diagnosis["hypotheses"] if h["id"] == "P2")["share"] = -0.19  # R2 would be next in line

    assert "R2" not in [c.hypothesis_id for c in _claims(data["metrics.json"], diagnosis)]


def test_r3_is_worded_with_stage_3s_own_words() -> None:
    metrics, diagnosis = _named("kaggle", "R3")
    r3 = next(h for h in diagnosis["hypotheses"] if h["id"] == "R3")
    r3 |= {"verdict": "supported", "contribution": -900.0, "share": 0.5, "against_the_change": False}
    (claim,) = [c for c in _claims(metrics, diagnosis) if c.hypothesis_id == "R3"]

    assert claim.fact == ("At least one best-selling product stopped selling - consistent with a stockout, verify on "
                          "the shelf - worth about -900.00.")
    assert claim.why == "Their sales stopped in a way consistent with a stockout - verify on the shelf."
