"""Evidence for B2, basket size, and its interim refusal on refund lines
(docs/AI_PIPELINE.md 7.8), split out of `hypothesis_evidence.py` in 2E-c for
file size. B1 stays there: it shares D1's check with the time family.
"""

from stages.diagnose.lever import refund_lines
from stages.diagnose.step7_inputs import Changes, Outcome, Step7Inputs


def _refunds_in_level_2(inputs: Step7Inputs) -> Outcome | None:
    """INTERIM for B2 only (Thach, 2E), until the three-factor level 2 (a
    session after 3E2, before 3F). Since 2E an order is a sale row, so refunds
    no longer move purchase frequency and B1 is evaluated on refund months.
    Level 2 still splits AOV into NET units per order x price per net unit, so
    a refunded unit leaves the basket: with this refusal lifted, a month where
    ONLY refunds changed headlined "baskets got smaller (100% of the change)"
    (measured in 2E). Either period with any refund leaves B2 inconclusive."""
    # Any return line, and any counted non-return line with a negative amount
    # (2E-b, 2E-c2 doubt-review cycles 2-3: the reasons beside
    # `lever.refund_lines`, where the count lives - the bridge withholds the
    # split on the same count, the report redesign's step 1).
    lines = refund_lines(inputs.data)
    if lines["prev"] or lines["cur"]:
        return Outcome(verdict="inconclusive",
                       # Line counts only: money beside them read as a
                       # contradiction when it was a different set of rows
                       # (2E-b review).
                       evidence={"refund_lines_prev": lines["prev"],
                                 "refund_lines_cur": lines["cur"]},
                       rule="level 2 counts refunded units against the basket, so basket "
                            "size cannot be separated from return lines, or from deduction "
                            "lines with a negative amount (a refund booked at a negative "
                            "price cannot be told from a coupon), until level 2 has a "
                            "refund factor of its own")
    return None


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
