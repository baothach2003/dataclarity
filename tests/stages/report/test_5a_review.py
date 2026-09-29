"""Session 5A, review 1's cases for layers 1 and 2: the report built for
every run the earlier stages can produce - an incomplete or nearly whole
previous month, a month with no line, a blocked diagnosis, no customer
column, lines in no figure - and every field a null figure's reason rides
on. Layer 3 and the file: test_5a_review_actions.py.
"""

import json

from stages.report.layers import NO_CUSTOMER_COLUMN, NO_LINE_IN_MONTH
from tests.contracts.test_cleaning import report_payload as cleaning_report_payload
from tests.contracts.test_diagnosis import diagnosis_payload
from tests.contracts.test_metrics import metrics_payload
from tests.contracts.test_metrics_reasons import REASON, _partial
from tests.stages.report.report_fixtures import REVENUE_NOTE, SAME_DAY, build, metrics_data

# --- the months: the chart and the KPIs agree ---------------------------------------------------


def test_a_previous_month_the_kpis_do_not_compare_is_not_drawn_complete() -> None:
    # Review 1 #1: sales from 16 October, one refund dated 1 October - every
    # month from data_start is "covered", but stage 2 withholds October.
    metrics = _partial(metrics_data(months=(("2011-10", 310693.43), ("2011-11", 654527.09),
                                            ("2011-12", 170647.13))))
    metrics["period"]["data_start"] = "2011-10-01"
    report = build(metrics=metrics)
    months = report.layer_1_numbers.revenue_by_month
    assert [(m.period, m.complete) for m in months] == [("2011-10", False), ("2011-11", True), ("2011-12", False)]
    trend = report.charts[0]
    assert (trend.series[0].x, trend.series[0].y, trend.note) == (["2011-11"], [654527.09], None)


def test_a_month_either_definition_calls_partial_is_never_drawn_whole() -> None:
    # Review 2 #3, reversing review 1's fold-in: a file from 2 October - the
    # KPIs compare with October (stage 2 tolerates two missing leading days,
    # shared/periods), but stage 3's history and the forecast do not count
    # it (complete_months). The chart claims no more than either: October is
    # not drawn; the KPIs still compare (8D).
    metrics = metrics_data(months=(("2011-10", 515060.53), ("2011-11", 654527.09), ("2011-12", 170647.13)))
    metrics["period"]["data_start"] = "2011-10-02"
    report = build(metrics=metrics)
    assert [(m.period, m.complete) for m in report.layer_1_numbers.revenue_by_month][:2] == [
        ("2011-10", False), ("2011-11", True)]
    assert report.charts[0].series[0].x == ["2011-11"]
    assert report.layer_1_numbers.kpis[0].previous == 1290000.0


def test_a_month_grain_file_dated_on_month_ends_covers_its_first_month() -> None:
    # 2E-o: a line dated 30 September stands for September.
    metrics = metrics_data(months=(("2011-09", 1000000.0), ("2011-10", 1290000.0), ("2011-11", 1150000.0)))
    metrics["period"] |= {"month_grain": True, "data_start": "2011-09-30", "data_end": "2011-11-30"}
    months = build(metrics=metrics).layer_1_numbers.revenue_by_month
    assert [(m.period, m.complete) for m in months] == [("2011-09", True), ("2011-10", True), ("2011-11", True)]


def test_a_month_with_no_line_is_a_gap_with_its_reason_never_a_zero_or_a_join() -> None:
    # Review 1 #4 (the standing rule): August to November, September absent.
    metrics = metrics_data(months=(("2011-08", 900000.0), ("2011-10", 1290000.0), ("2011-11", 1150000.0),
                                   ("2011-12", 300000.0)))
    report = build(metrics=metrics)
    september = report.layer_1_numbers.revenue_by_month[1]
    assert (september.period, september.revenue, september.revenue_reason, september.complete) == (
        "2011-09", None, NO_LINE_IN_MONTH, True)
    trend = report.charts[0]
    assert (trend.series[0].x, trend.series[0].y) == (
        ["2011-08", "2011-09", "2011-10", "2011-11"], [900000.0, None, 1290000.0, 1150000.0])
    assert trend.note == ("No line counted in revenue is dated in 2011-09: a closed month or missing data, which "
                          "the file cannot tell apart.")


