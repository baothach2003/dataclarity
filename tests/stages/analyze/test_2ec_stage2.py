"""Session 2E-c, stage 2 (Thach), written before the change.

1. Orders, buyers and AOV count SALE rows - quantity > 0 AND a positive
   amount - so a free item and a coupon line are not orders.
2. Identical customers receive identical RFM scores; ties are never broken by
   customer id (supersedes 2B's rank(method="first")). The rule, "meanpos":
   score every position as before, then each tied group takes the MEAN of its
   positions' scores, exact halves rounded down. A file with no ties scores
   exactly as before; a population that ties throughout scores 3.
3. metrics.json 3.0: the meaning of orders, buyers, AOV, new customers and
   RFM scores changed, and the version is a promise to every reader.
"""

from datetime import date

import numpy as np
import pandas as pd
import pytest
from pydantic import ValidationError

from contracts.metrics import MetricsContract
from stages.analyze.assemble import SCHEMA_VERSION, assemble_metrics
from stages.analyze.rfm import rfm_snapshot, score_quintile
from tests.stages.diagnose.diagnose_fixtures import MAPPING, NOW, row


def _two_months(extra: list[dict]) -> list[dict]:
    """Ten customers each buy one unit at 10 on the 1st-10th of July and of
    August 2026, plus `extra`, plus one sale on 1 September so August is a
    complete month."""
    rows = []
    for month in (7, 8):
        rows += [row(date(2026, month, day), qty=1.0, price=10.0, customer=f"C{day}")
                 for day in range(1, 11)]
    rows.append(row(date(2026, 9, 1), qty=1.0, price=10.0, customer="C1"))
    return rows + extra


def test_a_free_item_and_a_coupon_are_not_orders() -> None:
    """August adds a free item for a new customer (1 @ 0), a free item for C2
    (2 @ 0) and a coupon for C1 (1 @ -5). By hand: orders 10 (not 13);
    revenue 100 - 5 = 95; AOV 95 / 10 = 9.5 (not 95 / 13 = 7.31); buyers 10
    (the free-item customer bought nothing); active customers 11 (any row)."""
    extra = [row(date(2026, 8, 12), qty=1.0, price=0.0, customer="Freebie"),
             row(date(2026, 8, 16), qty=2.0, price=0.0, customer="C2"),
             row(date(2026, 8, 15), qty=1.0, price=-5.0, customer="C1")]

    core = assemble_metrics(pd.DataFrame(_two_months(extra)), MAPPING, now=NOW).core

    assert core.orders_current == 10
    assert core.revenue_current == pytest.approx(95.0)
    assert core.aov_current == pytest.approx(9.5)
    assert core.buyers_current == 10
    assert core.active_customers_current == 11


# --- RFM ties (F2) --------------------------------------------------------------


def _one_time_buyers(names: list[str]) -> pd.DataFrame:
    return pd.DataFrame({"customer": names,
                         "date": pd.to_datetime(["2011-06-01"] * len(names)),
                         "revenue": [10.0] * len(names), "sale": [True] * len(names)})


def test_identical_buyers_get_identical_scores() -> None:
    """2E-b review F2: five identical one-time buyers came out Hibernating,
    Hibernating, Loyal, Champions, Champions by customer id."""
    snapshot = rfm_snapshot(_one_time_buyers(["amy", "ben", "cat", "dan", "eve"]),
                            date(2011, 12, 1))

    assert snapshot["r_score"].nunique() == 1
    assert snapshot["f_score"].nunique() == 1
    assert snapshot["segment"].nunique() == 1


def test_renaming_a_customer_moves_no_one() -> None:
    """Renaming amy to zed made zed a Champion and ben Hibernating."""
    before = rfm_snapshot(_one_time_buyers(["amy", "ben", "cat", "dan", "eve"]),
                          date(2011, 12, 1))
    after = rfm_snapshot(_one_time_buyers(["zed", "ben", "cat", "dan", "eve"]),
                         date(2011, 12, 1))

    assert after.loc["zed", "segment"] == before.loc["amy", "segment"]
    columns = ["r_score", "f_score", "segment"]
    assert after.loc[["ben", "cat", "dan", "eve"], columns].equals(
        before.loc[["ben", "cat", "dan", "eve"], columns])


def test_a_population_that_ties_throughout_scores_the_middle() -> None:
    """Ten equal values: no one is better than anyone. Was 1,1,2,2,3,3,4,4,5,5
    by position (2B); now every one scores 3."""
    values = pd.Series([5] * 10)

    assert list(score_quintile(values, ascending=True)) == [3] * 10
    assert list(score_quintile(values, ascending=False)) == [3] * 10


def test_a_tied_group_takes_the_mean_of_its_positions_scores() -> None:
    """Ten values, ascending (Frequency: largest is best). Position scores
    by rank, as before: 1,1,2,2,3,3,4,4,5,5.
    - 10 (position 1): 1.
    - the two 20s (positions 2 and 3, scores 1 and 2): mean 1.5, an exact
      half, rounded DOWN -> 1 (a tie never lifts a group).
    - the three 30s (positions 4-6, scores 2, 3, 3): mean 2.67 -> 3.
    - 40, 50, 60, 70 (positions 7-10): 4, 4, 5, 5."""
    values = pd.Series([10, 20, 20, 30, 30, 30, 40, 50, 60, 70])

    assert list(score_quintile(values, ascending=True)) == [1, 1, 1, 3, 3, 3, 4, 4, 5, 5]


def _before(values: pd.Series, ascending: bool) -> list[int]:
    """2B's rule, which untied files must keep exactly."""
    ranks = values.rank(method="first", ascending=ascending)
    return pd.qcut(ranks, 5, labels=[1, 2, 3, 4, 5]).astype(int).tolist()


@pytest.mark.parametrize("ascending", [True, False])
def test_a_file_with_no_ties_scores_exactly_as_before(ascending: bool) -> None:
    """Every size from 2 to 120, distinct values in shuffled order: a group of
    one keeps its own position's score, so nothing moves."""
    rng = np.random.default_rng(7)
    for n in range(2, 121):
        values = pd.Series(rng.permutation(n).astype(float) * 3.5 + 1)
        assert list(score_quintile(values, ascending=ascending)) == _before(values, ascending), n


# --- metrics.json 3.0 --------------------------------------------------------------


def test_metrics_json_is_the_current_major_version() -> None:
    # 3.0 in 2E-c; 4.0 in 2E-c2; 5.0 since 2E-e (test_2ee_stage2.py).
    assert SCHEMA_VERSION == "8.0"
    metrics = assemble_metrics(pd.DataFrame(_two_months([])), MAPPING, now=NOW)
    assert metrics.schema_version == "8.0"


def test_a_2x_metrics_json_is_refused_with_a_reason_to_reanalyse() -> None:
    payload = assemble_metrics(pd.DataFrame(_two_months([])), MAPPING,
                               now=NOW).model_dump(mode="json")
    payload["schema_version"] = "2.0"  # any older major is refused

    with pytest.raises(ValidationError, match="re-analyse"):
        MetricsContract.model_validate(payload)

