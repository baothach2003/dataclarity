"""Step 2: can the data be trusted? (docs/AI_PIPELINE.md section 7.3)

Three checks run before anything is explained, because explaining an artefact
is worse than explaining nothing. Each returns ok / caution / blocked /
inconclusive with the evidence behind it; the gate takes the worst.

Only D1 can block. D2 and D3 describe things that are *consistent with* a data
problem but equally consistent with a real business decision, and the engine
must not claim to tell those apart.
"""

from collections.abc import Mapping
from typing import Any

import pandas as pd

from contracts.diagnosis import Trust, TrustCheck
from stages.diagnose.d1_pattern import MonthZeros, cautions, count_zeros, judge, pattern_zero_days, zero_rates
from stages.diagnose.inputs import MONTH_GRAIN_NOTE, RunData, days_in_month
from stages.diagnose.frame import previous_coverage_of
from stages.diagnose.thresholds import D1_HISTORY_MAX_MONTHS
# D2 and D3 live in trust_checks.py; re-exported so callers keep one import.
from stages.diagnose.trust_checks import d2_price_level, d3_flagged_rows

__all__ = ["evaluate_trust", "d1_coverage", "d2_price_level", "d3_flagged_rows"]

# Rows stage 1 removed are simply not in cleaned.csv, so nothing here can tell
# which period they belonged to. Stated in the output rather than quietly
# ignored; fixing it needs dropped-row counts per month in
# cleaning_report.json, which is a stage 1 contract change (Backlog).
DROPPED_ROWS_LIMITATION = (
    "rows dropped in stage 1 cannot be assigned to a period, so a gap caused by "
    "dropped rows is invisible here"
)


def evaluate_trust(data: RunData, history: list[str]) -> Trust:
    """`history`: the frame's window, the call shape every step shares. Since
    3E1b no check reads it - D1 learns from its own, longer window."""
    del history
    checks = [
        d1_coverage(data),
        d2_price_level(data),
        d3_flagged_rows(data),
    ]
    statuses = {check.status for check in checks}
    if "blocked" in statuses:
        verdict = "blocked"
    elif "caution" in statuses or "inconclusive" in statuses:
        # `inconclusive` downgrades too (Thach, 3B): a check that could not run
        # is not evidence that the data is fine, and reporting "trusted" on a
        # run where two of three checks never executed claims a verification
        # that did not happen. Caution never changes the headline (7.8), so the
        # cost is one honest badge on thin files.
        verdict = "caution"
    else:
        verdict = "trusted"
    return Trust(verdict=verdict, checks=checks, limitations=[DROPPED_ROWS_LIMITATION])


# --- D1: days of data missing -------------------------------------------------


