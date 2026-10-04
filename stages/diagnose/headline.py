"""Step 7's headline, written by code (docs/AI_PIPELINE.md 7.8): the report
must state its conclusion when the AI is unavailable, so this sentence is
never the AI's. First matching rule wins - except that rules 5 and 6 rank
their causes together under one fit (Thach, 2E-o Q1), and a supported
directional cause comes before the movements (Q4).

Every number in a message comes from the blocks it is chosen from; nothing is
estimated here.
"""

from contracts.diagnosis import Headline, HeadlineMovement, Hypothesis, Tree, Trust
from stages.diagnose.catalog import BY_ID
from stages.diagnose.step7_inputs import Changes
from stages.diagnose.numbers import is_negligible
from stages.diagnose.season_headline import beyond, consistent
from stages.diagnose.thresholds import HEADLINE_CONTEXT_MIN_SHARE

# Their finding IS the trust caution, shown beside every headline; 7.8 says
# caution never changes the headline, so rule 6 does not name them (3E1).
NOT_A_HEADLINE = ("D2", "D3")
CONTEXT = {"T1": "the calendar (the mix of weekdays in each month)",
           "T2": "seasonality (the same months a year earlier moved the same way)"}
# T2 with no season claimed: the bare fact - only 4A's claim may say "season"
# (Thach, 2026-10-04, 8D b).
FACT_CONTEXT = {"T2": "the same months a year earlier, which moved the same way"}


def _context(hypothesis_id: str, moved: Changes) -> str:
    if not moved.season_claimed and hypothesis_id in FACT_CONTEXT:
        return FACT_CONTEXT[hypothesis_id]
    return CONTEXT[hypothesis_id]


def _residue(amount: float, moved: Changes) -> bool:
    """Float residue next to the two months and the money moved - the scale
    every "nothing" in stage 3 is judged against (2E doubt-review cycle 3)."""
    return is_negligible(amount, moved.revenue_prev, moved.revenue_cur, moved.scale)


def _size(hypothesis: Hypothesis, moved: Changes) -> str:
    """The share of the NET change - the change the headline states - for
    every lens, and a percentage only up to 100% (Thach, 2E-n Q4): "1000% of
    the change" reads as a finding when it is the sign of an overshoot (3E1),
    so past the change the two figures are printed instead. A product-lens
    cause printed its share of GROSS sales beside a net change it was ranked
    against (2E-m); its verdict's own share stays in the evidence."""
    past = abs(hypothesis.contribution) - abs(moved.net)
    if past <= 0 or _residue(past, moved):
        return f"{min(abs(hypothesis.contribution / moved.net), 1.0):.0%} of the change"
    return f"{hypothesis.contribution:+,.2f} against the change of {moved.net:+,.2f}"


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
    if _residue(moved.net, moved):
        return False
    return (hypothesis.contribution > 0) == (moved.net > 0)


def _lens_holds_the_change(hypothesis: Hypothesis, moved: Changes) -> bool:
    """A product-lens cause is named only when MORE than half of the change
    sits in the products (Thach's "more than half", 2E-l), read from
    breadth's decision - the change in the products' SALE lines over the net
    change, customer returns being their own class (Thach, 2E-m: one
    definition; 2E-n: reading G). A product-lens term can land near the net
    change by an offset inside gross sales: sales -195 and refunds -200 of a
    -395 month, the mix -420 (1.06x) against the price - the refunds carried
    half the month, so returns (51%) are named, not the mix. Its verdict is
    not touched: it does explain the gross change."""
    return hypothesis.lens != "product" or moved.products_hold_the_change


def _distance(hypothesis: Hypothesis, moved: Changes) -> float:
    """How far a cause's contribution lands from the net change, in money.

    ONE fit for every cause (Thach, 2E-n, superseding 3E1's cap on terms and
    2E-m's D1): fit = max(0, 1 - |1 - share of the net change|) = max(0, 1 -
    distance / |net|). For one net change the order of fit is the order of
    this distance, closest first - so a cause at 1.14x of the change beats
    one at 7.8x, which the cap scored alike. Compared as money so that
    "positive" and "tied" are judged above float residue: 0.9x and 1.1x of
    the change are one tie, while 1 - |1 - 0.9| and 1 - |1 - 1.1| differ in
    binary."""
    return abs(moved.net - hypothesis.contribution)


def _fits(hypothesis: Hypothesis, moved: Changes) -> bool:
    """A positive fit: closer to the change than |net|, i.e. a share of it
    strictly between 0 and 2, above residue. Twice the change fits as badly
    as none of it."""
    room = abs(moved.net) - _distance(hypothesis, moved)
    return room > 0 and not _residue(room, moved)


