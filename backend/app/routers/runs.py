from typing import Annotated, Literal

from fastapi import APIRouter, Depends, UploadFile
from pydantic import BaseModel

from app.config import Settings
from app.dependencies import get_app_settings
from app.services.uploads import max_upload_bytes, store_upload

router = APIRouter(prefix="/api/runs", tags=["runs"])


class RunCreated(BaseModel):
    """SPECS section 8: 201 {run_id, filename, size_bytes, status}."""

    run_id: str
    filename: str
    size_bytes: int
    status: Literal["uploaded"]


@router.post("", status_code=201)
def create_run(
    file: UploadFile, settings: Annotated[Settings, Depends(get_app_settings)]
) -> RunCreated:
    stored = store_upload(
        file.filename, file.file, settings.runs_dir, max_upload_bytes(settings.max_upload_mb)
    )
    return RunCreated(
        run_id=stored.run_id,
        filename=stored.filename,
        size_bytes=stored.size_bytes,
        status="uploaded",
    )
