"""What step 7 reads (docs/AI_PIPELINE.md 7.8): the blocks steps 1-6
produced, the change each hypothesis must explain, and the shape of one
evidence function's answer. Separate from `hypotheses.py` so the evidence
functions and the verdict rule can both import it without a cycle."""

from dataclasses import dataclass

from contracts.diagnosis import Calendar, Frame, Localization, Signal, Tree, Trust
from stages.diagnose.inputs import RunData, money_moved
from stages.diagnose.lever import month_revenue


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


def changes(inputs: Step7Inputs) -> Changes:
    period = inputs.data.metrics.period
    prev = month_revenue(inputs.data, period.previous)
    cur = month_revenue(inputs.data, period.current)
    tree = inputs.tree
    gross = (tree.returns.gross_cur - tree.returns.gross_prev) if tree else None
    alert = bool(tree and tree.lever.masked_shift_alert)
    return Changes(prev, cur, cur - prev, gross, alert, money_moved(inputs.data))
