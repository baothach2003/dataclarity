"""Shared base for every contract model (docs/CONTRACTS.md section 1)."""

import re
from collections.abc import Iterator
from math import isfinite
from typing import Annotated, Any, ClassVar

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator

SUPPORTED_MAJOR_VERSION = 1

_VERSION_PATTERN = re.compile(r"^(\d+)\.(\d+)$")
# The words every refusal of a file of another major carries, so a caller can
# tell "written by another version of the app" from any other refusal (2E-v).
UNSUPPORTED_MAJOR = "unsupported major version"

Percent = Annotated[float, Field(ge=0, le=100)]
UnitInterval = Annotated[float, Field(ge=0, le=1)]
NonNegativeFloat = Annotated[float, Field(ge=0)]
# A calendar month, e.g. "2011-11" (the period format in CONTRACTS.md 6 and 8).
YearMonth = Annotated[str, Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")]


class ContractModel(BaseModel):
    # "ignore", not "forbid": a minor bump adds optional fields and must leave
    # older readers unaffected (CONTRACTS.md section 10). Strict checking of AI
    # output happens in the stages, before anything is written to a contract.
    model_config = ConfigDict(extra="ignore")


class ContractFile(ContractModel):
    """Header fields every contract file carries."""

    schema_version: str
    generated_at: AwareDatetime

    # Per contract file, since each bumps on its own (CONTRACTS.md section 10):
    # metrics.json went to 2.0 in session 2E while every other file is 1.x.
    supported_major: ClassVar[int] = SUPPORTED_MAJOR_VERSION
    # Appended to the refusal of an older major, so the reader is told what
    # to do rather than only what went wrong.
    stale_major_hint: ClassVar[str] = ""
    # The run file this model reads (CONTRACTS.md section 1) - None for a
    # model of two files - and the stage that writes it: a file another
    # version wrote is answered by what that stage needs (2E-v review 3 #2).
    filename: ClassVar[str | None] = None
    written_by_stage: ClassVar[int] = 1

    @field_validator("schema_version")
    @classmethod
    def _known_major_version(cls, value: str) -> str:
        match = _VERSION_PATTERN.match(value)
        if match is None:
            raise ValueError(f"expected 'MAJOR.MINOR', got {value!r}")
        if int(match.group(1)) != cls.supported_major:
            # A newer major: this version cannot know what it holds (2E-v
            # review 2 #5).
            hint = (cls.stale_major_hint if int(match.group(1)) < cls.supported_major
                    else ": this file was written by a newer version of DataClarity, which this one cannot "
                         "read; upload the file again")
            raise ValueError(
                f"{UNSUPPORTED_MAJOR} {value!r}; "
                f"this reader supports {cls.supported_major}.x{hint}"
            )
        return value


def major_of(data: Any) -> int | None:
    """The major of a raw contract document's `schema_version`, or None."""
    version = data.get("schema_version") if isinstance(data, dict) else None
    match = _VERSION_PATTERN.match(version) if isinstance(version, str) else None
    return int(match.group(1)) if match else None


def numbers_json_cannot_carry(data: Any, path: str = "") -> Iterator[tuple[str, float]]:
    """Every float of a dumped contract (`model_dump()`) that is infinite or
    not a number, with its path: JSON writes it as null, so a required field
    holding one makes a file no reader can load back (2E-v #1)."""
    if isinstance(data, dict):
        for key, value in data.items():
            yield from numbers_json_cannot_carry(value, f"{path}.{key}" if path else str(key))
    elif isinstance(data, list):
        for index, value in enumerate(data):
            yield from numbers_json_cannot_carry(value, f"{path}[{index}]")
    elif isinstance(data, float) and not isfinite(data):
        yield path, data
