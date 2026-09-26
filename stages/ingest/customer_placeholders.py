"""Walk-in placeholders (Thach, session 2E-k): customer values that may stand
for the customers a shop did not record - "Guest", "Walk-in", "0", "Khach
le". Stage 1 measures them on the raw file, never the AI; Review asks the
user about each, and a Yes makes those lines unattributed in stages 2 and 3
(shared/transactions.py). A false question only costs the user one answer
(Thach), so every rule below errs towards asking.

A value is a candidate when
- it reads as a placeholder word (`is_placeholder_word`), at any share; or
- it carries PLACEHOLDER_SHARE or more of the counted lines or of the sale
  revenue; or
- it is the largest value by lines or by sale revenue, among the values not
  already asked, and carries PLACEHOLDER_RATIO times the next one - taken
  again after each value it finds (2E-r F1) - Thach's "unusual share": a
  placeholder at 7% of the lines, off the word list, read as the top
  customer at 15 times the next one (doubt-review cycle 2 F1).
Measured before choosing (scratchpad 2ek/measure_shares.out): the largest
real customer carries 4.4% of lines or revenue on either demo file, and 1.01
to 1.15 times the next one; Online Retail II's walk-ins - left blank by its
export - are 22.8% of its lines, 18.5 times its largest customer. 10% and 4
sit in those gaps, on the asking side.
"""

import re
import unicodedata

import numpy as np
import pandas as pd

from contracts.profile import CustomerPlaceholder
from shared.transactions import RequiredColumnMissingError, customer_identity, is_blank
from stages.ingest.line_reading import undated_lines

PLACEHOLDER_SHARE = 0.10
PLACEHOLDER_RATIO = 4
# Words POS systems write for an unrecorded customer, found inside the
# customer identity (stripped, case-folded): "Guest Customer", "Cash Sale",
# "Walk-In Client", and the defaults of other languages - "Khach le", "Khach
# hang le", "Khach vang lai" (Vietnamese), "Consumidor Final", "Cliente
# final", "Publico en General", "Laufkunde", "Barverkauf", "Client divers",
# "Pelanggan Umum", the Chinese default (cycle 1 F6, cycle 2 F1, cycle 3 F3).
# Only a LETTER before or after makes it part of another word - the surname
# "Walker", "Cashmere Ltd", "Miscellaneous Ltd" (cycle 2 F4) - so plurals,
# digits and underscores still match: "Walk-ins", "GUEST01", "Walk_In".
_LETTER = r"[^\W\d_]"
# Words written apart may be joined by a space, an underscore, a hyphen or
# several ("Retail_Customer", "No-Customer", "Walk - In"), and a compound may
# be written as one word ("walkin"): 2E-r F2.
_JOIN = r"[\s_-]+"
_JOINED = r"[\s_-]*"
_WORDS = (
    "guest", f"walk{_JOINED}in", "cash", "anonymous", "unknown", "none", "null", "blank", "default",
    f"one{_JOINED}time", f"retail{_JOIN}customer", "counter", f"no{_JOIN}customer", "misc",
    f"non{_JOINED}member", "unregistered", "laufkunden?", "barverkauf", "diverse?",
    f"consumidor{_JOIN}final", f"cliente{_JOIN}(?:final|contado)", f"p[uú]blico{_JOIN}en{_JOIN}general",
    f"pelanggan{_JOIN}umum", f"kh[aá]ch{_JOIN}(?:h[aà]ng{_JOIN})?l[eẻ]", f"kh[aá]ch{_JOIN}v[aã]ng{_JOIN}lai",
)
PLACEHOLDER_WORDS = re.compile(rf"(?<!{_LETTER})(?:{'|'.join(_WORDS)})s?(?!{_LETTER})")
# Chinese writes no space between words, so the default reads inside a longer
# name too ("门店散客", "散客户"; 2E-r F2).
_UNSPACED = re.compile("散客")
_NOT_APPLICABLE = re.compile(r"#?n\s*[./]?\s*a\.?")