def d1_coverage(data: RunData) -> TrustCheck:
    """Zero-revenue days beyond what this store's own weekday pattern predicts.

    The expectation is per weekday, not one scalar rate (Thach, session 3B): a
    shop closed on Sundays has a zero-rate near 1.0 on Sundays and near 0 on
    Tuesdays, and months hold four or five of each. A single scalar leaves a
    residue that varies with month shape - bounded well under the caution
    threshold, but nonzero - while per-weekday rates cancel regular closing
    exactly. It also makes a *Tuesday* gap visible in a shop that never trades
    Sundays, which a scalar rate partly absorbs.
    """
    period = data.metrics.period
    # A previous month the file only partly covers - or holds no sale in at
    # all - is not a comparison base, whatever the history says (Thach, 3E1):
    # a file starting on 15 January headlined "customers bought more often
    # (100%)", a one-month file "products were launched (100%)" for 0 -> 310,
    # and a product sold for eleven months, absent one December, "launched"
    # (3E1 cycles 3 and 4). The rule is shared/periods.py's, the one stage 2
    # applies to metrics.json (2E), so the two stages cannot disagree about it.
    coverage = previous_coverage_of(data)
    if not coverage.complete:
        return TrustCheck(
            id="D1", status="blocked", month="coverage",
            evidence={"previous_leading_days_missing": coverage.leading_days_missing,
                      "first_sale": (coverage.first_counted.isoformat()
                                     if coverage.first_counted else None),
                      "previous_month_has_sales": coverage.has_rows},
            message=coverage.reason)
    # A month-grain file has one dated day a month (the 1st or the last), so
    # a day with no sales is every other day: the check read "normal" and passed, having
    # measured nothing (Thach, Q1 of 2E-h; 2E-j).
    # Not applicable, as Thach put it - not "could not run", which would
    # badge every monthly file "caution" (2E-j review cycle 1 #11).
    if period.month_grain:
        return TrustCheck(
            id="D1", status="not_applicable", evidence={"month_grain": True},
            message=f"Days with no sales do not apply: {MONTH_GRAIN_NOTE}.")
    # Only months that hold rows can teach what normal looks like. A history
    # month with nothing in it is itself a gap, and letting it set the
    # expectation lets missing data hide missing data: three empty months lift
    # the learned zero-rate enough to absorb a real six-day hole in the current
    # month, and the file with MORE missing data gets the cleaner verdict
    # (3B doubt-review finding 2).
    # ...and never from the PREVIOUS month: it is itself checked below, and
    # learning "normal" from it let a 12-day February gap teach itself away
    # (3E1 doubt-review cycle 2, M2).
    # D1 learns from more than the frame's 24 months when the file holds them
    # (3E1b review 1, F2): a month's same calendar month a year and two years
    # earlier tell a season from a gap; at exactly two years the previous
    # month's has one copy, and the badge cautions rather than guess (3.3a).
    window = [month for month in data.complete_months
              if month < period.current][-D1_HISTORY_MAX_MONTHS:]
    candidates = [month for month in window if month in data.months_with_rows
                  and month != period.previous]
    empty_history = [month for month in window if month not in data.months_with_rows]
    active = _active_dates(data)
    months = _zero_counts(active, [*candidates, period.previous, period.current])
    # ...nor from a month that is itself mostly gap: a March missing 20 days,
    # or a November holding one row, taught "closed" as normal and hid a real
    # gap in the current month (3E1 doubt-review cycle 3) - and a December
    # missing 14 of 31 days still did under the "half the median active
    # days" floor (cycle 4; 3E1b part B). A month is excluded when its own
    # excess over the others would caution (d1_pattern.learn).
    judged = judge(months, candidates, period.current, period.previous)
    if judged is None:
        # The previous month is never learned from, so a two-month file lands
        # here with a complete, full history month: say so rather than "no
        # month holds rows" (3E1 doubt-review cycle 4).
        return TrustCheck(
            id="D1", status="inconclusive",
            evidence={"history_months": len(window),
                      "history_months_with_rows": len(window) - len(empty_history),
                      "learned_from_months": 0},
            message="No complete month before the current one, other than the month it is "
                    "compared with (which is itself under check), has sales to learn this "
                    "store's normal trading pattern from.")

    rates = zero_rates(months, judged.weekdays)
    evidence: dict[str, object] = {
        "zero_rate_by_weekday": {str(day): round(rate, 4) for day, rate in enumerate(rates)},
        "history_months_with_rows": len(window) - len(empty_history),
        "learned_from_months": len(judged.learned),
        "learned_months": judged.learned,
        # The learned months the weekday rates come from: an annual closure
        # is learned for its season but teaches no weekday (3E1b review 3, R1).
        "weekday_months": judged.weekdays,
        "empty_history_months": empty_history,
        "gapped_history_months": judged.excluded,
        "caution_min_days": judged.floor,
    }
    # Two excesses (3E1b review 1, F1): beyond the weekday PATTERN - what B1's
    # and T2's refusals, the gaps and the D1 hypothesis read, since a closure
    # still moves the month against the other - and beyond the pattern AND the
    # same month of other years (UNEXPLAINED) - what the badge reads: an annual
    # closure is no missing data.
    by_label = {"cur": judged.current, "prev": judged.previous}
    for label, month in by_label.items():
        evidence[f"zero_days_{label}"] = month.observed
        evidence[f"expected_zero_days_{label}"] = round(month.pattern, 3)
        evidence[f"excess_zero_days_{label}"] = round(month.excess, 3)
        evidence[f"seasonal_expected_zero_days_{label}"] = round(month.expected, 3)
        evidence[f"unexplained_zero_days_{label}"] = round(month.unexplained, 3)
        evidence[f"caution_bar_days_{label}"] = round(month.bar, 3)
    excess = {label: month.excess for label, month in by_label.items()}
    unexplained = {label: month.unexplained for label, month in by_label.items()}

    # Each gap at its OWN month's pace, since a month's missing days would have
    # traded at that month's rate: pricing at the other month's pace flipped
    # the sign of D1 when both months had gaps and revenue grew (3E1
    # doubt-review cycle 2, F1), and a message priced one way beside a verdict
    # priced the other showed the reader two figures for one gap (cycle 3).
    # The PREVIOUS month can be the incomplete one, inflating the change
    # upward (3E1 doubt-review #4): it cautions but never blocks - the
    # current month is the one being diagnosed.
    pace = {"cur": _mean_revenue_per_active_day(data, period.current),
            "prev": _mean_revenue_per_active_day(data, period.previous)}
    evidence["estimated_revenue_gap"] = round(excess["cur"] * pace["cur"], 2)
    evidence["estimated_revenue_gap_prev"] = round(excess["prev"] * pace["prev"], 2)

    days = days_in_month(period.current)
    if judged.blocked:
        observed = evidence["zero_days_cur"]
        return TrustCheck(
            id="D1", status="blocked", evidence=evidence, month="current",
            message=f"{observed} of {days} days in the current month have no sales at all, "
                    f"about {unexplained['cur']:.0f} more than this store's normal closing "
                    "pattern explains - missing data, or days the shop was closed. Too few "
                    "trading days to diagnose.")
    for label, which, tail in (("cur", "current", "."),
                               ("prev", "previous", " - the change is measured against an incomplete month.")):
        if by_label[label].flagged:
            count, verb = _days(unexplained[label])
            return TrustCheck(
                id="D1", status="caution", evidence=evidence, month=which,
                message=f"About {count} in the {which} month {verb} no sales beyond this store's "
                        "normal closing pattern (missing data, or days the shop was closed), worth "
                        f"roughly {unexplained[label] * pace[label]:,.0f} in revenue{tail}")
    # Days the season explains but the weekday pattern does not (an annual
    # closure, an off-season) are no missing data, yet the D1 hypothesis reads
    # them (F1): an "ok" saying coverage is normal stood beside rule 2's "days
    # with no sales explain the change". Both measures stay; the badge says so
    # (Thach, 2026-10-05, Q3).
    usual = usual_days_sentence(evidence, period.current, period.previous)
    return TrustCheck(
        id="D1", status="ok", evidence=evidence,
        message=usual or "Coverage matches this store's normal trading pattern.")


