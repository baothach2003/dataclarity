"""Session 4A-b, review 2: files the ninth run's version wrote, in their real
shape - a forecast.json 1.0 without `season_years`, a report.json 1.0 whose
forecast view has none - are answered "run that stage again", never shown
as if current (CONTRACTS 1 and 10): a two-year season would reach the page
without its note."""

from typing import Any

import pytest

from tests.backend.test_api_report import _error, _predicted


def _as_written_before(data: dict[str, Any], view: str) -> dict[str, Any]:
    """The 1.x shape: the version before 4A-b had no `season_years`."""
    data["schema_version"] = "1.0"
    shown = data[view] if view == "forecast" else data[view]["forecast"]
    del shown["season_years"]
    return data


def test_a_forecast_of_the_version_before_is_run_the_prediction_again(make_api: Any) -> None:
    api, run_id = _predicted(make_api)
    api.write_json(run_id, "forecast.json", _as_written_before(api.read_json(run_id, "forecast.json"), "forecast"))

    response = api.post(run_id, "report")

    status, code, details = _error(response)
    assert (status, code, details["reason"], details["file"]) == (409, "INVALID_STATE", "another_version",
                                                                   "forecast.json")
    assert "Run the prediction again" in response.json()["error"]["message"]
    assert not api.file(run_id, "report.json").exists()


def test_the_page_of_a_report_of_the_version_before_is_build_the_report_again(make_api: Any) -> None:
    # Review 2 #1: the page has no version of its own - it is report.json
    # rendered, so it follows report.json's.
    api, run_id = _predicted(make_api)
    assert api.post(run_id, "report").status_code == 200
    api.write_json(run_id, "report.json", _as_written_before(api.read_json(run_id, "report.json"),
                                                             "layer_3_actions"))

    response = api.get(run_id, "download/report.html")

    status, code, details = _error(response)
    assert (status, code, details["reason"], details["file"]) == (409, "INVALID_STATE", "another_version",
                                                                   "report.json")
    assert "Build the report again" in response.json()["error"]["message"]
    # Built again, it downloads.
    assert api.post(run_id, "report").status_code == 200
    assert api.get(run_id, "download/report.html").status_code == 200


def test_the_page_of_a_report_json_of_a_newer_major_or_none_is_refused_too(make_api: Any) -> None:
    api, run_id = _predicted(make_api)
    assert api.post(run_id, "report").status_code == 200
    report = api.read_json(run_id, "report.json")
    for written, reason in (('{"schema_version": "9.0"}', "another_version"), ("not json", "unreadable"),
                            ('{"no": "version"}', "another_version")):  # review 4 #8: not JSON is unreadable
        api.file(run_id, "report.json").write_text(written, encoding="utf-8")
        response = api.get(run_id, "download/report.html")
        assert _error(response)[:2] == (409, "INVALID_STATE"), written
        assert response.json()["error"]["details"]["reason"] == reason, written
    api.write_json(run_id, "report.json", report)
    assert api.get(run_id, "download/report.html").status_code == 200


# --- review 3 ------------------------------------------------------------------------------------


def test_a_page_of_the_version_before_names_the_earliest_file_to_run_again(make_api: Any) -> None:
    # Review 3 #1: a report.json 1.x always sits on a forecast.json 1.x (a
    # prediction run again removes the report), and "build the report again"
    # would then be refused - the answer is the first step that works.
    api, run_id = _predicted(make_api)
    assert api.post(run_id, "report").status_code == 200
    api.write_json(run_id, "forecast.json", _as_written_before(api.read_json(run_id, "forecast.json"), "forecast"))
    api.write_json(run_id, "report.json", _as_written_before(api.read_json(run_id, "report.json"),
                                                             "layer_3_actions"))

    response = api.get(run_id, "download/report.html")

    status, code, details = _error(response)
    assert (status, code, details["reason"], details["file"]) == (409, "INVALID_STATE", "another_version",
                                                                   "forecast.json")
    assert "Run the prediction again" in response.json()["error"]["message"]
    assert api.post(run_id, "predict").status_code == 200
    assert api.post(run_id, "report").status_code == 200
    assert api.get(run_id, "download/report.html").status_code == 200


