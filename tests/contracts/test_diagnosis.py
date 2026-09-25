"""diagnosis.json against docs/CONTRACTS.md section 7.

Rewritten in session 3C together with `contracts/diagnosis.py`. The previous
version of this file pinned the pre-3A shape (a single `decomposition` block
and an `ai_findings` of headline/root_cause/ruled_out), which session 3A
deliberately left in place while it rewrote the specification. Those blocks no
longer exist, so the tests naming them could not survive; every rule that still
applies is still tested here, and the degraded-mode tests are unchanged in
substance.
"""

from typing import Any

import pytest
from pydantic import ValidationError

from contracts.diagnosis import DiagnosisContract, Lever, LeverFactor, LeverLevel, Signal


def diagnosis_payload() -> dict[str, Any]:
    # The example from docs/CONTRACTS.md section 7, with the arrays that the
    # documentation shows one element of filled in completely.
    return {
        "schema_version": "6.0",  # 2E-c: deductions; 2E-c2: the bridge's new; 2E-e: orders by basis; 2E-f: customers; 2E-g: products
        "generated_at": "2026-09-18T04:16:00Z",
        "model_used": "claude-sonnet-5",
        "frame": {
            "current": "2011-11", "previous": "2011-10",
            "year_ago_current": "2010-11", "year_ago_previous": "2010-10",
            "history_months": 23, "previous_leading_days_missing": 0,
            "history_start": "2009-12", "history_end": "2011-10",
        },
        "trust": {
            "verdict": "caution",
            "checks": [{"id": "D1", "status": "caution",
                        "evidence": {"zero_days_cur": 6, "excess_zero_days_cur": 5.2,
                                     "excess_zero_days_prev": 0.0,
                                     "estimated_revenue_gap": 18400.0,
                                     "estimated_revenue_gap_prev": 0.0,
                                     "sparse_history_months": [],
                                     "history_months_with_rows": 23,
                                     "learned_from_months": 22},
                        "message": "About 5 days in the current month have no sales beyond "
                                   "this store's normal closing pattern (missing data, or "
                                   "days the shop was closed), worth roughly 18,400 in "
                                   "revenue."}],
            "limitations": ["rows dropped in stage 1 cannot be assigned to a period"],
        },
        "calendar": {
            "method": "weekday_weights", "expected_cur": 1180000.0,
            "expected_prev": 1210000.0, "calendar_effect": -31900.0,
            "calendar_adjusted_change": -108100.0,
            "evidence": {"weights": {"mon": 31200.0, "sat": 52100.0}},
        },
        "signals": [{"series": "revenue", "mode": "level", "value_cur": 1150000.0,
                     "center": 1240000.0, "lower": 1090000.0, "upper": 1390000.0,
                     "signal": "within", "rule": None,
                     "limits_method": "median_moving_range"}],
        "tree": {
            "method": "shapley",
            "lever": {
                "level1": {
                    "formula": "customers*frequency*aov",
                    "factors": [
                        {"name": "customers", "value_prev": 905.0, "value_cur": 812.0,
                         "contribution": -102300.0},
                        {"name": "frequency", "value_prev": 2.15, "value_cur": 2.24,
                         "contribution": -21400.0},
                        {"name": "aov", "value_prev": 661.5, "value_cur": 631.9,
                         "contribution": -16300.0},
                    ],
                },
                "level2": {
                    "formula": "units_per_order*price_per_unit",
                    "factors": [
                        {"name": "units_per_order", "value_prev": 4.1, "value_cur": 3.9,
                         "contribution": -11200.0},
                        {"name": "price_per_unit", "value_prev": 161.3, "value_cur": 162.0,
                         "contribution": -5100.0},
                    ],
                },
                "gross_to_net": 1.04, "masked_shift_alert": False, "reasons": {},
            },
            "customers": {"new": 92000.0, "resurrected": 14000.0, "expansion": 61000.0,
                          "contraction": -88000.0, "lapsed": -219000.0,
                          "unattributed": 0.0, "previous_transition": None,
                          "evidence": {"new_customers": 148, "left_censored": False}},
            "returns": {"gross_prev": 1338000.0, "gross_cur": 1198000.0,
                        "returns_prev": 48000.0, "returns_cur": 48000.0,
                        "deductions_prev": 0.0, "deductions_cur": 0.0},
            "products": {"volume": -96000.0, "mix": -21000.0, "price": -8000.0,
                         "new_products": 12000.0, "discontinued_products": -27000.0},
        },
        "localization": {
            "dimensions": [{"name": "category",
                            "members": [{"name": "Home Decor", "rev_prev": 268000.0,
                                         "rev_cur": 210000.0, "delta": -58000.0,
                                         "share_of_change": 0.414}],
                            "other": {"name": "Other", "rev_prev": 31000.0,
                                      "rev_cur": 29500.0, "delta": -1500.0,
                                      "share_of_change": 0.011},
                            "new_members": [], "removed_members": []}],
            "mix_rate": {"metric": "aov", "mix": -24450.0, "rate": 3050.0},
            "breadth": {"declining_base_share": 0.74, "top_member_share": 0.41,
                        "classification": "broad"},
        },
        "hypotheses": [{"id": "P2", "family": "price_mix", "lens": "product",
                        "statement": "Sales mix shifted towards cheaper products",
                        "verdict": "supported", "contribution": -21000.0, "share": 0.21,
                        "evidence": {"mix_effect": -21000.0, "delta_gross": -100000.0},
                        "rule": "same sign and share >= 0.20"}],
        "not_testable": [{"id": "X1", "statement": "Marketing, promotions, discounts",
                          "reason": "no campaign data; discount columns are not canonical"}],
        "headline": {"rule": 6, "hypothesis_id": "P2", "lens": "product",
                     "message": "Most of the decline is consistent with a shift in "
                                "sales mix towards cheaper products."},
        "ai_findings": {
            "summary": "Revenue fell 10.9% this month...",
            "headline_explanation": "The mix effect accounts for 21% of the drop...",
            "hypothesis_notes": [{"id": "P2", "text": "Shoppers bought more of the cheaper lines..."}],
            "not_tested_note": "This data cannot test marketing, competitors, weather or footfall.",
        },
    }


