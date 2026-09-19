"""diagnosis.json (docs/CONTRACTS.md section 7)."""

from typing import Self

from pydantic import model_validator

from contracts._base import ContractFile, ContractModel


class DecompositionFactor(ContractModel):
    factor: str
    contribution_abs: float
    contribution_pct: float
    value_current: float
    value_previous: float


class Decomposition(ContractModel):
    """Computed by pandas in stage 3; the AI never produces it."""

    metric: str
    change_abs: float
    change_pct: float
    factors: list[DecompositionFactor]
    method: str


class RootCause(ContractModel):
    driver: str
    evidence: str
    secondary: list[str]


class RuledOutHypothesis(ContractModel):
    hypothesis: str
    evidence_against: str


class AiFindings(ContractModel):
    headline: str
    root_cause: RootCause
    ruled_out: list[RuledOutHypothesis]


class DiagnosisContract(ContractFile):
    # Required but nullable: null means the AI step was unavailable, and a
    # missing key must not be mistaken for that (CONTRACTS.md section 7).
    model_used: str | None
    decomposition: Decomposition
    ai_findings: AiFindings | None

    @model_validator(mode="after")
    def _ai_blocks_all_or_nothing(self) -> Self:
        if (self.model_used is None) != (self.ai_findings is None):
            raise ValueError(
                "model_used and ai_findings must be both null or both filled"
            )
        return self