def test_a_run_of_months_with_no_line_is_named_once() -> None:
    # Review 2 #9: a stray date years back must not list every month.
    metrics = metrics_data(months=(("2011-05", 900000.0), ("2011-09", 1000000.0), ("2011-10", 1290000.0),
                                   ("2011-11", 1150000.0)))
    trend = build(metrics=metrics).charts[0]
    assert trend.series[0].y == [900000.0, None, None, None, 1000000.0, 1290000.0, 1150000.0]
    assert trend.note == ("No line counted in revenue is dated in 2011-06 to 2011-08 (3 months): a closed month or "
                          "missing data, which the file cannot tell apart.")


def test_the_chart_starts_and_ends_at_a_month_it_draws() -> None:
    # Review 2 #9: never a leading or trailing gap; no month drawn, said so.
    metrics = metrics_data(months=(("2011-08", 900000.0), ("2011-10", 1290000.0), ("2011-11", 1150000.0)))
    metrics["period"]["data_start"] = "2011-08-15"
    trend = build(metrics=metrics).charts[0]
    assert (trend.series[0].x, trend.note) == (["2011-10", "2011-11"], None)
    metrics = _partial(metrics_data(months=(("2011-10", 1290000.0), ("2011-11", 1150000.0))))
    metrics["period"] |= {"data_start": "2011-10-16", "data_end": "2011-11-20"}
    trend = build(metrics=metrics).charts[0]
    assert (trend.series[0].x, trend.note) == (
        [], "No month of the file is covered whole and holds revenue, so none is drawn.")


def test_an_incomplete_month_inside_the_chart_is_a_gap_with_its_own_reason() -> None:
    # Review 2 #4: inside the chart only the compared month can be withheld,
    # and its reason is the KPIs' own.
    metrics = _partial(metrics_data())
    trend = build(metrics=metrics).charts[0]
    assert (trend.series[0].x, trend.series[0].y) == (
        ["2011-09", "2011-10", "2011-11"], [1000000.0, None, 1150000.0])
    assert trend.note == f"2011-10 is not drawn: {REASON}."


def test_the_charts_carry_the_notes_naming_revenue() -> None:
    metrics = metrics_data(notes=metrics_payload()["core"]["notes"] + [REVENUE_NOTE, SAME_DAY])
    assert [c.notes for c in build(metrics=metrics).charts] == [["unconfirmed_suggestions"]] * 2


# --- the numbers: every reason reaches the report -----------------------------------------------


def test_the_trust_badge_carries_its_checks_reasons() -> None:
    # Review 1 #2: a caution beside the KPIs says why (CONTRACTS 6).
    check = diagnosis_payload()["trust"]["checks"][0]
    trust = build().layer_1_numbers.trust
    assert [(c.id, c.status, c.message) for c in trust.checks] == [("D1", "caution", check["message"])]


def test_a_null_kpi_carries_its_reason() -> None:
    # No sale in the current month: AOV and the return rate have no base.
    metrics = metrics_data(orders_current=0, aov_current=None, aov_current_reason="no order in the current month",
                           return_rate_current=None, return_rate_current_reason="no sale line in the current month")
    kpis = {k.id: k for k in build(metrics=metrics).layer_1_numbers.kpis}
    assert (kpis["aov"].current, kpis["aov"].current_reason) == (None, "no order in the current month")
    assert (kpis["return_rate"].current, kpis["return_rate"].current_reason) == (
        None, "no sale line in the current month")


def test_a_null_previous_kpi_carries_its_reason() -> None:
    metrics = metrics_data(orders_previous=0, aov_previous=None, aov_previous_reason="no order in the previous month",
                           return_rate_previous=None, return_rate_previous_reason="no sale line in the previous month")
    kpis = {k.id: k for k in build(metrics=metrics).layer_1_numbers.kpis}
    assert (kpis["aov"].previous, kpis["aov"].previous_reason) == (None, "no order in the previous month")
    assert (kpis["return_rate"].previous, kpis["return_rate"].previous_reason) == (
        None, "no sale line in the previous month")


def test_revenues_change_carries_its_reason_when_comparable() -> None:
    metrics = metrics_data(revenue_change_pct=None, revenue_change_pct_reason="the previous month netted zero")
    revenue = build(metrics=metrics).layer_1_numbers.kpis[0]
    assert (revenue.change_pct, revenue.change_reason) == (None, "the previous month netted zero")


