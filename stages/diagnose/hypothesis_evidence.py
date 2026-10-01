"""One evidence function per catalog id (docs/AI_PIPELINE.md 7.8).

Each returns an `Outcome`: a finished verdict when the hypothesis is
directional or a requirement is not met, otherwise the contribution the
shared share rule in `hypotheses.py` judges. None of them reads a step-4 row
as a judgement - since ADR-0007 no row is one.
"""

from stages.diagnose.members import product_totals
from stages.diagnose.numbers import is_negligible
from stages.diagnose.step7_inputs import Changes, Outcome, Step7Inputs
from stages.diagnose.stockout import detect_stockouts
# D1 and the time family live in their own module (file size, 2E-j).
from stages.diagnose.hypothesis_evidence_time import (
    check_of as _check,
    d1,
    month_grain_outcome,
    t1,
    t2,
    t3,
)
# The customer family lives in its own module (file size); c4 is re-exported.
from stages.diagnose.hypothesis_evidence_customers import (
    NOT_TESTABLE_NO_CUSTOMER,
    blank_customers,
    bridge_difference,
    c4,
    no_customer,
)
# B2 and its interim refusal live in their own module (file size, 2E-c).
from stages.diagnose.hypothesis_evidence_lever import b2

# --- data quality -------------------------------------------------------------

def _directional_check(check_id: str):
    def evaluate(inputs: Step7Inputs, moved: Changes) -> Outcome:
        check = _check(inputs, check_id)
        verdict = {"caution": "supported", "inconclusive": "inconclusive"}.get(
            check.status, "ruled_out")
        return Outcome(verdict=verdict, evidence={"check_status": check.status,
                                                  **check.evidence},
                       rule=f"supported when {check_id} cautions")
    return evaluate


# --- lever ----------------------------------------------------------------------

def b1(inputs: Step7Inputs, moved: Changes) -> Outcome:
    if no_customer(inputs):
        return NOT_TESTABLE_NO_CUSTOMER
    if blank := blank_customers(inputs, reads="compared"):
        return blank
    # An order is a row count, so a day with no sales removes whole orders and
    # reads as customers buying less often: two missing days under D1's
    # threshold headlined "customers bought less often (100%)" (3E1 doubt-
    # review cycle 3). Refused on ANY excess zero day, or when D1 could not
    # learn a pattern (Thach, 3E1). B2 is not refused: removing whole orders
    # leaves units per order unchanged - measured, 0 movement on 48 shops.
    check = _check(inputs, "D1")
    excess = (check.evidence.get("excess_zero_days_cur"),
              check.evidence.get("excess_zero_days_prev"))
    # A month-grain file has no day to miss: the refusal does not apply
    # (Thach, Q1 of 2E-h; 2E-j review cycle 1 #3).
    grain = bool(check.evidence.get("month_grain"))  # the check knows the file's grain
    if not grain and (None in excess or max(excess) > 0):
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


# --- product and returns --------------------------------------------------------

def _pvm(term: str):
    def evaluate(inputs: Step7Inputs, moved: Changes) -> Outcome:
        totals = product_totals(inputs.data)
        # "Sold in both periods" is L's membership in pvm.py: positive sold
        # units. Since 2E orders count sale rows only, so the orders index IS
        # that; a product seen only through a refund this month is present
        # (members.py) but not sold, and L without it may be empty (2E
        # mutation check).
        # Lines the user classed as not products are no product L holds
        # (pvm.py, 2E-d2 doubt-review F2): postage sold every month made a
        # catalogue with nothing in common look comparable. Nor is the gap -
        # no identity, or pooled items - since 2E-l review cycle 1: its own
        # term, `unidentified`.
        both = (set(totals.orders_prev.index) & set(totals.orders_cur.index)) - totals.gap_keys
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


def p4(inputs: Step7Inputs, moved: Changes) -> Outcome:
    """Deductions (discounts, coupons, write-offs; 2E-c) are positive
    magnitudes: more of them took revenue away (Thach, 2E-l)."""
    returns = inputs.tree.returns
    delta = returns.deductions_cur - returns.deductions_prev
    return Outcome(contribution=-delta, evidence={"deductions_prev": returns.deductions_prev,
                                                  "deductions_cur": returns.deductions_cur})


def p5(inputs: Step7Inputs, moved: Changes) -> Outcome:
    """The charges the customer paid (lines classed so in Review) are revenue
    but no order (Thach, 2E-l). With none classed its requirement is unmet:
    "charges did not move" was a finding the engine could not make - Online
    Retail II's unclassed postage moved +21,624 (review cycle 1)."""
    if not inputs.data.parsed.charge.any():
        return Outcome(verdict="not_testable",
                       evidence={"reason": "no line is classed as a charge in Review"},
                       rule="requires lines classed as charges")
    returns = inputs.tree.returns
    return Outcome(contribution=returns.charges_cur - returns.charges_prev,
                   evidence={"charges_prev": returns.charges_prev,
                             "charges_cur": returns.charges_cur})


# --- localization and lifecycle -------------------------------------------------

def r1(inputs: Step7Inputs, moved: Changes) -> Outcome:
    breadth = inputs.localization.breadth
    # Products only, as breadth measures them: the gap is never the top
    # product (Thach, after 2E-g review cycle 3). Each product's own (net)
    # change, as breadth's concentration: R1 asks where the NET change sits,
    # and read on sale lines an order cancelled the month before was named
    # the top product with a revenue of 0 in both months (2E-n review cycle 1).
    totals = product_totals(inputs.data)
    keys = (set(totals.rev_prev.index) | set(totals.rev_cur.index)) - totals.gap_keys
    deltas = {key: float(totals.rev_cur.get(key, 0.0)) - float(totals.rev_prev.get(key, 0.0))
              for key in keys}
    top = max(sorted(deltas), key=lambda key: abs(deltas[key]), default=None)
    moving = (top is not None and deltas[top] != 0
              and not is_negligible(moved.net, moved.revenue_prev, moved.revenue_cur,
                                    moved.scale)
              and (deltas[top] > 0) == (moved.net > 0))
    evidence = {"classification": breadth.classification,
                "top_member_share": breadth.top_member_share,
                "products_share_of_change": breadth.products_share_of_change,
                "top_member": totals.labels.get(top) if top is not None else None,
                "top_member_delta": deltas.get(top) if top is not None else None}
    # `concentrated` holds only when more than half of the change sits in the
    # products (Thach, 2E-l; localization.compute_breadth).
    verdict = "supported" if breadth.classification == "concentrated" and moving else "ruled_out"
    return Outcome(verdict=verdict, evidence=evidence,
                   rule="breadth concentrated - more than half of the change in the products' sales, the "
                        "concentration over each product's own change - and the top product moving with "
                        "the total")


def r2(inputs: Step7Inputs, moved: Changes) -> Outcome:
    products = inputs.tree.products
    value = products.new_products + products.discontinued_products
    return Outcome(contribution=value,
                   evidence={"new_products": products.new_products,
                             "discontinued_products": products.discontinued_products})


def r3(inputs: Step7Inputs, moved: Changes) -> Outcome:
    if inputs.data.metrics.period.month_grain:
        return month_grain_outcome("a run of days without a sale")
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
    "P1": _pvm("price"), "P2": _pvm("mix"), "P3": p3, "P4": p4, "P5": p5,
    "R1": r1, "R2": r2, "R3": r3,
}
