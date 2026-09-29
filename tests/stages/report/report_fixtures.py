"""Hand-built contract files for stage 5's tests (session 5A), and the report
built from them. Every expected value in the tests is a field of these."""

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from contracts.cleaning import CleaningPlanContract, CleaningReportContract
from contracts.diagnosis import DiagnosisContract
from contracts.forecast import ForecastContract
from contracts.lines import NOTE_FIGURES
from contracts.metrics import MetricsContract
from contracts.profile import SchemaInferenceContract
from contracts.report import ReportContract
from stages.report.builder import build_report
from tests.contracts.test_cleaning import plan_payload
from tests.contracts.test_cleaning import report_payload as cleaning_report_payload
from tests.contracts.test_diagnosis import diagnosis_payload
from tests.contracts.test_forecast import forecast_payload
from tests.contracts.test_metrics import metrics_payload
from tests.contracts.test_profile import inference_payload

NOW = datetime(2026, 9, 29, tzinfo=UTC)
RUN = "3f0c9a1e-5b7d-4c2e-9a8b-1d2e3f4a5b6c"
# A note of the file's own data, naming orders, aov, return rate and more -
# never revenue.
SAME_DAY = {"code": "same_day_cancellations", "text": "t", "figures": [
    "gross_sales", "returns", "return_rate", "orders", "aov", "customers", "products", "diagnosis"],
    "measures": [{"name": name, "scope": scope, "lines": 10, "amount": amount, "orders": 5, "keys": None}
                 for name, amount in (("returns", -345.5), ("sales", 414.6), ("returns_unchecked", -219.6))
                 for scope in ("file", "current", "previous")]}
# A note that names revenue.
REVENUE_NOTE = {"code": "unconfirmed_suggestions", "text": "t", "figures": NOTE_FIGURES["unconfirmed_suggestions"],
                "measures": [{"name": name, "scope": scope, "lines": 3, "amount": 12.0, "orders": 2, "keys": None}
                             for name in ("lines", "returns") for scope in ("file", "current", "previous")]}


def metrics_data(months: tuple[tuple[str, float], ...] | None = None, **changes: Any) -> dict[str, Any]:
    payload = metrics_payload()
    # Four months: September-November complete, December the partial month
    # the file ends in (data_end 2011-12-09).
    if months is None:
        months = (("2011-09", 1000000.0), ("2011-10", 1290000.0), ("2011-11", 1150000.0), ("2011-12", 300000.0))
    payload["core"]["revenue_by_month"] = [{"period": p, "revenue": r} for p, r in months]
    for key, value in changes.items():
        payload["core"][key] = value
    return payload


def cleaning_data(**mapping: str) -> dict[str, Any]:
    """The cleaning report, a customer column mapped (the example maps none)."""
    payload = cleaning_report_payload()
    payload["column_mapping"] |= {"Customer ID": "customer"} | mapping
    return payload


def build(metrics: dict | None = None, diagnosis: dict | None = None, forecast: dict | None = None,
          include_recommendations: bool = True, schema: bool = True, plan_source: str | None = "ai",
          cleaning: dict | None = None) -> ReportContract:
    return build_report(
        run_id=RUN, source_file="sales_2011.csv",
        metrics=MetricsContract.model_validate(metrics or metrics_data()),
        diagnosis=DiagnosisContract.model_validate(diagnosis or diagnosis_payload()),
        forecast=ForecastContract.model_validate(forecast or forecast_payload()),
        cleaning=CleaningReportContract.model_validate(cleaning or cleaning_data()),
        schema=SchemaInferenceContract.model_validate(inference_payload()) if schema else None,
        plan_source=plan_source, include_recommendations=include_recommendations, now=NOW)


def run_dir(tmp_path: Path, *, optional: bool = True) -> Path:
    """runs/<RUN>/ holding the files stage 5 reads; stage 1's AI answers
    (`optional`) only when asked."""
    run = tmp_path / RUN
    run.mkdir()
    files = {"metrics.json": MetricsContract.model_validate(metrics_data()),
             "diagnosis.json": DiagnosisContract.model_validate(diagnosis_payload()),
             "forecast.json": ForecastContract.model_validate(forecast_payload()),
             "cleaning_report.json": CleaningReportContract.model_validate(cleaning_data())}
    if optional:
        files |= {"schema_inference.json": SchemaInferenceContract.model_validate(inference_payload()),
                  "plan_proposed.json": CleaningPlanContract.model_validate(plan_payload() | {"source": "ai"})}
    for name, model in files.items():
        (run / name).write_text(model.model_dump_json(), encoding="utf-8")
    return run
