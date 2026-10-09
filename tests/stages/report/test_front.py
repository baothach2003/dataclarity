"""The report redesign's step 3 (Thach, 2026-10-05): report.json's front
section, written by stage 5 from the earlier files - docs/REPORT_REDESIGN.md
1.1-1.6 with every answer Q1-Q31 applied, the partial month (7), the rows
left out (1.6) and the currency (6.4, Q8). Written before the code, on the
three real runs (fixtures/: Thach's Kaggle run, both Online Retail II demo
runs); every expected figure is a field of those files, formatted by hand."""

import copy
import re

import pytest

from contracts.report_front import FRONT_BANNED
from tests.stages.report.real_runs import RUNS, build_real, files, with_actions

NOT_AVAILABLE = ("Suggested actions are not available for this report: its forecast was made before they existed - "
                 "run the forecast again to see them.")


def _front(run: str = "kaggle", **replaced):
    return build_real(run, **replaced).front


def _group(front, kind: str):
    return next(group for group in front.checklist if group.kind == kind)


# --- section 1: the 30-second summary (1.1; Q3, Q22, Q24) -------------------------------------------------


def test_kaggle_outside_the_typical_change_says_a_then_b_then_c() -> None:
    front = _front()

    assert front.state == "compared"
    assert front.summary == [
        "Sales in December 2024 were 46,292.50, up 4,925.00 (+11.9%) on November 2024 (41,367.50).",
        "That is more than twice this shop's typical month-to-month change (about 4.9%).",
        "The figures match customers ordering more often: 25 customers placed an order in each month, and "
        "together they placed 343 orders, up from 308."]


# Q57: the yardstick; Q56: A prints the change as B does (two decimals on demo_unanswered,
# where at one the printed gap 12.1 would not be 39.1 - 27.1).
@pytest.mark.parametrize(("run", "sales", "change", "pct", "previous", "last_year"), [
    ("demo_classed", "663,315.58", "141,755.41", "+27.2%", "521,560.17",
     "27.1% last year, 27.2% this year (one earlier year to compare with) - a gap of 0.1 points, within twice this "
     "shop's typical gap (13.1 points)"),
    ("demo_unanswered", "654,527.09", "139,466.56", "+27.08%", "515,060.53",
     "39.14% last year, 27.08% this year (one earlier year to compare with) - a gap of 12.06 points, within twice "
     "this shop's typical gap (8.55 points)")])
def test_inside_the_season_b_opens_the_summary(run, sales, change, pct, previous, last_year) -> None:
    assert _front(run).summary == [
        f"This change is in line with last year's: {last_year}.",
        f"Sales in November 2011 were {sales}, up {change} ({pct}) on October 2011 ({previous}).",
        "Nothing else stands out: the change is in line with last year's, so none of the checks below is named "
        "as the reason."]


def test_sentence_a_prints_the_bridges_shown_change_q22() -> None:
    # The months' shown cents: an exact change of 141,755.4100000001 prints as the chart's 141,755.41.
    diagnosis = files("demo_classed")["diagnosis.json"]
    assert diagnosis["tree"]["lever"]["bridge"]["shown_change"] == 141755.41

    assert "up 141,755.41 (+27.2%)" in _front("demo_classed").summary[1]


def test_with_the_bridge_withheld_sentence_a_prints_the_exact_change_q24() -> None:
    data = files("kaggle")
    diagnosis = copy.deepcopy(data["diagnosis.json"])
    lever = diagnosis["tree"]["lever"]
    lever["bridge"], lever["bridge_withheld"] = None, "failed_checks"

    front = _front(diagnosis=diagnosis)

    assert front.summary[0] == "Sales in December 2024 were 46,292.50, up 4,925.00 (+11.9%) on November 2024 " \
                               "(41,367.50)."
    assert front.waterfall is None
    assert front.waterfall_note == ("The chart of what changed is not drawn: the split into parts did not pass its "
                                    "checks, so it is not shown.")


