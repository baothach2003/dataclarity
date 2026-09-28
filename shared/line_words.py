"""Lines that may not be products (Thach, session 2E-d2): postage, fees,
commissions, bank charges, discounts and accounting adjustments that a POS
export books as product lines - DOTCOM POSTAGE was Online Retail II's top
"product" of 2011-11. Stage 1 PROPOSES them, measured on the raw file by
pandas (the AI's 30-row sample cannot see a file's codes); the user classes
each in Review, and a suggestion never applies by itself. In shared/ since
2E-t2: the line taxonomy's classifier reads the same candidates as each
line's pending suggestion, in stage 1 and for a frame without stage 1's
columns.

A product key (shared/line_classes.py: the SKU, else the name) is asked about
when its SKU text, or the name its lines carry most often, has a class word as
its FIRST or LAST word - measured on Online Retail II, "carriage" inside a name
was four real products (FRENCH CARRIAGE LANTERN, BAROQUE CARRIAGE CLOCK), and
every verified code keeps its word at an end. Only letters bound a word (as
2E-k's placeholder words), so "COFFEE" holds no "fee" and "ADJUSTABLE" no
"adjust". A key whose counted lines move no money is not asked: classed or
not, it changes no money figure - though its zero-amount lines are still a
product to stage 3's members (a "FREE DELIVERY" 1 @ 0 line can be listed as a
new product; review cycle 2 #4, recorded for Phase 8). No number is tuned.
"""

import re

import numpy as np
import pandas as pd

from contracts.profile import LineClass, NonProductCandidate
from shared.line_classes import keyed, text_identity
from shared.line_numbers import RequiredColumnMissingError, undated_lines

_LETTER = r"[^\W\d_]"
# First match wins, in this order: "Adjust bad debt" is an adjustment, and
# "Shipping fee" a charge the customer paid. The type keeps None for a word
# that would fit no class; none does since 2E-l.
CLASS_WORDS: tuple[tuple[LineClass | None, tuple[str, ...]], ...] = (
    ("adjustment", ("adjust", "adjustment", "bad debt", r"write[\s-]?off", "written off",
                    "điều chỉnh", "dieu chinh")),
    # Thach, 2E-l: M "Manual" is manually priced sales and their refunds, many
    # unnamed items under one code - not an adjustment. "Manual adjustment"
    # still reads as one (the class order).
    ("pooled", ("manual",)),
    ("discount", ("discount", "coupon", "giảm giá", "giam gia", "chiết khấu",
                  "chiet khau")),
    # Thach, 2E-t1 (the line taxonomy's decision 4): a voucher sold is a
    # liability until redeemed. After the discount words, so "Discount
    # voucher" is a discount; no bare "voucher" ("Promo voucher"), and no bare
    # "gift" ("GIFT BAG") - review 5 #12. "gift_": Online Retail II's
    # gift_0001_10 to _90, whose names end in a price.
    ("gift_card", ("gift card", "gift voucher", "gift certificate", "gift_")),
    ("charge", ("postage", "shipping", "delivery", "carriage", "freight", r"p\s?&\s?p",
                "phí vận chuyển", "phi van chuyen", "phí ship", "phi ship")),
    # Not the Vietnamese "hoa hồng" (commission): it is also roses, and a
    # flower shop's "Hoa hồng đỏ" read as a fee to leave revenue (review F7).
    # "sample": Thach, 2E-l - samples given away are a marketing cost.
    ("cost", ("fee", "bank charge", "commission", "sample")),
)
_AT_AN_END = [(line_class, re.compile(rf"^(?:{'|'.join(words)})s?(?!{_LETTER})"),
               re.compile(rf"(?<!{_LETTER})(?:{'|'.join(words)})s?$"))
              for line_class, words in CLASS_WORDS]
# Any class word at either end, in one pattern: whether `class_word` finds
# anything, over a column at once. One regex per key and class made a 50 MB
# file of unique codes take 29 s (2E-t1 review cycle 1 #4).
_ALL_WORDS = "|".join(word for _, words in CLASS_WORDS for word in words)
_ANY_AT_AN_END = re.compile(rf"^(?:{_ALL_WORDS})s?(?!{_LETTER})|(?<!{_LETTER})(?:{_ALL_WORDS})s?$")


def class_word(text: str) -> tuple[LineClass | None, str] | None:
    """The class a product text suggests and the word found at its start or
    end; None when no class word is there. `text` is read and case-folded
    as a product key is (shared/line_classes.text_identity)."""
    for line_class, first, last in _AT_AN_END:
        found = first.search(text) or last.search(text)
        if found:
            return line_class, found.group(0)
    return None


