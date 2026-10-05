"""Thach's decisions (vii)-(ix) on the fifteenth report (2026-10-04), stage 5's half: report.json carries,
per hypothesis, whether it was ruled out for moving AGAINST the change, its verdict label and its evidence
text, and, per line outside revenue, its reason worded by class code - so report.html and the page print
the same words from one copy (report.json 2.5, additive). "Against" is stage 3's statement
(diagnosis.json's `against_the_change`, 18.3): stage 5 re-derives nothing, it only decides where the
statement is shown (the sixteenth run's review, findings 2 and 3)."""

from copy import deepcopy
from typing import Any

import pytest
from pydantic import ValidationError

from contracts.diagnosis import DiagnosisContract
from contracts.lines import OUTSIDE_REVENUE_TEXTS
from contracts.report_views import HypothesisView, OutsideRevenueView, against_label
from stages.report.builder import SCHEMA_VERSION
from stages.report.html_report import render_html
from tests.contracts.test_diagnosis import diagnosis_payload
from tests.stages.report.html_probe import Page
from tests.stages.report.report_fixtures import build

# The fixture compares 2011-11 (1,150,000) with 2011-10 (1,290,000): revenue FELL; gross sales fell too
# (1,338,000 -> 1,198,000, tree.returns).


def _with(*rows: dict[str, Any], suggested: dict[str, str] | None = None, tree: bool = True) -> dict:
    """The fixture diagnosis with these hypotheses added beside its supported P2."""
    payload = diagnosis_payload()
    base = payload["hypotheses"][0]
    for row in rows:
        payload["hypotheses"].append(deepcopy(base) | row)
    if suggested is not None:
        payload["suggested_classes"] = suggested
    if not tree:
        payload["tree"] = None
    return payload


def _row(report, hypothesis_id: str) -> HypothesisView:
    return next(h for h in report.layer_2_causes.hypotheses if h.id == hypothesis_id)


def _hypothesis(payload: dict, hypothesis_id: str):
    return next(h for h in DiagnosisContract.model_validate(payload).hypotheses if h.id == hypothesis_id)


C2_UP = {"id": "C2", "family": "customers", "lens": "customers", "statement": "Revenue lost to lapsed customers changed",
         "verdict": "ruled_out", "contribution": 5000.0, "share": 0.0357, "evidence": {"lapsed_current": 1000.0},
         "against_the_change": True}
P1_UP = {"id": "P1", "lens": "product", "statement": "Like-for-like prices changed", "verdict": "ruled_out",
         "contribution": 3000.0, "share": 0.0214, "against_the_change": True}  # gross sales fell


def test_the_version_is_2_6() -> None:
    # 2.5: the hypotheses' labels and evidence text, the outside lines' reasons; 2.6: each row's lens (Q2).
    assert SCHEMA_VERSION == "2.8"


# (vii) One label, from stage 3's own sign test as diagnosis.json states it.
def test_a_cause_stage_3_ruled_out_against_the_change_is_labelled_so() -> None:
    report = build(diagnosis=_with(C2_UP, P1_UP))

    assert (_row(report, "C2").moved_against, _row(report, "C2").verdict_label) == (
        True, "moved against the change (+5,000.00)")
    # Q2 (Thach, 2026-10-05): the product lens names its total - gross sales, shown nowhere else.
    assert (_row(report, "P1").moved_against, _row(report, "P1").verdict_label, _row(report, "P1").lens) == (
        True, "moved against the change in gross sales (+3,000.00)", "product")
    assert _row(report, "C2").lens == "customers"
    assert _row(report, "C2").verdict == "ruled_out"  # the code is unchanged


def test_stage_5_re_derives_nothing() -> None:
    # Stage 3 measured P1 on its own gross sales; stage 5 reads no tree, no gross and no KPI direction: a
    # diagnosis with no tree still labels it, and one stage 3 did not call against is never labelled, even
    # where the report's revenue moved the other way.
    assert _row(build(diagnosis=_with(P1_UP, tree=False)), "P1").moved_against is True
    unsaid = _row(build(diagnosis=_with(C2_UP | {"against_the_change": False})), "C2")
    assert (unsaid.moved_against, unsaid.verdict_label) == (False, "ruled out")


def test_a_leftover_that_prints_as_zero_is_not_labelled() -> None:
    hypothesis = _row(build(diagnosis=_with(C2_UP | {"contribution": 1e-13, "share": 7e-19})), "C2")

    assert (hypothesis.moved_against, hypothesis.verdict_label) == (False, "ruled out")