def test_accepts_documented_example() -> None:
    diagnosis = DiagnosisContract.model_validate(diagnosis_payload())

    assert diagnosis.frame.current == "2011-11"
    assert diagnosis.trust.verdict == "caution"
    assert diagnosis.tree is not None
    assert [f.name for f in diagnosis.tree.lever.level1.factors] == [
        "customers", "frequency", "aov"]
    assert diagnosis.tree.customers is not None
    assert diagnosis.tree.customers.lapsed == -219000.0
    assert diagnosis.headline.rule == 6
    assert diagnosis.ai_findings is not None
    assert diagnosis.ai_findings.hypothesis_notes[0].id == "P2"


def test_rejects_missing_tree() -> None:
    payload = diagnosis_payload()
    del payload["tree"]

    with pytest.raises(ValidationError, match="tree"):
        DiagnosisContract.model_validate(payload)


def test_rejects_factor_missing_contribution() -> None:
    payload = diagnosis_payload()
    del payload["tree"]["lever"]["level1"]["factors"][0]["contribution"]

    with pytest.raises(ValidationError, match="contribution"):
        DiagnosisContract.model_validate(payload)


def test_rejects_a_level_whose_factors_do_not_match_its_formula() -> None:
    # A decomposition quietly missing a term still sums to something; it just
    # sums to the wrong thing, and every number built on it would be wrong.
    payload = diagnosis_payload()
    payload["tree"]["lever"]["level1"]["factors"].pop()

    with pytest.raises(ValidationError, match="requires factors"):
        DiagnosisContract.model_validate(payload)


def test_rejects_hypothesis_missing_evidence() -> None:
    payload = diagnosis_payload()
    del payload["hypotheses"][0]["evidence"]

    with pytest.raises(ValidationError, match="evidence"):
        DiagnosisContract.model_validate(payload)


def test_rejects_not_testable_entry_missing_reason() -> None:
    payload = diagnosis_payload()
    del payload["not_testable"][0]["reason"]

    with pytest.raises(ValidationError, match="reason"):
        DiagnosisContract.model_validate(payload)