def test_the_not_profit_sentence_and_the_currency_sentence_follow() -> None:
    assert _front().sales_note == ("Sales here means the money customers paid (before any costs). It is not "
                                   "profit: the file has no cost data. Amounts are in your file's currency.")


def test_the_chart_is_titled_sales_and_names_the_part_month_by_its_dates_only_q13() -> None:
    front = _front()

    assert front.chart_title == "Sales by month (before any costs)"
    assert front.chart_note == ["January 2025 is not in the chart: the file covers only 1 to 18 January 2025. "
                                "Comparing part of a month with full months would mislead, so it is left out."]


def test_the_part_month_is_carried_with_its_dates() -> None:
    month = build_real("kaggle").layer_1_numbers.partial_months

    assert [(m.period, f"{m.covers_from}", f"{m.covers_to}", m.position) for m in month] == [
        ("2025-01", "2025-01-01", "2025-01-18", "last")]


# --- section 2: the waterfall (1.2; Q1, Q2, Q4) ------------------------------------------------------------


def test_kaggles_waterfall_draws_every_part_and_adds_up() -> None:
    waterfall = _front().waterfall

    assert [(b.label, b.was, b.now, b.worth) for b in waterfall.bars] == [
        ("Customers who placed an order", "25", "25", "+0.00"),
        ("Orders per customer", "12.32", "13.72", "+4,712.29"),
        ("Items per order", "5.44", "5.80", "+2,858.84"),
        ("Average price per item", "24.70", "23.25", "-2,646.13")]
    assert (waterfall.previous_label, waterfall.current_label) == ("November 2024 sales", "December 2024 sales")
    assert (waterfall.previous_text, waterfall.current_text, waterfall.change_text) == (
        "41,367.50", "46,292.50", "+4,925.00")
    assert round(sum(b.shown for b in waterfall.bars) * 100) == round(waterfall.shown_change * 100) == 492500
    assert waterfall.note is None
    assert waterfall.caption == (
        "Read from the first bar to the last: November's sales, then what each part added or took away, ending at "
        "December's sales. The bars add up exactly to the change. 'Worth' amounts split the effect of things that "
        "moved together, so read them as sizes, not exact causes.")


def test_where_the_split_is_refused_the_order_value_is_one_bar_q1() -> None:
    waterfall = _front("demo_classed").waterfall

    assert [(b.label, b.was, b.now, b.worth) for b in waterfall.bars] == [
        ("Customers who placed an order", "609", "756", "+127,578.73"),
        ("Orders per customer", "1.48", "1.63", "+56,167.67"),
        ("Average order value", "576.95", "537.53", "-41,990.99")]
    assert waterfall.note == ("Average order value is shown as one bar: returns in these months make the split "
                              "into items per order and price per item unreliable, so it is not drawn.")


# --- section 3: what was checked (1.3; Q16, Q20) -----------------------------------------------------------


def test_kaggles_checklist_groups_and_lines() -> None:
    front = _front()

    assert [group.kind for group in front.checklist] == ["matches", "against", "not_reason", "cannot_show"]
    matches = _group(front, "matches")
    assert matches.title == "Matches the figures" and matches.note is None
    assert matches.lines == [
        "Customers ordered more often: 343 orders, up from 308 - worth about +4,712.29.",
        "Last year alone, sales rose between November and December: 34,900.00 to 41,046.00.",  # Q41: the fact only
        "Bigger baskets: 5.80 items per order, up from 5.44 - worth about +2,858.84.",
        "The calendar: December's length and mix of weekdays - worth about +1,274.15.",
        "Products sold in only one of the two months: sales of products sold in December but not in November "
        "(+9,101.00) and the other way round (-8,835.50) - together worth about +265.50 (a small part)."]
    assert matches.after == ("These amounts are measured in different ways and overlap, so they do not add up to "
                             "the change (4,925.00). The chart in section 2 is the one that adds up.")


