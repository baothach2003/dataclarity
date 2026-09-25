"""Step 6: where did the change happen?
(docs/AI_PIPELINE.md section 7.7, docs/DIAGNOSE_DESIGN.md 5.6)

Step 5 says *what* moved - customers, price, mix. This step says *where*: which
categories, which products, which kinds of customer. The two answer different
questions about the same change and neither replaces the other.

**The dimensions are fixed in advance** (docs/adr/0005): category when it is
mapped, product, and customer type from the bridge. Nothing here searches the
data for an interesting way to slice it. A search would find one on any file -
that is what searching does - and the engine's credibility rests on testing a
list it committed to before seeing the numbers.
"""

from dataclasses import dataclass

import pandas as pd

from contracts.diagnosis import Dimension, Member
from shared.products import GAP_LABEL, product_keys, product_labels
from shared.transactions import is_blank, normalize_text, require_column
from stages.diagnose.numbers import is_negligible
from stages.diagnose.inputs import RunData, period_mask
from stages.diagnose.thresholds import (
    MEMBER_MIN_ORDERS,
    MEMBER_MIN_REVENUE_SHARE,
    MEMBERS_PER_DIMENSION,
)

# Rows whose key column is blank. The label is what a reader sees; the bucket
# is identified by `is_data_gap`, not by its name, so a real category that
# happens to be spelled this way stays a separate member rather than merging
# into the gap (Thach, 3D). The internal key carries characters
# `normalize_text` can never produce - it lowercases and strips - so the two
# cannot collide during grouping either.
UNCATEGORISED_LABEL = "(uncategorised)"
UNCATEGORISED_KEY = "\x00UNCATEGORISED"
UNNAMED_PRODUCT_LABEL = GAP_LABEL  # stage 2 shows the gap in the same words
UNNAMED_PRODUCT_KEY = "\x00UNNAMED_PRODUCT"

CUSTOMER_TYPES = ("new", "resurrected", "retained", "lapsed")


@dataclass(frozen=True)
class MemberTotals:
    """One dimension's raw material: revenue and order counts per member, per
    period, before any filtering or ranking."""

    rev_prev: pd.Series
    rev_cur: pd.Series
    orders_prev: pd.Series
    orders_cur: pd.Series
    # Display name per key, since keys are normalised for grouping but a
    # reader wants the spelling the file used.
    labels: dict[str, str]
    gap_keys: frozenset[str]


def build_dimension(name: str, totals: MemberTotals, delta_total: float,
                    scale: float = 0.0) -> Dimension:
    """Rank, group and report one dimension.

    The invariant every test checks: named members + Other + new + removed
    account for the dimension's whole change exactly. A dimension that
    silently drops a member reads as a smaller change happening somewhere
    identifiable, which is worse than no localization at all.
    """
    keys = sorted(set(totals.rev_prev.index) | set(totals.rev_cur.index))
    # Presence is simply "this key has a revenue-counted row in that period" -
    # the definition Thach chose for the bridge in 3C, reused so the two
    # lenses agree about who was there. The revenue groupby only ever holds
    # keys that occurred, so membership of its index IS the rule. Not the
    # orders index: since 2E orders count sale rows only, and a product seen
    # only through a refund is still present (decision (c) rejects
    # "non-zero orders" as the rule).
    present_prev = set(totals.rev_prev.index)
    present_cur = set(totals.rev_cur.index)

    # Everything below keys on the IDENTITY, never on the display name. Two
    # keys can legitimately share a label - two SKUs of one product name is
    # the commonest shape in retail, and a real category spelled
    # "(uncategorised)" collides with the gap bucket's label by construction.
    # Keyed on names, the second such member matched the first's entry in
    # `named_names`, was excluded from the remainder, and appeared in neither
    # `members` nor `other`: 6.4% of the change silently vanished and the
    # dimension stopped reconciling (3D doubt-review C1).
    members = {key: _member(key, totals, delta_total, scale) for key in keys}

    # A member whose sales and returns cancelled to zero in both periods is an
    # ordinary member with delta 0: neither new nor removed, never named
    # (ranking is by |delta|), contributing nothing to any total.
    #
    # The data-gap buckets are deliberately absent from both lists: reported
    # there they become "a new category launched this month: (uncategorised)",
    # which defeats through the side door the very thing `is_data_gap` exists
    # to prevent, since these lists carry no flag (3D doubt-review R3).
    new_members = [totals.labels[key] for key in keys
                   if key in present_cur and key not in present_prev
                   and key not in totals.gap_keys]
    removed_members = [totals.labels[key] for key in keys
                       if key in present_prev and key not in present_cur
                       and key not in totals.gap_keys]

    large = _large_keys(keys, totals)

    # Two reasons to name a member that did not clear the size bar.
    #
    # Nothing cleared it: localization exists to answer "where", and a
    # dimension that names nobody answers nothing - on a fragmented shop that
    # is exactly where a reader most needs the biggest movers pointed at
    # (Thach, 3D).
    #
    # Everything fits anyway: the bar exists to stop a long tail crowding the
    # list, and there is no tail when the whole dimension fits in the named
    # slots. This is not hypothetical tidiness - `customer_type` has four
    # fixed members and the bar is a share of PREVIOUS revenue, which `new`
    # has none of - or only a deduction's worth, since 2E-c lets a customer
    # present through a coupon last month be new now - so a filtered
    # customer_type dimension would hide new customers every single run.
    everything_fits = len(keys) <= MEMBERS_PER_DIMENSION
    candidates = keys if (not large or everything_fits) else \
        [key for key in keys if key in large]

    ranked = sorted(candidates, key=lambda key: (-abs(members[key].delta), key))
    named = ranked[:MEMBERS_PER_DIMENSION]
    remainder = [members[key] for key in keys if key not in set(named)]

    return Dimension(
        name=name,
        members=[members[key] for key in named],
        other=_other(remainder, delta_total, scale),
        new_members=new_members,
        removed_members=removed_members,
        # Exactly what the contract says it is: nothing cleared the size bar
        # and the top movers were named anyway. It deliberately does NOT cover
        # the `everything_fits` branch - a two-member dimension where one holds
        # 99.9% of revenue would otherwise report a waiver, handing step 7 the
        # opposite of the signal it reads this field for (3D doubt-review R4).
        size_filter_waived=not large and bool(keys),
        member_count=len(keys),
    )


