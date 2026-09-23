"""diagnosis.json (docs/CONTRACTS.md section 7).

Rewritten in Phase 3 session 3C to the 8-block diagnostic engine. Session 3A
rewrote CONTRACTS section 7 and deliberately left this model on its previous
shape, recording the divergence in that file's section 10 change log rather
than leaving a doc/code conflict silent; 3C is where the two meet again.

Blocks for steps 6-8 (`localization`, `hypotheses`, `headline`, `ai_findings`)
are modelled here even though the code that fills them lands in 3D-3F. A
contract describes the file, not this session's progress, and writing them now
means the sessions that produce them are validated from their first line.
"""

from math import isfinite
from typing import Any, Literal, Self

from pydantic import NonNegativeInt, model_validator

from contracts._base import ContractFile, ContractModel, UnitInterval, YearMonth

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


# --- Step 5 (session 3C): the metric tree -------------------------------------


class LeverFactor(ContractModel):
    """One factor of a multiplicative decomposition and what it contributed,
    in revenue units (docs/AI_PIPELINE.md 7.6)."""

    name: Literal["customers", "frequency", "orders", "aov",
                  "units_per_order", "price_per_unit"]
    value_prev: float
    value_cur: float
    contribution: float

    @model_validator(mode="after")
    def _figures_are_finite(self) -> Self:
        if not all(isfinite(v) for v in (self.value_prev, self.value_cur, self.contribution)):
            raise ValueError(f"factor {self.name!r} must carry finite figures")
        return self


class LeverLevel(ContractModel):
    formula: Literal["customers*frequency*aov", "orders*aov",
                     "units_per_order*price_per_unit"]
    factors: list[LeverFactor]

    @model_validator(mode="after")
    def _factors_match_the_formula(self) -> Self:
        """A level that names three factors and carries two is a bug that would
        otherwise reach the report as a decomposition quietly missing a term."""
        expected = self.formula.split("*")
        if [factor.name for factor in self.factors] != expected:
            raise ValueError(
                f"formula {self.formula!r} requires factors {expected}, "
                f"got {[factor.name for factor in self.factors]}"
            )
        return self


class Lever(ContractModel):
    """The lever lens: revenue split into its multiplicative drivers.

    `level1` is null when a factor cannot be formed at all - a period with zero
    orders leaves AOV as 0/0, and there is no multiplicative story to tell about
    a month with no sales. `level2` is null when net units are not positive in
    both periods, or when AOV did not move (the proportional conversion into
    revenue units divides by that change).

    `gross_to_net` and `masked_shift_alert` are **null together with level1**,
    never `false` (Thach, 3C): `false` states that the check ran and found
    nothing, and a downstream reader must not take "the tree could not be
    built" for "no masked shift". `gross_to_net` is also null when revenue did
    not move at all, because the ratio divides by that change - the alert is
    still decided in that case, on whether any component has a step-4 signal.

    `reasons` carries one entry per null field, keyed by field name.
    """

    level1: LeverLevel | None
    level2: LeverLevel | None
    gross_to_net: float | None
    masked_shift_alert: bool | None
    reasons: dict[str, str]

    @model_validator(mode="after")
    def _nulls_are_explained_and_consistent(self) -> Self:
        if (self.level1 is None) != (self.masked_shift_alert is None):
            raise ValueError(
                "masked_shift_alert is null exactly when level1 is null: "
                "'false' would claim a check that did not run"
            )
        if self.level1 is None and self.gross_to_net is not None:
            raise ValueError("gross_to_net cannot be computed without level1")
        if self.level2 is not None and self.level1 is None:
            raise ValueError("level2 is expressed in level1's units and requires it")
        if self.gross_to_net is not None and not isfinite(self.gross_to_net):
            raise ValueError("gross_to_net must be finite or null")
        for field in ("level1", "level2", "gross_to_net"):
            if getattr(self, field) is None and field not in self.reasons:
                raise ValueError(f"{field} is null and carries no reason")
        return self


class BridgeTerms(ContractModel):
    """The six additive terms of a customer bridge, each already signed so that
    they sum to the revenue change (`contraction` and `lapsed` are normally
    negative). They are never clamped: a returns-only customer can legitimately
    make a term carry the sign its name does not suggest, and clamping would
    replace a measurement with an invented number (Thach, 3C)."""

    new: float
    resurrected: float
    expansion: float
    contraction: float
    lapsed: float
    unattributed: float

    @model_validator(mode="after")
    def _terms_are_finite(self) -> Self:
        values = (self.new, self.resurrected, self.expansion,
                  self.contraction, self.lapsed, self.unattributed)
        if not all(isfinite(value) for value in values):
            raise ValueError("bridge terms must be finite")
        return self


class CustomerLens(BridgeTerms):
    """The bridge for the current transition, plus the previous one when the
    file has the history for it, so C1-C3 can compare flows between
    transitions instead of reading one month in isolation."""

    previous_transition: BridgeTerms | None
    evidence: dict[str, Any]


