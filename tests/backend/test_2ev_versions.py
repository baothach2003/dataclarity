"""Session 2E-v review cycle 2 (fresh context, 2026-09-29): a run file another
version of the app wrote - `stage_errors.another_version` and POST /analyze.

#1  a run an older version really wrote has every file at its old major:
    analyze read schema_inference.json first, outside the mapping - a 500.
#4  the stale metrics.json branch and the file names were pinned by no test.
#5  a newer major was told nothing about what to do.
#6  the remedy follows the file: a stage 1 file means upload again (EXPIRED);
    a later stage's output means run that stage again (INVALID_STATE) -
    "upload again" was wrong for a metrics.json stage 2 can rewrite.
Review cycle 3: #1 only POST /analyze answered so - /plan, /execute and
/profile still gave a 500 (one handler for every endpoint now); #2 only
metrics.json was a later stage's (diagnosis, forecast and report too - each
contract says its file and the stage that writes it); #5 every older major
says what to do.
"""

import json
from typing import Any

import pytest
from pydantic import ValidationError

from app.models import RunStatus
from app.services import stage_errors
from contracts import (
    CleaningPlanContract,
    CleaningReportContract,
    DiagnosisContract,
    ForecastContract,
    ProfileContract,
    ReportContract,
    SchemaInferenceContract,
)
from contracts.metrics import MetricsContract
from tests.backend.api_support import MakeApi, analyzed_run, make_api_with_plan, planned, plan_reply, schema_reply


def _cleaned_run(make_api: MakeApi) -> tuple[Any, str]:
    api, run_id, plan = make_api_with_plan(make_api)
    response = api.post(run_id, "execute", plan)
    assert response.status_code == 200, response.text
    return api, run_id


def _set_version(api: Any, run_id: str, name: str, version: str) -> None:
    path = api.file(run_id, name)
    document = json.loads(path.read_text(encoding="utf-8"))
    document["schema_version"] = version
    path.write_text(json.dumps(document), encoding="utf-8")


def test_a_run_whose_every_stage_1_file_is_an_older_major_is_expired_not_a_500(make_api: MakeApi) -> None:
    api, run_id = _cleaned_run(make_api)
    for name in ("profile.json", "schema_inference.json", "plan_proposed.json", "plan_final.json",
                 "cleaning_report.json"):
        _set_version(api, run_id, name, "1.0")

    response = api.post(run_id, "analyze")

    assert response.status_code == 410, response.text
    error = response.json()["error"]
    assert (error["code"], error["details"]) == ("EXPIRED", {"reason": "another_version",
                                                             "file": "schema_inference.json"})
    assert "Upload the file again" in error["message"]
    assert api.status(run_id) is RunStatus.CLEANED


def _refusal(model: Any, document: dict[str, Any]) -> ValidationError:
    with pytest.raises(ValidationError) as caught:
        model.model_validate(document)
    return caught.value


def _metrics_document(api: Any, run_id: str) -> dict[str, Any]:
    response = api.post(run_id, "analyze")
    assert response.status_code == 200, response.text
    return response.json()["metrics"]


def test_a_metrics_json_from_before_the_line_taxonomy_asks_for_the_analysis_again(make_api: MakeApi) -> None:
    api, run_id = _cleaned_run(make_api)
    document = _metrics_document(api, run_id)
    del document["core"]["identity"]

    answer = stage_errors.another_version(_refusal(MetricsContract, document))

    assert answer is not None
    assert (answer.code, answer.details) == ("INVALID_STATE", {"reason": "another_version", "file": "metrics.json"})
    assert "Run the analysis again" in answer.message


def test_a_metrics_json_of_another_major_asks_for_the_analysis_again(make_api: MakeApi) -> None:
    api, run_id = _cleaned_run(make_api)
    for version in ("15.0", "17.0"):
        document = {**_metrics_document(api, run_id), "schema_version": version}
        answer = stage_errors.another_version(_refusal(MetricsContract, document))
        assert answer is not None and answer.code == "INVALID_STATE"
        assert answer.details == {"reason": "another_version", "file": "metrics.json"}


def test_a_stage_1_file_of_another_major_asks_for_the_file_again() -> None:
    answer = stage_errors.another_version(_refusal(CleaningReportContract, {"schema_version": "9.0"}))
    assert answer is not None
    assert (answer.code, answer.details) == ("EXPIRED", {"reason": "another_version",
                                                         "file": "cleaning_report.json"})
    answer = stage_errors.another_version(_refusal(SchemaInferenceContract, {"schema_version": "1.0"}))
    assert answer is not None and answer.details == {"reason": "another_version", "file": "schema_inference.json"}


