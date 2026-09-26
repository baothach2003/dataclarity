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

from math import isclose, isfinite
from typing import Any, ClassVar, Literal, Self

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
    # Days of the previous month before the file's first sale. Nonzero when
    # the export starts mid-month (or the shop opened then): the month the
    # current one is compared with is incomplete. The trust gate blocks on it
    # at D1's caution size (docs/AI_PIPELINE.md 7.2, Thach, 3E1).
    previous_leading_days_missing: NonNegativeInt
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
    """One series' step 4 row (docs/AI_PIPELINE.md 7.5). Under
    `insufficient_history` the four numbers are null: there is no baseline to
    compute a centre or limits from, and reporting zeros would read as real.

    A row is not a verdict. In v1 no step-4 row is, in either mode - see
    `is_verdict` below, docs/adr/0006-level-signals-are-descriptive.md and
    docs/adr/0007-no-step4-verdicts-in-v1.md."""

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
    # baseline.
    #
    # **Step 7 acts on rule 1 only.** Rule 2 measures a run against a centre
    # computed from the same points, so one anomalous month re-fires it every
    # month until it leaves the window (3B). Re-baselining was attempted in
    # 3D2 and the method did not work (PROJECT_PLAN section 12), so rule-2
    # signals stay in the output - a reader can see them. Since ADR-0007 no
    # row of either rule is a verdict in v1; the distinction is kept because
    # the Backlog's "unusualness verdicts" would need it again (Thach, 3D2).
    rule: Literal[1, 2] | None
    # Which estimator drew the limits: the median moving range, the average as
    # a fallback when the median is zero, or `minimum_spread` when neither
    # measured any variation and a floor in the series' own units was used
    # instead. Recorded so that a later change of estimator is visible in the
    # file rather than silently changing what every verdict means (Thach,
    # 3D2) - which is exactly why the floored case needs its own value and
    # cannot be reported as the estimator that returned zero (3D3
    # doubt-review C2).
    limits_method: Literal["median_moving_range", "mean_moving_range",
                           "minimum_spread"]
    # Set when this series WOULD have charted year over year - it had enough
    # usable baseline points - but the current month had no usable comparator,
    # so it fell back to the level chart. `no_year_ago_value` means the month
    # is absent from the file (the shop was shut); `unusable_year_ago_base`
    # means it is present but not a denominator: it netted zero or below, was
    # floating-point residue, or (3D6) was too small against the series'
    # typical level to divide by (AI_PIPELINE 7.5, the base guard).
    #
    # It records WHY a series is in level mode. Since ADR-0006 it no longer
    # has to carry the weight of stopping T3 on its own: a level-mode row is
    # not a verdict at all, whatever put it there. It stays because "the shop
    # was shut" and "that month netted zero" are different facts about the
    # business and 3F narrates them differently.
    mode_fallback: Literal["no_year_ago_value", "unusable_year_ago_base"] | None = None
    # Why no chart was drawn at all, when `signal` is `insufficient_history`.
    #
    # **This is not the same question as `mode_fallback` and the two must not
    # be merged** (Thach, 3D5). `mode_fallback` says the series IS charted, on
    # the level chart, because its comparator was unusable. `insufficient_reason`
    # says there is no chart at all.
    #
    # `step_change_too_recent` is deliberately NOT a member. Step-change
    # detection was attempted in 3D2 and reverted; listing a value nothing can
    # produce invites a consumer to handle it and a later reader to believe the
    # feature exists. It goes in when the backlog item does.
    #
    # `neither_chart_informative` and `month_not_comparable_to_centre` were
    # members for the length of session 3D5 and were removed by ADR-0006. They
    # described a level chart refusing to judge a month; a level chart no
    # longer judges any month, so there is nothing to refuse.
    insufficient_reason: Literal[
        "too_few_points",
        "no_current_value",
        "no_measurable_spread",
    ] | None = None

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
        # The same reasoning as above, applied to the fields that arrived
        # later: each of these couplings was stated in CONTRACTS section 7 or
        # in a comment in this file, and none was checked (3D5b review R6).
        if self.signal == "insufficient_history":
            if self.insufficient_reason is None:
                raise ValueError(
                    "insufficient_history requires insufficient_reason: a row "
                    "saying there is no chart must say why"
                )
        elif self.insufficient_reason is not None:
            raise ValueError(
                f"insufficient_reason is only set under insufficient_history, "
                f"not alongside {self.signal!r}"
            )
        if self.mode == "yoy" and self.mode_fallback is not None:
            raise ValueError(
                "mode_fallback says the series fell back to the LEVEL chart, "
                "so a yoy row cannot carry one"
            )
        if self.signal == "within" and self.rule is not None:
            raise ValueError("rule is null when the series is within limits")
        if any(value is not None and not isfinite(value) for value in numbers):
            raise ValueError("value_cur, center, lower and upper must be finite")
        return self