def test_a_page_of_the_version_before_during_a_build_says_wait(make_api: Any) -> None:
    # Review 3 #2 (5C review #1's rule): while a step runs on the run, the
    # page is "wait", never "build it" - building then is refused.
    api, run_id = _predicted(make_api)
    assert api.post(run_id, "report").status_code == 200
    api.write_json(run_id, "report.json", _as_written_before(api.read_json(run_id, "report.json"),
                                                             "layer_3_actions"))
    with api.app.state.run_work.execution(run_id):
        response = api.get(run_id, "download/report.html")
    assert _error(response)[:2] == (409, "INVALID_STATE")
    assert response.json()["error"]["details"] == {"reason": "step_in_progress"}
    assert "Wait for it to finish" in response.json()["error"]["message"]


def test_a_report_json_that_cannot_be_read_is_never_a_500(make_api: Any) -> None:
    # Review 3 #7: nested past the parser's depth, it raised RecursionError.
    api, run_id = _predicted(make_api)
    assert api.post(run_id, "report").status_code == 200
    api.file(run_id, "report.json").write_text("[" * 100000 + "]" * 100000, encoding="utf-8")
    response = api.get(run_id, "download/report.html")
    assert _error(response)[:2] == (409, "INVALID_STATE")
    assert response.json()["error"]["details"]["reason"] == "unreadable"  # review 4 #8


def test_the_wait_never_says_the_report_is_being_built_when_another_step_runs(make_api: Any) -> None:
    # Review 3 #9: a re-run of stage 2, 3 or 4 also holds the run, and it
    # removes the report rather than building it.
    api, run_id = _predicted(make_api)
    assert api.post(run_id, "report").status_code == 200
    api.file(run_id, "report.html").rename(api.file(run_id, ".aside-report.html"))
    with api.app.state.run_work.execution(run_id):
        response = api.get(run_id, "download/report.html")
    message = response.json()["error"]["message"]
    assert "being built" not in message and "Wait for it to finish" in message


def test_the_earliest_stale_file_is_named_in_stage_order(make_api: Any) -> None:
    # Two files of another version: running the later stage first would be
    # refused for the earlier one's file - the analysis comes first.
    api, run_id = _predicted(make_api)
    assert api.post(run_id, "report").status_code == 200
    for name in ("metrics.json", "forecast.json", "report.json"):
        api.write_json(run_id, name, api.read_json(run_id, name) | {"schema_version": "9.0"})
    response = api.get(run_id, "download/report.html")
    assert response.json()["error"]["details"]["file"] == "metrics.json"
    assert "Run the analysis again" in response.json()["error"]["message"]


# --- review 4 (scoped, the late fixes) -------------------------------------------------------------


def _stale_report(api: Any, run_id: str) -> None:
    api.write_json(run_id, "report.json", _as_written_before(api.read_json(run_id, "report.json"),
                                                             "layer_3_actions"))


def test_a_stale_page_answers_a_missing_earlier_file_as_the_report_does(make_api: Any) -> None:
    # Review 4 #1: "build the report again" was refused for the missing file.
    for gone, expected in (("cleaning_report.json", (410, "EXPIRED")), ("diagnosis.json", (409, "INVALID_STATE"))):
        api, run_id = _predicted(make_api)
        assert api.post(run_id, "report").status_code == 200
        _stale_report(api, run_id)
        api.file(run_id, gone).unlink()
        download, build = api.get(run_id, "download/report.html"), api.post(run_id, "report")
        assert _error(download)[:2] == _error(build)[:2] == expected, gone
        assert download.json()["error"]["message"] == build.json()["error"]["message"]


@pytest.mark.parametrize("name,code,remedy", [
    ("cleaning_report.json", "EXPIRED", "Upload the file again"),
    ("diagnosis.json", "INVALID_STATE", "Run the diagnosis again"),
])
def test_every_file_the_report_is_built_from_is_checked(make_api: Any, name: str, code: str, remedy: str) -> None:
    # Review 4 #6: a stage 1 file of another version is uploaded again (SPECS 10).
    api, run_id = _predicted(make_api)
    assert api.post(run_id, "report").status_code == 200
    _stale_report(api, run_id)
    api.write_json(run_id, name, api.read_json(run_id, name) | {"schema_version": "9.0"})
    response = api.get(run_id, "download/report.html")
    assert (response.json()["error"]["code"], response.json()["error"]["details"]["file"]) == (code, name)
    assert remedy in response.json()["error"]["message"]


def test_the_files_checked_are_the_ones_the_report_needs() -> None:
    # Review 4 #6: one list, not two that drift.
    from app.services import reporting

    assert ({str(model.filename) for model in reporting._BUILT_FROM}
            == {*reporting._GONE_WITHOUT, *(name for name, _ in reporting._FIRST)})