def test_every_other_verdict_is_worded_as_its_code() -> None:
    report = build(diagnosis=_with(C2_UP | {"verdict": "not_testable", "contribution": None, "share": None,
                                            "against_the_change": False}))

    assert _row(report, "P2").verdict_label == "supported"
    assert _row(report, "C2").verdict_label == "not testable"


@pytest.mark.parametrize("row", [C2_UP, P1_UP], ids=["customers", "product"])
def test_never_beside_a_month_the_report_does_not_compare(row: dict) -> None:
    # Every lens alike (review finding 2: the product lens once answered before the withheld check).
    from stages.report.hypothesis_rows import moved_against

    numbers = build(diagnosis=_with(row)).layer_1_numbers
    revenue = numbers.kpis[0]
    assert revenue.id == "revenue"
    withheld = numbers.model_copy(update={"kpis": [revenue.model_copy(update={
        "current": None, "change_pct": None, "current_reason": "r", "change_reason": "r"}), *numbers.kpis[1:]]})
    no_previous = numbers.model_copy(update={"kpis": [revenue.model_copy(update={
        "previous": None, "change_pct": None, "previous_reason": "r", "change_reason": "r"}), *numbers.kpis[1:]]})
    incomplete = numbers.model_copy(update={"period": numbers.period.model_copy(update={"previous_complete": False})})
    hypothesis = _hypothesis(_with(row), row["id"])

    assert moved_against(hypothesis, numbers) is True
    assert [moved_against(hypothesis, n) for n in (withheld, no_previous, incomplete)] == [False, False, False]


def test_the_label_is_the_contracts_one_copy() -> None:
    assert against_label(5000.0, "customers") == "moved against the change (+5,000.00)"
    assert against_label(-1234.567, "lever") == "moved against the change (-1,234.57)"
    assert against_label(-50.0, "product") == "moved against the change in gross sales (-50.00)"
    assert against_label(-50.0, None) == "moved against the change (-50.00)"  # a 2.5 row: no lens written


def test_one_copy_says_which_total_a_share_is_measured_on(monkeypatch) -> None:
    # Stage 3's share test - its total and the basis its rule prints - and the label read the same rule
    # (CLAUDE.md 3.1), by behaviour: moved to the returns lens, all three follow (review, findings 2-3).
    from types import SimpleNamespace

    import contracts.diagnosis
    import contracts.report_views as views
    from contracts.diagnosis import measured_on_gross_sales
    from stages.diagnose import hypotheses
    from stages.diagnose.catalog import BY_ID
    from stages.diagnose.step7_inputs import Changes

    assert [lens for lens in ("product", "customers", "lever", "time", "data", "returns", None)
            if measured_on_gross_sales(lens)] == ["product"]
    assert hypotheses.measured_on_gross_sales is views.measured_on_gross_sales is contracts.diagnosis.measured_on_gross_sales
    p3 = BY_ID["P3"]  # the returns lens
    moved = Changes(1000.0, 800.0, -200.0, 100.0, False)  # revenue fell, gross sales rose
    for module in (hypotheses, views):
        monkeypatch.setattr(module, "measured_on_gross_sales", lambda lens: lens in ("product", "returns"))
    _, _, rule = hypotheses.share_verdict(p3, 50.0, SimpleNamespace(tree=None), moved)
    assert "|change in gross sales|" in rule
    assert hypotheses.against_the_change(p3, -50.0, moved) is True  # against the gross sales' rise
    assert views.against_label(-50.0, "returns") == "moved against the change in gross sales (-50.00)"