class ReturnsLens(ContractModel):
    """Levels, not changes: `delta_net = delta_gross - delta_returns`.
    `returns_*` are positive magnitudes."""

    gross_prev: float
    gross_cur: float
    returns_prev: float
    returns_cur: float

    @model_validator(mode="after")
    def _figures_are_finite(self) -> Self:
        values = (self.gross_prev, self.gross_cur, self.returns_prev, self.returns_cur)
        if not all(isfinite(value) for value in values):
            raise ValueError("returns lens figures must be finite")
        return self


class ProductLens(ContractModel):
    """Price-volume-mix on gross sales. The five terms sum to the change in
    gross sales - not to net revenue, which is the returns lens's total."""

    volume: float
    mix: float
    price: float
    new_products: float
    discontinued_products: float

    @model_validator(mode="after")
    def _figures_are_finite(self) -> Self:
        """Every sibling lens carries this check and these two did not, which
        is how an infinite price reached `new_products` and was serialised as
        `null` into a required float field (3C doubt-review C2). The boundary
        fix in `shared/transactions.py` stops such a row being counted at all;
        this is the second line of defence, kept consistent across lenses so
        the next one written inherits the habit."""
        values = (self.volume, self.mix, self.price,
                  self.new_products, self.discontinued_products)
        if not all(isfinite(value) for value in values):
            raise ValueError("product lens figures must be finite")
        return self


class Tree(ContractModel):
    method: Literal["shapley"]
    lever: Lever
    # Null when no column is mapped to `customer`; the lever lens then uses the
    # two-factor formula and the C-family hypotheses are not_testable.
    customers: CustomerLens | None
    returns: ReturnsLens
    products: ProductLens


# --- Step 6 (session 3D): localization ----------------------------------------


class Member(ContractModel):
    name: str
    rev_prev: float
    rev_cur: float
    delta: float
    share_of_change: float


class Dimension(ContractModel):
    name: str
    members: list[Member]
    other: Member | None
    new_members: list[str]
    removed_members: list[str]


class MixRate(ContractModel):
    metric: str
    mix: float
    rate: float


class Breadth(ContractModel):
    declining_base_share: UnitInterval
    top_member_share: UnitInterval
    classification: Literal["broad", "mixed", "concentrated"]


class Localization(ContractModel):
    dimensions: list[Dimension]
    # Null when no column is mapped to `category`.
    mix_rate: MixRate | None
    breadth: Breadth


# --- Step 7 (session 3E): hypotheses and headline -----------------------------


class Hypothesis(ContractModel):
    """One entry of the fixed catalog (docs/adr/0005). Every id in the catalog
    appears every run, including the ones that came out `ruled_out`: showing
    what was tested and rejected is the point."""

    id: str
    family: str
    lens: str
    statement: str
    verdict: Literal["supported", "partial", "ruled_out", "inconclusive", "not_testable"]
    # Null for the directional hypotheses (D2, D3, T3, C4, R1), which carry
    # their test in `evidence` and `rule` instead of a share of a total.
    contribution: float | None
    share: float | None
    evidence: dict[str, Any]
    rule: str


class NotTestable(ContractModel):
    id: str
    statement: str
    reason: str


class Headline(ContractModel):
    """Written by code, never by the AI: the report must still state its
    conclusion when the AI is unavailable (CONTRACTS.md section 7)."""

    rule: Literal[1, 2, 3, 4, 5, 6, 7]
    hypothesis_id: str | None
    lens: str | None
    message: str


# --- Step 8 (session 3F): AI narration ----------------------------------------


class HypothesisNote(ContractModel):
    id: str
    text: str


class AiFindings(ContractModel):
    summary: str
    headline_explanation: str
    hypothesis_notes: list[HypothesisNote]
    not_tested_note: str


class DiagnosisContract(ContractFile):
    # Required but nullable: null means the AI step was unavailable, and a
    # missing key must not be mistaken for that (CONTRACTS.md section 7).
    model_used: str | None
    frame: Frame
    trust: Trust
    # All four are null together when trust.verdict is "blocked": the engine
    # refuses to diagnose data it does not believe.
    calendar: Calendar | None
    signals: list[Signal] | None
    tree: Tree | None
    localization: Localization | None
    hypotheses: list[Hypothesis]
    not_testable: list[NotTestable]
    headline: Headline
    ai_findings: AiFindings | None

    @model_validator(mode="after")
    def _ai_blocks_all_or_nothing(self) -> Self:
        if (self.model_used is None) != (self.ai_findings is None):
            raise ValueError(
                "model_used and ai_findings must be both null or both filled"
            )
        return self

    @model_validator(mode="after")
    def _blocked_runs_carry_no_analysis(self) -> Self:
        """A blocked run must not ship half a diagnosis. CONTRACTS section 7
        states this as a rule; without a check, a future step that filled
        `tree` before consulting the gate would produce a file that looks
        authoritative about data the engine refused to trust."""
        analysis = (self.calendar, self.signals, self.tree, self.localization)
        if self.trust.verdict == "blocked":
            if any(block is not None for block in analysis):
                raise ValueError(
                    "a blocked run carries no calendar, signals, tree or localization"
                )
            if self.headline.rule != 1:
                raise ValueError("a blocked run uses headline rule 1")
        return self
