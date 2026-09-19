from typing import Annotated, Literal

from fastapi import APIRouter, Depends, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import Settings
from app.dependencies import get_app_settings, get_db_session
from app.services.runs import create_run_from_upload
from app.services.uploads import max_upload_bytes

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
