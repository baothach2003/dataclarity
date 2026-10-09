"""Sections 1 and 2 of the front: the 30-second summary and the waterfall
(docs/REPORT_REDESIGN.md 1.1, 1.2; Thach Q1-Q4, Q22, Q24, Q33, Q37-Q41).
Thach's pattern (2026-10-06): what a stage 3 result MEANS is data stage 3
writes - which month a check is about (`trust.checks[].month`), whether the
headline is the offsetting case (`headline.offsetting`), the causes it names
(`headline.named`), how many years a season reads - never inferred here;
where a field is missing, the front says less. Every figure is a field,
formatted - with as many decimals as it takes for the printed figures to
agree with stage 3's comparison."""

from fractions import Fraction

from contracts.diagnosis import DiagnosisContract, HeadlineMovement, TrustCheck
from contracts.lever_bridge import LeverBridge
from contracts.metrics import MetricsContract, Period
from contracts.report_front import FrontBar, Waterfall
from shared.claim_lines import Context, match_phrase
from shared.wording import amount, count, month_name, month_only, prints_as_zero, signed, times, two

NOT_PROFIT = ("Sales here means the money customers paid (before any costs). It is not profit: the file has no "
              "cost data.")
HEDGES = {"seasonal": "This may be seasonal: treat it as a pointer, not a finding.",
          "plain": "A shift like this can happen in any month: treat it as a pointer, not a finding."}
# D1-D3 in one line when none cautions or blocks (Thach, 2026-10-06); a check
# that could not run (too few products, a month-grain file) is no problem
# found either, said as such.
# Thach, Q45: "passed" - "no problem found" stood beside days with no sales a
# season explains (D1's check ok, its hypothesis matching the change).
# Thach, Q70: the technical part named as the page and report.html name it.
CHECKS_OK = "Data checks passed (see Technical details)."
# Thach, Q59: with the count of the checks that could run.
CHECKS_PARTLY = "Data checks passed ({ran} of {total} could run on this file; see Technical details)."
# The trust checks by id, status and the month stage 3 says they are about
# (Thach, Q37, Q39); stage 3's own message stays in the appendix, as written.
# `{when}` is " in <month>", or nothing where the file names no month (before
# diagnosis 18.7): the front never guesses this month.
CHECK_WORDS = {
    ("D1", "caution"): "Some days{when} have no sales at all - missing data, or days the shop was closed (the file "
                       "cannot tell which).",
    ("D1", "blocked"): "at least half the days{when} have no sales at all - missing data, or days the shop was "
                       "closed.",
    # D2 says what it tests (Thach, 2026-10-06), and both meanings (CLAUDE.md 3.3a).
    ("D2", "caution"): "A sudden price jump or fall across most products{when}: a change in the data's units or "
                       "currency, or a deliberate repricing (the file cannot tell which).",
    ("D3", "caution"): "Many rows{when} were flagged during cleaning."}
COVERAGE_BLOCKED = "the file does not show sales across the whole of {month}, so the two months cannot be compared."
UNNAMED_BLOCK = "the data checks did not pass - see Technical details for which, and why."  # Q70
_LABELS = {"customers": "Customers who placed an order", "frequency": "Orders per customer", "orders": "Orders",
           "aov": "Average order value", "units_per_order": "Items per order",
           "price_per_unit": "Average price per item"}
# A file with no order id counts lines (metrics `orders_basis`): never "orders".
_LINES_LABELS = {"customers": "Customers who bought", "frequency": "Lines per customer", "orders": "Lines",
                 "aov": "Average line value", "units_per_order": "Items per line"}
SPLIT_WITHHELD = {
    "refund_lines": "returns in these months make the split into items per {unit} and price per item unreliable, "
                    "so it is not drawn",
    "aov_unchanged": "it did not change, so there is nothing to split",
    "net_units_not_positive": "the items sold, net of returns, are zero or fewer in a month, so the split cannot be "
                              "drawn"}
NOT_DRAWN = "The chart of what changed is not drawn: {why}."
BRIDGE_WITHHELD = {
    "zero_orders": "a compared month has no {unit}s to split",
    "month_not_positive": "a compared month's sales are zero or below, so the change cannot be split into parts",
    "not_to_the_cent": "the amounts are too large to split exactly to the cent",
    "failed_checks": "the split into parts did not pass its checks, so it is not shown",
    None: "this report's diagnosis was made before the chart existed - run the diagnosis again to draw it"}