def is_placeholder_word(identity: str) -> bool:
    """A customer identity that reads as a placeholder: a word above, the
    word "customer" alone, "n.a.", no letter or digit at all ("-", "?"), or
    a number at or below zero ("0", "0.0", "0000", "-1": float-style id
    exports and dummy ids). Read composed (NFC): a decomposed "Khach le" was
    missed (2E-r F2)."""
    identity = unicodedata.normalize("NFC", identity)
    if not any(character.isalnum() for character in identity):
        return True
    try:
        if float(identity) <= 0:
            return True
    except ValueError:
        pass
    return (identity == "customer" or _NOT_APPLICABLE.fullmatch(identity) is not None
            or PLACEHOLDER_WORDS.search(identity) is not None or _UNSPACED.search(identity) is not None)


def placeholder_candidates(df: pd.DataFrame, column_mapping: dict[str, str]
                           ) -> list[CustomerPlaceholder] | None:
    """The customer values Review asks about, commonest first, over the
    counted lines of the raw file (a stock-in line is no customer's, and
    blank customers stay in the share's denominator; no date is read). None:
    not measured - quantity or price is not mapped, or no line parses before
    the plan's cleaning - so Review reads the profile instead (cycle 1 F4)."""
    reverse = {field: source for source, field in column_mapping.items()}
    if "customer" not in reverse:
        return []
    try:
        lines_read = undated_lines(df, column_mapping)
    except RequiredColumnMissingError:
        return None
    counted = lines_read.counted
    total_lines = int(counted.sum())
    if total_lines == 0:
        return None
    raw = df[reverse["customer"]].astype(object)
    identity = customer_identity(raw).where(~is_blank(raw))[counted]
    lines = identity.value_counts()
    sale_revenue = lines_read.amounts.where(lines_read.sale, 0.0)[counted]
    # Finite amounts can still sum past a float: no share can be read from
    # that total (two customers each showed 100%, 2E-r F6) - an overflow this
    # code expects and handles, so numpy need not warn about it.
    with np.errstate(over="ignore"):
        total_revenue = float(sale_revenue.sum())
    measurable = 0 < total_revenue < float("inf")
    revenue = sale_revenue.groupby(identity).sum().sort_values(ascending=False)
    measured = []
    for value, count in lines.items():
        # Capped: the two revenue sums add the same numbers in another order,
        # and one customer on every line read 100.00000000000003% (cycle 1 F2).
        revenue_pct = (min(100.0, 100 * float(revenue.get(value, 0.0)) / total_revenue)
                       if measurable else None)
        lines_pct = 100 * int(count) / total_lines
        word = is_placeholder_word(str(value))
        share = (lines_pct >= 100 * PLACEHOLDER_SHARE
                 or (revenue_pct is not None and revenue_pct >= 100 * PLACEHOLDER_SHARE))
        measured.append((value, int(count), lines_pct, revenue_pct, word, share))
    # The largest of the values NOT already asked about: a first placeholder
    # shielded a second one from the ratio (2E-k cycle 3 F1) - and taken again
    # after each value the ratio finds, or that value shielded the next: an
    # off-list "99999" hid "88888" at 25 times any real customer (2E-r F1).
    asked = {value for value, _, _, _, word, share in measured if word or share}
    unusual: set = set()
    for totals in (lines, revenue) if measurable else (lines,):
        rest = totals.drop(list(asked | unusual), errors="ignore")
        while (top := _dominant(rest)) is not None:
            unusual.add(top)
            rest = rest.drop(top)
    found = [CustomerPlaceholder(value=value, lines=count, lines_pct=lines_pct, revenue_pct=revenue_pct,
                                 why="word" if word else "share")
             for value, count, lines_pct, revenue_pct, word, share in measured
             if word or share or value in unusual]
    # Each value as the file writes it most often, found in one pass over the
    # candidates' lines (a scan per candidate was quadratic, cycle 2 F4).
    if found:
        chosen = identity.isin([c.value for c in found])
        spelled = (pd.DataFrame({"id": identity[chosen], "raw": raw[counted][chosen]})
                   .value_counts().reset_index().drop_duplicates("id").set_index("id")["raw"])
        found = [c.model_copy(update={"value": str(spelled[c.value])}) for c in found]
    return found


def _dominant(totals: pd.Series) -> object | None:
    """The largest value, when it is PLACEHOLDER_RATIO times the next one."""
    if len(totals) < 2 or totals.iloc[1] <= 0:
        return None
    return totals.index[0] if totals.iloc[0] >= PLACEHOLDER_RATIO * totals.iloc[1] else None