def _member(key: str, totals: MemberTotals, delta_total: float, scale: float = 0.0) -> Member:
    rev_prev = float(totals.rev_prev.get(key, 0.0))
    rev_cur = float(totals.rev_cur.get(key, 0.0))
    delta = rev_cur - rev_prev
    return Member(
        name=totals.labels[key],
        rev_prev=rev_prev,
        rev_cur=rev_cur,
        delta=delta,
        share_of_change=_share(delta, delta_total, scale),
        is_data_gap=key in totals.gap_keys,
    )


def _share(delta: float, delta_total: float, scale: float = 0.0) -> float:
    """A member's slice of the total change, or 0.0 when the total did not
    really move.

    The guard is relative, not `== 0` (3D doubt-review C2). On a flat month
    whose total came out as -5.6e-17 of float residue, dividing by it gave a
    member a share of -5.4e15 - which step 8 would narrate as "this product
    accounts for -540,000,000,000,000,000% of the change". `lever.py` fixed
    this same mistake twice in 3C; the helper now lives in `numbers.py` so a
    third place cannot rediscover it. `scale` is the money moved (2E doubt-
    review cycle 3): a +1 change on 3.1e9 of trade is nothing to stage 2, and
    judged only against the members' own deltas it gave one a share of
    2,000,000x.
    """
    if is_negligible(delta_total, delta_total, delta, scale):
        return 0.0
    return delta / delta_total


def _large_keys(keys: list[str], totals: MemberTotals) -> set[str]:
    """Which members are too big or too busy to be swept into Other.

    Small AND quiet collapses - both conditions, per the spec. A member with
    little revenue but many orders stays named: a cheap line selling
    constantly is a real part of the business, and hiding it inside Other
    would lose exactly the kind of member a shop owner recognises.

    The size test is on MAGNITUDES. Signed, a returns line whose previous
    month netted -2,500 against a 600 base produced a share of -4.2, which is
    "below 2%", so the single largest movement in the dimension was judged
    small and quiet; and a negative base inverted the test so that only
    members with negative previous revenue counted as large, burying six
    ordinary products in Other (3D doubt-review C3). `compute_breadth` already
    guards this; this function did not.
    """
    base = sum(abs(float(totals.rev_prev.get(key, 0.0))) for key in keys)
    large = set()
    for key in keys:
        share = abs(float(totals.rev_prev.get(key, 0.0))) / base if base else 0.0
        orders = max(int(totals.orders_prev.get(key, 0)),
                     int(totals.orders_cur.get(key, 0)))
        if share >= MEMBER_MIN_REVENUE_SHARE or orders >= MEMBER_MIN_ORDERS:
            large.add(key)
    return large


