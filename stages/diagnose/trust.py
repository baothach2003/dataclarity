"""Step 2: can the data be trusted? (docs/AI_PIPELINE.md section 7.3)

Three checks run before anything is explained, because explaining an artefact
is worse than explaining nothing. Each returns ok / caution / blocked /
inconclusive with the evidence behind it; the gate takes the worst.

Only D1 can block. D2 and D3 describe things that are *consistent with* a data
problem but equally consistent with a real business decision, and the engine
must not claim to tell those apart.
"""

import pandas as pd

from contracts.diagnosis import Trust, TrustCheck
from stages.diagnose.inputs import RunData, days_in_month, month_dates
from stages.diagnose.frame import first_sale, previous_leading_days_missing
from stages.diagnose.thresholds import (
    D1_BLOCK_SHARE,
    D1_CAUTION_DAYS,
    D1_CAUTION_SHARE,
    D1_LEARN_MIN_ACTIVE_SHARE,
)
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
    checks = [
        d1_coverage(data, history),
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


def d1_coverage(data: RunData, history: list[str]) -> TrustCheck:
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
    # A previous month the file only partly covers is not a comparison base,
    # whatever the history says (Thach, 3E1): blocked at D1's own caution size,
    # so one leading closed day (New Year's Day) is not read as a cut export.
    # A file with NO row in the previous month is the extreme case: it
    # headlined "products were launched or discontinued (100%)" for 0 -> 310,
    # the launch being where the export starts (3E1, run to the headline).
    # And a previous month with NO sale anywhere in it, even in a file with
    # history: it only cautioned "worth roughly 0" and a product sold for
    # eleven months was headlined as launched (3E1 doubt-review cycle 4).
    leading = previous_leading_days_missing(data)
    days_prev = days_in_month(period.previous)
    # Any counted row in the month, NOT `months_with_rows`: that set holds only
    # complete months, so a January starting on the 2nd read as "no sales".
    empty_prev = not bool((data.parsed.counted & (data.months == period.previous)).any())
    if empty_prev or leading >= D1_CAUTION_DAYS or leading >= D1_CAUTION_SHARE * days_prev:
        first = str(first_sale(data))
        where = (f"the file has no sales in {period.previous}, the month the current one is "
                 f"compared with" if empty_prev else
                 f"the file's first sale is on {first}, {leading} days into {period.previous}, "
                 "the month the current one is compared with, so that month is incomplete")
        return TrustCheck(
            id="D1", status="blocked",
            evidence={"previous_leading_days_missing": leading, "first_sale": first,
                      "previous_month_has_sales": not empty_prev},
            message=f"{where[0].upper()}{where[1:]}. If the export was cut short, re-export "
                    f"the file from {period.previous}-01; if the shop opened then, there is "
                    "no full month to compare with yet.")
    # Only months that hold rows can teach what normal looks like. A history
    # month with nothing in it is itself a gap, and letting it set the
    # expectation lets missing data hide missing data: three empty months lift
    # the learned zero-rate enough to absorb a real six-day hole in the current
    # month, and the file with MORE missing data gets the cleaner verdict
    # (3B doubt-review finding 2).
    # ...and never from the PREVIOUS month: it is itself checked below, and
    # learning "normal" from it let a 12-day February gap teach itself away
    # (3E1 doubt-review cycle 2, M2).
    candidates = [month for month in history if month in data.months_with_rows
                  and month != period.previous]
    empty_history = [month for month in history if month not in data.months_with_rows]
    active = _active_dates(data)
    # ...nor from a month that is itself mostly gap: a March missing 20 days,
    # or a November holding one row, taught "closed" as normal and hid a real
    # gap in the current month (3E1 doubt-review cycle 3). Measured against
    # the history's own median, so a sparse shop's ordinary months all stay.
    active_days = {month: len(month_dates(month)) - _zero_days(active, month)
                   for month in candidates}
    floor = D1_LEARN_MIN_ACTIVE_SHARE * float(pd.Series(active_days).median()) \
        if active_days else 0.0
    learned_from = [month for month in candidates if active_days[month] >= floor]
    sparse_history = [month for month in candidates if active_days[month] < floor]
    if not learned_from:
        # The previous month is never learned from, so a two-month file lands
        # here with a complete, full history month: say so rather than "no
        # month holds rows" (3E1 doubt-review cycle 4).
        return TrustCheck(
            id="D1", status="inconclusive",
            evidence={"history_months": len(history),
                      "history_months_with_rows": len(history) - len(empty_history),
                      "learned_from_months": 0},
            message="No complete month before the current one, other than the month it is "
                    "compared with (which is itself under check), has sales to learn this "
                    "store's normal trading pattern from.")

    zero_rates = _zero_rate_by_weekday(active, learned_from)

    evidence: dict[str, object] = {
        "zero_rate_by_weekday": {str(day): round(rate, 4) for day, rate in zero_rates.items()},
        "history_months_with_rows": len(history) - len(empty_history),
        "learned_from_months": len(learned_from),
        "empty_history_months": empty_history,
        "sparse_history_months": sparse_history,
    }
    excess = {}
    for label, month in (("cur", period.current), ("prev", period.previous)):
        observed = _zero_days(active, month)
        expected = _expected_zero_days(zero_rates, month)
        excess[label] = max(0.0, observed - expected)
        evidence[f"zero_days_{label}"] = observed
        evidence[f"expected_zero_days_{label}"] = round(expected, 3)
        evidence[f"excess_zero_days_{label}"] = round(excess[label], 3)

    # Each gap at its OWN month's pace, since a month's missing days would have
    # traded at that month's rate: pricing at the other month's pace flipped
    # the sign of D1 when both months had gaps and revenue grew (3E1
    # doubt-review cycle 2, F1), and a message priced one way beside a verdict
    # priced the other showed the reader two figures for one gap (cycle 3).
    # The PREVIOUS month can be the incomplete one, inflating the change
    # upward (3E1 doubt-review #4): it cautions but never blocks - the
    # current month is the one being diagnosed.
    gap = excess["cur"] * _mean_revenue_per_active_day(data, period.current)
    gap_prev = excess["prev"] * _mean_revenue_per_active_day(data, period.previous)
    evidence["estimated_revenue_gap"] = round(gap, 2)
    evidence["estimated_revenue_gap_prev"] = round(gap_prev, 2)

    days = days_in_month(period.current)
    if excess["cur"] >= D1_BLOCK_SHARE * days:
        observed = evidence["zero_days_cur"]
        return TrustCheck(
            id="D1", status="blocked", evidence=evidence,
            message=f"{observed} of {days} days in the current month have no sales at all, "
                    f"about {excess['cur']:.0f} more than this store's normal closing "
                    "pattern explains - missing data, or days the shop was closed. Too few "
                    "trading days to diagnose.")
    if excess["cur"] >= D1_CAUTION_DAYS or excess["cur"] >= D1_CAUTION_SHARE * days:
        return TrustCheck(
            id="D1", status="caution", evidence=evidence,
            message=f"About {excess['cur']:.0f} days in the current month have no sales beyond "
                    "this store's normal closing pattern (missing data, or days the shop was "
                    f"closed), worth roughly {gap:,.0f} in revenue.")
    days_prev = days_in_month(period.previous)
    if excess["prev"] >= D1_CAUTION_DAYS or excess["prev"] >= D1_CAUTION_SHARE * days_prev:
        return TrustCheck(
            id="D1", status="caution", evidence=evidence,
            message=f"About {excess['prev']:.0f} days in the previous month have no sales "
                    "beyond this store's normal closing pattern (missing data, or days the "
                    f"shop was closed), worth roughly {gap_prev:,.0f} in revenue - the change "
                    "is measured against an incomplete month.")
    return TrustCheck(
        id="D1", status="ok", evidence=evidence,
        message="Coverage matches this store's normal trading pattern.")


def excess_zero_days(data: RunData, check: TrustCheck, month: str) -> float | None:
    """Zero-sale days in any `month` beyond D1's learned weekday pattern, or
    None when D1 learned none. For T2's year-ago pair, which D1 does not check
    (3E1 doubt-review cycle 3: a year-ago gap read as the season)."""
    rates = check.evidence.get("zero_rate_by_weekday")
    if rates is None:
        return None
    zero_rates = {int(day): rate for day, rate in rates.items()}
    return max(0.0, _zero_days(_active_dates(data), month)
               - _expected_zero_days(zero_rates, month))


def _active_dates(data: RunData) -> pd.Series:
    """Revenue per calendar date, over revenue-counted rows only."""
    counted = data.parsed.counted
    return data.parsed.revenue_amounts[counted].groupby(
        data.parsed.dates[counted].dt.normalize()).sum()


def _zero_rate_by_weekday(active: pd.Series, history: list[str]) -> dict[int, float]:
    """Share of history dates of each weekday (0 = Monday) with no revenue."""
    traded = set(active.index)
    rates: dict[int, float] = {}
    counts: dict[int, list[int]] = {day: [0, 0] for day in range(7)}
    for month in history:
        for day in month_dates(month):
            slot = counts[day.weekday()]
            slot[1] += 1
            if day not in traded:
                slot[0] += 1
    for day, (zeros, total) in counts.items():
        rates[day] = zeros / total if total else 0.0
    return rates


def _zero_days(active: pd.Series, month: str) -> int:
    traded = set(active.index)
    return sum(1 for day in month_dates(month) if day not in traded)


def _expected_zero_days(zero_rates: dict[int, float], month: str) -> float:
    return sum(zero_rates[day.weekday()] for day in month_dates(month))


def _mean_revenue_per_active_day(data: RunData, month: str) -> float:
    """Active days only: dividing by calendar days would understate the gap for
    a shop that closes regularly."""
    active = _active_dates(data)
    in_month = active[active.index.to_period("M").astype(str) == month]
    return float(in_month.mean()) if len(in_month) else 0.0
