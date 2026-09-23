"""Shapley attribution: how much of a change each factor is responsible for
(docs/adr/0004-shapley-attribution.md, docs/AI_PIPELINE.md section 7.6).

The question every lens in step 5 asks is "revenue moved by X - how much of
that was each factor?". The obvious answer, switching one factor at a time
from its previous value to its current one, is exact but **order-dependent**:
on the example in ADR-0004 the customers effect ranges from -40,000 to -67,200
depending only on which loop a developer wrote first. Shapley removes the
choice by averaging over every ordering.

This module is deliberately general. It takes a *value function* rather than a
list of numbers, because two of the decompositions in this stage are not
products of scalars: the price-volume-mix split has a whole share vector and a
whole price vector as single players. One implementation, proved exact once,
serves all of them.
"""

from collections.abc import Callable, Mapping, Sequence
from itertools import permutations

# ADR-0004 accepts n! enumeration precisely because n stays small. The guard is
# here so that a future decomposition with more factors fails loudly instead of
# quietly enumerating 24 or 120 orderings per lens.
MAX_PLAYERS = 3

# A set of players already switched from their previous to their current value.
Coalition = frozenset[str]
ValueFunction = Callable[[Coalition], float]


def shapley(players: Sequence[str], value: ValueFunction) -> dict[str, float]:
    """Each player's average marginal effect over all `len(players)!` orderings.

    `value(switched)` is the total when exactly the players in `switched` hold
    their current values and the rest hold their previous ones. The result sums
    to `value(all) - value(none)` for any value function - a property of the
    construction rather than of the caller's arithmetic.

    **In exact arithmetic.** In floating point the residue is normally around
    1e-16 relative, but it is not always negligible next to the total: when
    the total is itself a near-cancellation the residue can be 100% of it
    (3C doubt-review R1a). Callers that divide by such a total must test it
    relatively rather than against zero, and `tree.py` checks every lens
    against `RECONCILE_REL_TOLERANCE` at runtime rather than trusting this
    docstring.
    """
    if not players:
        return {}
    if len(players) > MAX_PLAYERS:
        raise ValueError(
            f"Shapley here enumerates all orderings and is capped at {MAX_PLAYERS} "
            f"players (docs/adr/0004); got {len(players)}"
        )
    if len(set(players)) != len(players):
        raise ValueError(f"players must be distinct, got {list(players)}")

    totals = dict.fromkeys(players, 0.0)
    orderings = list(permutations(players))
    for ordering in orderings:
        switched: set[str] = set()
        running = value(frozenset(switched))
        for player in ordering:
            switched.add(player)
            after = value(frozenset(switched))
            totals[player] += after - running
            running = after
    return {player: total / len(orderings) for player, total in totals.items()}


def shapley_product(
    previous: Mapping[str, float], current: Mapping[str, float]
) -> dict[str, float]:
    """Shapley for `F = x_1 * ... * x_n`, the shape of every lever-tree level.

    Both mappings carry the same factor names; each factor contributes its
    current value when it is in the coalition and its previous value otherwise.
    """
    if set(previous) != set(current):
        raise ValueError(
            f"previous and current must describe the same factors; "
            f"got {sorted(previous)} and {sorted(current)}"
        )
    players = list(previous)

    def value(switched: Coalition) -> float:
        product = 1.0
        for name in players:
            product *= current[name] if name in switched else previous[name]
        return product

    return shapley(players, value)
