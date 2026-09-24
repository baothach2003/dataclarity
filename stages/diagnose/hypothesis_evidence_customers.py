"""Evidence for the customer family, C1-C4 (docs/AI_PIPELINE.md 7.8), split
out of `hypothesis_evidence.py` in 3E1 for file size. Also home to the
no-customer-column refusal, which B1 shares.
"""

from stages.diagnose.numbers import is_negligible
from stages.diagnose.step7_inputs import Changes, Outcome, Step7Inputs
from stages.diagnose.thresholds import C4_RULE_OUT_POINTS, C4_SUPPORT_POINTS

# Off in v1 (Thach, 3E1). Stage 2's segment counts are a snapshot anchored at
# the file's END, over every row including the partial month after the
# current one - not the two diagnosed months - so rows after the period
# decided C4: the same January came out ruled_out or "migrated to weaker
# segments", supported, depending on who bought on 2-10 February (3E1
# doubt-review cycle 3). Switched on when stage 2 anchors a snapshot at the
# end of each compared month (Backlog), like T3 with `is_verdict`.
SEGMENTS_ANCHORED_TO_THE_PERIOD = False

WEAK = ("At-risk", "Hibernating")
STRONG = ("Champions", "Loyal")
# Stage 2's R x F grid (metrics_customers.assign_segment). "Returns only"
# (2E-b, never-buyers) is left out: most files have none, so requiring it
# would refuse C4 everywhere - its place is decided when C4 is switched on.
ALL_SEGMENTS = frozenset({"Champions", "Loyal", "At-risk", "Hibernating", "New",
                          "Needs Attention"})


def no_customer(inputs: Step7Inputs) -> bool:
    return inputs.data.parsed.reverse.get("customer") is None


NOT_TESTABLE_NO_CUSTOMER = Outcome(
    verdict="not_testable", evidence={"reason": "no column is mapped to customer"},
    rule="requires a customer column")


def bridge_difference(term: str, censored_matters: bool):
    def evaluate(inputs: Step7Inputs, moved: Changes) -> Outcome:
        if no_customer(inputs):
            return NOT_TESTABLE_NO_CUSTOMER
        lens = inputs.tree.customers
        if lens.previous_transition is None:
            return Outcome(verdict="inconclusive", evidence=dict(lens.evidence),
                           rule="requires the previous transition")
        if censored_matters and lens.evidence.get("left_censored"):
            return Outcome(verdict="inconclusive", evidence=dict(lens.evidence),
                           rule="left-censored: near the file start everyone looks new")
        now, before = getattr(lens, term), getattr(lens.previous_transition, term)
        return Outcome(contribution=now - before,
                       evidence={f"{term}_current": now, f"{term}_previous": before})
    return evaluate


def c4(inputs: Step7Inputs, moved: Changes) -> Outcome:
    if no_customer(inputs):
        return NOT_TESTABLE_NO_CUSTOMER
    if not SEGMENTS_ANCHORED_TO_THE_PERIOD:
        return Outcome(verdict="inconclusive", evidence={},
                       rule="stage 2's segment counts are a snapshot at the file's end, "
                            "not at the end of each compared month (off in v1)")
    segments = inputs.data.metrics.customers.segments
    missing = sorted(ALL_SEGMENTS - {s.segment for s in segments})
    if missing:
        # Stage 2 lists only segments present NOW, so a segment that emptied
        # vanishes from both totals and the previous shares are wrong: a
        # 15-point FAVOURABLE move came out supported at 17.5 unfavourable
        # (3E1 doubt-review #7). Refused until stage 2 lists every segment.
        return Outcome(verdict="inconclusive", evidence={"segments_missing": missing},
                       rule="requires every stage 2 segment in metrics.json; a missing "
                            "one may have emptied, and its previous count is lost")
    total_cur = sum(s.customers for s in segments)
    total_prev = sum(s.customers_previous for s in segments)
    if not total_cur or not total_prev:
        return Outcome(verdict="inconclusive", evidence={"segments": len(segments)},
                       rule="requires segment counts in both periods")

    def share(names, attribute, total):
        return 100.0 * sum(getattr(s, attribute) for s in segments if s.segment in names) / total

    weak = share(WEAK, "customers", total_cur) - share(WEAK, "customers_previous", total_prev)
    strong = share(STRONG, "customers", total_cur) - share(STRONG, "customers_previous", total_prev)
    unfavourable = weak - strong
    evidence = {"weak_share_change_points": round(weak, 4),
                "strong_share_change_points": round(strong, 4),
                "unfavourable_points": round(unfavourable, 4)}
    rule = (f"supported if the movement is WITH revenue (weaker in a fall, stronger in "
            f"a rise) by >= {C4_SUPPORT_POINTS} points, partial from {C4_RULE_OUT_POINTS}")
    # Direction-neutral (Thach, 3E1): towards weaker segments explains a fall,
    # towards stronger ones a rise; the statement is rendered from the side.
    if is_negligible(moved.net, moved.revenue_prev, moved.revenue_cur, moved.scale):
        with_revenue = 0.0
    else:
        with_revenue = unfavourable if moved.net < 0 else -unfavourable
    if with_revenue >= C4_SUPPORT_POINTS:
        verdict = "supported"
    elif with_revenue >= C4_RULE_OUT_POINTS:
        verdict = "partial"
    else:
        verdict = "ruled_out"
    return Outcome(verdict=verdict, evidence=evidence, rule=rule,
                   sign=-unfavourable if unfavourable else None)
