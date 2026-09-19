"""The API error envelope: `{error: {code, message, details?}}` (SPECS section 8)."""

from typing import Any, Literal

from fastapi import Request
from fastapi.responses import JSONResponse

# Codes from SPECS section 10 in use so far; each sub-phase adds the ones it
# raises, together with their HTTP status.
ErrorCode = Literal["FILE_TOO_LARGE", "UNSUPPORTED_TYPE", "EMPTY_FILE", "PARSE_FAILED"]

STATUS_BY_CODE: dict[ErrorCode, int] = {
    "FILE_TOO_LARGE": 413,
    "UNSUPPORTED_TYPE": 400,
    "EMPTY_FILE": 400,
    "PARSE_FAILED": 400,
}


class ApiError(Exception):
    """Raised by services; turned into the envelope by `api_error_handler`."""

    def __init__(
        self, code: ErrorCode, message: str, details: dict[str, Any] | None = None
    ) -> None:
        super().__init__(message)
        self.code: ErrorCode = code
        self.message = message
        self.details = details


async def api_error_handler(_request: Request, exc: ApiError) -> JSONResponse:
    body: dict[str, Any] = {"code": exc.code, "message": exc.message}
    if exc.details is not None:
        body["details"] = exc.details
    return JSONResponse(status_code=STATUS_BY_CODE[exc.code], content={"error": body})
