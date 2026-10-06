"""Session 5B, review 2's cases: signals named as the KPIs are, floored
limits said so, a suggested product marked where the evidence names it,
nothing filled in that report.json does not say, and every wording and
format of the page pinned."""

from typing import Any

import pytest

from contracts.report import ReportContract
from stages.report.html_parts import change, count, money, number, one_decimal
from stages.report.html_report import render_html
from tests.contracts.test_diagnosis import diagnosis_payload
from tests.contracts.test_forecast import forecast_payload
from tests.contracts.test_metrics import metrics_payload
from tests.contracts.test_metrics_reasons import _partial
from tests.stages.report.html_probe import Page
from tests.stages.report.report_fixtures import REVENUE_NOTE, SAME_DAY, build, metrics_data


def _signal(series: str, mode: str = "level", signal: str = "within", rule: int | None = None,
            values: tuple[float | None, ...] = (1.0, 1.0, 0.0, 2.0), **extra: Any) -> dict[str, Any]:
    cur, center, lower, upper = values
    return {"series": series, "mode": mode, "value_cur": cur, "center": center, "lower": lower, "upper": upper,
            "signal": signal, "rule": rule, "limits_method": "median_moving_range"} | extra


def _causes(*signals: dict[str, Any], metrics: dict[str, Any] | None = None) -> str:
    diagnosis = diagnosis_payload()
    diagnosis["signals"] = list(signals)
    return Page(render_html(build(metrics=metrics, diagnosis=diagnosis))).section("causes")


def test_a_signal_is_named_as_the_kpis_are() -> None:
    # 5B review 2 #2: lines, not orders, on a file with no order numbers.
    lines = metrics_data(orders_basis="lines", orders_basis_reason="no column holds an order number")
    causes = _causes(*(_signal(s) for s in ("orders", "frequency", "aov", "units_per_order", "return_rate")),
                     metrics=lines)
    for label in ("Lines level", "Lines per customer level", "Average line value level", "Units per line level",
                  "Return lines per sale line level"):
        assert label in causes
    assert "Orders" not in causes.split("Where this month sits")[1]
    orders = _causes(*(_signal(s) for s in ("orders", "frequency", "units_per_order", "price_per_unit",
                                             "active_customers")))
    for label in ("Orders level", "Orders per customer level", "Units per order level", "Price per unit level",
                  "Active customers level"):
        assert label in orders
    # Money on a level row, as the KPI (review 2 #3).
    assert "Average order value level 1.00 1.00 0.00 2.00" in _causes(_signal("aov"))


def test_floored_limits_are_told_apart_from_measured_ones() -> None:
    # 5B review 2 #1 (CONTRACTS 7): no variation measured, a floor used.
    causes = _causes(_signal("return_rate", values=(0.0, 0.0, -0.01, 0.01), limits_method="minimum_spread"),
                     _signal("revenue", values=(1150000.0, 1240000.0, 1090000.0, 1390000.0)))
    assert ("Return rate level - floor limits: no variation measured 0.000 0.000 -0.010 0.010 within the limits"
            in causes)
    assert "Revenue level 1,150,000.00 1,240,000.00 1,090,000.00 1,390,000.00 within the limits" in causes