def test_rejects_limitations_that_is_not_a_list() -> None:
    payload = diagnosis_payload()
    payload["trust"]["limitations"] = "rows were dropped"

    with pytest.raises(ValidationError, match="limitations"):
        DiagnosisContract.model_validate(payload)


def test_rejects_a_headline_rule_outside_the_catalog() -> None:
    payload = diagnosis_payload()
    payload["headline"]["rule"] = 8

    with pytest.raises(ValidationError, match="rule"):
        DiagnosisContract.model_validate(payload)


# --- the lever lens's null rules (session 3C) ---------------------------------


def test_rejects_a_missing_tree_reported_as_no_masked_shift() -> None:
    """Thach's call, 3C: `false` claims the check ran. A lens that could not be
    built must say null, or a downstream reader takes "could not tell" for
    "nothing to see"."""
    payload = diagnosis_payload()
    payload["tree"]["lever"].update(
        {"level1": None, "level2": None, "gross_to_net": None,
         "masked_shift_alert": False, "reasons": {"level1": "zero orders"}})

    with pytest.raises(ValidationError, match="masked_shift_alert is null whenever"):
        DiagnosisContract.model_validate(payload)


def test_rejects_a_null_level_with_no_reason_recorded() -> None:
    payload = diagnosis_payload()
    payload["tree"]["lever"].update(
        {"level1": None, "level2": None, "gross_to_net": None,
         "masked_shift_alert": None, "reasons": {}})

    with pytest.raises(ValidationError, match="carries no reason"):
        DiagnosisContract.model_validate(payload)


def test_rejects_level_2_without_level_1() -> None:
    # Level 2's contributions are expressed in level 1's units.
    payload = diagnosis_payload()
    payload["tree"]["lever"].update(
        {"level1": None, "gross_to_net": None, "masked_shift_alert": None,
         "reasons": {"level1": "zero orders", "gross_to_net": "no level 1"}})

    with pytest.raises(ValidationError, match="requires it"):
        DiagnosisContract.model_validate(payload)


def test_accepts_a_lens_that_could_not_be_built_when_it_says_so() -> None:
    payload = diagnosis_payload()
    payload["tree"]["lever"].update(
        {"level1": None, "level2": None, "gross_to_net": None,
         "masked_shift_alert": None,
         "reasons": {"level1": "zero orders in the previous period",
                     "level2": "level 1 could not be computed",
                     "gross_to_net": "zero orders in the previous period",
                     "masked_shift_alert": "zero orders in the previous period"}})

    diagnosis = DiagnosisContract.model_validate(payload)

    assert diagnosis.tree is not None
    assert diagnosis.tree.lever.masked_shift_alert is None


# --- blocked runs (CONTRACTS.md section 7) ------------------------------------


def test_rejects_a_blocked_run_that_still_carries_a_tree() -> None:
    payload = diagnosis_payload()
    payload["trust"]["verdict"] = "blocked"
    payload["headline"]["rule"] = 1

    with pytest.raises(ValidationError, match="blocked run carries no"):
        DiagnosisContract.model_validate(payload)


def test_accepts_a_blocked_run_with_every_analysis_block_null() -> None:
    payload = diagnosis_payload()
    payload["trust"]["verdict"] = "blocked"
    payload.update({"calendar": None, "signals": None, "tree": None, "localization": None})
    payload["headline"] = {"rule": 1, "hypothesis_id": None, "lens": None,
                           "message": "The data could not be trusted for this period."}

    diagnosis = DiagnosisContract.model_validate(payload)

    assert diagnosis.tree is None
    assert diagnosis.headline.rule == 1


# --- degraded mode (CONTRACTS.md section 7, AI_PIPELINE.md section 9) --------
# Unchanged in substance from the pre-3C file: the AI blocks are still
# all-or-nothing and a dropped key still must not parse as a degraded run.


def test_accepts_degraded_file_with_null_ai_blocks() -> None:
    payload = diagnosis_payload()
    payload.update({"model_used": None, "ai_findings": None})

    diagnosis = DiagnosisContract.model_validate(payload)

    assert diagnosis.ai_findings is None
    assert diagnosis.tree is not None
    assert diagnosis.headline.message.startswith("Most of the decline")


