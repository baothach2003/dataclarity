"""Stage 5 orchestration: `POST /api/runs/{id}/report` and the page's
download (docs/SPECS.md sections 3 and 8; session 5C). The logic stays in
`stages/report` (CLAUDE.md 3.4): this service enforces the state machine,
keeps one piece of work at a time per run, tells the stage what only the
backend knows - the uploaded file's name (the run's row) and whether the AI
strategy step is on (4C review #4) - and shapes the answer.

The run stays `analyzed` (stages 2-5 all live in it; which files exist says
how far it went - 3G-lite's rule). report.json is written atomically; around
its rename the previous pair is set aside and the page rendered from the
new report.json - both or neither within the process (a crash between the
two can leave report.json alone: 8D).
"""

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import Settings
from app.errors import ApiError
from app.models import RunStatus
from app.schemas import ReportResponse
from app.services import later_outputs, run_state, stage_errors
from app.services.downloads import DownloadFile, safe_stem
from app.services.run_memory import RunWork
from contracts import CleaningReportContract, DiagnosisContract, ForecastContract, MetricsContract, ReportContract
from shared.run_registry import RunNotFoundError, run_file
from stages.report.builder import ReportMismatchError, report_run
from stages.report.html_report import REPORT_HTML, html_run

REPORTABLE_STATUSES = (RunStatus.ANALYZED,)
# The page stays downloadable once the run is imported (as cleaned.csv does).
_HAS_REPORT = (RunStatus.ANALYZED, RunStatus.IMPORTED)
# The earlier stages' files the report is built from: without the first two
# the run's files are gone (EXPIRED); without the others a stage has not run.
_GONE_WITHOUT = (MetricsContract.filename, CleaningReportContract.filename)
_FIRST = ((DiagnosisContract.filename, "Run the diagnosis first"),
          (ForecastContract.filename, "Run the prediction first"))


def build_report(session: Session, run_id: str, *, settings: Settings, work: RunWork) -> ReportResponse:
    """`analyzed` -> `analyzed`, with report.json and report.html written. A
    run file another version of the app wrote is answered by the app's
    handler (`stage_errors.run_file_version_handler`): "run that stage
    again", or "upload the file again" for a stage 1 file."""
    runs_root = settings.runs_dir
    run = run_state.load_run(session, run_id)
    run_state.require_status(run, *REPORTABLE_STATUSES, step="build the report")
    source_file = run.filename
    session.commit()  # no read transaction held through the work
    with work.execution(run_id):
        # Inside: a re-run of an earlier stage that finished just before
        # cannot remove the files between the check and the read (4C review #3).
        _require_run_files(runs_root, run_id)
        try:
            report = report_run(runs_root, run_id, source_file=source_file,
                                include_recommendations=settings.strategy_ai_enabled,
                                around_write=lambda: _pair(runs_root, run_id))
        except ReportMismatchError as error:
            raise ApiError("INVALID_STATE", f"The run's files do not describe the same months: {error}.",
                           {"reason": "files_mismatch"}) from error
    return ReportResponse(run_id=run_id, status="analyzed", report=report,
                          html_url=f"/api/runs/{run_id}/download/{REPORT_HTML}")


@contextmanager
def _pair(runs_root: Path, run_id: str) -> Iterator[None]:
    """Around report.json's rename alone (CONTRACTS section 1): the previous
    pair set aside, the page rendered from the new report.json while it is,
    and on any failure the previous pair put back - a first pair half
    written removed (5C review #1: the page is missing only while it is
    rendered, never through the whole build)."""
    with later_outputs.set_aside(runs_root, run_id, after_stage=4):
        try:
            yield
            html_run(runs_root, run_id)
        except BaseException:
            for name in (ReportContract.filename, REPORT_HTML):
                if name is not None:
                    run_file(runs_root, run_id, name).unlink(missing_ok=True)
            raise


def download_report_html(session: Session, run_id: str, *, settings: Settings, work: RunWork) -> DownloadFile:
    """Read-only: no work claim, so downloads never hold each other off. The
    page is read once - a report being built again has it set aside for a
    moment: "wait", never a 500 (5C review #1)."""
    run = run_state.load_run(session, run_id)
    run_state.require_status(run, *_HAS_REPORT, step="download the report")
    try:
        content = run_file(settings.runs_dir, run_id, REPORT_HTML).read_bytes()
    except RunNotFoundError:
        raise stage_errors.files_gone() from None
    except FileNotFoundError:
        if work.is_active(run_id):
            raise ApiError("INVALID_STATE", "The report is being built again. Wait for it to finish.",
                           {"reason": "step_in_progress"}) from None
        raise ApiError("INVALID_STATE", "Build the report first: this run has no report.html.",
                       {"status": run.status.value, "missing": REPORT_HTML}) from None
    return DownloadFile(content=content, media_type="text/html; charset=utf-8",
                        filename=f"report_{safe_stem(run.filename, default='data')}.html")


def _require_run_files(runs_root: Path, run_id: str) -> None:
    """Its files gone (the retention cleanup): EXPIRED. An earlier stage not
    run - or its output removed by a re-run before it - is the steps'
    order, not an expiry: INVALID_STATE, naming the file."""
    names = [name for name in (*_GONE_WITHOUT, *(name for name, _ in _FIRST)) if name is not None]
    try:
        present = {name for name in names if run_file(runs_root, run_id, name).exists()}
    except RunNotFoundError:
        present = set()
    if not all(name in present for name in _GONE_WITHOUT):
        raise stage_errors.files_gone()
    for name, first in _FIRST:
        if name not in present:
            raise ApiError("INVALID_STATE", f"{first}: this run has no {name}.",
                           {"status": RunStatus.ANALYZED.value, "missing": name})
