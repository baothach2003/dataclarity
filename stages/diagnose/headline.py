"""Step 7's headline, written by code (docs/AI_PIPELINE.md 7.8): the report
must state its conclusion when the AI is unavailable, so this sentence is
never the AI's. First matching rule wins.

Every number in a message comes from the blocks it is chosen from; nothing is
estimated here.
"""

from contracts.diagnosis import Headline, Hypothesis, Tree, Trust
from stages.diagnose.catalog import BY_ID, CATALOG
from stages.diagnose.step7_inputs import Changes
from stages.diagnose.numbers import is_negligible
from stages.diagnose.thresholds import HEADLINE_CONTEXT_MIN_SHARE

ORDER = {spec.id: index for index, spec in enumerate(CATALOG)}
# Their finding IS the trust caution, shown beside every headline; 7.8 says
# caution never changes the headline, so rule 6 does not name them (3E1).
NOT_A_HEADLINE = ("D2", "D3")


def _size(hypothesis: Hypothesis, moved: Changes) -> str:
    """A share as a reader can take it: a percentage up to 100%, otherwise the
    two figures - "1000% of the change" reads as a finding when it is the
    sign that the estimate overshot (3E1 doubt-review). The product lens
    decomposes GROSS sales, so its share says so and shows that total: the
    headline opens with the NET change, and "86% of the change" beside it
    was a share of a different number (3E1 doubt-review cycle 2, H3)."""
    if hypothesis.lens == "product":
        what = f"the change in gross sales ({moved.gross:+,.2f})"
        total = moved.gross
    else:
        what, total = "the change", moved.net
    if abs(hypothesis.share) <= 1:
        return f"{abs(hypothesis.share):.0%} of {what}"
    return f"{hypothesis.contribution:+,.2f} against {what.split(' (')[0]} of {total:+,.2f}"


def _moves_with_the_change(hypothesis: Hypothesis, moved: Changes) -> bool:
    """The headline states the NET change, so it may only name a cause that
    moved the same way. A product-lens share is of GROSS sales: a price rise
    lifting gross sales while refunds sank revenue was named "the best
    explanation" of the fall (3E1 doubt-review cycle 3). A directional
    hypothesis carries no number and already tests its own direction."""
    if hypothesis.contribution is None:
        return True
    # A change of zero has no best explanation in either direction: the sign
    # test alone admitted every negative cause when net was exactly 0 (cycle 4).
    if is_negligible(moved.net, moved.revenue_prev, moved.revenue_cur, moved.scale):
        return False
    return (hypothesis.contribution > 0) == (moved.net > 0)


def _lens_holds_the_change(hypothesis: Hypothesis, moved: Changes) -> bool:
    """A product-lens cause is named only when MORE than half of the change
    sits in the products (Thach's "more than half", 2E-l): one unit's mix
    shift was 100% of a -5 gross change and headlined a -780 month the
    discounts carried (2E-l review cycle 1). Measured as breadth and R1
    measure it - the products' net change over the total net change (Thach,
    2E-m: one definition; 2E-l's gross over net read 62% where breadth read
    7%). Its verdict is not touched: it does explain the gross change."""
    return hypothesis.lens != "product" or moved.products_hold_the_change


def _fit(hypothesis: Hypothesis, moved: Changes) -> float:
    """How well a supported hypothesis explains the change, in [0, 1], for
    ranking. Measured against the NET change the headline states, for every
    lens (Thach, 2E-m, superseding 3E1's per-lens share): a product-lens
    share is of the GROSS change, and P1's "100%" of gross -62 beat P4's 93%
    of net -100 only because its denominator was smaller. The verdicts keep
    their own lens totals. A term: min(size, 1). An expectation: the closer
    to the change the better, so min(size, 2 - size) - ranking by the largest
    size picked the WORST overshoot (T2 at 1.75 over T1 at 1.00; 3E1) -
    floored at 0: R3 is judged against GROSS, so a supported R3 can be three
    times the net change, and min(size, 2 - size) fell below a directional
    cause's -1 (2E-m review cycle 1). A directional hypothesis has no number
    and ranks after all of them."""
    if hypothesis.contribution is None:
        return -1.0
    size = abs(hypothesis.contribution / moved.net)
    if BY_ID[hypothesis.id].kind == "expectation":
        return max(min(size, 2 - size), 0.0)
    return min(size, 1.0)


def _best(candidates: list[Hypothesis], moved: Changes) -> Hypothesis:
    """The best fit; a tie goes to catalog order (3E1) - except among TERMS
    that are all past the net change (capped), where the larger share of it
    decides (Thach, 2E-m: rank every cause by its share of the net change).
    Catalog order named the smaller of two: P1 -23.8k over P2 -26.8k on a
    -9.8k change (Online Retail II 2011-07, unanswered). A tie with an
    expectation still goes to catalog order: an overshooting term does not
    beat an exact explanation (3E1)."""
    top = max(_fit(h, moved) for h in candidates)
    tied = [h for h in candidates if _fit(h, moved) == top]
    if len(tied) > 1 and all(BY_ID[h.id].kind == "term" and _past_the_change(h, moved) for h in tied):
        return max(tied, key=lambda h: (abs(h.contribution / moved.net), -ORDER[h.id]))
    return min(tied, key=lambda h: ORDER[h.id])


