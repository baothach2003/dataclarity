"""The dashboard's step 2 (Thach's D5, 2026-10-14): stage 2's "sales by
<category column>" for the compared months - metrics.json 16.3
`by_dimension.breakdowns` (docs/DASHBOARD_DESIGN.md section 7; method
C:/Users/Happy/dashboard-step2-method.txt).

Every expected figure is worked by hand in the comments."""

import json
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pytest

from stages.analyze.assemble import SCHEMA_VERSION, analyze_run, assemble_metrics
from stages.analyze.metrics_breakdowns import BLANK_LABEL, compute_breakdowns
from stages.analyze.metrics_core import compute_core_metrics

NOW = datetime(2026, 9, 19, 12, 0, tzinfo=UTC)
MAPPING = {"Date": "transaction_date", "Qty": "quantity", "Price": "unit_price", "Product": "product_name"}


def _row(day: str, qty: str, price: str, pay: str | None, product: str = "X") -> dict:
    return {"Date": day, "Qty": qty, "Price": price, "Product": product, "Pay": pay}


def _shop() -> pd.DataFrame:
    return pd.DataFrame([
        # December 2019 (previous, from the 1st: complete): Cash 50, Card 50, Voucher 20 -> 120
        _row("2019-12-01", "5", "10.0", "Cash"),
        _row("2019-12-02", "5", "10.0", "Card"),
        _row("2019-12-03", "2", "10.0", "Voucher"),
        # January 2020 (current): Cash 30 and a Cash return -10, Card 70, a blank 5 -> 95
        _row("2020-01-10", "3", "10.0", "Cash"),
        _row("2020-01-12", "-1", "10.0", "Cash"),
        _row("2020-01-20", "1", "5.0", None),
        _row("2020-01-31", "7", "10.0", "Card"),
    ])


def _breakdowns(frame: pd.DataFrame, columns: list[str], mapping: dict[str, str] = MAPPING):
    period, core = compute_core_metrics(frame, mapping, now=NOW)
    return period, core, compute_breakdowns(frame, mapping, period, columns)


def test_each_value_sums_its_lines_net_of_returns() -> None:
    period, core, (split,) = _breakdowns(_shop(), ["Pay"])

    assert (period.previous, period.current, period.previous_complete) == ("2019-12", "2020-01", True)
    assert split.column == "Pay" and split.withheld_reason is None and split.change_reason is None
    by = {m.name: m for m in split.members}
    # Cash: 30 - 10 = 20 now, 50 before, -30; Card 70 / 50, +20; Voucher sold in December only: 0 / 20, -20;
    # the blank cell its own member: 5 / 0, +5.
    assert [(m.name, m.revenue_current, m.revenue_previous, m.change, m.is_blank) for m in split.members] == [
        ("Card", 70.0, 50.0, 20.0, False), ("Cash", 20.0, 50.0, -30.0, False),
        ("Voucher", 0.0, 20.0, -20.0, False), (BLANK_LABEL, 5.0, 0.0, 5.0, True)]
    # The members are the whole of each month's revenue: 70 + 20 + 0 + 5 = 95; 50 + 50 + 20 + 0 = 120.
    assert sum(m.revenue_current for m in by.values()) == core.revenue_current == 95.0
    assert sum(m.revenue_previous for m in by.values()) == core.revenue_previous == 120.0


def test_the_blank_label_is_the_reserved_bucket() -> None:
    assert BLANK_LABEL == "(blank)"


def test_spellings_of_one_value_are_one_member_named_as_first_written() -> None:
    frame = _shop()
    frame.loc[3, "Pay"] = " cash"   # January's Cash sale, written another way
    frame.loc[4, "Pay"] = "CASH"
    _, _, (split,) = _breakdowns(frame, ["Pay"])

    cash = [m for m in split.members if m.name.lower().strip() == "cash"]
    assert len(cash) == 1 and cash[0].name == "Cash"  # the first spelling in the file (December's)
    assert (cash[0].revenue_current, cash[0].revenue_previous) == (20.0, 50.0)


def test_an_incomplete_previous_month_keeps_its_totals_and_has_no_change() -> None:
    # December starts on the 5th: incomplete (stage 2 tolerates two missing leading days, not four).
    frame = _shop().iloc[1:].reset_index(drop=True)
    frame.loc[frame["Date"] < "2019-12-05", "Date"] = "2019-12-05"
    period, _, (split,) = _breakdowns(frame, ["Pay"])

    assert period.previous_complete is False
    assert split.change_reason == period.previous_incomplete_reason
    assert all(m.change is None for m in split.members)
    # Card 50 and Voucher 20 in the part of December the file holds; Cash none there.
    assert {m.name: m.revenue_previous for m in split.members} == {
        "Card": 50.0, "Cash": 0.0, "Voucher": 20.0, BLANK_LABEL: 0.0}


