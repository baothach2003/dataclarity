"""Report redesign step 1 (Thach, 2026-10-05): metrics.json 16.2's
`core.revenue_change` - the summary's change amount, which existed only
inside stage 3's headline text (docs/REPORT_REDESIGN.md section 2; method
C:/Users/Happy/redesign-step1-method.txt M1).

Null with the period's reason exactly when the previous month is
incomplete (CONTRACTS 11: an incomplete month is never compared), and not
otherwise - an amount needs no base, unlike the percentage."""

from datetime import date

import pandas as pd
import pytest
from pydantic import ValidationError

from contracts.metrics import MetricsContract
from stages.analyze.assemble import SCHEMA_VERSION, assemble_metrics
from tests.stages.diagnose.diagnose_fixtures import MAPPING, NOW, full_months, row, run_data


def _metrics(rows: list[dict]) -> MetricsContract:
    return assemble_metrics(pd.DataFrame(rows), MAPPING, now=NOW)


def test_the_change_is_this_month_less_last_month() -> None:
    # The Kaggle run's two compared months (December 2024 against November).
    metrics = _metrics(full_months({"2024-10": 41_399.5, "2024-11": 41_367.5, "2024-12": 46_292.5}))

    assert (metrics.period.previous, metrics.period.current) == ("2024-11", "2024-12")
    assert metrics.core.revenue_change == 4_925.0
    assert metrics.core.revenue_change_reason is None


def test_a_fall_is_negative() -> None:
    metrics = _metrics(full_months({"2024-10": 500.0, "2024-11": 800.0, "2024-12": 650.0}))

    assert metrics.core.revenue_change == -150.0


def test_a_non_positive_base_still_has_its_amount() -> None:
    # The percentage is null here (no base); the amount is not: it needs none. November nets -50: a sale
    # of 100 and a return of 150.
    rows = [row(date(2024, 10, 1), qty=30.0), row(date(2024, 11, 2), qty=10.0),
            row(date(2024, 11, 20), qty=-15.0), row(date(2024, 12, 31), qty=25.0)]
    metrics = _metrics(rows)

    assert metrics.period.previous_complete is True
    assert metrics.core.revenue_previous == -50.0
    assert metrics.core.revenue_change_pct is None
    assert metrics.core.revenue_change == 300.0
    assert metrics.core.revenue_change_reason is None


def test_an_incomplete_previous_month_has_no_change_and_says_why() -> None:
    # An export that starts on 15 November: November is half a month.
    rows = [row(date(2024, 11, 15)), row(date(2024, 12, 1)), row(date(2024, 12, 31))]
    metrics = _metrics(rows)

    assert metrics.period.previous_complete is False
    assert metrics.core.revenue_change is None
    assert metrics.core.revenue_change_reason == metrics.period.previous_incomplete_reason


def test_the_version_is_16_2() -> None:
    assert SCHEMA_VERSION == "16.2"  # 16.2: core.revenue_change (the report redesign, step 1); 16.1 in 2E-u6


def _dump(**core: object) -> dict:
    data = _metrics(full_months({"2024-10": 500.0, "2024-11": 800.0, "2024-12": 650.0})).model_dump(mode="json")
    data["core"].update(core)
    return data


def test_a_16_2_file_without_the_change_is_refused() -> None:
    with pytest.raises(ValidationError, match="revenue_change"):
        MetricsContract.model_validate(_dump(revenue_change=None))


def test_a_change_that_is_not_the_two_months_difference_is_refused() -> None:
    with pytest.raises(ValidationError, match="revenue_change"):
        MetricsContract.model_validate(_dump(revenue_change=-149.0))


def test_a_change_beside_an_incomplete_month_is_refused() -> None:
    rows = [row(date(2024, 11, 15)), row(date(2024, 12, 1)), row(date(2024, 12, 31))]
    data = _metrics(rows).model_dump(mode="json")
    data["core"].update(revenue_change=0.0, revenue_change_reason=None)

    with pytest.raises(ValidationError):
        MetricsContract.model_validate(data)


def test_an_incomplete_month_with_another_reason_is_refused() -> None:
    rows = [row(date(2024, 11, 15)), row(date(2024, 12, 1)), row(date(2024, 12, 31))]
    data = _metrics(rows).model_dump(mode="json")
    data["core"]["revenue_change_reason"] = "some other reason"

    with pytest.raises(ValidationError, match="period's reason"):
        MetricsContract.model_validate(data)


def test_a_complete_month_with_a_reason_is_refused() -> None:
    with pytest.raises(ValidationError, match="no reason"):
        MetricsContract.model_validate(_dump(revenue_change_reason="why"))


def test_stage_3s_lever_months_are_stage_2s_revenue() -> None:
    # Stage 3 recomputes each month (shared/transactions): the bridge's ends are stage 2's figures.
    from stages.diagnose.assemble import diagnose

    rows = full_months({"2024-10": 500.0, "2024-11": 800.0, "2024-12": 650.0})
    metrics = _metrics(rows)
    bridge = diagnose(run_data(rows), NOW).tree.lever.bridge

    assert (bridge.revenue_previous, bridge.revenue_current) == (metrics.core.revenue_previous,
                                                                 metrics.core.revenue_current)
    assert bridge.change == metrics.core.revenue_change


def test_a_16_1_file_without_the_field_still_loads() -> None:
    data = _dump()
    data["schema_version"] = "16.1"
    del data["core"]["revenue_change"], data["core"]["revenue_change_reason"]

    assert MetricsContract.model_validate(data).core.revenue_change is None
