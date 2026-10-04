"""Evidence for D1 and the time family - T1 the calendar, T2 seasonality, T3
routine variation (docs/AI_PIPELINE.md 7.8) - split out of
`hypothesis_evidence.py` in 2E-j for file size. In a month-grain file their
day-level steps do not apply and say so (Thach, Q1 of 2E-h).
"""

from contracts.diagnosis import is_verdict
from stages.diagnose.inputs import MONTH_GRAIN_NOTE
from stages.diagnose.lever import month_revenue
from stages.diagnose.numbers import typical_magnitude, usable_base
from stages.diagnose.step7_inputs import Changes, Outcome, Step7Inputs
from stages.diagnose.trust import excess_zero_days, pattern_found


def check_of(inputs: Step7Inputs, check_id: str):
    return next(check for check in inputs.trust.checks if check.id == check_id)


# --- data quality -------------------------------------------------------------

def month_grain_outcome(what: str) -> Outcome:
    """Not testable in a month-grain file (Thach, Q1 of 2E-h; 2E-j), saying so."""
    return Outcome(verdict="not_testable", evidence={"month_grain": True},
                   rule=f"{what} cannot be seen: {MONTH_GRAIN_NOTE}")


def d1(inputs: Step7Inputs, moved: Changes) -> Outcome:
    check = check_of(inputs, "D1")
    # Read off the check, which knows the file's grain (trust.d1_coverage).
    if check.evidence.get("month_grain"):
        return month_grain_outcome("days with no sales")
    if "estimated_revenue_gap" not in check.evidence:
        # D1 could not run, or blocked before measuring (a previous month the
        # file only partly covers): there is no gap figure to weigh.
        return Outcome(verdict="inconclusive", evidence=dict(check.evidence),
                       rule="D1 could not measure the gaps: " + check.message)
    gap_cur = float(check.evidence["estimated_revenue_gap"])
    gap_prev = float(check.evidence["estimated_revenue_gap_prev"])
    evidence = {"estimated_revenue_gap": gap_cur, "estimated_revenue_gap_prev": gap_prev,
                "d1_status": check.status}
    if not pattern_found(check):
        # Tied to the check's test (Thach, 3E1): a few excess zero days are
        # noise in a sparse shop, and D1 came out supported on 17-24 of 40
        # shops with NO missing data. "Missing" is what the check's thresholds
        # define, and the rule says what the check found rather than "none"
        # (cycle 3). Since 3E1b the test is applied to the days beyond the
        # weekday PATTERN, not to the badge: a closure the shop has every year
        # is no data problem, yet it still moves the month (review 1, F1).
        found = (check.evidence["excess_zero_days_cur"], check.evidence["excess_zero_days_prev"])
        return Outcome(verdict="ruled_out", evidence=evidence,
                       rule=f"excess zero days (current {found[0]:.1f}, previous "
                            f"{found[1]:.1f}) stay under the D1 check's thresholds")
    # Days with no sales this month pull the change down, last month's push it
    # up, each priced at its OWN month's pace (7.3; 3E1 doubt-review cycle 2, F1).
    return Outcome(contribution=gap_prev - gap_cur, evidence=evidence)


# --- time -----------------------------------------------------------------------

def t1(inputs: Step7Inputs, moved: Changes) -> Outcome:
    if inputs.calendar.method == "not_applicable":
        return month_grain_outcome("the mix of weekdays in a month")
    effect = inputs.calendar.calendar_effect
    return Outcome(contribution=effect, evidence={"calendar_effect": effect,
                                                  "method": inputs.calendar.method})


def t2(inputs: Step7Inputs, moved: Changes) -> Outcome:
    """Seasonality: what last year's move from the same previous month to the
    same current month would have done to this year's previous month. Divides
    by the year-ago previous month, so it goes through the SAME base guard as
    step 4's year-over-year series (`usable_base`) - a 12.50 year-ago month
    would otherwise make seasonality "explain" anything."""
    frame = inputs.frame
    if frame.year_ago_current is None or frame.year_ago_previous is None:
        return Outcome(verdict="inconclusive",
                       evidence={"reason": "the year-ago pair is not in the data"},
                       rule="requires the year-ago pair")
    ly_prev = month_revenue(inputs.data, frame.year_ago_previous)
    ly_cur = month_revenue(inputs.data, frame.year_ago_current)
    history = [month_revenue(inputs.data, month) for month in inputs.history]
    typical = typical_magnitude(history)
    scale = max((abs(value) for value in history), default=0.0)
    evidence = {"ly_prev": ly_prev, "ly_cur": ly_cur,
                "revenue_prev": moved.revenue_prev, "typical_month": typical}
    if not usable_base(ly_prev, typical, scale):
        return Outcome(verdict="inconclusive", evidence=evidence,
                       rule="the year-ago previous month fails the base guard "
                            "(AI_PIPELINE 7.5): not a denominator")
    if moved.revenue_prev <= 0 or ly_cur <= 0:
        return Outcome(verdict="inconclusive", evidence=evidence,
                       rule="a month netted zero or below; a year-ago ratio "
                            "cannot be applied to it")
    # D1 checks only the compared months; a year-ago month with missing days
    # is a "season" that never happened: last February's 10-day gap
    # headlined rule 5 (3E1 doubt-review cycle 3). Any excess day refuses; checked last, after the
    # arithmetic refusals.
    # A day-level guard: in a month-grain file there is no day to miss, so it
    # does not apply, and seasonality reads the months as they are (Thach, Q1
    # of 2E-h; refused on "days with no sales" before - 2E-j review cycle 1 #3).
    if inputs.data.metrics.period.month_grain:
        evidence["zero_day_guard"] = f"not applicable: {MONTH_GRAIN_NOTE}"
        return Outcome(contribution=moved.revenue_prev * (ly_cur / ly_prev - 1), evidence=evidence)
    check = check_of(inputs, "D1")
    for label, month in (("cur", frame.year_ago_current), ("prev", frame.year_ago_previous)):
        found = excess_zero_days(inputs.data, check, month)
        evidence[f"excess_zero_days_year_ago_{label}"] = None if found is None else round(found, 3)
    if any(evidence[f"excess_zero_days_year_ago_{label}"] != 0 for label in ("cur", "prev")):
        return Outcome(verdict="inconclusive", evidence=evidence,
                       rule="a year-ago month has days with no sales beyond this store's "
                            "pattern (or D1 learned none), so it is not a year-ago pair to compare")
    return Outcome(contribution=moved.revenue_prev * (ly_cur / ly_prev - 1), evidence=evidence)


def t3(inputs: Step7Inputs, moved: Changes) -> Outcome:
    """Always inconclusive in v1 (ADR-0007), written as the full rule so the
    Backlog's "unusualness verdicts" switches it on by changing `is_verdict`
    alone."""
    signals = inputs.signals or []
    without = [s.series for s in signals if not is_verdict(s)]
    revenue = next((s for s in signals if s.series == "revenue"), None)
    evidence = {"series_without_verdict": without}
    if revenue is None or not is_verdict(revenue):
        return Outcome(verdict="inconclusive", evidence=evidence,
                       rule="revenue has no year-over-year verdict (ADR-0006, ADR-0007)")
    fired = [s.series for s in signals if is_verdict(s) and s.rule in (1, 2)]
    routine = not fired and not moved.alert
    return Outcome(verdict="supported" if routine else "ruled_out",
                   evidence={**evidence, "series_with_signal": fired},
                   rule="no rule-1 or rule-2 verdict on any series and no masked alert")
