"""Stage 4 Predict - the suggested actions (the report redesign, step 4 as
Thach's option (d); docs/REPORT_REDESIGN.md 4.1-4.3; Thach Q10, Q11, Q52,
Q54). No AI writes them in v1: code selects the claims and writes every
sentence - the fact, the action and why (catalog.py), the watch line.

Only when the headline names a cause (rules 5 and 6), the diagnosis is not
blocked and the previous month is complete. From the checks moving with the
change (supported or partial) and those pulled the other way at the
supported bar or above - never a data check (a data problem is fixed, not
acted on in the shop), a time check (the calendar is no lever), C4
(dormant) or R2 (Q52: no watch line next month can follow it). Ranked: the
headline's causes first, then by amount; a claim with no catalog entry for
the way its own figure moved is dropped; at most three. A claim's fact is
the checklist's own sentence (shared/claim_lines: one copy); its direction
reads the order of the two figures it rests on, never a new figure."""

from dataclasses import dataclass

from contracts.diagnosis import DiagnosisContract, Hypothesis
from contracts.forecast_actions import CLAIM_IDS, MAX_ACTIONS, ai_text_problems, front_word_problems
from contracts.metrics import MetricsContract
from shared.claim_lines import Context, money_terms, moved_line
from shared.share_bars import SUPPORTED_MIN_SHARE
from shared.wording import amount
from stages.predict.catalog import ACTIONS, Direction

# Never a claim: the data checks, the time checks, C4 (dormant in v1:
# ADR-0007) and R2 (Thach, Q52) - and B1, B2 and P4, moved out by step 4's
# scoped review under Thach's stop rule (2026-10-06): no code-written action
# and why was found for them that reads true in every case they reach (B1
# and B2 are ratios over all customers and lines; P4's lines are deductions
# the file cannot always name - CLAUDE.md 3.3a).
MOVED_OUT = frozenset({"B1", "B2", "P4"})
NOT_A_LEVER = frozenset({"D1", "D2", "D3", "T1", "T2", "T3", "C4", "R2"}) | MOVED_OUT
_NAMED_RULES = (5, 6)
_WATCH = "Next month, check: {what}."
_PAIR = "{what} ({now} this month; {was} the month before)"
BLOCKED = "no suggested action: the diagnosis is blocked - the data cannot be diagnosed (its trust checks say why)"
NOT_COMPARABLE = "no suggested action: the previous month is not complete, so the months cannot be compared"


@dataclass(frozen=True)
class Claim:
    id: str  # K1, K2, K3 in rank order
    hypothesis_id: str
    fact: str  # the checklist's own sentence
    direction: Direction  # the way the claim's own figure moved
    subject: str  # the check's plain name
    watch: str
    action: str  # the catalog's, by kind and direction
    why: str


def not_asked(metrics: MetricsContract, diagnosis: DiagnosisContract) -> str | None:
    """Why no claim can be selected on this run at all, or None."""
    if diagnosis.trust.verdict == "blocked":
        return BLOCKED
    if not metrics.period.previous_complete:
        return NOT_COMPARABLE
    return None


def candidates(metrics: MetricsContract, diagnosis: DiagnosisContract) -> list[Hypothesis]:
    """The checks a claim may rest on, before the catalog is read (design
    4.1): none unless a cause is named on a diagnosable, comparable run."""
    if (diagnosis.headline.rule not in _NAMED_RULES or not_asked(metrics, diagnosis) is not None
            or diagnosis.tree is None):
        return []
    return [h for h in diagnosis.hypotheses if h.id not in NOT_A_LEVER and _moves(h)]


def select_claims(metrics: MetricsContract, diagnosis: DiagnosisContract, code: str | None) -> list[Claim]:
    """The claims, ranked, each with its catalog sentences, or none (design
    4.1). `code`: the file's confirmed currency, so money in a claim is
    written as the front writes it."""
    eligible = candidates(metrics, diagnosis)
    if not eligible or diagnosis.tree is None:
        return []
    headline = diagnosis.headline
    tree = diagnosis.tree
    ctx = Context(metrics=metrics, tree=tree, bridge=tree.lever.bridge, year_ago=diagnosis.year_ago, code=code)
    named = headline.named or ([headline.hypothesis_id] if headline.hypothesis_id else [])
    order = {h.id: index for index, h in enumerate(diagnosis.hypotheses)}

    def rank(h: Hypothesis) -> tuple[int, float, int]:
        first = named.index(h.id) if h.id in named else len(named)
        return first, -abs(h.contribution or 0.0), order[h.id]

    found: list[tuple[Hypothesis, Direction, tuple[str, str]]] = []
    for hypothesis in sorted(eligible, key=rank):
        direction = own_direction(hypothesis, ctx)
        entry = None if direction is None else ACTIONS.get((hypothesis.id, direction))
        if direction is not None and entry is not None:
            found.append((hypothesis, direction, entry))
    return [Claim(id=claim_id, hypothesis_id=h.id, fact=moved_line(h, ctx), direction=direction,
                  subject=_lower(ctx.subject(h.id)), watch=watch(h, ctx),
                  action=_filled(action, h, set(diagnosis.suggested_classes)), why=why)
            for claim_id, (h, direction, (action, why)) in zip(CLAIM_IDS, found[:MAX_ACTIONS], strict=False)]


