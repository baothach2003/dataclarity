"""Session 2E-l (Thach, 2026-09-27), the hypotheses and the R1/breadth guard,
written before the change.

A. P4 "Discounts and other deductions changed" (`-delta_deductions`) and P5
   "Charges paid by customers changed" (`delta_charges`), in the returns lens
   - an amendment to ADR-0005's pre-registered catalog.
B. R1 and breadth say "concentrated in one product" only when MORE THAN HALF
   of the change sits in the products, and measure concentration against the
   products' own change.

The shop (2E-d2 doubt-review cycle 3's): six products at 10 a day each, from
March to August, and one more line a day - a discount -1 @ 5, or postage
1 @ 5 - at 30 in August. In the discount shop P0 sells one unit fewer on
August 15, in the postage shop one more.
  discount: July 1,860 - 155 = 1,705; August 1,850 - 930 = 920 (-785)
  postage:  July 1,860 + 155 = 2,015; August 1,870 + 930 = 2,800 (+785)
Before 2E-l the discount month headlined P2 or "one product" for a sliver.
"""

from datetime import UTC, date, datetime, timedelta

import pandas as pd
import pytest

from contracts.cleaning import LineClassAnswer, OrderConfirmations
from stages.analyze.assemble import assemble_metrics
from stages.diagnose.catalog import BY_ID, CATALOG
from stages.diagnose.headline import choose_headline
from stages.diagnose.hypotheses import DECOMPOSITION, evaluate_hypotheses
from stages.diagnose.inputs import build_run_data
from stages.diagnose.step7_inputs import changes
from tests.stages.diagnose.test_hypotheses import by_id, step7

NOW = datetime(2026, 9, 26, 12, 0, tzinfo=UTC)
MAPPING = {"Date": "transaction_date", "Qty": "quantity", "Price": "unit_price", "Cust": "customer",
           "Sku": "sku", "Name": "product_name"}


def _shop(kind: str, p0_change: int = 0) -> pd.DataFrame:
    # From November: enough history for the headline's size test (decision 5).
    rows, day, i = [], date(2025, 11, 1), 0
    customers = [f"C{n}" for n in range(12)]
    while day <= date(2026, 8, 31):
        for k in range(6):
            rows.append((day.isoformat(), customers[i % 12], f"P{k}", f"PRODUCT {k}", "1", "10"))
            i += 1
        price = "30" if day.month == 8 else "5"
        if kind == "discount":
            rows.append((day.isoformat(), customers[i % 12], "D", "Discount", "-1", price))
        elif kind == "postage":
            rows.append((day.isoformat(), customers[i % 12], "POST", "POSTAGE", "1", price))
        i += 1
        day += timedelta(days=1)
    rows.append(("2026-09-01", "C1", "P1", "PRODUCT 1", "1", "10"))
    df = pd.DataFrame(rows, columns=["Date", "Cust", "Sku", "Name", "Qty", "Price"])
    if p0_change:
        # P0's units on August 15 move by p0_change.
        target = (df["Date"] == "2026-08-15") & (df["Sku"] == "P0")
        df.loc[target, "Qty"] = str(1 + p0_change)
    return df


def _step7(df: pd.DataFrame, classes: dict[str, str]):
    confirmations = OrderConfirmations(line_classes=[
        LineClassAnswer(value=value, field="sku", line_class=line_class)  # type: ignore[arg-type]  # a str from the dict
        for value, line_class in classes.items()])
    metrics = assemble_metrics(df, MAPPING, NOW, confirmations)
    inputs = step7(build_run_data(df, MAPPING, metrics, confirmations))
    hypotheses = evaluate_hypotheses(inputs)
    headline = choose_headline(inputs.trust, hypotheses, inputs.tree, changes(inputs))
    return inputs, by_id(hypotheses), headline


def test_the_catalog_holds_p4_and_p5_after_p3() -> None:
    ids = [spec.id for spec in CATALOG]

    assert ids[ids.index("P3") + 1: ids.index("P3") + 3] == ["P4", "P5"]
    assert (BY_ID["P4"].lens, BY_ID["P4"].kind, BY_ID["P5"].lens, BY_ID["P5"].kind) == (
        "returns", "term", "returns", "term")
    assert (DECOMPOSITION["P4"], DECOMPOSITION["P5"]) == ("returns", "returns")


