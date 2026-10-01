"""The conformance suite, part 3: DF-E identities, DF-F placeholders, DF-G
coverage (docs/DATA_FAILURE_MODES.md; the rule and the base: test_conformance.py)."""

import pandas as pd
import pytest

from shared.order_checks import order_id_spanning
from stages.diagnose.inputs import build_run_data
from stages.diagnose.signals import monthly_series
from stages.ingest.customer_placeholders import placeholder_candidates
from stages.ingest.issue_counts import count_column_issues, count_duplicate_business_key
from stages.ingest.profiling import read_csv_text
from stages.analyze.assemble import assemble_metrics
from stages.predict.forecast import forecast
# The report's own withholding rules, read where they live (layer 1).
from stages.report.layers import _current_note, _empty_current
from tests.data_failures.flow import FEB, NOW, check, diagnosis, metrics, notes, sample, verdicts

# --- E. identities -----------------------------------------------------------------------------------


def test_df_e1_an_order_id_spanning_days_is_flagged_and_counted_per_day() -> None:
    # FLAG: stage 1's own check (2E-e). Kept mapped, an order is keyed by
    # (id, day, customer) - Ann's id on two days is two orders: 29 x 3 = 87.
    case = sample("DF-E1")
    spanning = order_id_spanning(pd.DataFrame(case.rows), case.mapping)
    assert spanning is not None and spanning.spanning == 1
    assert metrics(case).core.orders_current == 87


@pytest.mark.parametrize("mode", ["DF-E2", "DF-E4"])
def test_an_order_id_that_is_not_one_receipt_counts_lines_and_says_why(mode: str) -> None:
    found = metrics(sample(mode))
    assert found.core.orders_basis == "lines" and found.core.orders_basis_reason


def test_df_e3_a_receipt_naming_its_customer_once_gives_every_line_that_customer() -> None:
    found = metrics(sample("DF-E3"))
    assert (found.core.orders_basis, found.core.active_customers_current, found.core.orders_current) == (
        "order_id", 3, 87)


def test_df_e5_one_product_whatever_its_spelling() -> None:
    assert len(metrics(sample("DF-E5")).products.top_products) == 2


def test_df_e6_a_near_duplicate_label_is_counted_by_stage_1() -> None:
    # "Mug." and the five "Mug" cells are one label once punctuation goes;
    # the cells written the less common way are counted: one.
    frame = read_csv_text(sample("DF-E6").raw or b"").frame
    assert count_column_issues(frame["Product"]).get("near_duplicate_labels") == 1


def test_df_e7_a_duplicate_business_key_is_counted_by_stage_1() -> None:
    frame = pd.DataFrame(sample("DF-E7").rows)
    assert count_duplicate_business_key(frame, ["Date", "Product", "Cust"]) == 2  # both lines of the key


def test_df_e8_a_month_naming_no_customer_makes_the_customer_causes_not_testable() -> None:
    found = verdicts(diagnosis(sample("DF-E8")))
    assert {found[i] for i in ("C1", "C2", "C3", "C4", "B1")} == {"not_testable"}


def test_df_e9_a_partly_blank_customer_column_counts_the_named_lines() -> None:
    # Unnamed lines stay revenue (the bridge's unattributed term, 2E-f).
    found = metrics(sample("DF-E9"))
    assert (found.core.revenue_current, found.core.active_customers_current) == (FEB, 3)


def test_known_limit_df_e11_refunders_are_the_months_active_customers() -> None:
    """LIMIT (8D "From 3E2"): February's sales name nobody, one return names
    Ann - stage 2's frozen definition counts her as February's one active
    customer, with no note."""
    found = metrics(sample("DF-E11"))
    assert (found.core.active_customers_current, found.core.buyers_current) == (1, 0)


# --- F. placeholders ---------------------------------------------------------------------------------


@pytest.mark.parametrize("mode", ["DF-F1", "DF-F4"])
def test_a_customer_cell_that_names_nobody_is_no_customer(mode: str) -> None:
    assert metrics(sample(mode)).core.active_customers_current == 2


@pytest.mark.parametrize("mode,label", [("DF-F1B", "Guest"), ("DF-F5", "-")])
def test_known_limit_an_unanswered_walk_in_label_is_a_customer_without_a_note(mode: str, label: str) -> None:
    """LIMIT (2E-u review #4; for Thach): Review asks about "Guest" and "-";
    unanswered, each is one customer buying for every walk-in - three
    active customers, and no note says so."""
    case = sample(mode)
    asked = placeholder_candidates(pd.DataFrame(case.rows), case.mapping) or []
    assert label in {c.value for c in asked}
    found = metrics(case)
    assert found.core.active_customers_current == 3 and notes(found) == {"discounts_in_prices"}


