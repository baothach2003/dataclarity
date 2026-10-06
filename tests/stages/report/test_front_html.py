"""The report redesign's step 3 (Thach, 2026-10-05): report.html opens with
the front section a shop owner reads - report.json's `front`, printed as it
stands - and keeps everything it showed before in one closed "Technical
details" appendix (D3: moved, never deleted). docs/REPORT_REDESIGN.md 1.1-1.7
and section 9's tests that belong to stage 5. Written before the code, on the
three real runs (fixtures/). Structure and text, never pixels."""

import copy
import re

import pytest

from contracts.report_front import FRONT_BANNED
from stages.report.html_report import render_html
from tests.stages.report.html_probe import Page
from tests.stages.report.real_runs import RUNS, build_real, files, with_actions

FRONT_SECTIONS = ["summary", "change", "checked", "next-steps", "next-month", "cannot-know"]
APPENDIX_SECTIONS = ["quality", "numbers", "how-to-read", "causes", "actions", "provenance"]


def _page(run: str = "kaggle", **replaced) -> Page:
    return Page(render_html(build_real(run, **replaced)))


def _html(run: str = "kaggle", **replaced) -> str:
    return render_html(build_real(run, **replaced))


# --- the shape: the front, then one closed appendix (1.7) ------------------------------------------------


def test_the_front_comes_first_and_the_old_report_is_one_closed_appendix() -> None:
    page = _page()

    assert [a["id"] for a in page.named("section")] == FRONT_SECTIONS + APPENDIX_SECTIONS
    details = page.named("details")
    appendix = [d for d in details if d.get("id") == "appendix"]
    assert len(appendix) == 1 and "open" not in appendix[0]
    html = _html()
    start, end = html.index('<details id="appendix">'), html.rindex("</details>")
    for section in APPENDIX_SECTIONS:
        assert start < html.index(f'<section id="{section}">') < end
    assert "Technical details (for an analyst)" in html


def test_the_appendix_says_revenue_is_sales() -> None:
    assert "In this appendix, 'revenue' is the same figure as 'sales' above." in _page().text


def test_the_appendix_keeps_every_hypothesis_the_limits_table_and_its_method() -> None:
    page = _page()
    causes = page.section("causes")

    for hypothesis_id in ("D1", "D2", "D3", "T1", "T2", "T3", "C1", "C2", "C3", "C4", "B1", "B2", "P1", "P2", "P3",
                          "P4", "P5", "R1", "R2", "R3"):
        assert re.search(rf"(?<![A-Z0-9]){hypothesis_id}(?![0-9])", causes), hypothesis_id
    assert "Where this month sits" in causes
    assert "Against limits drawn from the history's own variation" in causes


def test_the_appendix_keeps_the_exact_split_and_the_range_construction_q12() -> None:
    page = _page("demo_classed")

    assert "The split of the change, exact" in page.text
    assert "-41,990.99" in page.text or "-41,990.991" in page.text
    assert ("The range is an 80% interval worked out from how far off this method's past estimates were (their root "
            "mean square times Student's t) or, with too few past estimates, from the spread of the months "
            "themselves.") in page.section("actions")


# --- no jargon in the front (section 3; Q3) -----------------------------------------------------------------


@pytest.mark.parametrize("run", RUNS)
def test_no_jargon_or_verdict_word_outside_the_appendix(run: str) -> None:
    text = " " + _page(run).front_text.lower()

    assert [w for w in FRONT_BANNED if re.search(rf"(?<![a-z]){re.escape(w)}(?:s|es)?(?![a-z])", text)] == []


def test_the_front_says_sales_before_any_costs_and_not_profit() -> None:
    front = _page().front_text

    assert "Sales by month (before any costs)" in front
    assert "It is not profit: the file has no cost data." in front


def test_no_ai_narration_line_anywhere() -> None:
    assert "AI narration is unavailable" not in _html()


# --- section 1: the summary, the chart, the part-month (1.1, 7; Q13, Q15, Q22) --------------------------------


def test_the_summary_is_the_front_blocks_sentences_in_order() -> None:
    summary = _page().section("summary")

    a = summary.index("Sales in December 2024 were 46,292.50, up 4,925.00 (+11.9%) on November 2024 (41,367.50).")
    b = summary.index("That is more than twice this shop's typical month-to-month change (about 4.9%).")
    c = summary.index("The figures match customers ordering more often")
    assert a < b < c


def test_inside_the_season_b_comes_first_on_the_page() -> None:
    summary = _page("demo_classed").section("summary")

    assert summary.index("This change is in line with last year's") < summary.index("Sales in November 2011 were")


def test_the_chart_draws_whole_months_only_and_the_part_month_by_its_dates() -> None:
    page = _page()
    summary = page.section("summary")
    chart = re.search(r'<svg[^>]*class="sales".*?</svg>', _html(), re.S).group(0)

    assert "December 2024: 46,292.50" in chart and "January 2025" not in chart
    assert ("January 2025 is not in the chart: the file covers only 1 to 18 January 2025. Comparing part of a month "
            "with full months would mislead, so it is left out.") in summary


