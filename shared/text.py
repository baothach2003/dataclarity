"""Text readings the stages share: what a blank cell is, who a customer is,
what an order id, a category or a transaction type reads as, and how a
product name or SKU reads. Pure functions of a column, importing no other
shared module, so `shared/transactions.py`, `shared/products.py` and
`shared/line_classes.py` can all read them without an import cycle (2E-d2).

One reading for every stage (Thach, 2E-i), on two questions:
- Is a cell EMPTY? Nothing visible (`is_blank`): a cell of only whitespace,
  format characters that draw nothing (`_VISIBLE_FORMAT` excepted) or the
  products' invisible characters renders as nothing - the same for every
  column, stage 1's drop_rows_missing included.
- Are two cells the SAME value? Differences a reader cannot see merge
  (`identifier_text`): Unicode composition, the characters that render as
  nothing AND change nothing around them (`_NOTHING`), a no-break space for a
  space, whitespace at the ends - and the direction marks (`_MARKS`), whose
  rare reordering of digits and punctuation is a known cost. Each reader
  then decides case and runs of spaces. Products read wider (`product_text`,
  2E-g)."""

import re
import unicodedata

import numpy as np
import pandas as pd

# Characters no reader sees in a product name: the soft hyphen, the Unicode
# format characters (zero-width space, direction marks and embeddings, word
# joiner, invisible operators, BOM, tags), variation selectors, the Hangul and
# Mongolian fillers, the braille blank. A left-to-right mark alone made a
# "product" with an empty label, the top product and biggest decliner, and one
# inside a name split one product in two (2E-g doubt-review F3, cycle 2 F8,
# cycle 3 F5). The zero-width non-joiner and joiner (U+200C, U+200D) are kept:
# inside a word they change how it renders. Products' keys remove them all
# (Thach, option A of 2E-g); every column's EMPTINESS reads them (2E-i).
_INVISIBLE = re.compile(
    "[\u00ad\u034f\u061c\u115f\u1160\u17b4\u17b5\u180b-\u180f\u200b\u200e\u200f"
    "\u202a-\u202e\u2060-\u206f\u2800\u3164\ufe00-\ufe0f\ufeff\uffa0"
    "\ufff9-\ufffb\U0001d173-\U0001d17a\U000e0000-\U000e007f]")


# The characters that render as nothing AND change nothing around them: the
# soft hyphen, the zero-width space, the word joiner, the invisible operators,
# the BOM. "INV1" and "INV1" with a trailing zero-width space were two orders,
# and one customer typed both ways a lapsed and a new one (2E-g review cycles
# 2-3). Not the products' wider set: a direction override reverses what is
# shown, a variation selector turns a text heart into an emoji, a joiner
# changes a Persian word - removing those merged visibly different ids
# (2E-g review cycle 3 F7). Built from code points, so no invisible character
# sits in this file.
_NOTHING = re.compile("[" + "".join(chr(code) for code in (
    0x00AD, 0x200B, 0x2060, 0x2061, 0x2062, 0x2063, 0x2064, 0xFEFF)) + "]")
# The direction MARKS (left-to-right, right-to-left, Arabic letter mark),
# removed everywhere - as the products' reading removes them (2E-g). A stray
# mark split one customer into a lapsed and a new one, in Latin text (review
# cycle 1 #1) and in the Persian and Hebrew exports where marks are actually
# typed (cycle 2 #1: leading and trailing marks render nothing there either).
# The rare cost, taken knowingly: a mark between digits and punctuation can
# reorder them ("12<RLM>-34" shows "1234-") and now merges with "12-34" - two
# real ids differing only so is far rarer than a stray mark (customer_identity
# explains why the split is the harmful side). The overrides, embeddings and
# isolates stay: they CAN reorder ("<RLO>1C" shows "C1", 2E-g review cycle 3
# F7), though a wrapper around text that renders alike or a stray terminator
# does not - such a value still splits (2E-i review cycle 3 #1, for Thach).
_MARKS = re.compile("[" + chr(0x200E) + chr(0x200F) + chr(0x061C) + "]")
# Inside a value, the only whitespace kind read as a plain space: a no-break
# space looks like one (review31 f2: "Home Garden" and "Home<NBSP>Garden").
# Not Python's \s: it holds control characters (a Windows-1252 ellipsis read
# as latin-1 is U+0085), the wider ideographic space and the Ogham space mark
# (2E-i review cycle 1 #3). At the ENDS every whitespace character is trimmed
# (`str.strip`), as a cell of only whitespace is blank.
_NO_BREAK_SPACE = chr(0x00A0)
# Format characters (category Cf) that DRAW a sign - the prepended
# concatenation marks (the Arabic number and end-of-ayah signs, the Syriac
# abbreviation mark, the Kaithi number signs) - so a cell of one is not blank
# (2E-i review cycle 2 #3).
_VISIBLE_FORMAT = frozenset(chr(code) for code in (
    0x0600, 0x0601, 0x0602, 0x0603, 0x0604, 0x0605, 0x06DD, 0x070F, 0x0890, 0x0891, 0x08E2,
    0x110BD, 0x110CD))


