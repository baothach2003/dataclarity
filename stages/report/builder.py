"""Stage 5 Report - assembles report.json (docs/CONTRACTS.md section 9) from
the earlier contract files and writes it to runs/<run_id>/ atomically
(session 5A).

Stage 5 performs no analysis: it selects, orders and formats (the layers:
`layers.py`). Every number is a field of an earlier file (CONTRACTS 9). The
recommendations are shown only while stage 4's AI step is on - the backend
says so (4C review #4).
"""

import json
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
from datetime import UTC, datetime
from pathlib import Path

from contracts._base import major_of
from contracts.cleaning import CleaningPlanContract, CleaningReportContract
from contracts.diagnosis import DiagnosisContract
from contracts.forecast import ForecastContract
from contracts.metrics import MetricsContract
from contracts.profile import SchemaInferenceContract
from contracts.report import (
    Actions,
    Chart,
    ChartSeries,
    DataQuality,
    MonthRevenue,
    Numbers,
    Provenance,
    ReportContract,
    ReportPeriod,
)
from shared import later_outputs
from shared.contract_files import write_atomically
from shared.periods import shift_month
from shared.run_registry import run_file
from stages.report.html_report import REPORT_HTML, html_run
from stages.report.layers import actions, causes, numbers, revenue_notes

# 2 since 4A-b: the forecast's season_years, its two-year note; 2.1 since 3E1b: the headline's
# optional movement; 2.2 since 2E-u6: the lines dated after the upload; 2.3: the hypotheses note; 2.4: the
# headline's season comparison; 2.5: each hypothesis's label and evidence text, each line outside
# revenue's reason; 2.6: each hypothesis's lens, so the label names its total (CONTRACTS 10).
SCHEMA_VERSION = "2.6"
STAGES_RUN = ["ingest", "analyze", "diagnose", "predict"]


class ReportMismatchError(ValueError):
    """The run's files describe other months than metrics.json (stage 4's
    DiagnosisMismatchError, for stage 5: another comparison's badge and
    headline beside these KPIs)."""


def _same_months(metrics: MetricsContract, diagnosis: DiagnosisContract, forecast: ForecastContract) -> None:
    period, frame, points = metrics.period, diagnosis.frame, forecast.forecast.revenue
    if (frame.current, frame.previous) != (period.current, period.previous):
        raise ReportMismatchError(
            f"diagnosis.json describes {frame.current} against {frame.previous}, metrics.json {period.current} "
            f"against {period.previous}: run the diagnosis again")
    if points and points[0].period != shift_month(period.current, 1):
        raise ReportMismatchError(
            f"forecast.json starts at {points[0].period}, not the month after {period.current}: "
            "run the prediction again")


def _span(months: list[str]) -> str:
    return months[0] if len(months) == 1 else f"{months[0]} to {months[-1]} ({len(months)} months)"


def _gaps(shown: list[MonthRevenue], period: ReportPeriod) -> str | None:
    """Why the line breaks: each run of months with no line counted in
    revenue once (a stray date years back names one span, not a hundred
    months - 5A review 2 #9), and a month not whole with its own reason -
    inside the chart only the compared month, withheld by the KPIs (#4)."""
    sentences: list[str] = []
    run: list[str] = []
    for month in [*shown, None]:
        if month is not None and month.revenue is None:
            run.append(month.period)
            continue
        if run:
            sentences.append(f"No line counted in revenue is dated in {_span(run)}: a closed month or missing data, "
                             "which the file cannot tell apart.")
            run = []
        if month is not None and not month.complete:
            reason = period.previous_incomplete_reason if month.period == period.previous else None
            sentences.append(f"{month.period} is not drawn: {reason.rstrip('.')}." if reason else
                             f"{month.period} is not drawn: the file does not cover it whole.")
    return " ".join(sentences) or None


def _charts(metrics: MetricsContract, numbers: Numbers, actions: Actions) -> list[Chart]:
    """Revenue from the first complete month with revenue to the last, a
    month between them with none or not whole a gap said so - never joined,
    never a zero (the standing rule); the forecast's point, low and high.
    Both carry the notes naming revenue and the trust checks that caution
    the compared months: a cut-short month is plotted as it stands (#2)."""
    months = numbers.revenue_by_month
    drawn = [i for i, m in enumerate(months) if m.complete and m.revenue is not None]
    shown = months[drawn[0]:drawn[-1] + 1] if drawn else []
    notes = revenue_notes(metrics)
    # D1 "inconclusive": whether the month was cut short cannot be judged -
    # the standing rule's shape (review 3 #5). D2's is about prices, too few
    # products to compare: the badge says so, not every chart (review 4 #7).
    cautions = [c.message for c in numbers.trust.checks
                if c.status in ("caution", "blocked") or (c.id == "D1" and c.status == "inconclusive")]
    charts = [Chart(
        id="revenue_trend", type="line", title="Revenue by month", notes=notes, cautions=cautions,
        note=_gaps(shown, numbers.period) if shown else "No month of the file is covered whole and holds revenue, "
                                                         "so none is drawn.",
        series=[ChartSeries(name="revenue", x=[m.period for m in shown],
                            y=[m.revenue if m.complete else None for m in shown])])]
    forecast = actions.forecast
    if forecast.points:
        x = [p.period for p in forecast.points]
        own = " ".join(n for n in (forecast.history_note, forecast.season_note) if n) or None
        charts.append(Chart(id="forecast", type="line", title="Revenue forecast", notes=notes, cautions=cautions,
                            note=own, series=[ChartSeries(name=name, x=x, y=[getattr(p, name) for p in forecast.points])
                                              for name in ("point", "low", "high")]))
    return charts


