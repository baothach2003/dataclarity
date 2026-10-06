"""Stage 5 orchestration: `POST /api/runs/{id}/report` and the page's
download (docs/SPECS.md sections 3 and 8; session 5C). The logic stays in
`stages/report` (CLAUDE.md 3.4): this service enforces the state machine,
keeps one piece of work at a time per run, tells the stage what only the
backend knows - the uploaded file's name (the run's row) - and shapes the
answer.

The run stays `analyzed` (stages 2-5 all live in it; which files exist says
how far it went - 3G-lite's rule). Both files are written by stage 5's
`build_run` - both or neither within the process (a crash between the two
can leave report.json alone: 8D).
"""

import json
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import Settings
from app.errors import ApiError
from app.models import RunStatus
from app.schemas import ReportResponse
from app.services import run_state, stage_errors
from app.services.downloads import DownloadFile, safe_stem
from app.services.run_memory import RunWork
from contracts import CleaningReportContract, DiagnosisContract, ForecastContract, MetricsContract, ReportContract
from contracts._base import major_of
from shared.later_outputs import REPORT_HTML
from shared.run_registry import RunNotFoundError, run_file
from stages.report.builder import ReportMismatchError, build_run

REPORTABLE_STATUSES = (RunStatus.ANALYZED,)
# The page stays downloadable once the run is imported (as cleaned.csv does).
_HAS_REPORT = (RunStatus.ANALYZED, RunStatus.IMPORTED)
# The earlier stages' files the report is built from: without the first two
# the run's files are gone (EXPIRED); without the others a stage has not run.
_GONE_WITHOUT = (MetricsContract.filename, CleaningReportContract.filename)
_FIRST = ((DiagnosisContract.filename, "Run the diagnosis first"),
          (ForecastContract.filename, "Run the prediction first"))
# What the report is built from, in stage order (4A-b review 3 #1).
_BUILT_FROM = (CleaningReportContract, MetricsContract, DiagnosisContract, ForecastContract)


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
            report = build_run(runs_root, run_id, source_file=source_file)
        except ReportMismatchError as error:
            raise ApiError("INVALID_STATE", f"The run's files do not describe the same months: {error}.",
                           {"reason": "files_mismatch"}) from error
    return ReportResponse(run_id=run_id, status="analyzed", report=report,
                          html_url=f"/api/runs/{run_id}/download/{REPORT_HTML}")


def download_report_html(session: Session, run_id: str, *, settings: Settings, work: RunWork) -> DownloadFile:
    """Read-only: no work claim, so downloads never hold each other off. The
    page is read once - a report being built again has it set aside for a
    moment: "wait", never a 500 (5C review #1)."""
    run = run_state.load_run(session, run_id)
    run_state.require_status(run, *_HAS_REPORT, step="download the report")
    _require_current_report(settings.runs_dir, run_id, work)
    try:
        content = run_file(settings.runs_dir, run_id, REPORT_HTML).read_bytes()
    except RunNotFoundError:
        raise stage_errors.files_gone() from None
    except FileNotFoundError:
        if work.is_active(run_id):
            raise _wait() from None
        raise ApiError("INVALID_STATE", "Build the report first: this run has no report.html.",
                       {"status": run.status.value, "missing": REPORT_HTML}) from None
    except OSError:  # held by another program, or not a file: never a 500 (4A-b review 4 #3)
        if work.is_active(run_id):
            raise _wait() from None
        raise _unreadable(REPORT_HTML) from None
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


def _wait() -> ApiError:
    """A step is running on the run - a report being built, or an earlier
    stage run again, which removes the report rather than building it (4A-b
    review 3 #9): "wait", never "build it" (5C review #1)."""
    return ApiError("INVALID_STATE", "Another step is running for this run. Wait for it to finish.",
                    {"reason": "step_in_progress"})


class _Unreadable(Exception):
    """A run file that is there but cannot be read as JSON."""


def _unreadable(name: str) -> ApiError:
    """Not "another version": nothing says which wrote it (4A-b review 4 #8)."""
    return ApiError("INVALID_STATE", f"This run's {name} cannot be read. Build the report again.",
                    {"reason": "unreadable", "file": name})


def _major(runs_root: Path, run_id: str, name: str) -> int | None:
    """A run file's major, None when it names none. A missing file or run
    directory is raised as it is; a file that cannot be read as JSON - held
    by another program, cut short, nested past the parser - is _Unreadable,
    never a 500 (4A-b review 3 #7)."""
    try:
        return major_of(json.loads(run_file(runs_root, run_id, name).read_text(encoding="utf-8")))
    except FileNotFoundError:
        raise
    except (OSError, ValueError, RecursionError) as error:
        raise _Unreadable(name) from error


def _require_current_report(runs_root: Path, run_id: str, work: RunWork) -> None:
    """The page is report.json rendered: a report.json another version wrote
    means a page built from a forecast this version would not show as it is
    (4A-b review 2 #1: a two-year season without its note) - never served,
    and neither is a page with no report.json beside it (review 4 #7). With
    no report at all, the page's own read answers. A step holding the run is
    "wait", decided last so a step that took the run meanwhile is seen too
    (review 4 #4)."""
    try:
        try:
            if _major(runs_root, run_id, str(ReportContract.filename)) == ReportContract.supported_major:
                return
            answer = _first_step_that_works(runs_root, run_id)
        except FileNotFoundError:
            if not run_file(runs_root, run_id, REPORT_HTML).exists():
                return
            answer = _unreadable(str(ReportContract.filename))
    except RunNotFoundError:
        answer = stage_errors.files_gone()
    except _Unreadable:
        answer = _unreadable(str(ReportContract.filename))
    except ApiError as error:  # _require_run_files: an earlier file missing
        answer = error
    if work.is_active(run_id):
        raise _wait()
    raise answer


def _first_step_that_works(runs_root: Path, run_id: str) -> ApiError:
    """For a page another version built (4A-b review 3 #1): what POST
    /report answers for a missing earlier file (review 4 #1), else the
    earliest file it is built from that another version wrote - a
    report.json 1.x always sits on a forecast.json 1.x - else the report."""
    _require_run_files(runs_root, run_id)
    for model in _BUILT_FROM:
        try:
            if _major(runs_root, run_id, str(model.filename)) != model.supported_major:
                return stage_errors.written_by_another_version(model)
        except (FileNotFoundError, _Unreadable):
            # Set aside since the check (a step: "wait" decides), or corrupt -
            # which the build answers (8D "From 5C").
            continue
    return stage_errors.written_by_another_version(ReportContract)
