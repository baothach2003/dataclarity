from datetime import UTC, date, datetime
from pathlib import Path

import pandas as pd
import pytest

from contracts.cleaning import CleaningReportContract
from shared.run_registry import create_run
from stages.analyze.metrics_core import compute_core_metrics
from stages.analyze.metrics_customers import (
    NEEDS_ATTENTION,
    assign_segment,
    compute_customer_metrics,
    customer_metrics_for_run,
    score_quintile,
)

NOW = datetime(2026, 9, 19, 12, 0, tzinfo=UTC)

# source column name -> canonical field, no transaction_type mapped: every
# row defaults to "out" (2A's convention), which keeps these RFM-focused
# fixtures free of an unrelated concern.
MAPPING = {"Date": "transaction_date", "Qty": "quantity", "Price": "unit_price", "Cust": "customer"}


def frame(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def row(customer: str, day: str, qty: str = "1", price: str = "10.0") -> dict:
    return {"Date": day, "Qty": qty, "Price": price, "Cust": customer}


# --- assign_segment: the full 5x5 R x F grid, hand-derived from Thach's rules
# (Champions R>=4&F>=4, Loyal R>=3&F>=3, At-risk R<=2&F>=3, Hibernating
# R<=2&F<=2, New R>=4&F<=1, "Needs Attention" catch-all) -------------------

SEGMENT_GRID = {
    (1, 1): "Hibernating", (1, 2): "Hibernating", (1, 3): "At-risk", (1, 4): "At-risk", (1, 5): "At-risk",
    (2, 1): "Hibernating", (2, 2): "Hibernating", (2, 3): "At-risk", (2, 4): "At-risk", (2, 5): "At-risk",
    (3, 1): NEEDS_ATTENTION, (3, 2): NEEDS_ATTENTION, (3, 3): "Loyal", (3, 4): "Loyal", (3, 5): "Loyal",
    (4, 1): "New", (4, 2): NEEDS_ATTENTION, (4, 3): "Loyal", (4, 4): "Champions", (4, 5): "Champions",
    (5, 1): "New", (5, 2): NEEDS_ATTENTION, (5, 3): "Loyal", (5, 4): "Champions", (5, 5): "Champions",
}  # fmt: skip


@pytest.mark.parametrize(("r", "f"), list(SEGMENT_GRID))
def test_assign_segment_matches_the_full_grid(r: int, f: int) -> None:
    assert assign_segment(r, f) == SEGMENT_GRID[(r, f)]


# --- score_quintile ----------------------------------------------------------


def test_a_single_customer_scores_best_on_both_directions() -> None:
    values = pd.Series([42])

    assert list(score_quintile(values, ascending=False)) == [5]
    assert list(score_quintile(values, ascending=True)) == [5]


def test_five_distinct_values_map_one_to_one_onto_1_through_5() -> None:
    values = pd.Series([1, 11, 21, 31, 73])  # ascending recency_days, e.g.

    # ascending=False: the smallest raw value (freshest) scores best (5).
    assert list(score_quintile(values, ascending=False)) == [5, 4, 3, 2, 1]
    # ascending=True: the largest raw value (most frequent) scores best (5).
    assert list(score_quintile(values, ascending=True)) == [1, 2, 3, 4, 5]


def test_many_ties_still_spread_across_all_five_quintiles() -> None:
    # Verified against real pandas behavior: rank(method="first") breaks ties
    # by original position, so an all-equal column still forms 5 real,
    # evenly-sized groups rather than colliding into one bucket or raising.
    values = pd.Series([5] * 10)

    assert list(score_quintile(values, ascending=True)) == [1, 1, 2, 2, 3, 3, 4, 4, 5, 5]


# --- compute_customer_metrics: the hand-calculated scenario -----------------


def _five_customer_scenario() -> pd.DataFrame:
    return frame(
        [
            # Customer A: 1 order, last (only) purchase 2020-01-31 -> recency 1 day
            row("A", "2020-01-31"),
            # Customer B: 2 orders, last 2020-01-21 -> recency 11 days
            row("B", "2020-01-05"),
            row("B", "2020-01-21"),
            # Customer C: 3 orders, last 2020-01-11 -> recency 21 days
            row("C", "2020-01-02"),
            row("C", "2020-01-06"),
            row("C", "2020-01-11"),
            # Customer D: 4 orders (3 in Dec 2019, 1 in Jan 2020) -> recency 31 days
            row("D", "2019-12-05"),
            row("D", "2019-12-15"),
            row("D", "2019-12-25"),
            row("D", "2020-01-01"),
            # Customer E: 5 orders, all Nov 2019 (none in the current period) -> recency 73 days
            row("E", "2019-11-01"),
            row("E", "2019-11-05"),
            row("E", "2019-11-10"),
            row("E", "2019-11-15"),
            row("E", "2019-11-20"),
        ]
    )


def _period_for(df: pd.DataFrame):
    period, _ = compute_core_metrics(df, MAPPING, now=NOW)
    return period


def test_customer_metrics_hand_calculated() -> None:
    df = _five_customer_scenario()
    period = _period_for(df)
    assert (period.current, period.previous) == ("2020-01", "2019-12")  # data_end 2020-01-31 is month-end

    customers = compute_customer_metrics(df, MAPPING, period)

    assert customers.rfm_reference_date == date(2020, 2, 1)  # data_end + 1 day

    by_segment = {s.segment: s for s in customers.segments}
    assert set(by_segment) == {"New", NEEDS_ATTENTION, "Loyal", "At-risk"}

    # A: r_score=5 (freshest), f_score=1 (fewest orders) -> New
    new = by_segment["New"]
    assert (new.customers, new.avg_monetary) == (1, 10.0)
    assert new.revenue_share_pct == pytest.approx(10 / 150 * 100)
    assert new.customers_previous == 1  # D, "New" as of the previous snapshot (below)

    # B: r_score=4, f_score=2 -> one of the 4 combinations no named rule covers
    needs_attention = by_segment[NEEDS_ATTENTION]
    assert (needs_attention.customers, needs_attention.avg_monetary) == (1, 20.0)
    assert needs_attention.customers_previous == 0

    # C: r_score=3, f_score=3 -> Loyal
    loyal = by_segment["Loyal"]
    assert (loyal.customers, loyal.avg_monetary) == (1, 30.0)
    assert loyal.customers_previous == 0

    # D and E: r_score in {1, 2}, f_score >= 3 -> At-risk
    at_risk = by_segment["At-risk"]
    assert at_risk.customers == 2
    assert at_risk.avg_monetary == 45.0  # (40 + 50) / 2
    assert at_risk.revenue_share_pct == pytest.approx(90 / 150 * 100)
    assert at_risk.customers_previous == 1  # E, "At-risk" as of the previous snapshot

    # new_vs_returning, scoped to the current period (2020-01) only:
    # A, B, C's first-ever purchase is in 2020-01 -> new. D's first-ever
    # purchase was 2019-12-05 (before the current period) -> returning. E has
    # no 2020-01 activity at all and is excluded entirely.
    nvr = customers.new_vs_returning
    assert (nvr.new_customers, nvr.returning_customers) == (3, 1)
    assert nvr.new_revenue == 60.0  # A(10) + B(10+10) + C(10+10+10)
    assert nvr.returning_revenue == 10.0  # D's single 2020-01 row


# --- edge cases --------------------------------------------------------------


def test_unmapped_customer_column_degrades_to_an_empty_block() -> None:
    mapping = {k: v for k, v in MAPPING.items() if v != "customer"}
    df = frame([{"Date": "2020-01-31", "Qty": "1", "Price": "10.0"}])
    period = _period_for(frame([row("A", "2020-01-31")]))

    customers = compute_customer_metrics(df, mapping, period)

    assert customers.rfm_reference_date == date(2020, 2, 1)  # still computed: doesn't need `customer`
    assert customers.segments == []
    assert customers.new_vs_returning.new_customers == 0
    assert customers.new_vs_returning.returning_customers == 0


def test_every_row_missing_its_customer_value_also_degrades_to_empty() -> None:
    df = frame([{"Date": "2020-01-31", "Qty": "1", "Price": "10.0", "Cust": None}])
    period = _period_for(df)

    customers = compute_customer_metrics(df, MAPPING, period)

    assert customers.segments == []


def test_a_return_only_customer_is_scored_like_any_other() -> None:
    # Their only-ever row is a return (negative quantity, 2A's convention):
    # negative Monetary, still scored and counted (2B). Was Champions - a lone
    # customer scored best (5, 5). SUPERSEDED for R and F (Thach, 2E-b): a
    # customer who never bought scores 1 and 1 and has a segment of their own,
    # "Returns only" - not Hibernating, which describes buyers who stopped.
    # Monetary stays net, and they are still counted.
    df = frame([row("Refunder", "2020-01-31", qty="-1", price="10.0")])
    period = _period_for(df)

    customers = compute_customer_metrics(df, MAPPING, period)

    assert len(customers.segments) == 1
    segment = customers.segments[0]
    assert segment.segment == "Returns only"
    assert (segment.customers, segment.avg_monetary) == (1, -10.0)

    assert customers.new_vs_returning.new_customers == 1
    assert customers.new_vs_returning.new_revenue == -10.0


def test_whitespace_only_customer_value_is_excluded_like_a_missing_one() -> None:
    df = frame(
        [
            row("Alice", "2020-01-31"),
            {"Date": "2020-01-30", "Qty": "1", "Price": "10.0", "Cust": "   "},
        ]
    )
    period = _period_for(df)

    customers = compute_customer_metrics(df, MAPPING, period)

    assert len(customers.segments) == 1
    assert customers.segments[0].customers == 1  # only Alice; the blank row is not a customer
    assert customers.new_vs_returning.new_customers == 1


def test_empty_new_vs_returning_results_do_not_share_mutable_state() -> None:
    # Doubt-review finding: a module-level singleton returned by reference
    # from every "no customer data" path would let an in-place mutation on
    # one run's result corrupt every other run's "empty" result too.
    mapping = {k: v for k, v in MAPPING.items() if v != "customer"}
    df = frame([{"Date": "2020-01-31", "Qty": "1", "Price": "10.0"}])
    period = _period_for(frame([row("A", "2020-01-31")]))

    first = compute_customer_metrics(df, mapping, period)
    first.new_vs_returning.new_revenue = 999.0

    second = compute_customer_metrics(df, mapping, period)

    assert second.new_vs_returning.new_revenue == 0.0


def test_revenue_share_pct_stays_sign_consistent_when_whole_file_monetary_is_negative() -> None:
    # BigReturner nets -900 (a heavy returner), SmallBuyer nets +1. The whole
    # file's total monetary is -899 (net negative). Dividing by the raw
    # signed total would flip signs (BigReturner > 100%, SmallBuyer negative);
    # dividing by the magnitude keeps each segment's own sign meaningful.
    df = frame(
        [
            row("BigReturner", "2020-01-31", qty="-90", price="10.0"),
            row("SmallBuyer", "2020-01-31", qty="1", price="1.0"),
        ]
    )
    period = _period_for(df)

    customers = compute_customer_metrics(df, MAPPING, period)
    by_segment = {s.segment: s for s in customers.segments}

    # BigReturner only refunded, so it never bought: "Returns only" (Thach,
    # 2E-b; it was Hibernating by row-order tie-break before). SmallBuyer is
    # the only buyer, so the buyers-only quintiles put it at the top ->
    # Champions. The shares are unchanged: the denominator is still |-899|.
    assert by_segment["Returns only"].avg_monetary == -900.0
    assert by_segment["Champions"].avg_monetary == 1.0

    assert by_segment["Returns only"].revenue_share_pct == pytest.approx(-900 / 899 * 100)
    assert by_segment["Champions"].revenue_share_pct == pytest.approx(1 / 899 * 100)
    assert by_segment["Returns only"].revenue_share_pct < 0  # the loss-making segment reads negative...
    assert by_segment["Champions"].revenue_share_pct > 0  # ...never inverted past +100%


def test_missing_unit_price_mapping_propagates_the_same_error_as_2a() -> None:
    from stages.analyze.metrics_core import RequiredColumnMissingError

    mapping = {k: v for k, v in MAPPING.items() if v != "unit_price"}
    df = frame([row("Alice", "2020-01-31")])
    period = _period_for(_five_customer_scenario())

    with pytest.raises(RequiredColumnMissingError):
        compute_customer_metrics(df, mapping, period)


def test_customer_metrics_for_run_reads_cleaned_csv_and_the_mapping(tmp_path: Path) -> None:
    run = create_run(tmp_path)
    (run.path / "cleaned.csv").write_text(
        "Date,Qty,Price,Cust\n2020-01-31,1,10.0,Alice\n2020-01-20,2,5.0,Alice\n",
        encoding="utf-8",
    )
    report = CleaningReportContract(
        schema_version="1.0",
        generated_at=NOW,
        rows_in=2,
        rows_out=2,
        columns_in=4,
        columns_out=4,
        changes=[],
        warnings=[],
        column_mapping=MAPPING,
    )
    (run.path / "cleaning_report.json").write_text(report.model_dump_json(), encoding="utf-8")

    customers = customer_metrics_for_run(tmp_path, run.run_id, now=NOW)

    assert customers.rfm_reference_date == date(2020, 2, 1)
    assert len(customers.segments) == 1
    assert customers.segments[0].customers == 1  # Alice, the only customer
