"""Steps 1 and 2: frame, and the trust gate (D1, D2, D3, verdict)."""

from datetime import date

import pytest

from stages.diagnose.frame import build_frame, history_window
from stages.diagnose.inputs import complete_months
from stages.diagnose.trust import d1_coverage, d2_price_level, d3_flagged_rows, evaluate_trust
from tests.stages.diagnose.diagnose_fixtures import (
    MAPPING,
    daily_rows,
    full_months,
    month_span,
    row,
    run_data,
)

# --- complete months ---------------------------------------------------------


def test_a_partly_covered_first_month_is_not_a_complete_month() -> None:
    # The file opens on 15 January, so January is not a month this file can
    # describe - putting its half-month into a baseline would invent a dip.
    months = complete_months(date(2011, 1, 15), date(2011, 4, 30))

    assert months == ["2011-02", "2011-03", "2011-04"]


def test_a_partly_covered_last_month_is_not_complete_either() -> None:
    months = complete_months(date(2011, 1, 1), date(2011, 3, 9))

    assert months == ["2011-01", "2011-02"]


# --- step 1: frame -----------------------------------------------------------


def test_frame_takes_its_pair_from_stage_2_and_finds_the_year_ago_pair() -> None:
    start, end = month_span("2010-01", 23)  # 2010-01 .. 2011-11
    data = run_data(daily_rows(start, end))

    frame = build_frame(data)

    assert (frame.current, frame.previous) == ("2011-11", "2011-10")
    assert (frame.year_ago_current, frame.year_ago_previous) == ("2010-11", "2010-10")
    assert (frame.history_start, frame.history_end) == ("2010-01", "2011-10")
    assert frame.history_months == 22


def test_the_year_ago_pair_is_null_when_only_one_side_exists() -> None:
    # Starts 2010-11, so 2010-11 exists but 2010-10 does not: half a year-ago
    # comparison is not a comparison.
    start, end = month_span("2010-11", 13)  # 2010-11 .. 2011-11
    data = run_data(daily_rows(start, end))

    frame = build_frame(data)

    assert (frame.year_ago_current, frame.year_ago_previous) == (None, None)


def test_history_is_capped_at_two_years_and_excludes_the_current_month() -> None:
    start, end = month_span("2008-01", 47)  # four years, current = 2011-11
    data = run_data(daily_rows(start, end))

    history = history_window(data)

    assert len(history) == 24
    assert history[-1] == "2011-10"  # strictly before current
    assert data.metrics.period.current not in history


def test_a_single_month_file_has_no_history_window() -> None:
    data = run_data(daily_rows(date(2011, 1, 1), date(2011, 1, 31)))

    frame = build_frame(data)

    assert frame.history_months == 0
    assert (frame.history_start, frame.history_end) == (None, None)


# --- step 2: D1 coverage ------------------------------------------------------


def test_d1_flags_a_run_of_missing_days_and_prices_the_gap() -> None:
    # Trades every day for a year, then six days vanish from the current month.
    start, end = month_span("2011-01", 11)  # 2011-01 .. 2011-11
    gap = tuple(date(2011, 11, day) for day in range(10, 16))
    data = run_data(daily_rows(start, end, skip=gap))

    check = d1_coverage(data, history_window(data))

    assert check.status == "caution"
    assert check.evidence["zero_days_cur"] == 6
    assert check.evidence["expected_zero_days_cur"] == 0.0
    assert check.evidence["excess_zero_days_cur"] == 6.0
    # Every day is worth 10, so six missing days is about 60.
    assert check.evidence["estimated_revenue_gap"] == pytest.approx(60.0)


def test_d1_blocks_when_most_of_the_month_is_missing() -> None:
    start, end = month_span("2011-01", 11)
    gap = tuple(date(2011, 11, day) for day in range(1, 21))  # 20 of 30 days
    data = run_data(daily_rows(start, end, skip=gap))

    check = d1_coverage(data, history_window(data))

    assert check.status == "blocked"


