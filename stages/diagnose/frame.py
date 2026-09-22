"""Step 1: what is compared with what (docs/AI_PIPELINE.md section 7.2).

The comparison pair is not chosen here - it is stage 2's own `period`, so the
diagnosis explains exactly the change metrics.json reports. This step adds the
two things the later steps need around it: the same pair one year earlier (for
T2, seasonality) and the history window (for the calendar weights and the XmR
baselines).
"""

from contracts.diagnosis import Frame
from stages.diagnose.inputs import RunData, shift_month
from stages.diagnose.thresholds import HISTORY_MAX_MONTHS, YOY_LAG_MONTHS


def build_frame(data: RunData) -> Frame:
    period = data.metrics.period

    # Both or neither: a year-ago comparison with only one side is not a
    # comparison, and T2 would have nothing to divide by. Membership is tested
    # against months that hold rows, not merely months the calendar covers - a
    # year-ago month with no sales gives T2 a zero denominator, which is the
    # same "nothing to divide by" this guard exists to prevent (3B
    # doubt-review finding 7).
    year_ago_current = shift_month(period.current, -YOY_LAG_MONTHS)
    year_ago_previous = shift_month(period.previous, -YOY_LAG_MONTHS)
    has_year_ago = (
        year_ago_current in data.months_with_rows
        and year_ago_previous in data.months_with_rows
    )

    history = history_window(data)
    return Frame(
        current=period.current,
        previous=period.previous,
        year_ago_current=year_ago_current if has_year_ago else None,
        year_ago_previous=year_ago_previous if has_year_ago else None,
        history_months=len(history),
        history_start=history[0] if history else None,
        history_end=history[-1] if history else None,
    )


def history_window(data: RunData) -> list[str]:
    """Complete months strictly before `current`, most recent
    HISTORY_MAX_MONTHS. Ascending.

    Strictly before, so the month being diagnosed never helps set the
    expectation it is judged against. Capped, because a shop's behaviour two
    years ago is a different business.
    """
    current = data.metrics.period.current
    earlier = [month for month in data.complete_months if month < current]
    return earlier[-HISTORY_MAX_MONTHS:]
