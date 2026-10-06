"""Stage 4 Predict - what the strategy step's AI is given (docs/AI_PIPELINE.md
section 8; session 4B's S1): the consumer contract's 4B rows of metrics.json
and diagnosis.json (docs/CONTRACTS.md section 11), never the whole files,
and the computed forecast block.

Bounded: every list the file can grow - countries, categories, a
dimension's members, top products and decliners - capped to its largest
movers. Every note is worded by its code (contracts.lines.NOTE_TEXTS),
never by the file's sentence (3G0, adjustment 2), with its figures,
measures and `always_on`. The deterministic diagnosis is read, never its
narration: the step runs whether or not `ai_findings` exists (4B's S4).
"""

from collections.abc import Callable, Sequence
from typing import Any

from contracts.diagnosis import DiagnosisContract, Localization
from contracts.forecast import ForecastBlock
from contracts.lines import NOTE_TEXTS, FigureNote
from contracts.metrics import MetricsContract

MEMBERS_SHOWN = 10  # a list's largest movers (3G0 review #6: the input is bounded)


def _largest[T](rows: Sequence[T], change: Callable[[T], float]) -> list[T]:
    """The MEMBERS_SHOWN rows that moved most, either way, in their order."""
    kept = set(sorted(range(len(rows)), key=lambda i: -abs(change(rows[i])))[:MEMBERS_SHOWN])
    return [row for i, row in enumerate(rows) if i in kept]


def _note(note: FigureNote) -> dict[str, Any]:
    return {"code": note.code, "says": NOTE_TEXTS[note.code], "figures": list(note.figures),
            "measures": [m.model_dump(mode="json") for m in note.measures], "always_on": note.always_on}


def _dumped(rows: Sequence[Any]) -> list[dict[str, Any]]:
    return [row.model_dump(mode="json") for row in rows]


def _metrics(metrics: MetricsContract) -> dict[str, Any]:
    core, products, dimensions = metrics.core, metrics.products, metrics.by_dimension
    moved = lambda row: row.revenue_current - row.revenue_previous  # noqa: E731 - one rule, two lists
    return {
        "period": metrics.period.model_dump(mode="json"),
        # The basis's reason stays (4B review 1 #12): with no order numbers
        # the AI must say lines, not orders.
        # The report redesign's fields (step 1) are read by 5 and FE only (CONTRACTS 11).
        "core": core.model_dump(mode="json", exclude={"notes", "buyers_current", "buyers_previous",
                                                      "revenue_change", "revenue_change_reason"})
        | {"notes": [_note(n) for n in core.notes]},
        # Never the walk-in candidates: customer values from the file, beyond
        # the AI's bounded sample (CLAUDE.md 3.2; 2E-u3 review 1, #3).
        "customers": metrics.customers.model_dump(
            mode="json", exclude={"unconfirmed_placeholders", "unconfirmed_placeholders_reason"}),
        "products": products.model_dump(mode="json", exclude={"velocity", "velocity_reason", "top_products",
                                                              "biggest_decliners"})
        | {"top_products": _dumped(products.top_products[:MEMBERS_SHOWN]),
           "biggest_decliners": None if products.biggest_decliners is None
           else _dumped(products.biggest_decliners[:MEMBERS_SHOWN])},
        "by_dimension": {"country": _dumped(_largest(dimensions.country, moved)),
                         "category": _dumped(_largest(dimensions.category, moved)),
                         "contribution_reason": dimensions.contribution_reason},
    }


def _localization(localization: Localization | None) -> dict[str, Any] | None:
    if localization is None:
        return None
    return {
        "dimensions": [dimension.model_dump(mode="json", exclude={"members", "new_members", "removed_members",
                                                                  "member_count", "size_filter_waived"})
                       | {"members": _dumped(_largest(dimension.members, lambda m: m.delta)),
                          "new_members": dimension.new_members[:MEMBERS_SHOWN],
                          "removed_members": dimension.removed_members[:MEMBERS_SHOWN]}
                       for dimension in localization.dimensions],
        "mix_rate": None if localization.mix_rate is None else localization.mix_rate.model_dump(mode="json"),
        "breadth": localization.breadth.model_dump(mode="json"),
    }


def _diagnosis(diagnosis: DiagnosisContract) -> dict[str, Any]:
    trust = diagnosis.trust
    return {
        "frame": diagnosis.frame.model_dump(mode="json", include={"current", "previous", "year_ago_current",
                                                                  "year_ago_previous", "history_months"}),
        "trust": {"verdict": trust.verdict, "limitations": list(trust.limitations),
                  "checks": [{"id": c.id, "status": c.status, "message": c.message} for c in trust.checks]},
        "calendar": None if diagnosis.calendar is None else diagnosis.calendar.model_dump(
            mode="json", exclude={"evidence"}),
        "signals": None if diagnosis.signals is None else [
            s.model_dump(mode="json", exclude={"limits_method"}) for s in diagnosis.signals],
        "tree": None if diagnosis.tree is None else diagnosis.tree.model_dump(
            mode="json", exclude={"lever": {"reasons", "bridge", "bridge_withheld"},
                                  "customers": {"evidence", "previous_transition"}}),
        "localization": _localization(diagnosis.localization),
        "hypotheses": [h.model_dump(mode="json", include={"id", "family", "lens", "statement", "verdict",
                                                          "contribution", "share", "rule"})
                       for h in diagnosis.hypotheses],
        "not_testable": _dumped(diagnosis.not_testable),
        "headline": diagnosis.headline.model_dump(mode="json", exclude={"hedge", "named", "offsetting"}),
        "notes": [_note(n) for n in diagnosis.notes],
        "suggested_classes": dict(diagnosis.suggested_classes),
    }


def strategy_input(metrics: MetricsContract, diagnosis: DiagnosisContract,
                   forecast: ForecastBlock) -> dict[str, Any]:
    """The three parts the prompt carries: metrics, diagnosis, forecast."""
    return {"metrics": _metrics(metrics), "diagnosis": _diagnosis(diagnosis),
            "forecast": forecast.model_dump(mode="json")}
