"""The three real runs' contract files as stage 5 reads them (the report
redesign, step 3; design section 9): Thach's Kaggle run and both Online
Retail II demo runs, copied with every product and category name replaced by
a neutral label (fixtures/; figures and codes as written)."""

import copy
import json
from pathlib import Path
from typing import Any

from contracts.cleaning import CleaningReportContract
from contracts.diagnosis import DiagnosisContract
from contracts.forecast import ForecastContract
from contracts.metrics import MetricsContract
from contracts.report import ReportContract
from stages.report.builder import build_report
from tests.stages.report.report_fixtures import NOW, RUN

FIXTURES = Path(__file__).with_name("fixtures")
RUNS = ("kaggle", "demo_classed", "demo_unanswered")
FILES = ("metrics.json", "diagnosis.json", "forecast.json", "cleaning_report.json")


def files(run: str) -> dict[str, dict[str, Any]]:
    return {name: json.loads((FIXTURES / run / name).read_text(encoding="utf-8")) for name in FILES}


def build_real(run: str, **replaced: dict[str, Any]) -> ReportContract:
    """The report of `run`, with any file given replaced (by its stem:
    metrics, diagnosis, forecast, cleaning)."""
    data = files(run)
    return build_report(
        run_id=RUN, source_file=f"{run}.csv",
        metrics=MetricsContract.model_validate(replaced.get("metrics", data["metrics.json"])),
        diagnosis=DiagnosisContract.model_validate(replaced.get("diagnosis", data["diagnosis.json"])),
        forecast=ForecastContract.model_validate(replaced.get("forecast", data["forecast.json"])),
        cleaning=CleaningReportContract.model_validate(replaced.get("cleaning", data["cleaning_report.json"])),
        schema=None, plan_source=None, include_recommendations=False, now=NOW)


def with_actions(run: str, status: str, actions: list[dict[str, Any]] | None = None,
                 model: str | None = None) -> dict[str, Any]:
    """`run`'s forecast.json at 2.1 with its actions in one of the three
    states (Thach: off, suppressed, list) - a fake file, no AI step."""
    forecast = copy.deepcopy(files(run)["forecast.json"])
    forecast |= {"schema_version": "2.1", "actions_status": status, "actions": actions, "actions_model": model}
    return forecast
