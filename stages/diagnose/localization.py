"""Step 6 assembled: the dimensions, the mix/rate split and breadth
(docs/AI_PIPELINE.md section 7.7).

Breadth is the shape of the change rather than its location. A drop spread
thinly across most of the shop points somewhere quite different from the same
drop concentrated in one line - the first at the calendar, seasonality or a
general price move, the second at something specific that a shop owner can go
and look at.
"""

from contracts.diagnosis import Breadth, Localization
from stages.diagnose.bridge import customer_classes
from stages.diagnose.inputs import RunData, money_moved
from stages.diagnose.members import (
    MemberTotals,
    build_dimension,
    category_totals,
    customer_type_totals,
    product_totals,
)
from stages.diagnose.mix_rate import compute_mix_rate
from stages.diagnose.numbers import is_negligible
from stages.diagnose.thresholds import BREADTH_BROAD, BREADTH_CONCENTRATED


def compute_localization(data: RunData, delta_total: float) -> Localization:
    # Residue in the total change is judged against the money moved, row by
    # row as stage 2 judges it, so stage 3's member shares and breadth call
    # the same change "nothing" that stage 2 does (2E doubt-review cycle 3).
    scale = money_moved(data)
    products = product_totals(data)
    dimensions = []

    categories = category_totals(data)
    if categories is not None:
        dimensions.append(build_dimension("category", categories, delta_total, scale))
    dimensions.append(build_dimension("product", products, delta_total, scale))
    if data.parsed.reverse.get("customer") is not None:
        customers = customer_type_totals(data, customer_classes(data))
        dimensions.append(build_dimension("customer_type", customers, delta_total, scale))

    return Localization(
        dimensions=dimensions,
        mix_rate=compute_mix_rate(data),
        # Measured over products: the finest dimension, and the only one
        # always available (`product_name` is required for stage 2 to have
        # produced metrics.json at all, so there is no run where this is
        # missing). Session 3D's choice - DIAGNOSE_DESIGN 5.6 defines breadth
        # over "members" without naming the dimension. Flagged for veto.
        breadth=compute_breadth(products, delta_total, scale),
    )


def compute_breadth(totals: MemberTotals, delta_total: float, scale: float = 0.0) -> Breadth:
    """How concentrated the change is.

    Both figures are computed over EVERY member, not the handful the
    dimension names: breadth measured over the top five would report that
    every change is concentrated, since the top five are chosen for being the
    largest movers.
    """
    keys = sorted(set(totals.rev_prev.index) | set(totals.rev_cur.index))
    deltas = {key: float(totals.rev_cur.get(key, 0.0)) - float(totals.rev_prev.get(key, 0.0))
              for key in keys}

    # The base is positive previous revenue only. A member whose previous
    # month netted below zero (more refunded than sold) would otherwise make
    # this ratio exceed 1 or go negative, and the contract types it as a
    # share. Leaving such a member out of the base is the conservative
    # reading: it held no revenue to speak of.
    base = {key: float(totals.rev_prev.get(key, 0.0)) for key in keys}
    positive_base = sum(value for value in base.values() if value > 0)
    # A total that did not move has no direction to share. Testing
    # `delta_total > 0` treats a flat month as "down" and counts every member
    # that fell, which produced a `concentrated` breadth verdict - reachable
    # by the headline - on a month where one product rose 50 and another fell
    # 50 (3D doubt-review R8).
    # ...and against the money moved, as stage 2 judges it (2E cycle 3).
    flat = is_negligible(delta_total, *base.values(), delta_total, scale)
    same_direction = 0.0 if flat else sum(
        base[key] for key in keys
        if base[key] > 0 and deltas[key] != 0 and (deltas[key] > 0) == (delta_total > 0)
    )
    declining_base_share = same_direction / positive_base if positive_base else 0.0

    # `max(default=0.0)`, not `sorted(...)[0]`: a run whose periods hold no
    # counted rows at all has no members, and indexing an empty list would
    # take the stage down rather than report a shape it cannot see.
    absolute = [abs(value) for value in deltas.values()]
    total_movement = sum(absolute)
    top_member_share = max(absolute, default=0.0) / total_movement if total_movement else 0.0

    return Breadth(
        declining_base_share=min(max(declining_base_share, 0.0), 1.0),
        top_member_share=min(max(top_member_share, 0.0), 1.0),
        classification="mixed" if flat else _classify(declining_base_share, top_member_share),
    )


def _classify(declining_base_share: float, top_member_share: float) -> str:
    """Broad is tested first, per the spec's own order.

    The two conditions are not exclusive - a shop with one dominant product
    can have most of its revenue base moving the same way - and when both
    hold, "this is happening across the business" is the more useful thing to
    tell a reader than "one member leads it", because it is the one that
    redirects attention away from a single product and towards a cause that
    could affect everything.
    """
    if declining_base_share >= BREADTH_BROAD:
        return "broad"
    if top_member_share >= BREADTH_CONCENTRATED:
        return "concentrated"
    return "mixed"
