"""The frontend's report.json fixture is one stage 5 could write (6E1 review #8).

frontend/src/pages/insightsFixture.json feeds every Insights test. A fixture the contract refuses - a
note with the wrong measures or figures, a KPI naming a note the report does not show - lets the page's
tests pass on states that never occur, so contracts/report.py validates it here.
"""

import json
from pathlib import Path

from contracts.lines import NOTE_FIGURES
from contracts.report import ReportContract

FIXTURE = Path(__file__).resolve().parents[2] / "frontend" / "src" / "pages" / "insightsFixture.json"

# The note figures each KPI stands for (stages/report/layers.py lists a note beside a KPI it names).
KPI_FIGURE = {"revenue": "revenue", "orders": "orders", "active_customers": "customers", "aov": "aov",
              "return_rate": "return_rate"}


def test_the_insights_fixture_is_a_report_stage_5_could_write() -> None:
    report = ReportContract.model_validate_json(FIXTURE.read_text(encoding="utf-8"))

    assert report.layer_1_numbers.notes, "the fixture keeps a note beside figures for the marker tests"


def test_each_kpi_lists_exactly_the_notes_that_name_its_figure() -> None:
    report = json.loads(FIXTURE.read_text(encoding="utf-8"))
    notes = report["layer_1_numbers"]["notes"]

    for kpi in report["layer_1_numbers"]["kpis"]:
        named = [note["code"] for note in notes if KPI_FIGURE[kpi["id"]] in NOTE_FIGURES[note["code"]]]
        assert kpi["notes"] == named, kpi["id"]
