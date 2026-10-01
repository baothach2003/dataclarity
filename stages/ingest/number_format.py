"""How a number written for people is read: decided at stage 1 (Thach,
2026-10-02, 2E-u F1; session 2E-u1), as 2E-j decided the date order.

"1,000" is one thousand or one, and nothing in the cell says which. Read by
pd.to_numeric, as every stage read it until 2E-u1, "1,000.00", "$10.00" and
"10,5" were no number at all: one product priced with a thousands separator
silently left revenue that product short, and a file priced so throughout
blocked saying the export was cut short (2E-u). So stage 1 decides, on the
RAW file, per numeric column: the cells that PROVE the format ("1,000.00" -
the last mark is the decimal one; "10,5" - a mark not followed by a group of
three is a decimal mark), else the user's answer in Review; unanswered and
unproven, the plan does not run. Never a default either way. Readable cells
are then rewritten as plain numbers before the plan runs, so the plan's own
steps and stages 2-3 read them as numbers.

The method, fixed before this code: C:/Users/Happy/2E-u1-method.txt (N2-N6).
"""

import re
import unicodedata
from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd

from contracts.profile import NumberFormat, NumberFormatMeasure, ProfileContract
from stages.ingest.ai_input import MAX_VALUE_CHARS, TRUNCATION_MARK
Shape = Literal["plain", "point", "comma", "ambiguous"]

# Grouping only: a space, a no-break space (U+00A0), a narrow no-break space
# (U+202F) or an apostrophe between groups of three digits.
_GROUPERS = " \u00a0\u202f'"
_BODY = re.compile(r"^(\d*)([.,\d" + _GROUPERS + r"]*)$")


@dataclass(frozen=True)
class CellReading:
    """A cell's shape and what it is read as under each format (None: that
    format cannot read it). The texts are the plain numbers written back."""

    shape: Shape
    point_text: str | None
    comma_text: str | None

    @property
    def as_point(self) -> float | None:
        return None if self.point_text is None else float(self.point_text)

    @property
    def as_comma(self) -> float | None:
        return None if self.comma_text is None else float(self.comma_text)

    def text(self, number_format: NumberFormat) -> str | None:
        return self.point_text if number_format == "decimal_point" else self.comma_text


def _strip_currency(text: str) -> tuple[str, bool]:
    """Currency symbols (Unicode category Sc) at either end, with or without
    a space; whether any was there."""
    found = False
    while text and unicodedata.category(text[0]) == "Sc":
        text, found = text[1:].lstrip(), True
    while text and unicodedata.category(text[-1]) == "Sc":
        text, found = text[:-1].rstrip(), True
    return text, found


def _sign(text: str) -> tuple[str, str] | None:
    """A leading plus or minus, or a trailing minus (at most one); None for
    two. A plus is no sign of its own: "+2.500" is read like "2.500" - left
    unread it was in no count and stage 2 read it with a decimal point
    whatever the column proved (2E-u1 review 2, N1)."""
    sign = ""
    if text.startswith("+"):
        # A second sign after it is left in the body, which reads no sign.
        return "", text[1:]
    if text.startswith("-"):
        sign, text = "-", text[1:]
    if text.endswith("-"):
        if sign:
            return None
        sign, text = "-", text[:-1]
    return sign, text


def _digits(text: str) -> bool:
    """ASCII digits only: pandas reads no other (2E-u1 review 1, F9)."""
    return bool(text) and all("0" <= c <= "9" for c in text)


def _grouped(integer: str, mark: str) -> str | None:
    """The integer part without its grouping mark, or None when the groups
    are not of three - the first one to three digits, and not a leading 0:
    nobody writes 500 as "0,500", so "0,500" can only be a decimal (2E-u1
    review 1, F2: read as a group it rewrote 0.5 as 500)."""
    if mark == "":
        return integer if _digits(integer) or integer == "" else None
    parts = integer.split(mark)
    if not parts[0] or len(parts[0]) > 3 or parts[0].startswith("0") or not all(len(p) == 3 for p in parts[1:]):
        return None
    joined = "".join(parts)
    return joined if _digits(joined) else None


