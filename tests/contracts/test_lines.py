"""The line taxonomy's contract blocks (session 2E-t2; review 1's findings
#2, #5 and #7 - written before the fixes): the identity judged against the
money moved, a note's fixed sentence and figures, one note per code, stock
received by sign, and diagnosis.json's two fields required and its marks
only on products it names."""

import pytest
from pydantic import ValidationError

from contracts.diagnosis import DiagnosisContract
from contracts.lines import NOTE_FIGURES, NOTE_TEXTS, FigureNote, IdentityTerms, OutsideRevenueLines
from contracts.metrics import MetricsContract
from tests.contracts.test_diagnosis import diagnosis_payload
from tests.contracts.test_metrics import metrics_payload


def _terms(**changes: float) -> dict[str, float]:
    return {"gross_sales": 0.01, "returns": 0.0, "discounts": 0.0, "other_deductions": 0.0, "other_revenue": 0.0,
            "net_revenue": 0.01, "returns_on_suggested_keys": 0.0, "money_moved": 0.01} | changes


def test_a_charge_and_its_reversal_leave_residue_the_money_moved_absorbs() -> None:
    # 0.01 of sales, then a 1e9 charge and its reversal in the same month:
    # summed in file order the net is 0.01 plus residue, while the charges'
    # own term nets to exactly 0 (review 1 #2 - stage 2 crashed on it).
    net = 0.01 + 1e9 - 1e9
    assert net != 0.01
    terms = IdentityTerms(**_terms(net_revenue=net, money_moved=2e9 + 0.01))
    assert terms.net_revenue == net


def test_an_identity_that_does_not_add_up_is_refused() -> None:
    with pytest.raises(ValidationError, match="does not add up"):
        IdentityTerms(**_terms(net_revenue=0.02))
    # Residue is judged against the money moved: 0.01 off is no residue of 1,000,000 moved.
    with pytest.raises(ValidationError, match="does not add up"):
        IdentityTerms(**_terms(gross_sales=1e6, net_revenue=1e6 + 0.01, money_moved=1e6))
    with pytest.raises(ValidationError, match="money_moved"):
        IdentityTerms(**_terms(money_moved=-1.0))


def _note(code: str, **changes: object) -> dict[str, object]:
    return {"code": code, "figures": NOTE_FIGURES[code], "text": NOTE_TEXTS[code], "measures": []} | changes


def test_a_note_carries_its_codes_sentence_and_figures() -> None:
    assert FigureNote.model_validate(_note("returns_booked_as_in")).figures == [
        "revenue", "returns", "return_rate", "aov", "units", "customers", "products", "diagnosis"]
    with pytest.raises(ValidationError, match="fixed sentence"):
        FigureNote.model_validate(_note("discounts_in_prices", text="Discounts, roughly."))
    with pytest.raises(ValidationError, match="figures"):
        FigureNote.model_validate(_note("same_day_cancellations", figures=["units"]))


def test_a_measure_has_a_name() -> None:
    with pytest.raises(ValidationError, match="name"):
        FigureNote.model_validate(_note("other_transaction_types", measures=[
            {"name": "", "scope": "file", "lines": 1, "amount": 5.0}]))


def test_a_note_names_each_measure_once_per_scope() -> None:
    # Review 3 #8: two type values cut to one name could not be told apart.
    twice = [{"name": "Cash", "scope": "file", "lines": 1, "amount": 5.0},
             {"name": "Cash", "scope": "file", "lines": 2, "amount": 9.0}]
    with pytest.raises(ValidationError, match="twice"):
        FigureNote.model_validate(_note("other_transaction_types", measures=twice))
    twice[1]["scope"] = "current"
    assert len(FigureNote.model_validate(_note("other_transaction_types", measures=twice)).measures) == 2


def test_one_note_per_code_in_both_contracts() -> None:
    twice = [_note("discounts_in_prices"), _note("discounts_in_prices")]
    metrics = metrics_payload()
    metrics["core"]["notes"] = twice
    with pytest.raises(ValidationError, match="one note per code"):
        MetricsContract.model_validate(metrics)
    diagnosis = diagnosis_payload()
    diagnosis["notes"] = twice
    with pytest.raises(ValidationError, match="one note per code"):
        DiagnosisContract.model_validate(diagnosis)


def _outside(**changes: object) -> dict[str, object]:
    return {"line_class": "stock_in", "scope": "file", "sign": "positive", "lines": 1, "amount": 50.0,
            "lines_without_amount": 0} | changes


def test_stock_received_is_reported_by_sign_and_nothing_else_is() -> None:
    assert OutsideRevenueLines.model_validate(_outside()).sign == "positive"
    assert OutsideRevenueLines.model_validate(
        _outside(sign="no_money", amount=0.0, lines_without_amount=1)).lines_without_amount == 1
    with pytest.raises(ValidationError, match="sign"):
        OutsideRevenueLines.model_validate(_outside(sign=None))
    with pytest.raises(ValidationError, match="sign"):
        OutsideRevenueLines.model_validate(_outside(line_class="cost", amount=-7.0))
    with pytest.raises(ValidationError, match="no_money"):
        OutsideRevenueLines.model_validate(_outside(lines=2, lines_without_amount=1))


@pytest.mark.parametrize("field", ["notes", "suggested_classes"])
def test_diagnosis_json_requires_the_notes_and_the_marks(field: str) -> None:
    # A writer that forgot them is refused, never read as "no note" (review 1 #5).
    payload = diagnosis_payload()
    del payload[field]
    with pytest.raises(ValidationError, match=field):
        DiagnosisContract.model_validate(payload)


def test_diagnosis_json_marks_only_the_products_it_names() -> None:
    payload = diagnosis_payload()
    payload["hypotheses"].append({"id": "R1", "family": "localization_lifecycle", "lens": "localization",
                                  "statement": "x", "verdict": "ruled_out", "contribution": None, "share": None,
                                  "evidence": {"top_member": "DOTCOM POSTAGE"}, "rule": "r"})
    payload["suggested_classes"] = {"DOTCOM POSTAGE": "charge"}
    assert DiagnosisContract.model_validate(payload).suggested_classes == {"DOTCOM POSTAGE": "charge"}

    payload["suggested_classes"] = {"A PRODUCT THIS FILE NEVER NAMES": "charge"}
    with pytest.raises(ValidationError, match="does not name"):
        DiagnosisContract.model_validate(payload)


def test_a_metrics_json_written_before_the_line_taxonomy_is_told_to_re_analyse() -> None:
    # 2E-t1 wrote 16.0 without these blocks (the migration's one major, T1).
    payload = metrics_payload()
    for block in ("identity", "outside_revenue", "unclassified", "unmeasurable", "notes"):
        del payload["core"][block]
    with pytest.raises(ValidationError, match="before the line taxonomy.*re-analyse"):
        MetricsContract.model_validate(payload)