def _as_text(values: pd.Series) -> pd.Series:
    """Every present cell as text - a number reads as its digits - and
    missing as NaN, object dtype: `.str` on an Int64 or float column raised or
    read a number as missing."""
    return values.astype(str).where(values.notna()).astype(object)


def _read_once(values: pd.Series, read) -> pd.Series:
    """`read` applied to each distinct value once: a column of a million
    cells holds a few thousand values (shared/line_classes.text_identity's
    reason, 2E-d2)."""
    codes, uniques = pd.factorize(_as_text(values))
    if len(uniques) == 0:
        return pd.Series(np.nan, index=values.index, dtype=object)
    read_values = read(pd.Series(uniques, dtype=object)).to_numpy(dtype=object)
    return pd.Series(np.where(codes >= 0, read_values[codes], np.nan), index=values.index, dtype=object)


def _renders_nothing(char: str) -> bool:
    return (char.isspace() or _INVISIBLE.match(char) is not None
            or (unicodedata.category(char) == "Cf" and char not in _VISIBLE_FORMAT)
            # Variation selectors 17-256: category Mn, drawn as nothing (cycle 2 #3).
            or 0xE0100 <= ord(char) <= 0xE01EF)


def _shows_nothing(text: str) -> bool:
    """Only whitespace, format characters that draw nothing (a joiner, a
    direction control, a tag - Unicode category Cf, less `_VISIBLE_FORMAT`)
    or the products' invisible characters (a variation selector, a filler,
    the braille blank): a cell of any of them renders as nothing. A lone
    joiner was a customer and an order id (2E-i review cycle 1 #2)."""
    return all(_renders_nothing(char) for char in text)


def is_blank(values: pd.Series) -> pd.Series:
    """True where a cell is missing or shows nothing (`_shows_nothing`) - one
    reading for every column (Thach, 2E-i). Stage 1's drop_rows_missing reads
    the same: it kept a name of only a zero-width space, and stage 2 read the
    line as the "(no product name)" gap the user had asked to drop (2E-g
    review cycle 3 F5)."""
    return _read_once(values, lambda text: text.map(_shows_nothing)).fillna(True).astype(bool)


def _identifier(text: str) -> str:
    # Removed BEFORE composing: "Jose<ZWSP><acute>" composed first stayed
    # decomposed (2E-i review cycle 1 #6).
    text = _MARKS.sub("", _NOTHING.sub("", text))
    return unicodedata.normalize("NFC", text).replace(_NO_BREAK_SPACE, " ").strip()


def identifier_text(values: pd.Series) -> pd.Series:
    """A value as a reader tells it apart (Thach, 2E-i): `_NOTHING` and the
    direction marks (`_MARKS`) removed, composed (NFC - canonically equivalent text renders alike), a no-break
    space a plain space, trimmed. Case and runs of spaces are left to the
    reader. A cell with nothing left reads "" - `is_blank` says whether it is
    missing - and a missing one NaN."""
    return _read_once(values, lambda text: text.map(_identifier))


def category_text(values: pd.Series) -> pd.Series:
    """A category as it is shown: `identifier_text` with runs of spaces as
    one - a label, as a product name is (2E-g); "Home  Garden" and
    "Home Garden" were two categories, one collapsing and one appearing."""
    return identifier_text(values).str.replace(r" {2,}", " ", regex=True)


def category_key(values: pd.Series) -> pd.Series:
    """The key two stages group categories by: `category_text` in lower case
    (not case-folded, as customers - 3C2), so stage 2 and stage 3 cannot split
    one category differently (2E-g review cycle 2 F1)."""
    return category_text(values).str.lower()


def customer_identity(values: pd.Series) -> pd.Series:
    """The key that decides whether two rows are the same customer.

    Stripped and lower-cased, so "CUST_01", " cust_01" and "Cust_01 " are one
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
    error direction is the safe one. Since 2E-i it reads `identifier_text`,
    which merges what a reader cannot see (a trailing zero-width space made
    one customer a lapsed and a new one), and lower case, not case folding
    ("Weiss" and "Weiss" with a sharp s stay two people).
    """
    return identifier_text(values).str.lower()


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
    "name:" + a float series does not add (the empty-file case crashed).
    Invisible characters go BEFORE composing, and a name that shows nothing
    (`_shows_nothing`: a lone joiner too) is NaN, as `is_blank` reads it
    (a text holding a NUL can compare wrongly in pandas' factorize - stage 1's
    CSV reader already cuts a cell at a NUL; 2E-i review cycle 3 #2)
    (2E-i review cycle 1 #2, #6)."""
    text = (values.astype(object).str.replace(_INVISIBLE, "", regex=True).str.normalize("NFC")
            .str.replace(r"\s+", " ", regex=True).str.strip())
    # Judged once per distinct value: per cell it cost ~0.5 s a call on
    # Online Retail II's million lines (2E-i review cycle 2 #5).
    codes, uniques = pd.factorize(text)
    shown = np.array([isinstance(value, str) and not _shows_nothing(value) for value in uniques], dtype=bool)
    visible = np.where(codes >= 0, shown[codes] if len(shown) else False, False)
    return text.where(pd.Series(visible, index=text.index)).astype(object)
