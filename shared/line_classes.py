"""Which lines are not products, as the user classed them in Review (Thach,
session 2E-d2): postage, fees, discounts, accounting adjustments booked on
product lines. One definition for stage 1's candidates, stage 2 and stage 3.

A line is keyed by its product text: its SKU when it has one, else its name -
`shared/products.py`'s key before its name-only-to-SKU step (2E-f L4), so a
line's class never depends on which lines are sales. The two halves live in
separate namespaces (`sku:`/`name:`), as there: an answer about the SKU
"POST" does not class a line with no SKU named "POST" - stage 1 asks about
such lines under their name - unless that name maps to the SKU as its one
SKU (`line_classes`, 2E-l). Values are read as products are read
(`product_text`) and case is fully folded.

What each class does is `shared/transactions.py`'s business; this module only
says which lines carry which class. Unanswered, a key is a product.
"""

import numpy as np
import pandas as pd

from contracts.cleaning import LineClassAnswer
from shared.text import product_text

# The answer "a product" (2E-l review cycle 1): no class, but an answer.
PRODUCT = "product"


def line_keys(df: pd.DataFrame, reverse: dict[str, str]) -> pd.Series:
    """Each line's key, "sku:<text>" or "name:<text>"; NaN with neither."""
    return keyed(text_identity(df, reverse.get("product_name")), text_identity(df, reverse.get("sku")))


def keyed(names: pd.Series, skus: pd.Series) -> pd.Series:
    """The key from the two halves `text_identity` reads."""
    keys = ("name:" + names).where(names.notna())
    return ("sku:" + skus).where(skus.notna(), keys).astype(object)


def text_identity(df: pd.DataFrame, column: str | None) -> pd.Series:
    """A product column as its key half: read as a reader sees it, case
    folded fully ("Maßband" and "MASSBAND" are one product, 2E-g F6). Each
    distinct value is read once: over every line, the reading cost ~3.5 s a
    parse on Online Retail II's 1,067,371 lines, and a classed run parses
    four times in stage 2 (2E-d2)."""
    if column is None:
        return pd.Series(np.nan, index=df.index, dtype=object)
    codes, uniques = pd.factorize(df[column].astype(object))
    if len(uniques) == 0:
        return pd.Series(np.nan, index=df.index, dtype=object)
    read = product_text(pd.Series(uniques, dtype=object)).str.casefold().to_numpy(dtype=object)
    return pd.Series(np.where(codes >= 0, read[codes], np.nan), index=df.index, dtype=object)


def answer_key(answer: LineClassAnswer) -> str | None:
    """The key an answer names; None when its value reads as nothing."""
    text = product_text(pd.Series([answer.value], dtype=object)).str.casefold().iloc[0]
    if pd.isna(text):
        return None
    return f"{'sku' if answer.field == 'sku' else 'name'}:{text}"


def line_classes(df: pd.DataFrame, reverse: dict[str, str], answers: list[LineClassAnswer],
                 would_sell: pd.Series) -> pd.Series:
    """Each line's class, NaN for a product. Two answers about one key: the
    later one holds, as a later edit would. A line with a name and no SKU
    whose name maps to exactly one SKU (`name_only_sku`) takes that SKU's
    class when the SKU is classed and the name is not answered itself: a
    postage refund rung by name was a product return with no purchase once
    POST, a charge, was no sale - classing only the charges made a new
    customer returning (Thach, 2E-l). "A product" is an answer that stops
    it (2E-l review cycle 1: the user is the final authority, CLAUDE.md
    3.3), and reads as NaN like every product."""
    classes = {key: answer.line_class for answer in answers
               if (key := answer_key(answer)) is not None}
    if not classes:
        return pd.Series(np.nan, index=df.index, dtype=object)
    names = text_identity(df, reverse.get("product_name"))
    skus = text_identity(df, reverse.get("sku"))
    own = keyed(names, skus).map(classes).astype(object)
    inherited = ("sku:" + name_only_sku(names, skus, would_sell)).map(classes).astype(object)
    answered = own.where(own.notna(), inherited)
    return answered.where(answered.ne(PRODUCT)).astype(object)


def name_only_sku(names: pd.Series, skus: pd.Series, would_sell: pd.Series) -> pd.Series:
    """For a line with a name and no SKU, the one SKU its name maps to among
    the lines that WOULD be sales if nothing were classed (2E-f L4, read so
    since 2E-d2 cycle 3 F3); NaN otherwise. Sale lines only, so a stock note
    written on one SKU's write-off cannot pull every such note to it."""
    sold = would_sell & skus.notna() & names.notna()
    one_sku = skus[sold].groupby(names[sold]).agg(
        lambda values: values.iloc[0] if values.nunique() == 1 else np.nan)
    return names.map(one_sku.dropna()).where(skus.isna()).astype(object)
