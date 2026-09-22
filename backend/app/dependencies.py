"""FastAPI dependencies shared by routers."""

from collections.abc import Iterator

from fastapi import Request
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.services.analysis import AiClientFactory
from app.services.run_memory import FrameCache, RetryBudgets, RunWork


def get_app_settings(request: Request) -> Settings:
    # The Settings the app was built with (create_app), so tests that inject
    # their own values reach every router, not just the app factory.
    settings: Settings = request.app.state.settings
    return settings


def get_frame_cache(request: Request) -> FrameCache:
    cache: FrameCache = request.app.state.frame_cache
    return cache


def get_retry_budgets(request: Request) -> RetryBudgets:
    budgets: RetryBudgets = request.app.state.retry_budgets
    return budgets


def get_run_work(request: Request) -> RunWork:
    work: RunWork = request.app.state.run_work
    return work


def get_ai_client_factory(request: Request) -> AiClientFactory:
    factory: AiClientFactory = request.app.state.ai_client_factory
    return factory


def get_db_session(request: Request) -> Iterator[Session]:
    factory: sessionmaker[Session] = request.app.state.session_factory
    with factory() as session:
        yield session
