"""FastAPI dependencies shared by routers."""

from fastapi import Request

from app.config import Settings


def get_app_settings(request: Request) -> Settings:
    # The Settings the app was built with (create_app), so tests that inject
    # their own values reach every router, not just the app factory.
    settings: Settings = request.app.state.settings
    return settings
