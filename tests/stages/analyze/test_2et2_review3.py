"""Session 2E-t2's third review (fresh context, 2026-09-28): stage 2's
findings, each on a file built by hand (docs/LINE_TAXONOMY.md section 3).

#1  a pooled code's returns were neither matched nor counted as returns no
    match can check;
#2  stage 1's raw parse read the date column twice with a name-only line;
#3  a same-day return rung by name alone was matched on its name, never on
    the product it is;
#6  every return undated, the same-day note still stood, all zero;
#7  one candidate key counted twice through a name-only line;
#8  two type values alike in their first characters shared a measure name;
#10 the "amount too large to add" reason was never asserted at stage 2.
"""

from datetime import UTC, datetime

import pandas as pd
import pytest

from contracts.cleaning import LineClassAnswer, OrderConfirmations
from shared import line_taxonomy
from shared.order_checks import parse_for_checks
from stages.analyze.assemble import assemble_metrics

NOW = datetime(2026, 9, 26, tzinfo=UTC)
MAPPING = {"Day": "transaction_date", "Order": "order_id", "Who": "customer", "Sku": "sku", "Name": "product_name",
           "Qty": "quantity", "Price": "unit_price", "Type": "transaction_type"}
COLUMNS = ["Day", "Order", "Who", "Sku", "Name", "Qty", "Price", "Type"]
AROUND = [("2026-07-01", "O0", "Zed", "A1", "Mug", "1", "5", "out"),
          ("2026-09-01", "O9", "Zed", "A1", "Mug", "1", "5", "out")]


def _metrics(rows: list[tuple], answers: OrderConfirmations | None = None):
    return assemble_metrics(pd.DataFrame(AROUND + rows, columns=COLUMNS), MAPPING, NOW, answers)


def _measures(metrics, code: str) -> dict:
    [note] = [n for n in metrics.core.notes if n.code == code]
    return {(m.name, m.scope): (m.lines, m.amount, m.orders, m.keys) for m in note.measures}


def test_a_pooled_codes_returns_are_counted_as_returns_no_match_can_check() -> None:
    rows = [("2026-08-03", "O1", "Ann", "M", "Manual", "2", "10", "out"),
            ("2026-08-03", "O2", "Ann", "M", "Manual", "-2", "10", "out")]
    answers = OrderConfirmations(line_classes=[LineClassAnswer(value="M", field="sku", line_class="pooled")])
    got = _measures(_metrics(rows, answers), "same_day_cancellations")
    assert got[("returns", "current")][0] == 0
    assert got[("returns_unchecked", "current")] == (1, -20.0, 1, None)


def test_a_same_day_return_rung_by_name_is_matched_to_its_product() -> None:
    # Ann buys the Mug under A1 and returns it the same day with no SKU: the
    # name is sold under A1 alone, so the return is A1's (2E-f L4).
    rows = [("2026-08-03", "O1", "Ann", "A1", "Mug", "3", "10", "out"),
            ("2026-08-03", "O2", "Ann", None, "Mug", "-1", "10", "out")]
    got = _measures(_metrics(rows), "same_day_cancellations")
    assert (got[("returns", "current")], got[("sales", "current")]) == ((1, -10.0, 1, None), (1, 30.0, 1, None))
    assert got[("returns_unchecked", "current")][0] == 0


def test_no_same_day_note_without_a_dated_return() -> None:
    rows = [("2026-08-03", "O1", "Ann", "A1", "Mug", "3", "10", "out"),
            ("not a date", "O2", "Ann", "A1", "Mug", "-1", "10", "out")]
    assert "same_day_cancellations" not in [n.code for n in _metrics(rows).core.notes]


def test_one_candidate_key_is_one_key_through_a_name_only_line() -> None:
    # The SKU POSTAGE, named "Blue box", is suggested a charge; a line with no
    # SKU named "Blue box" is sold under it and inherits the suggestion.
    rows = [("2026-08-03", "O1", "Ann", "POSTAGE", "Blue box", "1", "5", "out"),
            ("2026-08-04", "O2", "Bo", None, "Blue box", "1", "5", "out")]
    got = _measures(_metrics(rows), "unconfirmed_suggestions")
    assert got[("lines", "file")] == (2, 10.0, 2, 1)


def test_type_value_names_are_told_apart() -> None:
    # Two long values alike in their first 37 characters, on 2 lines each, and
    # a value spelled like the rest's own name: five named, two in the rest.
    long = "Payment via the regional card network, branch "
    values = [long + "north", long + "south", "(other values)", "Cash", "Card", "Wire", "Cheque",
              long + "north", long + "south"]
    rows = [("2026-08-03", f"O{n}", "Ann", "A1", "Mug", "1", "5", value) for n, value in enumerate(values)]
    names = [name for name, scope in _measures(_metrics(rows), "other_transaction_types") if scope == "file"]
    assert names == ["(other values) (2)", "Card", "Cash", "Payment via the regional card network...",
                     "Payment via the regional card net... (2)", "(other values)"]


def test_an_amount_too_large_to_add_is_unmeasurable_for_that_reason() -> None:
    rows = [("2026-08-03", "O1", "Ann", "A1", "Mug", "1e200", "1e200", "out"),
            ("2026-08-04", "O2", "Ann", "A1", "Mug", "1", "5", "out")]
    assert [(r.scope, r.reason, r.lines) for r in _metrics(rows).core.unmeasurable] == [
        ("file", "amount too large to add", 1), ("current", "amount too large to add", 1)]


def test_the_raw_parse_reads_the_dates_once(monkeypatch: pytest.MonkeyPatch) -> None:
    def again(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("read the date column a second time")

    monkeypatch.setattr(line_taxonomy, "_dates", again)
    raw = pd.DataFrame(AROUND + [("2026-08-03", "O1", "Ann", None, "Mug", "1", "5", "out")], columns=COLUMNS)
    parsed = parse_for_checks(raw, MAPPING)
    assert parsed is not None and parsed.sale.sum() == 3
