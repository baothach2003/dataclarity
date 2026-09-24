"""Evidence for B2, basket size, and its interim refusal on refund lines
(docs/AI_PIPELINE.md 7.8), split out of `hypothesis_evidence.py` in 2E-c for
file size. B1 stays there: it shares D1's check with the time family.
"""

from stages.diagnose.step7_inputs import Changes, Outcome, Step7Inputs


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
    # quantity +1 at a negative price read as a one-unit order, and B2 said
    # "baskets got smaller" while every real basket was 3 units (2E
    # doubt-review cycle 4; Thach, 2E-b). Since 2E-c such a line is a
    # deduction: not an order and not a unit, so it no longer distorts the
    # basket - its money lands in price per unit. The clause stays by Thach's
    # decision (2E-c D6) until he rules on lifting it: with one coupon, B2 went
    # inconclusive on a basket that fell 3 -> 2 units (2E-c review cycle 2).
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
                            "size cannot be separated from return lines until level 2 has a "
                            "refund factor of its own; deduction lines with a negative "
                            "amount (a refund booked at a negative price, a discount, a "
                            "coupon, a write-off) are refused with them for now (interim)")
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