def test_a_shop_closed_every_sunday_is_not_accused_of_missing_data() -> None:
    # The reason D1 uses a per-weekday zero rate (Thach, 3B): Sundays are
    # expected to be empty here, and months hold four or five of them.
    start, end = month_span("2011-01", 11)
    data = run_data(daily_rows(start, end, closed_weekdays=(6,)))

    check = d1_coverage(data, history_window(data))

    assert check.status == "ok"
    assert check.evidence["zero_days_cur"] == 4  # November 2011 has four Sundays
    assert check.evidence["excess_zero_days_cur"] == 0.0
    assert check.evidence["zero_rate_by_weekday"]["6"] == 1.0


def test_a_shop_closed_sundays_still_shows_a_weekday_gap() -> None:
    # The scalar rate would partly absorb this; the per-weekday one does not.
    start, end = month_span("2011-01", 11)
    gap = tuple(date(2011, 11, day) for day in (1, 2, 3, 8, 9))  # Tue/Wed/Thu
    data = run_data(daily_rows(start, end, closed_weekdays=(6,), skip=gap))

    check = d1_coverage(data, history_window(data))

    assert check.status == "caution"
    assert check.evidence["excess_zero_days_cur"] == pytest.approx(5.0)


def test_d1_is_inconclusive_without_any_history_to_compare_against() -> None:
    """Two months: the only history month is the previous one, which D1 never
    learns from. (A one-month file is now blocked outright - its previous month
    is absent - see test_step7_cycle3_fixes; 3E1 moved this fixture on.)"""
    data = run_data(daily_rows(date(2010, 12, 1), date(2011, 1, 31)))

    check = d1_coverage(data, history_window(data))

    assert check.status == "inconclusive"


# --- step 2: D2 uniform price-level shift -------------------------------------


def _two_period_prices(prices_prev: dict[str, float], prices_cur: dict[str, float]) -> list[dict]:
    """Three rows per product per period, so each clears D2_MIN_ROWS."""
    rows = []
    for product, price in prices_prev.items():
        rows += [row(date(2011, 10, day), price=price, product=product) for day in (5, 15, 25)]
    for product, price in prices_cur.items():
        rows += [row(date(2011, 11, day), price=price, product=product) for day in (5, 15, 25)]
    rows.append(row(date(2011, 11, 30), price=10.0, product="Widget"))  # closes the month
    return rows


def test_d2_flags_a_x100_price_shift_across_a_full_catalogue() -> None:
    prev = {f"P{i}": 10.0 + i for i in range(20)}
    cur = {name: price * 100 for name, price in prev.items()}
    data = run_data(_two_period_prices(prev, cur))

    check = d2_price_level(data)

    assert check.status == "caution"
    assert check.evidence["rule"] == "cluster"
    assert check.evidence["median_ratio"] == pytest.approx(100.0)
    assert check.evidence["share_in_cluster"] == pytest.approx(1.0)
    assert "unit or currency" in check.message


def test_d2_ignores_an_ordinary_across_the_board_price_rise() -> None:
    prev = {f"P{i}": 10.0 + i for i in range(20)}
    cur = {name: price * 1.05 for name, price in prev.items()}  # +5%, inside the neutral band
    data = run_data(_two_period_prices(prev, cur))

    check = d2_price_level(data)

    assert check.status == "ok"


def test_d2_flags_a_x100_shift_on_a_five_product_shop() -> None:
    # The small-catalogue rule (Thach, 3B): without it a cents-as-units error
    # here flows into the product lens and is reported as "like-for-like
    # prices +9,900%".
    prev = {f"P{i}": 10.0 + i for i in range(5)}
    cur = {name: price * 100 for name, price in prev.items()}
    data = run_data(_two_period_prices(prev, cur))

    check = d2_price_level(data)

    assert check.status == "caution"
    assert check.evidence["rule"] == "small_catalog_order_of_magnitude"
    assert check.evidence["share_extreme"] == pytest.approx(1.0)


def test_a_five_product_shop_raising_prices_fifteen_percent_is_not_flagged() -> None:
    prev = {f"P{i}": 10.0 + i for i in range(5)}
    cur = {name: price * 1.15 for name, price in prev.items()}
    data = run_data(_two_period_prices(prev, cur))

    check = d2_price_level(data)

    assert check.status == "ok"
    assert check.evidence["rule"] == "small_catalog_order_of_magnitude"


def test_d2_is_inconclusive_with_fewer_than_three_comparable_products() -> None:
    prev = {"P0": 10.0, "P1": 20.0}
    cur = {"P0": 1000.0, "P1": 2000.0}
    data = run_data(_two_period_prices(prev, cur))

    check = d2_price_level(data)

    assert check.status == "inconclusive"
    assert check.evidence["comparable_products"] == 2