def test_rejects_missing_ai_findings_key() -> None:
    # A dropped key must not parse as a degraded run: null is a value.
    payload = diagnosis_payload()
    del payload["ai_findings"]

    with pytest.raises(ValidationError, match="ai_findings"):
        DiagnosisContract.model_validate(payload)


def test_rejects_findings_without_model_used() -> None:
    payload = diagnosis_payload()
    payload["model_used"] = None

    with pytest.raises(ValidationError, match="both null or both filled"):
        DiagnosisContract.model_validate(payload)


def test_rejects_model_used_without_findings() -> None:
    payload = diagnosis_payload()
    payload["ai_findings"] = None

    with pytest.raises(ValidationError, match="both null or both filled"):
        DiagnosisContract.model_validate(payload)


# --- couplings this model states in prose and did not check (3D5b review) ----
#
# `Signal._nulls_mean_no_baseline` was added in 3B after a doc-only invariant
# let a `within` row through with null limits, and its docstring says such
# rules must be "enforced, not just documented". Four more couplings were
# documented and unenforced; two arrived with 3D4/3D5's fields and two predate
# them, marked below.


def _signal(**overrides: Any) -> dict:
    base = dict(series="revenue", mode="level", value_cur=1.0, center=1.0,
                lower=0.0, upper=2.0, signal="within", rule=None,
                limits_method="mean_moving_range")
    return {**base, **overrides}


@pytest.mark.parametrize("label,kwargs", [
    # Mine, 3D5: CONTRACTS section 7 says the reason "is only ever set
    # alongside signal = insufficient_history".
    ("a reason on a charted row", _signal(insufficient_reason="too_few_points")),
    ("no reason on an unchartable row",
     _signal(value_cur=None, center=None, lower=None, upper=None,
             signal="insufficient_history", insufficient_reason=None)),
    # Pre-existing, 3D3: mode_fallback means "charted on the LEVEL chart", so
    # a yoy row cannot carry one.
    ("a fallback on a year-over-year row",
     _signal(mode="yoy", mode_fallback="no_year_ago_value")),
    # Pre-existing, 3B: `rule` is documented as "null when the series is
    # within limits or has no baseline".
    ("a rule on a within row", _signal(rule=2)),
])
def test_a_signal_cannot_contradict_itself(label: str, kwargs: dict) -> None:
    with pytest.raises(ValidationError):
        Signal(**kwargs)


def _lever(**overrides: Any) -> dict:
    level1 = LeverLevel(formula="customers*frequency*aov", factors=[
        LeverFactor(name="customers", value_prev=1.0, value_cur=1.0,
                    contribution=0.0),
        LeverFactor(name="frequency", value_prev=1.0, value_cur=1.0,
                    contribution=0.0),
        LeverFactor(name="aov", value_prev=1.0, value_cur=1.0,
                    contribution=0.0),
    ])
    base = dict(level1=level1, level2=None, gross_to_net=1.0,
                masked_shift_alert=False,
                reasons={"level2": "AOV did not move"})
    return {**base, **overrides}


@pytest.mark.parametrize("label,kwargs", [
    ("an alert that could not be decided, with no reason",
     _lever(masked_shift_alert=None)),
])
def test_a_null_masked_shift_alert_must_say_why(label: str, kwargs: dict) -> None:
    """ADR-0007: the alert can now be null with level 1 present - there was no
    typical month to measure a material move against - so that null does not
    explain itself by pointing at level 1, and needs its own reason."""
    with pytest.raises(ValidationError, match="masked_shift_alert is null and carries no reason"):
        Lever(**kwargs)


def test_a_pre_adr_0007_lever_with_no_tree_still_loads() -> None:
    """3D6b doubt-review #1: the first version of this session's validator
    demanded a reason for EVERY null alert, so a diagnosis.json written before
    ADR-0007 - null level 1, null alert, the retired basis, no alert reason -
    no longer loaded, while the change log said it did."""
    lever = Lever(**_lever(level1=None, gross_to_net=None, masked_shift_alert=None,
                           masked_shift_basis=None,
                           reasons={"level1": "no orders", "level2": "no level 1",
                                    "gross_to_net": "no level 1"}))

    assert lever.masked_shift_alert is None


