"""Stage exceptions -> the SPECS section 10 error codes.

One place, so every endpoint answers the same failure the same way. Deciding what
happens to the RUN (failed, released, unchanged) is the caller's: it has the session.
"""

from typing import Any, cast

from pydantic import ValidationError

from fastapi import Request
from fastapi.responses import JSONResponse

import contracts
from app.errors import MAX_PROBLEMS, ApiError, ErrorCode, api_error_handler, format_problems
from contracts import CleaningPlanContract
from contracts._base import UNSUPPORTED_MAJOR, ContractFile
from contracts.lines import refused_as_too_large
from contracts.metrics import BEFORE_THE_LINE_TAXONOMY
from stages.ingest.cleaning import CleaningError
from stages.ingest.plan_validation import InvalidPlanError
from stages.ingest.profiling import ProfilingError


def files_gone() -> ApiError:
    """The run row exists but its directory (or raw.csv) does not: the retention
    cleanup removed it. Same answer as a run already marked expired."""
    return ApiError("EXPIRED", "The run's files are gone. Upload the file again.")


# Every run file's model, by the name a refusal carries (its title).
_RUN_FILES: dict[str, type[ContractFile]] = {
    name: model for name in contracts.__all__
    if isinstance(model := getattr(contracts, name), type) and issubclass(model, ContractFile)}
# What rewrites a later stage's output: running that stage again (2E-v review
# 2 #6, review 3 #2).
_RERUN = {2: "Run the analysis again.", 3: "Run the diagnosis again.", 4: "Run the prediction again.",
          5: "Build the report again."}


def another_version(error: ValidationError) -> ApiError | None:
    """A run file another version of the app wrote - an older or newer
    major, or a metrics.json of this major from before the line taxonomy's
    blocks - or None for any other refusal (SPECS section 10: never a 500 -
    2E-v #2). A stage 1 file cannot be read again by this version: the file
    is uploaded again, as for a run the retention cleanup removed (EXPIRED).
    A later stage's output is rewritten by running that stage again
    (INVALID_STATE). `details.file` names the file when one model reads one
    file (the cleaning plan's model reads two)."""
    if not any(UNSUPPORTED_MAJOR in str(problem["msg"]) or BEFORE_THE_LINE_TAXONOMY in str(problem["msg"])
               for problem in error.errors()):
        return None
    return written_by_another_version(_RUN_FILES.get(error.title))


def written_by_another_version(model: type[ContractFile] | None) -> ApiError:
    """The answer to `model`'s file written by another version: run its
    stage again, or upload the file again for a stage 1 file - also what
    the page's download answers for a report.json of another major (4A-b
    review 2 #1)."""
    details: dict[str, Any] = {"reason": "another_version"}
    if model is not None and model.filename is not None:
        details["file"] = model.filename
    if model is not None and model.written_by_stage in _RERUN:
        return ApiError("INVALID_STATE", f"This run's {model.filename} was written by another version of "
                        f"DataClarity. {_RERUN[model.written_by_stage]}", details)
    return ApiError("EXPIRED", "This run was prepared by another version of DataClarity. Upload the file again.",
                    details)


async def run_file_version_handler(request: Request, exc: Exception) -> JSONResponse:
    """Every endpoint's answer to a run file another version wrote (2E-v
    review 3 #1: /plan, /execute and /profile gave a 500 while /analyze did
    not). Any other refusal is a bug: re-raised, it becomes the 500 of
    `unexpected_error_middleware`. The service has already released any
    claim it held, as for every unexpected error."""
    if not isinstance(exc, ValidationError):
        raise exc
    answer = another_version(exc)
    if answer is None:
        raise exc
    return await api_error_handler(request, answer)


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
    field was never mapped, the file was flagged NOT_INVENTORY at schema
    inference, cleaned.csv's line classes are not stage 1's, or its amounts
    or quantities are too large to add up. Unlike cleaning_failed, the caller does not fail the run -
    cleaned.csv stays valid and downloadable, only the optional analysis is
    unavailable (Thach, 2D, mirrors how a NOT_INVENTORY run already keeps
    its cleaned status and downloads elsewhere)."""
    return ApiError("ANALYSIS_FAILED", message, details)


_WHAT_FAILED = {2: "its metrics", 3: "its diagnosis", 4: "its forecast"}


def too_large_to_add(error: ValidationError) -> bool:
    """Every problem is a number JSON cannot carry - a sum past a float in
    stage 2, or a figure stage 3's attribution multiplied past one (3G-lite
    review 1 #1): the contracts word both with TOO_LARGE_TO_ADD. Any other
    refusal is a bug. The one test, `contracts.lines.refused_as_too_large`."""
    return refused_as_too_large(error)


def amounts_too_large(stage: int) -> ApiError:
    """Stage 2 adds the amounts; stage 3 multiplies them in its attribution -
    either can pass a float where the other did not."""
    return analysis_failed(
        f"The file's amounts or quantities are too large to work with, so {_WHAT_FAILED[stage]} cannot be "
        "computed. Correct them in the file and upload it again.",
        {"reason": "amounts_too_large"})


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
