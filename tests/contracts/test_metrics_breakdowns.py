"""metrics.json 16.3's `by_dimension.breakdowns` (the dashboard's step 2): what
the contract refuses, so no reader meets a split that is not stage 2's."""

import copy
from datetime import UTC, datetime

import pandas as pd
import pytest
from pydantic import ValidationError

from contracts.metrics import MAX_BREAKDOWN_VALUES, MetricsContract
from stages.analyze.assemble import assemble_metrics

NOW = datetime(2026, 9, 19, 12, 0, tzinfo=UTC)
MAPPING = {"Date": "transaction_date", "Qty": "quantity", "Price": "unit_price", "Product": "product_name"}


def _frame(first_day: str = "2019-12-01") -> pd.DataFrame:
    return pd.DataFrame([
        {"Date": first_day, "Qty": "5", "Price": "10.0", "Product": "X", "Pay": "Cash"},
        {"Date": max(first_day, "2019-12-02"), "Qty": "5", "Price": "10.0", "Product": "X", "Pay": "Card"},
        {"Date": "2020-01-10", "Qty": "3", "Price": "10.0", "Product": "X", "Pay": "Cash"},
        {"Date": "2020-01-20", "Qty": "1", "Price": "5.0", "Product": "X", "Pay": None},
        {"Date": "2020-01-31", "Qty": "7", "Price": "10.0", "Product": "X", "Pay": "Card"},
    ])


def _data(first_day: str = "2019-12-01") -> dict:
    return assemble_metrics(_frame(first_day), MAPPING, now=NOW, breakdowns=["Pay"]).model_dump(mode="json")


def _refused(data: dict, match: str) -> None:
    with pytest.raises(ValidationError, match=match):
        MetricsContract.model_validate(data)


def test_the_written_file_loads() -> None:
    assert MetricsContract.model_validate(_data()).by_dimension.breakdowns[0].column == "Pay"


def test_the_bound_is_twelve() -> None:
    assert MAX_BREAKDOWN_VALUES == 12


def test_a_change_that_is_not_the_difference_is_refused() -> None:
    data = _data()
    data["by_dimension"]["breakdowns"][0]["members"][0]["change"] += 0.01
    _refused(data, "revenue_current - revenue_previous")


def test_a_null_change_without_its_reason_is_refused() -> None:
    data = _data()
    data["by_dimension"]["breakdowns"][0]["members"][0]["change"] = None
    _refused(data, "change")


def test_a_reason_beside_changes_is_refused() -> None:
    data = _data()
    data["by_dimension"]["breakdowns"][0]["change_reason"] = "why"
    _refused(data, "change")


def test_a_change_beside_an_incomplete_month_is_refused() -> None:
    data = _data("2019-12-05")
    assert data["period"]["previous_complete"] is False
    split = data["by_dimension"]["breakdowns"][0]
    split["change_reason"] = None
    for member in split["members"]:
        member["change"] = member["revenue_current"] - member["revenue_previous"]
    _refused(data, "incomplete")


def test_withheld_with_members_is_refused() -> None:
    data = _data()
    data["by_dimension"]["breakdowns"][0]["withheld_reason"] = "why"
    _refused(data, "withheld")


def test_not_withheld_without_members_is_refused() -> None:
    data = _data()
    data["by_dimension"]["breakdowns"][0]["members"] = []
    _refused(data, "withheld")


def test_two_blank_members_are_refused() -> None:
    data = _data()
    members = data["by_dimension"]["breakdowns"][0]["members"]
    members.append(copy.deepcopy(members[-1]))
    _refused(data, "blank")


def test_a_blank_member_with_another_name_is_refused() -> None:
    data = _data()
    data["by_dimension"]["breakdowns"][0]["members"][-1]["name"] = "Unknown"
    _refused(data, "blank")


def test_a_value_named_like_the_blank_bucket_is_refused() -> None:
    data = _data()
    data["by_dimension"]["breakdowns"][0]["members"][0]["name"] = "(blank)"
    _refused(data, "blank")


def test_a_repeated_name_is_refused() -> None:
    data = _data()
    members = data["by_dimension"]["breakdowns"][0]["members"]
    members[1]["name"] = members[0]["name"]
    _refused(data, "once")


def test_more_than_twelve_values_is_refused() -> None:
    data = _data()
    members = data["by_dimension"]["breakdowns"][0]["members"]
    model = members[0]
    members[:] = [dict(model, name=f"V{i}") for i in range(13)]
    _refused(data, "12")


def test_more_than_two_breakdowns_is_refused() -> None:
    data = _data()
    split = data["by_dimension"]["breakdowns"][0]
    data["by_dimension"]["breakdowns"] = [dict(split, column=c) for c in ("A", "B", "C")]
    _refused(data, "2")


def test_a_column_twice_is_refused() -> None:
    data = _data()
    split = data["by_dimension"]["breakdowns"][0]
    data["by_dimension"]["breakdowns"] = [split, copy.deepcopy(split)]
    _refused(data, "once")


def test_a_16_2_file_carrying_breakdowns_is_refused() -> None:
    data = _data()
    data["schema_version"] = "16.2"
    _refused(data, "16.3")


def test_a_16_2_file_without_the_field_still_loads() -> None:
    data = _data()
    data["schema_version"] = "16.2"
    del data["by_dimension"]["breakdowns"]
    assert MetricsContract.model_validate(data).by_dimension.breakdowns == []


def test_an_infinite_figure_is_refused() -> None:
    data = _data()
    data["by_dimension"]["breakdowns"][0]["members"][0]["revenue_current"] = float("inf")
    with pytest.raises(ValidationError):
        MetricsContract.model_validate(data)


def test_a_cleaning_report_with_three_breakdowns_is_refused() -> None:
    from contracts.cleaning import CleaningReportContract

    report = {"schema_version": "4.3", "generated_at": "2026-09-19T12:00:00Z", "rows_in": 1, "rows_out": 1,
              "columns_in": 1, "columns_out": 1, "changes": [], "warnings": [], "column_mapping": {}}
    assert CleaningReportContract.model_validate(report | {"breakdowns": ["A", "B"]}).breakdowns == ["A", "B"]
    with pytest.raises(ValidationError):
        CleaningReportContract.model_validate(report | {"breakdowns": ["A", "B", "C"]})


def test_a_cleaning_report_naming_a_column_twice_is_refused() -> None:
    # Review 1 F2: stage 2's own contract refuses a repeated column, so stage 1's does too (no 500 between them).
    from contracts.cleaning import CleaningReportContract

    report = {"schema_version": "4.3", "generated_at": "2026-09-19T12:00:00Z", "rows_in": 1, "rows_out": 1,
              "columns_in": 1, "columns_out": 1, "changes": [], "warnings": [], "column_mapping": {}}
    with pytest.raises(ValidationError, match="once"):
        CleaningReportContract.model_validate(report | {"breakdowns": ["Pay", "Pay"]})

def test_an_empty_list_is_not_written_so_stage_1s_file_is_unchanged() -> None:
    # The scoped review G1: a cleaning_report.json without a breakdown is exactly as before the field.
    from contracts.cleaning import CleaningReportContract

    report = {"schema_version": "4.3", "generated_at": "2026-09-19T12:00:00Z", "rows_in": 1, "rows_out": 1,
              "columns_in": 1, "columns_out": 1, "changes": [], "warnings": [], "column_mapping": {}}
    assert "breakdowns" not in CleaningReportContract.model_validate(report).model_dump(mode="json")
    assert CleaningReportContract.model_validate(report | {"breakdowns": ["A"]}).model_dump()["breakdowns"] == ["A"]