def test_a_file_without_order_numbers_says_return_lines_per_sale_line() -> None:
    # Review 1 #7: CONTRACTS 6 labels the basis-lines return rate so.
    metrics = metrics_data(orders_basis="lines", orders_basis_reason="no column holds an order number")
    kpis = {k.id: (k.label, k.unit) for k in build(metrics=metrics).layer_1_numbers.kpis}
    assert kpis["return_rate"] == ("Return lines per sale line", "ratio")


def test_counts_stay_whole_numbers() -> None:
    # Review 1 #15: metrics.json's counts are ints.
    dumped = json.loads(build().model_dump_json())["layer_1_numbers"]["kpis"]
    assert [(k["id"], k["current"]) for k in dumped[1:3]] == [("orders", 1820), ("active_customers", 812)]
    assert isinstance(dumped[1]["current"], int) and isinstance(dumped[0]["current"], float)


def test_a_file_with_no_customer_column_shows_the_reason_never_a_zero() -> None:
    # Review 1 #9: stage 2 counts 0 customers when no column holds one.
    metrics = metrics_data(active_customers_current=0, active_customers_previous=0)
    customers = build(metrics=metrics, cleaning=cleaning_report_payload()).layer_1_numbers.kpis[2]
    assert (customers.current, customers.previous, customers.current_reason, customers.previous_reason) == (
        None, None, NO_CUSTOMER_COLUMN, NO_CUSTOMER_COLUMN)
    incomplete = build(metrics=_partial(metrics), cleaning=cleaning_report_payload()).layer_1_numbers.kpis[2]
    assert (incomplete.current_reason, incomplete.previous_reason) == (NO_CUSTOMER_COLUMN, REASON)


def test_a_month_whose_lines_name_no_customer_shows_the_reason_never_a_zero() -> None:
    # Review 2 #5: the column is mapped but blank on every line of the month.
    metrics = metrics_data(active_customers_current=0)
    customers = build(metrics=metrics).layer_1_numbers.kpis[2]
    assert (customers.current, customers.current_reason, customers.previous) == (
        None, "no line in 2011-11 names a customer", 905)
    customers = build(metrics=metrics_data(active_customers_previous=0)).layer_1_numbers.kpis[2]
    assert (customers.current, customers.previous, customers.previous_reason) == (
        812, None, "no line in 2011-10 names a customer")


def test_a_refunds_only_current_month_names_no_customer_either() -> None:
    # Review 3 #3: a month with lines but no sale - its 0 customers count no
    # buyers, they say its lines name nobody (withheld, not a real 0).
    refunds_only = {"orders_current": 0, "active_customers_current": 0, "aov_current": None,
                    "aov_current_reason": "no order in the current month", "return_rate_current": None,
                    "return_rate_current_reason": "no sale line in the current month"}
    customers = build(metrics=metrics_data(**refunds_only)).layer_1_numbers.kpis[2]
    assert (customers.current, customers.current_reason) == (None, "no line in 2011-11 names a customer")
    customers = build(metrics=metrics_data(**refunds_only), cleaning=cleaning_report_payload()).layer_1_numbers.kpis[2]
    assert (customers.current, customers.current_reason) == (None, NO_CUSTOMER_COLUMN)


def test_a_current_month_with_no_line_shows_no_figure_but_its_reason() -> None:
    # Review 2 #1 (the standing rule): stage 2 writes 0 for a month holding
    # no line counted in revenue - a closed month or missing data.
    metrics = metrics_data(months=(("2011-09", 1000000.0), ("2011-10", 1290000.0), ("2011-12", 300000.0)))
    kpis = build(metrics=metrics).layer_1_numbers.kpis
    reason = ("no line counted in revenue is dated in 2011-11 - a closed month or missing data, which the file "
              "cannot tell apart")
    assert all((k.current, k.current_reason) == (None, reason) for k in kpis)
    assert (kpis[0].previous, kpis[0].change_pct, kpis[0].change_reason) == (1290000.0, None, reason)
    metrics = metrics_data(months=(("2011-12", 300000.0),))
    metrics["period"]["data_start"] = "2011-12-01"
    kpis = build(metrics=_partial(metrics)).layer_1_numbers.kpis
    assert kpis[1].current_reason == "the file starts on 2011-12-01, after 2011-11: it holds none of that month"