def _provenance(schema: SchemaInferenceContract | None, plan_source: str | None, diagnosis: DiagnosisContract,
                actions: Actions, forecast: ForecastContract) -> Provenance:
    """The AI answers the report's files hold and it uses - not the calls made."""
    answers = [schema is not None, plan_source == "ai", diagnosis.ai_findings is not None,
               actions.recommendations_status == "shown"]
    models = {schema.model_used if schema is not None else None,
              diagnosis.model_used if diagnosis.ai_findings is not None else None,
              forecast.model_used if actions.recommendations_status == "shown" else None}
    return Provenance(stages_run=list(STAGES_RUN), ai_calls=sum(answers), models_used=sorted(m for m in models if m))


def build_report(*, run_id: str, source_file: str, metrics: MetricsContract, diagnosis: DiagnosisContract,
                 forecast: ForecastContract, cleaning: CleaningReportContract,
                 schema: SchemaInferenceContract | None, plan_source: str | None, include_recommendations: bool,
                 now: datetime | None = None) -> ReportContract:
    """report.json from the run's files. Pure: writes nothing."""
    _same_months(metrics, diagnosis, forecast)
    layer_1 = numbers(metrics, diagnosis, has_customers="customer" in cleaning.column_mapping.values())
    layer_3 = actions(metrics, diagnosis, forecast, include_recommendations)
    return ReportContract(
        schema_version=SCHEMA_VERSION, generated_at=now or datetime.now(UTC), run_id=run_id, source_file=source_file,
        data_quality=DataQuality(rows_in=cleaning.rows_in, rows_out=cleaning.rows_out,
                                 issues_fixed=sum(1 for c in cleaning.changes
                                                  if c.cells_affected > 0 or c.rows_affected > 0),
                                 warnings=len(cleaning.warnings)),
        layer_1_numbers=layer_1, layer_2_causes=causes(diagnosis, metrics.core.orders_basis, layer_1), layer_3_actions=layer_3,
        charts=_charts(metrics, layer_1, layer_3),
        provenance=_provenance(schema, plan_source, diagnosis, layer_3, forecast))


def _read[T: (MetricsContract, DiagnosisContract, ForecastContract, CleaningReportContract)](
        runs_root: Path, run_id: str, model: type[T]) -> T:
    path = run_file(runs_root, run_id, model.filename or "")
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as error:
        raise ValueError(f"{path.name} is not UTF-8 text") from error
    return model.model_validate_json(text)


def _optional[T: (SchemaInferenceContract, CleaningPlanContract)](path: Path, model: type[T]) -> T | None:
    """Stage 1's AI answers feed only the provenance: absent when the AI gave
    none, and read as absent when another major wrote them - not a reason to
    refuse the whole report (5A review 1 #15)."""
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{path.name} cannot be read: it is not a JSON file") from error
    return model.model_validate(raw) if major_of(raw) == model.supported_major else None


def report_run(runs_root: Path, run_id: str, *, source_file: str, include_recommendations: bool,
               now: datetime | None = None,
               around_write: Callable[[], AbstractContextManager[object]] | None = None) -> ReportContract:
    """Read runs/<run_id>/, build report.json and write it atomically: a
    failure leaves the previous file whole."""
    plan = _optional(run_file(runs_root, run_id, "plan_proposed.json"), CleaningPlanContract)
    report = build_report(
        run_id=run_id, source_file=source_file, metrics=_read(runs_root, run_id, MetricsContract),
        diagnosis=_read(runs_root, run_id, DiagnosisContract), forecast=_read(runs_root, run_id, ForecastContract),
        cleaning=_read(runs_root, run_id, CleaningReportContract),
        schema=_optional(run_file(runs_root, run_id, SchemaInferenceContract.filename or ""),
                         SchemaInferenceContract),
        plan_source=None if plan is None else plan.source,
        include_recommendations=include_recommendations, now=now)
    write_atomically(run_file(runs_root, run_id, ReportContract.filename or "report.json"),
                     report.model_dump_json(indent=2).encode("utf-8"), around_replace=around_write)
    return report


@contextmanager
def _pair(runs_root: Path, run_id: str) -> Iterator[None]:
    """Around report.json's rename alone (CONTRACTS section 1): the previous
    pair set aside, the page rendered from the new report.json while it is,
    and on any failure the previous pair put back - a first pair half
    written removed (5C review #1)."""
    with later_outputs.set_aside(runs_root, run_id, after_stage=4):
        try:
            yield
            html_run(runs_root, run_id)
        except BaseException:
            for name in (ReportContract.filename, REPORT_HTML):
                if name is not None:
                    run_file(runs_root, run_id, name).unlink(missing_ok=True)
            raise


def build_run(runs_root: Path, run_id: str, *, source_file: str, include_recommendations: bool,
              now: datetime | None = None) -> ReportContract:
    """report.json and report.html for one run, both or neither within the
    process - the one way the backend and stage 5's CLI write them (5D
    review 2 #1: the CLI's own copy of this had drifted)."""
    return report_run(runs_root, run_id, source_file=source_file, include_recommendations=include_recommendations,
                      now=now, around_write=lambda: _pair(runs_root, run_id))
