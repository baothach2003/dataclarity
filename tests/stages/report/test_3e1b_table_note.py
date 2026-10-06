"""Thach, 2026-10-03 (decision 4), written before the code: when the size
test keeps every cause out of the headline, diagnosis.json (18.1) carries one
table-level note, and the report (2.3) shows it above the hypothesis table."""

from contracts.diagnosis import DiagnosisContract
from contracts.report import ReportContract
from stages.diagnose.assemble import SCHEMA_VERSION as DIAGNOSIS_VERSION
from stages.diagnose.headline import WITHIN_NOTE
from stages.report.builder import SCHEMA_VERSION as REPORT_VERSION
from stages.report.html_report import render_html
from tests.contracts.test_diagnosis import diagnosis_payload
from tests.stages.report.html_probe import Page
from tests.stages.report.report_fixtures import build


def _noted() -> dict:
    diagnosis = diagnosis_payload()
    diagnosis["hypotheses_note"] = WITHIN_NOTE
    return diagnosis


def test_the_versions_are_additive() -> None:
    assert (DIAGNOSIS_VERSION, REPORT_VERSION) == ("18.8", "2.9")  # 18.8 hypotheses[].member (Q62); 18.7 the checks' month and headline.offsetting (Q39, Q40); 18.6 headline.named (Q33); 2.9 the front section (step 3); 2.8 not_in_v1 and the revenue KPI's change (Q21, Q22); 18.5 "failed_checks"; 18.4 the report redesign's bridge, year_ago, hedge; 2.7 the headline's hedge; 18.1 / 2.3 the note; 18.2 / 2.4 the season; 18.3 / 2.5 the labels; 2.6 the lens


def test_report_json_carries_the_note() -> None:
    assert build(diagnosis=_noted()).layer_2_causes.hypotheses_note == WITHIN_NOTE
    assert build().layer_2_causes.hypotheses_note is None


def test_the_page_shows_it_above_the_hypothesis_table() -> None:
    causes = Page(render_html(build(diagnosis=_noted()))).section("causes")
    assert causes.index(WITHIN_NOTE) < causes.index("Every hypothesis tested")


def test_files_written_before_still_read() -> None:
    diagnosis = diagnosis_payload()
    diagnosis.pop("hypotheses_note", None)
    assert DiagnosisContract.model_validate(diagnosis).hypotheses_note is None
    report = build().model_dump(mode="json")
    del report["layer_2_causes"]["hypotheses_note"]
    assert ReportContract.model_validate(report).layer_2_causes.hypotheses_note is None
