"""report.json's contract, the rules its reviews added (5A reviews 2 #7 and
3 #9): what CONTRACTS 9 says the contract refuses, refused."""

from typing import Any

import pytest
from pydantic import ValidationError

from contracts.report import ReportContract
from tests.contracts.test_report import report_payload


def _numbers_rejected(payload: dict[str, Any], match: str) -> None:
    with pytest.raises(ValidationError, match=match):
        ReportContract.model_validate(payload)


# --- review 2 #7: what CONTRACTS 9 says the contract refuses, refused ---------------------------


def test_rejects_a_note_worded_otherwise_than_by_its_code() -> None:
    payload = report_payload()
    payload["layer_1_numbers"]["how_to_read"][0]["text"] = "Nothing to see here."
    _numbers_rejected(payload, "worded by its code")


def test_rejects_an_always_on_note_named_beside_a_figure() -> None:
    for place in ("kpi", "chart", "forecast", "actions"):
        payload = report_payload()
        target = {"kpi": payload["layer_1_numbers"]["kpis"][0], "chart": payload["charts"][0],
                  "forecast": payload["layer_3_actions"]["forecast"], "actions": payload["layer_3_actions"]}[place]
        target["notes"].append("discounts_in_prices")
        _numbers_rejected(payload, "named beside a figure but not shown")


def test_rejects_a_null_kpi_with_no_reason() -> None:
    payload = report_payload()
    payload["layer_1_numbers"]["kpis"][2]["current"] = None
    _numbers_rejected(payload, "a null figure carries its reason")
    payload = report_payload()
    payload["layer_1_numbers"]["kpis"][0].update(change_pct=None, change_reason=None)
    _numbers_rejected(payload, "revenue's change is null only with its reason")


def test_rejects_a_period_whose_reason_and_completeness_disagree() -> None:
    payload = report_payload()
    payload["layer_1_numbers"]["period"]["previous_incomplete_reason"] = "the previous month is incomplete"
    _numbers_rejected(payload, "previous_incomplete_reason says why")
    payload = report_payload()
    payload["layer_1_numbers"]["period"]["previous_complete"] = False
    _numbers_rejected(payload, "previous_incomplete_reason says why")


def test_rejects_a_month_with_revenue_and_a_reason_for_none() -> None:
    payload = report_payload()
    payload["layer_1_numbers"]["revenue_by_month"][0]["revenue_reason"] = "no line"
    _numbers_rejected(payload, "null exactly when its reason says why")


def test_rejects_months_out_of_order_or_twice() -> None:
    payload = report_payload()
    months = payload["layer_1_numbers"]["revenue_by_month"]
    months[0], months[1] = months[1], months[0]
    _numbers_rejected(payload, "listed once each, in order")


def test_rejects_a_chart_that_plots_other_figures_than_the_reports() -> None:
    payload = report_payload()
    payload["charts"][0]["series"][0]["y"][1] = 999.0
    _numbers_rejected(payload, "revenue chart plots 2011-10")
    payload = report_payload()
    payload["charts"][0]["series"][0].update(x=["2011-09", "2011-10", "2011-11", "2011-12"],
                                             y=[1000000.0, 1290000.0, 1150000.0, 0.0])
    _numbers_rejected(payload, "revenue chart plots 2011-12")
    payload = report_payload()
    payload["charts"][1]["series"][1]["y"][0] = 1.0
    _numbers_rejected(payload, "forecast chart plots the forecast's own low")


def test_rejects_a_first_forecast_month_in_the_file_with_no_forecast_or_another_day() -> None:
    payload = report_payload()
    forecast = payload["layer_3_actions"]["forecast"]
    forecast["partial_first_month_until"] = "2011-07-04"
    _numbers_rejected(payload, "the day the file ends in the first forecast month")
    payload = report_payload()
    payload["layer_3_actions"]["forecast"].update(points=[], partial_first_month_until=None)
    payload["charts"] = payload["charts"][:1]
    _numbers_rejected(payload, "first_month_in_file needs a forecast month")


# --- review 3 #9: the rest of what CONTRACTS 9 says the contract refuses ------------------------


def test_rejects_a_chart_the_report_does_not_define() -> None:
    payload = report_payload()
    payload["charts"].append(payload["charts"][0] | {"id": "revenue"})
    _numbers_rejected(payload, "charts.2.id")


def test_rejects_a_revenue_chart_joined_across_a_month_or_reversed() -> None:
    payload = report_payload()
    series = payload["charts"][0]["series"][0]
    series.update(x=[series["x"][0], series["x"][2]], y=[series["y"][0], series["y"][2]])
    _numbers_rejected(payload, "never a join")
    payload = report_payload()
    series = payload["charts"][0]["series"][0]
    series.update(x=series["x"][::-1], y=series["y"][::-1])
    _numbers_rejected(payload, "never a join")


