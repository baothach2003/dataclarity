"""Stage 4 Predict - the AI writes no number (CLAUDE.md 3.2 by construction;
session 4B's redesign after its review 2). It cites a figure of its input by
path - `{metrics.core.revenue_current}`, a list item by index or natural key
(`segments[At-risk]`, `signals[revenue]`, `revenue_by_month[2011-11]`) - and
code renders it; its own numbers are bounded tokens (`{offer:10%}`,
`{assume:20%}`, `{window:30 days}`); code computes an expected impact from a
formula of them. Any digit the AI wrote itself is refused (`digits_left`).
"""

import re
from dataclasses import dataclass
from typing import Any

PARTS = ("metrics", "diagnosis", "forecast")
NATURAL_KEYS = ("segment", "name", "product", "id", "code", "series", "period")
# The fields that hold a share or a rate as a fraction (0.4137 is 41.4%);
# every `*_pct` field already holds a percentage; a `yoy` signal's values
# are percentage points (CONTRACTS 7).
FRACTIONS = {"share", "share_of_change", "declining_base_share", "top_member_share", "products_share_of_change",
             "share_of_money_moved", "return_rate_current", "return_rate_previous", "confidence"}
SIGNAL_VALUES = {"value_cur", "center", "lower", "upper"}
_CHANGE_WORDS = ("change", "delta", "contribution", "effect")  # a signed change: its direction is checked
FALLS = {"fell", "fall", "falls", "falling", "dropped", "drop", "drops", "declined", "decline", "declines", "down",
         "lost", "lose", "loss", "shrank", "decreased", "decrease", "lower"}
RISES = {"rose", "rise", "rises", "rising", "grew", "grow", "growth", "up", "gained", "gain", "increased",
         "increase", "higher"}
NO_PURCHASES = "no purchases in file"  # the segment never sized (2E-b review F8)
PLACEHOLDER = re.compile(r"\{([^{}]*)\}")
_STEP = re.compile(r"\.?([^.\[\]]+)|\[([^\]]*)\]")
_PERCENT = re.compile(r"\s*(\d+(?:\.\d+)?)\s*%\s*")
_WINDOW = re.compile(r"\s*(\d+)\s*(day|days|week|weeks|month|months|year|years)\s*")
MONTHS = {"day": 1 / 30.4375, "week": 7 / 30.4375, "month": 1.0, "year": 12.0}
WORD = re.compile(r"[A-Za-z_]+(?:['-][A-Za-z_]+)*")
TOKENS = {"offer": "an offer only in an action or a tempting action",
           "assume": "an assumption only in an action or an expected impact"}


@dataclass(frozen=True)
class Figure:
    value: float | int | str
    key: str
    percent: bool  # rendered and computed as a percentage
    change: bool  # a signed change: a direction word before it must agree


@dataclass(frozen=True)
class Token:
    kind: str  # offer, assume, window
    number: float
    unit: str  # "%" or the window's unit
    text: str


def resolve(payload: dict[str, Any], path: str) -> Figure:
    """The figure a path names, or ValueError saying why it names none."""
    steps = [(m.group(1), m.group(2)) for m in _STEP.finditer(path.strip())]
    if not steps or "".join(m.group(0) for m in _STEP.finditer(path.strip())) != path.strip():
        raise ValueError("not a path")
    if steps[0][0] not in PARTS:
        raise ValueError("a path starts with metrics, diagnosis or forecast")
    value: Any = payload
    key, mode = "", None
    for name, selector in steps:
        if name is not None:
            if not isinstance(value, dict) or name not in value:
                raise ValueError(f"no key {name!r}")
            key, value = name, value[name]
        else:
            if not isinstance(value, list):
                raise ValueError(f"[{selector}] on something that is not a list")
            value = _item(value, selector)
            if isinstance(value, dict) and "series" in value:
                mode = value.get("mode")
    if isinstance(value, bool) or not isinstance(value, int | float | str):
        raise ValueError("not a figure")
    yoy = mode == "yoy" and key in SIGNAL_VALUES
    return Figure(value, key, key in FRACTIONS or key.endswith("_pct") or yoy,
                  yoy or any(word in key for word in _CHANGE_WORDS))


def _item(items: list[Any], selector: str) -> Any:
    if selector.isdigit():
        if int(selector) >= len(items):
            raise ValueError(f"no item {selector}")
        return items[int(selector)]
    found = [item for item in items if isinstance(item, dict)
             and any(item.get(field) == selector for field in NATURAL_KEYS)]
    if len(found) != 1:
        raise ValueError(f"no item {selector!r}" if not found else f"more than one item {selector!r}")
    return found[0]