# --- Step 5 (session 3C): the metric tree -------------------------------------


def is_verdict(signal: Signal) -> bool:
    """May step 7 treat this row as a judgement about the month? In v1: never.

    ADR-0006 made LEVEL rows descriptive: a level chart centred on the mean of
    every month cannot judge a seasonal month. ADR-0007 extends that to
    YEAR-OVER-YEAR rows, for the mirror-image reason: a year-over-year point
    compares with ONE year-ago month, and whether that month was itself
    normal cannot be told without further years. Session 3D6 ran every known
    limit to the headline and five of seven fabricated an actionable verdict
    on a month where nothing happened - a trickle off-season, a year-ago
    month at 10% of normal, one anomalous baseline point pulling the mean
    centre. Making a comparator robust to one bad year needs the median of at
    least THREE prior years (the median of two is their mean, which halves an
    anomaly rather than ignoring it), so 45 complete months, and a robust
    centre as well. No demo dataset reaches that; it is a Backlog item.

    Rows are still computed, carry limits and a rule, and are written to
    `diagnosis.json` as evidence a reader can look at. T3 is therefore never
    `supported` and headline rule 3 is dormant. The predicate is kept, rather
    than deleted, because it is the one place the Backlog item switches back
    on, and T3 (3E) reads it.
    """
    return False


def is_actionable(signal: Signal) -> bool:
    """May step 7 turn this row into a headline cause?

    A verdict, and rule 1. Rule 2 measures a run against a centre computed
    from the same points, so one anomalous month re-fires it every month until
    it leaves the window; re-baselining was attempted in session 3D2 and the
    method did not work. Under ADR-0006 a rule-2 row could PREVENT
    "routine" and never BECOME a cause (Thach, 3D2). Since ADR-0007 nothing is
    a verdict in v1, so this is False for every row; it is kept for the
    Backlog's "unusualness verdicts".
    """
    return is_verdict(signal) and signal.rule == 1


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


def _pair_matches_level1(pair: LeverLevel, level1: LeverLevel) -> bool:
    """Same orders and AOV in both periods, and the same revenue change.

    Relative tolerance, because customers x frequency re-multiplies to the
    order count only up to floating-point residue."""
    values = {period: {factor.name: getattr(factor, f"value_{period}")
                       for factor in level1.factors} for period in ("prev", "cur")}
    pairs = {period: {factor.name: getattr(factor, f"value_{period}")
                      for factor in pair.factors} for period in ("prev", "cur")}
    for period in ("prev", "cur"):
        v = values[period]
        orders = v["customers"] * v["frequency"] if "customers" in v else v["orders"]
        if not (isclose(pairs[period]["orders"], orders, rel_tol=1e-9)
                and isclose(pairs[period]["aov"], v["aov"], rel_tol=1e-9)):
            return False
    change = sum(f.contribution for f in level1.factors)
    scale = max(abs(f.contribution) for f in level1.factors) or 1.0
    return isclose(sum(f.contribution for f in pair.factors), change,
                   rel_tol=1e-9, abs_tol=1e-9 * scale)