def _closest(candidates: list[Hypothesis], moved: Changes) -> list[Hypothesis]:
    """The share causes with a positive fit that come closest to the change.
    An exact tie keeps every tied cause - the headline names them all, never
    one by catalog order (Thach, 2E-n); `candidates` come in catalog order,
    which is only the order they are listed in."""
    fitting = [h for h in candidates if _fits(h, moved)]
    if not fitting:
        return []
    best = min(_distance(h, moved) for h in fitting)
    return [h for h in fitting if _residue(_distance(h, moved) - best, moved)]


def _statement(hypothesis: Hypothesis) -> str:
    return hypothesis.statement[0].lower() + hypothesis.statement[1:]


def _explanation(named: list[Hypothesis], moved: Changes, change: str) -> Headline:
    """Rule 6 naming its best-fitting causes - one, or every cause of an
    exact tie, with no single `hypothesis_id` then (as rule 5 names T1/T2)."""
    def one(h: Hypothesis) -> str:
        size = f", {_size(h, moved)}" if h.contribution is not None else ""
        return f"{_statement(h)} ({h.lens} lens{size})"
    if len(named) == 1:
        best = named[0]
        return Headline(rule=6, hypothesis_id=best.id, lens=best.lens,
                        message=f"{change} The best-supported explanation: {one(best)}.")
    return Headline(rule=6, hypothesis_id=None, lens=None,
                    message=f"{change} Equally well supported: " + "; ".join(one(h) for h in named) + ".")


def _largest(causes: list[Hypothesis], moved: Changes) -> list[Hypothesis]:
    """The largest movement - every one of an exact tie."""
    top = max(abs(h.contribution) for h in causes)
    return [h for h in causes if _residue(abs(h.contribution) - top, moved)]


def _measured(hypothesis: Hypothesis) -> bool:
    """A movement that was MEASURED, whatever its verdict: a term - a part of
    one of the tree's decompositions, ruled out against the change only for
    its direction. What the catalog calls an expectation counts only when
    supported: D1, T1, T2 and R3 estimate what a cause WOULD have done; C2 is
    a difference between two transitions, no part of this month's change
    (2E-n review cycle 3: C2 at +400 read "lapsed customers took less revenue
    away" while this month's lapsed term pulled revenue down); C1 and C3 are
    parts of the change under the customer split, but the catalog judges
    them as expectations too (2E-o Q5 #5 corrected the premise)."""
    return BY_ID[hypothesis.id].kind == "term" or hypothesis.verdict == "supported"


def _opposing(hypotheses: list[Hypothesis], moved: Changes) -> str:
    """No cause rule 6 may name fits the change (Thach, 2E-n) - each lands
    at least |net| from it - so the change is what remains of movements that
    offset each other. One movement each way is named, in money - a
    percentage over 100 reads as a finding (3E1): the largest measured one
    (`_measured`), every one of an exact tie. The sentence says only its
    direction and money: the tree's parts are not all hypotheses (volume, the
    level-1 customers), so "the largest down" was false beside a larger part
    no hypothesis names (review cycle 3); for the same reason a way nothing
    tested moved is left unnamed rather than claimed. The product-lens gate
    guards naming an EXPLANATION and does not apply here: it is closed
    whenever the products' sales carry at most half of the change - also
    when they moved against it, and then "no tested cause moved revenue up"
    stood beside a supported price rise (review cycle 1). Lenses are never
    added together: each figure carries its own lens. D2 and D3 are
    directional - no number - so no NOT_A_HEADLINE test is needed here
    (mutation check: equivalent)."""
    pool = [h for h in hypotheses if h.contribution is not None and _measured(h)
            and not _residue(h.contribution, moved)]
    rise = moved.net > 0
    ways = [("up" if rise else "down", [h for h in pool if (h.contribution > 0) == rise]),
            ("down" if rise else "up", [h for h in pool if (h.contribution > 0) != rise])]
    named = ["{}, {}".format(way, " and ".join(f"{_statement(h)} ({h.lens} lens, {h.contribution:+,.2f})"
                                               for h in _largest(causes, moved)))
             for way, causes in ways if causes]
    # No claim that no cause fits: a ruled-out cause can (Online Retail II
    # 2011-07 unanswered: T1 at 1.84x fits 0.16; review cycle 1), and so can
    # one the product-lens gate held back (cycle 2). "Among them": the two
    # named are not the whole change - on Online Retail II 2011-07 they added
    # to +5,763.46 beside a -9,823.01 change (2E-o Q5 #1).
    return ("The change is what remains of movements in opposite directions, among them: "
            + "; ".join(named) + ".")


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

    # The size test (3E1b; Thach, 3E2-F1): rules 5 and 6 single a cause out
    # only beyond twice the shop's median month-to-month movement - inside it
    # any decomposition of noise has a term holding a fifth of the change, and
    # every month with nothing planted named a cause (30 of 30 seeds). The
    # verdicts and the table are untouched. Too short a history names no
    # cause (Thach, 2026-10-03); no percentage: rules 5-7 stand and say so -
    # the data cannot tell (CLAUDE.md 3.3a's shape).
    gate = moved.movement
    season = gate.season if gate is not None else None
    found, named = _ranked(hypotheses, by_id, moved, change)
    head = _size_tested(found, gate, change)
    # A season 4A's rule claims (Thach, 2026-10-03, decision 1; its bands
    # 2026-10-04): this month's change against the same month's in the
    # earlier years - a stated fact, no index estimated. Consistent: the
    # headline says so and names no other cause. Inconclusive: the size test
    # above decides, exactly as without a season (lifting it named a cause
    # not planted in 29 of 30 S13 seeds). A shortfall or excess: stated as a
    # fact where the size test names no cause; where it names one, the cause
    # stands and the gap is stated after it - the change from last month may
    # BE the gap (a flat season), and the engine cannot tell that from a
    # season masking the cause (CLAUDE.md 3.3a; method amendment 2, B8).
    # (`_ranked` returns rules 5-7 only, so every rule here is one of them.)
    if season is None or season.band == "inconclusive":
        return head
    if season.band == "consistent":
        return Headline(rule=7, hypothesis_id=None, lens=None, movement=gate,
                        message=f"{change} {consistent(season, gate.factor)}")
    # T2 IS the season's prediction (the same months a year earlier), so a
    # headline naming it cannot stand beside a gap FROM the season (review 2,
    # #1: "consistent with seasonality ... far below the same month"); ranking
    # without it promoted a weaker cause to "best-supported" (review 3, #1).
    # The ranking stays 6e9b224's, and the gap is stated instead.
    if head.rule == 7 or "T2" in named:
        return Headline(rule=7, hypothesis_id=None, lens=None, movement=gate,
                        message=f"{change} {beyond(season, stated=True)}")
    return head.model_copy(update={"message": f"{head.message} {beyond(season, stated=False)}"})