def test_the_contract_refuses_a_label_its_code_does_not_give() -> None:
    row = {"id": "C2", "statement": "s", "verdict": "ruled_out", "contribution": -3000.0, "share": -0.5, "rule": "r",
           "evidence": {"k": 1.0}, "evidence_text": ["k: 1.00"]}
    good = row | {"moved_against": True, "verdict_label": "moved against the change (-3,000.00)"}
    assert HypothesisView.model_validate(good).moved_against is True
    gross = good | {"lens": "product", "verdict_label": "moved against the change in gross sales (-3,000.00)"}
    # A lens the catalog does not have, its bare label consistent - only the vocabulary refuses it (review,
    # finding 4): "products" must not pass as a lens whose total goes unnamed.
    with pytest.raises(ValidationError, match="Input should be"):
        HypothesisView.model_validate(good | {"lens": "products"})
    assert HypothesisView.model_validate(gross).moved_against is True
    with pytest.raises(ValidationError, match="against"):  # the product lens's label names its total
        HypothesisView.model_validate(gross | {"verdict_label": "moved against the change (-3,000.00)"})
    with pytest.raises(ValidationError, match="against"):  # and only the product lens's
        HypothesisView.model_validate(good | {"verdict_label": "moved against the change in gross sales (-3,000.00)"})
    for wrong in ({"verdict": "supported", "verdict_label": "moved against the change (-3,000.00)"},  # code
                  {"verdict_label": "moved against the change (+5.00)"},  # another figure
                  {"verdict_label": None},  # no label
                  {"contribution": 1e-13, "verdict_label": "moved against the change (+0.00)"},  # prints as zero
                  {"share": None}):
        with pytest.raises(ValidationError, match="against"):
            HypothesisView.model_validate(good | wrong)
    with pytest.raises(ValidationError, match="label"):
        HypothesisView.model_validate(row | {"verdict_label": "supported"})
    assert HypothesisView.model_validate(row | {"evidence_text": []}).verdict_label is None  # a 2.4 report


def test_the_contract_pairs_the_evidence_text_with_the_evidence() -> None:
    row = {"id": "C2", "statement": "s", "verdict": "ruled_out", "contribution": None, "share": None, "rule": "r",
           "evidence": {"a": 1.0, "b": "x"}, "verdict_label": "ruled out"}
    assert HypothesisView.model_validate(row | {"evidence_text": ["a: 1.00", "b: x"]}).evidence_text
    for wrong in (["a: 1.00"], ["b: x", "a: 1.00"], ["a: 1.00", "c: x"]):
        with pytest.raises(ValidationError, match="evidence"):
            HypothesisView.model_validate(row | {"evidence_text": wrong})
        with pytest.raises(ValidationError, match="evidence"):  # unlabelled too (review 2, #3)
            HypothesisView.model_validate(row | {"verdict_label": None, "evidence_text": wrong})


# (viii) The evidence as report.html words it (html_parts.evidence_value), in report.json.
def test_each_hypothesis_carries_its_evidence_text() -> None:
    report = build(diagnosis=_with(
        {"id": "R1", "lens": "localization", "family": "localization_lifecycle", "verdict": "ruled_out",
         "contribution": None, "share": None, "evidence": {"top_member": "Gift wrap", "top_member_share": 0.12}},
        suggested={"Gift wrap": "charge"}))

    assert _row(report, "P2").evidence_text == ["mix_effect: -21,000.00", "delta_gross: -100,000.00"]
    assert _row(report, "R1").evidence_text == ["top_member: Gift wrap (suggested: charge, not confirmed)",
                                                "top_member_share: 0.12"]


# (ix) Every line outside revenue with its reason, worded by class code as notes are.
def test_each_class_outside_revenue_is_worded_so() -> None:
    assert OUTSIDE_REVENUE_TEXTS == {
        "gift_card_sale": "A gift card sold is owed to the customer until it is redeemed, so it is not counted in "
                          "revenue.",
        "gift_card_redemption": "A gift card line below 0 settles or reverses what a gift card sold owed, so it is "
                                "not counted in revenue.",
        "cost": "A fee or cost is not a sale, so it is not counted in revenue.",
        "adjustment": "An accounting adjustment is not a sale: it is left out of revenue and reported as a "
                      "reconciling amount.",
        "stock_in": 'Stock received (a line typed "in") is not a sale, so it is not counted in revenue.',
    }


# #2: the report itself holds the display rule and the 2.5 shape, as the page's reader does.
def test_the_report_refuses_against_beside_a_month_it_does_not_compare() -> None:
    from contracts.report import ReportContract

    # Withheld here; an incomplete previous month withholds revenue's previous value by the Numbers
    # contract itself, so compared_month_shown reads both (and stage 5's test above, each alone).
    payload = build(diagnosis=_with(C2_UP)).model_dump(mode="json")
    ReportContract.model_validate(payload)
    withheld = deepcopy(payload)
    withheld["layer_1_numbers"]["kpis"][0] |= {"current": None, "change_pct": None, "current_reason": "r",
                                               "change_reason": "r"}
    unflagged = deepcopy(withheld)
    for row in unflagged["layer_2_causes"]["hypotheses"]:
        row |= {"moved_against": False, "verdict_label": row["verdict"].replace("_", " ")}
    ReportContract.model_validate(unflagged)
    with pytest.raises(ValidationError, match="against"):
        ReportContract.model_validate(withheld)


