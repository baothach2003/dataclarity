"""POST /api/runs/{id}/report and GET /api/runs/{id}/download/report.html
(session 5C) - written before the code. Stage 5 writes report.json and
report.html from the run's files: allowed from `analyzed` once forecast.json
exists, the run stays `analyzed`; the recommendations only while the AI
step is on; the file's name from the run's row. The page downloads as an
attachment under a sanitized name.
"""

import json
import re
from typing import Any

from app.models import RunStatus
from contracts import ReportContract
from tests.ai_fakes import FakeResponse
from tests.backend.api_support import UNKNOWN_RUN, MakeApi, make_api_with_plan
from tests.backend.test_api_diagnose import _monthly_analyzed_run
from tests.backend.test_api_predict import ANSWER, _diagnosed


def _predicted(make_api: MakeApi, *answers: Any, **settings: Any) -> tuple[Any, str]:
    api, run_id = _diagnosed(make_api, *answers, **settings)
    assert api.post(run_id, "predict").status_code == 200
    return api, run_id


def _error(response: Any) -> tuple[int, str, dict[str, Any]]:
    error = response.json()["error"]
    return response.status_code, error["code"], error.get("details") or {}


# --- the report ----------------------------------------------------------------------------------


def test_report_writes_report_json_and_the_page(make_api: MakeApi) -> None:
    api, run_id = _predicted(make_api)
    calls = api.ai_requests

    response = api.post(run_id, "report")

    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["run_id"], body["status"], body["notices"]) == (run_id, "analyzed", [])
    assert body["html_url"] == f"/api/runs/{run_id}/download/report.html"
    report = ReportContract.model_validate(body["report"])
    assert report == ReportContract.model_validate(api.read_json(run_id, "report.json"))
    assert (report.run_id, report.source_file, report.schema_version) == (run_id, "sales.csv", "2.5")  # 2.5: the labels, evidence text and outside reasons; 2.4: the season
    # v1's default: the AI step is off - the page says so, whatever the file holds.
    assert report.layer_3_actions.recommendations_status == "switched_off"
    assert "<title>DataClarity report - sales.csv</title>" in api.file(run_id, "report.html").read_text(
        encoding="utf-8")
    assert api.ai_requests == calls  # stage 5 never calls the AI
    assert api.status(run_id) is RunStatus.ANALYZED


def test_the_recommendations_are_shown_while_the_step_is_on(make_api: MakeApi) -> None:
    api, run_id = _predicted(make_api, FakeResponse(json.dumps(ANSWER)), strategy_ai_enabled=True)

    report = ReportContract.model_validate(api.post(run_id, "report").json()["report"])

    assert report.layer_3_actions.recommendations_status == "shown"
    assert report.layer_3_actions.recommendations is not None and len(report.layer_3_actions.recommendations) == 3
    assert report.provenance.models_used == ["served-model"]


def test_report_again_replaces_both_files(make_api: MakeApi) -> None:
    api, run_id = _predicted(make_api)
    assert api.post(run_id, "report").status_code == 200
    api.file(run_id, "report.html").write_text("<p>stale", encoding="utf-8")

    assert api.post(run_id, "report").status_code == 200

    assert "<p>stale" not in api.file(run_id, "report.html").read_text(encoding="utf-8")
    assert not [name for name in api.files(run_id) if name.startswith(".aside-")]


# --- the order of the steps and the run's files -------------------------------------------------


def test_report_before_the_prediction_is_invalid_state(make_api: MakeApi) -> None:
    api, run_id = _diagnosed(make_api)

    response = api.post(run_id, "report")

    status, code, details = _error(response)
    assert (status, code, details["missing"]) == (409, "INVALID_STATE", "forecast.json")
    assert "Run the prediction first" in response.json()["error"]["message"]
    assert not {"report.json", "report.html"} & api.files(run_id)


def test_report_before_the_diagnosis_is_invalid_state(make_api: MakeApi) -> None:
    api, run_id = _monthly_analyzed_run(make_api)
    status, code, details = _error(api.post(run_id, "report"))
    assert (status, code, details["missing"]) == (409, "INVALID_STATE", "diagnosis.json")


