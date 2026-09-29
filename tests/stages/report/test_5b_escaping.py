"""Session 5B: SPECS SEC-3 as extended in 5B - every string report.html
takes from report.json is escaped (text from the AI and from the uploaded
file alike), and its charts carry only months and numbers; report.html is
written atomically beside report.json."""

import json
from pathlib import Path
from typing import Any

import pytest

from contracts.report import ReportContract
from stages.report.builder import report_run
from stages.report.html_report import html_run, render_html
from tests.stages.report.html_probe import Page
from tests.stages.report.report_fixtures import NOW, RUN, build, metrics_data, run_dir

SCRIPT = "<script>alert(1)</script>"
IMG = "<img src=x onerror=alert(2)>"


def _hostile() -> ReportContract:
    """A report whose every free-text field carries markup: the file's name,
    the AI's narration and recommendations, a trust message, a hypothesis's
    statement and evidence, a product in the suggested classes."""
    payload: dict[str, Any] = build().model_dump(mode="json")
    payload["source_file"] = f"</title><script>alert(3)</script><b>shop</b>{IMG}.csv"
    causes = payload["layer_2_causes"]
    causes["narration"]["summary"] = SCRIPT
    causes["narration"]["hypothesis_notes"][0]["text"] = f"</script>{SCRIPT}"
    causes["hypotheses"][0]["statement"] = IMG
    causes["hypotheses"][0]["evidence"] = {"top_member": f"</script>{IMG}"}
    causes["headline"]["message"] = f"<iframe src=//x>{SCRIPT}"
    payload["layer_1_numbers"]["trust"]["checks"][0]["message"] = IMG
    payload["layer_3_actions"]["recommendations"][0]["action"] = SCRIPT
    payload["layer_3_actions"]["do_not_do"][0]["tempting_action"] = IMG
    return ReportContract.model_validate(payload)


def test_every_string_from_the_file_or_the_ai_is_escaped() -> None:
    html = render_html(_hostile())
    page = Page(html)
    tags = {name for name, _ in page.tags}
    assert not tags & {"b", "img", "iframe"}
    assert len(page.scripts) == 3  # plotly.js and the two charts - none of the file's
    assert "alert(" not in "".join(page.scripts)
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html and "&lt;img src=x onerror=alert(2)&gt;" in html
    assert SCRIPT in page.text and IMG in page.text  # shown as text, as written


def test_the_charts_carry_only_months_and_numbers() -> None:
    # A gap stays a null point - never a zero, never a join.
    metrics = metrics_data(months=(("2011-08", 900000.0), ("2011-10", 1290000.0), ("2011-11", 1150000.0),
                                   ("2011-12", 300000.0)))
    page = Page(render_html(build(metrics=metrics)))
    trend = next(s for s in page.scripts if '"chart-revenue_trend"' in s)
    assert '"x":["2011-08","2011-09","2011-10","2011-11"]' in trend
    assert '"y":[900000.0,null,1290000.0,1150000.0]' in trend
    assert "connectgaps\":false" in trend
    forecast = next(s for s in page.scripts if '"chart-forecast"' in s)
    assert '"y":[1210000.0,730000.0,640000.0]' in forecast


def test_a_chart_month_that_is_not_a_month_is_refused() -> None:
    # Plotly draws its own markup in labels: nothing but YYYY-MM reaches it.
    payload: dict[str, Any] = build().model_dump(mode="json")
    report = ReportContract.model_validate(payload)
    report.charts[0].series[0].x[0] = "<b>2011-09</b>"
    with pytest.raises(ValueError, match="months"):
        render_html(report)


def test_a_chart_shows_its_gap_note_its_cautions_and_its_notes_beside_it() -> None:
    metrics = metrics_data(months=(("2011-08", 900000.0), ("2011-10", 1290000.0), ("2011-11", 1150000.0),
                                   ("2011-12", 300000.0)))
    numbers = Page(render_html(build(metrics=metrics))).section("numbers")
    assert "No line counted in revenue is dated in 2011-09" in numbers
    assert "Caution: About 5 days in the current month" in numbers


def test_html_run_writes_report_html_and_a_failed_write_leaves_the_old_one(tmp_path: Path) -> None:
    run = run_dir(tmp_path)
    report = report_run(tmp_path, RUN, source_file="sales_2011.csv", include_recommendations=True, now=NOW)
    path = html_run(tmp_path, RUN)
    assert path == run / "report.html"
    assert path.read_text(encoding="utf-8") == render_html(report)
    before = path.read_bytes()

    class Refused(Exception):
        pass

    def refuse() -> None:
        raise Refused

    (run / "report.json").write_text(json.dumps(report.model_dump(mode="json") | {"source_file": "other.csv"}),
                                     encoding="utf-8")
    with pytest.raises(Refused):
        html_run(tmp_path, RUN, around_write=refuse)
    assert path.read_bytes() == before