def test_more_than_twelve_values_is_drawn_as_eight_and_other() -> None:
    # Was "withheld with the count" (16.3); Thach's Q3 (16.4) draws the top 8 and "Other".
    rows = [_row("2019-12-01", "1", "1.0", "V0")]
    rows += [_row(f"2020-01-{day:02d}", "1", "1.0", f"V{day}") for day in range(1, 13)]
    rows.append(_row("2020-01-31", "1", "1.0", "V13"))  # 14 values in all; December's V0 counts too
    _, _, (split,) = _breakdowns(pd.DataFrame(rows), ["Pay"])

    # All 1.00 over the two months: by name - v0, v1, v10, v11, v12, v13, v2, v3 shown; V4..V9 are Other (6.00).
    assert split.withheld_reason is None
    assert [m.name for m in split.members] == ["V0", "V1", "V10", "V11", "V12", "V13", "V2", "V3", "Other (6 values)"]
    assert (split.members[-1].revenue_current, split.members[-1].values) == (6.0, 6)


def test_twelve_values_is_drawn() -> None:
    rows = [_row(f"2020-01-{day:02d}", "1", "1.0", f"V{day}") for day in range(1, 12)]
    rows += [_row("2019-12-01", "1", "1.0", "V0"), _row("2020-01-31", "1", "1.0", "V1")]
    _, _, (split,) = _breakdowns(pd.DataFrame(rows), ["Pay"])

    assert split.withheld_reason is None
    # Was 12 members (16.3); Q3: V1 (2.00) and the seven first by name of the 1.00s, then Other (V6..V9).
    assert len(split.members) == 9 and split.members[-1].name == "Other (4 values)"


def test_a_blank_member_is_not_counted_against_the_twelve() -> None:
    rows = [_row(f"2020-01-{day:02d}", "1", "1.0", f"V{day}") for day in range(1, 13)]
    rows += [_row("2019-12-01", "1", "1.0", None), _row("2020-01-31", "1", "1.0", "V1")]
    _, _, (split,) = _breakdowns(pd.DataFrame(rows), ["Pay"])

    assert split.withheld_reason is None
    # Was 13 members (16.3); Q3: 8 values, Other (4 values), and the blank - never folded.
    assert len(split.members) == 10 and split.members[-1].is_blank and split.members[-2].is_other


def test_one_value_splits_nothing() -> None:
    frame = _shop()
    frame["Pay"] = "Cash"
    _, _, (split,) = _breakdowns(frame, ["Pay"])

    assert split.members == []
    assert split.withheld_reason == ("the column has one value in December 2019 and January 2020, so it splits "
                                     "nothing")


def test_an_all_blank_column_splits_nothing() -> None:
    frame = _shop()
    frame["Pay"] = None
    _, _, (split,) = _breakdowns(frame, ["Pay"])

    assert split.members == []
    assert split.withheld_reason == ("the column has no value in December 2019 and January 2020, so it splits "
                                     "nothing")


def test_a_column_missing_from_the_cleaned_file_is_withheld_never_a_failure() -> None:
    _, _, (split,) = _breakdowns(_shop(), ["Store"])

    assert split.column == "Store" and split.members == []
    assert split.withheld_reason == "the column is not in the cleaned file"


def test_two_columns_in_the_order_given() -> None:
    frame = _shop()
    frame["Till"] = ["T1", "T2", "T1", "T2", "T2", "T1", "T1"]
    _, _, splits = _breakdowns(frame, ["Till", "Pay"])

    assert [s.column for s in splits] == ["Till", "Pay"]
    # Till: T1 = December 50 + 20 = 70, January 5 + 70 = 75; T2 = December 50, January 30 - 10 = 20.
    assert [(m.name, m.revenue_current, m.revenue_previous) for m in splits[0].members] == [
        ("T1", 75.0, 70.0), ("T2", 20.0, 50.0)]


def test_no_column_no_breakdown() -> None:
    _, _, splits = _breakdowns(_shop(), [])
    assert splits == []