def test_known_limit_df_f2_numbered_walk_in_labels_are_asked_one_by_one() -> None:
    """LIMIT (8D "From 2E-k", cycle 2): "Walk-in 1" .. "Walk-in 40" are forty
    candidates, one question each, and unanswered forty customers."""
    case = sample("DF-F2")
    asked = placeholder_candidates(pd.DataFrame(case.rows), case.mapping) or []
    assert sum(c.value.startswith("Walk-in") for c in asked) == 40
    assert metrics(case).core.active_customers_current == 2 + 40


def test_df_f3_na_words_are_blank_once_stage_1_reads_them() -> None:
    frame = read_csv_text(sample("DF-F3").raw or b"").frame
    assert assemble_metrics(frame, sample("DF-F3").mapping, now=NOW).core.active_customers_current == 2


# --- G. coverage ---------------------------------------------------------------------------------------


def test_df_g1_a_lost_week_is_a_trust_caution_and_the_headline_says_so() -> None:
    found = diagnosis(sample("DF-G1"))
    assert check(found, "D1") == "caution" and found.headline.rule == 2


def test_df_g1b_two_lost_days_are_a_caution_and_the_headline_says_so() -> None:
    """Was a LIMIT (a fixed 3-day caution, set for sparse shops in 3E1) - the
    headline gave the fall to seasonality. Since 3E1b (2E-u F5) D1 cautions
    from one whole day where the shop's own history has no zero day: January
    31 x 42 = 1,302, February 27 trading days x 42 = 1,134, -168. The two
    lost days are 2 x 42 = 84 of it - 50%, rule 2's share - the rest is
    February's two fewer calendar days."""
    found = diagnosis(sample("DF-G1B"))
    d1 = next(c for c in found.trust.checks if c.id == "D1")
    assert (d1.status, d1.evidence["excess_zero_days_cur"], d1.evidence["estimated_revenue_gap"]) \
        == ("caution", 2.0, 84.0)
    assert found.headline.rule == 2 and "-84.00" in found.headline.message


def test_known_limit_df_g2_an_empty_month_charts_zero() -> None:
    """LIMIT (3B's recorded defect, stages/diagnose/signals.py): a month with
    no line at all is charted 0, as if the shop sold nothing."""
    case = sample("DF-G2")
    series = monthly_series(build_run_data(pd.DataFrame(case.rows), case.mapping, metrics(case)))
    assert series.loc["2023-06", "revenue"] == 0.0


def test_df_g3_fewer_than_three_months_give_no_forecast() -> None:
    block = forecast(metrics(sample("DF-G3")))
    assert (block.insufficient_history, block.revenue) == (True, [])


def test_df_g4_fewer_than_eight_months_of_history_give_no_chart() -> None:
    found = diagnosis(sample("DF-G4"))
    assert found.signals is not None
    assert next(s for s in found.signals if s.series == "revenue").insufficient_reason == "too_few_points"


def test_df_g5_under_two_years_no_season_is_claimed() -> None:
    block = forecast(metrics(sample("DF-G5")))
    assert (block.season_years, block.insufficient_history) == (None, False)


def test_df_g6_a_month_of_refunds_only_blocks_the_diagnosis() -> None:
    found = diagnosis(sample("DF-G6"))
    assert (found.trust.verdict, found.headline.rule) == ("blocked", 1)


def test_df_g7_a_file_of_one_day_withholds_the_month_it_does_not_hold() -> None:
    assert _empty_current(metrics(sample("DF-G7"))) is not None
    assert diagnosis(sample("DF-G7")).headline.rule == 1


def test_df_g8_a_last_30_days_export_blocks_and_says_where_it_starts() -> None:
    assert _current_note(metrics(sample("DF-G8"))) is not None
    assert diagnosis(sample("DF-G8")).headline.rule == 1


def test_known_limit_df_g10_a_history_month_of_refunds_only_is_drawn_negative() -> None:
    """LIMIT (8D "From 5A"): a month of history holding one refund and no
    sale is charted at -10.00 - a compared one is withheld (DF-G6)."""
    case = sample("DF-G10")
    series = monthly_series(build_run_data(pd.DataFrame(case.rows), case.mapping, metrics(case)))
    assert series.loc["2023-06", "revenue"] == -10.0


def test_known_limit_df_g11_an_unpriced_line_on_the_1st_hides_the_part_way_note() -> None:
    """LIMIT (8D): the "last 30 days" export with an unpriced line dated
    2023-11-01 - the file now starts on the 1st, so layer 1 does not say it
    starts part-way through November."""
    assert _current_note(metrics(sample("DF-G11"))) is None
