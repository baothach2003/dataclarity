"""Session 2E in stage 3, written before the change (Thach's decisions, 2E).

1. B1 is no longer refused on refund months: with orders = sale rows, a
   refund cannot move purchase frequency. B2 stays refused until the
   three-factor level 2 (a session after 3E2): level 2 counts refunded units
   against the basket, so a month where ONLY refunds changed headlined
   "baskets got smaller (100%)" - measured in 2E with the refusal lifted.
2. mix_rate refuses a split it cannot make exact.
3. Stage 3 requires metrics.json 2.x and says to re-analyse a 1.x file.
4. Stage 2 and stage 3 agree on which previous months are incomplete: one
   definition, shared/periods.py.
"""

import json
from datetime import date, timedelta

import pandas as pd
import pytest
from pydantic import ValidationError

from shared.periods import previous_coverage
from stages.diagnose.frame import build_frame
from stages.diagnose.hypotheses import evaluate_hypotheses
from stages.diagnose.inputs import load_run
from stages.diagnose.mix_rate import compute_mix_rate
from tests.stages.diagnose.diagnose_fixtures import MAPPING, daily_rows, row, run_data
from tests.stages.diagnose.test_hypotheses import by_id, step7
from tests.stages.diagnose.test_localization import CATEGORY_MAPPING
from tests.stages.diagnose.test_localization import row as category_row


def _steady(refunds: int = 0, qty_cur: float = 2.0) -> list[dict]:
    """Three customers, one sale of 2 x 10 each every day from December 2010;
    January 2012 optionally changes quantity and adds `refunds` refund lines."""
    rows = []
    day = date(2010, 12, 1)
    while day <= date(2012, 1, 31):
        for customer in ("Ann", "Bob", "Cy"):
            rows.append(row(day, qty=qty_cur if day.year == 2012 else 2.0, price=10.0,
                            customer=customer))
        day += timedelta(days=1)
    rows += [row(date(2012, 1, 2 + i), qty=-1.0, price=10.0, customer="Ann")
             for i in range(refunds)]
    return rows


# --- 1. B1 and B2 on refund months ---------------------------------------------------


def test_refunds_alone_do_not_move_purchase_frequency() -> None:
    """Only refunds changed (10 lines of 1 x 10, net -100). Orders and
    customers are the same both months, so frequency contributes exactly 0:
    B1 is evaluated now, and ruled out."""
    b1 = by_id(evaluate_hypotheses(step7(run_data(_steady(refunds=10)))))["B1"]

    assert b1.verdict == "ruled_out"
    assert b1.contribution == 0.0


def test_b2_is_still_refused_on_refund_months_until_level_2_separates_refunds() -> None:
    """The measured reason: with the refusal lifted, this month headlined
    "baskets got smaller (100% of the change)" while baskets were unchanged."""
    b2 = by_id(evaluate_hypotheses(step7(run_data(_steady(refunds=10)))))["B2"]

    assert b2.verdict == "inconclusive"
    assert "refunded units" in b2.rule


def test_b2_still_reads_a_real_basket_change_without_refunds() -> None:
    """Quantity 2 -> 1.5 and no refunds: B2 is evaluated and supported."""
    b2 = by_id(evaluate_hypotheses(step7(run_data(_steady(qty_cur=1.5)))))["B2"]

    assert (b2.verdict, b2.statement) == ("supported", "Baskets got smaller")


# --- 2. mix_rate ------------------------------------------------------------------------


def test_mix_rate_refuses_a_category_that_only_refunded() -> None:
    """November: category Gift has a refund line and no sale, so 0 orders
    and -30 revenue. Its AOV is -30 / 0: it would drop out of the weighted
    average, and the AOV split would stop summing to the overall change
    ((8 x 22 + 2 x 105 - 30) / 10 - 60). Price per unit keeps a weight (-1
    unit), so only an AOV split is refused."""
    rows = []
    for index in range(5):
        rows.append(category_row(date(2011, 10, index + 1), qty=1, price=20.0, category="Cheap"))
        rows.append(category_row(date(2011, 10, index + 10), qty=5, price=20.0, category="Dear"))
    rows += [category_row(date(2011, 11, 30), qty=1, price=22.0, category="Cheap") for _ in range(8)]
    rows += [category_row(date(2011, 11, 30), qty=5, price=21.0, category="Dear") for _ in range(2)]
    rows.append(category_row(date(2011, 11, 30), qty=-1, price=30.0, category="Gift"))

    mix_rate = compute_mix_rate(run_data(rows, CATEGORY_MAPPING))

    assert mix_rate is None or mix_rate.metric != "aov"


# --- 3. the metrics.json version -------------------------------------------------------


