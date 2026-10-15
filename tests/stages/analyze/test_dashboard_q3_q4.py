"""Thach's Q3 and Q4 (2026-10-15) in stage 2's breakdowns (metrics.json 16.4;
method C:/Users/Happy/dashboard-q345-method.txt). Q3: above 9 values, the top
8 by the two months' sales and one "Other (N values)" member - the members
still add up to each month. Q4: with a trusted order id, a blank line takes
its order's one value. Every figure is worked by hand in the comments."""

from datetime import UTC, datetime

import pandas as pd
import pytest

from contracts.cleaning import OrderConfirmations
from contracts.metrics import MetricsContract
from stages.analyze.assemble import SCHEMA_VERSION, assemble_metrics
from stages.analyze.metrics_breakdowns import compute_breakdowns
from stages.analyze.metrics_core import compute_core_metrics

MAPPING = {"Date": "transaction_date", "Qty": "quantity", "Price": "unit_price", "Product": "product_name"}
ORDERED = MAPPING | {"Order": "order_id"}
RECEIPT = OrderConfirmations(order_id_is_receipt=True)
NOW = datetime(2026, 9, 19, 12, 0, tzinfo=UTC)


def _row(day: str, price: float, pay: str | None, order: str | None = None) -> dict:
    return {"Date": day, "Qty": "1", "Price": str(price), "Product": "X", "Pay": pay, "Order": order}


def _split(rows: list[dict], mapping: dict[str, str] = MAPPING, confirmations: OrderConfirmations | None = None):
    frame = pd.DataFrame(rows)
    period, core = compute_core_metrics(frame, mapping, now=NOW, confirmations=confirmations)
    (split,) = compute_breakdowns(frame, mapping, period, ["Pay"], confirmations)
    return core, split


def _thirteen() -> list[dict]:
    # V01 sold in December only (20.00); V02..V13 one January line each at its number (V13 = 13.00); a blank
    # January line of 0.50. Thirteen values in the two months.
    rows = [_row("2019-12-01", 20.0, "V01")]
    rows += [_row(f"2020-01-{k:02d}", float(k), f"V{k:02d}") for k in range(2, 14)]
    rows.append(_row("2020-01-31", 0.5, None))
    return rows


def test_above_nine_values_the_top_eight_by_both_months_and_one_other() -> None:
    core, split = _split(_thirteen())

    # By the two months' sales together: V01 20 (December only - it stays visible), V13 13, V12 12 ... V07 7.
    # Other: V02..V06 = 2 + 3 + 4 + 5 + 6 = 20.00 in January, nothing in December - 5 values.
    assert [(m.name, m.revenue_current, m.revenue_previous, m.change) for m in split.members] == [
        ("V01", 0.0, 20.0, -20.0), ("V07", 7.0, 0.0, 7.0), ("V08", 8.0, 0.0, 8.0), ("V09", 9.0, 0.0, 9.0),
        ("V10", 10.0, 0.0, 10.0), ("V11", 11.0, 0.0, 11.0), ("V12", 12.0, 0.0, 12.0), ("V13", 13.0, 0.0, 13.0),
        ("Other (5 values)", 20.0, 0.0, 20.0), ("(blank)", 0.5, 0.0, 0.5)]
    other = split.members[8]
    assert (other.is_other, other.values, other.is_blank) == (True, 5, False)
    assert not any(m.is_other for m in split.members if m is not other)
    assert all(m.values is None for m in split.members if m is not other)
    # Still the whole of each month: 0 + 7 + ... + 13 = 70, + 20 + 0.50 = 90.50; December 20.
    assert sum(m.revenue_current for m in split.members) == core.revenue_current == 90.5
    assert sum(m.revenue_previous for m in split.members) == core.revenue_previous == 20.0


def test_nine_values_are_all_shown() -> None:
    rows = [_row("2019-12-01", 1.0, "V1")] + [_row(f"2020-01-{k:02d}", 1.0, f"V{k}") for k in range(1, 9)]
    rows.append(_row("2020-01-31", 1.0, "V9"))
    _, split = _split(rows)
    assert [m.name for m in split.members] == [f"V{k}" for k in range(1, 10)]
    assert not any(m.is_other for m in split.members)


