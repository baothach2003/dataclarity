"""Shared base for every contract model (docs/CONTRACTS.md section 1)."""

import re
from typing import Annotated, ClassVar

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator

SUPPORTED_MAJOR_VERSION = 1

_VERSION_PATTERN = re.compile(r"^(\d+)\.(\d+)$")

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

    @field_validator("schema_version")
    @classmethod
    def _known_major_version(cls, value: str) -> str:
        match = _VERSION_PATTERN.match(value)
        if match is None:
            raise ValueError(f"expected 'MAJOR.MINOR', got {value!r}")
        if int(match.group(1)) != cls.supported_major:
            hint = cls.stale_major_hint if int(match.group(1)) < cls.supported_major else ""
            raise ValueError(
                f"unsupported major version {value!r}; "
                f"this reader supports {cls.supported_major}.x{hint}"
            )
        return value
