"""Session 2E-f, stage 2 (Thach, after 2E-e), written before the change.

1. New customers net each product on the opening day (N2, shared with
   stage 3 through shared/first_purchase.py).
2. The RFM tie rule (T2): a customer with exactly one order scores F = 1 -
   "bought once" is a fact of the data, not a rank. Every other score is
   unchanged. Under the mean-position tie rule (2E-c), one-time buyers above
   40% of buyers scored F = 2 and could never be "New", and a file where
   everyone bought once called 12 of 20 customers "Loyal". Measured: no
   customer of Online Retail II or the Kaggle demo changes segment.
3. (a) A single customer with one purchase is New, superseding 2B's 5/5 for
   that case: 5/5 is a convention for "no one to compare against", one
   purchase is a fact, and a fact overrides a convention.
4. A customer written on a receipt's first line only (header-style exports)
   owns every line of it when order_id is trusted. Measured on Online Retail
   II rewritten header-style: new revenue in 2011-11 read 8,783.75 against
   79,845.90; with the fill every figure equals the original.
5. metrics.json 6.0: new_vs_returning, RFM F and segment money changed
   meaning.
"""

from datetime import date

import pandas as pd
import pytest

from contracts.metrics import MetricsContract
from stages.analyze.assemble import SCHEMA_VERSION, assemble_metrics
from stages.analyze.rfm import rfm_snapshot
from tests.stages.diagnose.diagnose_fixtures import MAPPING, NOW, row

WITH_ORDERS = {**MAPPING, "Inv": "order_id"}


def _table(orders_by_customer: dict[str, list[date]]) -> pd.DataFrame:
    """One sale line of 10 per order."""
    rows = [{"customer": name, "date": pd.Timestamp(day), "revenue": 10.0, "sale": True,
             "order": f"{name}-{index}", "returned": False}
            for name, days in orders_by_customer.items() for index, day in enumerate(days)]
    return pd.DataFrame(rows)


def test_when_everyone_bought_once_no_one_is_loyal() -> None:
    """Five one-time buyers on five different days. R by hand: 1 (oldest) to
    5 (latest); F = 1 for all. Segments: R 5 and 4 -> New, R 3 -> Needs
    Attention, R 2 and 1 -> Hibernating. The mean-position rule gave every
    one F = 3: 3 Loyal and 2 At-risk."""
    table = _table({f"c{i}": [date(2026, 8, 1 + 5 * i)] for i in range(5)})

    snapshot = rfm_snapshot(table, date(2026, 9, 1))

    assert snapshot["f_score"].tolist() == [1, 1, 1, 1, 1]
    assert snapshot["segment"].to_dict() == {
        "c0": "Hibernating", "c1": "Hibernating", "c2": "Needs Attention",
        "c3": "New", "c4": "New"}


def test_one_time_buyers_score_one_when_they_are_45_percent() -> None:
    """9 of 20 buyers bought once, the others 2 to 12 times. Positions 1-9
    are the one-timers; five groups of four give them scores
    1,1,1,1,2,2,2,2,3, mean 1.67 -> 2 under the mean-position rule. Now 1.
    The customer with 2 orders sits at position 10 -> score 3, unchanged."""
    orders = {f"once{i}": [date(2026, 8, 1)] for i in range(9)}
    orders |= {f"many{n:02d}": [date(2026, 1, 1 + k) for k in range(n)] for n in range(2, 13)}
    snapshot = rfm_snapshot(_table(orders), date(2026, 9, 1))

    assert set(snapshot.loc[[f"once{i}" for i in range(9)], "f_score"]) == {1}
    assert snapshot.loc["many02", "f_score"] == 3
    assert snapshot.loc["many12", "f_score"] == 5


def test_a_single_customer_with_one_purchase_is_new() -> None:
    """(a): R = 5 by 2B's convention, F = 1 by the fact."""
    snapshot = rfm_snapshot(_table({"solo": [date(2026, 8, 1)]}), date(2026, 9, 1))

    assert (snapshot.loc["solo", "r_score"], snapshot.loc["solo", "f_score"]) == (5, 1)
    assert snapshot.loc["solo", "segment"] == "New"


