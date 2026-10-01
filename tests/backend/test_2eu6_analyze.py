"""2E-u6 (Thach, 2026-10-02; 2E-u F6): POST /analyze judges the lines dated
after the upload against the RUN's upload time, not the wall clock - so a run
analysed again later gives the same answer. Written before the wiring."""

from datetime import UTC, date, datetime
from typing import Any

import pandas as pd
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.models import Run
from tests.backend.api_support import MakeApi, make_api_with_plan


def _cleaned_run(make_api: MakeApi) -> tuple[Any, str]:
    api, run_id, plan = make_api_with_plan(make_api)
    response = api.post(run_id, "execute", plan)
    assert response.status_code == 200, response.text
    return api, run_id


def test_a_line_after_the_upload_but_before_today_is_left_out(make_api: MakeApi) -> None:
    api, run_id = _cleaned_run(make_api)
    with Session(api.engine) as session:
        session.execute(update(Run).where(Run.id == run_id).values(created_at=datetime(2024, 2, 1, 8, tzinfo=UTC)))
        session.commit()
    cleaned = api.file(run_id, "cleaned.csv")
    frame = pd.read_csv(cleaned, dtype=str)
    before = api.post(run_id, "analyze").json()  # the file as uploaded: nothing after the upload
    assert before["metrics"]["core"]["future_lines"] == 0
    sale = frame.index[frame["line_class"].eq("sale")][0]
    frame.loc[sale, "day"] = "2024-06-01"  # after the upload, long before today
    frame.to_csv(cleaned, index=False)

    response = api.post(run_id, "analyze")

    assert response.status_code == 200, response.text
    metrics = response.json()["metrics"]
    assert metrics["period"]["upload_cutoff"] == str(date(2024, 2, 1))
    assert metrics["core"]["future_lines"] == 1
    assert metrics["period"]["current"] == before["metrics"]["period"]["current"]
