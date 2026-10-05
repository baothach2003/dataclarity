"""The file's currency, read by code on the RAW file at execute (the report
redesign's step 2; Thach D6, Q5-Q9, Q26-Q30; docs/REPORT_REDESIGN.md section
6, as built in its section 12; method C:/Users/Happy/redesign-step2b-method.txt).
No AI step (Q7b).

Thach's principle: reading a currency that is not there fabricates a label
or blocks a correct file; finding nothing only means Review asks. So only
STRONG evidence counts, from two places alone (Q26):
- the plan's money columns (mapped to unit_price): a currency sign on their
  cells or in their header ("£2.50", "Price (€)"), or an ISO code written in
  capitals in their header, in brackets or as its last word ("Price (AUD)",
  "Price AUD"; never ALL or TOP, never in an all-capitals header unless
  bracketed);
- a currency column (its header IS a currency's name, alone or with one word
  around it): blanks and "-", "none", "n/a" are empty; a cell that reads as a
  number or a date is unreadable (counted, Q29); two or more distinct values
  block (Q28); one value is evidence when it is an ISO code, else only a
  hint for Review ("Euro").
Nothing else is read: a SKU "TOP-001", a weight "2.5 kgs", a country. A bare
"$" or "¥" narrows (Q5, Q9); beside exactly one code of its family it is that
code (Q27: pre-selected, Review always asks). One block rule: two or more
distinct currencies among the evidence - never summed silently.

Each currency is counted by the LINES carrying it, a line once, linear in
the file."""

import re
import unicodedata
from collections.abc import Iterable

import numpy as np
import pandas as pd

from contracts.currency import (ISO_4217, MAX_LABEL, MAX_PARTS, NARROWING, NARROWING_FAMILY, CurrencyFinding,
                                CurrencyPart)
from shared.dates import as_dates
from stages.ingest.profiling import NA_TOKENS

# A sign that names one currency. "$" and "¥" narrow (contracts/currency); a
# sign not here is a currency of its own that names no code.
SYMBOL_CODES = {"£": "GBP", "€": "EUR", "₹": "INR", "₩": "KRW", "₫": "VND", "₺": "TRY", "₽": "RUB", "₴": "UAH",
                "₪": "ILS", "₱": "PHP", "฿": "THB", "₦": "NGN", "₸": "KZT", "₮": "MNT", "₲": "PYG", "₡": "CRC",
                "₵": "GHS", "₭": "LAK", "₼": "AZN", "₾": "GEL"}
# A cent is a part of a dollar, no currency of its own.
CENT = "¢"
_HAS_SIGN = "[" + re.escape("".join(chr(c) for c in range(0x20, 0x10000)
                                    if unicodedata.category(chr(c)) == "Sc")) + "]"
# A currency column's header, letters only and lower-cased: a name, alone or
# with one word around it. A header that only mentions one is none.
CURRENCY_NAMES = frozenset({"currency", "ccy", "curr", "cur", "devise", "moneda", "moeda", "divisa", "monnaie",
                            "waluta", "waehrung", "währung", "valuta", "valuuta", "tiente", "tiềntệ", "币种",
                            "货币", "通貨"})
NAME_BEFORE = ("", "transaction", "txn", "trans", "order", "invoice", "sale", "sales", "payment", "pay", "local",
               "original", "base", "billing", "settlement", "price", "iso")
NAME_AFTER = ("", "code", "iso", "isocode", "name", "symbol", "id", "type", "unit", "cd")
CURRENCY_HEADERS = frozenset(before + name + after for before in NAME_BEFORE for name in CURRENCY_NAMES
                             for after in NAME_AFTER)
# A currency column's cells that are empty, compared trimmed and upper-cased:
# Thach's "-", "none", "n/a" (Q28), the dash written long, and what stage 1
# reads as missing anywhere (profiling's NA tokens) - each one means "no
# value", never a currency.
PLACEHOLDERS = frozenset({"-", "NONE", "N/A", "\u2014", "\u2013"} | {token.upper() for token in NA_TOKENS})
# Characters a cell is trimmed of besides spaces: zero-width ones.
_INVISIBLE = "\u200b\u200c\u200d\u2060\ufeff"
# A cell that reads as a number: digits and separators only (Q29).
_NUMBER = re.compile(r"[\d\s.,:/'+\-()T]*\d[\d\s.,:/'+\-()T]*")
# ISO codes that are also words or units (all, top, cup, pen, Bob, mop, gel,
# kgs, a time zone): never read in a header - doubtful, so Review asks. A
# currency column still names them.
NEVER_IN_HEADER = frozenset({"ALL", "TOP", "CUP", "PEN", "BOB", "SOS", "MAD", "MOP", "GEL", "KGS", "WST"})
_LETTERS = re.compile(r"[^\W\d_]+")
_PRIORITY = {"column": 0, "symbol": 1, "header": 2}


