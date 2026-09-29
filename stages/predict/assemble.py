"""Stage 4 Predict - assembles forecast.json (docs/CONTRACTS.md section 8)
from the computed forecast (4A) and the AI's checked recommendations (4B),
and writes it to runs/<run_id>/ atomically (session 4C).

The forecast always stands. The AI blocks - `model_used`, `recommendations`,
`do_not_do` - are null together when the step is not run (`Skip`: switched
off - v1's default, as 4B stopped at its review bound - or its attempts
used), when the AI is not asked (a blocked diagnosis, an incomplete previous
month: `ai_strategy.not_asked`), or when it gave no accepted answer;
`Prediction` says which, as a code and a sentence. An answer already
accepted into forecast.json is final (as stage 1's): a second predict of the
same run reuses it - a re-run of stage 2 or 3 removes the file first. It
reads metrics.json and diagnosis.json through their models and refuses a
diagnosis of other months than the metrics'.
"""

import logging
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import ValidationError

from contracts.diagnosis import DiagnosisContract
from contracts.forecast import ForecastBlock, ForecastContract
from contracts.metrics import MetricsContract
from shared.ai_client import AIUnavailable
from shared.contract_files import write_atomically
from shared.run_registry import run_file
from stages.predict.ai_strategy import BLOCKED, NOT_COMPARABLE, Strategy, not_asked
from stages.predict.forecast import forecast

logger = logging.getLogger(__name__)

SCHEMA_VERSION = "1.0"  # forecast.json's first major: no file has been written before (CONTRACTS 10)
METRICS_FILENAME = "metrics.json"
DIAGNOSIS_FILENAME = "diagnosis.json"
FORECAST_FILENAME = "forecast.json"
_NOT_ASKED_CODES = {BLOCKED: "diagnosis_blocked", NOT_COMPARABLE: "not_comparable"}

RecommendStep = Callable[[MetricsContract, DiagnosisContract, ForecastBlock], Strategy]


@dataclass(frozen=True)
class Skip:
    """Why the AI step is not run at all."""

    code: str
    sentence: str


SWITCHED_OFF = Skip("switched_off", "no recommendation: the AI strategy step is switched off")


class DiagnosisMismatchError(ValueError):
    """diagnosis.json describes other months than metrics.json."""


@dataclass(frozen=True)
class Prediction:
    contract: ForecastContract
    ai: Literal["answered", "not_asked", "unavailable"]
    code: str | None  # why the AI gave no recommendation: switched_off, diagnosis_blocked, ... or its failure code
    sentence: str | None


def predict(metrics: MetricsContract, diagnosis: DiagnosisContract, recommend_step: RecommendStep | Skip,
            now: datetime | None = None, previous: ForecastContract | None = None) -> Prediction:
    """The forecast, and the AI's recommendations when the step runs, the AI
    is asked and answers - or the answer `previous` already holds. Pure:
    writes nothing."""
    frame, period = diagnosis.frame, metrics.period
    if (frame.current, frame.previous) != (period.current, period.previous):
        raise DiagnosisMismatchError(
            f"diagnosis.json describes {frame.current} against {frame.previous}, metrics.json {period.current} "
            f"against {period.previous}: run the diagnosis again")
    block = forecast(metrics)
    strategy, ai, code, sentence = _strategy(metrics, diagnosis, block, recommend_step, previous)
    contract = ForecastContract(
        schema_version=SCHEMA_VERSION, generated_at=now or datetime.now(UTC),
        model_used=None if strategy is None else strategy.model, forecast=block,
        recommendations=None if strategy is None else strategy.recommendations,
        do_not_do=None if strategy is None else strategy.do_not_do)
    return Prediction(contract, ai, code, sentence)


def _strategy(metrics: MetricsContract, diagnosis: DiagnosisContract, block: ForecastBlock,
              step: RecommendStep | Skip, previous: ForecastContract | None
              ) -> tuple[Strategy | None, Literal["answered", "not_asked", "unavailable"], str | None, str | None]:
    if isinstance(step, Skip) and step is SWITCHED_OFF:
        return None, "not_asked", step.code, step.sentence  # off: nothing is reused either
    refused = not_asked(metrics, diagnosis)
    if refused is not None:
        return None, "not_asked", _NOT_ASKED_CODES[refused], refused
    if previous is not None and previous.model_used is not None and previous.recommendations is not None \
            and previous.do_not_do is not None:
        return Strategy(previous.recommendations, previous.do_not_do, previous.model_used), "answered", None, None
    if isinstance(step, Skip):
        return None, "not_asked", step.code, step.sentence
    try:
        return step(metrics, diagnosis, block), "answered", None, None
    except AIUnavailable as unavailable:
        return None, "unavailable", unavailable.reason, "the AI assistant gave no answer that could be used"
    except Exception:  # noqa: BLE001 - the forecast is written whatever the AI's path raises (4C review #7)
        logger.exception("stage 4's AI step failed; the forecast is written without recommendations")
        return None, "unavailable", "internal_error", "the AI step failed"


def _previous(runs_root: Path, run_id: str) -> ForecastContract | None:
    """The forecast.json a previous predict wrote, if it can be read."""
    path = run_file(runs_root, run_id, FORECAST_FILENAME)
    try:
        return ForecastContract.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValidationError, ValueError):
        return None  # none yet, or another version's: asked afresh


def predict_run(runs_root: Path, run_id: str, *, recommend_step: RecommendStep | Skip, now: datetime | None = None,
                around_write: Callable[[], AbstractContextManager[object]] | None = None) -> Prediction:
    """Read runs/<run_id>/ (metrics.json, diagnosis.json, and forecast.json
    for an answer already given), predict, and write forecast.json
    atomically: a failure leaves the previous file whole. `around_write`
    wraps the rename of the new file (as stages 2 and 3)."""
    metrics = MetricsContract.model_validate_json(
        run_file(runs_root, run_id, METRICS_FILENAME).read_text(encoding="utf-8"))
    diagnosis = DiagnosisContract.model_validate_json(
        run_file(runs_root, run_id, DIAGNOSIS_FILENAME).read_text(encoding="utf-8"))
    prediction = predict(metrics, diagnosis, recommend_step, now, _previous(runs_root, run_id))
    write_atomically(run_file(runs_root, run_id, FORECAST_FILENAME),
                     prediction.contract.model_dump_json(indent=2).encode("utf-8"), around_replace=around_write)
    return prediction