@pytest.mark.parametrize(("model", "version", "name", "remedy"), [
    (DiagnosisContract, "16.0", "diagnosis.json", "Run the diagnosis again."),
    (ForecastContract, "0.9", "forecast.json", "Run the prediction again."),
    (ReportContract, "2.0", "report.json", "Build the report again."),
])
def test_every_later_stages_output_asks_for_its_stage_again(model: Any, version: str, name: str,
                                                           remedy: str) -> None:
    answer = stage_errors.another_version(_refusal(model, {"schema_version": version}))
    assert answer is not None
    assert (answer.code, answer.details) == ("INVALID_STATE", {"reason": "another_version", "file": name})
    assert answer.message.endswith(remedy)


def test_a_plan_of_another_major_asks_for_the_file_again_without_naming_one_file() -> None:
    # One model reads plan_proposed.json and plan_final.json.
    answer = stage_errors.another_version(_refusal(CleaningPlanContract, {"schema_version": "3.0"}))
    assert answer is not None and (answer.code, answer.details) == ("EXPIRED", {"reason": "another_version"})


def test_the_stages_file_names_are_the_contracts() -> None:
    from stages.analyze.assemble import METRICS_FILENAME
    from stages.ingest import ai_schema
    from stages.ingest.cleaning import REPORT_FILENAME
    from stages.ingest.profiling import PROFILE_FILENAME

    assert (ProfileContract.filename, SchemaInferenceContract.filename, CleaningReportContract.filename,
            MetricsContract.filename) == (PROFILE_FILENAME, ai_schema.OUTPUT_FILENAME, REPORT_FILENAME,
                                          METRICS_FILENAME)


@pytest.mark.parametrize(("model", "version", "hint"), [
    (ProfileContract, "0.9", "re-upload the file"),
    (ForecastContract, "0.9", "run the prediction again"),
    (ReportContract, "0.9", "build the report again"),
    (MetricsContract, "17.0", "upload the file again"),
])
def test_every_refusal_of_another_major_says_what_to_do(model: Any, version: str, hint: str) -> None:
    [problem] = [p for p in _refusal(model, {"schema_version": version}).errors() if p["loc"] == ("schema_version",)]
    assert hint in str(problem["msg"])


def test_plan_on_a_run_whose_schema_another_version_wrote_is_expired(make_api: MakeApi) -> None:
    api = make_api(schema_reply(), plan_reply())
    run_id = analyzed_run(api)
    _set_version(api, run_id, "schema_inference.json", "1.0")

    response = api.post(run_id, "plan")

    assert response.status_code == 410, response.text
    assert response.json()["error"]["details"] == {"reason": "another_version", "file": "schema_inference.json"}
    assert api.status(run_id) is RunStatus.PROFILED


def test_execute_on_a_run_whose_plan_another_version_wrote_is_expired(make_api: MakeApi) -> None:
    api = make_api(schema_reply(), plan_reply())
    run_id, plan = planned(api)
    _set_version(api, run_id, "plan_proposed.json", "1.0")

    response = api.post(run_id, "execute", plan)

    assert response.status_code == 410, response.text
    assert response.json()["error"]["code"] == "EXPIRED"
    assert api.status(run_id) is RunStatus.PLANNED


def test_the_profile_of_a_run_another_version_profiled_is_expired(make_api: MakeApi) -> None:
    api = make_api(schema_reply(), plan_reply())
    run_id = analyzed_run(api)
    _set_version(api, run_id, "profile.json", "2.0")  # a newer major

    response = api.get(run_id, "profile")

    assert response.status_code == 410, response.text
    assert response.json()["error"]["details"] == {"reason": "another_version", "file": "profile.json"}


def test_any_other_refusal_is_not_another_version() -> None:
    assert stage_errors.another_version(_refusal(CleaningReportContract, {"schema_version": "4.0"})) is None


def test_a_newer_major_is_told_a_newer_version_wrote_it_and_what_to_do() -> None:
    [problem] = [p for p in _refusal(CleaningReportContract, {"schema_version": "9.0"}).errors()
                 if p["loc"] == ("schema_version",)]
    assert "a newer version of DataClarity" in str(problem["msg"])
