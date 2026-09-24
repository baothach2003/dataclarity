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
from shared.first_purchase import first_purchase_months
from shared.transactions import customer_identity, is_blank, merged_identity_count
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


def classify(
    previous: pd.Series, current: pd.Series, first_month: dict[str, str], month: str
) -> dict[str, str]:
    """Which class each customer falls into for one transition.

    The single statement of the rule. It used to be stated twice - once here
    and once inside `_bridge` - under a docstring claiming that step 6 taking
    its classes from step 5 made divergence impossible. It did not: two copies
    of a rule diverge the moment one is edited, and nothing compared them
    (3D doubt-review R9). Now `_bridge` calls this too, so there is one rule
    and both callers are wrong together or right together.
    """
    in_prev, in_cur = set(previous.index), set(current.index)
    classes = {name: "retained" for name in in_prev & in_cur}
    classes |= {name: "lapsed" for name in in_prev - in_cur}
    # New before present: a free sample or a coupon last month makes a
    # customer present in it, yet their first purchase is this month - the
    # bridge called them retained while stage 2 called them new (2E-c
    # doubt-review F2). A customer who BOUGHT last month cannot have their
    # first purchase this month, and one who refunded before their first sale
    # has none in the file (their history opens with a refund), so only a
    # deduction moves anyone here.
    classes |= {name: "new" for name in in_cur if first_month.get(name) == month}
    for name in in_cur - in_prev - {n for n, c in classes.items() if c == "new"}:
        # "New" is the FIRST PURCHASE anywhere in the file, not merely absence
        # from the previous month: a customer who bought in March, skipped
        # April and came back in May is resurrected, not new. A customer whose
        # history opens with a refund has no first purchase in the file - the
        # refund proves one before it - so they come back, never arrive
        # (shared/first_purchase.py; Thach, 2E-c, superseding 3C's "note only").
        classes[name] = "resurrected"
    return classes


def customer_classes(data: RunData) -> dict[str, str]:
    """Each customer's class for the current transition, for step 6."""
    customer_col = data.parsed.reverse.get("customer")
    if customer_col is None:
        return {}
    period = data.metrics.period
    return classify(
        customer_revenue(data, period.previous, customer_col),
        customer_revenue(data, period.current, customer_col),
        _first_purchase(data, customer_col).to_dict(),
        period.current,
    )


def _bridge(
    data: RunData, customer_col: str, transition: Transition
) -> tuple[BridgeTerms, dict]:
    previous = customer_revenue(data, transition.previous, customer_col)
    current = customer_revenue(data, transition.current, customer_col)
    first_month = _first_purchase(data, customer_col).to_dict()

    # One statement of the rule, shared with step 6 (see `classify`).
    classes = classify(previous, current, first_month, transition.current)
    members = {label: sorted(name for name, value in classes.items() if value == label)
               for label in ("new", "resurrected", "retained", "lapsed")}
    new, resurrected = members["new"], members["resurrected"]
    retained, lapsed = members["retained"], members["lapsed"]

    gains = sum(max(0.0, current[name] - previous[name]) for name in retained)
    losses = sum(max(0.0, previous[name] - current[name]) for name in retained)

    terms = BridgeTerms(
        # Each new customer's CHANGE: a coupon of -5 last month and 100 now
        # brings +105, so the six terms still sum to the change.
        new=float(current.reindex(new).sum() - previous.reindex(new).fillna(0.0).sum()),
        resurrected=float(current.reindex(resurrected).sum()),
        expansion=float(gains),
        # Signed, so the six terms simply add up to the revenue change.
        contraction=-float(losses),
        lapsed=-float(previous.reindex(lapsed).sum()),
        unattributed=_unattributed(data, customer_col, transition),
    )
    return terms, _evidence(data, customer_col, transition, new, resurrected, first_month,
                            previous, current)


def _unattributed(data: RunData, customer_col: str, transition: Transition) -> float:
    """The change in revenue from rows with no customer on them. Without this
    term the identity would not close on any real file - blank customer cells
    are the norm, not the exception."""
    blank = is_blank(data.df[customer_col])
    amounts = data.parsed.revenue_amounts
    current = float(amounts[period_mask(data, transition.current) & blank].sum())
    previous = float(amounts[period_mask(data, transition.previous) & blank].sum())
    return current - previous


def _first_purchase(data: RunData, customer_col: str) -> pd.Series:
    """Each customer's first purchase month in the file, or None when the file
    holds none (shared/first_purchase.py: only refunds, or a history that
    opens with one). Keyed on the normalised identity (3C2), so "first
    purchase in the file" is the PERSON's: keyed raw, a customer's second
    spelling looked like someone who had never bought, and landed in `new`.

    "Anywhere in the file" includes months too partial to be complete months,
    because the question is only whether we have ever seen this customer buy.
    """
    mask = data.parsed.counted & ~is_blank(data.df[customer_col])
    parsed = data.parsed
    return first_purchase_months(customer_identity(data.df.loc[mask, customer_col]),
                                 parsed.dates[mask], parsed.sale[mask], parsed.returned[mask])


def _evidence(
    data: RunData, customer_col: str, transition: Transition, new: list[str],
    resurrected: list[str], first_month: dict, previous: pd.Series, current: pd.Series,
) -> dict:
    """What C1 and C3 need to know before trusting the "new" term."""
    file_start = data.metrics.period.data_start
    months_in = (
        (int(transition.current[:4]) * 12 + int(transition.current[5:7]))
        - (file_start.year * 12 + file_start.month)
    )
    return {
        "transition": f"{transition.previous} -> {transition.current}",
        "new_customers": len(new),
        # Customers who arrived this month (absent from the previous one) with
        # no first purchase in the file - their history opens with a refund,
        # or they only got refunds, coupons or free items. Since 2E-c they are
        # resurrected, not new (Thach, rule C); 3C recorded them as a note on
        # `new` instead. The opening day is judged on its own lines - any
        # return line there, since 2E-c2 - not the sign of the month (3C
        # doubt-review R2).
        "arrivals_with_no_first_purchase_in_the_file": sum(
            first_month.get(name) is None for name in resurrected),
        # Within the first few months of the file, "new" mostly means "first
        # seen", not "first ever": everyone looks new when the file starts.
        "left_censored": months_in < LEFT_CENSOR_MONTHS,
        "months_since_file_start": months_in,
        # How many distinct raw customer values normalisation collapsed, over
        # the whole file (3C2). Reported here rather than in metrics.json,
        # which would be a stage 2 contract change; `evidence` is already a
        # free-form object in CONTRACTS section 7. A large number is worth
        # seeing: it says the customer column is inconsistently entered, which
        # is context for every C-family verdict built on it.
        "customer_values_merged_by_normalisation": merged_identity_count(
            data.df.loc[data.parsed.counted, customer_col]
        ),
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