def test_p2_is_worded_inside_the_charts_price_bar_q20() -> None:
    against = _group(_front(), "against")

    assert against.title == "Pulled the other way"
    assert against.lines == [
        "Inside the chart's average price per item (-2,646.13): customers chose cheaper products among those sold "
        "in both months. Measured product by product, that shift is about -1,479.65 - a different measure, not an "
        "amount to add to the chart."]


def test_kaggles_checked_and_cannot_show() -> None:
    front = _front()

    # D1-D3: the one data-checks line, before the groups (Thach, 2026-10-06).
    assert front.data_checks == ["Data checks passed (details in the technical section)."]
    assert _group(front, "not_reason").lines == [
        "Customers: no new customers, none stopped buying, none came back after a break - the same customers "
        "placed orders in both months.",
        "Prices: products sold in both months kept their prices, so the chart's average price per item "
        "(-2,646.13) moved with what customers bought, not with price changes.",
        "Refunds for returned goods: none in either month.",  # Q34: the field is money
        "Discounts: none booked as separate lines (a discount already taken off a price cannot be seen).",
        "One product or category: the change was not concentrated in one.",
        "Stockouts: no best-selling product stopped selling in a way that suggests it ran out."]
    assert _group(front, "cannot_show").lines == [
        "Postage and other charges paid by customers: no line was classed as a charge in Review."]


def test_under_rule_7_the_first_group_is_moved_but_not_singled_out_q16() -> None:
    front = _front("demo_classed")
    moved = front.checklist[0]

    assert (moved.kind, moved.title) == ("moved", "Moved this month, but not singled out")
    assert moved.note == "Because the change is in line with last year's, none of these is called the reason; " \
                         "each line says what moved."
    assert moved.lines[:2] == [
        "Last year alone, sales rose between October and November: 518,318.50 to 658,764.09.",  # Q41
        "Customers ordered more often: 1,234 orders, up from 904 - worth about +56,167.67."]
    assert ("Inside the chart's average order value (-41,990.99): prices of products sold in both months went up. "
            "Measured product by product, about +36,878.80 - a different measure, not an amount to add to the "
            "chart.") in moved.lines
    assert "Refunds for returned goods fell: 13,951.29, down from 41,074.29 (a small part)." in moved.lines  # Q34
    assert moved.after.startswith("These amounts are measured in different ways and overlap, so they do not add "
                                  "up to the change (141,755.41).")


def test_a_refused_basket_split_is_a_line_this_file_cannot_show() -> None:
    assert _group(_front("demo_classed"), "cannot_show").lines == [
        "Basket size (items per order): returns make it unreliable this month."]


def test_t3_and_c4_are_left_to_the_appendix() -> None:
    for run in RUNS:
        text = " ".join(line for group in _front(run).checklist for line in group.lines)
        assert "routine" not in text and "segment" not in text


# --- section 4: what to do next, its three states (1.4; D4) -------------------------------------------------


def test_a_forecast_from_before_the_actions_reads_as_not_available() -> None:
    # Step 4 as option (d): no AI switch - a forecast before 2.1 holds no actions.
    steps = _front().next_steps

    assert (steps.status, steps.sentence, steps.items) == ("unavailable", NOT_AVAILABLE, [])


def test_actions_off_read_as_not_available() -> None:
    # "off": only a run where stage 4 did not produce actions (design 4.4).
    steps = _front(forecast=with_actions("kaggle", "off")).next_steps

    # Never "made before" (the review).
    assert (steps.status, steps.sentence) == (
        "off", "Suggested actions are not available for this report: run the forecast again.")


def test_actions_suppressed_say_so_and_show_nothing() -> None:
    steps = _front(forecast=with_actions("kaggle", "suppressed")).next_steps

    assert (steps.status, steps.items) == ("suppressed", [])
    # Design 4.4: claims possible, nothing to act on.
    assert steps.sentence == ("No action is suggested: the figures above that moved have no action this report can "
                              "suggest.")


