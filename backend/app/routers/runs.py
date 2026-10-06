from typing import Annotated, Any, Literal

from fastapi import APIRouter, Body, Depends, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import Settings
from app.dependencies import (
    get_ai_client_factory,
    get_app_settings,
    get_db_session,
    get_frame_cache,
    get_retry_budgets,
    get_run_work,
)
from app.schemas import (
    AnalyzeResponse,
    AnalyzeSchemaResponse,
    DiagnoseResponse,
    ExecuteResponse,
    LineSummaryResponse,
    PlanResponse,
    PredictResponse,
    PreviewResponse,
    ReportResponse,
)
from app.services import analysis, diagnosis, downloads, metrics, plan_execution, prediction, reporting
from app.services.analysis import AiClientFactory
from app.services.run_memory import FrameCache, RetryBudgets, RunWork
from app.services.runs import create_run_from_upload
from app.services.uploads import max_upload_bytes
from contracts import ProfileContract

router = APIRouter(prefix="/api/runs", tags=["runs"])


class RunCreated(BaseModel):
    """SPECS section 8: 201 {run_id, filename, size_bytes, status}."""

    run_id: str
    filename: str
    size_bytes: int
    status: Literal["uploaded"]


@router.post("", status_code=201)
def create_run(
    file: UploadFile,
    settings: Annotated[Settings, Depends(get_app_settings)],
    session: Annotated[Session, Depends(get_db_session)],
) -> RunCreated:
    run = create_run_from_upload(
        session,
        file.filename,
        file.file,
        settings.runs_dir,
        max_upload_bytes(settings.max_upload_mb),
        settings.retention_hours,
    )
    return RunCreated(
        run_id=run.id, filename=run.filename, size_bytes=run.size_bytes, status="uploaded"
    )


# The four steps after the upload. Routers hold no logic (CLAUDE.md 3.4): each one
# hands the request to a service and returns what it gives back.

SessionDep = Annotated[Session, Depends(get_db_session)]
SettingsDep = Annotated[Settings, Depends(get_app_settings)]
# A plan is validated by the service, not by FastAPI, so that a body with an action
# outside the catalog is INVALID_PLAN (SPECS section 10) and not INVALID_REQUEST.
PlanBody = Annotated[dict[str, Any], Body()]
WorkDep = Annotated[RunWork, Depends(get_run_work)]


@router.get("/{run_id}/profile")
def get_profile(run_id: str, settings: SettingsDep, session: SessionDep) -> ProfileContract:
    return analysis.get_profile(session, run_id, settings=settings)


def _attachment(file: downloads.DownloadFile) -> Response:
    # An attachment, never shown on the API's own origin; nosniff keeps a
    # browser from reading it as anything but its type.
    return Response(content=file.content, media_type=file.media_type,
                    headers={"Content-Disposition": f'attachment; filename="{file.filename}"',
                             "X-Content-Type-Options": "nosniff"})


@router.get("/{run_id}/download/cleaned.csv")
def download_cleaned_csv(run_id: str, settings: SettingsDep, session: SessionDep) -> Response:
    return _attachment(downloads.download_cleaned_csv(session, run_id, settings=settings))


@router.get("/{run_id}/download/report.html")
def download_report_html(run_id: str, settings: SettingsDep, session: SessionDep, work: WorkDep) -> Response:
    return _attachment(reporting.download_report_html(session, run_id, settings=settings, work=work))


@router.post("/{run_id}/analyze-schema")
def analyze_schema(
    run_id: str,
    settings: SettingsDep,
    session: SessionDep,
    make_client: Annotated[AiClientFactory, Depends(get_ai_client_factory)],
    budgets: Annotated[RetryBudgets, Depends(get_retry_budgets)],
    work: WorkDep,
) -> AnalyzeSchemaResponse:
    return analysis.analyze_schema(
        session, run_id, settings=settings, make_client=make_client, budgets=budgets, work=work)


@router.post("/{run_id}/plan")
def propose_plan(
    run_id: str,
    settings: SettingsDep,
    session: SessionDep,
    make_client: Annotated[AiClientFactory, Depends(get_ai_client_factory)],
    budgets: Annotated[RetryBudgets, Depends(get_retry_budgets)],
    work: WorkDep,
) -> PlanResponse:
    return analysis.propose_plan(
        session, run_id, settings=settings, make_client=make_client, budgets=budgets, work=work)


@router.post("/{run_id}/preview")
def preview_plan(
    run_id: str,
    body: PlanBody,
    settings: SettingsDep,
    session: SessionDep,
    cache: Annotated[FrameCache, Depends(get_frame_cache)],
    work: WorkDep,
) -> PreviewResponse:
    return plan_execution.preview_plan(
        session, run_id, body, settings=settings, cache=cache, work=work)


@router.post("/{run_id}/line-summary")
def summarise_lines(
    run_id: str,
    body: PlanBody,
    settings: SettingsDep,
    session: SessionDep,
    cache: Annotated[FrameCache, Depends(get_frame_cache)],
    work: WorkDep,
) -> LineSummaryResponse:
    return plan_execution.summarise_lines(
        session, run_id, body, settings=settings, cache=cache, work=work)


@router.post("/{run_id}/execute")
def execute_plan(
    run_id: str,
    body: PlanBody,
    settings: SettingsDep,
    session: SessionDep,
    cache: Annotated[FrameCache, Depends(get_frame_cache)],
    budgets: Annotated[RetryBudgets, Depends(get_retry_budgets)],
    work: WorkDep,
) -> ExecuteResponse:
    return plan_execution.execute_plan(
        session, run_id, body, settings=settings, cache=cache, budgets=budgets, work=work)


@router.post("/{run_id}/analyze")
def analyze(run_id: str, settings: SettingsDep, session: SessionDep, work: WorkDep) -> AnalyzeResponse:
    return metrics.analyze(session, run_id, settings=settings, work=work)


@router.post("/{run_id}/diagnose")
def diagnose(run_id: str, settings: SettingsDep, session: SessionDep, work: WorkDep) -> DiagnoseResponse:
    return diagnosis.diagnose(session, run_id, settings=settings, work=work)


@router.post("/{run_id}/predict")
def predict(run_id: str, settings: SettingsDep, session: SessionDep, work: WorkDep) -> PredictResponse:
    # Stage 4 asks no AI in v1 (Thach, Q50 (d)): no client, no retry budget.
    return prediction.predict(session, run_id, settings=settings, work=work)


@router.post("/{run_id}/report")
def report(run_id: str, settings: SettingsDep, session: SessionDep, work: WorkDep) -> ReportResponse:
    return reporting.build_report(session, run_id, settings=settings, work=work)
