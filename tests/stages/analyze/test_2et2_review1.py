"""Session 2E-t2's first review (fresh context, 2026-09-28): stage 2's
findings, each on a file built by hand (docs/LINE_TAXONOMY.md section 3).

#2  a charge and its reversal in one month left residue the identity check
    judged against the terms alone, and stage 2 crashed;
#3  a type cell with nothing visible became a transaction type named " ";
#4  a product whose own key and a name-only line carried two suggestions
    was marked by whichever line came first;
#7  stock received netted to one figure (+50 and -50 read 0.0);
#14 the unclassified share was 0.0, not null, when nothing moved.
"""

from datetime import UTC, datetime

import pandas as pd
import pytest

from stages.analyze.assemble import assemble_metrics

NOW = datetime(2026, 9, 26, tzinfo=UTC)
MAPPING = {"Day": "transaction_date", "Sku": "sku", "Name": "product_name", "Qty": "quantity",
           "Price": "unit_price", "Type": "transaction_type"}
COLUMNS = ["Day", "Sku", "Name", "Qty", "Price", "Type"]


def _metrics(rows: list[tuple], answers=None):
    return assemble_metrics(pd.DataFrame(rows, columns=COLUMNS), MAPPING, NOW, answers)


def test_a_charge_and_its_reversal_in_one_month_do_not_stop_stage_2() -> None:
    from contracts.cleaning import LineClassAnswer, OrderConfirmations

    rows = [("2026-07-01", "A1", "Mug", "1", "5", "out"),
            ("2026-08-01", "A1", "Mug", "1", "0.01", "out"),
            ("2026-08-02", "POST", "POSTAGE", "1", "1000000000", "out"),
            ("2026-08-03", "POST", "POSTAGE", "-1", "1000000000", "out"),
            ("2026-09-01", "A1", "Mug", "1", "5", "out")]
    answers = OrderConfirmations(line_classes=[LineClassAnswer(value="POST", field="sku", line_class="charge")])
    identity = _metrics(rows, answers).core.identity.current
    # 0.01 of sales; the charges' term nets to 0; 2,000,000,000.01 moved.
    assert (identity.gross_sales, identity.other_revenue) == (0.01, 0.0)
    assert identity.net_revenue == pytest.approx(0.01, abs=1e-6)
    assert identity.money_moved == pytest.approx(2_000_000_000.01)


def test_a_type_cell_with_nothing_visible_is_blank_not_another_type() -> None:
    rows = [("2026-07-01", "A1", "Mug", "1", "5", " "),
            ("2026-08-01", "A1", "Mug", "1", "5", "​"),
            ("2026-08-02", "A1", "Mug", "1", "5", "out"),
            ("2026-09-01", "A1", "Mug", "1", "5", "out")]
    assert "other_transaction_types" not in [n.code for n in _metrics(rows).core.notes]


@pytest.mark.parametrize("name_only_first", [False, True])
def test_a_products_mark_is_its_own_keys_suggestion_whatever_the_line_order(name_only_first: bool) -> None:
    # SKU X1 is sold as POSTAGE (suggested a charge) and once as ADJUSTMENT
    # POSTAGE; the name-only line ADJUSTMENT POSTAGE resolves to X1, and its
    # own name key is suggested an adjustment. X1's mark is X1's.
    x1 = [("2026-08-0%d" % day, "X1", "POSTAGE", "1", "5", "out") for day in (1, 2, 3)]
    x1.append(("2026-08-04", "X1", "ADJUSTMENT POSTAGE", "1", "5", "out"))
    name_only = [("2026-08-05", None, "ADJUSTMENT POSTAGE", "1", "5", "out")]
    around = [("2026-07-01", "A1", "Mug", "1", "5", "out"), ("2026-09-01", "A1", "Mug", "1", "5", "out")]
    rows = around + (name_only + x1 if name_only_first else x1 + name_only)
    assert _metrics(rows).products.suggested_classes == {"POSTAGE": "charge"}


def test_stock_received_is_reported_by_sign() -> None:
    rows = [("2026-07-01", "A1", "Mug", "1", "5", "out"),
            ("2026-08-01", "A1", "Mug", "10", "5", "in"),
            ("2026-08-02", "A1", "Mug", "-10", "5", "in"),
            ("2026-08-03", "A1", "Mug", "3", "0", "in"),
            ("2026-09-01", "A1", "Mug", "1", "5", "out")]
    rows_out = [(r.scope, r.sign, r.lines, r.amount, r.lines_without_amount)
                for r in _metrics(rows).core.outside_revenue if r.scope == "file"]
    assert rows_out == [("file", "positive", 1, 50.0, 0), ("file", "negative", 1, -50.0, 0),
                        ("file", "no_money", 1, 0.0, 0)]


def test_the_unclassified_share_is_null_when_nothing_moved() -> None:
    rows = [("2026-07-01", "A1", "Mug", "1", "0", "out"), ("2026-08-01", "A1", "Mug", "1", "0", "out"),
            ("2026-09-01", "A1", "Mug", "1", "0", "out")]
    unclassified = _metrics(rows).core.unclassified
    assert (unclassified.lines, unclassified.amount, unclassified.share_of_money_moved) == (0, 0.0, None)