def test_a_single_row_has_no_previous_month_to_split() -> None:
    # One line: the current month is January 2020, December holds nothing - one value only.
    frame = pd.DataFrame([_row("2020-01-31", "1", "1.0", "Cash")])
    period, _, (split,) = _breakdowns(frame, ["Pay"])

    assert split.members == []
    assert "one value" in split.withheld_reason


def test_an_empty_frame_is_withheld() -> None:
    frame = pd.DataFrame(columns=["Date", "Qty", "Price", "Product", "Pay"])
    period, _, (split,) = _breakdowns(frame, ["Pay"])

    assert split.members == []
    assert split.withheld_reason.startswith("no line counted in revenue is dated in")


def test_lines_outside_the_two_months_are_not_counted() -> None:
    frame = pd.concat([_shop(), pd.DataFrame([_row("2019-11-15", "9", "10.0", "Cash")])], ignore_index=True)
    _, _, (split,) = _breakdowns(frame, ["Pay"])

    assert {m.name: m.revenue_previous for m in split.members}["Cash"] == 50.0  # November's 90 not in it


def test_assemble_writes_them_and_the_version_is_16_4() -> None:
    metrics = assemble_metrics(_shop(), MAPPING, now=NOW, breakdowns=["Pay"])

    # 16.3: by_dimension.breakdowns (the dashboard, step 2); 16.4: the Other member (Q3)
    assert SCHEMA_VERSION == "16.4"
    assert [s.column for s in metrics.by_dimension.breakdowns] == ["Pay"]


def test_assemble_without_a_breakdown_writes_an_empty_list() -> None:
    metrics = assemble_metrics(_shop(), MAPPING, now=NOW)

    assert metrics.by_dimension.breakdowns == []


def _run(tmp_path: Path, breakdowns: list[str] | None) -> Path:
    run = tmp_path / "0c000000-0000-4000-8000-000000000001"
    run.mkdir()
    _shop().to_csv(run / "cleaned.csv", index=False)
    report = {"schema_version": "4.3", "generated_at": "2026-09-19T12:00:00Z", "rows_in": 7, "rows_out": 7,
              "columns_in": 5, "columns_out": 5, "changes": [], "warnings": [], "column_mapping": MAPPING}
    if breakdowns is not None:
        report["breakdowns"] = breakdowns
    (run / "cleaning_report.json").write_text(json.dumps(report), encoding="utf-8")
    return run


def test_analyze_run_reads_the_breakdowns_stage_1_recorded(tmp_path: Path) -> None:
    run = _run(tmp_path, ["Pay"])
    analyze_run(tmp_path, run.name, now=NOW)
    written = json.loads((run / "metrics.json").read_text(encoding="utf-8"))

    assert [s["column"] for s in written["by_dimension"]["breakdowns"]] == ["Pay"]


def test_a_cleaning_report_before_the_field_reads_as_none(tmp_path: Path) -> None:
    run = _run(tmp_path, None)
    analyze_run(tmp_path, run.name, now=NOW)
    written = json.loads((run / "metrics.json").read_text(encoding="utf-8"))

    assert written["by_dimension"]["breakdowns"] == []


@pytest.mark.parametrize("column", ["Date", "Qty"])
def test_a_mapped_column_is_split_only_if_asked_and_never_crashes(column: str) -> None:
    # Stage 1 never records a mapped column (step 4's eligibility); stage 2 does not guess either way - the
    # values it reads decide (a date has more than 12 values here only with more days; this frame has 5).
    _, _, (split,) = _breakdowns(_shop(), [column])
    assert split.column == column

def test_on_a_generated_store_the_members_are_each_month_to_the_cent() -> None:
    # The scenario generator's S0 (seed 1): six categories over 26 months - the split of its Category column
    # adds up to stage 2's own revenue for both compared months.
    from tests.scenarios.scenarios import s0
    from tests.scenarios.store import MAPPING as STORE

    frame = s0(1)
    # Read per line (no order id).
    per_line = {k: v for k, v in STORE.items() if v != "order_id"}
    metrics = assemble_metrics(frame, per_line, now=NOW, breakdowns=["Category"])
    (split,) = metrics.by_dimension.breakdowns
    assert split.withheld_reason is None and len(split.members) == 6
    assert round(sum(m.revenue_current for m in split.members), 2) == round(metrics.core.revenue_current, 2)
    assert round(sum(m.revenue_previous for m in split.members), 2) == round(metrics.core.revenue_previous, 2)
    # With the order id: an invoice holds several categories - a line attribute, split line by line (Thach's
    # Q6, 2026-10-16), the same six members to the cent; Customer - one per invoice, many values - is the top 8
    # and Other, still to the cent.
    metrics = assemble_metrics(frame, STORE, now=NOW, breakdowns=["Category", "Customer"])
    category, customer = metrics.by_dimension.breakdowns
    assert category.withheld_reason is None and category.members == split.members
    assert customer.withheld_reason is None and any(m.is_other for m in customer.members)
    assert round(sum(m.revenue_current for m in customer.members), 2) == round(metrics.core.revenue_current, 2)
    assert round(sum(m.revenue_previous for m in customer.members), 2) == round(metrics.core.revenue_previous, 2)


