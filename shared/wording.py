"""The plain-words formats of the report's front section and of stage 4's
claims - one copy for both stages (CLAUDE.md 3.1; the report redesign, steps
3 and 4; docs/REPORT_REDESIGN.md section 1's conventions): a month as "December
2024", money with two decimals and its ISO code when one is confirmed (Q8:
"AUD 46,292.50", the code first, before any sign), counts whole. Formats
round for display; nothing is computed (CONTRACTS 9)."""

import calendar
import re
from datetime import date

_ZERO = re.compile(r"[-+]?[0.,]+%?")


def _signless(text: str) -> str:
    """A value that prints as zero carries no minus (CONTRACTS 11: -0.0)."""
    return text[1:] if text.startswith("-") and _ZERO.fullmatch(text) else text


def month_name(year_month: str) -> str:
    """"2024-12" -> "December 2024"."""
    return f"{calendar.month_name[int(year_month[5:7])]} {year_month[:4]}"


def month_only(year_month: str) -> str:
    """"2024-12" -> "December"."""
    return calendar.month_name[int(year_month[5:7])]


def amount(value: float, code: str | None) -> str:
    text = _signless(f"{value:,.2f}")
    return f"{code} {text}" if code else text


def signed(value: float, code: str | None) -> str:
    """"+4,712.29", "-2,646.13"; "+0.00" for a part that did not move."""
    text = f"{value:+,.2f}"
    text = "+" + text[1:] if _ZERO.fullmatch(text) else text
    return f"{code} {text}" if code else text


def unsigned(value: float, code: str | None) -> str:
    return amount(abs(value), code)


def pct(value: float) -> str:
    """A change in percent, its sign always written: "+11.9%"."""
    text = f"{value:+,.1f}%"
    return "0.0%" if _ZERO.fullmatch(text) else text


def plain_pct(value: float) -> str:
    """A rate in percent, its sign only when negative: "27.1%"."""
    return _signless(f"{value:,.1f}%")


def count(value: float) -> str:
    return _signless(f"{value:,.0f}")


def two(value: float) -> str:
    return _signless(f"{value:,.2f}")


def times(factor: float) -> str:
    """2 -> "twice"; 4 -> "4 times"."""
    return "twice" if factor == 2 else f"{factor:g} times"


def prints_as_zero(value: float) -> bool:
    return f"{abs(value):,.2f}" == "0.00"


def days(start: date, end: date) -> str:
    """"1 to 18 January 2025", or one day "18 January 2025"."""
    month = f"{calendar.month_name[end.month]} {end.year}"
    return f"{end.day} {month}" if start == end else f"{start.day} to {end.day} {month}"


def first_lower(text: str) -> str:
    return text[:1].lower() + text[1:]
