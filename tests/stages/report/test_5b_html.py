"""Session 5B (ninth run): report.html, one self-contained page rendered from
report.json - its structure, what it shows beside each figure, and that every
string from the file or the AI is escaped (SPECS SEC-3). Structure, never
pixels. Written before the code; every expected value is a field of the
report built in report_fixtures.py, formatted by hand.
"""

from typing import Any

from contracts.lines import NOTE_TEXTS
from contracts.report import ReportContract
from stages.report.html_report import render_html
from tests.contracts.test_metrics import metrics_payload
from tests.contracts.test_metrics_reasons import REASON, _partial
from tests.stages.report.html_probe import Page
from tests.stages.report.report_fixtures import SAME_DAY, build, metrics_data


def _page(report: ReportContract | None = None) -> Page:
    return Page(render_html(report or build()))


def test_the_report_is_one_self_contained_page() -> None:
    html = render_html(build())
    page = Page(html)
    assert html.startswith("<!doctype html>")
    assert page.named("html") == [{"lang": "en"}]
    assert {"charset": "utf-8"} in page.named("meta")
    # plotly.js once, inline, and one script per chart - nothing fetched.
    # (2.9: and the appendix's own script, which opens it to a note and resizes its charts.)
    assert len(page.scripts) == 4 and all(not s.get("src") for s in page.named("script"))
    assert page.named("link") == []
    assert not [attrs for _, attrs in page.tags if any(
        (value or "").startswith(("http:", "https:", "//")) for key, value in attrs.items() if key in ("src", "href"))]
    assert "<title>DataClarity report - sales_2011.csv</title>" in html


def test_the_sections_follow_the_three_layers() -> None:
    sections = [attrs["id"] for attrs in _page().named("section")]
    # 2.9: the front section first; the three layers in the appendix after it (the report redesign, step 3).
    assert sections == ["summary", "change", "checked", "next-steps", "next-month", "cannot-know",
                        "quality", "numbers", "how-to-read", "causes", "actions", "provenance"]


def test_the_kpis_are_the_reports_figures_formatted() -> None:
    # 1,150,000 against 1,290,000, -10.9%; 1,820 orders against 1,950;
    # 812 customers against 905; AOV 631.90 against 661.50; returns 0.042
    # against 0.038 (a ratio: three decimals, never a percentage).
    numbers = _page().section("numbers")
    for shown in ("Revenue 1,150,000.00 1,290,000.00 -10.9%", "Orders 1,820 1,950", "Active customers 812 905",
                  "Average order value 631.90 661.50", "Return rate 0.042 0.038"):
        assert shown in numbers
    assert "2011-11 compared with 2011-10" in numbers


def test_an_incomplete_previous_month_shows_its_reason_never_a_value() -> None:
    numbers = _page(build(metrics=_partial(metrics_data()))).section("numbers")
    assert "1,290,000.00" not in numbers and "-10.9%" not in numbers
    # Its reason once, beside the period (5B review 1 #8); each withheld cell
    # points to it - the revenue row twice: the previous value and the change.
    assert f"2011-11; 2011-10 is not compared. The file covers 2010-12-01 to 2011-12-09. {REASON}" in numbers
    pointer = "not compared - see why above"  # never a guess at why (5B review 2 #11)
    # Beside the period and beside the chart's gap (report.json's own note).
    assert "compared with 2011-10" not in numbers and numbers.replace(pointer, "").count(REASON) == 2
    assert f"2011-10 is not drawn: {REASON}." in numbers
    assert f"Revenue 1,150,000.00 {pointer} {pointer}" in numbers


def test_a_withheld_figure_shows_its_reason() -> None:
    metrics = metrics_data(active_customers_current=0)
    numbers = _page(build(metrics=metrics)).section("numbers")
    assert "Active customers no line in 2011-11 names a customer 905" in numbers


def test_the_trust_badge_says_its_verdict_in_words_with_its_reasons() -> None:
    # Colour is never the only signal (SPECS 11).
    numbers = _page().section("numbers")
    assert "Data trust: caution" in numbers
    assert "D1 (caution): About 5 days in the current month have no sales" in numbers
    assert "rows dropped in stage 1 cannot be assigned to a period" in numbers


def test_an_always_on_note_is_shown_once_in_how_to_read() -> None:
    page = _page()
    assert page.text.count(" ".join(NOTE_TEXTS["discounts_in_prices"].split())) == 1
    assert " ".join(NOTE_TEXTS["discounts_in_prices"].split()) in page.section("how-to-read")


def test_a_files_note_stands_beside_the_figures_it_names_by_its_code() -> None:
    metrics = metrics_data(notes=metrics_payload()["core"]["notes"] + [SAME_DAY])
    html = render_html(build(metrics=metrics))
    page = Page(html)
    assert "note-same_day_cancellations" in page.ids()
    links = [attrs["href"] for attrs in page.named("a")]
    # Beside orders, customers, AOV and the return rate (not revenue), and
    # beside the recommendations - and, since 2.9, beside the front's parts of the change and its checks (Q35).
    assert links.count("#note-same_day_cancellations") == 7
    assert " ".join(NOTE_TEXTS["same_day_cancellations"].split()) in page.section("numbers")