class Lever(ContractModel):
    """The lever lens: revenue split into its multiplicative drivers.

    `level1` is null when a factor cannot be formed at all - a period with zero
    orders leaves AOV as 0/0, and there is no multiplicative story to tell about
    a month with no sales. `level2` is null when net units are not positive in
    both periods, or when AOV did not move (the proportional conversion into
    revenue units divides by that change).

    `gross_to_net` and `masked_shift_alert` are **null whenever level1 is**,
    never `false` (Thach, 3C): `false` states that the check ran and found
    nothing, and a downstream reader must not take "the tree could not be
    built" for "no masked shift". `gross_to_net` is also null when revenue did
    not move at all, because the ratio divides by that change - and that IS the
    flat case, so the alert is still decided.

    The alert rests on the tree alone (ADR-0007): against a floor of
    `MASKED_MIN_CONTRIBUTION_SHARE` times the largest of the typical month,
    the previous month and the current month, one contribution of each sign
    on `masked_shift_pair` (orders x AOV) clears the floor; the revenue change
    stays under the same share of the larger compared month; and
    `gross_to_net >= MASKED_GROSS_TO_NET`. It is also null, with level 1
    present, when
    there is no typical month to measure "material" against - a history with
    no complete trading month - because the check could not run.
    `masked_shift_basis` is gone with the signals it described: nothing now
    establishes that the movement was UNUSUAL, so headline rule 4 is always
    worded as a movement that may be seasonal.

    `reasons` carries one entry per null field, keyed by field name.
    """

    level1: LeverLevel | None
    level2: LeverLevel | None
    gross_to_net: float | None
    masked_shift_alert: bool | None
    # The orders x AOV split the alert is decided on (Thach, 3D6b). Not
    # level 1's customers x frequency x AOV: customers x frequency = orders by
    # definition, so when orders hold steady and the customer count moves
    # those two cancel EXACTLY, and a three-factor rule read that identity as
    # a masked shift - 19-39% of such months with nothing planted. Headline
    # rule 4 names this pair's two contributions. Null exactly when level 1 is;
    # absent from files written before 3D6b, which still load.
    masked_shift_pair: LeverLevel | None = None
    reasons: dict[str, str]

    @model_validator(mode="after")
    def _nulls_are_explained_and_consistent(self) -> Self:
        if self.level1 is None and self.masked_shift_alert is not None:
            raise ValueError(
                "masked_shift_alert is null whenever level1 is null: "
                "'false' would claim a check that did not run"
            )
        if self.masked_shift_alert is True and self.masked_shift_pair is None:
            # Headline rule 4 names the pair's two contributions. No stage has
            # written a diagnosis.json yet, so no older file carries a fired
            # alert without one (pair review #5).
            raise ValueError("a fired alert must carry masked_shift_pair for rule 4 to name")
        if self.masked_shift_pair is not None:
            if self.level1 is None:
                raise ValueError("masked_shift_pair is derived from level1 and requires it")
            if self.masked_shift_pair.formula != "orders*aov":
                raise ValueError("masked_shift_pair is the orders*aov split, by definition")
            if not _pair_matches_level1(self.masked_shift_pair, self.level1):
                raise ValueError("masked_shift_pair does not match level1: the same "
                                 "orders, AOV and revenue change must underlie both")
        if self.level1 is None and self.gross_to_net is not None:
            raise ValueError("gross_to_net cannot be computed without level1")
        if self.level2 is not None and self.level1 is None:
            raise ValueError("level2 is expressed in level1's units and requires it")
        if self.gross_to_net is not None and not isfinite(self.gross_to_net):
            raise ValueError("gross_to_net must be finite or null")
        for field in ("level1", "level2", "gross_to_net"):
            if getattr(self, field) is None and field not in self.reasons:
                raise ValueError(f"{field} is null and carries no reason")
        # A null alert beside a null level 1 is explained by level 1's reason,
        # as it always was - so a diagnosis.json written before ADR-0007 still
        # loads. A null alert WITH level 1 present is new (no typical month to
        # measure against) and must say so (3D6b doubt-review #1).
        if (self.masked_shift_alert is None and self.level1 is not None
                and "masked_shift_alert" not in self.reasons):
            raise ValueError("masked_shift_alert is null and carries no reason")
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
    """Levels, not changes: `delta_net = delta_gross - delta_returns -
    delta_deductions`. Gross is the sale rows; returns the return lines;
    deductions every other counted row - coupons, discounts, write-offs
    (2E-c). `returns_*` and `deductions_*` are positive magnitudes."""

    gross_prev: float
    gross_cur: float
    returns_prev: float
    returns_cur: float
    deductions_prev: float
    deductions_cur: float

    @model_validator(mode="after")
    def _figures_are_finite(self) -> Self:
        values = (self.gross_prev, self.gross_cur, self.returns_prev, self.returns_cur,
                  self.deductions_prev, self.deductions_cur)
        if not all(isfinite(value) for value in values):
            raise ValueError("returns lens figures must be finite")
        return self


