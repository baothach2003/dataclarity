from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.config import Settings
from app.dependencies import get_app_settings

router = APIRouter(prefix="/api", tags=["limits"])


class Limits(BaseModel):
    """What the Upload page checks before uploading (PROJECT_PLAN 6A): the
    server's own MAX_UPLOAD_MB, so the client holds no second copy of a number
    that can differ per deployment. The server still enforces it (SEC-1)."""

    max_upload_mb: int


@router.get("/limits")
def limits(settings: Annotated[Settings, Depends(get_app_settings)]) -> Limits:
    return Limits(max_upload_mb=settings.max_upload_mb)
