"""Stage 4 Predict - assembles forecast.json (docs/CONTRACTS.md section 8)
from the computed forecast (4A) and the suggested actions (the report
redesign, step 4 as Thach's option (d): design 4.1-4.4), and writes it to
runs/<run_id>/ atomically (session 4C). Stage 4 makes no AI call in v1.

The forecast always stands. Code selects the claims and writes every
sentence of each action (claims.py, catalog.py). `actions_status`: "list" -
the actions, or none when no claim can be selected (no cause named, a
blocked diagnosis, an incomplete previous month); "suppressed" - checks a
claim may rest on exist but none has a catalog entry for the way its figure
moved, so there is nothing to act on. Stage 4 never writes "off" (Thach:
only for a run where stage 4 did not produce actions). `actions_model` and
4B's free-text blocks (`model_used`, `recommendations`, `do_not_do`) are
null (Q42, Q53). It reads metrics.json, diagnosis.json and the confirmed
currency of cleaning_report.json, and refuses a diagnosis of other months
than the metrics'.
"""

from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from pydantic import ValidationError

from contracts.cleaning import CleaningReportContract
from contracts.diagnosis import DiagnosisContract
from contracts.forecast import ForecastContract
from contracts.forecast_actions import ActionsStatus, SuggestedAction
from contracts.metrics import MetricsContract
from shared.contract_files import write_atomically
from shared.run_registry import run_file
from stages.predict.claims import candidates, not_asked, select_claims
from stages.predict.forecast import forecast

# 2.1 (the report redesign, step 4): the suggested actions and their state
# (CONTRACTS 10); 2 since 4A-b: the season reading noted.
SCHEMA_VERSION = "2.1"
METRICS_FILENAME = "metrics.json"
DIAGNOSIS_FILENAME = "diagnosis.json"
FORECAST_FILENAME = "forecast.json"
CLEANING_FILENAME = "cleaning_report.json"
NO_CAUSE = "no suggested action: the diagnosis names no cause an action in the shop works on"
NOTHING_TO_ACT_ON = "no suggested action: the figures that moved have no action to suggest"


class DiagnosisMismatchError(ValueError):
    """diagnosis.json describes other months than metrics.json."""


@dataclass(frozen=True)
class Prediction:
    contract: ForecastContract
    # Why no action is listed, in plain words (logs, the API's notices), or
    # None when actions are listed.
    why_none: str | None = None


def _actions(metrics: MetricsContract, diagnosis: DiagnosisContract,
             code: str | None) -> tuple[ActionsStatus, list[SuggestedAction], str | None]:
    claims = select_claims(metrics, diagnosis, code)
    if claims:
        return "list", [SuggestedAction(claim=c.id, hypothesis_id=c.hypothesis_id, fact=c.fact, action=c.action,
                                        why=c.why, watch=c.watch) for c in claims], None
    if candidates(metrics, diagnosis):
        return "suppressed", [], NOTHING_TO_ACT_ON
    return "list", [], not_asked(metrics, diagnosis) or NO_CAUSE


def predict(metrics: MetricsContract, diagnosis: DiagnosisContract, now: datetime | None = None,
            code: str | None = None) -> Prediction:
    """The forecast and the suggested actions. `code`: the file's confirmed
    currency, so a claim's money reads as the report's. Pure: writes
    nothing."""
    frame, period = diagnosis.frame, metrics.period
    if (frame.current, frame.previous) != (period.current, period.previous):
        raise DiagnosisMismatchError(
            f"diagnosis.json describes {frame.current} against {frame.previous}, metrics.json {period.current} "
            f"against {period.previous}: run the diagnosis again")
    status, actions, why_none = _actions(metrics, diagnosis, code)
    contract = ForecastContract(
        schema_version=SCHEMA_VERSION, generated_at=now or datetime.now(UTC), model_used=None,
        forecast=forecast(metrics), recommendations=None, do_not_do=None,
        actions=actions if status == "list" else None, actions_status=status, actions_model=None)
    return Prediction(contract, why_none)


def _currency(runs_root: Path, run_id: str) -> str | None:
    """The confirmed currency stage 1 applied, or none (no cleaning report,
    one written before 4.3, or another version's: the forecast never fails
    for a code - stage 5 refuses such a file on its own)."""
    try:
        cleaning = CleaningReportContract.model_validate_json(
            run_file(runs_root, run_id, CLEANING_FILENAME).read_text(encoding="utf-8"))
    except (OSError, ValidationError, ValueError):
        return None
    return cleaning.currency.code if cleaning.currency is not None else None


def predict_run(runs_root: Path, run_id: str, *, now: datetime | None = None,
                around_write: Callable[[], AbstractContextManager[object]] | None = None) -> Prediction:
    """Read runs/<run_id>/ (metrics.json, diagnosis.json, cleaning_report.json's
    currency), predict, and write forecast.json atomically: a failure leaves
    the previous file whole. `around_write` wraps the rename of the new file
    (as stages 2 and 3)."""
    metrics = MetricsContract.model_validate_json(
        run_file(runs_root, run_id, METRICS_FILENAME).read_text(encoding="utf-8"))
    diagnosis = DiagnosisContract.model_validate_json(
        run_file(runs_root, run_id, DIAGNOSIS_FILENAME).read_text(encoding="utf-8"))
    prediction = predict(metrics, diagnosis, now, _currency(runs_root, run_id))
    write_atomically(run_file(runs_root, run_id, FORECAST_FILENAME),
                     prediction.contract.model_dump_json(indent=2).encode("utf-8"), around_replace=around_write)
    return prediction
