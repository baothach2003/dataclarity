"""The number question's decision and the rewrite (2E-u1; the method's N4-N6,
C:/Users/Happy/2E-u1-method.txt): per quantity and price column, the cells
prove their own mark; the column's proof, else the user's answer in Review,
reads the ambiguous ones; unanswered and unproven the plan is refused with
the true reason - never a default either way. Readable cells are rewritten as
plain numbers before the plan runs. The reading itself: number_format.py.
"""

from collections.abc import Mapping

import pandas as pd

from contracts.cleaning import AppliedNumberFormat
from contracts.profile import NumberFormat
from stages.ingest.number_format import FormatEvidence, format_evidence, read_cell
from stages.ingest.plan_validation import InvalidPlanError

# The canonical fields stages 2 and 3 read as numbers.
NUMERIC_FIELDS = ("quantity", "unit_price")
_WORDS: dict[NumberFormat, str] = {"decimal_point": "a decimal point", "decimal_comma": "a decimal comma"}


class NumberQuestionUnanswered(InvalidPlanError):
    """A numeric column reads two ways and nobody has said which: Review's
    number question is open. Never a default either way (Thach, 2E-u F1)."""


class NumberAnswerContradicted(InvalidPlanError):
    """An answer the file's own cells disprove: the cells decide."""


# What stage 1 did to one numeric column (contracts/cleaning.py).
AppliedFormat = AppliedNumberFormat


def _decide(column: str, evidence: FormatEvidence, answer: NumberFormat | None) -> tuple[NumberFormat | None, bool]:
    decision = evidence.decision
    if decision is None:
        return None, False
    if decision == "ask":
        if answer is None:
            # Both marks proven is no guide either (review 1, F8).
            which = ("its other numbers prove both marks" if evidence.point and evidence.comma
                     else "nothing in the file says which")
            raise NumberQuestionUnanswered([
                f"The numbers in column {column!r} can be read two ways - {evidence.ambiguous_example!r} is "
                f"{_two_ways(evidence.ambiguous_example)} - and {which}: answer the number question in Review"])
        return answer, True
    if answer is not None and answer != decision:
        example = evidence.point_example if decision == "decimal_point" else evidence.comma_example
        mark = "a comma" if answer == "decimal_comma" else "a point"
        raise NumberAnswerContradicted([
            f"The answer for column {column!r} says the decimal mark is {mark}, but {example!r} can only "
            f"be read with {_WORDS[decision]}: change the answer in Review"])
    return decision, False


def _two_ways(example: str | None) -> str:
    """'1,000' -> "one thousand with a thousands comma, or one with a
    decimal comma": the cell's one separator read each way."""
    reading = read_cell(example)
    if example is None or reading is None or reading.as_point is None or reading.as_comma is None:
        return "two numbers"
    comma = "," in example
    word = "comma" if comma else "point"
    as_point = "thousands" if comma else "decimal"
    as_comma = "decimal" if comma else "thousands"
    return (f"{_spoken(reading.as_point)} with a {as_point} {word}, or "
            f"{_spoken(reading.as_comma)} with a {as_comma} {word}")


def _spoken(value: float) -> str:
    whole = {1.0: "one", 1000.0: "one thousand"}
    return whole.get(value, f"{value:g}")


def apply_number_formats(frame: pd.DataFrame, columns: dict[str, str], answers: Mapping[str, NumberFormat], *,
                         refuse: bool = True) -> tuple[pd.DataFrame, dict[str, AppliedFormat]]:
    """`columns`: source column -> canonical field (the plan's mapping);
    `answers`: Review's answers by source column. Every column mapped to a
    numeric field is decided and rewritten; the others are untouched. The
    frame given is not modified. Raises NumberQuestionUnanswered or
    NumberAnswerContradicted (both INVALID_PLAN), every column's problem
    together - or, with `refuse` False (the preview, while the user is still
    answering), leaves such a column as written."""
    cleaned = frame.copy()
    applied: dict[str, AppliedFormat] = {}
    problems: list[str] = []
    unanswered = False
    for column, field in columns.items():
        if field not in NUMERIC_FIELDS or column not in frame.columns:
            continue
        values = frame[column]
        evidence = format_evidence(values)
        try:
            decided, answered = _decide(column, evidence, answers.get(column))
        except InvalidPlanError as error:
            problems += error.problems
            unanswered = unanswered or isinstance(error, NumberQuestionUnanswered)
            continue
        # Per distinct value, as the evidence: a million rows of a few
        # thousand prices cost a few thousand readings.
        texts: dict[str, str] = {}
        # A whole number the reading would write back unchanged ("12", "-3")
        # is not read (review 2, N4: the line summary on every Review edit).
        distinct = pd.Series(values.dropna().unique(), dtype=object)
        # Matched as text: `.str` raised on a column pandas typed (review 3,
        # R3-4); a cell that is not text is read as no number either way.
        as_written = distinct.astype(str).str.fullmatch(r"-?[0-9]+")
        for cell in distinct[~as_written]:
            reading = read_cell(cell)
            if reading is None:
                continue
            text = (reading.text(decided) if reading.shape == "ambiguous" and decided is not None
                    else reading.point_text if reading.shape in ("plain", "point") else reading.comma_text)
            if text is not None and text != cell:
                texts[cell] = text
        changed = values.isin(list(texts))
        rewritten = int(changed.sum())
        out = values.copy()
        out[changed] = values[changed].map(texts)
        cleaned[column] = out
        applied[column] = AppliedFormat(format=decided, rewritten=rewritten, unreadable=evidence.unreadable,
                                        answered=answered)
    if problems and refuse:
        raise (NumberQuestionUnanswered if unanswered else NumberAnswerContradicted)(problems)
    return cleaned, applied