def test_an_undecided_alert_with_its_reason_is_accepted() -> None:
    lever = Lever(**_lever(masked_shift_alert=None, reasons={
        "level2": "AOV did not move",
        "masked_shift_alert": "no complete trading month in the history window"}))

    assert lever.masked_shift_alert is None


def _pair() -> LeverLevel:
    return LeverLevel(formula="orders*aov", factors=[
        LeverFactor(name="orders", value_prev=1.0, value_cur=1.0, contribution=0.0),
        LeverFactor(name="aov", value_prev=1.0, value_cur=1.0, contribution=0.0)])


@pytest.mark.parametrize("label,kwargs,match", [
    ("a pair with no level 1 to derive it from",
     _lever(level1=None, gross_to_net=None, masked_shift_alert=None,
            masked_shift_pair=_pair(),
            reasons={"level1": "no orders", "level2": "no level 1",
                     "gross_to_net": "no level 1"}),
     "requires it"),
    ("a pair that is not orders x aov",
     _lever(masked_shift_pair=LeverLevel(formula="units_per_order*price_per_unit", factors=[
         LeverFactor(name="units_per_order", value_prev=1.0, value_cur=1.0, contribution=0.0),
         LeverFactor(name="price_per_unit", value_prev=1.0, value_cur=1.0, contribution=0.0)])),
     "orders\\*aov"),
])
def test_the_masked_shift_pair_is_orders_times_aov_from_level_1(
    label: str, kwargs: dict, match: str,
) -> None:
    """3D6b: the alert is decided on the orders x AOV split of level 1, so a
    pair without level 1, or a pair of any other shape, is a bug in the file."""
    with pytest.raises(ValidationError, match=match):
        Lever(**kwargs)


def test_a_fired_alert_must_carry_its_pair() -> None:
    """Pair review #5: headline rule 4 names the pair's two contributions, so
    an alert that fired with no pair leaves it nothing to name."""
    with pytest.raises(ValidationError, match="fired alert must carry"):
        Lever(**_lever(masked_shift_alert=True))


@pytest.mark.parametrize("orders,aov,contributions,label", [
    ((1.0, 1.0), (1.0, 2.0), (1.0, -1.0), "AOV 1 -> 2 against level 1's 1 -> 1, sum still 0"),
    ((1.0, 3.0), (1.0, 1.0), (1.0, -1.0), "orders 1 -> 3 against level 1's 1 -> 1, sum still 0"),
    ((1.0, 1.0), (1.0, 1.0), (1.0, 0.0), "the right figures, contributions summing to 1 not 0"),
])
def test_a_pair_must_match_level_1(orders, aov, contributions, label) -> None:
    """Pair review #5: a pair whose figures contradict level 1 loaded. Level 1
    here is customers 1, frequency 1, AOV 1 in both periods, change 0. Each
    case breaks exactly one of the three ties, so each check is pinned on its
    own (the mutation check found the AOV tie covered only by accident)."""
    wrong = LeverLevel(formula="orders*aov", factors=[
        LeverFactor(name="orders", value_prev=orders[0], value_cur=orders[1],
                    contribution=contributions[0]),
        LeverFactor(name="aov", value_prev=aov[0], value_cur=aov[1],
                    contribution=contributions[1])])

    with pytest.raises(ValidationError, match="does not match level1"):
        Lever(**_lever(masked_shift_pair=wrong))


def test_a_lever_with_its_pair_is_accepted() -> None:
    lever = Lever(**_lever(masked_shift_pair=_pair()))

    assert lever.masked_shift_pair is not None
    assert lever.masked_shift_pair.formula == "orders*aov"


def test_a_file_still_carrying_the_retired_basis_is_read() -> None:
    """`masked_shift_basis` was removed by ADR-0007. Contract models ignore
    unknown fields (CONTRACTS section 10), so a diagnosis.json written before
    the change still loads - the field is simply not there any more."""
    lever = Lever(**_lever(masked_shift_basis="yoy"))

    assert not hasattr(lever, "masked_shift_basis")