def number(figure: Figure) -> float:
    """The figure as the arithmetic uses it: a percentage as a fraction."""
    value = float(figure.value)
    return value if figure.key in FRACTIONS else value / 100 if figure.percent else value


def show(figure: Figure, size_only: bool = False) -> str:
    if isinstance(figure.value, str):
        return figure.value
    value = abs(figure.value) if size_only else figure.value
    if figure.percent:
        points = value * 100 if figure.key in FRACTIONS else value
        return f"{points:.2f}%" if abs(points) < 1 else f"{points:.1f}%"
    return f"{value:,.0f}" if float(value).is_integer() else f"{value:,.2f}"


def token_of(content: str) -> Token | None:
    kind, _, raw = content.partition(":")
    kind = kind.strip()
    if kind in ("offer", "assume"):
        found = _PERCENT.fullmatch(raw)
        return Token(kind, float(found.group(1)) if found else float("nan"), "%", content)
    if kind == "window":
        found = _WINDOW.fullmatch(raw)
        return Token(kind, float(found.group(1)) if found else float("nan"),
                     found.group(2) if found else "", content)
    return None


def _token_problems(token: Token, allowed: set[str]) -> list[str]:
    if token.kind == "window":
        if token.unit == "":
            return [f"{{{token.text}}}: a window is a number of days, weeks, months or years"]
        months = token.number * MONTHS[token.unit.rstrip("s")]
        return [] if 0 < months <= 12 else [f"{{{token.text}}}: a window of at most a year"]
    problems = [] if token.kind in allowed else [f"{{{token.text}}}: {TOKENS[token.kind]}"]
    if not 0 < token.number <= 100:  # a NaN too: an unreadable percentage
        problems.append(f"{{{token.text}}}: a percentage above 0% and at most 100%")
    return problems


def _show_token(token: Token) -> str:
    if token.kind == "window":
        return f"{token.number:g} {token.unit}"
    return f"{token.number:g}%" + (" (assumed)" if token.kind == "assume" else "")


def _words_before(text: str) -> set[str]:
    return {word.lower() for word in WORD.findall(PLACEHOLDER.sub(" ", text))[-2:]}


def render(text: str, payload: dict[str, Any], suggested: dict[str, str], *,
           allowed: set[str]) -> tuple[str, list[str]]:
    """The text with every placeholder rendered by code, and each problem: a
    path that names no figure, a token out of bounds or out of place, a
    direction word against a change's sign. A marked product is rendered
    with its mark (AI_PIPELINE 7.9)."""
    pieces, problems, last = [], [], 0
    for found in PLACEHOLDER.finditer(text):
        pieces.append(text[last:found.start()])
        last = found.end()
        content = found.group(1).strip()
        token = token_of(content)
        if token is not None:
            problems += _token_problems(token, allowed)
            pieces.append(_show_token(token))
            continue
        try:
            figure = resolve(payload, content)
        except ValueError as error:
            problems.append(f"{{{content}}} is not a figure of the input: {error}")
            pieces.append(found.group(0))
            continue
        pieces.append(_figure_text(figure, content, _words_before(text[:found.start()]), suggested, problems))
    pieces.append(text[last:])
    return "".join(pieces), problems


def _figure_text(figure: Figure, content: str, before: set[str], suggested: dict[str, str],
                 problems: list[str]) -> str:
    if isinstance(figure.value, str):
        line_class = suggested.get(figure.value)
        return figure.value if line_class is None else f"{figure.value} (suggested: {line_class}, not confirmed)"
    if figure.change and before & (FALLS | RISES):
        falling = bool(before & FALLS)
        if figure.value > 0 and falling or figure.value < 0 and not falling:
            what = "a rise, not a fall" if falling else "a fall, not a rise"
            problems.append(f"{{{content}}} is {show(figure)}: {what}")
        return show(figure, size_only=True)
    return show(figure)


def input_texts(payload: Any) -> list[str]:
    """Every text of the input holding a digit - a product name, a period -
    longest first: the AI may write them as they are."""
    found: set[str] = set()
    pending = [payload]
    while pending:
        value = pending.pop()
        if isinstance(value, str) and any(c.isdigit() for c in value):
            found.add(value)
        elif isinstance(value, dict):
            pending.extend(value.values())
        elif isinstance(value, list):
            pending.extend(value)
    return sorted(found, key=len, reverse=True)


def digits_left(text: str, payload: dict[str, Any], texts: list[str] | None = None) -> list[str]:
    """Every number the AI wrote itself: a digit outside a placeholder and
    outside the input's own texts (4B review 2 #5, #6, #13)."""
    bare = PLACEHOLDER.sub(" ", text)
    for known in input_texts(payload) if texts is None else texts:
        bare = bare.replace(known, " ")
    return re.findall(r"\d+(?:[.,]\d+)*", bare)
