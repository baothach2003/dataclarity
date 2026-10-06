"""Section 3 of the front: "What was checked", a plain checklist grouped by
stage 3's verdicts (docs/REPORT_REDESIGN.md 1.3; Thach Q16, Q20). The groups
read `hypotheses[].verdict`, `.share` and the report's own "moved against"
(hypothesis_rows: only beside a comparison shown); the bars are stage 3's
(shared/share_bars). T3 and C4 are left to the appendix (dormant in v1)."""

from contracts.diagnosis import DiagnosisContract, Hypothesis
from contracts.report import HypothesisView
from contracts.report_front import ChecklistGroup
from shared.share_bars import PARTIAL_MIN_SHARE
from stages.report.front_lines import DATA_IDS, Context, cannot_show_line, moved_line, not_reason_lines
from stages.report.front_summary import whom
from stages.report.wording import amount, times

APPENDIX_ONLY = ("T3", "C4")
MOVED = "Moved this month, but not singled out"
_NOT_NAMED = "none of these is called the reason; each line says what moved."


def _note(diagnosis: DiagnosisContract) -> str:
    """Why nothing in the first group is called the reason (rules 3, 4, 7)."""
    headline = diagnosis.headline
    movement = headline.movement
    season = movement.season if movement is not None else None
    if headline.rule == 4:
        return f"Because the main movements largely cancelled out, {_NOT_NAMED}"
    if season is not None and season.band == "consistent":
        return f"Because the change is in line with {whom(season.years)}, {_NOT_NAMED}"
    if movement is not None and movement.singled_out is False:
        return (f"Because the change is less than {times(movement.factor)} this shop's typical month-to-month "
                f"change, {_NOT_NAMED}")
    if movement is not None and movement.singled_out is None:
        return f"Because the file's history is too short to compare the change with, {_NOT_NAMED}"
    return f"{_NOT_NAMED[:1].upper()}{_NOT_NAMED[1:]}"


def _ranked(hypotheses: list[Hypothesis], first: str | None) -> list[Hypothesis]:
    """The headline's cause first, then the largest amounts (as stage 4
    ranks its claims: design 4.2)."""
    order = {h.id: i for i, h in enumerate(hypotheses)}
    return sorted(hypotheses, key=lambda h: (h.id != first, -abs(h.contribution or 0.0), order[h.id]))


def checklist(diagnosis: DiagnosisContract, views: list[HypothesisView], ctx: Context) -> list[ChecklistGroup]:
    against_shown = {view.id for view in views if view.moved_against}
    matches, against, ruled_out, cannot = [], [], [], []
    for hypothesis in diagnosis.hypotheses:
        if hypothesis.id in APPENDIX_ONLY:
            continue
        if (hypothesis.id in against_shown and hypothesis.share is not None
                and abs(hypothesis.share) >= PARTIAL_MIN_SHARE):
            against.append(hypothesis)
        elif hypothesis.verdict in ("supported", "partial") and not hypothesis.against_the_change:
            matches.append(hypothesis)
        elif hypothesis.verdict == "ruled_out":
            ruled_out.append(hypothesis)
        elif hypothesis.id not in DATA_IDS:  # D1-D3: the one data-checks line
            cannot.append(hypothesis)
    headline = diagnosis.headline
    named = headline.rule in (2, 5, 6)
    groups = []
    if matches:
        change = ctx.bridge.shown_change if ctx.bridge is not None else ctx.metrics.core.revenue_change
        after = None
        if change is not None:
            after = (f"These amounts are measured in different ways and overlap, so they do not add up to the change "
                     f"({amount(change, ctx.code)}).")
            if ctx.bridge is not None:
                after += " The chart in section 2 is the one that adds up."
        groups.append(ChecklistGroup(
            kind="matches" if named else "moved", title="Matches the figures" if named else MOVED,
            note=None if named else _note(diagnosis),
            lines=[moved_line(h, ctx) for h in _ranked(matches, headline.hypothesis_id)], after=after))
    if against:
        groups.append(ChecklistGroup(kind="against", title="Pulled the other way", note=None,
                                     lines=[moved_line(h, ctx) for h in _ranked(against, None)], after=None))
    if ruled_out:
        groups.append(ChecklistGroup(kind="not_reason", title="Checked - not the reason", note=None,
                                     lines=not_reason_lines(ruled_out, ctx), after=None))
    if cannot:
        groups.append(ChecklistGroup(kind="cannot_show", title="This file cannot show it", note=None,
                                     lines=[cannot_show_line(h, ctx) for h in cannot], after=None))
    return groups
