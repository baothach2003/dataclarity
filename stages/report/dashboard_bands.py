"""The dashboard's words, as few as Thach's layout allows (report.json 2.11;
docs/DASHBOARD_DESIGN.md section 10): the one short line under the tiles,
the checked chips and the next-month and next-step bands. Every figure is a
field of an earlier file or a sentence the front section already words,
formatted - nothing is computed (CONTRACTS 11); every long text stays in the
front section, which Technical details prints whole."""

from contracts.diagnosis import DiagnosisContract
from contracts.lever_bridge import LeverBridge
from contracts.metrics import MetricsContract
from contracts.report import ForecastView, HypothesisView, Numbers
from contracts.report_dashboard import Chip, ChipStatus, Headline, NextMonthBand
from contracts.report_front import Front
from shared.claim_lines import DATA_IDS
from shared.wording import amount, month_name, prints_as_zero, signed
from stages.report.front_checklist import checklist_groups
from stages.report.front_summary import pct, sales_figures, sentence_b

BLOCKED_LINE = "Not compared: the data checks did not pass"
# The season's verbs, the front's own (front_summary.sentence_b).
_SEASON_VERB = {"consistent": "in line with", "shortfall": "differs from", "excess": "differs from"}
# The chips' subjects (design section 10): a word or two per check of the checklist.
_SUBJECT = {"C1": "Customers", "C2": "Customers", "C3": "Customers", "B1": "Order frequency", "B2": "Basket size",
            "P1": "Prices", "P2": "Product mix", "P3": "Refunds", "P4": "Discounts", "P5": "Charges",
            "R1": "One product", "R2": "Products in or out", "R3": "Stock", "T1": "Calendar", "T2": "Last year"}
_LINES_SUBJECT = {"B1": "Lines per customer"}  # a file that counts lines never says "order" (the review)
_ORDER = ("Customers", "Order frequency", "Lines per customer", "Basket size", "Prices", "Product mix", "Refunds",
          "Discounts", "Charges", "One product", "Products in or out", "Stock", "Calendar", "Last year")
# What each group of the checklist found, as a chip says it; a subject of several checks takes the strongest.
_STATUS: dict[str, ChipStatus] = {"matches": "matches", "moved": "moved", "against": "other way",
                                  "not_reason": "checked", "cannot_show": "can't tell"}
_STRENGTH: tuple[ChipStatus, ...] = ("matches", "other way", "moved", "checked", "can't tell")


def headline(*, metrics: MetricsContract, diagnosis: DiagnosisContract, bridge: LeverBridge | None, front: Front,
             numbers: Numbers, code: str | None) -> Headline:
    """Row 2: the summary as one line of at most about 20 words (Thach,
    replacing Q1). The change printed as sentence A prints it (its percentage
    at sentence B's decimals: one change printed one way, Q56); the season by
    the front's own verbs and figure."""
    # The summary's notes (the sales figure's among them): the line states its verdict (the scoped review's R1).
    notes = list(front.notes.summary)
    period, revenue = numbers.period, numbers.kpis[0]
    current, previous = month_name(period.current), month_name(period.previous)
    if front.state == "blocked":
        return Headline(text=BLOCKED_LINE, notes=notes, asides=[*front.summary, front.sales_note])
    # Behind the line's marker (the review: "in line with" needs its why): the caution lines, the front's own
    # summary - the season's gap and the shop's typical gap - then what the amounts are.
    asides = [*front.caution, *front.summary, front.sales_note]
    if revenue.current is None:
        return Headline(text=f"Sales in {current} not shown: no sale can be counted", notes=notes, asides=asides)
    if front.state == "not_compared":
        why = (f"{previous} is not covered whole" if not period.previous_complete
               else f"no sale in {previous} can be counted")
        return Headline(text=f"Sales {amount(revenue.current, code)} in {current} · not compared: {why}", notes=notes,
                        asides=asides)
    movement = diagnosis.headline.movement
    decimals = sentence_b(movement)[2]
    _, _, change = sales_figures(metrics, bridge)
    change_pct = metrics.core.revenue_change_pct
    if change is not None and prints_as_zero(change):
        text = f"Sales the same as {previous}"
    elif change_pct is not None:
        text = f"Sales {pct(change_pct, decimals)} vs {previous}"
    else:
        text = f"Sales {signed(change or 0.0, code)} vs {previous}"
    season = movement.season if movement is not None else None
    if season is not None and season.band in _SEASON_VERB:
        whom = "last year" if season.years == 1 else "earlier years"
        text += f" · {_SEASON_VERB[season.band]} {whom} ({pct(season.expected_change_pct, decimals)})"
    return Headline(text=text, notes=notes, asides=asides)


def checked(*, front: Front, diagnosis: DiagnosisContract, views: list[HypothesisView],
            lines_basis: bool) -> list[Chip]:
    """Row 4's "Checked": the data checks, then one chip per subject the
    checklist's own groups name (one copy: `checklist_groups`)."""
    if front.state == "blocked":
        return []
    chips = [Chip(label="Data", status="caution" if front.caution else "checked")]
    if front.state != "compared":
        return chips
    found: dict[str, ChipStatus] = {}
    for kind, ids in checklist_groups(diagnosis, views):
        for hypothesis_id in ids:
            if hypothesis_id in DATA_IDS or hypothesis_id not in _SUBJECT:
                continue
            subject = (_LINES_SUBJECT if lines_basis else {}).get(hypothesis_id, _SUBJECT[hypothesis_id])
            status = _STATUS[kind]
            held = found.get(subject)
            if held is None or _STRENGTH.index(status) < _STRENGTH.index(held):
                found[subject] = status
    return chips + [Chip(label=subject, status=found[subject]) for subject in _ORDER if subject in found]


def next_month(*, view: ForecastView, front: Front, code: str | None) -> NextMonthBand:
    """Row 4's "Next month": the forecast's first point and its range as
    numbers; the front's sentences behind the band's marker - the first too,
    which says what "likely" means (the review)."""
    notes = list(front.notes.next_month)
    if view.insufficient_history or not view.points:
        return NextMonthBand(month=None, figure=None, value=None, low=None, low_value=None, high=None,
                             high_value=None, reason="not estimated: too little history", notes=notes,
                             asides=list(front.next_month))
    first = view.points[0]
    return NextMonthBand(month=month_name(first.period), figure=amount(first.point, code), value=first.point,
                         low=amount(first.low, code), low_value=first.low, high=amount(first.high, code),
                         high_value=first.high, reason=None, notes=notes, asides=list(front.next_month))


def next_steps(front: Front) -> list[str]:
    """Row 4's "Next step": one line per suggested action, its own words;
    why and what to watch stay in Technical details."""
    return [item.action for item in front.next_steps.items] if front.next_steps is not None else []
