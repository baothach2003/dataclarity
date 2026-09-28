"""Session 2E-v (the scoped review of 2E-t1-t3's cycle-3 fixes, Thach,
2026-09-29), POST /analyze's side - written before the fixes.

#1  a month outside the two compared whose amounts overflow: 200, the run
    `analyzed`, and a metrics.json no reader could load. Now ANALYSIS_FAILED
    (amounts_too_large), nothing written, the run as it was.
#2  a run whose cleaning_report.json another version of the app wrote (an
    older major): a 500 with "An unexpected error occurred". Now EXPIRED
    (410) with the re-upload hint (SPECS section 10: no 500 for a problem the
    user can act on).
#4  "any other refusal is a bug: a 500" was pinned by no test.
Review cycle 2 #3: quantities too large to add (1e308 units at 1e-300, a
finite amount) overflowed a product's units and crashed stage 2 (a 500).
"""

import json
from typing import Any

import pandas as pd
import pytest
from pydantic import BaseModel, ValidationError

from app.models import RunStatus
from tests.backend.api_support import MakeApi, make_api_with_plan


def _cleaned_run(make_api: MakeApi) -> tuple[Any, str]:
    api, run_id, plan = make_api_with_plan(make_api)
    response = api.post(run_id, "execute", plan)
    assert response.status_code == 200, response.text
    return api, run_id


@pytest.mark.filterwarnings("ignore:overflow encountered:RuntimeWarning")  # the overflow is the case
def test_an_overflowing_month_outside_the_two_compared_is_analysis_failed(make_api: MakeApi) -> None:
    api, run_id = _cleaned_run(make_api)
    cleaned = api.file(run_id, "cleaned.csv")
    frame = pd.read_csv(cleaned, dtype=str)
    sales = frame.index[frame["line_class"].eq("sale")][:2]
    assert len(sales) == 2
    frame.loc[sales, "day"] = "2023-10-05"  # compared: 2023-12 against 2023-11 (the file ends mid-January)
    frame.loc[sales, "qty"] = "1"
    frame.loc[sales, "price"] = "1e308"
    frame.to_csv(cleaned, index=False)

    response = api.post(run_id, "analyze")

    assert response.status_code == 422, response.text
    error = response.json()["error"]
    assert (error["code"], error["details"]) == ("ANALYSIS_FAILED", {"reason": "amounts_too_large"})
    assert api.status(run_id) is RunStatus.CLEANED
    assert "metrics.json" not in api.files(run_id)


def test_a_run_written_by_an_earlier_version_is_expired_with_the_re_upload_hint(make_api: MakeApi) -> None:
    api, run_id = _cleaned_run(make_api)
    report_path = api.file(run_id, "cleaning_report.json")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["schema_version"] = "3.1"  # before the line taxonomy (2E-t1)
    report_path.write_text(json.dumps(report), encoding="utf-8")

    response = api.post(run_id, "analyze")

    assert response.status_code == 410, response.text
    error = response.json()["error"]
    assert error["code"] == "EXPIRED"
    assert error["details"] == {"reason": "another_version", "file": "cleaning_report.json"}
    assert "Upload the file again" in error["message"]
    assert api.status(run_id) is RunStatus.CLEANED


@pytest.mark.filterwarnings("ignore:overflow encountered:RuntimeWarning")  # the overflow is the case
def test_units_too_large_to_add_are_analysis_failed(make_api: MakeApi) -> None:
    api, run_id = _cleaned_run(make_api)
    cleaned = api.file(run_id, "cleaned.csv")
    frame = pd.read_csv(cleaned, dtype=str)
    same = frame.index[frame["line_class"].eq("sale")][:2]
    assert len(same) == 2
    frame.loc[same, frame.columns[:2]] = frame.loc[same[0], frame.columns[:2]].to_numpy()  # one product
    frame.loc[same, "day"] = "2023-12-05"  # the current month compared
    frame.loc[same, "qty"] = "1e308"
    frame.loc[same, "price"] = "1e-300"
    frame.to_csv(cleaned, index=False)

    response = api.post(run_id, "analyze")

    assert response.status_code == 422, response.text
    error = response.json()["error"]
    assert (error["code"], error["details"]) == ("ANALYSIS_FAILED", {"reason": "amounts_too_large"})
    # Says what is too large, and what to do (review cycle 3 #3).
    assert "amounts or quantities" in error["message"] and "upload it again" in error["message"]
    assert api.status(run_id) is RunStatus.CLEANED


class _Other(BaseModel):
    figure: int


def test_any_other_refusal_of_a_contract_stays_a_500(make_api: MakeApi, monkeypatch: pytest.MonkeyPatch) -> None:
    # A refusal that is neither "too large to add up" nor "another version"
    # is a bug in this code, never the user's to fix.
    api, run_id = _cleaned_run(make_api)

    def refused(*_args: Any, **_kwargs: Any) -> Any:
        try:
            _Other.model_validate({"figure": "not a number"})
        except ValidationError as error:
            raise error
        raise AssertionError("unreachable")

    monkeypatch.setattr("app.services.metrics.analyze_run", refused)

    response = api.post(run_id, "analyze")

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "INTERNAL_ERROR"
    assert api.status(run_id) is RunStatus.CLEANED
