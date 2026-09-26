"""Text readings the stages share: what a blank cell is, who a customer is,
and how a product name or SKU reads. Pure functions of a column, importing no
other shared module, so `shared/transactions.py`, `shared/products.py` and
`shared/line_classes.py` can all read them without an import cycle (2E-d2
moved them here - from transactions.py, to keep it under ~300 lines, and from
products.py; the definitions are unchanged)."""

import re

import pandas as pd

# Characters no reader sees in a product name: the soft hyphen, the Unicode
# format characters (zero-width space, direction marks and embeddings, word
# joiner, invisible operators, BOM, tags), variation selectors, the Hangul and
# Mongolian fillers, the braille blank. A left-to-right mark alone made a
# "product" with an empty label, the top product and biggest decliner, and one
# inside a name split one product in two (2E-g doubt-review F3, cycle 2 F8,
# cycle 3 F5). The zero-width non-joiner and joiner (U+200C, U+200D) are kept:
# inside a word they change how it renders. PRODUCTS ONLY (Thach, option A):
# customers, categories, order ids and stage 1 read text as they always did
# (`normalize_text`, `customer_identity` below), until one reading is decided
# for all (2E-i).
_INVISIBLE = re.compile(
    "[\u00ad\u034f\u061c\u115f\u1160\u17b4\u17b5\u180b-\u180f\u200b\u200e\u200f"
    "\u202a-\u202e\u2060-\u206f\u2800\u3164\ufe00-\ufe0f\ufeff\uffa0"
    "\ufff9-\ufffb\U0001d173-\U0001d17a\U000e0000-\U000e007f]")


def is_blank(values: pd.Series) -> pd.Series:
    """True where a cell is missing or holds only whitespace - the same
    definition of "missing" docs/AI_PIPELINE.md section 6 uses for
    drop_rows_missing, applied to optional columns (`customer`, `sku`,
    `category`) stage 1 has no reason to have trimmed."""
    return values.isna() | (values.astype(object).str.strip() == "")


def normalize_text(values: pd.Series) -> pd.Series:
    """Strip and case-fold for grouping. astype(object): an all-missing column
    can read back as float64, and .str only works on an object/string dtype.
    NaN propagates through strip/lower/concat unharmed."""
    return values.astype(object).str.strip().str.lower()


def customer_identity(values: pd.Series) -> pd.Series:
    """The key that decides whether two rows are the same customer.

    Stripped and case-folded, so "CUST_01", " cust_01" and "Cust_01 " are one
    person - the same treatment product keys have had (shared/products.py)
    since 2C, applied to the other identity column for the same reason
    (Thach, session 3C2). Blank values stay blank, so `is_blank` still selects
    the unattributed rows afterwards.

    Why the asymmetry of the risk decides it: grouping raw *splits* one
    customer into several, and 3C reproduced what that does - one customer
    written three ways, buying the same amount each month, reads as
    `new = 200 / lapsed = -200`, which is "we lost everyone and gained a
    whole new base" printed on a flat month. That fabrication comes from
    ordinary data entry and feeds the C-family hypotheses and possibly the
    headline. The opposite error needs two genuinely different ids differing
    only by case or whitespace, which is rare for POS codes.

    Deliberately no further normalisation - no leading-zero stripping, no
    punctuation rules (Thach, 3C2). Those would start merging ids that a POS
    really does distinguish, and this helper's whole justification is that its
    error direction is the safe one.
    """
    return normalize_text(values)


def merged_identity_count(values: pd.Series) -> int:
    """How many distinct raw values `customer_identity` collapsed away.

    Distinct raw values minus distinct identities, over the rows passed in: a
    customer written three ways contributes 2. Zero means normalisation
    changed no grouping at all, which is what a clean file should show.
    """
    identity = customer_identity(values)
    usable = ~is_blank(identity)
    return int(values[usable].nunique() - identity[usable].nunique())


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
