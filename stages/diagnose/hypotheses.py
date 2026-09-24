"""Step 7: evaluate the fixed catalog (docs/AI_PIPELINE.md 7.8).

Every id in `catalog.CATALOG` is evaluated on every run, in catalog order,
including the ones that come out `ruled_out` (docs/adr/0005). Ids, families,
lenses and statements come from the catalog and nowhere else; this module
decides verdicts. The per-hypothesis evidence functions live in
`hypothesis_evidence.py`; what lives here is the part every share hypothesis
shares - the change it must explain, the denominator D, and the verdict rule.

**D, the explained-share denominator.** `share = contribution / D`. Normally
D is |the total of the hypothesis's own lens| - the net change for every lens
except the product lens, whose total is the change in GROSS sales.

When the masked-shift alert is on, the net change is small by construction
and shares of it explode, so for a TERM D becomes the gross of **the
decomposition the term belongs to**:

    B1                   level 1 (customers x frequency x AOV)
    B2                   level 2 (units per order x price per unit)
    P1, P2, R2           the product lens (price-volume-mix)
    P3                   the returns lens (|change in gross| + |change in returns|)

A term is bounded by its split's gross, so |share| <= 1 holds by construction.

An EXPECTATION (D1, T1, T2, R3, C1-C3) keeps D = |the change it claims to
explain| even under the alert: whether it explains THAT change is the
question, and its overshoot is the signal. Measured against a gross, the
overshoot vanished - T2 predicting 26 times a flat month came out supported at
0.43 of level 1's gross (3E1 doubt-review cycle 2, F4). A directional
hypothesis has no share.

NEVER the orders x AOV pair the alert is decided on (the question 3D6b left
open). The pair is the alert's decision device: it deliberately hides the
customers/frequency movement, so its gross understates how much moved, and a
share whose numerator comes from one split and denominator from another is
not bounded by 1 - B1's frequency term is 0.31 of level 1's gross and would be
0.95 of the pair's on the pair review's S6-like case.
"""

from contracts.diagnosis import Hypothesis, Tree
from stages.diagnose.catalog import CATALOG, HypothesisSpec
from stages.diagnose.hypothesis_evidence import EVIDENCE
from stages.diagnose.numbers import is_negligible
from stages.diagnose.step7_inputs import Changes, Step7Inputs, changes
from stages.diagnose.thresholds import PARTIAL_MIN_SHARE, SUPPORTED_MIN_SHARE


# Which decomposition's gross is D for each TERM while the alert is on
# (module docstring). Exactly the catalog's `term` ids, under test.
DECOMPOSITION = {
    "B1": "level1",
    "B2": "level2",
    "P1": "product", "P2": "product", "R2": "product",
    "P3": "returns",
}


def decomposition_gross(tree: Tree, name: str) -> float | None:
    if name == "level1":
        level = tree.lever.level1
        return sum(abs(f.contribution) for f in level.factors) if level else None
    if name == "level2":
        level = tree.lever.level2
        return sum(abs(f.contribution) for f in level.factors) if level else None
    if name == "product":
        p = tree.products
        return (abs(p.volume) + abs(p.mix) + abs(p.price) + abs(p.new_products)
                + abs(p.discontinued_products))
    r = tree.returns
    return abs(r.gross_cur - r.gross_prev) + abs(r.returns_cur - r.returns_prev)


def share_verdict(spec: HypothesisSpec, contribution: float, inputs: Step7Inputs,
                  moved: Changes) -> tuple[str, float | None, str]:
    """The 7.8 verdict table for a share hypothesis: same sign as the change it
    claims to explain, and |share| against the two thresholds."""
    total = moved.gross if spec.lens == "product" else moved.net
    if total is None or is_negligible(total, moved.revenue_prev, moved.revenue_cur,
                                      moved.scale):
        return "ruled_out", None, "the total did not move, so there is no change to explain"
    if moved.alert and inputs.tree is not None and spec.kind == "term":
        denominator = decomposition_gross(inputs.tree, DECOMPOSITION[spec.id])
        basis = f"gross of {DECOMPOSITION[spec.id]} (masked-shift alert on)"
    else:
        denominator = abs(total)
        basis = "|change in gross sales|" if spec.lens == "product" else "|change in revenue|"
    if not denominator:
        return "ruled_out", None, f"D = {basis} is zero"
    share = contribution / denominator
    same_sign = contribution != 0 and (contribution > 0) == (total > 0)
    size = abs(share)
    if spec.kind == "expectation":
        # An estimate explains the change only if it leaves at most
        # 1 - SUPPORTED_MIN_SHARE of it unexplained, in EITHER direction:
        # share in [0.2, 1.8]. A season that predicted +500 for a +50 month
        # did not explain it - the month fell 450 short (Thach, 3E1).
        # Written as a band, not |1 - share| <= 0.8: 1 - 1.8 is
        # -0.8000000000000000444 in binary and would refuse the edge.
        explains = SUPPORTED_MIN_SHARE <= size <= 2 - SUPPORTED_MIN_SHARE
    else:
        explains = size >= SUPPORTED_MIN_SHARE
    if same_sign and explains:
        verdict = "supported"
    elif same_sign and PARTIAL_MIN_SHARE <= size < SUPPORTED_MIN_SHARE:
        verdict = "partial"
    else:
        verdict = "ruled_out"
    if spec.kind == "expectation":
        rule = (f"share = contribution / D, D = {basis}; an expectation is supported if "
                f"same sign and {SUPPORTED_MIN_SHARE} <= |share| <= "
                f"{2 - SUPPORTED_MIN_SHARE:.1f}, partial if {PARTIAL_MIN_SHARE} <= |share| < "
                f"{SUPPORTED_MIN_SHARE}")
    else:
        rule = (f"share = contribution / D, D = {basis}; supported if same sign and "
                f"|share| >= {SUPPORTED_MIN_SHARE}, partial if >= {PARTIAL_MIN_SHARE}")
    return verdict, share, rule


def evaluate_hypotheses(inputs: Step7Inputs) -> list[Hypothesis]:
    moved = changes(inputs)
    blocked = inputs.trust.verdict == "blocked"
    results = []
    for spec in CATALOG:
        if blocked and spec.family != "data_quality":
            results.append(_make(spec, "inconclusive", None, None,
                                 {"reason": "the trust gate blocked this run"},
                                 "not evaluated: blocked run (CONTRACTS section 7)"))
            continue
        outcome = EVIDENCE[spec.id](inputs, moved)
        evidence = outcome.evidence or {}
        if outcome.verdict is not None:
            results.append(_make(spec, outcome.verdict, None, None, evidence,
                                 outcome.rule or spec.test, outcome.sign))
            continue
        verdict, share, rule = share_verdict(spec, outcome.contribution, inputs, moved)
        results.append(_make(spec, verdict, outcome.contribution, share, evidence, rule,
                             outcome.contribution))
    return results


def _make(spec: HypothesisSpec, verdict: str, contribution: float | None,
          share: float | None, evidence: dict, rule: str,
          sign: float | None = None) -> Hypothesis:
    return Hypothesis(id=spec.id, family=spec.family, lens=spec.lens,
                      statement=spec.render(sign), verdict=verdict,
                      contribution=contribution, share=share,
                      evidence=evidence, rule=rule)