def test_previous_scope_amounts_are_hidden_when_the_previous_month_is_incomplete() -> None:
    # CONTRACTS 9 (5A review 3 #4): never a previous value beside a current one.
    non_product = [{"line_class": "charge", "lines": 213, "amount": 29920.84, "amount_current": 22564.68,
                    "amount_previous": 7356.16, "reason": "a charge the customer paid"}]
    whole = _page(build(metrics=metrics_data(non_product=non_product))).section("numbers")
    assert "22,564.68" in whole and "7,356.16" in whole
    part = _page(build(metrics=_partial(metrics_data(non_product=non_product)))).section("numbers")
    assert "22,564.68" in part and "7,356.16" not in part


def test_the_forecast_its_band_and_the_month_the_file_ends_in() -> None:
    actions = _page().section("actions")
    assert "2011-12 1,210,000.00 1,040,000.00 1,380,000.00" in actions
    assert "80%" in actions and "36 complete months" in actions
    # "The dates the file covers": a line dated after the upload is in no figure (Thach, 2026-10-04, (x)).
    assert "The dates the file covers end on 2011-12-09, part-way through 2011-12" in actions


def test_too_short_a_history_says_so_and_draws_no_forecast() -> None:
    from tests.contracts.test_forecast import forecast_payload

    forecast = forecast_payload()
    forecast["forecast"].update({"revenue": [], "horizon_periods": 0, "insufficient_history": True,
                                 "months_used": 2, "season_note": None, "season_years": None})
    page = _page(build(forecast=forecast))
    assert "There is too little history for a forecast: 2 complete months, and 3 are needed." in page.section(
        "actions")
    assert "chart-forecast" not in page.ids() and "chart-revenue_trend" in page.ids()


def test_the_recommendations_by_their_status() -> None:
    # Thach, Q42: the file's free-text recommendations are printed nowhere.
    # And no AI writes any in v1 (Q50 (d)): the appendix says so, never "switched off".
    shown = _page().section("actions")
    assert ("No AI writes recommendations in this version: suggested actions, when there are any, are written by "
            "code in section 4." in shown)
    assert "win-back email" not in shown and "Champions" not in shown and "switched off" not in shown


def test_the_causes_as_the_diagnosis_has_them() -> None:
    causes = _page().section("causes")
    assert "Most of the decline is consistent with a shift in sales mix towards cheaper products." in causes
    assert "P2" in causes and "supported" in causes and "same sign and share >= 0.20" in causes
    assert "mix_effect: -21,000.00" in causes  # evidence formatted, not raw (5B review 1 #13)
    assert "Marketing, promotions, discounts" in causes
    assert "Revenue fell 10.9% this month..." in causes


def test_no_narration_in_v1_prints_no_line() -> None:
    # Thach, Q21: the step was removed by design; "unavailable" would read as a failure. A report from
    # before 2.8 that says "unavailable" keeps its line (test_q21_q22).
    from tests.contracts.test_diagnosis import diagnosis_payload

    diagnosis: dict[str, Any] = diagnosis_payload() | {"ai_findings": None, "model_used": None}
    causes = _page(build(diagnosis=diagnosis)).section("causes")
    assert "narration" not in causes


def test_the_provenance_and_the_files_quality() -> None:
    page = _page()
    assert "AI answers used: 3 (claude-sonnet-5)" in page.section("provenance")
    assert "Rows in: 152,430. Rows out: 151,988." in page.section("quality")


def test_the_provenance_claims_for_the_ai_only_what_is_true() -> None:
    # An AI answer the report counts can be a column mapping or a cleaning plan
    # (builder.py), not only words - "the AI writes words only" was false; what
    # holds for every answer is that it computes no figure (CLAUDE.md 3.2; the
    # 6E1 review #9).
    provenance = _page().section("provenance")
    assert "Every figure is computed by code from the earlier stages' files; the AI computes none." in provenance
    assert "writes words only" not in provenance


def test_previous_scope_rows_and_measures_are_hidden_when_the_previous_month_is_incomplete() -> None:
    outside = [{"line_class": "cost", "scope": "file", "sign": None, "lines": 11, "amount": -26337.21,
                "lines_without_amount": 0},
               {"line_class": "cost", "scope": "previous", "sign": None, "lines": 5, "amount": -5977.22,
                "lines_without_amount": 0}]
    notes = metrics_payload()["core"]["notes"] + [SAME_DAY]
    whole = _page(build(metrics=metrics_data(outside_revenue=outside, notes=notes))).section("numbers")
    assert "-5,977.22" in whole and "returns previous 10 -345.50" in whole
    part = _page(build(metrics=_partial(metrics_data(outside_revenue=outside, notes=notes)))).section("numbers")
    assert "-26,337.21" in part and "-5,977.22" not in part
    assert "returns current 10 -345.50" in part and "returns previous" not in part


def test_a_negative_zero_shows_as_zero() -> None:
    # CONTRACTS 11: stage 3's terms may carry -0.0.
    from tests.contracts.test_diagnosis import diagnosis_payload

    diagnosis = diagnosis_payload()
    diagnosis["hypotheses"][0]["contribution"] = -0.0
    causes = _page(build(diagnosis=diagnosis)).section("causes")
    assert "P2 Sales mix shifted towards cheaper products supported 0.00 21%" in causes and "-0.00" not in causes
