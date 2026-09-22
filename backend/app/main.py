from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import Engine
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import Settings, get_settings
from app.db import make_engine, make_session_factory
from app.errors import (
    ApiError,
    api_error_handler,
    http_error_handler,
    unexpected_error_middleware,
    validation_error_handler,
)
from app.routers import health, runs
from app.services.analysis import AiClientFactory, default_ai_client_factory
from app.services.run_memory import BYTES_PER_MB, FrameCache, RetryBudgets, RunWork


def create_app(
    settings: Settings | None = None,
    engine: Engine | None = None,
    ai_client_factory: AiClientFactory | None = None,
) -> FastAPI:
    """Build the FastAPI app.

    Settings are injectable so tests can build an app from known values instead
    of whatever `.env` happens to be on the machine, the engine is injectable so
    tests run against SQLite instead of DATABASE_URL, and so is the AI client, so
    no test can reach the real API.
    """
    settings = settings or get_settings()

    app = FastAPI(title="DataClarity API")
    app.state.settings = settings
    app.state.session_factory = make_session_factory(
        engine or make_engine(settings.database_url)
    )
    app.state.ai_client_factory = ai_client_factory or default_ai_client_factory(settings)
    # In-memory, per process (services/run_memory.py); bounded by the settings.
    app.state.frame_cache = FrameCache(
        max_bytes=settings.preview_cache_max_mb * BYTES_PER_MB,
        ttl_seconds=settings.preview_cache_ttl_seconds,
    )
    app.state.retry_budgets = RetryBudgets()
    app.state.run_work = RunWork()
    # Middleware added first is innermost: the catch-all must sit inside CORS so
    # that the 500 envelope carries the CORS headers (errors.py).
    app.add_middleware(BaseHTTPMiddleware, dispatch=unexpected_error_middleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_exception_handler(ApiError, api_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(StarletteHTTPException, http_error_handler)
    app.include_router(health.router)
    app.include_router(runs.router)
    return app


app = create_app()