def _when(check: TrustCheck, period: Period) -> str:
    if check.month is None:
        return ""
    return f" in {month_name(period.current if check.month == 'current' else period.previous)}"


def check_line(check: TrustCheck, period: Period) -> str | None:
    """A caution's or a block's words, by the month stage 3 wrote."""
    if check.status == "blocked" and check.id == "D1" and check.month is None:
        return UNNAMED_BLOCK
    if check.month == "coverage":
        return COVERAGE_BLOCKED.format(month=month_name(period.previous))
    words = CHECK_WORDS.get((check.id, check.status))
    return None if words is None else words.format(when=_when(check, period))


def check_lines(checks: list[TrustCheck], status: str, period: Period) -> list[str]:
    return [line for check in checks if check.status == status
            and (line := check_line(check, period)) is not None]


def data_checks(checks: list[TrustCheck], period: Period) -> list[str]:
    cautions = check_lines(checks, "caution", period)
    if cautions:
        return cautions
    if all(check.status == "ok" for check in checks):
        return [CHECKS_OK]
    ran = sum(1 for check in checks if check.status == "ok")  # a count of the checks listed, no figure of the file
    return [CHECKS_PARTLY.format(ran=ran, total=len(checks))]


def _printed(value: float, decimals: int) -> Fraction:
    """The figure as the text prints it (Q44: never round(value * 10**d),
    which can differ - 4.35 is stored just under 4.35 and prints "4.3")."""
    return Fraction(f"{value:.{decimals}f}")


def _bumped(value: float, decimals: int) -> int:
    """The decimals a figure is printed with: a change that moved never
    prints as zero (the review: "+0.0%")."""
    while value != 0 and decimals < 4 and round(value, decimals) == 0:
        decimals += 1
    return decimals


def _shown(value: float, decimals: int) -> Fraction:
    """The figure exactly as the sentence prints it."""
    return _printed(value, _bumped(value, decimals))


def places(value: float, typical: float, factor: float, singled_out: bool) -> int | None:
    """The decimals at which the printed figures agree with stage 3's test
    (|value| >= factor x typical when singled out, under it when not) - never
    "+10.0%" beside "less than twice ... about 5.0%" (the reviews) - and a
    typical that is not zero never prints as zero. None where no precision
    up to 4 does: the sentence is then not said (the scoped review of
    Q56-Q62: "+0.2780%" beside "less than twice ... 0.1390%")."""
    for found in (1, 2, 3, 4):
        typical_shown = _shown(typical, found)
        if typical > 0 and typical_shown == 0:
            continue
        shown, bound = _shown(abs(value), found), Fraction(str(factor)) * typical_shown
        if (shown >= bound) if singled_out else (shown < bound):
            return found
    return None


def side(shown: Fraction, bound: Fraction) -> str:
    """Thach, Q58: "at least" only where the printed figures are equal."""
    return "more than" if shown > bound else "at least"


def season_places(change: float, expected: float, gap: float, typical: float, factor: float,
                  beyond: bool) -> int | None:
    """The decimals at which the season sentence's printed figures agree with
    themselves and with stage 3's band (Q44, Q57): the printed gap is the
    reader's subtraction of the two printed changes; a typical gap that is
    not zero never prints as zero; beyond the band the printed gap is at
    least `factor` times the printed typical, inside it less. None where no
    precision up to 4 does: the yardstick is then not said (the scoped
    review: "a gap of 14.7364 points" beside 103.5729 - 88.8364)."""
    for found in (1, 2, 3, 4):
        shown_gap = _shown(abs(gap), found)
        if shown_gap != abs(_shown(change, found) - _shown(expected, found)):
            continue
        typical_shown = _shown(typical, found)
        if typical > 0 and typical_shown == 0:
            continue
        bound = Fraction(str(factor)) * typical_shown
        if (shown_gap >= bound) if beyond else (shown_gap < bound or shown_gap == 0):
            return found
    return None


def _pct(value: float, decimals: int, sign: bool = True) -> str:
    decimals = _bumped(value, decimals)
    text = f"{value:+,.{decimals}f}%" if sign else f"{value:,.{decimals}f}%"
    return text[1:] if text.startswith("-") and set(text) <= set("-0.,%") else text