def test_no_claim_selected_says_no_action_is_suggested() -> None:
    steps = _front("demo_classed", forecast=with_actions("demo_classed", "list", [])).next_steps

    assert (steps.status, steps.items) == ("list", [])
    assert steps.sentence == ("No action is suggested: no single reason stands out in these figures. Next month, "
                              "compare sales with the estimate in section 5.")


def test_listed_actions_show_the_fact_the_action_the_why_and_the_watch_line() -> None:
    action = {"claim": "K1", "hypothesis_id": "B1",
              "fact": "Customers ordered more often: 343 orders, up from 308 - worth about +4,712.29.",
              "action": "Thank customers with a small reward on their next purchase.",
              "why": "The figure above rose; a reward on the next purchase may help keep it there.",
              "watch": "Next month, check: orders per customer (13.72 this month; 12.32 the month before)."}
    steps = _front(forecast=with_actions("kaggle", "list", [action])).next_steps

    assert steps.status == "list" and steps.sentence is None
    assert [(i.rests_on, i.action, i.why, i.watch) for i in steps.items] == [
        (action["fact"], action["action"], action["why"], action["watch"])]


# --- section 5: next month (1.5; Q12, Q13) -------------------------------------------------------------------


def test_kaggles_next_month() -> None:
    assert _front().next_month == [
        "Next month (January 2025): about 43,835.33, likely between 38,893.14 and 49,405.54 (the real figure "
        "should land in this range about 8 months in 10).",
        "It is based on the last three full months, the latest counting most, and assumes no seasonal pattern.",
        "Your file already has sales for 1 to 18 January 2025; that part-month is not compared with this "
        "estimate."]


def test_a_season_read_from_two_years_says_so_plainly() -> None:
    next_month = _front("demo_classed").next_month

    assert next_month[0].startswith("Next month (December 2011): about 401,224.73, likely between 313,360.52 and "
                                    "513,725.48")
    assert next_month[1] == ("It follows the seasonal pattern of the last two years - the fewest years that can "
                             "show one - so the shape is less certain than more years would make it.")


# --- section 6: what this report cannot know, and the rows left out (1.6) -------------------------------------


def test_the_rows_left_out_name_the_action_and_the_column() -> None:
    report = build_real("kaggle")

    assert [(r.action, r.column, r.rows) for r in report.rows_left_out] == [("drop_rows_missing", "Item", 1213)]
    rows = next(item for item in report.front.cannot_know if item.title == "Rows left out")
    assert rows.text == ('12,575 rows were read and 11,362 used: 1,213 rows with no value in "Item" were left out '
                         "during cleaning, as the plan you approved in Review said. Rows left out are in no figure, "
                         "and a gap they leave cannot be seen.")


def test_no_row_left_out_says_so() -> None:
    rows = next(item for item in _front("demo_classed").cannot_know if item.title == "Rows left out")

    assert rows.text.startswith("460,859 rows were read and used; no row was left out.")


def test_what_this_report_cannot_know() -> None:
    assert [item.title for item in _front().cannot_know] == [
        "Profit", "Marketing and promotions", "Competitors, weather and events",
        "How many people visited or browsed", "Stock", "Sales by channel, payment method or country",
        "Rows left out"]


# --- the currency (6.4, Q8) -----------------------------------------------------------------------------------


def test_not_stated_shows_no_code_and_the_sentence() -> None:
    report = build_real("kaggle")

    assert (report.currency.code, report.currency.sentence) == (None, "Amounts are in your file's currency.")
    assert "GBP" not in report.front.model_dump_json()


