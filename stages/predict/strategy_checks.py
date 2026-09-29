"""Stage 4 Predict - the checks on the strategy step's answer, and its
rendering (docs/AI_PIPELINE.md section 8; session 4B, redesigned after its
review 2). The AI writes no number: it cites figures by path and proposes
bounded tokens (strategy_render.py); any digit it wrote itself is refused,
so nothing it computed or invented can reach the report (CLAUDE.md 3.2). The
words are checked too: no stock (not supported in v1), no verdict on a
month (ADR-0006, ADR-0007), a product marked as possibly not a product
named so and never acted on, the customers with no purchase never a target
(only looked into), lines never called orders. Each problem is named, so
the one retry can fix it.
"""

import re
from dataclasses import dataclass, field
from typing import Any, Protocol

from stages.predict.strategy_impact import impact
from stages.predict.strategy_render import (
    NO_PURCHASES,
    PLACEHOLDER,
    digits_left,
    input_texts,
    render,
    resolve,
)

MIN_RECOMMENDATIONS, MAX_RECOMMENDATIONS = 3, 5  # AI_PIPELINE 8
_STOCK = re.compile(r"\b(?:re-?order\w*|re-?stock\w*|stock(?:s|ed)?|stock-?outs?|stocking\s+up|inventor(?:y|ies))\b",
                    re.IGNORECASE)
# Stage 3's prescribed wording for its stockout hypothesis (CONTRACTS 7).
_STOCKOUT_WORDING = re.compile(r"consistent with a stock-?out", re.IGNORECASE)
# A verdict on a period (ADR-0006/0007) - refused only in a sentence about a
# period, so "a typical Champion" stays sound (4B review 2 #7).
_VERDICT = re.compile(r"\b(?:(?:ab)?normal\w*|a?typical|(?:un)?usual\w*|anomal\w*|exceptional\w*|(?:extra)?ordinary"
                      r"|outliers?|routine|as\s+expected)\b", re.IGNORECASE)
_PERIOD = re.compile(r"\bPERIOD\b|\d{4}-\d{2}|\b(?:January|February|March|April|May|June|July|August|September|October"
                     r"|November|December|month|months|year|years|week|weeks|season\w*)\b", re.IGNORECASE)
_ORDERS = re.compile(r"\b(?:orders?|order\s+count|AOV|order\s+value)\b", re.IGNORECASE)
_LOOK_INTO = re.compile(r"\b(?:look\w*\s+into|investigat\w*|check\w*|review\w*|examin\w*|find\s+out)\b", re.IGNORECASE)


class Recommended(Protocol):
    priority: int
    insight: str
    cause: str
    action: str
    expected_impact: str
    how_to_measure: str
    confidence: float


class Avoided(Protocol):
    tempting_action: str
    why_wrong_here: str


@dataclass
class Reviewed:
    recommendations: list[dict[str, Any]] = field(default_factory=list)
    do_not_do: list[dict[str, str]] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Context:
    payload: dict[str, Any]
    suggested: dict[str, str]
    orders_basis: str
    texts: list[str]


def _prose(text: str, context: Context) -> str:
    """The text with each placeholder a word - PERIOD for a period, FIGURE
    otherwise - so the words around them can be read."""
    def word(found: re.Match[str]) -> str:
        try:
            value = resolve(context.payload, found.group(1)).value
        except ValueError:
            return " FIGURE "
        return " PERIOD " if isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}", value) else " FIGURE "
    return PLACEHOLDER.sub(word, text)


def _marked_names(text: str, suggested: dict[str, str]) -> list[str]:
    """The marked products a text names in prose: a name of several words in
    any case, a one-word name in its own case - "a discount" is a word, not
    the product "Discount" (4B review 1 #4, review 2 #10)."""
    found = []
    for name in suggested:
        flags = re.IGNORECASE if " " in name.strip() else 0
        if re.search(rf"(?<!\w){re.escape(name)}(?!\w)", text, flags):
            found.append(name)
    return found


def _cited_marked(text: str, context: Context) -> list[str]:
    names = []
    for found in PLACEHOLDER.finditer(text):
        try:
            value = resolve(context.payload, found.group(1)).value
        except ValueError:
            continue
        if isinstance(value, str) and value in context.suggested:
            names.append(value)
    return names


def _word_problems(where: str, text: str, context: Context, *, acts: bool, targets: bool,
                   names_what_not_to_do: bool) -> list[str]:
    prose = _prose(text, context)
    problems = []
    if not names_what_not_to_do:
        if _STOCK.search(_STOCKOUT_WORDING.sub("", prose)):
            problems.append(f"{where}: never stock, inventory, a reorder or a stockout (not supported in v1)")
        for sentence in re.split(r"[.!?;]", prose):
            if _VERDICT.search(sentence) and _PERIOD.search(sentence):
                problems.append(f"{where}: never call a month normal, typical, usual, unusual or exceptional "
                                "(no signal is a verdict)")
                break
    if context.orders_basis == "lines" and _ORDERS.search(re.sub(r"in order to", " ", prose, flags=re.IGNORECASE)):
        problems.append(f"{where}: the file has no order numbers - say lines and average line value, never orders")
    in_prose = _marked_names(PLACEHOLDER.sub(" ", text), context.suggested)
    for name in in_prose:
        if f"{name} (suggested: {context.suggested[name]}, not confirmed)" not in text:
            problems.append(f"{where}: cite {name!r} by its path, so it carries its mark - or write "
                            f"'{name} (suggested: {context.suggested[name]}, not confirmed)'")
    if acts:
        for name in in_prose + _cited_marked(text, context):
            problems.append(f"{where}: {name!r} is marked as possibly not a product - never the subject of an action")
    if targets and NO_PURCHASES in text.lower() and not _LOOK_INTO.search(text):
        problems.append(f"{where}: the 'No purchases in file' customers bought nothing in the file - only look "
                        "into why their lines exist, never a target")
    return problems


