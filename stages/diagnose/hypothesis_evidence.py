"""One evidence function per catalog id (docs/AI_PIPELINE.md 7.8).

Each returns an `Outcome`: a finished verdict when the hypothesis is
directional or a requirement is not met, otherwise the contribution the
shared share rule in `hypotheses.py` judges. None of them reads a step-4 row
as a judgement - since ADR-0007 no row is one.
"""

from contracts.diagnosis import is_verdict
from stages.diagnose.members import product_totals
from stages.diagnose.lever import month_revenue
from stages.diagnose.numbers import is_negligible, typical_magnitude, usable_base
from stages.diagnose.step7_inputs import Changes, Outcome, Step7Inputs
from stages.diagnose.stockout import detect_stockouts
from stages.diagnose.trust import excess_zero_days
# The customer family lives in its own module (file size); c4 is re-exported.
from stages.diagnose.hypothesis_evidence_customers import (
    NOT_TESTABLE_NO_CUSTOMER,
    bridge_difference,
    c4,
    no_customer,
)

def _check(inputs: Step7Inputs, check_id: str):
    return next(check for check in inputs.trust.checks if check.id == check_id)


# --- data quality -------------------------------------------------------------

def d1(inputs: Step7Inputs, moved: Changes) -> Outcome:
    check = _check(inputs, "D1")
    if "estimated_revenue_gap" not in check.evidence:
        # D1 could not run, or blocked before measuring (a previous month the
        # file only partly covers): there is no gap figure to weigh.
        return Outcome(verdict="inconclusive", evidence=dict(check.evidence),
                       rule="D1 could not measure the gaps: " + check.message)
    gap_cur = float(check.evidence["estimated_revenue_gap"])
    gap_prev = float(check.evidence["estimated_revenue_gap_prev"])
    evidence = {"estimated_revenue_gap": gap_cur, "estimated_revenue_gap_prev": gap_prev,
                "d1_status": check.status}
    if check.status == "ok":
        # Tied to the check (Thach, 3E1): a few excess zero days are noise in
        # a sparse shop, and D1 came out supported on 17-24 of 40 shops with
        # NO missing data. "Missing" is what the check's thresholds define,
        # and the rule says what the check found rather than "none" (cycle 3).
        found = (check.evidence["excess_zero_days_cur"], check.evidence["excess_zero_days_prev"])
        return Outcome(verdict="ruled_out", evidence=evidence,
                       rule=f"excess zero days (current {found[0]:.1f}, previous "
                            f"{found[1]:.1f}) stay under the D1 check's thresholds")
    # Days with no sales this month pull the change down, last month's push it
    # up, each priced at its OWN month's pace (7.3; 3E1 doubt-review cycle 2, F1).
    return Outcome(contribution=gap_prev - gap_cur, evidence=evidence)


def _directional_check(check_id: str):
    def evaluate(inputs: Step7Inputs, moved: Changes) -> Outcome:
        check = _check(inputs, check_id)
        verdict = {"caution": "supported", "inconclusive": "inconclusive"}.get(
            check.status, "ruled_out")
        return Outcome(verdict=verdict, evidence={"check_status": check.status,
                                                  **check.evidence},
                       rule=f"supported when {check_id} cautions")
    return evaluate


# --- time -----------------------------------------------------------------------

def t1(inputs: Step7Inputs, moved: Changes) -> Outcome:
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
                       rule="a month netted zero or below; a seasonal ratio "
                            "cannot be applied to it")
    # D1 checks only the compared months; a year-ago month with missing days
    # is a "season" that never happened: last February's 10-day gap
    # headlined rule 5 (3E1 doubt-review cycle 3). Any excess day refuses; checked last, after the
    # arithmetic refusals.
    check = _check(inputs, "D1")
    for label, month in (("cur", frame.year_ago_current), ("prev", frame.year_ago_previous)):
        found = excess_zero_days(inputs.data, check, month)
        evidence[f"excess_zero_days_year_ago_{label}"] = None if found is None else round(found, 3)
    if any(evidence[f"excess_zero_days_year_ago_{label}"] != 0 for label in ("cur", "prev")):
        return Outcome(verdict="inconclusive", evidence=evidence,
                       rule="a year-ago month has days with no sales beyond this store's "
                            "pattern (or D1 learned none), so it is not a season to compare")
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


# --- lever ----------------------------------------------------------------------