def test_stage_3_refuses_a_1x_metrics_file_and_says_to_re_analyse(tmp_path) -> None:
    from shared.run_registry import create_run
    from stages.analyze.assemble import assemble_metrics

    run = create_run(tmp_path)
    df = pd.DataFrame(_steady())
    df.to_csv(run.path / "cleaned.csv", index=False)
    (run.path / "cleaning_report.json").write_text(json.dumps({
        "schema_version": "1.0", "generated_at": "2026-09-24T00:00:00Z", "rows_in": 1,
        "rows_out": 1, "columns_in": 1, "columns_out": 1, "changes": [], "warnings": [],
        "column_mapping": MAPPING}), encoding="utf-8")
    metrics = json.loads(assemble_metrics(df, MAPPING).model_dump_json())
    metrics["schema_version"] = "1.0"
    (run.path / "metrics.json").write_text(json.dumps(metrics), encoding="utf-8")

    with pytest.raises(ValidationError, match="re-analyse this run"):
        load_run(tmp_path, run.run_id)


# --- 4. one definition of an incomplete previous month --------------------------------


@pytest.mark.parametrize("start,complete", [
    (date(2011, 1, 1), True), (date(2011, 1, 2), True), (date(2011, 1, 3), True),
    (date(2011, 1, 4), False), (date(2011, 1, 15), False), (date(2011, 2, 1), False),
])
def test_both_stages_agree_on_an_incomplete_previous_month(start, complete) -> None:
    """Stage 2's `period.previous_complete` and stage 3's frame and trust gate
    read the same rows the same way, at and around the 3-day boundary."""
    data = run_data(daily_rows(start, date(2011, 2, 28)))
    inputs = step7(data)
    d1 = next(check for check in inputs.trust.checks if check.id == "D1")

    counted = data.parsed.dates[data.parsed.counted]
    shared = previous_coverage(counted, data.metrics.period.previous)

    assert data.metrics.period.previous_complete is complete
    assert shared.complete is complete
    assert build_frame(data).previous_leading_days_missing == shared.leading_days_missing
    assert (d1.status == "blocked") is (not complete)


def test_the_shared_constants_equal_the_stage_3_ones_they_are_stated_to_equal() -> None:
    """shared/ cannot import a stage, so the value is stated twice; this is
    what keeps "equal to D1's caution size" true rather than a comment. (The
    residue tolerance is no longer stated twice: stage 3 imports it.)"""
    from shared.periods import PREVIOUS_MIN_MISSING_DAYS
    from stages.diagnose.thresholds import D1_CAUTION_DAYS, D1_CAUTION_SHARE

    assert PREVIOUS_MIN_MISSING_DAYS == D1_CAUTION_DAYS
    # D1's share condition is not repeated in shared/periods.py because it
    # cannot bind: the largest whole count "fewer than 3" allows (2 days) is
    # under 10% of every month length, 2.8 to 3.1 days.
    assert all(PREVIOUS_MIN_MISSING_DAYS - 1 < D1_CAUTION_SHARE * days
               for days in (28, 29, 30, 31))



# --- a product seen only through a refund (mutation check, 2E) ------------------------


def _refund_only_in_january() -> list[dict]:
    """Product Old sells daily through December 2011; in January 2012 it has
    only two refund lines. Product New sells daily in January only."""
    rows = daily_rows(date(2011, 1, 1), date(2011, 12, 31), product="Old")
    rows += [row(date(2012, 1, 3), qty=-1.0, product="Old"),
             row(date(2012, 1, 4), qty=-1.0, product="Old")]
    rows += daily_rows(date(2012, 1, 1), date(2012, 1, 31), product="New")
    return rows


def test_a_product_with_only_refunds_this_month_is_still_present() -> None:
    """Presence is a revenue-counted row (3C decision (c)), so Old is not
    "removed" - it is there, refunding - and its refunds are not orders."""
    from stages.diagnose.members import build_dimension, product_totals

    data = run_data(_refund_only_in_january())
    totals = product_totals(data)
    dimension = build_dimension("product", totals, data.metrics.core.revenue_current
                                - data.metrics.core.revenue_previous)

    assert "Old" not in dimension.removed_members
    assert int(totals.orders_cur.get("name:old", 0)) == 0


def test_p1_needs_products_sold_in_both_months_not_merely_refunded() -> None:
    """P1's like-for-like set L is products with positive sold units in both
    months (pvm.py). Old only refunded in January, so L is empty and P1 has
    nothing to test: inconclusive, not "ruled out with contribution 0"."""
    p1 = by_id(evaluate_hypotheses(step7(run_data(_refund_only_in_january()))))["P1"]

    assert p1.verdict == "inconclusive"
