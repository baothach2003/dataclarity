"""What step 7 reads (docs/AI_PIPELINE.md 7.8): the blocks steps 1-6
produced, the change each hypothesis must explain, and the shape of one
evidence function's answer. Separate from `hypotheses.py` so the evidence
functions and the verdict rule can both import it without a cycle."""

from dataclasses import dataclass

from contracts.diagnosis import Calendar, Frame, HeadlineMovement, Localization, Signal, Tree, Trust
from shared.seasonality import season_claim, season_window
from stages.diagnose.inputs import RunData, money_moved
from stages.diagnose.lever import month_revenue
from stages.diagnose.localization import products_hold_the_change
from stages.diagnose.movement import compare_with_season, measure_movement


@dataclass(frozen=True)
class Step7Inputs:
    """Everything steps 1-6 produced; step 7 reads it and never recomputes
    it. `calendar`, `signals`, `tree` and `localization` are None when the
    trust gate blocked (CONTRACTS section 7)."""

    data: RunData
    history: list[str]
    frame: Frame
    trust: Trust
    calendar: Calendar | None
    signals: list[Signal] | None
    tree: Tree | None
    localization: Localization | None


@dataclass(frozen=True)
class Outcome:
    """One evidence function's answer: a finished verdict (directional, or a
    requirement not met), or a contribution for the share rule to judge."""

    verdict: str | None = None
    contribution: float | None = None
    evidence: dict | None = None
    rule: str | None = None
    # For a directional hypothesis whose statement is rendered from a
    # direction (C4): the sign of the movement it found. Share hypotheses are
    # rendered from their contribution instead.
    sign: float | None = None


@dataclass(frozen=True)
class Changes:
    revenue_prev: float
    revenue_cur: float
    net: float
    gross: float | None
    alert: bool
    # The money that moved in the two months (inputs.money_moved, row by row
    # as stage 2 sums it): the scale residue is judged against (2E doubt-review
    # cycles 2 and 3). Judged against the two nets alone, a change stage 2
    # called residue got a "best explanation" in stage 3.
    scale: float = 0.0
    # What stage 2's orders are (2E-e): the wording says "lines" when they are
    # lines. A hand-built Changes (tests) is on lines, the honest default.
    orders_basis: str = "lines"
    # Do the products' sales hold more than half of the change - breadth's
    # own decision (localization.products_hold_the_change; Thach 2E-m, 2E-n),
    # read by the headline's product-lens gate. `changes()` always sets it; a
    # hand-built Changes (tests) holds the change unless it says otherwise.
    products_hold_the_change: bool = True
    # The headline's size test (3E1b, stages/diagnose/movement.py). `changes()`
    # always measures it; a hand-built Changes (tests) carries none, and then
    # rules 5 and 6 are not gated.
    movement: HeadlineMovement | None = None
    # Does 4A's rule claim a season on the forecast's window (shared/
    # seasonality.season_claim)? Only then does rule 4's hedge say "This may
    # be seasonal." (Thach, 2026-10-04, (i)); T2 is worded without "season"
    # either way ((ii)). `changes()` always sets it; a hand-built Changes
    # claims none - the honest default.
    season_claimed: bool = False


def changes(inputs: Step7Inputs) -> Changes:
    period = inputs.data.metrics.period
    prev = month_revenue(inputs.data, period.previous)
    cur = month_revenue(inputs.data, period.current)
    tree = inputs.tree
    gross = (tree.returns.gross_cur - tree.returns.gross_prev) if tree else None
    alert = bool(tree and tree.lever.masked_shift_alert)
    localization = inputs.localization
    scale = money_moved(inputs.data)
    movement = measure_movement(inputs.history, {month: month_revenue(inputs.data, month)
                                                 for month in inputs.history},
                                revenue_prev=prev, revenue_cur=cur, scale=scale)
    # The season, when 4A's rule claims one on the window stage 4 reads -
    # the same claim, the same months (Thach, 2026-10-03, decision 1).
    cycles, _ = season_claim(inputs.data.metrics)
    if cycles is not None:
        months, values, _ = season_window(inputs.data.metrics)
        season = compare_with_season(months, dict(zip(months, values, strict=True)), period.current)
        # Built, not copied: model_copy skips the contract's check that the
        # band agrees with its numbers (review 2, #7).
        movement = HeadlineMovement(**{**dict(movement), "season": season})
    return Changes(prev, cur, cur - prev, gross, alert, scale,
                   # The basis the lever counted on (F10): the same shared
                   # rule stage 2 wrote into metrics.json.
                   orders_basis=inputs.data.parsed.orders_basis,
                   products_hold_the_change=(localization is not None
                                             and products_hold_the_change(localization.breadth)),
                   movement=movement, season_claimed=cycles is not None)
