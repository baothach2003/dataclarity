"""Which lines are not products, as the user classed them in Review (Thach,
session 2E-d2): postage, fees, discounts, accounting adjustments booked on
product lines. One definition for stage 1's candidates, stage 2 and stage 3.

A line is keyed by its product text: its SKU when it has one, else its name -
`shared/products.py`'s key before its name-only-to-SKU step (2E-f L4), so a
line's class never depends on which lines are sales. The two halves live in
separate namespaces (`sku:`/`name:`), as there: an answer about the SKU
"POST" does not class a line with no SKU named "POST" - stage 1 asks about
such lines under their name. Values are read as products are read
(`product_text`) and case is fully folded.

What each class does is `shared/transactions.py`'s business; this module only
says which lines carry which class. Unanswered, a key is a product.
"""

import numpy as np
import pandas as pd

from contracts.cleaning import LineClassAnswer
from shared.text import product_text


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


def line_classes(df: pd.DataFrame, reverse: dict[str, str],
                 answers: list[LineClassAnswer]) -> pd.Series:
    """Each line's class, NaN for a product. Two answers about one key: the
    later one holds, as a later edit would."""
    classes = {key: answer.line_class for answer in answers
               if (key := answer_key(answer)) is not None}
    if not classes:
        return pd.Series(np.nan, index=df.index, dtype=object)
    return line_keys(df, reverse).map(classes).astype(object)