def test_report_before_the_analysis_is_invalid_state(make_api: MakeApi) -> None:
    api, run_id, plan = make_api_with_plan(make_api)
    assert api.post(run_id, "execute", plan).status_code == 200
    status, code, details = _error(api.post(run_id, "report"))
    assert (status, code, details["status"]) == (409, "INVALID_STATE", "cleaned")


def test_report_on_an_unknown_run_is_not_found(make_api: MakeApi) -> None:
    response = make_api().post(UNKNOWN_RUN, "report")
    assert (response.status_code, response.json()["error"]["code"]) == (404, "NOT_FOUND")


def test_report_when_the_files_are_gone_is_expired(make_api: MakeApi) -> None:
    for name in ("metrics.json", "cleaning_report.json"):
        api, run_id = _predicted(make_api)
        api.file(run_id, name).unlink()
        assert _error(api.post(run_id, "report"))[1] == "EXPIRED"


def test_files_of_other_months_are_invalid_state(make_api: MakeApi) -> None:
    api, run_id = _predicted(make_api)
    diagnosis = api.read_json(run_id, "diagnosis.json")
    diagnosis["frame"]["current"], diagnosis["frame"]["previous"] = "2023-12", "2023-11"
    api.write_json(run_id, "diagnosis.json", diagnosis)

    status, code, details = _error(api.post(run_id, "report"))

    assert (status, code, details["reason"]) == (409, "INVALID_STATE", "files_mismatch")
    assert not {"report.json", "report.html"} & api.files(run_id)


def test_a_forecast_another_version_wrote_is_run_that_stage_again(make_api: MakeApi) -> None:
    api, run_id = _predicted(make_api)
    forecast = api.read_json(run_id, "forecast.json")
    forecast["schema_version"] = "9.0"
    api.write_json(run_id, "forecast.json", forecast)

    response = api.post(run_id, "report")

    assert _error(response)[:2] == (409, "INVALID_STATE")
    assert "Run the prediction again" in response.json()["error"]["message"]


def test_one_report_at_a_time(make_api: MakeApi) -> None:
    api, run_id = _predicted(make_api)
    with api.app.state.run_work.execution(run_id):
        response = api.post(run_id, "report")
    assert (response.status_code, response.json()["error"]["details"]["reason"]) == (409, "step_in_progress")


def test_a_re_analysis_sets_the_report_aside(make_api: MakeApi) -> None:
    # CONTRACTS 1: a stage run again removes the later stages' outputs.
    api, run_id = _predicted(make_api)
    assert api.post(run_id, "report").status_code == 200
    assert api.post(run_id, "analyze").status_code == 200
    assert not {"report.json", "report.html"} & api.files(run_id)


# --- the download ------------------------------------------------------------------------------


def test_the_page_downloads_as_an_attachment(make_api: MakeApi) -> None:
    api, run_id = _predicted(make_api)
    html_url = api.post(run_id, "report").json()["html_url"]

    response = api.get(run_id, "download/report.html")

    assert html_url.endswith("/download/report.html")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert response.headers["content-disposition"] == 'attachment; filename="report_sales.html"'
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.content == api.file(run_id, "report.html").read_bytes()


def test_the_page_downloads_from_an_imported_run_too(make_api: MakeApi) -> None:
    api, run_id = _predicted(make_api)
    assert api.post(run_id, "report").status_code == 200
    api.set_status(run_id, RunStatus.IMPORTED)
    assert api.get(run_id, "download/report.html").status_code == 200


def test_a_hostile_filename_is_escaped_on_the_page_and_sanitized_in_the_header(make_api: MakeApi) -> None:
    api, run_id = _monthly_analyzed_run(make_api, filename='sales"<b>x</b>; evil\r\nX-Injected: yes.csv')
    assert api.post(run_id, "diagnose").status_code == 200
    assert api.post(run_id, "predict").status_code == 200
    assert api.post(run_id, "report").status_code == 200

    response = api.get(run_id, "download/report.html")

    disposition = response.headers["content-disposition"]
    assert "\r" not in disposition and "\n" not in disposition
    assert re.fullmatch(r'attachment; filename="report_[A-Za-z0-9._-]+\.html"', disposition)
    assert "<b>x</b>" not in response.text and "&lt;b&gt;x&lt;/b&gt;" in response.text