def _read(body: str, decimal: str, grouping: tuple[str, ...]) -> str | None:
    """`body` read with `decimal` as the decimal mark and any of `grouping`
    as thousands marks (one kind per cell), as a plain number text."""
    if body.count(decimal) > 1:
        return None
    integer, _, fraction = body.partition(decimal)
    if decimal in body and (not _digits(fraction)):
        return None
    marks = {c for c in integer if not "0" <= c <= "9"}
    if len(marks) > 1 or (marks and next(iter(marks)) not in grouping):
        return None
    digits = _grouped(integer, next(iter(marks)) if marks else "")
    if digits is None or (digits == "" and decimal not in body):
        return None
    return (digits or "0") + ("." + fraction if decimal in body else "")


# A quoted cell keeps its line breaks, and pandas reads past them (review 3,
# R3-3: "2.500" and a carriage return was read by no rule and counted nowhere).
_SPACES = " \t\r\n\u00a0\u202f"


def _parts(cell: str) -> tuple[str, str, bool] | None:
    """(sign, body, whether a currency symbol was there): the symbol stripped
    at either end, the sign inside or outside it ("$-5", "-$5", "5-")."""
    text, outer = _strip_currency(cell.strip(_SPACES))
    signed = _sign(text.strip(_SPACES))
    if signed is None:
        return None
    body, inner = _strip_currency(signed[1].strip(_SPACES))
    return signed[0], body.strip(_SPACES), outer or inner


def read_cell(cell: object) -> CellReading | None:
    """The method's N2. None when no rule reads the cell: it stays as written
    (stage 2 lists it as unmeasurable, as before)."""
    parts = _parts(cell) if isinstance(cell, str) else None
    if parts is None:
        return None
    sign, body, _ = parts
    if not body or not _BODY.match(body) or not any("0" <= c <= "9" for c in body):
        return None
    point = _read(body, ".", (",", *_GROUPERS))
    comma = _read(body, ",", (".", *_GROUPERS))
    if point is None and comma is None:
        return None
    point = None if point is None else sign + point
    comma = None if comma is None else sign + comma
    if point is not None and comma is not None:
        shape: Shape = "plain" if float(point) == float(comma) else "ambiguous"
    else:
        shape = "point" if point is not None else "comma"
    return CellReading(shape, point, comma)


def has_currency(cell: object) -> bool:
    parts = _parts(cell) if isinstance(cell, str) else None
    return parts is not None and parts[2]


@dataclass(frozen=True)
class FormatEvidence:
    """What a column's cells say about their number format (N3); counts of
    cells, not of distinct values."""

    readable: int
    point: int  # cells only a decimal point reads
    comma: int  # cells only a decimal comma reads
    ambiguous: int  # cells both read, as different numbers ("1,000")
    signed_currency: int  # readable cells that carried a currency symbol
    point_example: str | None
    comma_example: str | None
    ambiguous_example: str | None
    unreadable: int  # non-blank cells no rule reads (left as written)
    unreadable_example: str | None

    @property
    def decision(self) -> NumberFormat | Literal["ask"] | None:
        """The format the column proves for its ambiguous cells; "ask" when
        some cell reads two ways and the column proves neither format, or
        both; None when no cell depends on it. A cell that proves its own
        format is read by its proof whatever the column says - the user's
        word decides only what the file cannot."""
        if self.point and not self.comma:
            return "decimal_point"
        if self.comma and not self.point:
            return "decimal_comma"
        return "ask" if self.ambiguous else None


# What `read_cell` reads as "plain" with no reading needed: a sign, ASCII
# digits, spaces around (read_cell strips them). The space characters
# themselves, not escapes: pyarrow's regex engine reads no "\u".
_WHOLE_NUMBER = f"[{_SPACES}]*[+-]?[0-9]+[{_SPACES}]*"


def _cut(text: str) -> str:
    """An example no longer than a cell text the AI is shown (review 2, N8:
    a 400-digit cell was copied whole), after its spaces (review 3, R3-7)."""
    text = text.strip(_SPACES)
    return text if len(text) <= MAX_VALUE_CHARS else text[: MAX_VALUE_CHARS - len(TRUNCATION_MARK)] + TRUNCATION_MARK


def format_evidence(values: pd.Series) -> FormatEvidence:
    return format_evidence_of_counts(values.dropna().astype("str").value_counts(sort=False))


