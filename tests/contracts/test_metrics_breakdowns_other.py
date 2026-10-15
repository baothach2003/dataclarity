"""metrics.json 16.4's "Other" member of a breakdown (Thach's Q3, 2026-10-15):
what the contract refuses, so no reader meets a fold that is not stage 2's."""

import copy
from datetime import UTC, datetime

import pandas as pd
import pytest
from pydantic import ValidationError

from contracts.metrics import ALL_SHOWN, TOP_SHOWN, MetricsContract, other_label
from stages.analyze.assemble import assemble_metrics

NOW = datetime(2026, 9, 19, 12, 0, tzinfo=UTC)
MAPPING = {"Date": "transaction_date", "Qty": "quantity", "Price": "unit_price", "Product": "product_name"}


def _data() -> dict:
    # Thirteen values of 1.00 in January and a December line: the top 8 and "Other (5 values)".
    rows = [{"Date": "2019-12-01", "Qty": "1", "Price": "1.0", "Product": "X", "Pay": "V00"}]
    rows += [{"Date": f"2020-01-{day:02d}", "Qty": "1", "Price": "1.0", "Product": "X", "Pay": f"V{day:02d}"}
             for day in range(1, 13)]
    rows.append({"Date": "2020-01-31", "Qty": "1", "Price": "1.0", "Product": "X", "Pay": None})
    return assemble_metrics(pd.DataFrame(rows), MAPPING, now=NOW, breakdowns=["Pay"]).model_dump(mode="json")


def _members(data: dict) -> list[dict]:
    return data["by_dimension"]["breakdowns"][0]["members"]


def _refused(data: dict, match: str) -> None:
    with pytest.raises(ValidationError, match=match):
        MetricsContract.model_validate(data)


def test_the_bounds() -> None:
    assert (ALL_SHOWN, TOP_SHOWN, other_label(5)) == (9, 8, "Other (5 values)")


def test_the_written_file_loads() -> None:
    members = MetricsContract.model_validate(_data()).by_dimension.breakdowns[0].members
    assert [m.name for m in members][-2:] == ["Other (5 values)", "(blank)"]


def test_a_count_on_a_member_that_is_not_other_is_refused() -> None:
    data = _data()
    _members(data)[0]["values"] = 3
    _refused(data, "only it, counts its values")


def test_other_without_its_count_is_refused() -> None:
    data = _data()
    _members(data)[-2]["values"] = None
    _refused(data, "only it, counts its values")


def test_other_named_otherwise_is_refused() -> None:
    data = _data()
    _members(data)[-2]["name"] = "Other (6 values)"
    _refused(data, "named 'Other \\(5 values\\)'")


def test_two_others_are_refused() -> None:
    data = _data()
    other = copy.deepcopy(_members(data)[-2])
    other.update(values=2, name="Other (2 values)", revenue_current=0.0, revenue_previous=0.0, change=0.0)
    _members(data).insert(0, other)
    _refused(data, "one Other member at most")


def test_other_beside_fewer_than_eight_values_is_refused() -> None:
    data = _data()
    del _members(data)[0]
    _refused(data, "exactly 8 values")


def test_ten_values_without_other_are_refused() -> None:
    data = _data()
    members = _members(data)
    other = members[-2]
    members[-2] = dict(other, name="V99", is_other=False, values=None)
    members.insert(0, dict(other, name="V98", is_other=False, values=None))
    _refused(data, "more than 9 values")


def test_a_count_of_one_is_refused() -> None:
    data = _data()
    _members(data)[-2].update(values=1, name="Other (1 values)")
    _refused(data, "values")


def test_other_in_a_16_3_file_is_refused() -> None:
    data = _data()
    data["schema_version"] = "16.3"
    _refused(data, "16.4")