def test_ten_values_fold_two_and_equal_sales_are_ranked_by_name() -> None:
    # Ten values of 1.00 each: equal, so by name - V01..V08 shown, V09 and V10 are Other (2.00, 2 values).
    rows = [_row("2019-12-01", 5.0, "V01")] + [_row(f"2020-01-{k:02d}", 1.0, f"V{k:02d}") for k in range(1, 10)]
    rows.append(_row("2020-01-31", 1.0, "V10"))
    rows[0]["Pay"] = "V01"  # December's line: V01 now 6.00 over the two months, still first
    _, split = _split(rows)
    assert [m.name for m in split.members] == [f"V{k:02d}" for k in range(1, 9)] + ["Other (2 values)"]
    assert (split.members[-1].revenue_current, split.members[-1].values) == (2.0, 2)


def test_the_blank_member_is_never_folded_into_other() -> None:
    _, split = _split(_thirteen())
    assert split.members[-1].is_blank and not split.members[-1].is_other


@pytest.mark.parametrize("written", ["Other (5 values)", " other (5 VALUES) "])
def test_a_value_written_like_the_other_bar_is_withheld(written: str) -> None:
    rows = _thirteen()
    rows[5]["Pay"] = written  # replaces V06's name: still 13 values, and one reads as the Other bar's label
    _, split = _split(rows)
    assert split.members == []
    assert split.withheld_reason == 'a value is written like "Other (N values)", the label of the folded values'


def test_with_nine_values_or_fewer_a_value_named_like_other_is_just_a_value() -> None:
    rows = [_row("2019-12-01", 1.0, "Card"), _row("2020-01-02", 1.0, "Other (3 values)"),
            _row("2020-01-31", 2.0, "Card")]
    _, split = _split(rows)
    assert [m.name for m in split.members] == ["Card", "Other (3 values)"]
    assert not any(m.is_other for m in split.members)


def test_the_written_file_loads_and_the_version_is_16_4() -> None:
    metrics = assemble_metrics(pd.DataFrame(_thirteen()).drop(columns=["Order"]), MAPPING, now=NOW,
                               breakdowns=["Pay"])
    assert SCHEMA_VERSION == "16.4"  # 16.4: a breakdown's "Other" member (Thach's Q3)
    MetricsContract.model_validate(metrics.model_dump(mode="json"))


# --- Q4: a blank line takes its order's one value ------------------------------------------------------------------

def _orders() -> list[dict]:
    return [
        # December: T0 Cash 20.00; T9 Card 4.00.
        _row("2019-12-01", 20.0, "Cash", "T0"), _row("2019-12-02", 4.0, "Card", "T9"),
        # January: T1 - Card 10.00 on its first line, a blank line of 5.00 (Shopify's shape): Card 15.00.
        _row("2020-01-10", 10.0, "Card", "T1"), _row("2020-01-10", 5.0, None, "T1"),
        # T2 - one blank line of 3.00: no value, the blank member.
        _row("2020-01-11", 3.0, None, "T2"),
        # T3 - Cash 7.00.
        _row("2020-01-31", 7.0, "Cash", "T3"),
    ]


def test_with_an_order_id_a_blank_line_is_its_orders_value() -> None:
    core, split = _split(_orders(), ORDERED, RECEIPT)
    assert [(m.name, m.revenue_current, m.revenue_previous) for m in split.members] == [
        ("Card", 15.0, 4.0), ("Cash", 7.0, 20.0), ("(blank)", 3.0, 0.0)]
    assert sum(m.revenue_current for m in split.members) == core.revenue_current == 25.0


def test_without_an_order_id_a_blank_line_stays_blank() -> None:
    _, split = _split(_orders(), MAPPING)
    assert [(m.name, m.revenue_current) for m in split.members] == [("Card", 10.0), ("Cash", 7.0), ("(blank)", 8.0)]


def test_an_order_id_the_run_does_not_trust_counts_lines() -> None:
    # Without the receipt answer and no customer column, the order id is checked by date only and not trusted
    # (shared/orders.py): the per-line reading stands.
    _, split = _split(_orders(), ORDERED)
    assert [(m.name, m.revenue_current) for m in split.members] == [("Card", 10.0), ("Cash", 7.0), ("(blank)", 8.0)]


def test_an_order_holding_two_values_is_withheld() -> None:
    rows = _orders()
    rows[3]["Pay"] = "Cash"  # T1 now Card and Cash
    _, split = _split(rows, ORDERED, RECEIPT)
    assert split.members == []
    assert split.withheld_reason == "an order holds two different values of this column"
