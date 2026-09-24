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
    # Any return LINE, not only refunded money (2E doubt-review cycle 3).
    # Since 2E-c2 a return line needs a negative amount, so a zero-price
    # write-off is a deduction and carries no unit into the basket.
    period = inputs.data.metrics.period
    lines = {label: int((inputs.data.parsed.returned
                         & (inputs.data.months == month)).sum())
             for label, month in (("prev", period.previous), ("cur", period.current))}
    # ...and any counted row with a negative amount (2E-b). Thach decided in
    # 2E-c2 to drop this clause IF a test proved a deduction line cannot move
    # B2; the proof failed. A refund booked +1 at a negative price is a
    # deduction, so its units leave level 2 - while the same refund booked as
    # a return line counts against the basket: fifteen such refunds a day made
    # B2 headline "baskets got bigger" (+8,525 against +3,100) while each
    # order kept 2.5 units, down from 3 (2E-c2 doubt-review cycle 2). A coupon
    # and a refund at a negative price cannot be told apart, so both refuse B2
    # until 3E3 gives refunds a factor of their own - the SUPPRESS side. It
    # also covers a month netting zero or below, where price per unit and the
    # basket term's sign flip: only return lines or negative amounts can
    # take a month there, and both refuse B2 first (2E-c2 doubt-review F1).
    for label, month in (("prev", period.previous), ("cur", period.current)):
        lines[label] += int((inputs.data.parsed.counted
                             & (inputs.data.parsed.revenue_amounts < 0)
                             & ~inputs.data.parsed.returned
                             & (inputs.data.months == month)).sum())
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
