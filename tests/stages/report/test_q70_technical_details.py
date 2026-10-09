"""Thach, Q70 (2026-10-09): the four sentences that said "the technical
section" name it as the page and report.html do, "Technical details" - the
data-checks line and its "N of 3" form (Q59), the blocked line, and R1/R3's
row (stage 4; tests/stages/predict/test_q70_row_name.py). Stage 5 holds one
copy for report.html and the page. Written before the fix."""

import copy
from html import unescape

from stages.report.html_report import render_html
from tests.stages.report.html_probe import Page
from tests.stages.report.real_runs import RUNS, build_real, files


def test_the_data_checks_line_points_to_technical_details() -> None:
    report = build_real("kaggle")

    assert report.front.data_checks == ["Data checks passed (see Technical details)."]
    assert "Data checks passed (see Technical details)." in Page(render_html(report)).section("checked")


def test_the_count_form_points_to_technical_details() -> None:
    diagnosis = copy.deepcopy(files("kaggle")["diagnosis.json"])
    diagnosis["trust"]["checks"][1] |= {"status": "inconclusive", "message": "m"}

    assert build_real("kaggle", diagnosis=diagnosis).front.data_checks == [
        "Data checks passed (2 of 3 could run on this file; see Technical details)."]


def test_the_blocked_line_points_to_technical_details() -> None:
    from tests.contracts.test_diagnosis import diagnosis_payload
    from tests.stages.report.report_fixtures import build

    diagnosis = diagnosis_payload()
    diagnosis["trust"]["verdict"] = "blocked"
    diagnosis["trust"]["checks"][0] |= {"status": "blocked", "message": "m"}
    diagnosis.update({"calendar": None, "signals": None, "tree": None, "localization": None})
    diagnosis["headline"] = {"rule": 1, "hypothesis_id": None, "lens": None, "message": "m"}

    assert build(diagnosis=diagnosis).front.summary == [
        "The data cannot support conclusions: the data checks did not pass - see Technical details for which, "
        "and why."]


def test_no_front_sentence_says_the_technical_section() -> None:
    for run in RUNS:
        report = build_real(run)

        assert "technical section" not in str(report.front.model_dump()), run
        assert "technical section" not in unescape(Page(render_html(report)).front_text), run