class ProductLens(ContractModel):
    """Price-volume-mix on gross sales. The six terms sum to the change in
    gross sales - not to net revenue, which is the returns lens's total.
    `non_product` is the change in the gross of lines the user classed as a
    charge the customer paid (postage, 2E-d2): gross sales, but no product
    whose price, volume or mix could move; 0.0 when none is classed."""

    volume: float
    mix: float
    price: float
    new_products: float
    discontinued_products: float
    non_product: float

    @model_validator(mode="after")
    def _figures_are_finite(self) -> Self:
        """Every sibling lens carries this check and these two did not, which
        is how an infinite price reached `new_products` and was serialised as
        `null` into a required float field (3C doubt-review C2). The boundary
        fix in `shared/transactions.py` stops such a row being counted at all;
        this is the second line of defence, kept consistent across lenses so
        the next one written inherits the habit."""
        values = (self.volume, self.mix, self.price,
                  self.new_products, self.discontinued_products, self.non_product)
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
    # True for a bucket that exists because the data is incomplete - rows whose
    # category or product name is blank - rather than because the business has
    # such a group. Step 7 must not write a recommendation about
    # "(uncategorised)" as though it were a real product line (Thach, 3D); it
    # is a data-completeness signal, and D3 carries its share as evidence.
    is_data_gap: bool = False
    # True for the product dimension's "(not a product)" bucket (2E-d2): the
    # lines the user classed as charges or discounts - revenue, no missing
    # data, but no product a recommendation could be about. Kept apart from
    # `is_data_gap`, or postage would read as missing data (review cycle 2).
    is_not_a_product: bool = False

    @model_validator(mode="after")
    def _figures_are_finite(self) -> Self:
        values = (self.rev_prev, self.rev_cur, self.delta, self.share_of_change)
        if not all(isfinite(value) for value in values):
            raise ValueError(f"member {self.name!r} must carry finite figures")
        if self.is_data_gap and self.is_not_a_product:
            raise ValueError(f"member {self.name!r} is a data gap or is_not_a_product, not both")
        return self


class Dimension(ContractModel):
    name: str
    members: list[Member]
    other: Member | None
    new_members: list[str]
    removed_members: list[str]
    # True when no member cleared the size bar and the top movers were named
    # anyway, so that step 7 can tell a genuinely concentrated dimension from
    # one whose members are all small (Thach, 3D): a `concentrated` verdict
    # means something different under a waived bar, and the headline rules
    # must be able to see the difference rather than infer it from prose.
    size_filter_waived: bool = False
    # How many members the dimension had before ranking and grouping, which is
    # the context that makes the waiver readable: 5 named out of 7 is a
    # different story from 5 named out of 500.
    member_count: NonNegativeInt = 0


class MixRate(ContractModel):
    """The Simpson's-paradox split. `metric` is closed, not an open string:
    only two averages are ever split (docs/AI_PIPELINE.md 7.7), and a typo in
    a free string would reach the narration as the name of a metric that does
    not exist."""

    metric: Literal["aov", "price_per_unit"]
    mix: float
    rate: float

    @model_validator(mode="after")
    def _figures_are_finite(self) -> Self:
        """Every sibling lens carries this and MixRate was written without it
        - the same omission, in the same place, as the two lenses that shipped
        `null` into required float fields in 3C. `ProductLens` says the habit
        is "kept consistent across lenses so the next one written inherits
        it"; the next one written did not (3D doubt-review R7)."""
        if not all(isfinite(value) for value in (self.mix, self.rate)):
            raise ValueError("mix and rate must be finite")
        return self


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
    # 2 since 2E-c: the returns lens gained deductions, and gross sales became
    # the sale rows only (Thach). 3 since 2E-c2: the bridge's `new` and
    # `resurrected` changed meaning (any return on a customer's first day),
    # and returns exclude zero-amount write-offs. 4 since 2E-e: the lever's
    # orders and the B1/B2 statements follow the orders basis. 5 since 2E-f:
    # the bridge's `new` / `resurrected` net the first day per product, and
    # its terms, `unattributed` and the customer counts read the customer
    # filled from the receipt. 6 since 2E-g: product members are keyed and
    # named as stage 2 does (a SKU-only line is its product), and the data gap
    # is never a stockout (R3) or a price-check product (D2). 7 since 2E-h:
    # every day and month on the wall clock as written (UTC before). 8 since
    # 2E-e2: the lever's orders and the bridge's customers follow the user's
    # answers in Review (an order id checked by date only; the customer fill).
    # 9 since 2E-k: confirmed walk-in placeholders are unattributed (the
    # bridge, the lever's customers), and the order-id check is per receipt.
    # 10 since 2E-d2: lines the user classed as not products leave the
    # product lens (its `non_product` term) and the product members (one
    # "(not a product)" bucket), fees and adjustments leave revenue, and a
    # discount is a deduction, not a return.
    supported_major: ClassVar[int] = 10
    stale_major_hint: ClassVar[str] = (
        ": this diagnosis.json was written by an earlier stage 3 with different "
        "definitions (returns lens, new and resurrected customers); re-analyse "
        "this run")

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
