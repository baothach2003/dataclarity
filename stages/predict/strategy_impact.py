"""Stage 4 Predict - the expected impact: the AI writes the formula, code
computes the result (session 4B's redesign after its review 2, whose #1 was
an impact inflated without limit by dividing by 1% or chaining +100%). Split
from strategy_render.py.

A formula is figures cited by path and tokens, joined by x, /, + or - ("of"
multiplies); an assumption or a window only multiplies (a window in months);
division only by a figure; at most 6 terms, two assumptions, one window; the
"No purchases in file" customers never sized; no result written, no digit.
"""

import ast
import operator
import re
from collections.abc import Iterator
from typing import Any

from stages.predict.strategy_render import (
    MONTHS,
    NO_PURCHASES,
    PLACEHOLDER,
    TOKENS,
    WORD,
    Figure,
    Token,
    digits_left,
    number,
    render,
    resolve,
    token_of,
)

MAX_TERMS, MAX_ASSUMPTIONS, MAX_WINDOWS = 6, 2, 1
_OPERATOR = re.compile(r"[x×*/+\-−]")
_SYMBOLS = {"x": "*", "×": "*", "*": "*", "/": "/", "+": "+", "-": "-", "−": "-"}


_OPERATIONS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv}


def _evaluate(node: ast.AST) -> float:
    if isinstance(node, ast.Expression):
        return _evaluate(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, int | float):
        return float(node.value)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        return -_evaluate(node.operand)
    if isinstance(node, ast.BinOp) and type(node.op) in _OPERATIONS:
        return _OPERATIONS[type(node.op)](_evaluate(node.left), _evaluate(node.right))
    raise ValueError("not arithmetic")


def _terms(formula: str, payload: dict[str, Any]) -> Iterator[tuple[re.Match[str], Figure | Token | None]]:
    """The formula's numeric placeholders (a name is text, not a term)."""
    for found in PLACEHOLDER.finditer(formula):
        content = found.group(1).strip()
        token = token_of(content)
        if token is not None:
            yield found, token
            continue
        try:
            figure = resolve(payload, content)
        except ValueError:
            yield found, None  # render() names it
            continue
        if not isinstance(figure.value, str):
            yield found, figure


def _operator(between: str) -> str | None:
    kept = WORD.sub(lambda w: " x " if w.group(0) in ("x", "X", "of", "times") else " ", PLACEHOLDER.sub(" ", between))
    found = _OPERATOR.findall(kept)
    return _SYMBOLS[found[0]] if len(found) == 1 else None


def impact(formula: str, payload: dict[str, Any], suggested: dict[str, str]) -> tuple[str, list[str]]:
    """The expected impact rendered, with the result code computed, and each
    problem: the AI writes the formula, never the result (4B review 2 #1)."""
    rendered, problems = render(formula, payload, suggested, allowed={"assume"})
    problems = [p.replace(TOKENS["assume"], "") for p in problems if TOKENS["assume"] not in p]
    if "=" in formula:
        problems.append("expected_impact: write no result - the code computes it")
    problems += [f"expected_impact: {digits} is the AI's: cite a figure or use a token"
                 for digits in digits_left(formula, payload)]
    if NO_PURCHASES in formula.lower():
        problems.append("expected_impact: the 'No purchases in file' customers are never sized")
    terms = list(_terms(formula, payload))
    if any(term is None for _, term in terms):
        return rendered, problems  # a path named by render()
    problems += _formula_problems(formula, terms)
    if problems:
        return rendered, problems
    expression = ""
    for index, (found, term) in enumerate(terms):
        if index:
            expression += _operator(formula[terms[index - 1][0].end():found.start()]) or ""
        if isinstance(term, Token):
            value = term.number / 100 if term.kind == "assume" else term.number * MONTHS[term.unit.rstrip("s")]
        else:
            value = number(term)
        expression += repr(value)
    try:
        result = _evaluate(ast.parse(expression, mode="eval"))
    except ZeroDivisionError:
        return rendered, ["expected_impact divides by zero"]
    return f"{rendered} = {result:,.0f}" if abs(result) >= 100 else f"{rendered} = {result:,.2f}", []


def _formula_problems(formula: str, terms: list[tuple[re.Match[str], Figure | Token | None]]) -> list[str]:
    problems = []
    if len(terms) < 2:
        return ["expected_impact: at least two terms - a figure times an assumption, say"]
    if len(terms) > MAX_TERMS:
        problems.append(f"expected_impact: at most {MAX_TERMS} terms")
    tokens = [term for _, term in terms if isinstance(term, Token)]
    if sum(t.kind == "offer" for t in tokens):
        problems.append("expected_impact: an offer only in an action or a tempting action")
    if sum(t.kind == "assume" for t in tokens) > MAX_ASSUMPTIONS:
        problems.append("expected_impact: at most two assumptions")
    windows = [t for t in tokens if t.kind == "window"]
    if len(windows) > MAX_WINDOWS:
        problems.append("expected_impact: at most one window")
    if any(t.unit.rstrip("s") not in ("month", "year") for t in windows):
        problems.append("expected_impact: a window multiplies in months (or a year)")
    operators = [_operator(formula[terms[i - 1][0].end():terms[i][0].start()]) for i in range(1, len(terms))]
    if None in operators:
        return problems + ["expected_impact: one operator between two terms (x, /, + or -; 'of' multiplies)"]
    for index, (_, term) in enumerate(terms):
        around = operators[max(index - 1, 0):index] + operators[index:index + 1]
        if isinstance(term, Token) and any(op != "*" for op in around):
            problems.append(f"expected_impact: {{{term.text}}} - an assumption or a window only multiplies")
    return problems
