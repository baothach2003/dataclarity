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
from app.schemas import AnalyzeSchemaResponse, ExecuteResponse, PlanResponse, PreviewResponse
from app.services import analysis, downloads, plan_execution
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


@router.get("/{run_id}/download/cleaned.csv")
def download_cleaned_csv(run_id: str, settings: SettingsDep, session: SessionDep) -> Response:
    file = downloads.download_cleaned_csv(session, run_id, settings=settings)
    return Response(
        content=file.content,
        media_type=file.media_type,
        headers={"Content-Disposition": f'attachment; filename="{file.filename}"'},
    )


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