def _past_the_change(hypothesis: Hypothesis, moved: Changes) -> bool:
    """A term that alone moved more than the net change: other terms offset
    it. One that explains the change exactly is not past it, and keeps its
    catalog-order tie with the overshooting ones (2E-m review cycle 1) -
    exactly above residue: -200.20 is past 800.1 - 1000.3 =
    -200.19999999999993 by a float's last bit (review cycle 2)."""
    excess = abs(hypothesis.contribution) - abs(moved.net)
    return excess > 0 and not is_negligible(excess, moved.revenue_prev, moved.revenue_cur, moved.scale)


def choose_headline(trust: Trust, hypotheses: list[Hypothesis], tree: Tree | None,
                    moved: Changes) -> Headline:
    by_id = {h.id: h for h in hypotheses}
    change = (f"Revenue went from {moved.revenue_prev:,.2f} to {moved.revenue_cur:,.2f} "
              f"({moved.net:+,.2f}).")

    # 1. The data cannot be trusted.
    if trust.verdict == "blocked":
        blocked = next(check for check in trust.checks if check.status == "blocked")
        return Headline(rule=1, hypothesis_id=None, lens=None,
                        message=f"The data cannot be diagnosed: {blocked.message}")

    # 2. Missing days explain most of it.
    d1 = by_id["D1"]
    if d1.verdict == "supported" and abs(d1.share) >= HEADLINE_CONTEXT_MIN_SHARE:
        # The netted effect the verdict came from, not one month's gap: the
        # first version printed "a gap of 0.00" when the gap was last month's
        # (3E1 doubt-review cycle 2, F2).
        # A day with no sales is missing data OR a closure - the engine cannot
        # tell which (cycle 3) - and a gap larger than the change is not
        # "part" of it: printed against the change, as in every rule.
        size = (f"which account for an estimated {d1.contribution:+,.2f} of it"
                if abs(d1.share) <= 1 else
                f"an estimated {d1.contribution:+,.2f} against the change of {moved.net:+,.2f}")
        return Headline(rule=2, hypothesis_id=None, lens=None,
                        message=f"{change} The change is consistent with days that have no "
                                "sales at all - missing data, or days the shop was closed - "
                                f"{size}.")

    alert = bool(tree and tree.lever.masked_shift_alert)

    # 3. Routine variation. DORMANT in v1 (ADR-0007): T3 cannot be supported.
    if by_id["T3"].verdict == "supported" and not alert:
        return Headline(rule=3, hypothesis_id=None, lens=None,
                        message=f"{change} The change is within normal variation.")

    # 4. A flat total hiding offsetting movements - ALWAYS hedged, and stating
    # the real net change beside the pair, so "stable" is never read as zero.
    if alert:
        pair = {f.name: f.contribution for f in tree.lever.masked_shift_pair.factors}
        # Named by what was counted (2E-e): lines, unless order_id was mapped.
        unit, average = (("orders", "average order value") if moved.orders_basis == "order_id"
                         else ("lines", "average line value"))
        return Headline(
            rule=4, hypothesis_id=None, lens=None,
            message=f"{change} Underneath that, {unit} contributed {pair['orders']:+,.2f} and "
                    f"{average} {pair['aov']:+,.2f}: large movements that "
                    "largely cancelled out. This may be seasonal.")

    # 5. Calendar or seasonality explains most of it.
    context = [by_id[i] for i in ("T1", "T2") if by_id[i].verdict == "supported"
               and abs(by_id[i].share) >= HEADLINE_CONTEXT_MIN_SHARE]
    if context:
        best = _best(context, moved)
        what = "the calendar (the mix of weekdays in each month)" if best.id == "T1" \
            else "seasonality (the same months a year earlier moved the same way)"
        return Headline(rule=5, hypothesis_id=None, lens=None,
                        message=f"{change} The change is consistent with {what}: "
                                f"{_size(best, moved)}.")

    # 6. The best-supported explanation, ranked by share of the net change. Directional hypotheses carry no
    # share and rank after every share hypothesis, in catalog order.
    supported = [h for h in hypotheses if h.verdict == "supported"
                 and h.id not in NOT_A_HEADLINE and _moves_with_the_change(h, moved)
                 and _lens_holds_the_change(h, moved)]
    if supported:
        best = _best(supported, moved)
        size = f", {_size(best, moved)}" if best.share is not None else ""
        return Headline(rule=6, hypothesis_id=best.id, lens=best.lens,
                        message=f"{change} The best-supported explanation: "
                                f"{best.statement[0].lower() + best.statement[1:]} "
                                f"({best.lens} lens{size}).")

    # 7. Nothing supported - the engine does not invent a cause.
    partial = [h for h in hypotheses if h.verdict == "partial"]
    tail = ("" if not partial else " Partly consistent: "
            + "; ".join(f"{h.statement[0].lower() + h.statement[1:]} ({h.id})"
                        for h in partial) + ".")
    return Headline(rule=7, hypothesis_id=None, lens=None,
                    message=f"{change} No single tested cause explains most of the change.{tail}")