def test_a_line_not_counted_in_revenue_makes_no_member() -> None:
    # A January line with no price is in no figure (stage 2's unmeasurable lines): its value "Gift" appears
    # nowhere, and the split still adds up to January's 95.
    frame = pd.concat([_shop(), pd.DataFrame([_row("2020-01-15", "1", "", "Gift")])], ignore_index=True)
    _, core, (split,) = _breakdowns(frame, ["Pay"])

    assert "Gift" not in {m.name for m in split.members}
    assert sum(m.revenue_current for m in split.members) == core.revenue_current == 95.0


def test_values_only_outside_the_two_months_do_not_count_towards_the_bound() -> None:
    # Cash is the one value in December and January; Card was sold in November only: one value here.
    frame = _shop()
    frame["Pay"] = "Cash"
    frame = pd.concat([frame, pd.DataFrame([_row("2019-11-10", "1", "1.0", "Card")])], ignore_index=True)
    _, _, (split,) = _breakdowns(frame, ["Pay"])

    assert split.members == []
    assert "one value" in split.withheld_reason


def test_thirteen_values_is_eight_and_other() -> None:
    rows = [_row(f"2020-01-{day:02d}", "1", "1.0", f"V{day}") for day in range(1, 13)]
    rows += [_row("2019-12-01", "1", "1.0", "V0"), _row("2020-01-31", "1", "1.0", "V1")]  # V0..V12: 13 values
    _, _, (split,) = _breakdowns(pd.DataFrame(rows), ["Pay"])

    # Was withheld (16.3); Q3: V1 2.00 first, then v0, v10, v11, v12, v2, v3, v4 by name; Other V5..V9 (5 values).
    assert split.withheld_reason is None
    assert split.members[-1].name == "Other (5 values)" and split.members[-1].revenue_current == 5.0


def test_a_month_of_returns_is_a_negative_member() -> None:
    # December: Voucher's only line is a return of 2 x 10 = -20 (a refund for an earlier sale).
    frame = _shop()
    frame.loc[2, "Qty"] = "-2"
    _, core, (split,) = _breakdowns(frame, ["Pay"])

    voucher = next(m for m in split.members if m.name == "Voucher")
    assert (voucher.revenue_current, voucher.revenue_previous, voucher.change) == (0.0, -20.0, 20.0)
    assert sum(m.revenue_previous for m in split.members) == core.revenue_previous == 80.0


@pytest.mark.parametrize("written", ["(blank)", " (Blank) ", "(BLANK)"])
def test_a_value_written_like_the_blank_bucket_is_withheld_never_a_failure(written: str) -> None:
    # Review 1 F1: an Excel pivot's "(blank)" read as a value would stand beside the empty cells' own bucket
    # under the same label - the reader could not tell them apart (and the contract refused the file: a 500).
    frame = _shop()
    frame.loc[1, "Pay"] = written
    _, _, (split,) = _breakdowns(frame, ["Pay"])

    assert split.members == []
    assert split.withheld_reason == 'a value is written "(blank)", the label of the empty cells'


@pytest.mark.parametrize("column", ["line_class", "class_source", "suggested_class", "__flag_Qty"])
def test_a_column_stage_1_added_is_never_split(column: str) -> None:
    # Review 1 F4: stage 1's own columns (the line classes, its flags) are no column of the user's file.
    frame = _shop()
    # The three class columns come together (stage 1 writes all three); every line a sale.
    frame["line_class"], frame["class_source"], frame["suggested_class"] = "sale", "rule", None
    if column.startswith("__flag_"):
        frame[column] = ["a", "b", "a", "b", "a", "b", "a"]
    _, _, (split,) = _breakdowns(frame, [column])

    assert split.members == []
    assert split.withheld_reason == "the column was added by the cleaning, not read from your file"