def _split_case(run: str) -> list[str]:
    """"TotalEUR" -> Total, EUR; "WährungCode" -> Währung, Code. A script
    without case is one word."""
    parts, start = [], 0
    for index in range(1, len(run)):
        if run[index - 1].islower() and run[index].isupper():
            parts.append(run[start:index])
            start = index
    parts.append(run[start:])
    return parts


def _tokens(text: str) -> list[str]:
    return [part for run in _LETTERS.findall(text) for part in _split_case(run)]


def _names_a_currency(header: str) -> bool:
    return "".join(_LETTERS.findall(header.lower())) in CURRENCY_HEADERS


def _header_code(header: str) -> str | None:
    """The ISO code a money column's header states: the only code written in
    capitals in it, in brackets or as its last word in a header not written
    all in capitals. Anything else is doubtful: None."""
    tokens = _tokens(header)
    codes = {token for token in tokens if token.isupper() and token in ISO_4217}
    if len(codes) != 1 or len(tokens) < 2:
        return None
    (code,) = codes
    bracketed = {token for inner in re.findall(r"[(\[]([^)\]]*)[)\]]", header) for token in _tokens(inner)}
    last = tokens[-1] == code and header != header.upper()
    return code if code not in NEVER_IN_HEADER and (code in bracketed or last) else None


def _wide(char: str) -> str:
    # Only the full-width forms are read as their usual sign: NFKC on any other
    # sign can turn it into letters (the rupee sign into "Rs").
    return unicodedata.normalize("NFKC", char) if 0xFF00 <= ord(char) <= 0xFFEF else char


def _signs(text: str) -> set[str]:
    """The currency signs in a text, full width read as usual, the cent left out."""
    return {_wide(char) for char in text if unicodedata.category(char) == "Sc"} - {CENT}


def _sign_label(sign: str) -> str:
    return SYMBOL_CODES.get(sign, sign)


def _evidence(label: str, where: str) -> str:
    return f"{label}, {where}" if label in ISO_4217 else where


class _Evidence:
    """(line, label) rows, the best place each label was found, and a
    currency column's values - linear in the file."""

    def __init__(self) -> None:
        self.rows: list[pd.DataFrame] = []
        self.sources: dict[str, tuple[int, str, str]] = {}
        # Each currency column with a value: its header and (line, key) rows.
        self.columns: list[tuple[str, pd.DataFrame]] = []
        self.shown: dict[str, str] = {}
        self.unreadable = 0

    def add(self, lines: np.ndarray, labels: np.ndarray | str, source: str, where: dict[str, str]) -> None:
        self.rows.append(pd.DataFrame({"line": lines, "label": labels}))
        for label, text in where.items():
            best = (_PRIORITY[source], source, _evidence(label, text))
            if label not in self.sources or best < self.sources[label]:
                self.sources[label] = best


def _read_money(evidence: _Evidence, header: str, values: pd.Series) -> None:
    text = values.astype(str)
    present = values.notna().to_numpy()
    signed = text[present & text.str.contains(_HAS_SIGN, regex=True).to_numpy()]
    if len(signed):
        found = {cell: _signs(cell) for cell in signed.unique()}
        signs = signed.map(lambda cell: sorted(found[cell])).explode().dropna()
        labels = {sign: _sign_label(sign) for sign in signs.unique()}
        evidence.add(np.asarray(signs.index), signs.map(labels).to_numpy(), "symbol",
                     {label: f"from the {sign} in column {header}" for sign, label in labels.items()})
    stated = {_sign_label(sign) for sign in _signs(header)} | ({code} if (code := _header_code(header)) else set())
    for label in stated:
        evidence.add(np.flatnonzero(present), label, "header", {label: f"from the header {header}"})


def _unreadable(cells: pd.Series) -> pd.Series:
    """The cells that read as a number or a date (Q29): digits and separators,
    or a date as stage 1 reads one (shared.dates) with a digit in it - so a
    month's name alone is no date."""
    distinct = pd.Series(cells.unique(), dtype="object")
    digits = distinct[distinct.str.contains(r"\d", regex=True)]
    if digits.empty:
        return cells.isin(())
    read = set(digits[digits.str.fullmatch(_NUMBER) | as_dates(digits).notna()])
    return cells.isin(read)


