"""POST /api/runs/{id}/diagnose (session 3G-lite, Thach, 2026-09-29) -
written before the code. Stage 3 in the designed degraded mode: no AI call,
`ai_findings` and `model_used` null, the code-written headline stands
(docs/AI_PIPELINE.md section 9). Allowed from `analyzed`, which the run
keeps: stages 2-4 all live in it (SPECS section 3). One piece of work at a
time per run; a re-run overwrites only diagnosis.json.
"""

import json
import threading
from typing import Any

import pandas as pd
import pytest

from app.models import RunStatus
from contracts import DiagnosisContract
from tests.backend.api_support import UNKNOWN_RUN, MakeApi, make_api_with_plan


def _analyzed_run(make_api: MakeApi) -> tuple[Any, str]:
    api, run_id, plan = make_api_with_plan(make_api)
    assert api.post(run_id, "execute", plan).status_code == 200
    assert api.post(run_id, "analyze").status_code == 200
    return api, run_id


def test_diagnose_writes_the_diagnosis_and_the_run_stays_analyzed(make_api: MakeApi) -> None:
    api, run_id = _analyzed_run(make_api)

    response = api.post(run_id, "diagnose")

    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["run_id"], body["status"], body["notices"]) == (run_id, "analyzed", [])
    diagnosis = DiagnosisContract.model_validate(body["diagnosis"])
    assert diagnosis == DiagnosisContract.model_validate(api.read_json(run_id, "diagnosis.json"))
    assert (diagnosis.model_used, diagnosis.ai_findings) == (None, None)
    assert diagnosis.schema_version == "18.1"  # 18.1 since 2026-10-03: hypotheses_note
    assert api.status(run_id) is RunStatus.ANALYZED


def test_diagnose_again_overwrites_only_the_diagnosis(make_api: MakeApi) -> None:
    api, run_id = _analyzed_run(make_api)
    assert api.post(run_id, "diagnose").status_code == 200
    metrics = api.file(run_id, "metrics.json").read_bytes()

    again = api.post(run_id, "diagnose")

    assert again.status_code == 200
    assert api.file(run_id, "metrics.json").read_bytes() == metrics
    assert api.status(run_id) is RunStatus.ANALYZED


def test_diagnose_before_the_analysis_is_invalid_state(make_api: MakeApi) -> None:
    api, run_id, plan = make_api_with_plan(make_api)
    assert api.post(run_id, "execute", plan).status_code == 200

    response = api.post(run_id, "diagnose")

    assert response.status_code == 409
    error = response.json()["error"]
    assert (error["code"], error["details"]["status"]) == ("INVALID_STATE", "cleaned")
    assert "diagnosis.json" not in api.files(run_id)


def test_diagnose_on_an_unknown_run_is_not_found(make_api: MakeApi) -> None:
    response = make_api().post(UNKNOWN_RUN, "diagnose")
    assert (response.status_code, response.json()["error"]["code"]) == (404, "NOT_FOUND")


def test_diagnose_when_the_metrics_are_gone_is_expired(make_api: MakeApi) -> None:
    api, run_id = _analyzed_run(make_api)
    api.file(run_id, "metrics.json").unlink()

    response = api.post(run_id, "diagnose")

    assert (response.status_code, response.json()["error"]["code"]) == (410, "EXPIRED")


def test_diagnose_on_metrics_another_version_wrote_asks_for_the_analysis_again(make_api: MakeApi) -> None:
    api, run_id = _analyzed_run(make_api)
    metrics = api.read_json(run_id, "metrics.json")
    metrics["schema_version"] = "15.0"
    api.write_json(run_id, "metrics.json", metrics)

    response = api.post(run_id, "diagnose")

    assert response.status_code == 409, response.text
    error = response.json()["error"]
    assert (error["code"], error["details"]) == ("INVALID_STATE", {"reason": "another_version", "file": "metrics.json"})
    assert "Run the analysis again" in error["message"]
    assert api.status(run_id) is RunStatus.ANALYZED


