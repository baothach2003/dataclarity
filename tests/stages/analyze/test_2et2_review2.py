"""Session 2E-t2's second review (fresh context, 2026-09-28): stage 2's
findings, each on a file built by hand (docs/LINE_TAXONOMY.md section 3).

#1 a charge's "in" line or unpriced line lost the user's item, became a
   product named like the charge, and renamed a real product that shares
   its name;
#2 with no customer column the same-day note read 0 lines - "no return
   could be a cancellation" - where the data cannot tell;
#3 the other transaction types were unbounded: a free-text column mapped as
   the type put every value into the notes.
"""

from datetime import UTC, datetime

import pandas as pd

from contracts.cleaning import LineClassAnswer, OrderConfirmations
from stages.analyze.assemble import assemble_metrics
from shared.line_report import OTHER_TYPE_NAME_CHARS, OTHER_TYPES_NAMED

NOW = datetime(2026, 9, 26, tzinfo=UTC)
MAPPING = {"Day": "transaction_date", "Sku": "sku", "Name": "product_name", "Qty": "quantity",
           "Price": "unit_price", "Type": "transaction_type"}
COLUMNS = ["Day", "Sku", "Name", "Qty", "Price", "Type"]


def test_a_charges_stock_in_and_unpriced_lines_rename_no_product() -> None:
    # X9 is a product called POSTAGE; P1, also called POSTAGE, is answered a
    # charge and has a line typed "in" and a line with no price.
    rows = [("2026-07-01", "X9", "POSTAGE", "3", "6", "out"), ("2026-08-01", "X9", "POSTAGE", "5", "2", "out"),
            ("2026-08-02", "P1", "POSTAGE", "1", "4", "out"), ("2026-08-03", "P1", "POSTAGE", "1", None, "out"),
            ("2026-08-04", "P1", "POSTAGE", "2", "4", "in"), ("2026-09-01", "X9", "POSTAGE", "1", "2", "out")]
    answers = OrderConfirmations(line_classes=[LineClassAnswer(value="P1", field="sku", line_class="charge")])
    products = assemble_metrics(pd.DataFrame(rows, columns=COLUMNS), MAPPING, NOW, answers).products
    assert [(p.product, p.revenue) for p in products.top_products] == [("POSTAGE", 10.0)]
    assert [(d.product, d.revenue_change) for d in products.biggest_decliners or []] == [("POSTAGE", -8.0)]


def test_returns_with_no_customer_are_counted_apart_not_read_as_no_cancellation() -> None:
    rows = [("2026-07-01", "A1", "Mug", "1", "5", "out"),
            ("2026-08-01 10:00", "A1", "Mug", "10", "5", "out"),
            ("2026-08-01 10:05", "A1", "Mug", "-10", "5", "out"),
            ("2026-09-01", "A1", "Mug", "1", "5", "out")]
    notes = {n.code: n for n in assemble_metrics(pd.DataFrame(rows, columns=COLUMNS), MAPPING, NOW).core.notes}
    got = {(m.name, m.scope): (m.lines, m.amount) for m in notes["same_day_cancellations"].measures}
    assert got[("returns", "current")] == (0, 0.0)
    assert got[("returns_unchecked", "current")] == (1, -50.0)
    assert got[("returns_unchecked", "file")] == (1, -50.0)


def test_the_other_transaction_types_are_bounded() -> None:
    # Twelve values V00..V11 on 5, 12, 1, 9, 3, 11, 7, 2, 10, 4, 8, 6 lines -
    # neither the names' order nor its reverse. The five with the most lines
    # are named, in order of their names, each by its commonest spelling (3
    # of V01's lines read "v01"), V10's long name cut; the seven others are
    # measured together, `keys` counting them.
    lines = [5, 12, 1, 9, 3, 11, 7, 2, 10, 4, 8, 6]
    rows = [("2026-07-01", "A1", "Mug", "1", "5", "out")]
    for n, count in enumerate(lines):
        name = f"V{n:02d}" + ("x" * 60 if n == 10 else "")
        spellings = [name.lower()] * 3 + [name] * (count - 3) if n == 1 else [name] * count
        rows += [("2026-08-02", "A1", "Mug", "1", "5", spelled) for spelled in spellings]
    rows.append(("2026-09-01", "A1", "Mug", "1", "5", "out"))
    notes = {n.code: n for n in assemble_metrics(pd.DataFrame(rows, columns=COLUMNS), MAPPING, NOW).core.notes}
    files = [m for m in notes["other_transaction_types"].measures if m.scope == "file"]
    assert OTHER_TYPES_NAMED == 5
    assert [(m.name, m.lines, m.keys) for m in files] == [
        ("V01", 12, None), ("V03", 9, None), ("V05", 11, None), ("V08", 10, None),
        ("V10" + "x" * (OTHER_TYPE_NAME_CHARS - 6) + "...", 8, None),
        ("(other values)", 5 + 1 + 3 + 7 + 2 + 4 + 6, 7)]
    assert all(len(m.name) <= OTHER_TYPE_NAME_CHARS for m in files)