def non_product_candidates(df: pd.DataFrame, column_mapping: dict[str, str]
                           ) -> list[NonProductCandidate] | None:
    """The candidates, the commonest key first. [] with no product column;
    None when not measured - quantity or price not mapped, or no line counts
    before the plan's cleaning - so Review reads the profile instead."""
    # The candidates read no row's label, and lines are picked by label below:
    # a frame put together from others (repeated labels) broke the picking
    # (2E-t2).
    df = df.reset_index(drop=True)
    reverse = {field: source for source, field in column_mapping.items()}
    name_col, sku_col = reverse.get("product_name"), reverse.get("sku")
    if name_col is None and sku_col is None:
        return []
    try:
        lines_read = undated_lines(df, column_mapping)
    except RequiredColumnMissingError:
        return None
    if not lines_read.counted.any():
        return None
    names, skus = text_identity(df, name_col), text_identity(df, sku_col)
    frame = pd.DataFrame({
        "key": keyed(names, skus),
        "name": _raw(df, name_col).where(names.notna()),
        "sku": _raw(df, sku_col).where(skus.notna()),
    }).dropna(subset=["key"])
    # A candidate's SKU text or commonest name has a class word, so one of its
    # lines does: only those keys are read further - over a 50 MB file of
    # unique codes, every key's commonest name took most of 16 s (2E-t1
    # review cycle 1 #4).
    worded_line = _worded(frame["key"].str.split(":", n=1).str[1]) | _worded(names[frame.index])
    frame = frame[frame["key"].isin(set(frame["key"][worded_line]))]
    commonest_name = _commonest(frame, "name")
    # Each commonest name read as a key reads it, in one pass (5,131 keys on
    # Online Retail II).
    name_text = text_identity(commonest_name.to_frame("name"), "name")
    keys = pd.Series(frame["key"].unique(), dtype=object)
    texts = keys.str.split(":", n=1).str[1]
    names_read = keys.map(name_text).astype(object)
    # Only the keys with a class word somewhere are read word by word.
    worded = texts.str.contains(_ANY_AT_AN_END) | names_read.fillna("").str.contains(_ANY_AT_AN_END)
    found = []
    # Plain dicts, the same result as Series lookups (checked on the demo
    # files and fuzzed frames). They did not fix the speed of a 50 MB file
    # whose every line is a worded key of its own (2E-t1 review cycle 3 #1):
    # its time is in reading the texts and the commonest names (2E-v #5, 8D).
    commonest = commonest_name.to_dict()
    for key, text, name_read in zip(keys[worded], texts[worded], names_read[worded], strict=True):
        name = commonest.get(key)
        hit = class_word(text) or (class_word(name_read) if name is not None else None)
        if hit is not None:
            found.append((key, key.split(":", 1)[0], name, *hit))
    return _measured(found, frame, lines_read)


def _worded(texts: pd.Series) -> np.ndarray:
    """Whether each text has a class word at an end, read once per distinct
    text (a file repeats its codes and names); False for a missing one."""
    codes, uniques = pd.factorize(texts)
    if len(uniques) == 0:
        return np.zeros(len(texts), dtype=bool)
    found = pd.Series(uniques, dtype=object).str.contains(_ANY_AT_AN_END).to_numpy(dtype=bool)
    return np.where(codes >= 0, found[codes], False)


def _measured(found: list[tuple], frame: pd.DataFrame, lines_read) -> list[NonProductCandidate]:
    # An amount that overflows (1e200 x 1e200) is no money a reader can sum:
    # it crashed the schema step (2E-d2 doubt-review F5).
    measurable = lines_read.counted & np.isfinite(lines_read.amounts)
    counted = frame.index[measurable[frame.index]]
    # One grouping pass: a scan of every line per candidate took 56 s with
    # 2,000 candidates over 1,000,000 lines (2E-d2 doubt-review F6).
    table = pd.DataFrame({"key": frame.loc[counted, "key"], "amount": lines_read.amounts[counted]})
    table = table[table["key"].isin({key for key, *_ in found})]
    by_key = table.groupby("key")["amount"]
    lines = by_key.size().to_dict()
    positive = table["amount"].clip(lower=0).groupby(table["key"]).sum().to_dict()
    negative = table["amount"].clip(upper=0).groupby(table["key"]).sum().to_dict()
    spelled = {"sku": _commonest(frame, "sku").to_dict(), "product_name": _commonest(frame, "name").to_dict()}
    candidates = []
    for key, field, name, line_class, word in found:
        up, down = float(positive.get(key, 0.0)), float(negative.get(key, 0.0))
        # Finite lines can still sum past a float (two 1e154 x 1e154): no
        # money a reader can be shown, and it crashed the schema step (cycle 3 F5).
        if (up == 0 and down == 0) or not (np.isfinite(up) and np.isfinite(down)):
            continue
        field_name = "sku" if field == "sku" else "product_name"
        candidates.append(NonProductCandidate(
            value=str(spelled[field_name][key]), field=field_name, name=name, lines=int(lines[key]),
            positive=up, negative=down, suggested=line_class, word=word))
    return sorted(candidates, key=lambda c: (-c.lines, c.value))


def _commonest(frame: pd.DataFrame, column: str) -> pd.Series:
    """Per key, the value of `column` its lines carry most often, as written.
    A tie goes to a value with a class word - a false question costs one
    answer - then to the first in order of text: by row order, whether a key
    was asked depended on which line came first (cycle 3 F6)."""
    pairs = frame[["key", column]].dropna()
    if pairs.empty:
        return pd.Series(dtype=object)
    counted = pairs.value_counts().reset_index()
    read = text_identity(counted, column)
    counted["worded"] = read.fillna("").str.contains(_ANY_AT_AN_END).to_numpy()
    counted = counted.sort_values(["key", "count", "worded", column], ascending=[True, False, False, True])
    return counted.drop_duplicates("key").set_index("key")[column]


def _raw(df: pd.DataFrame, column: str | None) -> pd.Series:
    if column is None:
        return pd.Series(None, index=df.index, dtype=object)
    return df[column].astype(object).map(lambda value: value if isinstance(value, str) else
                                         (None if pd.isna(value) else str(value)))
