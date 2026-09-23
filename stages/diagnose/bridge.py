"""Step 5, customer lens: where the revenue change came from, customer by
customer (docs/AI_PIPELINE.md section 7.6, docs/DIAGNOSE_DESIGN.md 5.5.5).

An additive bridge, exact by construction rather than by attribution: every
customer active in either period lands in exactly one class, and the six terms
sum to the revenue change. Nothing here is a Shapley value - there is no
multiplicative formula to split, only arithmetic to account for.

The word is **lapsed**, never "churned". Retail is not a subscription, and a
customer who did not buy this month has not left forever; the engine says what
it measured over one period, which is what the term means.
"""

from dataclasses import dataclass

import pandas as pd

from contracts.diagnosis import BridgeTerms, CustomerLens
from shared.transactions import is_blank
from stages.diagnose.inputs import RunData, period_mask, shift_month
from stages.diagnose.lever import customer_revenue
from stages.diagnose.thresholds import LEFT_CENSOR_MONTHS


@dataclass(frozen=True)
class Transition:
    """One prev -> cur pair and everything the bridge needs about it."""

    previous: str
    current: str


def compute_bridge(data: RunData) -> CustomerLens | None:
    """The bridge for the current transition, plus the previous one when the
    file covers it, plus the evidence C1/C3 need to judge it."""
    customer_col = data.parsed.reverse.get("customer")
    if customer_col is None:
        return None

    period = data.metrics.period
    current = Transition(previous=period.previous, current=period.current)
    terms, evidence = _bridge(data, customer_col, current)

    earlier = Transition(previous=shift_month(period.previous, -1), current=period.previous)
    previous_transition = None
    missing = [month for month in (earlier.previous, earlier.current)
               if month not in data.months_with_rows]
    if not missing:
        previous_transition, _ = _bridge(data, customer_col, earlier)
    else:
        # `months_with_rows`, not `complete_months`: a calendar-complete month
        # holding no rows produced an all-zero bridge that was then offered to
        # C1-C3 as a real comparison of flows. That is 3B doubt-review finding
        # 2 in a new place - a month with no rows is evidence of a gap, never
        # evidence of what normal looks like (3C doubt-review R3).
        evidence["previous_transition_reason"] = (
            f"no revenue-counted rows in {', '.join(missing)}"
        )

    return CustomerLens(**terms.model_dump(), previous_transition=previous_transition,
                        evidence=evidence)


def _bridge(
    data: RunData, customer_col: str, transition: Transition
) -> tuple[BridgeTerms, dict]:
    previous = customer_revenue(data, transition.previous, customer_col)
    current = customer_revenue(data, transition.current, customer_col)
    first = _first_activity(data, customer_col)
    first_month = first["month"].to_dict()

    in_prev = set(previous.index)
    in_cur = set(current.index)
    retained = sorted(in_prev & in_cur)
    entered = sorted(in_cur - in_prev)
    lapsed = sorted(in_prev - in_cur)

    # "New" is first activity anywhere in the file, not merely absence from the
    # previous month: a customer who bought in March, skipped April and came
    # back in May is resurrected, not new.
    new = [name for name in entered if first_month.get(name) == transition.current]
    resurrected = [name for name in entered if first_month.get(name) != transition.current]

    gains = sum(max(0.0, current[name] - previous[name]) for name in retained)
    losses = sum(max(0.0, previous[name] - current[name]) for name in retained)

    terms = BridgeTerms(
        new=float(current.reindex(new).sum()),
        resurrected=float(current.reindex(resurrected).sum()),
        expansion=float(gains),
        # Signed, so the six terms simply add up to the revenue change.
        contraction=-float(losses),
        lapsed=-float(previous.reindex(lapsed).sum()),
        unattributed=_unattributed(data, customer_col, transition),
    )
    return terms, _evidence(data, transition, new, first, previous, current)


def _unattributed(data: RunData, customer_col: str, transition: Transition) -> float:
    """The change in revenue from rows with no customer on them. Without this
    term the identity would not close on any real file - blank customer cells
    are the norm, not the exception."""
    blank = is_blank(data.df[customer_col])
    amounts = data.parsed.revenue_amounts
    current = float(amounts[period_mask(data, transition.current) & blank].sum())
    previous = float(amounts[period_mask(data, transition.previous) & blank].sum())
    return current - previous


def _first_activity(data: RunData, customer_col: str) -> pd.DataFrame:
    """Each customer's first appearance in the file: the month of it, and
    whether that first appearance was a return.

    "Anywhere in the file" includes months too partial to be complete months,
    because the question is only whether we have ever seen this customer
    before. Where several rows share a customer's earliest date, the net
    quantity of that day decides - a same-day buy-and-refund is not a customer
    whose first act was a return.
    """
    mask = data.parsed.counted & ~is_blank(data.df[customer_col])
    if not mask.any():
        return pd.DataFrame(columns=["month", "first_is_return"])
    frame = pd.DataFrame({
        "customer": data.df.loc[mask, customer_col],
        "month": data.months[mask],
        "date": data.parsed.dates[mask],
        "quantity": data.parsed.quantities[mask],
    })
    first_date = frame.groupby("customer")["date"].transform("min")
    opening = frame[frame["date"] == first_date]
    return pd.DataFrame({
        "month": opening.groupby("customer")["month"].min(),
        "first_is_return": opening.groupby("customer")["quantity"].sum() < 0,
    })


def _evidence(
    data: RunData, transition: Transition, new: list[str],
    first: pd.DataFrame, previous: pd.Series, current: pd.Series,
) -> dict:
    """What C1 and C3 need to know before trusting the "new" term."""
    file_start = data.metrics.period.data_start
    months_in = (
        (int(transition.current[:4]) * 12 + int(transition.current[5:7]))
        - (file_start.year * 12 + file_start.month)
    )
    returns_first = first["first_is_return"].reindex(new, fill_value=False)
    return {
        "transition": f"{transition.previous} -> {transition.current}",
        "new_customers": len(new),
        # A customer whose first-ever activity in the file is a return almost
        # certainly bought before the file starts - they are returning
        # something they were never recorded buying. A left-censoring hint for
        # the narration (Thach, 3C); it changes no term, because excluding
        # them would break the identity.
        #
        # This asks about the customer's FIRST ROW, not the sign of their month
        # (3C doubt-review R2): a customer who bought on the 5th and refunded
        # more on the 20th has a negative month but did not start with a
        # return, and one who refunded on the 6th and bought on the 21st has a
        # positive month and did. The first version counted both backwards.
        "new_customers_whose_first_activity_is_a_return": int(returns_first.sum()),
        # Within the first few months of the file, "new" mostly means "first
        # seen", not "first ever": everyone looks new when the file starts.
        "left_censored": months_in < LEFT_CENSOR_MONTHS,
        "months_since_file_start": months_in,
        # A transition with an empty side decomposes an artifact: every
        # customer looks new or lapsed because the month holds nothing. The
        # lever lens refuses such a period outright (Thach, 3C); the bridge
        # still adds up, so it reports rather than refuses - but it must not
        # report silently (3C doubt-review R3).
        "empty_period": [
            label for label, series in (("previous", previous), ("current", current))
            if series.empty
        ],
    }