def test_a_single_customer_with_two_purchases_keeps_2b_convention() -> None:
    snapshot = rfm_snapshot(_table({"solo": [date(2026, 7, 1), date(2026, 8, 1)]}),
                            date(2026, 9, 1))

    assert snapshot.loc["solo", "segment"] == "Champions"


def test_a_product_bought_and_part_returned_on_the_first_day_is_a_new_customer() -> None:
    """X buys 2 mugs at 10 and returns 1 on 7 August, her first day: new,
    with 2 x 10 - 10 = 10 of new revenue. Regular (July and August) is
    returning with 10. Under "any return line on the first day" X was
    returning and new revenue was 0."""
    rows = [row(date(2026, 7, 5), customer="Regular"), row(date(2026, 8, 5), customer="Regular"),
            row(date(2026, 8, 7), qty=2.0, product="Mug", customer="X"),
            row(date(2026, 8, 7), qty=-1.0, product="Mug", customer="X"),
            row(date(2026, 9, 1), customer="Regular")]

    split = assemble_metrics(pd.DataFrame(rows), MAPPING, now=NOW).customers.new_vs_returning

    assert (split.new_customers, split.new_revenue) == (1, pytest.approx(10.0))
    assert (split.returning_customers, split.returning_revenue) == (1, pytest.approx(10.0))


def _receipts(header_style: bool) -> list[dict]:
    """July: A's receipt J1, three lines at 10. August: A's A1, two lines
    (20); B's first receipt A2, a free sample (1 @ 0) then three lines at 10
    (30). 1 September: A's S. In the header-style copy only each receipt's
    first line names the customer - for B, the free sample, so read raw B
    bought nothing."""
    receipts = [("J1", date(2026, 7, 10), "A", 3), ("A1", date(2026, 8, 10), "A", 2),
                ("A2", date(2026, 8, 12), "B", 4), ("S", date(2026, 9, 1), "A", 1)]
    rows = []
    for receipt, day, customer, lines in receipts:
        for line in range(lines):
            name = customer if line == 0 or not header_style else ""
            price = 0.0 if receipt == "A2" and line == 0 else 10.0
            rows.append({**row(day, price=price, product=f"P{line}", customer=name),
                         "Inv": receipt})
    return rows


def _customers(rows, mapping=WITH_ORDERS):
    metrics = assemble_metrics(pd.DataFrame(rows), mapping, now=NOW)
    segments = {s.segment: (s.customers, s.avg_monetary, s.revenue_share_pct)
                for s in metrics.customers.segments}
    return metrics, segments


def test_a_header_style_export_reads_as_the_fully_named_file() -> None:
    """By hand, August: B is new with 30, A returning with 20. RFM: A has 3
    orders and 60, B 1 order and 30. Today the header-style copy gave B 10
    and A 10 - only each receipt's first line."""
    named, named_segments = _customers(_receipts(header_style=False))
    header, header_segments = _customers(_receipts(header_style=True))
    split = header.customers.new_vs_returning

    assert (split.new_customers, split.new_revenue) == (1, pytest.approx(30.0))
    assert (split.returning_customers, split.returning_revenue) == (1, pytest.approx(20.0))
    assert header_segments == named_segments
    assert (header.core.buyers_current, header.core.active_customers_current) == (2, 2)
    assert (named.core.buyers_current, named.core.active_customers_current) == (2, 2)


def test_without_order_id_a_header_style_file_is_not_filled() -> None:
    """No trusted receipt, no fill: the unnamed lines stay unattributed and
    only the first lines count - B's free sample (0) and A's 10. B holds no
    sale row, so B is not new."""
    mapping = {k: v for k, v in WITH_ORDERS.items() if v != "order_id"}
    header, _ = _customers(_receipts(header_style=True), mapping)
    split = header.customers.new_vs_returning

    assert (split.new_customers, split.new_revenue) == (0, pytest.approx(0.0))
    assert split.returning_revenue == pytest.approx(10.0)


def test_metrics_json_is_version_6_or_the_current_one() -> None:
    # 6.0 in 2E-f; 7.0 since 2E-g (test_2eg_stage2.py).
    assert SCHEMA_VERSION == "7.0"
    assert MetricsContract.supported_major == 7