def test_a_confirmed_currency_is_on_every_front_amount() -> None:
    cleaning = copy.deepcopy(files("kaggle")["cleaning_report.json"])
    cleaning["currency"] = {"code": "GBP", "source": "user", "evidence": None}
    report = build_real("kaggle", cleaning=cleaning)

    assert (report.currency.code, report.currency.sentence) == ("GBP", None)
    front = report.front
    assert front.summary[0] == ("Sales in December 2024 were GBP 46,292.50, up GBP 4,925.00 (+11.9%) on November "
                                "2024 (GBP 41,367.50).")
    assert front.waterfall.bars[1].worth == "GBP +4,712.29"
    assert "Amounts are in your file's currency" not in front.sales_note


# --- the states (the standing rules) ------------------------------------------------------------------------------


def test_a_caution_opens_section_1_with_the_checks_own_message() -> None:
    diagnosis = copy.deepcopy(files("kaggle")["diagnosis.json"])
    diagnosis["schema_version"] = "18.7"  # the month the check is about (Q39)
    diagnosis["headline"]["offsetting"] = False
    diagnosis["trust"]["verdict"] = "caution"
    diagnosis["trust"]["checks"][0] |= {"status": "caution", "month": "current",
                                        "message": "About 5 days in December have no sales."}

    front = _front(diagnosis=diagnosis)

    # Q37: the check worded by its id and status; stage 3's message stays in the appendix.
    assert front.caution == ["Some days in December 2024 have no sales at all - missing data, or days the shop was "
                             "closed (the file cannot tell which)."]  # the opener left the front (safety valve)


def _texts(value) -> list[str]:
    """Every sentence a reader sees - the bars' factor codes are not text."""
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [t for key, item in value.items() if key != "factor" for t in _texts(item)]
    if isinstance(value, list):
        return [t for item in value for t in _texts(item)]
    return []


def test_no_front_word_is_jargon_or_a_verdict() -> None:
    for run in RUNS:
        text = " " + " ".join(_texts(build_real(run).front.model_dump())).lower()
        found = [word for word in FRONT_BANNED if re.search(rf"(?<![a-z]){re.escape(word)}(?:s|es)?(?![a-z])", text)]
        assert found == [], run


def test_the_report_is_2_9_and_carries_its_front() -> None:
    report = build_real("kaggle")

    assert report.schema_version == "2.9" and report.front is not None and report.currency is not None


# --- the blocked and not-compared states, on the hand-built files of 5A -----------------------------------------


def test_a_blocked_run_replaces_sections_1_to_4_with_one_sentence() -> None:
    from tests.contracts.test_diagnosis import diagnosis_payload
    from tests.stages.report.report_fixtures import build

    diagnosis = diagnosis_payload()
    diagnosis["trust"]["verdict"] = "blocked"
    diagnosis["trust"]["checks"][0] |= {"status": "blocked", "message": "Most days of the month have no sales."}
    diagnosis.update({"calendar": None, "signals": None, "tree": None, "localization": None})
    diagnosis["headline"] = {"rule": 1, "hypothesis_id": None, "lens": None,
                             "message": "The data could not be trusted for this period."}
    front = build(diagnosis=diagnosis).front

    assert front.state == "blocked"
    # A file before 18.7 names no month: the front says less, never this month (Q39).
    assert front.summary == ["The data cannot support conclusions: the data checks did not pass - the technical "
                             "section says which, and why."]
    assert (front.waterfall, front.checklist, front.next_steps, front.caution) == (None, [], None, [])


def test_an_incomplete_previous_month_shows_this_month_alone() -> None:
    from tests.contracts.test_metrics_reasons import REASON, _partial
    from tests.stages.report.report_fixtures import build, metrics_data

    front = build(metrics=_partial(metrics_data())).front

    assert front.state == "not_compared"
    # In plain words; stage 2's reason stays in the appendix (Q37's rule, the review).
    assert REASON not in " ".join(front.summary)
    assert front.summary == ["Sales in November 2011 were 1,150,000.00.",
                             "They are not compared with October 2011: the file does not cover October 2011 whole."]
    assert (front.waterfall, front.checklist, front.next_steps) == (None, [], None)