# --- step 2: D3 flagged rows --------------------------------------------------


def test_d3_flags_a_jump_in_flagged_rows_this_period() -> None:
    rows = [row(date(2011, 10, day)) for day in range(1, 11)]
    rows += [row(date(2011, 11, day)) for day in range(1, 11)]
    rows.append(row(date(2011, 11, 30)))
    # Clean last month, half of this month flagged.
    flags = ["False"] * 10 + ["True"] * 5 + ["False"] * 5 + ["False"]
    for entry, flag in zip(rows, flags, strict=True):
        entry["__flag_negative__Qty"] = flag
    data = run_data(rows)

    check = d3_flagged_rows(data)

    assert check.status == "caution"
    assert check.evidence["flagged_share_prev"] == 0.0
    # Evidence figures are rounded for a readable contract file; 5 of 11 rows.
    assert check.evidence["flagged_share_cur"] == pytest.approx(5 / 11, abs=5e-5)


def test_d3_is_ok_when_the_file_has_no_flag_columns() -> None:
    data = run_data(daily_rows(*month_span("2011-10", 2)))

    check = d3_flagged_rows(data)

    assert check.status == "ok"
    assert check.evidence["flag_columns"] == 0


# --- step 2: the gate ---------------------------------------------------------


def test_the_gate_takes_the_worst_check_and_always_states_the_dropped_row_limit() -> None:
    start, end = month_span("2011-01", 11)
    gap = tuple(date(2011, 11, day) for day in range(10, 16))
    data = run_data(daily_rows(start, end, skip=gap))

    trust = evaluate_trust(data, history_window(data))

    assert trust.verdict == "caution"
    assert [check.id for check in trust.checks] == ["D1", "D2", "D3"]
    assert any("dropped in stage 1" in limit for limit in trust.limitations)


def test_a_clean_file_is_trusted() -> None:
    # Enough products for D2 to actually run: a one-product shop is
    # `inconclusive` by design, and inconclusive now downgrades to caution.
    data = run_data(daily_rows(*month_span("2011-01", 11), products=20))

    trust = evaluate_trust(data, history_window(data))

    assert trust.verdict == "trusted"
    assert [check.status for check in trust.checks] == ["ok", "ok", "ok"]


def test_an_unmapped_customer_column_does_not_break_the_gate() -> None:
    mapping = {key: value for key, value in MAPPING.items() if value != "customer"}
    data = run_data(daily_rows(*month_span("2011-01", 11), products=20), mapping)

    trust = evaluate_trust(data, history_window(data))

    assert trust.verdict == "trusted"


def test_a_check_that_could_not_run_downgrades_the_verdict_to_caution() -> None:
    """Thach's call, 3B doubt-review: "trusted" must not be reported on a run
    where the checks never executed. A two-month, one-product file can
    evaluate neither D1 (no history besides the previous month) nor D2 (one
    comparable product). The fixture was a single-month file until 3E1, which
    blocks a file with no previous month at all."""
    data = run_data(daily_rows(date(2010, 12, 1), date(2011, 1, 31)))

    trust = evaluate_trust(data, history_window(data))

    statuses = {check.id: check.status for check in trust.checks}
    assert statuses["D1"] == "inconclusive"
    assert statuses["D2"] == "inconclusive"
    assert trust.verdict == "caution"


def test_empty_history_months_do_not_teach_d1_that_gaps_are_normal() -> None:
    """3B doubt-review finding 2: the file with MORE missing data used to get
    the cleaner verdict. Three empty history months lifted the learned
    zero-rate enough to absorb a real six-day hole in the current month."""
    start, end = month_span("2010-01", 23)
    gap = tuple(date(2011, 11, day) for day in range(10, 16))
    rows = [entry for entry in daily_rows(start, end, skip=gap)
            if entry["Date"][:7] not in ("2010-05", "2010-06", "2010-07")]
    data = run_data(rows)

    check = d1_coverage(data, history_window(data))

    assert check.status == "caution"
    assert check.evidence["excess_zero_days_cur"] == 6.0
    assert check.evidence["empty_history_months"] == ["2010-05", "2010-06", "2010-07"]