def _size_tested(found: Headline, gate: HeadlineMovement | None, change: str) -> Headline:
    """Rules 5-7 through the size test, as before any season (HEAD 6e9b224)."""
    # Only a cause singled out is gated: a rule 7 keeps its own sentence and
    # its "partly consistent" list (3E1b review 1, F6).
    if gate is not None and gate.singled_out is False and found.rule in (5, 6):
        times = "twice" if gate.factor == 2 else f"{gate.factor:g} times"
        places = _places(gate.change_pct, gate.typical_pct, gate.factor)
        return Headline(rule=7, hypothesis_id=None, lens=None, movement=gate,
                        message=f"{change} This month's change ({gate.change_pct:+.{places}f}%) is within "
                                f"this shop's usual month-to-month range: under {times} its median "
                                f"movement of about {gate.typical_pct:.{places}f}% over the "
                                f"{gate.movements} month-to-month changes before it. No single cause "
                                "is singled out.")
    if gate is not None and gate.singled_out is None and gate.change_pct is not None and found.rule in (5, 6):
        # Too short to size names NO cause (Thach, 2026-10-03, decision 5): the
        # engine cannot tell a cause from noise, and naming one with "the
        # size cannot be said" is still a guess - S11 plants nothing and named
        # one in 30 of 30 seeds.
        return Headline(rule=7, hypothesis_id=None, lens=None, movement=gate,
                        message=f"{change} The history is too short to tell whether this change is larger "
                                f"than this shop's ordinary month-to-month movement ({gate.reason}); the table "
                                "shows what each hypothesis measured.")
    if gate is not None and gate.singled_out is None and found.rule in (5, 6):
        # A change with no percentage: the test cannot run for another reason
        # - the cause stands and says so (3E1b, outside decision 5).
        found = found.model_copy(update={"message": (
            f"{found.message} Whether this change is larger than this shop's usual month-to-month "
            f"movement cannot be said: {gate.reason}.")})
    return found.model_copy(update={"movement": gate})


WITHIN_NOTE = ("This month's change is within the shop's usual month-to-month movement, so the verdicts below "
               "describe a change too small to single out: each shows what its hypothesis measured, and none is "
               "named as the cause.")
SEASON_NOTE = ("This month's change is consistent with the season, so none of the verdicts below is named as the "
               "cause: each shows what its hypothesis measured.")
BEYOND_NOTE = ("The headline compares this month's change with the same calendar month's change in the year or "
               "years before; the verdicts below describe the change from last month, not that gap: each shows what "
               "its hypothesis measured, and none is named as the cause.")
