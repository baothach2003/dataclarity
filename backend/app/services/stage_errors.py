"""Stage exceptions -> the SPECS section 10 error codes.

One place, so every endpoint answers the same failure the same way. Deciding what
happens to the RUN (failed, released, unchanged) is the caller's: it has the session.
"""

from typing import Any, cast

from pydantic import ValidationError

from app.errors import MAX_PROBLEMS, ApiError, ErrorCode, format_problems
from contracts import CleaningPlanContract
from stages.ingest.cleaning import CleaningError
from stages.ingest.plan_validation import InvalidPlanError
from stages.ingest.profiling import ProfilingError


def files_gone() -> ApiError:
    """The run row exists but its directory (or raw.csv) does not: the retention
    cleanup removed it. Same answer as a run already marked expired."""
    return ApiError("EXPIRED", "The run's files are gone. Upload the file again.")


def profiling_failed(error: ProfilingError) -> ApiError:
    """EmptyCsvError -> EMPTY_FILE, CsvParseError -> PARSE_FAILED (both 400); each
    carries its SPECS code in `.code`."""
    return ApiError(cast(ErrorCode, error.code), str(error))


def invalid_plan(error: InvalidPlanError) -> ApiError:
    return ApiError(
        "INVALID_PLAN", "The plan cannot run.",
        {"problems": error.problems[:MAX_PROBLEMS], "problem_count": len(error.problems)})


def analysis_failed(message: str, details: dict[str, Any] | None = None) -> ApiError:
    """Stage 2 cannot compute metrics for this run: a required canonical
    field was never mapped, or the file was flagged NOT_INVENTORY at schema
    inference. Unlike cleaning_failed, the caller does not fail the run -
    cleaned.csv stays valid and downloadable, only the optional analysis is
    unavailable (Thach, 2D, mirrors how a NOT_INVENTORY run already keeps
    its cleaned status and downloads elsewhere)."""
    return ApiError("ANALYSIS_FAILED", message, details)


def cleaning_failed(error: CleaningError) -> ApiError:
    # Only what is known: a plan that leaves no row fails as a whole, on no one action.
    details: dict[str, Any] = {
        key: value for key, value in (("action", error.action), ("column", error.column))
        if value is not None
    }
    return ApiError("CLEANING_FAILED", str(error), details or None)


def parse_plan(body: object) -> CleaningPlanContract:
    """The submitted plan as a contract, or INVALID_PLAN (422).

    An action outside the catalog, a missing field or a wrong type is the same
    "whole plan rejected" as an illegal action (SPECS section 10), so the body is
    validated here and not by FastAPI, which would answer INVALID_REQUEST.
    """
    try:
        return CleaningPlanContract.model_validate(body)
    except ValidationError as error:
        problems = error.errors()
        raise ApiError(
            "INVALID_PLAN", "The plan is not a valid cleaning plan.",
            {"problems": format_problems(problems), "problem_count": len(problems)},
        ) from None