def test_every_signal_wording_and_unit() -> None:
    # 5B review 2 #3: no verdict word, each rule and reason as written.
    causes = _causes(
        _signal("revenue", signal="below", rule=2, values=(900.0, 1000.0, 800.0, 1200.0)),
        _signal("orders", values=(None, None, None, None), signal="insufficient_history",
                insufficient_reason="no_current_value"),
        _signal("aov", values=(None, None, None, None), signal="insufficient_history",
                insufficient_reason="no_measurable_spread"),
        _signal("active_customers", values=(812.0, 850.5, 700.0, 1000.0), mode_fallback="no_year_ago_value"),
        _signal("frequency", values=(1.23456, 1.2, 1.0, 1.4)),
        _signal("price_per_unit", values=(2.5, 2.4, 2.0, 2.8)),
        _signal("units_per_order", values=(10.5, 10.0, 9.0, 11.0)))
    for row in ("Revenue level 900.00 1,000.00 800.00 1,200.00 below the centre for a run of months",
                "Orders level no chart: no value this month", "Average order value level no chart: no measurable spread",
                "Active customers level (no year ago value) 812.0 850.5 700.0 1,000.0 within the limits",
                "Orders per customer level 1.235 1.200 1.000 1.400", "Price per unit level 2.50 2.40 2.00 2.80",
                "Units per order level 10.500 10.000 9.000 11.000"):
        assert row in causes
    table = causes.split("Series Chart This month")[1]
    for verdict in ("normal", "unusual"):
        assert verdict not in table
    diagnosis = diagnosis_payload()
    diagnosis["trust"]["verdict"] = "blocked"
    diagnosis.update({"calendar": None, "signals": None, "tree": None, "localization": None})
    diagnosis["headline"] = {"rule": 1, "hypothesis_id": None, "lens": None, "message": "Not trusted."}
    page = Page(render_html(build(diagnosis=diagnosis)))
    assert "The signals were not measured for this run." in page.section("causes")
    assert "Data trust: blocked - the figures below are not a base for conclusions" in page.section("numbers")


def test_nothing_is_filled_in_that_the_row_does_not_say() -> None:
    # 5B review 2 #10: a rule or a reason the row leaves null stays unsaid.
    payload: dict[str, Any] = build().model_dump(mode="json")
    payload["layer_2_causes"]["signals"] = [
        payload["layer_2_causes"]["signals"][0] | {"signal": "above", "rule": None},
        payload["layer_2_causes"]["signals"][0] | {"signal": "insufficient_history", "value_cur": None, "center": None,
                                                    "lower": None, "upper": None, "insufficient_reason": None}]
    causes = Page(render_html(ReportContract.model_validate(payload))).section("causes")
    assert "1,390,000.00 above Revenue level no chart" in causes and "no chart:" not in causes


def test_a_product_with_an_unconfirmed_class_is_marked_where_the_evidence_names_it() -> None:
    # 5B review 2 #9 (CONTRACTS 6 and 7): "(suggested: <class>, not confirmed)".
    diagnosis = diagnosis_payload()
    diagnosis["localization"]["dimensions"].append({
        "name": "product", "members": [], "other": {"name": "Other", "rev_prev": 0.0, "rev_cur": 0.0, "delta": 0.0,
                                                     "share_of_change": 0.0},
        "new_members": ["POSTAGE"], "removed_members": []})
    diagnosis["suggested_classes"] = {"POSTAGE": "charge"}
    diagnosis["hypotheses"][0]["evidence"] |= {"top_member": "POSTAGE", "products": [{"product": "POSTAGE"}]}
    causes = Page(render_html(build(diagnosis=diagnosis))).section("causes")
    assert "top_member: POSTAGE (suggested: charge, not confirmed)" in causes
    assert 'products: [{"product": "POSTAGE (suggested: charge, not confirmed)"}]' in causes


def test_the_wordings_of_the_page_as_written() -> None:
    # 5B review 2 #3: the not-testable reason, no recommendation, the band's
    # name in the legend, a note's orders, the causes' notes by the rule.
    page = Page(render_html(build()))
    assert "Marketing, promotions, discounts: no campaign data; discount columns are not canonical" in page.section(
        "causes")
    assert '"name":"80% band"' in next(s for s in page.scripts if '"chart-forecast"' in s)
    forecast = forecast_payload() | {"model_used": None, "recommendations": None, "do_not_do": None}
    assert ("No AI writes recommendations in this version: suggested actions, when there are any, are written by "
            "code in section 4." in Page(render_html(build(forecast=forecast))).section("actions"))
    notes = metrics_payload()["core"]["notes"] + [SAME_DAY]
    assert "returns file 10 -345.50 5" in Page(render_html(build(metrics=metrics_data(notes=notes)))).section(
        "numbers")
    diagnosis = diagnosis_payload()
    diagnosis["notes"].append(SAME_DAY)  # the diagnosis's own, not the numbers'
    causes = Page(render_html(build(metrics=_partial(metrics_data()), diagnosis=diagnosis))).section("causes")
    assert "returns current 10" in causes and "returns previous" not in causes


