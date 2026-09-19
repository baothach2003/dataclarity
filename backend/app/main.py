from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import Settings, get_settings
from app.routers import health


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the FastAPI app.

    Settings are injectable so tests can build an app from known values instead
    of whatever `.env` happens to be on the machine.
    """
    settings = settings or get_settings()

    app = FastAPI(title="CleanStock API")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health.router)
    return app


app = create_app()
