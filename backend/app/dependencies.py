"""FastAPI dependencies shared by routers."""

from collections.abc import Iterator

from fastapi import Request
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings


def get_app_settings(request: Request) -> Settings:
    # The Settings the app was built with (create_app), so tests that inject
    # their own values reach every router, not just the app factory.
    settings: Settings = request.app.state.settings
    return settings


def get_db_session(request: Request) -> Iterator[Session]:
    factory: sessionmaker[Session] = request.app.state.session_factory
    with factory() as session:
        yield session
