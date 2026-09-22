"""The API error envelope: `{error: {code, message, details?}}` (SPECS section 8).

Every response that is not a success leaves through here, including the ones
FastAPI would answer itself (a malformed request, an unknown path) and an
unexpected exception, so a client parses one shape only.
"""

import logging
from collections.abc import Awaitable, Callable, Mapping, Sequence
from typing import Any, Literal

from fastapi import Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)

# SPECS section 10 codes that are HTTP errors. NOT_INVENTORY and AI_UNAVAILABLE
# are not here: they are 200 responses with a flag (see schemas.Notice).
ErrorCode = Literal[
    "FILE_TOO_LARGE",
    "UNSUPPORTED_TYPE",
    "EMPTY_FILE",
    "PARSE_FAILED",
    "INVALID_STATE",
    "INVALID_PLAN",
    "CLEANING_FAILED",
    "EXPIRED",
    "RATE_LIMITED",
    # Added by 1G (SPECS section 10 had no row for them): a run id that names
    # nothing, a malformed request, and a server error outside the envelope.
    "NOT_FOUND",
    "INVALID_REQUEST",
    "INTERNAL_ERROR",
]

STATUS_BY_CODE: dict[ErrorCode, int] = {
    "FILE_TOO_LARGE": 413,
    "UNSUPPORTED_TYPE": 400,
    "EMPTY_FILE": 400,
    "PARSE_FAILED": 400,
    "INVALID_STATE": 409,
    "INVALID_PLAN": 422,
    "CLEANING_FAILED": 422,
    "EXPIRED": 410,
    "RATE_LIMITED": 429,
    "NOT_FOUND": 404,
    "INVALID_REQUEST": 400,
    "INTERNAL_ERROR": 500,
}

# The most problems one answer lists: a body of 50,000 bad entries must not come back as a
# 3 MB answer.
MAX_PROBLEMS = 20


class ApiError(Exception):
    """Raised by services; turned into the envelope by `api_error_handler`."""

    def __init__(
        self, code: ErrorCode, message: str, details: dict[str, Any] | None = None
    ) -> None:
        super().__init__(message)
        self.code: ErrorCode = code
        self.message = message
        self.details = details


def _envelope(
    status: int,
    code: ErrorCode,
    message: str,
    details: dict[str, Any] | None = None,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    body: dict[str, Any] = {"code": code, "message": message}
    if details is not None:
        body["details"] = details
    return JSONResponse(status_code=status, content={"error": body}, headers=headers)


async def api_error_handler(_request: Request, exc: ApiError) -> JSONResponse:
    return _envelope(STATUS_BY_CODE[exc.code], exc.code, exc.message, exc.details)


def format_problems(errors: Sequence[Any]) -> list[str]:
    """One line per pydantic problem, "where: what", the first `MAX_PROBLEMS`. The
    library's own answer also repeats the input that failed; that can be a plan or an
    upload part, so it is left out."""
    return [
        ".".join(str(part) for part in error["loc"]) + ": " + str(error["msg"])
        for error in errors[:MAX_PROBLEMS]
    ]


async def validation_error_handler(_request: Request, exc: RequestValidationError) -> JSONResponse:
    return _envelope(
        STATUS_BY_CODE["INVALID_REQUEST"],
        "INVALID_REQUEST",
        "The request is malformed.",
        {"problems": format_problems(exc.errors())},
    )


async def http_error_handler(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
    # Routing answers (no such path, wrong method) keep their own status.
    code: ErrorCode = "NOT_FOUND" if exc.status_code == 404 else "INVALID_REQUEST"
    # The headers matter: a 405 without `Allow` does not say what is allowed.
    return _envelope(exc.status_code, code, str(exc.detail), headers=exc.headers)


async def unexpected_error_middleware(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """Turns an exception nothing handled into INTERNAL_ERROR (500).

    A middleware, not `add_exception_handler(Exception, ...)`: that handler runs in
    Starlette's outermost layer, outside the CORS middleware, so its response would
    carry no CORS headers and the browser would hide the envelope from the frontend.
    Registered before the CORS middleware, this one sits inside it.
    """
    try:
        return await call_next(request)
    except Exception:
        # The text of the exception can hold paths, SQL or connection strings, so
        # none of it reaches the client; the operator gets it here instead.
        logger.exception("Unhandled error on %s %s", request.method, request.url.path)
        return _envelope(
            STATUS_BY_CODE["INTERNAL_ERROR"], "INTERNAL_ERROR", "An unexpected error occurred."
        )
