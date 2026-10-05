"""The bridge never takes the diagnosis down (Thach, 2026-10-05, item 1).

The waterfall is a display: every doubt-review cycle of step 1 found a
rounding edge that crashed stage 3 and lost the whole diagnosis.json. Here a
bridge that fails for ANY reason - building it, its own validation, or the
file's validation of it - is withheld (`bridge_withheld` "failed_checks"),
and every other field of the diagnosis is written exactly as without it:
suppress, never fabricate."""

from datetime import date

import pytest

from contracts.lever_bridge import floor_cents
from stages.diagnose import lever as lever_module
from stages.diagnose.assemble import diagnose
from tests.stages.diagnose.diagnose_fixtures import NOW, row, run_data


def _rows() -> list[dict]:
    # October: 31 lines of 10.00 from three customers; November: 30 lines of 2 x 12.00 from four.
    rows = [row(date(2024, 10, day), qty=1.0, price=10.0, customer=f"C{day % 3}") for day in range(1, 32)]
    rows += [row(date(2024, 11, day), qty=2.0, price=12.0, customer=f"C{day % 4}") for day in range(1, 31)]
    return rows


def _without_the_bridge(found) -> dict:
    data = found.model_dump(mode="json")
    data.pop("generated_at")
    for key in ("bridge", "bridge_withheld"):
        data["tree"]["lever"].pop(key)
    return data


@pytest.fixture
def baseline():
    found = diagnose(run_data(_rows()), NOW)
    assert found.tree.lever.bridge is not None  # the run draws a bridge when nothing fails
    return found


def _raises(*args, **kwargs):
    raise RuntimeError("a bridge bug")


def _wrong_cents(terms, total):
    # Cents that do not sum to the target: the bridge's own validator refuses them.
    return [floor_cents(term) + 7 for term in terms]


@pytest.mark.parametrize("name,replacement", [
    ("allocate_cents", _raises),        # building the bridge raises
    ("allocate_cents", _wrong_cents),   # the bridge's own validation refuses it
    ("as_shown", _raises),              # a helper of the bridge raises
])
def test_a_bridge_that_fails_is_withheld_and_the_diagnosis_stands(baseline, monkeypatch, name, replacement) -> None:
    monkeypatch.setattr(lever_module, name, replacement)

    found = diagnose(run_data(_rows()), NOW)

    assert (found.tree.lever.bridge, found.tree.lever.bridge_withheld) == (None, "failed_checks")
    assert _without_the_bridge(found) == _without_the_bridge(baseline)


def test_a_bridge_the_file_refuses_is_withheld_and_the_diagnosis_stands(baseline, monkeypatch) -> None:
    # The bridge is valid on its own but breaks a tie the whole file checks: it withholds the split for
    # refund lines where B2 refused on none (compute_lever's refund count patched; B2 keeps its own).
    monkeypatch.setattr(lever_module, "refund_lines", lambda data: {"prev": 1, "cur": 0})

    found = diagnose(run_data(_rows()), NOW)

    assert (found.tree.lever.bridge, found.tree.lever.bridge_withheld) == (None, "failed_checks")
    assert _without_the_bridge(found) == _without_the_bridge(baseline)


def test_a_file_refused_for_something_else_is_still_refused(monkeypatch) -> None:
    # A suggestion marking a product the file never names: the contract refuses the file with or without
    # its bridge, so withholding the bridge must not hide it.
    from pydantic import ValidationError

    from stages.diagnose import assemble

    monkeypatch.setattr(assemble, "named_suggestions", lambda *args: {"No such product": "charge"})

    with pytest.raises(ValidationError, match="suggested_classes marks products"):
        diagnose(run_data(_rows()), NOW)


def test_an_18_4_file_cannot_carry_failed_checks(monkeypatch) -> None:
    from pydantic import ValidationError

    from contracts.diagnosis import DiagnosisContract

    monkeypatch.setattr(lever_module, "allocate_cents", _raises)
    data = diagnose(run_data(_rows()), NOW).model_dump()
    data["schema_version"] = "18.4"

    with pytest.raises(ValidationError, match="exists from 18.5"):
        DiagnosisContract.model_validate(data)


def test_a_failure_that_is_not_the_bridges_still_fails(monkeypatch) -> None:
    # Suppressing the bridge must not hide anything else: a failure in another block still raises.
    from stages.diagnose import assemble

    monkeypatch.setattr(assemble, "evaluate_hypotheses", _raises)

    with pytest.raises(RuntimeError, match="a bridge bug"):
        diagnose(run_data(_rows()), NOW)
