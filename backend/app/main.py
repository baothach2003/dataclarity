from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import Settings, get_settings
from app.errors import ApiError, api_error_handler
from app.routers import health, runs


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the FastAPI app.

    Settings are injectable so tests can build an app from known values instead
    of whatever `.env` happens to be on the machine.
    """
    settings = settings or get_settings()

    app = FastAPI(title="DataClarity API")
    app.state.settings = settings
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_exception_handler(ApiError, api_error_handler)
    app.include_router(health.router)
    app.include_router(runs.router)
    return app


app = create_app()