def _refunds_in_level_2(inputs: Step7Inputs) -> Outcome | None:
    """INTERIM for B2 only (Thach, 2E), until the three-factor level 2 (a
    session after 3E2, before 3F). Since 2E an order is a sale row, so refunds
    no longer move purchase frequency and B1 is evaluated on refund months.
    Level 2 still splits AOV into NET units per order x price per net unit, so
    a refunded unit leaves the basket: with this refusal lifted, a month where
    ONLY refunds changed headlined "baskets got smaller (100% of the change)"
    (measured in 2E). Either period with any refund leaves B2 inconclusive."""
    # Any return LINE, not only refunded money (2E doubt-review cycle 3): a
    # zero-price write-off carries units but no money, and B2 headlined
    # "baskets got bigger" while baskets shrank from 3 units to 1.
    period = inputs.data.metrics.period
    lines = {label: int((inputs.data.parsed.returned
                         & (inputs.data.months == month)).sum())
             for label, month in (("prev", period.previous), ("cur", period.current))}
    # ...and any counted row with a negative amount: a refund booked as
    # quantity +1 at a negative price is a "sale row" of one unit to level 2,
    # and B2 read "baskets got smaller" while every real basket was 3 units
    # (2E doubt-review cycle 4; Thach, 2E-b).
    for label, month in (("prev", period.previous), ("cur", period.current)):
        lines[label] += int((inputs.data.parsed.counted
                             & (inputs.data.parsed.revenue_amounts < 0)
                             & ~inputs.data.parsed.returned
                             & (inputs.data.months == month)).sum())
    if lines["prev"] or lines["cur"]:
        return Outcome(verdict="inconclusive",
                       # Line counts only: the returns lens's money counts
                       # qty<0 rows alone, so "12 refund lines, 0.0 refunded"
                       # side by side read as a contradiction (2E-b review).
                       evidence={"refund_lines_prev": lines["prev"],
                                 "refund_lines_cur": lines["cur"]},
                       rule="level 2 counts refunded units against the basket, so basket "
                            "size cannot be separated from refund lines (return lines, or "
                            "lines with a negative amount - a refund, or a discount or "
                            "coupon line) until level 2 has a refund factor of its own")
    return None


def b1(inputs: Step7Inputs, moved: Changes) -> Outcome:
    if no_customer(inputs):
        return NOT_TESTABLE_NO_CUSTOMER
    # An order is a row count, so a day with no sales removes whole orders and
    # reads as customers buying less often: two missing days under D1's
    # threshold headlined "customers bought less often (100%)" (3E1 doubt-
    # review cycle 3). Refused on ANY excess zero day, or when D1 could not
    # learn a pattern (Thach, 3E1). B2 is not refused: removing whole orders
    # leaves units per order unchanged - measured, 0 movement on 48 shops.
    check = _check(inputs, "D1")
    excess = (check.evidence.get("excess_zero_days_cur"),
              check.evidence.get("excess_zero_days_prev"))
    if None in excess or max(excess) > 0:
        return Outcome(verdict="inconclusive",
                       evidence={"d1_status": check.status,
                                 "excess_zero_days_cur": excess[0],
                                 "excess_zero_days_prev": excess[1]},
                       rule="a day with no sales removes whole orders, so frequency cannot "
                            "be separated from missing or closed days; requires D1 to find "
                            "no excess zero day in either month")
    # AOV = net revenue / orders is not positive in a month that netted zero
    # or below, and the Shapley frequency term changes sign with it: B1
    # headlined "customers bought MORE often (+21,400)" while frequency fell
    # 9.3 -> 3.1 (2E doubt-review cycle 2, F1). The masked-shift alert
    # refuses such months for the same reason.
    if moved.revenue_prev <= 0 or moved.revenue_cur <= 0:
        return Outcome(verdict="inconclusive",
                       evidence={"revenue_prev": moved.revenue_prev,
                                 "revenue_cur": moved.revenue_cur},
                       rule="a compared month netted zero or below, so its frequency "
                            "term's sign cannot be read")
    level = inputs.tree.lever.level1
    if level is None or level.formula != "customers*frequency*aov":
        reason = inputs.tree.lever.reasons.get("level1_form") or inputs.tree.lever.reasons.get(
            "level1", "level 1 could not use the three-factor form")
        return Outcome(verdict="inconclusive", evidence={"reason": reason},
                       rule="requires the customers x frequency x AOV split")
    factor = next(f for f in level.factors if f.name == "frequency")
    return Outcome(contribution=factor.contribution,
                   evidence={"frequency_prev": factor.value_prev,
                             "frequency_cur": factor.value_cur})


