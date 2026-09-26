"""Which product a line is, and what to call it: one definition, shared by
stage 2's product tables, stage 3's product lens and the first-day rule
(Thach, session 2E-g). Infrastructure in the sense of `shared/transactions.py`:
two stages that name one product two ways describe two different reports.

The key is the line's SKU when it has one, else its name - the business-key
precedent of docs/AI_PIPELINE.md section 11, per line since a mapped sku
column can have blank cells. Values are read as a reader sees them
(`product_text`: composed, invisible characters removed, whitespace runs as
one space, trimmed), and case is fully folded, so "SKU1",
" SKU1" and "sku1" are one product, and the two halves live in separate
namespaces (`sku:`/`name:`) so a SKU that reads like an unrelated product's
name can never merge them (2C). A line with neither is no product: its key
is NaN, the data gap every reader shows as "(no product name)" and never
ranks (Thach, 2E-c2).

A name-only line takes the SKU when its name, as carried by SALE lines that
have a SKU, maps to exactly one SKU (Thach, 2E-f limit L4): a refund rung by
description no longer reads as a second product. Sale lines only, so a stock
note written on one SKU's write-off cannot pull every such note to it - read
as if nothing were classed (2E-d2), so classing one SKU never moves another
product's lines; a classed SKU itself is never taken.
Online Retail II has no name-only line; 99 of its names map to several SKUs
("?" alone to 88) and stay names.

A line the user classed in Review as not a product - postage, a fee, a
discount, an adjustment (Thach, 2E-d2) - has no product key either. Unlike
the gap it is no data problem: readers that must still add up to revenue
(stage 3's product lens and members) carry it as a bucket of its own.
"""

from collections import Counter

import numpy as np
import pandas as pd

from shared.line_classes import keyed, text_identity
from shared.text import product_text
from shared.transactions import ParsedTransactions

GAP_LABEL = "(no product name)"


def product_keys(df: pd.DataFrame, parsed: ParsedTransactions) -> pd.Series:
    """Each line's product key; NaN for the data gap, and for a line the
    user classed in Review as not a product (Thach, 2E-d2: postage, fees,
    discounts and adjustments leave every product table). Keyed as
    shared/line_classes.py keys a line's class, one definition."""
    return _keys(df, parsed, classed_leave=True)


def netting_keys(df: pd.DataFrame, parsed: ParsedTransactions) -> pd.Series:
    """The first-day netting's key (2E-f, shared/first_purchase.py): every
    line keyed as it would be unanswered, classed or not. Keyed as no
    product, a postage refund on a customer's first day was "nameless", the
    history opened with a refund and the customer was never new - 191 new
    customers read 190 on Online Retail II's 2011-11 (2E-d2 doubt-review F1);
    keyed by its class's own line key, a refund rung without a SKU no longer
    netted the classed POST sale (cycle 3 F4)."""
    return _keys(df, parsed, classed_leave=False)


def _keys(df: pd.DataFrame, parsed: ParsedTransactions, *, classed_leave: bool) -> pd.Series:
    names = text_identity(df, parsed.reverse.get("product_name"))
    skus = text_identity(df, parsed.reverse.get("sku"))
    keys = keyed(names, skus)
    # The name-only vote reads the lines as if nothing were classed: read on
    # sales only, a classed fee (no sale) left "Manual" one SKU instead of two
    # and a 900 line joined WHITE HEART (2E-d2 doubt-review cycle 3 F3).
    would_sell = ((parsed.counted | parsed.left_out) & (parsed.quantities > 0)
                  & (parsed.revenue_amounts > 0))
    sold = would_sell & skus.notna() & names.notna()
    one_sku = skus[sold].groupby(names[sold]).agg(
        lambda values: values.iloc[0] if values.nunique() == 1 else np.nan)
    resolved = names.map(one_sku.dropna()).astype(object)
    if classed_leave:
        # A classed SKU names no product, so a name-only line cannot take it.
        classed_skus = set(skus[parsed.line_class.notna()].dropna())
        resolved = resolved.where(~resolved.isin(classed_skus))
    name_only = skus.isna() & resolved.notna()
    keys = keys.where(~name_only, "sku:" + resolved.fillna(""))
    return keys.where(parsed.line_class.isna()) if classed_leave else keys


