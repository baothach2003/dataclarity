"""Thach's layout (report.json 2.11): the branches mutation found untested,
each its own test (the line's templates, the chips' strength and wording,
the contract's refusals). Expected texts from the real runs' own fields."""

import copy

import pytest
from pydantic import ValidationError

from contracts.diagnosis import DiagnosisContract
from contracts.metrics import MetricsContract
from contracts.report import ReportContract
from stages.report import dashboard_bands
from stages.report.front_checklist import checklist_groups
from stages.report.front_summary import sales_change
from tests.stages.report.real_runs import build_real, files

_REPORTS: dict[str, ReportContract] = {}


def _real(run: str) -> ReportContract:
    if run not in _REPORTS:
        _REPORTS[run] = build_real(run)
    return _REPORTS[run]


def test_a_season_of_several_years_is_said_as_earlier_years() -> None:
    diagnosis = copy.deepcopy(files("demo_classed")["diagnosis.json"])
    diagnosis["headline"]["movement"]["season"]["years"] = 2
    report = build_real("demo_classed", diagnosis=diagnosis)
    assert report.dashboard.headline.text.endswith("· in line with earlier years (+27.1%)")


def test_no_change_says_the_same_on_the_line_and_no_change_on_the_tile() -> None:
    metrics = MetricsContract.model_validate(files("kaggle")["metrics.json"])
    metrics = metrics.model_copy(update={"core": metrics.core.model_copy(update={"revenue_change": 0.0})})
    assert sales_change(metrics, None, None, None)[2] == "no change"
    report = _real("kaggle")
    diagnosis = DiagnosisContract.model_validate(files("kaggle")["diagnosis.json"])
    line = dashboard_bands.headline(metrics=metrics, diagnosis=diagnosis, bridge=None, front=report.front,
                                    numbers=report.layer_1_numbers, code=None)
    assert line.text == "Sales the same as November 2024"


def test_a_subject_takes_its_strongest_status_other_way_over_moved(monkeypatch: pytest.MonkeyPatch) -> None:
    # Customers: C3 moved (rule 7), C2 pulled the other way - "other way" is the stronger word.
    monkeypatch.setattr(dashboard_bands, "checklist_groups", lambda d, v: [("moved", ["C3"]), ("against", ["C2"])])
    report = _real("demo_classed")
    chips = dashboard_bands.checked(front=report.front, diagnosis=None, views=[], lines_basis=False)  # type: ignore[arg-type]
    assert [(c.label, c.status) for c in chips] == [("Data", "checked"), ("Customers", "other way")]


def test_a_file_that_counts_lines_never_says_order(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dashboard_bands, "checklist_groups", lambda d, v: [("matches", ["B1"])])
    report = _real("kaggle")
    chips = dashboard_bands.checked(front=report.front, diagnosis=None, views=[], lines_basis=True)  # type: ignore[arg-type]
    assert [c.label for c in chips] == ["Data", "Lines per customer"]


def test_under_rule_2_the_first_group_is_named() -> None:
    report = _real("demo_classed")
    diagnosis = DiagnosisContract.model_validate(files("demo_classed")["diagnosis.json"])
    diagnosis = diagnosis.model_copy(update={"headline": diagnosis.headline.model_copy(update={"rule": 2})})
    groups = checklist_groups(diagnosis, report.layer_2_causes.hypotheses)
    assert groups[0][0] == "matches"


def _dump(run: str = "kaggle") -> dict:
    return _real(run).model_dump(mode="json")


def test_the_contract_refuses_a_line_over_twenty_words() -> None:
    data = _dump()
    data["dashboard"]["headline"]["text"] = " ".join(["word"] * 21)
    with pytest.raises(ValidationError, match="20 words at most"):
        ReportContract.model_validate(data)


def test_the_contract_refuses_chips_on_a_blocked_report() -> None:
    data = _dump()
    data["dashboard"]["state"] = "blocked"
    with pytest.raises(ValidationError, match="blocked report draws no chip"):
        ReportContract.model_validate(data)


def test_the_contract_refuses_a_next_step_that_is_not_an_action() -> None:
    data = _dump()
    data["dashboard"]["next_steps"] = ["Sell more."]
    with pytest.raises(ValidationError, match="one next-step line per suggested action"):
        ReportContract.model_validate(data)