def test_diagnose_on_a_cleaned_file_whose_classes_were_changed_is_analysis_failed(make_api: MakeApi) -> None:
    api, run_id = _analyzed_run(make_api)
    cleaned = api.file(run_id, "cleaned.csv")
    frame = pd.read_csv(cleaned, dtype=str)
    frame.loc[0, "line_class"] = "fee"
    frame.to_csv(cleaned, index=False)

    response = api.post(run_id, "diagnose")

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "ANALYSIS_FAILED" and "re-upload" in error["message"]
    assert api.status(run_id) is RunStatus.ANALYZED


def test_a_second_diagnose_during_the_first_is_refused_not_raced(make_api: MakeApi,
                                                                 monkeypatch: pytest.MonkeyPatch) -> None:
    api, run_id = _analyzed_run(make_api)
    from stages.diagnose import assemble

    real = assemble.diagnose_run
    inside, proceed = threading.Event(), threading.Event()

    def slow(*args: Any, **kwargs: Any) -> Any:
        inside.set()
        assert proceed.wait(timeout=10), "the test never released the first diagnose"
        return real(*args, **kwargs)

    monkeypatch.setattr("app.services.diagnosis.diagnose_run", slow)
    first: dict[str, Any] = {}
    worker = threading.Thread(target=lambda: first.update(response=api.post(run_id, "diagnose")))
    worker.start()
    assert inside.wait(timeout=10)

    second = api.post(run_id, "diagnose")
    proceed.set()
    worker.join(timeout=20)

    assert second.status_code == 409
    assert second.json()["error"]["details"]["reason"] == "step_in_progress"
    assert first["response"].status_code == 200


def test_the_diagnosis_is_json_the_contract_reads(make_api: MakeApi) -> None:
    api, run_id = _analyzed_run(make_api)
    body = api.post(run_id, "diagnose").json()
    assert json.loads(json.dumps(body["diagnosis"])) == api.read_json(run_id, "diagnosis.json")


# --- review 1 (fresh context, 2026-09-29) -----------------------------------------------------------


def _monthly_csv(price: str = "10") -> bytes:
    """Two products sold every day from January 2023 to 10 March 2024: the
    trust gate passes (a complete previous month, a year of history), so the
    diagnosis carries every block (review 1 #5: the one-month fixture always
    blocked)."""
    days = pd.date_range("2023-01-01", "2024-03-10", freq="D")
    lines = ["sku,name,qty,price,day"]
    for day in days:
        lines.append(f"A1,Mug,{2 + day.day % 3},{price},{day.date()}")
        lines.append(f"B2,Cup,1,4.50,{day.date()}")
    return ("\n".join(lines) + "\n").encode()


_MANUAL = [("sku", "identifier", "sku"), ("name", "text", "product_name"), ("qty", "numeric_discrete", "quantity"),
           ("price", "numeric_continuous", "unit_price"), ("day", "datetime", "transaction_date")]


def _monthly_analyzed_run(make_api: MakeApi, content: bytes | None = None, filename: str = "sales.csv",
                          **settings: Any) -> tuple[Any, str]:
    """Through the no-AI path: profiled, then a plan built by hand (the fake
    AI's answers are written for the one-month fixture)."""
    from tests.backend.api_support import unusable_reply

    api = make_api(unusable_reply(), unusable_reply(), **settings)  # the AI answers nothing usable: degraded
    run_id = api.upload(content or _monthly_csv(), filename=filename)
    assert api.post(run_id, "analyze-schema").status_code == 200  # profiles; the AI is unavailable
    plan = {"schema_version": "4.0", "generated_at": "2026-09-29T00:00:00Z", "source": "manual",
            "dataset_actions": [],
            "column_actions": [{"source_name": n, "semantic_type": t, "canonical_field": f, "action": "flag_only",
                                "params": {"note": ""}, "rationale": "", "alternatives": [], "edited_by_user": True}
                               for n, t, f in _MANUAL]}
    executed = api.post(run_id, "execute", plan)
    assert executed.status_code == 200, executed.text
    assert api.post(run_id, "analyze").status_code == 200, "the fixture must analyze"
    return api, run_id


