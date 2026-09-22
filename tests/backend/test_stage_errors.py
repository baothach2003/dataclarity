"""Stage exceptions -> SPECS section 10 codes, one test per exception type (1G).

The endpoint tests drive the same mappings through HTTP; these pin the table itself,
including the corners no plan or file can easily produce.
"""

import pytest

from app.errors import STATUS_BY_CODE, ApiError
from app.services import stage_errors
from contracts import CleaningPlanContract
from stages.ingest.cleaning import CleaningError
from stages.ingest.plan_validation import InvalidPlanError
from stages.ingest.profiling import CsvParseError, EmptyCsvError


def test_an_empty_csv_is_empty_file_400() -> None:
    error = stage_errors.profiling_failed(
        EmptyCsvError("The file has a header row but no data rows."))

    assert (error.code, STATUS_BY_CODE[error.code]) == ("EMPTY_FILE", 400)
    assert error.message == "The file has a header row but no data rows."


def test_an_unparseable_csv_is_parse_failed_400() -> None:
    error = stage_errors.profiling_failed(
        CsvParseError("Rows have more fields than the header row."))

    assert (error.code, STATUS_BY_CODE[error.code]) == ("PARSE_FAILED", 400)


def test_an_invalid_plan_is_422_with_its_problems() -> None:
    error = stage_errors.invalid_plan(InvalidPlanError(["a is wrong", "b is wrong"]))

    assert (error.code, STATUS_BY_CODE[error.code]) == ("INVALID_PLAN", 422)
    assert error.details == {"problems": ["a is wrong", "b is wrong"], "problem_count": 2}


def test_a_flood_of_problems_is_cut_but_counted() -> None:
    # A plan of 50,000 bad column actions must not come back as a 3 MB answer.
    error = stage_errors.invalid_plan(InvalidPlanError([f"problem {i}" for i in range(50_000)]))

    assert error.details is not None
    assert len(error.details["problems"]) == 20
    assert error.details["problems"][0] == "problem 0"
    assert error.details["problem_count"] == 50_000


def test_a_cleaning_failure_names_the_action_and_the_column() -> None:
    error = stage_errors.cleaning_failed(
        CleaningError("impute_median on column 'price' failed: x", "impute_median", "price"))

    assert (error.code, STATUS_BY_CODE[error.code]) == ("CLEANING_FAILED", 422)
    assert error.details == {"action": "impute_median", "column": "price"}


def test_a_cleaning_failure_of_the_whole_plan_has_no_details() -> None:
    error = stage_errors.cleaning_failed(CleaningError("The plan removes every row."))

    assert error.details is None


def test_files_that_are_gone_are_expired_410() -> None:
    error = stage_errors.files_gone()

    assert (error.code, STATUS_BY_CODE[error.code]) == ("EXPIRED", 410)
    assert "upload" in error.message.lower()


@pytest.mark.parametrize("body", [{}, {"source": "ai"}, {"column_actions": "no"}])
def test_a_body_that_is_not_a_plan_is_invalid_plan(body: object) -> None:
    with pytest.raises(ApiError) as caught:
        stage_errors.parse_plan(body)

    assert caught.value.code == "INVALID_PLAN"
    assert caught.value.details is not None and caught.value.details["problems"]


def test_parse_plan_returns_the_contract_for_a_valid_plan() -> None:
    from tests.stages.ingest.cleaning_fixtures import make_plan

    plan = make_plan()

    parsed = stage_errors.parse_plan(plan.model_dump(mode="json"))

    assert isinstance(parsed, CleaningPlanContract)
    assert parsed == plan