TOO_SHORT_NOTE = ("The history is too short to tell whether this change is larger than ordinary movement, so the "
                  "verdicts below describe a change that cannot be singled out: each shows what its hypothesis "
                  "measured, and none is named as the cause.")


def hypotheses_note(headline: Headline) -> str | None:
    """The hypothesis table's one note when the size test kept every cause
    out of the headline (Thach, 2026-10-03, decision 4): the verdicts are not
    false - the components did move that much - but they describe a change
    too small, or a history too short, to single one out. Rules 1-4 judge
    something else and carry none."""
    gate = headline.movement
    if headline.rule != 7 or gate is None:
        return None
    if gate.season is not None and gate.season.band == "consistent":
        return SEASON_NOTE
    if gate.season is not None and gate.season.band in ("shortfall", "excess"):
        return BEYOND_NOTE
    if gate.singled_out is False:
        return WITHIN_NOTE
    if gate.singled_out is None and gate.change_pct is not None:
        return TOO_SHORT_NOTE
    return None


def _places(change_pct: float, typical_pct: float, factor: float) -> int:
    """Decimal places for the two percentages, one unless rounding would print
    a change that is not under `factor` x the typical movement - "+37.0% ...
    under twice about 18.5%" for 36.96 against 18.49 (3E1b review 2, N5)."""
    for places in range(1, 10):
        # ...and never prints a change that moved as "-0.0%" (review 3, R5).
        if round(abs(change_pct), places) < factor * round(typical_pct, places) and (
                change_pct == 0 or round(change_pct, places) != 0):
            return places
    return 10


def _ranked(hypotheses: list[Hypothesis], by_id: dict[str, Hypothesis], moved: Changes,
            change: str) -> tuple[Headline, frozenset[str]]:
    """Rules 5 to 7, as they stood before the size test, and the hypotheses
    the headline names (none for the offsetting movements or rule 7)."""
    # 5 and 6, ranked together under the one fit (Thach, 2E-o Q1): rule 5's
    # context causes - the calendar or seasonality, supported and at least
    # half of the change - and rule 6's share causes compete, and the
    # closest fit wins, whichever rule it belongs to. Ranked first, a context
    # cause won at 1.48x of the change beside B1 at 0.96x (Kaggle 2024-12).
    # Positive fit above residue: on a change of cents 0.2 of it can be
    # residue, and the sentence came out "consistent with ." (review cycle 1).
    context = [by_id[i] for i in ("T1", "T2") if by_id[i].verdict == "supported"
               and abs(by_id[i].share) >= HEADLINE_CONTEXT_MIN_SHARE]
    supported = [h for h in hypotheses if h.verdict == "supported"
                 and h.id not in NOT_A_HEADLINE and _moves_with_the_change(h, moved)
                 and _lens_holds_the_change(h, moved)]
    shares = [h for h in supported if h.contribution is not None]
    ranked = shares + [h for h in context if h.id not in {s.id for s in shares}]
    named = _closest(ranked, moved)
    # 5. Calendar or seasonality - when only they fit best (a T2 under half
    # of the change is rule 6's, as before).
    if named and all(h.id in {c.id for c in context} for h in named):
        if len(named) == 1:
            what = f"{_context(named[0].id, moved)}: {_size(named[0], moved)}"
        else:
            what = "; and equally with ".join(f"{_context(h.id, moved)}: {_size(h, moved)}" for h in named)
        return Headline(rule=5, hypothesis_id=None, lens=None,
                        message=f"{change} The change is consistent with {what}."), _ids(named)

    # 6. The best-fitting supported cause, closest to the net change (a tie
    # across the two rules named in rule 6's words); then a supported
    # directional cause, which carries no number (Thach, 2E-o Q4: a
    # directional R1 before the movements); the movements that offset each
    # other are the last resort.
    if named:
        return _explanation(named, moved, change), _ids(named)
    directional = [h for h in supported if h.contribution is None]
    if directional:
        return _explanation(directional, moved, change), _ids(directional)
    if shares:
        return Headline(rule=6, hypothesis_id=None, lens=None,
                        message=f"{change} {_opposing(hypotheses, moved)}"), frozenset()

    # 7. Nothing supported - the engine does not invent a cause.
    partial = [h for h in hypotheses if h.verdict == "partial"]
    tail = ("" if not partial else " Partly consistent: "
            + "; ".join(f"{_statement(h)} ({h.id})" for h in partial) + ".")
    return Headline(rule=7, hypothesis_id=None, lens=None,
                    message=f"{change} No single tested cause explains most of the change.{tail}"), frozenset()


def _ids(named: list[Hypothesis]) -> frozenset[str]:
    return frozenset(h.id for h in named)