def _other(remainder: list[Member], delta_total: float, scale: float = 0.0) -> Member | None:
    if not remainder:
        return None
    rev_prev = sum(m.rev_prev for m in remainder)
    rev_cur = sum(m.rev_cur for m in remainder)
    delta = rev_cur - rev_prev
    return Member(
        name="Other",
        rev_prev=rev_prev,
        rev_cur=rev_cur,
        delta=delta,
        share_of_change=_share(delta, delta_total, scale),
    )


# --- the three dimensions -----------------------------------------------------


def category_totals(data: RunData) -> MemberTotals | None:
    column = data.parsed.reverse.get("category")
    if column is None:
        return None
    keys = normalize_text(data.df[column])
    blank = is_blank(data.df[column])
    # Blank categories are one visible member, not an omission (Thach, 3D).
    # Dropping them would leave the dimension reconciling to a subtotal while
    # the rest of the report talks about the whole change - the shape of 3C's
    # first critical. Note this deliberately differs from stage 2's
    # `by_dimension`, which excludes them: that block has no reconciliation
    # duty, this one does.
    keys = keys.where(~blank, UNCATEGORISED_KEY)
    labels = _labels(data.df[column], keys, {UNCATEGORISED_KEY: UNCATEGORISED_LABEL})
    return _totals(data, keys, labels, frozenset({UNCATEGORISED_KEY}))


def product_totals(data: RunData) -> MemberTotals:
    require_column(data.parsed.reverse, "product_name")
    # Stage 2's keys and labels (shared/products.py, 2E-g): a line with a SKU
    # and no name is its product - it was in the gap while stage 2 named it
    # by SKU (4,275 Online Retail II lines). Only a line with neither is the
    # gap member, which `is_data_gap` keeps out of step 7's recommendations
    # (3D doubt-review R1: a whitespace name once became a product "   ").
    keys = product_keys(data.df, data.parsed)
    labels = product_labels(data.df, data.parsed, keys).to_dict()
    labels[UNNAMED_PRODUCT_KEY] = UNNAMED_PRODUCT_LABEL
    return _totals(data, keys.fillna(UNNAMED_PRODUCT_KEY), labels,
                   frozenset({UNNAMED_PRODUCT_KEY}))


def customer_type_totals(data: RunData, classes: dict[str, str]) -> MemberTotals:
    """Revenue by how the bridge classified each customer.

    The classes come from step 5 rather than being recomputed, so the two
    blocks cannot disagree about who was new. Rows with no customer are the
    bridge's `unattributed` term and form their own visible member here for
    the same reason blank categories do.
    """
    customer_col = data.parsed.reverse.get("customer")
    if customer_col is None:
        raise ValueError("customer_type_totals requires a mapped customer column")
    # The per-row customer the classes were built on (2E-f): a header-style
    # receipt's unnamed lines are its customer's, not "(no customer)".
    keys = data.parsed.customers.map(classes).fillna(UNCATEGORISED_KEY)
    labels = {name: name for name in CUSTOMER_TYPES}
    labels[UNCATEGORISED_KEY] = "(no customer)"
    return _totals(data, keys, labels, frozenset({UNCATEGORISED_KEY}))


def _labels(source: pd.Series, keys: pd.Series, reserved: dict[str, str]) -> dict[str, str]:
    """Each key's first-seen spelling in the file, so the report shows what the
    shop actually typed rather than the normalised key."""
    frame = pd.DataFrame({"key": keys, "label": source})
    labels = frame.groupby("key")["label"].first().to_dict()
    for key, label in reserved.items():
        labels[key] = label
    return {key: str(label) for key, label in labels.items()}


def _totals(
    data: RunData, keys: pd.Series, labels: dict[str, str], gap_keys: frozenset[str]
) -> MemberTotals:
    period = data.metrics.period
    frames = {}
    for label, month in (("prev", period.previous), ("cur", period.current)):
        mask = period_mask(data, month)
        grouped = keys[mask]
        frames[f"rev_{label}"] = data.parsed.revenue_amounts[mask].groupby(grouped).sum()
        # Orders containing the member (2E-e): distinct order keys among its
        # sale rows - order ids when order_id is mapped, else each sale line. A
        # key with only refunds has 0 orders, not an entry.
        sale = mask & data.parsed.sale
        frames[f"orders_{label}"] = data.parsed.order_key[sale].groupby(keys[sale]).nunique()
    return MemberTotals(
        rev_prev=frames["rev_prev"],
        rev_cur=frames["rev_cur"],
        orders_prev=frames["orders_prev"],
        orders_cur=frames["orders_cur"],
        labels=labels,
        gap_keys=gap_keys,
    )