def test_wait_is_decided_last(make_api: Any, monkeypatch: Any) -> None:
    # Review 4 #4: a step that takes the run while the files are read is
    # "wait" too - checked once, first, it was missed.
    from app.services import reporting

    api, run_id = _predicted(make_api)
    assert api.post(run_id, "report").status_code == 200
    _stale_report(api, run_id)
    work = api.app.state.run_work
    read = reporting._major

    def major_while_a_step_starts(runs_root: Any, run: str, name: str) -> Any:
        if name == "forecast.json":
            monkeypatch.setattr(work, "is_active", lambda _: True)
        return read(runs_root, run, name)

    monkeypatch.setattr(reporting, "_major", major_while_a_step_starts)
    response = api.get(run_id, "download/report.html")
    assert response.json()["error"]["details"] == {"reason": "step_in_progress"}


def test_a_report_json_that_cannot_be_read_says_so(make_api: Any, monkeypatch: Any) -> None:
    # Review 4 #8: not "another version" - and a lock (OSError) never a 500 (#6).
    from pathlib import Path

    api, run_id = _predicted(make_api)
    assert api.post(run_id, "report").status_code == 200
    api.file(run_id, "report.json").write_text('{"schema_version": "2.0", "cut sho', encoding="utf-8")
    response = api.get(run_id, "download/report.html")
    assert _error(response)[:2] == (409, "INVALID_STATE")
    assert response.json()["error"]["details"] == {"reason": "unreadable", "file": "report.json"}
    assert "cannot be read" in response.json()["error"]["message"]
    assert api.post(run_id, "report").status_code == 200
    original = Path.read_text

    def locked(self: Path, *args: Any, **kwargs: Any) -> str:
        if self.name == "report.json":
            raise PermissionError("held by another program")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", locked)
    response = api.get(run_id, "download/report.html")
    assert response.json()["error"]["details"]["reason"] == "unreadable"


def test_a_page_with_no_report_json_is_never_served(make_api: Any) -> None:
    # Review 4 #7: no report.json, no version to show the page under.
    api, run_id = _predicted(make_api)
    assert api.post(run_id, "report").status_code == 200
    api.file(run_id, "report.json").unlink()
    response = api.get(run_id, "download/report.html")
    assert _error(response)[:2] == (409, "INVALID_STATE")
    assert "Build the report again" in response.json()["error"]["message"]


def test_a_page_that_cannot_be_read_is_never_a_500(make_api: Any) -> None:
    # Review 4 #3.
    api, run_id = _predicted(make_api)
    assert api.post(run_id, "report").status_code == 200
    api.file(run_id, "report.html").unlink()
    api.file(run_id, "report.html").mkdir()
    response = api.get(run_id, "download/report.html")
    assert _error(response)[:2] == (409, "INVALID_STATE")
    assert response.json()["error"]["details"] == {"reason": "unreadable", "file": "report.html"}


def test_a_run_directory_gone_while_the_files_are_read_is_expired(make_api: Any, monkeypatch: Any) -> None:
    # Review 4 #6 (M7): the retention cleanup between two reads.
    from app.services import reporting
    from shared.run_registry import RunNotFoundError

    api, run_id = _predicted(make_api)
    assert api.post(run_id, "report").status_code == 200
    _stale_report(api, run_id)
    read = reporting._major

    def gone_at_the_forecast(runs_root: Any, run: str, name: str) -> Any:
        if name == "forecast.json":
            raise RunNotFoundError(run)
        return read(runs_root, run, name)

    monkeypatch.setattr(reporting, "_major", gone_at_the_forecast)
    response = api.get(run_id, "download/report.html")
    assert _error(response)[:2] == (410, "EXPIRED")


def test_an_earlier_file_that_cannot_be_read_falls_to_the_report(make_api: Any) -> None:
    # A file this version wrote cannot be half written (atomic writes): a
    # corrupt one is hand-made, and the build answers it (8D "From 5C").
    api, run_id = _predicted(make_api)
    assert api.post(run_id, "report").status_code == 200
    _stale_report(api, run_id)
    api.file(run_id, "metrics.json").write_text("{", encoding="utf-8")
    response = api.get(run_id, "download/report.html")
    assert (response.status_code, response.json()["error"]["details"]) == (
        409, {"reason": "another_version", "file": "report.json"})  # report.json read fine: it is stale