def test_rejects_a_note_listed_twice() -> None:
    payload = report_payload()
    how_to_read = payload["layer_1_numbers"]["how_to_read"]
    how_to_read.append(how_to_read[0])
    _numbers_rejected(payload, "shown once in a list")


def test_rejects_a_kpi_set_other_than_the_five() -> None:
    payload = report_payload()
    kpis = payload["layer_1_numbers"]["kpis"]
    kpis[1] = kpis[0]
    _numbers_rejected(payload, "once each, in that order")


def test_rejects_a_period_whose_months_or_days_do_not_follow() -> None:
    payload = report_payload()
    payload["layer_1_numbers"]["period"]["previous"] = "2011-07"
    _numbers_rejected(payload, "the one before the current")
    payload = report_payload()
    payload["layer_1_numbers"]["period"]["data_start"] = "2012-01-01"
    _numbers_rejected(payload, "starts before it ends")


def test_rejects_a_forecast_of_other_months_or_a_wrong_first_month() -> None:
    payload = report_payload()
    forecast = payload["layer_3_actions"]["forecast"]
    for point, month in zip(forecast["points"], ("2013-01", "2013-02", "2013-03")):
        point["period"] = month
    forecast.update(first_month_in_file=False, partial_first_month_until=None)
    payload["charts"] = payload["charts"][:1]
    _numbers_rejected(payload, "not the month after 2011-11")
    payload = report_payload()
    payload["layer_3_actions"]["forecast"].update(first_month_in_file=False, partial_first_month_until=None)
    _numbers_rejected(payload, "whether the file ends inside the first forecast month")
    payload = report_payload()
    payload["layer_3_actions"]["forecast"]["partial_first_month_until"] = "2011-12-25"
    _numbers_rejected(payload, "the day the file ends")


def test_the_month_after_crosses_the_year() -> None:
    from contracts.report_views import month_after

    assert [month_after(m) for m in ("2011-11", "2011-12", "2012-01")] == ["2011-12", "2012-01", "2012-02"]


def test_rejects_a_note_named_twice_beside_one_figure() -> None:
    from tests.contracts.test_metrics import metrics_payload
    from tests.stages.report.report_fixtures import REVENUE_NOTE, build, metrics_data

    def with_revenue_note() -> dict[str, Any]:
        metrics = metrics_data(notes=metrics_payload()["core"]["notes"] + [REVENUE_NOTE])
        payload: dict[str, Any] = build(metrics=metrics).model_dump(mode="json")
        return payload

    for place in ("kpi", "chart", "forecast", "actions"):
        payload = with_revenue_note()
        target = {"kpi": payload["layer_1_numbers"]["kpis"][0], "chart": payload["charts"][0],
                  "forecast": payload["layer_3_actions"]["forecast"], "actions": payload["layer_3_actions"]}[place]
        assert target["notes"] == ["unconfirmed_suggestions"]
        target["notes"].append("unconfirmed_suggestions")
        _numbers_rejected(payload, "shown once in a list")


def test_rejects_a_file_note_twice_in_the_numbers_or_the_causes() -> None:
    from tests.contracts.test_metrics import metrics_payload
    from tests.stages.report.report_fixtures import SAME_DAY, build, metrics_data

    payload: dict[str, Any] = build(metrics=metrics_data(
        notes=metrics_payload()["core"]["notes"] + [SAME_DAY])).model_dump(mode="json")
    payload["layer_1_numbers"]["notes"].append(payload["layer_1_numbers"]["notes"][0])
    _numbers_rejected(payload, "shown once in a list")
    payload = build(metrics=metrics_data(notes=metrics_payload()["core"]["notes"] + [SAME_DAY])).model_dump(mode="json")
    payload["layer_2_causes"]["notes"] = payload["layer_1_numbers"]["notes"] * 2
    _numbers_rejected(payload, "shown once in a list")


def test_rejects_the_kpis_out_of_order() -> None:
    payload = report_payload()
    kpis = payload["layer_1_numbers"]["kpis"]
    kpis[1], kpis[2] = kpis[2], kpis[1]
    _numbers_rejected(payload, "once each, in that order")


def test_rejects_a_chart_twice_a_second_series_joined_or_a_forecast_series_of_its_own() -> None:
    payload = report_payload()
    payload["charts"].append(payload["charts"][0])
    _numbers_rejected(payload, "each chart is drawn once")
    payload = report_payload()
    first = payload["charts"][0]["series"][0]
    payload["charts"][0]["series"].append(first | {"name": "again", "x": first["x"][::-1], "y": first["y"][::-1]})
    _numbers_rejected(payload, "never a join")
    payload = report_payload()
    point = payload["charts"][1]["series"][0]
    payload["charts"][1]["series"].append(point | {"name": "confidence", "y": [0.8] * len(point["x"])})
    _numbers_rejected(payload, "not 'confidence'")