def _points(value: float, decimals: int) -> str:
    return f"{value:,.{_bumped(value, decimals)}f}"


def _moved(value: float) -> str:
    return "rose" if value > 0 else "fell" if value < 0 else "stayed the same"


def whom(years: int) -> str:
    """The season's comparison, by the years it reads (never "last year's"
    beside several years: the review)."""
    return "last year's" if years == 1 else "earlier years"


def sentence_b(movement: HeadlineMovement | None) -> tuple[str | None, bool, int]:
    """The comparison with the shop's own history, as a fact with its figure
    (Q3: no adjective), whether the change is inside it (B opens: a season
    in line, or under the size test - design 1.1), and the decimals sentence
    A prints its percentage with: the decimals of the sentence printed, so
    one change is printed one way (Q56)."""
    if movement is None or movement.change_pct is None:
        return None, False, 1
    season, change = movement.season, movement.change_pct
    inside = (season is not None and season.band == "consistent") or movement.singled_out is False
    if season is not None and season.band in ("consistent", "shortfall", "excess"):
        expected, gap, typical = season.expected_change_pct, season.difference_pct, season.typical_pct
        beyond = season.band != "consistent"
        factor = season.beyond_factor if beyond else movement.factor
        agreed = season_places(change, expected, gap, typical, factor, beyond)
        decimals = 1 if agreed is None else agreed
        if season.years == 1:
            facts = f"{_pct(expected, decimals, False)} last year, {_pct(change, decimals, False)} this year (one " \
                    "earlier year to compare with)"
        else:
            facts = (f"in the {season.years} earlier years, sales typically {_moved(expected)} "
                     f"{_pct(abs(expected), decimals, False)} between these months; this year they {_moved(change)} "
                     f"{_pct(abs(change), decimals, False)}")
        verb = "is in line with" if not beyond else "differs from"
        if agreed is None:
            return f"This change {verb} {whom(season.years)}: {facts}.", inside, decimals
        # The yardstick from stage 3's fields (Thach, Q57): the gap and the
        # shop's typical gap, printed as the reader can check them.
        shown_gap = _shown(abs(gap), decimals)
        bound = Fraction(str(factor)) * _shown(typical, decimals)
        word = "within" if not beyond else side(shown_gap, bound)
        yardstick = (f"a gap of {_points(abs(gap), decimals)} points, {word} {times(factor)} this shop's typical gap "
                     f"({_points(typical, decimals)} points)")
        return f"This change {verb} {whom(season.years)}: {facts} - {yardstick}.", inside, decimals
    if movement.singled_out is None or movement.typical_pct is None:
        return ("The file's history is too short to compare this change with this shop's earlier month-to-month "
                "changes.", False, 1)
    decimals = places(change, movement.typical_pct, movement.factor, movement.singled_out)
    if decimals is None:
        return None, inside, 1
    shown = _shown(abs(change), decimals)
    bound = Fraction(str(movement.factor)) * _shown(movement.typical_pct, decimals)
    word = side(shown, bound) if movement.singled_out else "less than"
    return (f"That is {word} {times(movement.factor)} this shop's typical month-to-month change (about "
            f"{_pct(movement.typical_pct, decimals, False)}).", inside, decimals)


def sentence_a(metrics: MetricsContract, bridge: LeverBridge | None, code: str | None, decimals: int = 1) -> str:
    """This month's sales and the change: the bridge's shown cents (Q22), or
    the exact change where no chart is drawn (Q24)."""
    core, period = metrics.core, metrics.period
    current, previous = month_name(period.current), month_name(period.previous)
    if bridge is not None:
        now, was, change = bridge.shown_current, bridge.shown_previous, bridge.shown_change
    else:
        now, was, change = core.revenue_current, core.revenue_previous, core.revenue_change
    percent = "" if core.revenue_change_pct is None else f" ({_pct(core.revenue_change_pct, decimals)})"
    if change is None:
        return f"Sales in {current} were {amount(now, code)}, against {amount(was, code)} in {previous}{percent}."
    if prints_as_zero(change):
        return f"Sales in {current} were {amount(now, code)}, the same as in {previous}."
    direction = "up" if change > 0 else "down"
    return (f"Sales in {current} were {amount(now, code)}, {direction} {amount(abs(change), code)}{percent} on "
            f"{previous} ({amount(was, code)}).")


