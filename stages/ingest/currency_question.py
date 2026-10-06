"""Review's currency question (the report redesign's step 5; design 6.2 and
6.3): the raw file read on the plan's money column by the function execute
uses (one reading, never two), and what Review shows worded here - the
block, the unreadable cells, the hint - so the page words no figure."""

from collections.abc import Iterable

import pandas as pd

from contracts.cleaning import CleaningPlanContract
from contracts.currency import ISO_4217, NOT_STATED, CurrencyFinding, CurrencyQuestion
from stages.ingest.currency import currency_finding
from stages.ingest.currency_apply import mixed_sentence

# The codes Review offers first when nothing narrows the list (design 6.2:
# "the common ones first (GBP, EUR, USD, AUD, CAD, ...)"); then the rest of
# ISO 4217 in alphabetical order.
COMMON = ("GBP", "EUR", "USD", "AUD", "CAD", "NZD", "JPY", "CNY", "CHF", "INR", "SGD", "HKD")


def plan_currency(frame: pd.DataFrame, plan: CleaningPlanContract) -> CurrencyFinding:
    """The raw file's currency on the columns the plan maps to the unit
    price (Thach, Q26) - what execute applies and Review asks about."""
    money = [action.source_name for action in plan.column_actions if action.canonical_field == "unit_price"]
    return currency_finding(frame, money)


def _ordered(first: Iterable[str]) -> list[str]:
    head = list(dict.fromkeys(first))
    return head + sorted(ISO_4217 - set(head))


def currency_question(finding: CurrencyFinding) -> CurrencyQuestion:
    """Found: its code pre-selected; narrowed: its candidates first, nothing
    assumed ("not stated" until the user picks); none: the common codes
    first, "not stated" the default; mixed: the block, no answer offered."""
    if finding.kind == "mixed":
        return CurrencyQuestion(finding=finding, options=[], selected=None, blocked=mixed_sentence(finding),
                                unreadable=None, hint=None)
    first = finding.candidates if finding.kind == "narrowed" else COMMON
    cells = finding.unreadable
    return CurrencyQuestion(
        finding=finding, options=_ordered(first),
        selected=finding.code if finding.kind == "found" and finding.code else NOT_STATED, blocked=None,
        # Worded for one currency column or several (step 5's review: two columns, "GBP, EUR").
        unreadable=(f"{cells} cell{'' if cells == 1 else 's'} where the file names its currency could not be read."
                    if cells else None),
        hint=f"Where your file names its currency, it says: {finding.hint}" if finding.hint else None)