def b2(inputs: Step7Inputs, moved: Changes) -> Outcome:
    if (refused := _refunds_in_level_2(inputs)) is not None:
        return refused
    level = inputs.tree.lever.level2
    if level is None:
        return Outcome(verdict="inconclusive",
                       evidence={"reason": inputs.tree.lever.reasons.get("level2", "")},
                       rule="requires net units > 0 in both periods and a change in AOV")
    factor = next(f for f in level.factors if f.name == "units_per_order")
    return Outcome(contribution=factor.contribution,
                   evidence={"units_per_order_prev": factor.value_prev,
                             "units_per_order_cur": factor.value_cur})


# --- product and returns --------------------------------------------------------

def _pvm(term: str):
    def evaluate(inputs: Step7Inputs, moved: Changes) -> Outcome:
        totals = product_totals(inputs.data)
        # "Sold in both periods" is L's membership in pvm.py: positive sold
        # units. Since 2E orders count sale rows only, so the orders index IS
        # that; a product seen only through a refund this month is present
        # (members.py) but not sold, and L without it may be empty (2E
        # mutation check).
        both = set(totals.orders_prev.index) & set(totals.orders_cur.index)
        if not both:
            return Outcome(verdict="inconclusive", evidence={"products_in_both_periods": 0},
                           rule="requires products sold in both periods (L)")
        value = getattr(inputs.tree.products, term)
        return Outcome(contribution=value, evidence={f"{term}_effect": value,
                                                     "products_in_both_periods": len(both)})
    return evaluate


def p3(inputs: Step7Inputs, moved: Changes) -> Outcome:
    returns = inputs.tree.returns
    delta = returns.returns_cur - returns.returns_prev
    return Outcome(contribution=-delta, evidence={"returns_prev": returns.returns_prev,
                                                  "returns_cur": returns.returns_cur})


# --- localization and lifecycle -------------------------------------------------

def r1(inputs: Step7Inputs, moved: Changes) -> Outcome:
    breadth = inputs.localization.breadth
    totals = product_totals(inputs.data)
    keys = set(totals.rev_prev.index) | set(totals.rev_cur.index)
    deltas = {key: float(totals.rev_cur.get(key, 0.0)) - float(totals.rev_prev.get(key, 0.0))
              for key in keys}
    top = max(sorted(deltas), key=lambda key: abs(deltas[key]), default=None)
    moving = (top is not None and deltas[top] != 0
              and not is_negligible(moved.net, moved.revenue_prev, moved.revenue_cur,
                                    moved.scale)
              and (deltas[top] > 0) == (moved.net > 0))
    evidence = {"classification": breadth.classification,
                "top_member_share": breadth.top_member_share,
                "top_member": totals.labels.get(top) if top is not None else None,
                "top_member_delta": deltas.get(top) if top is not None else None}
    verdict = "supported" if breadth.classification == "concentrated" and moving else "ruled_out"
    return Outcome(verdict=verdict, evidence=evidence,
                   rule="breadth concentrated and the top product moving with the total")


def r2(inputs: Step7Inputs, moved: Changes) -> Outcome:
    products = inputs.tree.products
    value = products.new_products + products.discontinued_products
    return Outcome(contribution=value,
                   evidence={"new_products": products.new_products,
                             "discontinued_products": products.discontinued_products})


def r3(inputs: Step7Inputs, moved: Changes) -> Outcome:
    found = detect_stockouts(inputs.data)
    return Outcome(contribution=sum(item.contribution for item in found),
                   evidence={"products": [vars(item) for item in found],
                             "wording": "consistent with a stockout, verify on the shelf"})


EVIDENCE = {
    "D1": d1, "D2": _directional_check("D2"), "D3": _directional_check("D3"),
    "T1": t1, "T2": t2, "T3": t3,
    "C1": bridge_difference("new", True),
    "C2": bridge_difference("lapsed", False),
    "C3": bridge_difference("resurrected", True),
    "C4": c4,
    "B1": b1, "B2": b2,
    "P1": _pvm("price"), "P2": _pvm("mix"), "P3": p3,
    "R1": r1, "R2": r2, "R3": r3,
}