def test_the_period_line_never_says_compared_when_nothing_is() -> None:
    # 5B review 2 #12.
    metrics = metrics_data(months=(("2011-09", 1000000.0), ("2011-10", 1290000.0), ("2011-12", 300000.0)))
    numbers = Page(render_html(build(metrics=metrics))).section("numbers")
    assert "2011-11 against 2011-10: the current month's figures are withheld (see below)." in numbers
    assert "compared with" not in numbers.split("Data trust")[0]


def test_a_real_amount_of_a_withheld_month_stands() -> None:
    # 5B review 2 #8: only a withheld month's 0 is hidden.
    non_product = [{"line_class": "cost", "lines": 11, "amount": -26337.21, "amount_current": -8788.49,
                    "amount_previous": -5977.22, "reason": "a cost, left out of revenue"}]
    metrics = metrics_data(months=(("2011-09", 1000000.0), ("2011-10", 1290000.0), ("2011-12", 300000.0)),
                           non_product=non_product)
    assert "cost 11 -26,337.21 -8,788.49 -5,977.22" in Page(render_html(build(metrics=metrics))).section("numbers")


def test_no_forecast_no_forecast_notes_and_a_caution_the_gap_note_says_once() -> None:
    # 5B review 2 #6 and #11.
    forecast = forecast_payload()
    forecast["forecast"].update({"revenue": [], "horizon_periods": 0, "insufficient_history": True,
                                 "months_used": 2, "season_note": None, "season_years": None})
    metrics = metrics_data(notes=metrics_payload()["core"]["notes"] + [REVENUE_NOTE])
    actions = Page(render_html(build(metrics=metrics, forecast=forecast))).section("actions")
    assert "Read the forecast with" not in actions
    payload: dict[str, Any] = build().model_dump(mode="json")
    payload["charts"][0]["note"] = "2011-10 is not drawn: the file has no sales in 2011-10."
    payload["charts"][0]["cautions"] = ["The file has no sales in 2011-10."]
    numbers = Page(render_html(ReportContract.model_validate(payload))).section("numbers")
    assert "Caution: The file has no sales" not in numbers


def test_formats_as_written() -> None:
    # 5B review 2 #3, #7, #13.
    assert (number(150.0), number(500.0), number(99.5), number(0.017439)) == ("150.00", "500.00", "99.5", "0.01744")
    assert (one_decimal(-0.04), count(-0.4), change(12345.6)) == ("0.0", "0", "+12,345.6%")
    assert (money(float("-inf")), change(float("-inf"))) == ("-inf", "-inf%")


@pytest.mark.parametrize("month", ["2011-13", "٢٠١١-09", "2011-9"])
def test_a_chart_month_is_ascii_yyyy_mm(month: str) -> None:
    report = build()
    report.charts[0].series[0].x[0] = month
    with pytest.raises(ValueError, match="months"):
        render_html(report)


def test_a_forecast_shown_without_its_chart_keeps_its_notes_beside_it() -> None:
    # The chart carries them when drawn; without it the table does (review 2 #4).
    metrics = metrics_data(notes=metrics_payload()["core"]["notes"] + [REVENUE_NOTE])
    payload: dict[str, Any] = build(metrics=metrics).model_dump(mode="json")
    payload["charts"] = payload["charts"][:1]
    actions = Page(render_html(ReportContract.model_validate(payload))).section("actions")
    assert "Read the forecast with: unconfirmed suggestions" in actions