def _filled(action: str, hypothesis: Hypothesis, suggested: set[str]) -> str:
    """The catalog's placeholders from stage 3's fields, never its evidence:
    R1's member, R3's row as the appendix labels it (Thach, Q61, Q62). The
    row is named by its label alone: an action holds no digit (the actions
    contract), so not "R3". A member is printed only where the sentence
    stays one the contract carries and the front allows (a code like
    SKU-1042 does not: Q56-Q62's scoped review) and Review did not only
    suggest it is no product (CLAUDE.md 3.3a: the appendix marks it
    "suggested ... not confirmed", the action would call it a product);
    else, and before 18.8, the action points to its row."""
    row = _row(hypothesis)
    named = action.format(member=hypothesis.member, row=row)
    if (hypothesis.member is None or hypothesis.member in suggested or ai_text_problems(named)
            or front_word_problems(named)):
        return action.format(member=f"the product named in {row}", row=row)
    return named


def _row(hypothesis: Hypothesis) -> str:
    """A check's row named as the appendix labels it - by its statement, not
    its id (Thach, Q61; no digit in an action)."""
    return f'the technical section\'s row "{hypothesis.statement}"'


def _moves(hypothesis: Hypothesis) -> bool:
    """With the change (supported or partial), or against it at the
    supported bar or above (design 4.1: "pulled the other way")."""
    if hypothesis.against_the_change:
        return hypothesis.share is not None and abs(hypothesis.share) >= SUPPORTED_MIN_SHARE
    return hypothesis.verdict in ("supported", "partial")


def _sign(value: float | None) -> Direction | None:
    if value is None or value == 0:
        return None
    return "up" if value > 0 else "down"


def own_direction(hypothesis: Hypothesis, ctx: Context) -> Direction | None:
    """The way the claim's own figure moved, read from the order of the two
    figures it rests on (as the fact line words it), or None where they are
    equal as printed or the term cannot be worded (no new figure)."""
    match hypothesis.id:
        case "C1" | "C2" | "C3" | "P3" | "P5":
            terms = money_terms(hypothesis.id, ctx)
            if terms is None:
                return None
            _, now, was = terms
            return None if amount(now, None) == amount(was, None) else ("up" if now > was else "down")
        case "R3":
            return "down"  # a best-seller stopped selling (stage 3's own reading)
        case "R1":
            # Stage 3 writes R1 with no amount (the review): the change was
            # concentrated in one member, so it moved as the sales did.
            return _sign(ctx.metrics.core.revenue_change)
        case _:  # P1 prices, P2 the mix: the measured amount's sign
            return _sign(hypothesis.contribution)


def _lower(text: str) -> str:
    return text[:1].lower() + text[1:]


def _bar(ctx: Context, factor: str) -> tuple[float, float] | None:
    bridge = ctx.bridge
    bar = None if bridge is None else next((b for b in bridge.bars if b.factor == factor), None)
    return None if bar is None else (bar.value_cur, bar.value_prev)


def watch(hypothesis: Hypothesis, ctx: Context) -> str:
    """What to check next month, by kind: the value the claim rests on, this
    month and the month before (design 4.2) - or, with no such field, what
    to look at in words."""
    per = "line" if ctx.lines_basis else "order"
    match hypothesis.id:
        case "P1" | "P2":
            # The chart's bar that holds the price per item (Q20), or the check
            # itself in words where no chart is drawn.
            price = ctx.price_bar()
            if price is None:
                what, values, money = _lower(ctx.subject(hypothesis.id)), None, False
            elif price[0] == "average price per item":
                what, values, money = "the average price per item", _bar(ctx, "price_per_unit"), True
            else:
                what, values, money = f"the average {per} value", _bar(ctx, "aov"), True
        case "C1" | "C2" | "C3" | "P3" | "P5":
            terms = money_terms(hypothesis.id, ctx)
            subject = ctx.subject(hypothesis.id)
            what, values, money = (_lower(terms[0]), (terms[1], terms[2]), True) if terms is not None \
                else (_lower(subject), None, False)
        case "R1":
            return _WATCH.format(what="whether the change stays concentrated in one product or category")
        case "R3":
            return _WATCH.format(what=f"whether the products in {_row(hypothesis)} sell again")
        case _:
            what, values, money = _lower(ctx.subject(hypothesis.id)), None, False
    if values is None:
        return _WATCH.format(what=what)
    now, was = values
    # Every value left is money: B1 and B2's rates moved out with their kinds.
    assert money
    return _WATCH.format(what=_PAIR.format(what=what, now=amount(now, ctx.code), was=amount(was, ctx.code)))
