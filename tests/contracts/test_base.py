import pytest
from pydantic import ValidationError

from contracts._base import ContractFile


def test_accepts_version_one_with_utc_timestamp() -> None:
    header = ContractFile.model_validate(
        {"schema_version": "1.0", "generated_at": "2026-09-18T04:12:00Z"}
    )

    assert header.schema_version == "1.0"
    assert header.generated_at.utcoffset() is not None


def test_accepts_minor_bump_of_known_major() -> None:
    # CONTRACTS.md section 10: a minor bump leaves readers unaffected.
    header = ContractFile.model_validate(
        {"schema_version": "1.3", "generated_at": "2026-09-18T04:12:00Z"}
    )

    assert header.schema_version == "1.3"


@pytest.mark.parametrize("version", ["2.0", "0.9", "1", "1.0.0", "v1.0", ""])
def test_rejects_unknown_major_or_malformed_version(version: str) -> None:
    with pytest.raises(ValidationError, match="schema_version"):
        ContractFile.model_validate(
            {"schema_version": version, "generated_at": "2026-09-18T04:12:00Z"}
        )


def test_rejects_timestamp_without_timezone() -> None:
    with pytest.raises(ValidationError, match="generated_at"):
        ContractFile.model_validate(
            {"schema_version": "1.0", "generated_at": "2026-09-18T04:12:00"}
        )


def test_rejects_missing_generated_at() -> None:
    with pytest.raises(ValidationError, match="generated_at"):
        ContractFile.model_validate({"schema_version": "1.0"})


def test_ignores_unknown_fields_from_a_newer_minor_version() -> None:
    header = ContractFile.model_validate(
        {
            "schema_version": "1.1",
            "generated_at": "2026-09-18T04:12:00Z",
            "field_added_in_1_1": "x",
        }
    )

    assert "field_added_in_1_1" not in header.model_dump()
