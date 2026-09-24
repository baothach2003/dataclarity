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


def _fit(hypothesis: Hypothesis) -> float:
    """How well a supported hypothesis explains the change, in [0, 1], for
    ranking (Thach, 3E1). A term: min(|share|, 1). An expectation: the closer
    to the change the better, so min(|share|, 2 - |share|) - ranking by the
    largest |share| picked the WORST overshoot (T2 at 1.75 over T1 at 1.00).
    A directional hypothesis has no share and ranks after all of them."""
    if hypothesis.share is None:
        return -1.0
    size = abs(hypothesis.share)
    if BY_ID[hypothesis.id].kind == "expectation":
        return min(size, 2 - size)
    return min(size, 1.0)


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
        return Headline(
            rule=4, hypothesis_id=None, lens=None,
            message=f"{change} Underneath that, orders contributed {pair['orders']:+,.2f} and "
                    f"average order value {pair['aov']:+,.2f}: large movements that "
                    "largely cancelled out. This may be seasonal.")

    # 5. Calendar or seasonality explains most of it.
    context = [by_id[i] for i in ("T1", "T2") if by_id[i].verdict == "supported"
               and abs(by_id[i].share) >= HEADLINE_CONTEXT_MIN_SHARE]
    if context:
        best = max(context, key=lambda h: (_fit(h), -ORDER[h.id]))
        what = "the calendar (the mix of weekdays in each month)" if best.id == "T1" \
            else "seasonality (the same months a year earlier moved the same way)"
        return Headline(rule=5, hypothesis_id=None, lens=None,
                        message=f"{change} The change is consistent with {what}: "
                                f"{_size(best, moved)}.")

    # 6. The largest supported explanation. Directional hypotheses carry no
    # share and rank after every share hypothesis, in catalog order.
    supported = [h for h in hypotheses if h.verdict == "supported"
                 and h.id not in NOT_A_HEADLINE and _moves_with_the_change(h, moved)]
    if supported:
        best = max(supported, key=lambda h: (_fit(h), -ORDER[h.id]))
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