def _field(where: str, text: str, context: Context, *, allowed: set[str], acts: bool = False,
           names_what_not_to_do: bool = False) -> tuple[str, list[str]]:
    """One field rendered, and its problems. `acts`: an action - a marked
    product is never its subject, the no-purchase customers only looked into."""
    if not text.strip():
        return text, [f"{where} is empty"]
    rendered, problems = render(text, context.payload, context.suggested, allowed=allowed)
    problems = [f"{where}: {p}" for p in problems]
    problems += [f"{where}: {digits} is a number you wrote - cite the figure by its path, or use a token"
                 for digits in digits_left(text, context.payload, context.texts)]
    problems += _word_problems(where, text, context, acts=acts, targets=acts,
                               names_what_not_to_do=names_what_not_to_do)
    return rendered, problems


def _cites(text: str, context: Context) -> bool:
    for found in PLACEHOLDER.finditer(text):
        try:
            if not isinstance(resolve(context.payload, found.group(1)).value, str):
                return True
        except ValueError:
            continue
    return False


def review(recommendations: list[Recommended], do_not_do: list[Avoided], payload: dict[str, Any],
           suggested: dict[str, str], orders_basis: str) -> Reviewed:
    """The answer rendered by code, and every problem of session 4B's rules."""
    context = Context(payload, suggested, orders_basis, input_texts(payload))
    reviewed = Reviewed()
    if not MIN_RECOMMENDATIONS <= len(recommendations) <= MAX_RECOMMENDATIONS:
        reviewed.problems.append(f"give {MIN_RECOMMENDATIONS} to {MAX_RECOMMENDATIONS} recommendations, not "
                                 f"{len(recommendations)}")
    if [r.priority for r in recommendations] != list(range(1, len(recommendations) + 1)):
        reviewed.problems.append("rank the recommendations by priority 1, 2, 3... in order")
    if not do_not_do:
        reviewed.problems.append("give at least one do_not_do")
    for index, rec in enumerate(recommendations, start=1):
        where = f"recommendation {index}"
        insight, a = _field(f"{where} insight", rec.insight, context, allowed=set())
        cause, b = _field(f"{where} cause", rec.cause, context, allowed=set())
        action, c = _field(f"{where} action", rec.action, context, allowed={"offer", "assume"}, acts=True)
        measure, d = _field(f"{where} how_to_measure", rec.how_to_measure, context, allowed=set())
        effect, e = impact(rec.expected_impact, payload, suggested)
        e = [p if p.startswith("expected_impact") else f"expected_impact: {p}" for p in e]
        e = [f"{where} {p}" for p in e] + _word_problems(f"{where} expected_impact", rec.expected_impact, context,
                                                         acts=True, targets=False, names_what_not_to_do=False)
        reviewed.problems += a + b + c + d + e
        if not (_cites(rec.insight, context) or _cites(rec.cause, context)):
            reviewed.problems.append(f"{where} cites no figure in its insight or cause - cite one by its path")
        if "{window:" not in rec.how_to_measure.replace(" ", ""):
            reviewed.problems.append(f"{where} how_to_measure names no review window - use {{window:30 days}} "
                                     "(SPECS 7.6)")
        reviewed.recommendations.append({"priority": rec.priority, "insight": insight, "cause": cause,
                                         "action": action, "expected_impact": effect, "how_to_measure": measure,
                                         "confidence": rec.confidence})
    for index, item in enumerate(do_not_do, start=1):
        where = f"do_not_do {index}"
        tempting, f = _field(f"{where} tempting_action", item.tempting_action, context, allowed={"offer"},
                             names_what_not_to_do=True)
        why, g = _field(f"{where} why_wrong_here", item.why_wrong_here, context, allowed=set())
        reviewed.problems += f + g
        reviewed.do_not_do.append({"tempting_action": tempting, "why_wrong_here": why})
    return reviewed


def check_answer(recommendations: list[Recommended], do_not_do: list[Avoided], payload: dict[str, Any],
                 suggested: dict[str, str], orders_basis: str) -> None:
    """Raises ValueError naming every problem, which the retry sends back.
    Anything the check cannot read is a problem, never a crash."""
    try:
        problems = review(recommendations, do_not_do, payload, suggested, orders_basis).problems
    except (OverflowError, RecursionError) as error:
        problems = [f"the answer could not be read ({type(error).__name__})"]
    if problems:
        raise ValueError("; ".join(problems))
