"""What runs, from stage 1's currency finding and the user's answer (the
report redesign's step 2; Thach D6, Q7 = A): more than one currency refuses
the plan, an answer stands, unanswered a currency found is the one found and
anything else is not stated. The finding itself: currency.py.
"""

from contracts.currency import NOT_STATED, AppliedCurrency, CurrencyFinding
from stages.ingest.plan_validation import InvalidPlanError


class MixedCurrencies(InvalidPlanError):
    """More than one currency in the file: never summed (Thach, Q7 = A) - the
    plan does not run, whatever the answer."""


def _lines(count: int) -> str:
    # No thousands separator: the parts are themselves listed with commas.
    return f"{count} line" + ("" if count == 1 else "s")


def apply_currency(finding: CurrencyFinding, answer: str | None) -> AppliedCurrency:
    """What runs: mixed is refused whatever the answer; an answer stands (the
    user may change what was found); unanswered, a found currency is the one
    found and anything else is "not stated" - never a dollar picked for a
    bare "$" (Thach, D6)."""
    if finding.kind == "mixed":
        # Thach's form (Q28): "Euro: 300 lines, US Dollar: 20 lines".
        parts = ", ".join(f"{part.label}: {_lines(part.lines)}" for part in finding.parts)
        if finding.more_parts:
            parts += f" and {finding.more_parts} more"
        raise MixedCurrencies([
            f"Your file has amounts in more than one currency ({parts}). DataClarity cannot add different "
            "currencies together. Split the file by currency and upload each part."])
    if answer is None:
        if finding.kind == "found":
            return AppliedCurrency(code=finding.code, source=finding.source, evidence=finding.evidence)  # type: ignore[arg-type]  # a source of the Literal
        return AppliedCurrency(code=None, source=NOT_STATED, evidence=finding.evidence)
    if answer == NOT_STATED:
        return AppliedCurrency(code=None, source=NOT_STATED, evidence=finding.evidence)
    if answer == finding.code:  # only a found currency has a code
        return AppliedCurrency(code=answer, source=finding.source, evidence=finding.evidence)  # type: ignore[arg-type]  # a source of the Literal
    return AppliedCurrency(code=answer, source="user", evidence=finding.evidence)