def test_the_page_before_the_report_is_invalid_state(make_api: MakeApi) -> None:
    api, run_id = _predicted(make_api)
    response = api.get(run_id, "download/report.html")
    status, code, details = _error(response)
    assert (status, code, details["missing"]) == (409, "INVALID_STATE", "report.html")
    assert "Build the report first" in response.json()["error"]["message"]


def test_the_page_of_a_run_not_analyzed_is_invalid_state(make_api: MakeApi) -> None:
    api, run_id, plan = make_api_with_plan(make_api)
    assert api.post(run_id, "execute", plan).status_code == 200
    status, code, details = _error(api.get(run_id, "download/report.html"))
    assert (status, code, details["status"], "missing" in details) == (409, "INVALID_STATE", "cleaned", False)
    # A failed run's page is not served, even when it is on disk.
    api, run_id = _predicted(make_api)
    assert api.post(run_id, "report").status_code == 200
    api.set_status(run_id, RunStatus.FAILED)
    assert _error(api.get(run_id, "download/report.html"))[:2] == (409, "INVALID_STATE")


def test_the_page_of_an_unknown_run_is_not_found(make_api: MakeApi) -> None:
    assert make_api().get(UNKNOWN_RUN, "download/report.html").status_code == 404


# --- both files or neither -----------------------------------------------------------------------


