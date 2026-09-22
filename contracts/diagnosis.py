"""diagnosis.json (docs/CONTRACTS.md section 7).

**Transitional state, Phase 3.** Session 3A rewrote CONTRACTS section 7 to the
8-block diagnostic engine; the blocks arrive here as the sessions that compute
them land. Session 3B added `Frame`, `TrustCheck`, `Trust`, `Calendar` and
`Signal` - the blocks it produces - so those outputs are validated from day
one. `DiagnosisContract` below is still the pre-3A shape and is rewritten in
3C, together with `tests/contracts/test_diagnosis.py`; until then it
deliberately does not reference the new models. See CONTRACTS section 10.
"""

from math import isfinite
from typing import Any, Literal, Self

from pydantic import NonNegativeInt, model_validator

from contracts._base import ContractFile, ContractModel, YearMonth


# --- Steps 1-4 (session 3B): frame, trust, calendar, signals ------------------


class Frame(ContractModel):
    """Step 1: what is compared with what (docs/AI_PIPELINE.md section 7.2)."""

    current: YearMonth
    previous: YearMonth
    # Both null together when the year-ago pair is not in the data (T2 then
    # has nothing to test).
    year_ago_current: YearMonth | None
    year_ago_previous: YearMonth | None
    history_months: NonNegativeInt
    # Null together when history_months is 0: a file whose only complete month
    # is `current` has no history window at all.
    history_start: YearMonth | None
    history_end: YearMonth | None


class TrustCheck(ContractModel):
    """One of the step 2 data-quality checks (docs/AI_PIPELINE.md 7.3)."""

    id: Literal["D1", "D2", "D3"]
    status: Literal["ok", "caution", "blocked", "inconclusive"]
    evidence: dict[str, Any]
    message: str


class Trust(ContractModel):
    verdict: Literal["trusted", "caution", "blocked"]
    checks: list[TrustCheck]
    limitations: list[str]


class Calendar(ContractModel):
    """Step 3 (docs/AI_PIPELINE.md 7.4). `calendar_effect` is the part of the
    change explained by month shape alone; positive means the current month's
    weekday mix was worth more than the previous month's."""

    method: Literal["weekday_weights", "day_count"]
    expected_cur: float
    expected_prev: float
    calendar_effect: float
    calendar_adjusted_change: float
    evidence: dict[str, Any]

    @model_validator(mode="after")
    def _figures_are_finite(self) -> Self:
        values = (self.expected_cur, self.expected_prev, self.calendar_effect,
                  self.calendar_adjusted_change)
        if not all(isfinite(value) for value in values):
            raise ValueError("calendar figures must be finite")
        return self


class Signal(ContractModel):
    """One series' step 4 verdict (docs/AI_PIPELINE.md 7.5). Under
    `insufficient_history` the four numbers are null: there is no baseline to
    compute a centre or limits from, and reporting zeros would read as real."""

    series: Literal[
        "revenue",
        "orders",
        "active_customers",
        "frequency",
        "aov",
        "units_per_order",
        "price_per_unit",
        "return_rate",
    ]
    mode: Literal["level", "yoy"]
    value_cur: float | None
    center: float | None
    lower: float | None
    upper: float | None
    signal: Literal["above", "below", "within", "insufficient_history"]
    # Which detection rule fired: 1 = outside the limits, 2 = a run on one side
    # of the centre line. Null when the series is within limits or has no
    # baseline. Kept in the output even when a signal is rule 2 only, so step 7
    # can tell those apart until re-baselining lands (session 3D2).
    rule: Literal[1, 2] | None

    @model_validator(mode="after")
    def _nulls_mean_no_baseline(self) -> Self:
        """The four numbers are null exactly under `insufficient_history`.

        Enforced, not just documented (3B doubt-review finding 10): plain
        `float` fields accept NaN and inf, and pydantic then serialises them to
        JSON `null` - which produced a valid-looking `"signal": "within"` row
        with null limits and no error anywhere. Two documents stated this
        invariant and nothing checked it.
        """
        numbers = (self.value_cur, self.center, self.lower, self.upper)
        missing = [value is None for value in numbers]
        if self.signal == "insufficient_history":
            if not all(missing):
                raise ValueError("insufficient_history requires all four numbers to be null")
        elif any(missing):
            raise ValueError(f"signal {self.signal!r} requires value_cur, center, lower and upper")
        if any(value is not None and not isfinite(value) for value in numbers):
            raise ValueError("value_cur, center, lower and upper must be finite")
        return self


# --- Pre-3A shape, rewritten in session 3C ------------------------------------


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
