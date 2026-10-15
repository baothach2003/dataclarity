"""Columns that name or locate a person (Thach's Q8, 2026-10-16;
docs/DASHBOARD_DESIGN.md section 5.1; method C:/Users/Happy/dashboard-q678-method.txt
section 3): never offered to split sales, and so never in the AI's input -
personal data on a shareable report, and no use to a shop owner.

Told by the header or by the profile's evidence (its commonest values). A
false find only leaves a column unoffered (the cheap side); a miss draws a
person's name or address on a chart - so a doubtful header is refused. Only
Thach's list: names, e-mail, phone, address, postcode - a city, a province,
a country or a company is not refused (decision made alone). A person's name
cannot be told by its value: by the header only."""

import re
from collections.abc import Iterable

# A person word right before "name", anywhere in the header ("Billing Name", "First Name (Billing)",
# "billing_first_name"); "Device Name", "Item Name" or "Shipping Province Name" names no person (the doubt
# review's F1: anchored, WooCommerce's billing names went through to the AI).
_NAMED = (r"first|last|full|given|family|middle|sur|billing|shipping|ship|delivery|ship to|bill to|customer"
          r"|client|buyer|purchaser|recipient|contact|cardholder|card holder|account holder|holder|member|user"
          r"|employee|staff|cashier|seller|salesperson|sales person|sales rep|rep|agent|owner|person|guest|driver"
          r"|courier")
# A word that names a person wherever it stands ("Buyer Username", "Contact Person", "Account Holder").
# Not "seller" alone: "Best Seller" is a flag (the scoped review's S2); "Seller Name" is a name by _NAMED.
_ANYWHERE = r"username|sales ?person|sales ?man|sales ?woman|contact person|account holder|card ?holder"
# A header that IS a person ("Cashier"); beside another word it is not ("Customer Type").
_PERSON = (r"customer|client|buyer|purchaser|recipient|contact|cardholder|salesperson|sales rep|cashier"
           r"|employee|staff|server|user|seller|served by|sold by|created by")
_HEADER = re.compile(
    rf"^(?:{_PERSON})$|^name(?: (?:billing|shipping|bill to|ship to))?$|\b(?:{_NAMED}) ?name\b|\b(?:{_ANYWHERE})\b"
    r"|\be ?mail\b|\b(?:phone|telephone|tel|mobile|cell|fax)\b"
    r"|\baddress ?\d?\b|\baddr\b|\bstreet\b"
    r"|\bpost ?code\b|\bpostal(?: code)?\b|\bzip ?(?:code)?\b|\beircode\b")
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_PHONE = re.compile(r"^\+?[\d\s().\-]+$")
# A phone is written with a "+", brackets or two separators ("555-123-4567", "555 12 34"); one separator is a
# range or a season ("500-1000", "2023-2024" - the doubt review's F2), and a date is not a phone ("2024-12-01").
_SEPARATED = re.compile(r"^\+|[()]|[\s.\-].*[\s.\-]")
_DATE_SHAPE = re.compile(r"^\d{1,4}[-./]\d{1,2}[-./]\d{1,4}$")
# A range of two numbers ("500 - 1000", "10.00 - 20.00", "0900 - 1200"): a band, never a phone (the scoped review's S1).
_RANGE = re.compile(r"^\d[\d.,:]*\s*-\s*\d[\d.,:]*$")
_POSTCODE = re.compile(
    r"^[a-z]{1,2}\d[a-z\d]?\s*\d[a-z]{2}$"   # UK: SW1A 1AA
    r"|^[a-z]\d[a-z]\s?\d[a-z]\d$"           # Canada: K1A 0B1
    r"|^\d{4}\s?[a-z]{2}$"                   # the Netherlands: 1012 AB
    # 90210-1234, 01310-100; never a range (the doubt review's F2) - so not Japan's 100-0001, which a value cannot
    # tell from "500-1000" (its header, "Postal Code", says it).
    r"|^\d{5}-\d{4}$|^\d{5}-\d{3}$",
    re.IGNORECASE)
MIN_PHONE_DIGITS = 7


def _header(name: str) -> str:
    """Case folded, every run of punctuation, underscores or spaces one space."""
    # A word starting with a capital letter starts a new word: "BillingFirstName" (the scoped review's S3).
    words = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", name)
    return re.sub(r"[\W_]+", " ", words.casefold()).strip()


def _personal_value(value: str) -> bool:
    text = value.strip()
    if _EMAIL.match(text) or _POSTCODE.match(text):
        return True
    return (bool(_PHONE.match(text)) and bool(_SEPARATED.search(text)) and not _DATE_SHAPE.match(text)
            and not _RANGE.match(text)
            and sum(ch.isdigit() for ch in text) >= MIN_PHONE_DIGITS)


def names_a_person(name: str, values: Iterable[str]) -> bool:
    """The header or any of the commonest values names or locates a person."""
    return bool(_HEADER.search(_header(name))) or any(_personal_value(value) for value in values)