def product_labels(df: pd.DataFrame, parsed: ParsedTransactions, keys: pd.Series) -> pd.Series:
    """Per product key, the name a reader sees (Thach, 2E-g): the name its sale
    lines carry most often over the whole file, a tie going to the most
    recent sale, so a product reads the same in both months - the first name
    written showed "RED SPOTTY PURSE" for a product sold as "RED RETROSPOT
    PURSE", and stock notes ("Damaged", "given away") for 17 Online Retail II
    products. With no named sale line, the commonest name on any line, else
    the SKU as written. A name several products share (34 names, 75 products
    on Online Retail II) shows each one's SKU, and so does a product named
    like the gap. Every label is unique."""
    frame = pd.DataFrame({"key": keys, "name": _shown(df, parsed.reverse.get("product_name")),
                          "sku": _shown(df, parsed.reverse.get("sku")), "sale": parsed.sale,
                          "date": parsed.dates}).dropna(subset=["key"])
    products = pd.Index(frame["key"].unique())
    labels = _commonest(frame[frame["sale"]]).reindex(products)
    labels = labels.fillna(_commonest(frame).reindex(products))
    sku_shown = frame.dropna(subset=["sku"]).groupby("key")["sku"].first().reindex(products)
    labels = labels.fillna(sku_shown)

    # Compared as a reader sees them (`_fold`): "RED MUG" and "RED\u00a0MUG"
    # look alike (2E-g doubt-review F7). Counted once, not per label: counting
    # inside the loop took 20 s at 50,000 products (cycle 3, F8).
    names, skus = labels.astype(object).tolist(), sku_shown.astype(object).tolist()
    folded = [_fold(name) for name in names]
    gap = _fold(GAP_LABEL)
    counts = Counter(folded)
    shared = {text for text, count in counts.items() if count > 1} | {gap}
    shown = [f"{name} ({sku})" if text in shared and isinstance(sku, str)
             # A product literally named like the gap, with no SKU to show
             # (F2): it kept the gap's label and the report seemed to rank it.
             else f"{name} (named product)" if text == gap else name
             for name, sku, text in zip(names, skus, folded, strict=True)]
    # A suffixed label can meet another product's name ("MUG" under S1 and a
    # product named "MUG (S1)"), and a reader would credit both sums to one
    # product (cycle 2, F6): the later one is numbered until every label is
    # unique. The gap's own label is never given to a product.
    seen, unique = {gap}, []
    for label in shown:
        candidate, number = label, 1
        while _fold(candidate) in seen:
            number += 1
            candidate = f"{label} ({number})"
        seen.add(_fold(candidate))
        unique.append(candidate)
    return pd.Series(unique, index=products, dtype=object)


def _fold(label: str) -> str:
    """A label as a reader compares it. Labels are built from `product_text`
    - already composed, free of invisible characters, spaces as one - so
    only case is left to fold (removing the rest again was a no-op, the
    mutation check's equivalent mutant P17)."""
    return label.casefold()


def _shown(df: pd.DataFrame, column: str | None) -> pd.Series:
    if column is None:
        return pd.Series(np.nan, index=df.index, dtype=object)
    return product_text(df[column])


def _commonest(lines: pd.DataFrame) -> pd.Series:
    """Per key, its most frequent name; a tie goes to the name sold last."""
    named = lines.dropna(subset=["name"])
    if named.empty:
        return pd.Series(dtype=object)
    # One pass over the dates for both figures: the named-aggregation form
    # took most of a stage 3 run, which asks for the labels a dozen times.
    dates = named.groupby(["key", "name"], sort=False)["date"]
    stats = pd.DataFrame({"count": dates.size(), "last": dates.max()}).reset_index()
    stats = stats.sort_values(["key", "count", "last"], ascending=[True, False, False])
    return stats.drop_duplicates("key").set_index("key")["name"]