def _read_currency_column(evidence: _Evidence, header: str, values: pd.Series) -> None:
    """A currency column's values (Q28, Q29), judged on its own: empty cells,
    a repeated header line, cells that read as a number or a date (counted),
    and the values, compared upper-cased."""
    cells = values.dropna().astype(str).map(lambda cell: unicodedata.normalize("NFC", cell.strip().strip(_INVISIBLE)))
    keys = cells.str.upper()
    filled = ~keys.isin(PLACEHOLDERS) & (keys != header.strip().upper())
    unreadable = filled & _unreadable(cells)
    named = filled & ~unreadable
    evidence.unreadable += int(unreadable.sum())
    if named.any():
        evidence.columns.append((header, pd.DataFrame({"line": np.asarray(cells.index[named]),
                                                        "key": keys[named].to_numpy()})))
        for key, shown in zip(keys[named], cells[named], strict=True):
            evidence.shown.setdefault(key, shown[:MAX_LABEL])


def _counted(rows: Iterable[pd.DataFrame], column: str) -> dict[str, int]:
    """Lines per label, a line once, in the order first found."""
    pairs = pd.concat(rows, ignore_index=True)
    counts = pairs.drop_duplicates()[column].value_counts()
    return {label: int(counts[label]) for label in dict.fromkeys(pairs[column])}


def _mixed(counts: dict[str, int], shown: dict[str, str] | None = None) -> CurrencyFinding:
    order = {label: index for index, label in enumerate(counts)}
    ranked = sorted(counts.items(), key=lambda item: (-item[1], order[item[0]]))
    return CurrencyFinding(kind="mixed", more_parts=max(len(ranked) - MAX_PARTS, 0), parts=[
        CurrencyPart(label=(shown or {}).get(label, label), lines=count)
        for label, count in ranked[:MAX_PARTS]])


def currency_finding(frame: pd.DataFrame, money_columns: Iterable[str]) -> CurrencyFinding:
    """The raw file's currency, from the plan's money columns and any
    currency column (execution; Review's question in step 5)."""
    frame = frame.reset_index(drop=True)
    money = set(money_columns)
    evidence = _Evidence()
    for name in frame.columns:
        header = unicodedata.normalize("NFC", str(name))
        if str(name) in money:
            _read_money(evidence, header, frame[name])
        elif _names_a_currency(header):
            _read_currency_column(evidence, header, frame[name])
    return _decided(evidence, _columns_read(evidence))


def _columns_read(evidence: _Evidence) -> str | CurrencyFinding | None:
    """The currency columns, each judged on its own (Q28): one of two or more
    values blocks; columns of one value each - one ISO code they agree on is
    evidence; codes that differ, or a value that is no code, are doubtful: a
    hint for Review, never evidence. Returns the block, or the hint."""
    for _, rows in evidence.columns:
        values = _counted([rows], "key")
        if len(values) >= 2:
            return _mixed(values, evidence.shown)
    singles = {rows["key"].iloc[0]: header for header, rows in evidence.columns}
    if len(singles) == 1 and next(iter(singles)) in ISO_4217:
        ((key, header),) = singles.items()
        lines = np.concatenate([rows["line"].to_numpy() for _, rows in evidence.columns])
        evidence.add(lines, key, "column", {key: f"from column {header}"})
        return None
    return ", ".join(evidence.shown[key] for key in singles)[:MAX_LABEL] or None


def _decided(evidence: _Evidence, columns: str | CurrencyFinding | None) -> CurrencyFinding:
    if isinstance(columns, CurrencyFinding):
        return columns
    hint = columns
    rows = pd.concat(evidence.rows, ignore_index=True) if evidence.rows else pd.DataFrame({"line": [], "label": []})
    present = list(dict.fromkeys(rows["label"]))
    for sign, family in NARROWING_FAMILY.items():
        codes = [label for label in present if label in family]
        if sign in present and len(codes) == 1:
            rows.loc[rows["label"] == sign, "label"] = codes[0]
    counts = _counted([rows], "label") if len(rows) else {}
    unreadable = evidence.unreadable
    if len(counts) >= 2:
        return _mixed(counts)
    if not counts:
        return CurrencyFinding(kind="none", hint=hint, unreadable=unreadable)
    (label,) = counts
    if label in ISO_4217:
        _, source, where = evidence.sources[label]
        return CurrencyFinding(kind="found", code=label, source=source, evidence=where,  # type: ignore[arg-type]  # a source of the Literal
                               hint=hint, unreadable=unreadable)
    if label in NARROWING:
        return CurrencyFinding(kind="narrowed", candidates=list(NARROWING[label]), evidence=evidence.sources[label][2],
                               hint=hint, unreadable=unreadable)
    # One currency this version cannot name: nothing is decided, Review asks.
    return CurrencyFinding(kind="none", hint=hint, unreadable=unreadable)