def excess_zero_days(data: RunData, check: TrustCheck, month: str) -> float | None:
    """Zero-sale days in any `month` beyond D1's learned weekday PATTERN, or
    None when D1 learned none. For T2's year-ago pair, which D1 does not check
    (3E1 doubt-review cycle 3: a year-ago gap read as the season): measured
    against the learned months other than itself, and against the pattern
    alone - a closure in the year-ago month moves last year's season whatever
    the season expects (3E1b review 1, F1)."""
    learned = check.evidence.get("weekday_months")
    if learned is None:
        return None
    others = [other for other in learned if other != month]
    months = _zero_counts(_active_dates(data), [*others, month])
    return max(0.0, months[month].total - pattern_zero_days(months, month, others))


# English whatever the process locale (calendar.month_name follows it).
MONTH_NAMES = ("January", "February", "March", "April", "May", "June", "July", "August", "September",
               "October", "November", "December")


def months_beyond_pattern(evidence: Mapping[str, Any]) -> list[str]:
    """The compared months ("cur", "prev") whose days with no sales beyond the
    weekday pattern pass D1's caution test - the D1 hypothesis's own test
    (3E1b review 1, F1), read off the check's evidence so the badge (Q3) and
    the hypothesis read one predicate on the same figures."""
    return [label for label in ("cur", "prev")
            if cautions(float(evidence[f"excess_zero_days_{label}"]),
                        float(evidence[f"caution_bar_days_{label}"]),
                        float(evidence["caution_min_days"]))]