def format_evidence_of_counts(counts: pd.Series) -> FormatEvidence:
    """`counts`: each distinct cell text and how many cells hold it (the
    profile has it already). Read per distinct value: a million rows of a few
    thousand prices cost a few thousand readings."""
    tally = {"plain": 0, "point": 0, "comma": 0, "ambiguous": 0}
    examples: dict[str, str] = {}
    currency = unreadable = 0
    unreadable_example = None
    texts = pd.Series(counts.index.astype(str), index=counts.index)
    # Only a cell of digits, separators, signs and symbols can be a number:
    # a column of product names costs one vectorised pass, not a reading per
    # value (2E-u1 review 1, F4: profiling +5 s on a 41 MB worst case).
    candidate = texts.str.contains(r"[0-9]", regex=True) & ~texts.str.contains(r"[A-Za-z]", regex=True)
    # A whole number of ASCII digits is plain whatever the format: counted in
    # one pass, never read cell by cell (review 2, N4). What is left is read
    # one distinct value at a time: a column of 500,000 distinct "1,234.56"
    # prices still costs seconds (a known limit, PROJECT_PLAN Phase 9).
    whole = texts.str.fullmatch(_WHOLE_NUMBER)
    tally["plain"] += int(counts[whole].sum())
    blank = texts.str.strip().eq("").to_numpy(dtype=bool)
    # "Unreadable" is what stage 2 cannot read either: "1e3" is left as
    # written and pandas reads it (review 1, F6). A cell with no digit or
    # with a letter no rule reads: judged in one pass, never one by one -
    # an id column of 600,000 codes cost seconds (review 3, R3-2).
    pandas_reads = pd.to_numeric(texts, errors="coerce").notna().to_numpy(dtype=bool)
    rest = ~whole.to_numpy(dtype=bool) & ~blank
    maybe = candidate.to_numpy(dtype=bool)
    unread = rest & ~maybe & ~pandas_reads
    values, totals = texts.to_numpy(dtype=object), counts.to_numpy()
    for position in np.flatnonzero(rest & maybe):
        text, count = values[position], int(totals[position])
        reading = read_cell(text)
        if reading is None:
            unread[position] = not pandas_reads[position]
            continue
        tally[reading.shape] += count
        examples.setdefault(reading.shape, _cut(text))
        currency += count if has_currency(text) else 0
    if unread.any():
        unreadable, unreadable_example = int(totals[unread].sum()), _cut(values[np.flatnonzero(unread)[0]])
    return FormatEvidence(
        readable=sum(tally.values()), point=tally["point"], comma=tally["comma"],
        ambiguous=tally["ambiguous"], signed_currency=currency,
        point_example=examples.get("point"), comma_example=examples.get("comma"),
        ambiguous_example=examples.get("ambiguous"), unreadable=unreadable,
        unreadable_example=unreadable_example)


def proven_formats(profile: ProfileContract) -> dict[str, NumberFormat]:
    """The decimal mark each column's cells prove over the whole raw file, by
    source column - profile.json's measure. The preview reads its sample by
    it, as execution reads the whole file (review 3, R3-1)."""
    return {column.name: column.number_format.decision for column in profile.columns
            if column.number_format is not None and column.number_format.decision in ("decimal_point", "decimal_comma")}


def format_measure(counts: pd.Series, *, numeric: bool = False) -> NumberFormatMeasure | None:
    """profile.json's measure of a column (2E-u1), for Review; None when
    no cell reads as a number written for people (a separator, a decimal
    comma or a currency symbol) - nothing to show."""
    evidence = format_evidence_of_counts(counts)
    if not (evidence.point or evidence.comma or evidence.ambiguous or evidence.signed_currency):
        return None
    # A column pandas reads as numbers ("1.000", "2.500" - three decimals
    # throughout) is measured only when it holds a question: execution asks
    # it all the same, and Review had none to show (review 1, F1). An
    # ordinary price column ("9.99") shows nothing.
    if numeric and evidence.decision != "ask":
        return None
    return NumberFormatMeasure(
        readable=evidence.readable, point=evidence.point, comma=evidence.comma, ambiguous=evidence.ambiguous,
        currency=evidence.signed_currency, unreadable=evidence.unreadable,
        point_example=evidence.point_example, comma_example=evidence.comma_example,
        ambiguous_example=evidence.ambiguous_example, decision=evidence.decision)
