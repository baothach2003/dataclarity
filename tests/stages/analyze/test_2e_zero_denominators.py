"""One rule for every ratio in metrics.json 2.0 (Thach, 2E): a zero or
NEGLIGIBLE denominator gives null with a reason, never 2A's 0.0. Negligible
means floating-point residue next to the figures compared - the definition
stage 3 uses (shared/numbers.py) - because a flat month's residue produced
shares of 1e15 twice in stage 3 (3C, 3D). Each money denominator is tested
at residue as well as at an exact zero; order and product counts are
integers and have no residue.
"""

from datetime import UTC, datetime

import pandas as pd
import pytest

from stages.analyze.assemble import assemble_metrics
from stages.analyze.metrics_core import compute_core_metrics

NOW = datetime(2026, 9, 19, 12, 0, tzinfo=UTC)
MAPPING = {"Date": "transaction_date", "Qty": "quantity", "Price": "unit_price",
           "Product": "product_name", "Cat": "category", "Cust": "customer"}


def r(day: str, qty: float, price: float = 10.0, product: str = "Widget",
      cat: str = "A", cust: str = "Alice") -> dict:
    return {"Date": day, "Qty": repr(qty), "Price": repr(price), "Product": product,
            "Cat": cat, "Cust": cust}


# --- aov and return_rate: zero orders ------------------------------------------------


def test_aov_and_return_rate_are_unavailable_in_a_month_with_no_orders() -> None:
    """October: one sale. November: only a refund line - no order. AOV is
    -10 / 0 and return rate 1 / 0: both unavailable (were 0.0 under 2A)."""
    df = pd.DataFrame([r("2011-10-01", 1), r("2011-11-30", -1)])

    _, core = compute_core_metrics(df, MAPPING, NOW)

    assert core.orders_current == 0
    assert (core.aov_current, core.return_rate_current) == (None, None)
    assert "no orders in 2011-11" in core.aov_current_reason
    assert "no orders in 2011-11" in core.return_rate_current_reason
    assert core.aov_previous == pytest.approx(10.0) and core.aov_previous_reason is None


# --- contribution_pct: the total change ----------------------------------------------


def _flat(prev: list[float], cur: list[float]) -> pd.DataFrame:
    """Category A's December quantities `prev` and January `cur`, price 1,
    with rows on the 1st and 31st so both months are complete."""
    rows = [r("2019-12-01", q, 1.0) for q in prev[:-1]] + [r("2019-12-31", prev[-1], 1.0)]
    rows += [r("2020-01-01", q, 1.0) for q in cur[:-1]] + [r("2020-01-31", cur[-1], 1.0)]
    return pd.DataFrame(rows)


def test_contribution_is_unavailable_when_the_total_change_is_exactly_zero() -> None:
    """December 10 + 10 = 20, January 5 + 15 = 20: the change is 0, and a
    share of nothing is not 0% (was 0.0 under 2A)."""
    metrics = assemble_metrics(_flat([10.0, 10.0], [5.0, 15.0]), MAPPING, NOW)

    assert all(c.contribution_pct is None for c in metrics.by_dimension.category)
    assert "total change" in metrics.by_dimension.contribution_reason


def test_contribution_at_float_residue_is_unavailable() -> None:
    """December 0.1 + 0.2 = 0.30000000000000004; January 0.3. The total change
    is -5.55e-17 - residue, not a change - and a share of it read 1e15."""
    df = _flat([0.1, 0.2], [0.3])
    total = df.assign(v=df.Qty.astype(float) * df.Price.astype(float)).groupby(
        df.Date.str[:7])["v"].sum()
    assert 0 < abs(total["2020-01"] - total["2019-12"]) < 1e-15  # the fixture is residue

    metrics = assemble_metrics(df, MAPPING, NOW)

    assert metrics.by_dimension.category[0].contribution_pct is None
    assert "total change" in metrics.by_dimension.contribution_reason


# --- revenue_share_pct: whole-file monetary ---------------------------------------------


@pytest.mark.parametrize("ann,bob", [
    ([10.0], [-10.0]),        # exact: 10 - 10 = 0
    ([0.1, 0.2], [-0.3]),     # residue: 5.55e-17
])
def test_segment_share_is_unavailable_when_whole_file_monetary_is_nothing(ann, bob) -> None:
    rows = [r("2019-12-01", q, 1.0, cust="Ann") for q in ann]
    rows += [r("2020-01-31", q, 1.0, cust="Bob") for q in bob]
    metrics = assemble_metrics(pd.DataFrame(rows), MAPPING, NOW)

    assert all(s.revenue_share_pct is None for s in metrics.customers.segments)
    assert "monetary" in metrics.customers.revenue_share_reason


# --- concentration_pct: no products ----------------------------------------------------


def test_concentration_is_unavailable_with_no_product_in_the_month() -> None:
    """January holds only a refund: no product has positive revenue."""
    df = pd.DataFrame([r("2019-12-01", 1), r("2019-12-31", 1), r("2020-01-31", -1)])

    pareto = assemble_metrics(df, MAPPING, NOW).products.pareto

    assert pareto.total_products == 0
    assert pareto.concentration_pct is None
    assert "no product" in pareto.concentration_reason
