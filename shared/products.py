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
note written on one SKU's write-off cannot pull every such note to it.
Online Retail II has no name-only line; 99 of its names map to several SKUs
("?" alone to 88) and stay names.
"""

import re
from collections import Counter

import numpy as np
import pandas as pd

from shared.transactions import ParsedTransactions

GAP_LABEL = "(no product name)"

# Characters no reader sees in a product name: the soft hyphen, the Unicode
# format characters (zero-width space, direction marks and embeddings, word
# joiner, invisible operators, BOM, tags), variation selectors, the Hangul and
# Mongolian fillers, the braille blank. A left-to-right mark alone made a
# "product" with an empty label, the top product and biggest decliner, and one
# inside a name split one product in two (2E-g doubt-review F3, cycle 2 F8,
# cycle 3 F5). The zero-width non-joiner and joiner (U+200C, U+200D) are kept:
# inside a word they change how it renders. PRODUCTS ONLY (Thach, option A):
# customers, categories, order ids and stage 1 read text as they always did,
# through shared/transactions.py, until one reading is decided for all.
_INVISIBLE = re.compile(
    "[\u00ad\u034f\u061c\u115f\u1160\u17b4\u17b5\u180b-\u180f\u200b\u200e\u200f"
    "\u202a-\u202e\u2060-\u206f\u2800\u3164\ufe00-\ufe0f\ufeff\uffa0"
    "\ufff9-\ufffb\U0001d173-\U0001d17a\U000e0000-\U000e007f]")


def product_keys(df: pd.DataFrame, parsed: ParsedTransactions) -> pd.Series:
    """Each line's product key, NaN for the data gap."""
    name_col, sku_col = parsed.reverse.get("product_name"), parsed.reverse.get("sku")
    names = _normalized(df, name_col)
    skus = _normalized(df, sku_col)
    keys = ("name:" + names).where(names.notna())
    keys = ("sku:" + skus).where(skus.notna(), keys)
    sold = parsed.sale & skus.notna() & names.notna()
    one_sku = skus[sold].groupby(names[sold]).agg(
        lambda values: values.iloc[0] if values.nunique() == 1 else np.nan)
    resolved = names.map(one_sku.dropna()).astype(object)
    name_only = skus.isna() & resolved.notna()
    return keys.where(~name_only, "sku:" + resolved.fillna(""))


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


def product_text(values: pd.Series) -> pd.Series:
    """A product name or SKU as a reader sees it: Unicode composed (NFC - a
    name typed composed in one month and decomposed in the next was both a
    top seller and the biggest decliner), invisible characters removed,
    whitespace runs as one space, trimmed; NaN where nothing visible is left.
    object dtype: an empty or all-missing column reads back as float, and
    "name:" + a float series does not add (the empty-file case crashed)."""
    text = (values.astype(object).str.normalize("NFC").str.replace(_INVISIBLE, "", regex=True)
            .str.replace(r"\s+", " ", regex=True).str.strip())
    return text.where(text.str.len() > 0).astype(object)


def _fold(label: str) -> str:
    """A label as a reader compares it. Labels are built from `product_text`
    - already composed, free of invisible characters, spaces as one - so
    only case is left to fold (removing the rest again was a no-op, the
    mutation check's equivalent mutant P17)."""
    return label.casefold()


def _normalized(df: pd.DataFrame, column: str | None) -> pd.Series:
    """The key half: the product reading, case folded fully - "Maßband" and
    "MASSBAND" are one product (F6) - where customers keep 3C2's lower-case."""
    return _shown(df, column).str.casefold().astype(object)


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