def pattern_found(check: TrustCheck) -> bool:
    """Whether days with no sales beyond the weekday pattern pass D1's caution
    test in either compared month: an annual closure explains a change though
    it is no missing data."""
    return bool(months_beyond_pattern(check.evidence))


def usual_days_sentence(evidence: Mapping[str, Any], current: str, previous: str) -> str:
    """The badge beside an "ok" its season explains (Thach, 2026-10-05, Q3):
    one sentence per month the D1 hypothesis finds, the current month first;
    empty when it finds none. "As in other years" only where it is what was
    measured - this month's days beyond the weekday pattern, rounded, equal
    to what the same month of other years held beyond theirs; otherwise both
    figures are stated, for the data cannot tell whether the difference is
    lost days or ordinary variation (CLAUDE.md 3.3a; the Q3 review, finding
    1: 4 beside the other Decembers' 2 read "as in other years")."""
    months = {"cur": current, "prev": previous}
    sentences = []
    for label in months_beyond_pattern(evidence):
        beyond = f"{float(evidence[f'excess_zero_days_{label}']):.0f}"
        season = max(0.0, float(evidence[f"seasonal_expected_zero_days_{label}"])
                     - float(evidence[f"expected_zero_days_{label}"]))
        usual = "as in other years" if f"{season:.0f}" == beyond else f"against about {season:.0f} in other years"
        sentences.append(f"Days with no sales match this store's usual {MONTH_NAMES[int(months[label][5:7]) - 1]}: "
                         f"{beyond} beyond its weekday pattern, {usual}.")
    return " ".join(sentences)


def _days(excess: float) -> tuple[str, str]:
    return ("1 day", "has") if round(excess) == 1 else (f"{excess:.0f} days", "have")


def _zero_counts(active: pd.Series, months: list[str]) -> dict[str, MonthZeros]:
    traded = set(active.index.date)
    return {month: count_zeros(traded, month) for month in dict.fromkeys(months)}


def _active_dates(data: RunData) -> pd.Series:
    """Net revenue per TRADING date: a date with at least one sale row (2E
    doubt-review F2). A date holding only refund lines is a day without
    sales - ten such days hid ten missing days and B1 headlined "customers
    bought less often (79%)". Each trading date's value is its sales less
    its own refunds; refunds on refund-only dates are left out, so a gap is
    priced at a trading day's pace (Thach, 2E cycle 2: a missing day is
    missing sales, not missing refunds)."""
    counted = data.parsed.counted
    days = data.parsed.dates.dt.normalize()
    trading = set(days[data.parsed.sale])
    revenue = data.parsed.revenue_amounts[counted].groupby(days[counted]).sum()
    return revenue[revenue.index.isin(trading)]


def _mean_revenue_per_active_day(data: RunData, month: str) -> float:
    """Active days only: dividing by calendar days would understate the gap for
    a shop that closes regularly."""
    active = _active_dates(data)
    in_month = active[active.index.to_period("M").astype(str) == month]
    return float(in_month.mean()) if len(in_month) else 0.0