def test_lines_in_no_figure_reach_the_report() -> None:
    # Review 1 #10 (CONTRACTS 6: never dropped silently).
    unmeasurable = [{"scope": "file", "reason": "no price", "lines": 9120}]
    metrics = metrics_data(undated_lines=48213, undated_lines_reason="48,213 lines carry no date",
                           unmeasurable=unmeasurable)
    numbers = build(metrics=metrics).layer_1_numbers
    assert (numbers.undated_lines, numbers.undated_lines_reason) == (48213, "48,213 lines carry no date")
    assert [(u.scope, u.reason, u.lines) for u in numbers.unmeasurable] == [("file", "no price", 9120)]


def test_a_change_that_touched_nothing_is_not_an_issue_fixed() -> None:
    cleaning = cleaning_report_payload()
    cleaning["column_mapping"]["Customer ID"] = "customer"
    cleaning["changes"].append(cleaning["changes"][0] | {"cells_affected": 0, "rows_affected": 0})
    assert build(cleaning=cleaning).data_quality.issues_fixed == 2


# --- the causes ---------------------------------------------------------------------------------


def test_the_hypotheses_and_signals_keep_their_figures_and_reasons() -> None:
    # Review 1 #5: a null figure's reason is `rule` (a hypothesis) or
    # `insufficient_reason` (a signal).
    diagnosis = diagnosis_payload()
    diagnosis["signals"].append({"series": "orders", "mode": "level", "value_cur": None, "center": None,
                                 "lower": None, "upper": None, "signal": "insufficient_history", "rule": None,
                                 "limits_method": "median_moving_range", "insufficient_reason": "too_few_points"})
    diagnosis["signals"][0]["mode_fallback"] = "no_year_ago_value"
    causes = build(diagnosis=diagnosis).layer_2_causes
    hypothesis = diagnosis["hypotheses"][0]
    assert [(h.id, h.verdict, h.contribution, h.share, h.rule, h.evidence) for h in causes.hypotheses] == [
        ("P2", "supported", -21000.0, 0.21, "same sign and share >= 0.20", hypothesis["evidence"])]
    assert causes.signals is not None
    assert [(s.series, s.value_cur, s.center, s.lower, s.upper, s.mode_fallback, s.insufficient_reason)
            for s in causes.signals] == [
        ("revenue", 1150000.0, 1240000.0, 1090000.0, 1390000.0, "no_year_ago_value", None),
        ("orders", None, None, None, None, None, "too_few_points")]


def test_the_causes_keep_what_was_not_testable_and_the_suggested_classes() -> None:
    diagnosis = diagnosis_payload()
    diagnosis["localization"]["dimensions"].append({
        "name": "product", "members": [], "other": {"name": "Other", "rev_prev": 0.0, "rev_cur": 0.0, "delta": 0.0,
                                                     "share_of_change": 0.0},
        "new_members": ["POSTAGE"], "removed_members": []})
    diagnosis["suggested_classes"] = {"POSTAGE": "charge"}
    causes = build(diagnosis=diagnosis).layer_2_causes
    assert [(n.id, n.reason) for n in causes.not_testable] == [
        ("X1", "no campaign data; discount columns are not canonical")]
    assert causes.suggested_classes == {"POSTAGE": "charge"}


def test_the_causes_show_the_files_notes_and_never_an_always_on_one() -> None:
    # discounts_in_prices is on both files: once, in how_to_read.
    assert build().layer_2_causes.notes == []
    diagnosis = diagnosis_payload()
    diagnosis["notes"].append(SAME_DAY)
    assert [n.code for n in build(diagnosis=diagnosis).layer_2_causes.notes] == ["same_day_cancellations"]


def test_a_blocked_diagnosis_builds_a_report() -> None:
    # Contract item 3: every analysis block null, the headline rule 1.
    diagnosis = diagnosis_payload()
    diagnosis["trust"]["verdict"] = "blocked"
    diagnosis.update({"calendar": None, "signals": None, "tree": None, "localization": None})
    diagnosis["headline"] = {"rule": 1, "hypothesis_id": None, "lens": None,
                             "message": "The data could not be trusted for this period."}
    report = build(diagnosis=diagnosis)
    assert (report.layer_1_numbers.trust.verdict, report.layer_2_causes.signals,
            report.layer_2_causes.headline.message) == ("blocked", None, "The data could not be trusted for this period.")