def test_no_part_month_figure_anywhere_in_the_front_q13() -> None:
    metrics = files("kaggle")["metrics.json"]
    january = next(m["revenue"] for m in metrics["core"]["revenue_by_month"] if m["period"] == "2025-01")
    page = _page()

    assert f"{january:,.2f}" not in page.front_text
    assert f"{january:,.2f}" in page.text  # the appendix's monthly table keeps it


# --- section 2: the waterfall (1.2; Q1, Q2) ------------------------------------------------------------------


def _waterfall_rows(page: Page) -> list[str]:
    change = page.section("change")
    return re.findall(r"([+-][\d,]+\.\d\d)", change)


def test_the_waterfall_table_adds_up_to_the_shown_change() -> None:
    change = _page().section("change")
    bars = ["+0.00", "+4,712.29", "+2,858.84", "-2,646.13"]

    for bar in bars:
        assert bar in change
    assert sum(round(float(b.replace(",", "")) * 100) for b in bars) == 492500
    assert "Total change +4,925.00" in change


def test_where_the_split_is_withheld_the_page_says_why_and_draws_no_items_per_order() -> None:
    change = _page("demo_classed").section("change")

    assert "Average order value is shown as one bar" in change
    assert "Items per order" not in change and "Average price per item" not in change


# --- section 3: the checklist (1.3; Q16, Q20) -----------------------------------------------------------------


def test_the_checklist_prints_its_groups_and_the_overlap_sentence() -> None:
    checked = _page().section("checked")

    for title in ("Matches the figures", "Pulled the other way", "Checked - not the reason", "This file cannot show it"):
        assert title in checked
    assert ("These amounts are measured in different ways and overlap, so they do not add up to the change "
            "(4,925.00). The chart in section 2 is the one that adds up.") in checked
    assert "Inside the chart's average price per item (-2,646.13)" in checked
    assert "Last year alone, sales rose" in checked and "regular pattern" not in checked  # Q41
    assert "launched" not in checked and "discontinued" not in checked


# --- section 4: what to do next, three states (1.4) -----------------------------------------------------------


def test_switched_off() -> None:
    assert "Suggested actions are switched off for this report." in _page().section("next-steps")


def test_suppressed() -> None:
    steps = _page(forecast=with_actions("kaggle", "suppressed")).section("next-steps")

    assert "Suggested actions are not shown for this report" in steps


def test_a_listed_action_is_printed_and_escaped() -> None:
    action = {"claim": "K1", "hypothesis_id": "B1",
              "fact": "Customers ordered more often: 343 orders, up from 308 - worth about +4,712.29.",
              "action": "Keep <b>reminder</b> emails going.", "why": "Regular customers ordered again.",
              "watch": "Next month, check: orders per customer (13.72 this month; 12.32 the month before)."}
    html = _html(forecast=with_actions("kaggle", "list", [action], model="claude-sonnet-5"))
    steps = Page(html).section("next-steps")

    assert "Keep <b>reminder</b> emails going." in steps and "&lt;b&gt;reminder&lt;/b&gt;" in html
    assert "Rests on: Customers ordered more often" in steps
    assert "Next month, check: orders per customer" in steps


# --- section 5 and 6 --------------------------------------------------------------------------------------------


def test_next_month_in_plain_words_q12() -> None:
    next_month = _page().section("next-month")

    assert "likely between 38,893.14 and 49,405.54 (the real figure should land in this range about 8 months in 10)" \
           in next_month
    assert "80%" not in next_month and "band" not in next_month


def test_the_rows_left_out_are_said_in_section_6() -> None:
    assert '1,213 rows with no value in "Item" were left out' in _page().section("cannot-know")


# --- the currency (Q8) ------------------------------------------------------------------------------------------


def test_not_stated_shows_no_code_and_says_so() -> None:
    page = _page()

    assert "Amounts are in your file's currency." in page.front_text
    assert not re.search(r"\b[A-Z]{3} [\d+-]", page.text)


def test_a_confirmed_currency_is_on_every_amount() -> None:
    cleaning = copy.deepcopy(files("kaggle")["cleaning_report.json"])
    cleaning["currency"] = {"code": "GBP", "source": "user", "evidence": None}
    page = _page(cleaning=cleaning)

    assert "Sales in December 2024 were GBP 46,292.50" in page.section("summary")
    assert "GBP +4,712.29" in page.section("change")
    assert "GBP 46,292.50" in page.section("numbers")  # the appendix too: the code everywhere
    assert "Amounts are in your file's currency." not in page.text


# --- the states -------------------------------------------------------------------------------------------------


def test_a_caution_opens_the_summary() -> None:
    diagnosis = copy.deepcopy(files("kaggle")["diagnosis.json"])
    diagnosis["schema_version"] = "18.7"  # the month the check is about (Q39)
    diagnosis["headline"]["offsetting"] = False
    diagnosis["trust"]["verdict"] = "caution"
    diagnosis["trust"]["checks"][0] |= {"status": "caution", "month": "current",
                                        "message": "About 5 days in December have no sales."}
    summary = _page(diagnosis=diagnosis).section("summary")

    assert summary.startswith("In 30 seconds Some days in December 2024")  # the opener left the front (safety valve)
    assert "Some days in December 2024 have no sales at all" in summary  # Q37: by the check's id and status


def test_the_page_is_still_one_self_contained_file() -> None:
    page = _page()

    assert all(not s.get("src") for s in page.named("script")) and page.named("link") == []
