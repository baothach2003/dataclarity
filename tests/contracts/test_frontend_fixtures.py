"""The frontend's report.json fixture is one stage 5 could write (6E1 review #8).

frontend/src/pages/insightsFixture.json feeds every Insights test. A fixture the contract refuses - a
note with the wrong measures or figures, a KPI naming a note the report does not show - lets the page's
tests pass on states that never occur, so contracts/report.py validates it here.
"""

import json
import re
from pathlib import Path

import pytest

from contracts.diagnosis import LeverBridge
from contracts.forecast import MIN_HISTORY_MONTHS
from contracts.lines import NOTE_FIGURES
from contracts.report import ReportContract
from contracts.report_front import FRONT_BANNED
from tests.contracts.front_fixtures import CASES, FRONT_FIXTURES, written

FRONTEND = Path(__file__).resolve().parents[2] / "frontend" / "src"
FIXTURE = FRONTEND / "pages" / "insightsFixture.json"

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


def test_the_frontends_history_minimum_is_the_contracts() -> None:
    # The Insights page says "and 3 are needed" as report.html does; report.json carries only how many
    # months were used, so the frontend keeps the minimum - one value, pinned here to the contract's.
    source = (FRONTEND / "domain" / "forecastRules.ts").read_text(encoding="utf-8")
    found = re.search(r"export const MIN_HISTORY_MONTHS = (\d+)", source)

    assert found is not None
    assert int(found.group(1)) == MIN_HISTORY_MONTHS


# --- the report redesign, step 5: the front section's fixtures are stage 5's output, unchanged ---------------


@pytest.mark.parametrize("case", CASES)
def test_each_front_fixture_is_what_stage_5_writes_today(case: str) -> None:
    on_disk = (FRONT_FIXTURES / f"{case}.json").read_text(encoding="utf-8")
    data = json.loads(on_disk)

    ReportContract.model_validate(data["report"])
    LeverBridge.model_validate(data["bridge"])
    assert on_disk == written(case), "regenerate: python -m tests.contracts.front_fixtures"


def test_the_pages_banned_words_are_the_contracts() -> None:
    # The Insights page checks its front against the same list report.html is checked against (step 5).
    source = (FRONTEND / "domain" / "frontBanned.ts").read_text(encoding="utf-8")
    found = re.search(r"export const FRONT_BANNED = \[(.*?)\]", source, re.S)

    assert found is not None
    assert tuple(re.findall(r"'([^']*)'", found.group(1))) == FRONT_BANNED