def test_a_discount_promotion_month_headlines_the_deductions() -> None:
    _, results, headline = _step7(_shop("discount", p0_change=-1), {"D": "discount"})

    # Deductions 155 -> 930: P4 = -775 of the -785 change.
    assert results["P4"].verdict == "supported"
    assert results["P4"].contribution == pytest.approx(-775.0)
    assert (headline.rule, headline.hypothesis_id) == (6, "P4")
    assert "discounts and other deductions took more revenue away" in headline.message


def test_a_postage_price_month_headlines_the_charges() -> None:
    _, results, headline = _step7(_shop("postage", p0_change=1), {"POST": "charge"})

    # Charges 155 -> 930: P5 = +775 of the +785 change.
    assert results["P5"].verdict == "supported"
    assert results["P5"].contribution == pytest.approx(775.0)
    assert (headline.rule, headline.hypothesis_id) == (6, "P5")
    assert "customers paid more in charges" in headline.message


def test_the_change_outside_the_products_is_never_concentrated_in_one() -> None:
    inputs, results, _ = _step7(_shop("postage", p0_change=1), {"POST": "charge"})

    breadth = inputs.localization.breadth
    # The products moved +10 of +785.
    assert breadth.classification == "outside_products"
    assert breadth.products_share_of_change == pytest.approx(10 / 785)
    assert results["R1"].verdict == "ruled_out"


def _without_p0_sales(df: pd.DataFrame, last_day: int) -> pd.DataFrame:
    """P0 does not sell on August 1 to `last_day` - a change in its SALES,
    which is what the products' change counts (Thach, 2E-n: reading G)."""
    gone = (df["Sku"] == "P0") & (df["Date"] >= "2026-08-01") & (df["Date"] <= f"2026-08-{last_day:02d}")
    return df[~gone].reset_index(drop=True)


def test_a_change_in_one_product_is_still_concentrated() -> None:
    # P0 sells on none of August 1-21 (-210), the discount stays at 5 a day:
    # all of the -210 is in the products' sales, P0's.
    df = _without_p0_sales(_shop("discount"), 21)
    df.loc[(df["Sku"] == "D") & df["Date"].str.startswith("2026-08"), "Price"] = "5"

    inputs, results, _ = _step7(df, {"D": "discount"})

    breadth = inputs.localization.breadth
    assert breadth.products_share_of_change == pytest.approx(1.0)
    assert (breadth.classification, results["R1"].verdict) == ("concentrated", "supported")


def test_a_refund_of_one_product_is_the_returns_not_a_change_in_the_products() -> None:
    # Until 2E-n the test above booked its -210 as P0's August 15 line, a
    # refund of 20 instead of a sale of 1 - and the products held it all.
    # A refund is the customer returns class (Thach, 2E-n: reading G): the
    # products' sales moved only by the lost sale of 1 at 10, 5% of -210.
    df = _shop("discount", p0_change=-21)
    df.loc[(df["Sku"] == "D") & df["Date"].str.startswith("2026-08"), "Price"] = "5"

    inputs, results, _ = _step7(df, {"D": "discount"})

    breadth = inputs.localization.breadth
    assert breadth.products_share_of_change == pytest.approx(10 / 210)
    assert (breadth.classification, results["R1"].verdict) == ("outside_products", "ruled_out")
    assert results["P3"].contribution == pytest.approx(-200.0)


def test_exactly_half_in_the_products_is_not_more_than_half() -> None:
    # P0 sells on none of August's 31 days (-310), the discount 5 -> 15 a day
    # (deductions +310): the products hold exactly half of the -620 change -
    # not MORE than half (2E-k D1's word).
    df = _without_p0_sales(_shop("discount"), 31)
    df.loc[(df["Sku"] == "D") & df["Date"].str.startswith("2026-08"), "Price"] = "15"

    inputs, results, _ = _step7(df, {"D": "discount"})

    breadth = inputs.localization.breadth
    assert breadth.products_share_of_change == pytest.approx(0.5)
    assert (breadth.classification, results["R1"].verdict) == ("outside_products", "ruled_out")


def test_with_no_classed_charge_p5_is_not_testable() -> None:
    # Its requirement is "lines classed as charges" (review cycle 1 #6): with
    # none, "charges did not move" would be a finding the engine cannot make.
    _, results, _ = _step7(_shop("none", p0_change=-21), {})

    assert (results["P5"].verdict, results["P5"].contribution, results["P5"].share) == (
        "not_testable", None, None)


def test_with_a_classed_charge_that_did_not_move_p5_is_ruled_out() -> None:
    _, results, _ = _step7(_shop("postage", p0_change=-21).replace({"Price": {"30": "5"}}), {"POST": "charge"})

    assert (results["P5"].contribution, results["P5"].verdict) == (0.0, "ruled_out")
