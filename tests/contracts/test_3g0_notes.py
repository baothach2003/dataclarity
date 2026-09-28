"""Session 3G0 (Thach, 2026-09-29): how a consumer reads a note.

Adjustment 2: a note's CODE, figures and measures are the contract; its
sentence is the default rendering - rewording it is not a major bump, and a
reader accepts any non-empty sentence (the writers still write the default).
Adjustment 1: a note present by construction rather than because of the
file's data is shown ONCE, in "How to read these figures" - "always-on":
`discounts_in_prices`, and `same_day_cancellations` whose every measure
counts 0 lines (docs/LINE_TAXONOMY.md section 3). One function decides it,
for stage 5 and the frontend alike.
"""

import json
from datetime import UTC, datetime

import pandas as pd
import pytest
from pydantic import ValidationError

from contracts.lines import NOTE_FIGURES, NOTE_MEASURES, NOTE_TEXTS, FigureNote, is_always_on
from stages.analyze.assemble import assemble_metrics


def _note(code: str, measures: list[dict] | None = None, **changes: object) -> FigureNote:
    """`measures` None: every measure of the code, at zero, in the file scope."""
    if measures is None:
        measures = [_measure(name, "file", 0) for name in NOTE_MEASURES[code] or ()]
    return FigureNote.model_validate({"code": code, "figures": NOTE_FIGURES[code], "text": NOTE_TEXTS[code],
                                      "measures": measures} | changes)


def _measure(name: str, scope: str, lines: int, amount: float = 0.0) -> dict:
    return {"name": name, "scope": scope, "lines": lines, "amount": amount, "orders": 0}


def test_a_reworded_sentence_is_read_the_code_decides() -> None:
    note = _note("discounts_in_prices", text="Some prices may already include a discount.")
    assert (note.code, note.figures) == ("discounts_in_prices", NOTE_FIGURES["discounts_in_prices"])


def test_a_note_still_has_a_sentence_and_its_codes_figures() -> None:
    with pytest.raises(ValidationError, match="sentence"):
        _note("discounts_in_prices", text="  ")
    with pytest.raises(ValidationError, match="figures"):
        _note("same_day_cancellations", figures=["units"])


def test_the_writers_still_write_the_default_sentence() -> None:
    rows = [("2026-07-01", "O1", "Ann", "A1", "Mug", "2", "10"), ("2026-08-03", "O2", "Ann", "A1", "Mug", "1", "10"),
            ("2026-08-03", "O3", "Ann", "A1", "Mug", "-1", "10"), ("2026-09-01", "O4", "Ann", "A1", "Mug", "1", "10")]
    mapping = {"Day": "transaction_date", "Order": "order_id", "Who": "customer", "Sku": "sku",
               "Name": "product_name", "Qty": "quantity", "Price": "unit_price"}
    notes = assemble_metrics(pd.DataFrame(rows, columns=list(mapping)), mapping,
                             datetime(2026, 9, 26, tzinfo=UTC)).core.notes
    assert [n.code for n in notes] == ["same_day_cancellations", "discounts_in_prices"]
    assert all(n.text == NOTE_TEXTS[n.code] for n in notes)


def test_discounts_in_prices_is_always_on() -> None:
    assert is_always_on(_note("discounts_in_prices"))


def test_the_same_day_note_at_zero_is_always_on() -> None:
    zero = [_measure(name, scope, 0) for name in ("returns", "sales", "returns_unchecked")
            for scope in ("file", "current", "previous")]
    assert is_always_on(_note("same_day_cancellations", zero))


def test_the_same_day_note_with_lines_in_any_measure_or_scope_is_the_files_own() -> None:
    zero = [_measure(name, scope, 0) for name in ("returns", "sales", "returns_unchecked")
            for scope in ("file", "current", "previous")]
    # A file with no customer column: its returns are unchecked, not "none".
    unchecked = [m if (m["name"], m["scope"]) != ("returns_unchecked", "previous") else _measure(
        "returns_unchecked", "previous", 1, -10.0) for m in zero]
    assert not is_always_on(_note("same_day_cancellations", unchecked))
    matched = [m if (m["name"], m["scope"]) != ("returns", "file") else _measure("returns", "file", 2, -20.0)
               for m in zero]
    assert not is_always_on(_note("same_day_cancellations", matched))


@pytest.mark.parametrize("code", ["returns_booked_as_in", "unconfirmed_suggestions", "unconfirmed_deductions",
                                  "other_transaction_types"])
def test_every_other_note_is_the_files_own(code: str) -> None:
    # Present only when their measures have lines - and even at zero, never
    # always-on: nothing constructs them on every file.
    measures = None if NOTE_MEASURES[code] else [_measure("Cash", "file", 0)]
    assert not is_always_on(_note(code, measures))


# --- 3G0 review 1 -------------------------------------------------------------------------------


def test_every_note_says_whether_it_is_always_on_in_the_file() -> None:
    # #10: the frontend and the AI's input read the flag, not a second rule.
    written = json.loads(_note("discounts_in_prices").model_dump_json())
    assert written["always_on"] is True
    positive = [_measure(name, "file", int(name == "positive"), 5.0 * (name == "positive"))
                for name in NOTE_MEASURES["returns_booked_as_in"] or ()]
    assert json.loads(_note("returns_booked_as_in", positive).model_dump_json())["always_on"] is False
    # Read back from a file that carries it, or one written before it: the same.
    assert FigureNote.model_validate(written).always_on is True
    assert FigureNote.model_validate({k: v for k, v in written.items() if k != "always_on"}).always_on is True


def test_a_notes_measures_are_its_codes() -> None:
    # #2: consumers read a measure by name; a renamed one is refused.
    with pytest.raises(ValidationError, match="measures exactly"):
        _note("same_day_cancellations", [_measure("cancelled", "file", 1, -5.0)])
    # 3G-lite review 1 #7: and every one of them is there - a same-day note
    # with no measures, or without its unchecked returns, is no note.
    with pytest.raises(ValidationError, match="measures exactly"):
        _note("same_day_cancellations", [])
    with pytest.raises(ValidationError, match="measures exactly"):
        _note("same_day_cancellations", [_measure("returns", "file", 0), _measure("sales", "file", 0)])
    # 3G-lite review 2 #6 and #7: no other name beside them, and every one in
    # every scope the note measures.
    every = [_measure(name, "file", 0) for name in ("returns", "sales", "returns_unchecked")]
    with pytest.raises(ValidationError, match="measures exactly"):
        _note("same_day_cancellations", every + [_measure("cancelled", "file", 0)])
    with pytest.raises(ValidationError, match="measures exactly"):
        _note("same_day_cancellations", every + [_measure("returns", "current", 0), _measure("sales", "current", 0)])
    assert len(_note("same_day_cancellations", every + [_measure(m["name"], "current", 0) for m in every])
               .measures) == 6
    # The file's own type values name other_transaction_types' measures.
    assert _note("other_transaction_types", [_measure("Cash", "file", 3, 30.0)]).measures[0].name == "Cash"
