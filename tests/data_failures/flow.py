"""How the conformance suite runs a sample (session 2E-u).

Two paths. The direct one hands the sample's rows to stages 2 and 3, as the
stage tests do - stage 2 then classes the lines itself. The real one is the
production flow: the file's bytes as raw.csv, stage 1's profile and execute
(a plan of flag_only steps, or the steps a case names - a cast, say), then
stages 2 and 3 on cleaned.csv - for every mode whose handling depends on
stage 1 (its reader, its classing, its suggestions, its cast; review #11).
"""

from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from contracts.cleaning import ColumnAction, OrderConfirmations
from contracts.diagnosis import DiagnosisContract
from contracts.metrics import MetricsContract
from shared.run_registry import create_run
from stages.analyze.assemble import analyze_run, assemble_metrics
from stages.diagnose.assemble import diagnose, diagnose_run
from stages.diagnose.inputs import build_run_data
from stages.ingest.cleaning import execute_run
from stages.ingest.profiling import profile_run
from tests.data_failures.dirty import SAMPLES
from tests.data_failures.dirty_base import Sample, as_csv
from tests.stages.ingest.cleaning_fixtures import make_plan

NOW = datetime(2026, 10, 1, tzinfo=UTC)
FEB, JAN = 1218.0, 1302.0
ROOT = Path(__file__).resolve().parents[2]
CAST_PRICE = {"Price": ("cast_type", {"target": "float"})}
_KINDS = {"transaction_date": "datetime", "quantity": "numeric_discrete", "unit_price": "numeric_continuous",
          "product_name": "categorical_nominal", "customer": "identifier", "order_id": "identifier",
          "transaction_type": "categorical_nominal"}


def sample(mode: str) -> Sample:
    return SAMPLES[mode]()


def _answers(case: Sample) -> OrderConfirmations | None:
    return OrderConfirmations.model_validate(case.answers) if case.answers else None


def metrics(case: Sample) -> MetricsContract:
    return assemble_metrics(pd.DataFrame(case.rows), case.mapping, now=NOW, confirmations=_answers(case))


def diagnosis(case: Sample) -> DiagnosisContract:
    frame = pd.DataFrame(case.rows)
    found = assemble_metrics(frame, case.mapping, now=NOW, confirmations=_answers(case))
    return diagnose(build_run_data(frame, case.mapping, found, _answers(case)), NOW)


def real_flow(case: Sample, root: Path, steps: dict[str, tuple[str, dict]] | None = None
              ) -> tuple[MetricsContract, DiagnosisContract]:
    run = create_run(root)
    (run.path / "raw.csv").write_bytes(case.raw if case.raw is not None else as_csv(case.rows))
    profile_run(root, run.run_id, now=NOW)
    columns = list(pd.read_csv(run.path / "raw.csv", nrows=0, sep=None, engine="python").columns)
    actions = []
    for name in columns:
        field = case.mapping.get(name, "ignore")
        action, params = (steps or {}).get(name, ("flag_only", {}))
        actions.append(ColumnAction.model_validate({
            "source_name": name, "semantic_type": _KINDS.get(field, "text"), "canonical_field": field,
            "action": action, "params": params, "rationale": "chosen by the user", "alternatives": [],
            "edited_by_user": True}))
    plan = make_plan(actions).model_copy(update={"confirmations": OrderConfirmations.model_validate(case.answers)})
    execute_run(root, run.run_id, plan, now=NOW)
    return analyze_run(root, run.run_id, now=NOW), diagnose_run(root, run.run_id, now=NOW)


def verdicts(found: DiagnosisContract) -> dict[str, str]:
    return {h.id: h.verdict for h in found.hypotheses}


def unmeasurable(found: MetricsContract) -> set[tuple[str, str, int]]:
    return {(u.scope, u.reason, u.lines) for u in found.core.unmeasurable}


def notes(found: MetricsContract) -> set[str]:
    return {note.code for note in found.core.notes}


def check(found: DiagnosisContract, check_id: str) -> str:
    return next(c.status for c in found.trust.checks if c.id == check_id)