def sentence_c(diagnosis: DiagnosisContract, ctx: Context) -> list[str]:
    """The main reason, worded "the figures match", never "caused by"; the
    causes from `headline.named` (Q33) and the offsetting case from
    `headline.offsetting` (Q40), never from the message or the signs. A
    file that does not say either gets no sentence C (say less)."""
    headline = diagnosis.headline
    movement = headline.movement
    season = movement.season if movement is not None else None
    by_id = {h.id: h for h in diagnosis.hypotheses}
    named = headline.named or ([headline.hypothesis_id] if headline.hypothesis_id else None)
    match headline.rule:
        case 5 | 6 if named and all(i in by_id for i in named):
            causes = [by_id[i] for i in named]
            if headline.offsetting:
                return ["The change is what is left of movements in opposite directions, among them: "
                        + "; ".join(match_phrase(h, ctx, with_worth=True) for h in causes) + "."]
            if headline.rule == 6 and headline.hypothesis_id is None and headline.offsetting is None:
                return []  # before 18.7: a tie cannot be told from the offsetting case
            return ["The figures match " + "; and equally ".join(match_phrase(h, ctx) for h in causes) + "."]
        case 5 | 6:
            return []
        case 4:
            unit, average = (("lines", "average line value") if ctx.lines_basis
                             else ("orders", "average order value"))
            first = (f"Underneath, the number of {unit} and the {average} moved a lot in opposite directions and "
                     "largely cancelled out.")
            return [first, HEDGES[headline.hedge]] if headline.hedge else [first]
        case 2:
            return ["The change matches days with no sales at all - missing data, or days the shop was closed (the "
                    "file cannot tell which)."]
    if season is not None and season.band == "consistent":
        return [f"Nothing else stands out: the change is in line with {whom(season.years)}, so none of the checks "
                "below is named as the reason."]
    if season is not None and season.band in ("shortfall", "excess"):
        return ["No single reason is named."]
    if movement is not None and movement.singled_out is None:
        return ["With this little history, no single reason can be picked out."]
    return ["No single reason stands out."]


def waterfall(bridge: LeverBridge, metrics: MetricsContract, code: str | None) -> Waterfall:
    """The bridge's bars as stage 3 wrote them, labelled (Q1, Q4); each
    value by its unit: an amount coded, a count whole, a rate to two decimals."""
    lines = metrics.core.orders_basis == "lines"
    labels = _LABELS | (_LINES_LABELS if lines else {})
    money = ("aov", "price_per_unit")
    whole = ("customers", "orders")

    def shown(factor: str, value: float) -> str:
        return amount(value, code) if factor in money else count(value) if factor in whole else two(value)

    period = metrics.period
    note = None
    if not bridge.aov_split and bridge.aov_split_withheld is not None:
        value = "Average line value" if lines else "Average order value"
        note = (f"{value} is shown as one bar: "
                f"{SPLIT_WITHHELD[bridge.aov_split_withheld].format(unit='line' if lines else 'order')}.")
    return Waterfall(
        previous_label=f"{month_name(period.previous)} sales", current_label=f"{month_name(period.current)} sales",
        shown_previous=bridge.shown_previous, shown_current=bridge.shown_current, shown_change=bridge.shown_change,
        previous_text=amount(bridge.shown_previous, code), current_text=amount(bridge.shown_current, code),
        change_text=signed(bridge.shown_change, code),
        bars=[FrontBar(factor=bar.factor, label=labels[bar.factor], was=shown(bar.factor, bar.value_prev),
                       now=shown(bar.factor, bar.value_cur), shown=bar.shown, worth=signed(bar.shown, code))
              for bar in bridge.bars],
        # Thach, Q67: "from the first bar to the last" - a phone draws the bars across.
        caption=(f"Read from the first bar to the last: {month_only(period.previous)}'s sales, then what each part "
                 f"added or took away, ending at {month_only(period.current)}'s sales. The bars add up exactly to the "
                 "change. 'Worth' amounts split the effect of things that moved together, so read them as sizes, not "
                 "exact causes."),
        note=note)
