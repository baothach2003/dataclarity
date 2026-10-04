"""Decision 1 (Thach, 2026-10-03/04), written before the bump: diagnosis.json
18.2 carries the season comparison in headline.movement.season, report.json
2.4 carries it with the Headline model, and the page shows the season's
sentence as the headline and its note above the hypothesis table."""

from contracts.diagnosis import DiagnosisContract, SeasonChange
from contracts.report import ReportContract
from stages.diagnose.assemble import SCHEMA_VERSION as DIAGNOSIS_VERSION
from stages.diagnose.headline import BEYOND_NOTE, SEASON_NOTE
from stages.diagnose.season_headline import beyond, consistent
from stages.report.builder import SCHEMA_VERSION as REPORT_VERSION
from stages.report.html_report import render_html
from tests.contracts.test_diagnosis import diagnosis_payload
from tests.stages.report.html_probe import Page
from tests.stages.report.report_fixtures import build

CHANGE = "Revenue went from 515,060.53 to 654,527.09 (+139,466.56)."


def _season(band: str, expected: float, gap: float, typical: float) -> dict:
    return {"expected_change_pct": expected, "years": 1, "difference_pct": gap, "typical_pct": typical,
            "differences": 10, "band": band, "beyond_factor": 4.0}


def _seasonal(season: dict, note: str) -> dict:
    words = (consistent(SeasonChange(**season), 2.0) if season["band"] == "consistent"
             else beyond(SeasonChange(**season), stated=True))
    diagnosis = diagnosis_payload()
    diagnosis["headline"] = {
        "rule": 7, "hypothesis_id": None, "lens": None, "message": f"{CHANGE} {words}",
        "movement": {"change_pct": season["expected_change_pct"] + season["difference_pct"], "typical_pct": 16.2,
                     "movements": 22, "factor": 2.0, "singled_out": False, "reason": None, "season": season}}
    diagnosis["hypotheses_note"] = note
    return diagnosis


# The unanswered plan's 2011-11 (this run's measurement).
CONSISTENT = _season("consistent", 39.14152352999991, -12.06382064331202, 8.54560525372709)
SHORTFALL = _season("shortfall", 48.5, -33.9, 8.0)  # 33.9 >= 4 x 8.0


def test_the_versions_are_additive() -> None:
    assert (DIAGNOSIS_VERSION, REPORT_VERSION) == ("18.3", "2.5")  # 18.3 against_the_change; 2.5 the labels, evidence text, outside reasons


def test_report_json_carries_the_season() -> None:
    season = build(diagnosis=_seasonal(CONSISTENT, SEASON_NOTE)).layer_2_causes.headline.movement.season
    assert season is not None and (season.band, season.years) == ("consistent", 1)
    assert season.difference_pct == CONSISTENT["difference_pct"]


def test_the_page_states_the_season_and_its_note() -> None:
    diagnosis = _seasonal(CONSISTENT, SEASON_NOTE)
    causes = Page(render_html(build(diagnosis=diagnosis))).section("causes")
    assert diagnosis["headline"]["message"] in causes and "+27.1%" in causes
    assert causes.index(SEASON_NOTE) < causes.index("Every hypothesis tested")


def test_a_shortfall_reads_through_with_its_own_note() -> None:
    diagnosis = _seasonal(SHORTFALL, BEYOND_NOTE)
    report = build(diagnosis=diagnosis)
    assert report.layer_2_causes.headline.movement.season.band == "shortfall"
    causes = Page(render_html(report)).section("causes")
    assert diagnosis["headline"]["message"] in causes and BEYOND_NOTE in causes


def test_files_written_before_still_read() -> None:
    # An 18.1 diagnosis.json and a 2.3 report.json have no season: it reads as null.
    diagnosis = _seasonal(CONSISTENT, SEASON_NOTE)
    del diagnosis["headline"]["movement"]["season"]
    assert DiagnosisContract.model_validate(diagnosis).headline.movement.season is None
    report = build(diagnosis=_seasonal(CONSISTENT, SEASON_NOTE)).model_dump(mode="json")
    del report["layer_2_causes"]["headline"]["movement"]["season"]
    assert ReportContract.model_validate(report).layer_2_causes.headline.movement.season is None