def test_a_2_6_report_names_every_rows_lens() -> None:
    from contracts.report import ReportContract

    payload = build().model_dump(mode="json")
    lensless = deepcopy(payload)
    lensless["layer_2_causes"]["hypotheses"][0]["lens"] = None
    with pytest.raises(ValidationError, match="2.6"):
        ReportContract.model_validate(lensless)
    ReportContract.model_validate(lensless | {"schema_version": "2.5"})  # written before: as it was


def test_a_2_5_report_labels_every_row_and_words_every_outside_line() -> None:
    from contracts.report import ReportContract

    payload = build().model_dump(mode="json")
    unlabelled = deepcopy(payload)
    unlabelled["layer_2_causes"]["hypotheses"][0] |= {"verdict_label": None, "evidence_text": []}
    unworded = deepcopy(payload)
    unworded["layer_1_numbers"]["outside_revenue"][0]["reason"] = None
    for incomplete_2_5 in (unlabelled, unworded):
        with pytest.raises(ValidationError, match="2.5"):
            ReportContract.model_validate(incomplete_2_5)
        ReportContract.model_validate(incomplete_2_5 | {"schema_version": "2.4"})  # written before: as it was


def test_every_class_outside_revenue_has_its_reason() -> None:
    from shared.line_effects import OUTSIDE_REVENUE

    assert set(OUTSIDE_REVENUE_TEXTS) == OUTSIDE_REVENUE
    assert OUTSIDE_REVENUE_TEXTS["stock_in"] == ('Stock received (a line typed "in") is not a sale, so it is not '
                                                 "counted in revenue.")
    assert all("revenue" in text for text in OUTSIDE_REVENUE_TEXTS.values())


def test_the_report_words_each_outside_line_by_its_class() -> None:
    report = build()  # the fixture's cost lines

    assert [(o.line_class, o.reason) for o in report.layer_1_numbers.outside_revenue] == [
        ("cost", OUTSIDE_REVENUE_TEXTS["cost"])]


def test_the_contract_refuses_a_reason_its_class_does_not_give() -> None:
    row = {"line_class": "cost", "scope": "file", "sign": None, "lines": 2, "amount": -5.0, "lines_without_amount": 0}
    with pytest.raises(ValidationError, match="class code"):
        OutsideRevenueView.model_validate(row | {"reason": "money the shop spent"})
    with pytest.raises(ValidationError, match="class code"):  # another class's words
        OutsideRevenueView.model_validate(row | {"reason": OUTSIDE_REVENUE_TEXTS["stock_in"]})
    # A class with no wording is refused as invalid, never a KeyError (review finding 6).
    with pytest.raises(ValidationError, match="class code"):
        OutsideRevenueView.model_validate(row | {"line_class": "sale", "reason": "anything"})
    assert OutsideRevenueView.model_validate(row).reason is None  # a 2.4 report


# report.html prints the same words.
def test_report_html_prints_the_label_the_evidence_and_the_reasons() -> None:
    page = Page(render_html(build(diagnosis=_with(C2_UP))))
    causes, numbers = page.section("causes"), page.section("numbers")

    assert "moved against the change (+5,000.00)" in causes
    assert "mix_effect: -21,000.00" in causes
    assert OUTSIDE_REVENUE_TEXTS["cost"] in numbers


def test_report_html_prints_report_jsons_own_evidence_text() -> None:
    # One copy: report.html prints the text report.json carries, not words of its own.
    report = build(diagnosis=_with(C2_UP))
    rows = [h.model_copy(update={"evidence_text": ["written: by the builder"]}) if h.id == "C2" else h
            for h in report.layer_2_causes.hypotheses]
    report = report.model_copy(update={"layer_2_causes": report.layer_2_causes.model_copy(update={"hypotheses": rows})})

    assert "written: by the builder" in Page(render_html(report)).section("causes")


# (vi) Rule 2's line above the table is stage 3's table note: report.html prints it as the page does.
def test_report_html_prints_rule_2s_line_above_the_table() -> None:
    from stages.diagnose.headline import GAPS_NOTE

    assert GAPS_NOTE.startswith("The days with no sales at all affect the verdicts below")
    payload = _with()
    payload["headline"] = payload["headline"] | {"rule": 2, "hypothesis_id": "D1", "movement": None}
    payload["hypotheses_note"] = GAPS_NOTE
    causes = Page(render_html(build(diagnosis=payload))).section("causes")

    assert GAPS_NOTE in causes
    assert causes.index(GAPS_NOTE) < causes.index("Every hypothesis tested")