def test_a_diagnosis_with_every_block_goes_through_the_answer(make_api: MakeApi) -> None:
    api, run_id = _monthly_analyzed_run(make_api)

    response = api.post(run_id, "diagnose")

    assert response.status_code == 200, response.text
    diagnosis = DiagnosisContract.model_validate(response.json()["diagnosis"])
    assert diagnosis.trust.verdict != "blocked"
    assert None not in (diagnosis.calendar, diagnosis.signals, diagnosis.tree, diagnosis.localization)
    assert response.json()["diagnosis"] == api.read_json(run_id, "diagnosis.json")


@pytest.mark.filterwarnings("ignore:overflow encountered:RuntimeWarning")  # the overflow is the case
@pytest.mark.filterwarnings("ignore:invalid value encountered:RuntimeWarning")
def test_amounts_stage_3_cannot_multiply_out_are_analysis_failed(make_api: MakeApi) -> None:
    # #1: lines of 1e160 are finite to stage 2, but stage 3's attribution
    # multiplies them past a float: a 500 before.
    content = _monthly_csv().replace(b"A1,Mug,2,10,2024-02-", b"A1,Mug,2,1e160,2024-02-")
    api, run_id = _monthly_analyzed_run(make_api, content)

    response = api.post(run_id, "diagnose")

    assert response.status_code == 422, response.text
    error = response.json()["error"]
    assert (error["code"], error["details"]) == ("ANALYSIS_FAILED", {"reason": "amounts_too_large"})
    assert "diagnosis.json" not in api.files(run_id)
    assert api.status(run_id) is RunStatus.ANALYZED


def test_a_diagnose_during_an_analysis_is_refused(make_api: MakeApi, monkeypatch: pytest.MonkeyPatch) -> None:
    # #5: one piece of work at a time per run, across the two steps.
    api, run_id = _analyzed_run(make_api)
    from stages.analyze import assemble

    real = assemble.analyze_run
    inside, proceed = threading.Event(), threading.Event()

    def slow(*args: Any, **kwargs: Any) -> Any:
        inside.set()
        assert proceed.wait(timeout=10), "the test never released the analysis"
        return real(*args, **kwargs)

    monkeypatch.setattr("app.services.metrics.analyze_run", slow)
    first: dict[str, Any] = {}
    worker = threading.Thread(target=lambda: first.update(response=api.post(run_id, "analyze")))
    worker.start()
    assert inside.wait(timeout=10)

    during = api.post(run_id, "diagnose")
    proceed.set()
    worker.join(timeout=20)

    assert during.status_code == 409
    assert during.json()["error"]["details"]["reason"] == "step_in_progress"
    assert first["response"].status_code == 200


def test_analysing_again_removes_the_diagnosis_it_made_stale(make_api: MakeApi) -> None:
    # #2: a re-analysis rewrites metrics.json; a diagnosis of the old one
    # would stand beside it, its headline about other figures.
    api, run_id = _analyzed_run(make_api)
    assert api.post(run_id, "diagnose").status_code == 200
    api.file(run_id, "forecast.json").write_text("{}", encoding="utf-8")  # a later stage's output

    assert api.post(run_id, "analyze").status_code == 200

    assert {"diagnosis.json", "forecast.json"} & api.files(run_id) == set()
    assert api.post(run_id, "diagnose").status_code == 200


def test_diagnosing_again_removes_the_later_outputs(make_api: MakeApi) -> None:
    api, run_id = _analyzed_run(make_api)
    api.file(run_id, "forecast.json").write_text("{}", encoding="utf-8")
    api.file(run_id, "report.html").write_text("<html></html>", encoding="utf-8")

    assert api.post(run_id, "diagnose").status_code == 200

    assert {"forecast.json", "report.html"} & api.files(run_id) == set()
    assert {"metrics.json", "diagnosis.json"} <= api.files(run_id)


def test_a_diagnosis_that_fails_removes_nothing(make_api: MakeApi, monkeypatch: pytest.MonkeyPatch) -> None:
    api, run_id = _analyzed_run(make_api)
    api.file(run_id, "forecast.json").write_text("{}", encoding="utf-8")

    def broken(*_args: Any, **_kwargs: Any) -> Any:
        from shared.transactions import LineClassColumnsError

        raise LineClassColumnsError("line_class")

    monkeypatch.setattr("app.services.diagnosis.diagnose_run", broken)
    assert api.post(run_id, "diagnose").status_code == 422
    assert "forecast.json" in api.files(run_id)

