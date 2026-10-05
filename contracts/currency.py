"""The file's currency (the report redesign's step 2; Thach D6, Q5-Q9,
Q26-Q30; docs/REPORT_REDESIGN.md section 6): what stage 1 finds in the raw
file on the plan's money column and a currency column (the finding, for
Review and execution), the user's answer (plan `confirmations.currency`) and
what ran (cleaning_report.json `currency`). Strong evidence only - anything
doubtful is not found and Review asks; a bare "$" or the yen sign narrows;
more than one currency blocks the plan. Stage 5 shows the ISO code (Q8)."""

from typing import Annotated, Literal, Self

from pydantic import AfterValidator, Field, model_validator

from contracts._base import ContractModel

# ISO 4217 active codes (as of 2025; ZWG and XCG included). A closed list:
# a code outside it is no answer.
ISO_4217 = frozenset("""
AED AFN ALL AMD ANG AOA ARS AUD AWG AZN BAM BBD BDT BGN BHD BIF BMD BND BOB BRL BSD BTN BWP BYN BZD
CAD CDF CHF CLP CNY COP CRC CUP CVE CZK DJF DKK DOP DZD EGP ERN ETB EUR FJD FKP GBP GEL GHS GIP GMD
GNF GTQ GYD HKD HNL HTG HUF IDR ILS INR IQD IRR ISK JMD JOD JPY KES KGS KHR KMF KPW KRW KWD KYD KZT
LAK LBP LKR LRD LSL LYD MAD MDL MGA MKD MMK MNT MOP MRU MUR MVR MWK MXN MYR MZN NAD NGN NIO NOK NPR
NZD OMR PAB PEN PGK PHP PKR PLN PYG QAR RON RSD RUB RWF SAR SBD SCR SDG SEK SGD SHP SLE SLL SOS SRD
SSP STN SVC SYP SZL THB TJS TMT TND TOP TRY TTD TWD TZS UAH UGX USD UYU UZS VES VND VUV WST XAF XCD
VED XCG XOF XPF YER ZAR ZMW ZWG ZWL
""".split())

# The answer that says the file's currency is not known: amounts are then
# shown with no code, "in your file's currency".
NOT_STATED = "not_stated"

# The dollar currencies, the ones Review offers first for a bare "$" (Thach,
# Q9: then the full list, where the pesos are).
DOLLARS = ("USD", "AUD", "CAD", "NZD", "SGD", "HKD", "BBD", "BMD", "BND", "BSD", "BZD", "FJD", "GYD", "JMD",
           "KYD", "LRD", "NAD", "SBD", "SRD", "TTD", "TWD", "XCD")
# A symbol that names a family, never one currency: the user picks (Q5, Q9),
# offered these first (then the full list).
NARROWING = {"$": DOLLARS, "¥": ("JPY", "CNY")}
# Every currency a sign is written for - the dollars and the pesos for "$" -
# so a file naming one of them beside the sign is that currency, not two
# (a peso file writes "$", a Brazilian one "R$").
NARROWING_FAMILY = {"$": (*DOLLARS, "MXN", "CLP", "COP", "ARS", "UYU", "DOP", "CUP", "MOP", "NIO", "BRL"),
                    "¥": ("JPY", "CNY")}


def _iso(value: str) -> str:
    if value not in ISO_4217:
        raise ValueError(f"{value!r} is not an ISO 4217 code")
    return value


def _answer(value: str) -> str:
    return value if value == NOT_STATED else _iso(value)


CurrencyCode = Annotated[str, AfterValidator(_iso)]
# An ISO code, or "not_stated".
CurrencyAnswer = Annotated[str, AfterValidator(_answer)]


# A mixed finding lists at most this many currencies; a label (a currency
# column's value as first written) is cut to this length.
MAX_PARTS = 10
MAX_LABEL = 40


class CurrencyPart(ContractModel):
    """One currency of a file that has more than one: its code (or a
    narrowing symbol) and how many lines carry it."""

    label: str = Field(min_length=1, max_length=MAX_LABEL)
    lines: int = Field(gt=0)


class CurrencyFinding(ContractModel):
    """What stage 1 found in the raw file: one currency, with where it was
    found ("found"); a symbol that names a family ("narrowed", the candidates
    in the order Review offers them); more than one ("mixed", which blocks
    the plan); or nothing ("none"). Unless blocked: what the currency
    columns say that is no evidence, for Review to show (`hint`: a value
    that is no code, "Euro", or columns that disagree, "EUR, USD"), and
    their cells that read as a number or a date (`unreadable`, Q29)."""

    kind: Literal["found", "narrowed", "mixed", "none"]
    code: CurrencyCode | None = None
    source: Literal["column", "symbol", "header"] | None = None
    candidates: list[CurrencyCode] = Field(default_factory=list)
    evidence: str | None = None
    parts: list[CurrencyPart] = Field(default_factory=list, max_length=MAX_PARTS)
    # The currencies past the first MAX_PARTS (largest first), counted, not
    # listed: the sentence and the file stay bounded (step 2's review 2 #1).
    more_parts: int = Field(default=0, ge=0)
    hint: str | None = Field(default=None, min_length=1, max_length=MAX_LABEL)
    unreadable: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def _shape_follows_the_kind(self) -> Self:
        found = self.kind == "found"
        if (self.code is not None, self.source is not None) != (found, found) or (found and self.evidence is None):
            raise ValueError("a found currency carries its code, source and evidence - nothing else does")
        if (self.kind == "narrowed") != bool(self.candidates):
            raise ValueError("a narrowed finding carries its candidates - nothing else does")
        if (self.kind == "mixed") != (len(self.parts) >= 2) or (self.kind != "mixed" and self.parts):
            raise ValueError("a mixed finding carries two or more parts - nothing else does")
        if self.more_parts and len(self.parts) < MAX_PARTS:
            raise ValueError("currencies are counted past the listed ones only once the list is full")
        if self.hint is not None and self.kind == "mixed":
            raise ValueError("a blocked file lists its currencies, no hint")
        if self.unreadable and self.kind == "mixed":
            raise ValueError("a blocked file lists its currencies, not its unreadable cells")
        return self


class AppliedCurrency(ContractModel):
    """What ran (cleaning_report.json): the code stages 4-5 show amounts in,
    or none ("not_stated": "amounts in your file's currency"); where it came
    from - the file (column, symbol, header) or the user's answer - and what
    the file said, kept even when the user changed it."""

    code: CurrencyCode | None
    source: Literal["column", "symbol", "header", "user", "not_stated"]
    evidence: str | None

    @model_validator(mode="after")
    def _a_code_exactly_when_stated(self) -> Self:
        if (self.code is None) != (self.source == NOT_STATED):
            raise ValueError("a currency carries a code exactly when it is stated")
        return self
