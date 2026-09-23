"""Step 5: the metric tree, assembled (docs/AI_PIPELINE.md section 7.6).

Four lenses on the same month, each answering a different question, each
reconciling to its own total:

  lever     revenue = customers x frequency x AOV   -> delta_net
  customers who bought, who stopped, who grew       -> delta_net
  returns   gross sales against refunds             -> delta_net
  products  price, volume and mix on gross sales    -> delta_gross

**The lenses never sum together.** They are four views of one change, not four
parts of it; adding a lever contribution to a product effect double-counts the
same pounds. CONTRACTS section 7 states this as a rule for stage 5, and it is
repeated here because this is the file where someone would be tempted.
"""

from contracts.diagnosis import ReturnsLens, Tree
from stages.diagnose.bridge import compute_bridge
from stages.diagnose.inputs import RunData
from stages.diagnose.lever import compute_lever, month_revenue, returns_levels
from stages.diagnose.pvm import compute_products
from stages.diagnose.thresholds import RECONCILE_REL_TOLERANCE


class ReconciliationError(AssertionError):
    """A lens did not sum to the total it decomposes.

    This is never a data problem: every lens here is exact in real arithmetic,
    so if one fails to reconcile the code is wrong, and every number it feeds
    downstream - the localized members, the hypothesis shares, the headline -
    is wrong with it. Failing loudly beats writing a confident report built on
    a decomposition that does not add up.
    """


def compute_tree(data: RunData, history: list[str]) -> Tree:
    returns = ReturnsLens(**returns_levels(data))
    tree = Tree(
        method="shapley",
        lever=compute_lever(data, history),
        customers=compute_bridge(data),
        returns=returns,
        products=compute_products(data),
    )
    _check_reconciliation(data, tree)
    return tree


def _check_reconciliation(data: RunData, tree: Tree) -> None:
    """Assert at runtime what the specification claims about the output.

    Until this existed, `RECONCILE_REL_TOLERANCE` was imported by the tests and
    by nothing else, so "every decomposition reconciles to its total" held on
    seven hand-built fixtures and was unchecked on every real file (3C
    doubt-review R6). Both criticals that review found produced a tree that
    does not reconcile; this turns that class of bug from silent into loud.
    """
    delta_net = (month_revenue(data, data.metrics.period.current)
                 - month_revenue(data, data.metrics.period.previous))
    delta_gross = tree.returns.gross_cur - tree.returns.gross_prev
    delta_returns = tree.returns.returns_cur - tree.returns.returns_prev

    if tree.lever.level1 is not None:
        _assert_sums([f.contribution for f in tree.lever.level1.factors],
                     delta_net, "lever level 1")
    if tree.lever.level2 is not None:
        phi_aov = next(f.contribution for f in tree.lever.level1.factors
                       if f.name == "aov")
        _assert_sums([f.contribution for f in tree.lever.level2.factors],
                     phi_aov, "lever level 2")
    if tree.customers is not None:
        _assert_sums(
            [tree.customers.new, tree.customers.resurrected, tree.customers.expansion,
             tree.customers.contraction, tree.customers.lapsed,
             tree.customers.unattributed],
            delta_net, "customer bridge")
    _assert_sums(
        [tree.products.volume, tree.products.mix, tree.products.price,
         tree.products.new_products, tree.products.discontinued_products],
        delta_gross, "product lens")
    _assert_sums([delta_gross, -delta_returns], delta_net, "returns lens")


def _assert_sums(parts: list[float], total: float, lens: str) -> None:
    residual = sum(parts) - total
    scale = max(abs(total), sum(abs(part) for part in parts))
    if abs(residual) > RECONCILE_REL_TOLERANCE * scale:
        raise ReconciliationError(
            f"{lens} does not reconcile: parts sum to {sum(parts)!r}, "
            f"total is {total!r}, residual {residual!r}"
        )