def test_a_page_that_fails_leaves_no_half_report(make_api: MakeApi, monkeypatch: Any) -> None:
    # report.json is written first; if the page then fails, neither stands -
    # and a previous pair is put back whole.
    from stages.report import builder

    def broken(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("the page failed")

    api, run_id = _predicted(make_api)
    monkeypatch.setattr(builder, "html_run", broken)
    assert api.post(run_id, "report").status_code == 500
    assert not {"report.json", "report.html"} & api.files(run_id)

    monkeypatch.undo()
    assert api.post(run_id, "report").status_code == 200
    before = {name: api.file(run_id, name).read_bytes() for name in ("report.json", "report.html")}
    monkeypatch.setattr(builder, "html_run", broken)
    assert api.post(run_id, "report").status_code == 500
    assert {name: api.file(run_id, name).read_bytes() for name in ("report.json", "report.html")} == before
    assert not [name for name in api.files(run_id) if name.startswith(".aside-")]


def test_a_forecast_removed_as_the_report_starts_is_invalid_state_not_a_500(make_api: MakeApi,
                                                                            monkeypatch: Any) -> None:
    # Checked inside the exclusive block (4C review #3's race).
    from contextlib import contextmanager

    api, run_id = _predicted(make_api)
    work = api.app.state.run_work
    real = work.execution

    @contextmanager
    def removing(run: str):  # type: ignore[no-untyped-def]  # the patched method's own shape
        api.file(run_id, "forecast.json").unlink()
        with real(run):
            yield

    monkeypatch.setattr(work, "execution", removing)
    status, code, details = _error(api.post(run_id, "report"))
    assert (status, details["missing"]) == (409, "forecast.json")


# --- review 1's cases ----------------------------------------------------------------------------


def _rename_run_file(api: Any, run_id: str, filename: str) -> None:
    """A name the upload's client would percent-encode, set where the
    server keeps it (5C review #5: httpx never sends CR, LF or a quote)."""
    from sqlalchemy import update
    from sqlalchemy.orm import Session

    from app.models import Run

    with Session(api.engine) as session:
        session.execute(update(Run).where(Run.id == run_id).values(filename=filename))
        session.commit()


def test_a_run_whose_directory_is_gone_is_expired_on_every_path(make_api: MakeApi) -> None:
    # The retention cleanup removes the whole directory (review #2, #3).
    import shutil

    api, run_id = _predicted(make_api)
    assert api.post(run_id, "report").status_code == 200
    shutil.rmtree(api.runs_root / run_id)
    for response in (api.post(run_id, "report"), api.get(run_id, "download/report.html"),
                     api.get(run_id, "download/cleaned.csv")):
        assert (response.status_code, response.json()["error"]["code"]) == (410, "EXPIRED")


def test_a_page_set_aside_by_a_rebuild_says_wait_never_build_it(make_api: MakeApi) -> None:
    # Review #1: while a report is built again its page is set aside.
    api, run_id = _predicted(make_api)
    assert api.post(run_id, "report").status_code == 200
    api.file(run_id, "report.html").rename(api.file(run_id, ".aside-report.html"))
    with api.app.state.run_work.execution(run_id):
        response = api.get(run_id, "download/report.html")
    assert _error(response)[:2] == (409, "INVALID_STATE")
    assert response.json()["error"]["details"]["reason"] == "step_in_progress"


def test_the_cleaned_file_downloads_with_nosniff_too(make_api: MakeApi) -> None:
    api, run_id, plan = make_api_with_plan(make_api)
    assert api.post(run_id, "execute", plan).status_code == 200
    assert api.get(run_id, "download/cleaned.csv").headers["x-content-type-options"] == "nosniff"


def test_a_report_is_built_from_analyzed_only(make_api: MakeApi) -> None:
    api, run_id = _predicted(make_api)
    api.set_status(run_id, RunStatus.IMPORTED)
    status, code, details = _error(api.post(run_id, "report"))
    assert (status, code, details["status"]) == (409, "INVALID_STATE", "imported")


def test_a_name_with_nothing_safe_in_it_downloads_as_data(make_api: MakeApi) -> None:
    api, run_id = _predicted(make_api)
    _rename_run_file(api, run_id, "~.csv")
    assert api.post(run_id, "report").status_code == 200
    assert api.get(run_id, "download/report.html").headers["content-disposition"] == (
        'attachment; filename="report_data.html"')


def test_a_name_carrying_cr_lf_and_quotes_never_reaches_the_header(make_api: MakeApi) -> None:
    api, run_id = _predicted(make_api)
    _rename_run_file(api, run_id, 'sales"<b>x</b>; evil\r\nX-Injected: yes.csv')
    report = ReportContract.model_validate(api.post(run_id, "report").json()["report"])
    assert report.source_file == 'sales"<b>x</b>; evil\r\nX-Injected: yes.csv'

    response = api.get(run_id, "download/report.html")

    disposition = response.headers["content-disposition"]
    assert "x-injected" not in {name.lower() for name in response.headers}
    assert "\r" not in disposition and "\n" not in disposition and disposition.count('"') == 2
    assert re.fullmatch(r'attachment; filename="report_[A-Za-z0-9._-]+\.html"', disposition)
    assert "<b>x</b>" not in response.text and "&lt;b&gt;x&lt;/b&gt;" in response.text


def test_files_of_other_months_say_so_in_words(make_api: MakeApi) -> None:
    api, run_id = _predicted(make_api)
    diagnosis = api.read_json(run_id, "diagnosis.json")
    diagnosis["frame"]["current"], diagnosis["frame"]["previous"] = "2023-12", "2023-11"
    api.write_json(run_id, "diagnosis.json", diagnosis)
    message = api.post(run_id, "report").json()["error"]["message"]
    assert message.startswith("The run's files do not describe the same months: diagnosis.json describes 2023-12")
    assert message.endswith("run the diagnosis again.")


def test_a_cleaned_file_gone_from_its_directory_is_expired(make_api: MakeApi) -> None:
    api, run_id, plan = make_api_with_plan(make_api)
    assert api.post(run_id, "execute", plan).status_code == 200
    api.file(run_id, "cleaned.csv").unlink()
    assert _error(api.get(run_id, "download/cleaned.csv"))[:2] == (410, "EXPIRED")
