"""Session 2E-l, doubt-review cycle 1, written before the fixes.

F1 A promotion month (or a postage month) headlined a gross-lens sliver: a
   product-lens share is a share of the GROSS change, which such a month
   barely moves, so one unit's mix shift reached a fit of 1.0 and beat P4 /
   P5 (shares of the net change, just under 1). Rule 6 names a product-lens
   hypothesis only when more than half of the change sits in the product
   lens - Thach's "more than half" of B.
F2 Lines with no product identity (neither SKU nor name; pooled items since
   2E-l) were one bucket the product lens priced like-for-like and counted
   as launched or discontinued: M "Manual"'s average price over unrelated
   items was 40,647 of P1 on Online Retail II 2011-11. The bucket is its own
   term, `unidentified` - in the total, never a product (Thach, 2E-g; Q4).
F4 "More than half" is decided above floating-point residue.

The sliver shop: P0-P4 at 10 and P5 at 5, one unit each a day, March to
August; on August 15 one unit of P0 is sold as P5 instead (mix -5). One more
line a day: a discount -1 @ 5, 30 in August; or postage 1 @ 30, 5 in August.
  discount: July 1,705 - 155 = 1,550; August 1,700 - 930 = 770 (-780)
  postage:  July 1,705 + 930 = 2,635; August 1,700 + 155 = 1,855 (-780)
The gross change is -5 in both; the deductions carry -775, or the charges.
"""

import math
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

import pandas as pd
import pytest

from contracts.cleaning import LineClassAnswer, OrderConfirmations
from contracts.diagnosis import Hypothesis
from stages.analyze.assemble import assemble_metrics
from stages.diagnose.catalog import CATALOG
from stages.diagnose.headline import choose_headline
from stages.diagnose.hypotheses import decomposition_gross, evaluate_hypotheses
from stages.diagnose.inputs import build_run_data
from stages.diagnose.localization import compute_breadth
from stages.diagnose.members import MemberTotals
from stages.diagnose.numbers import products_hold_most
from stages.diagnose.step7_inputs import Changes, changes
from tests.stages.diagnose.test_headline import trust
from tests.stages.diagnose.test_hypotheses import by_id, step7

NOW = datetime(2026, 9, 26, 12, 0, tzinfo=UTC)
MAPPING = {"Date": "transaction_date", "Qty": "quantity", "Price": "unit_price", "Cust": "customer",
           "Sku": "sku", "Name": "product_name"}
COLUMNS = ["Date", "Cust", "Sku", "Name", "Qty", "Price"]


def _days():
    # From November: eight month-to-month movements before August, enough for
    # the headline's size test (Thach, 2026-10-03: too short names no cause).
    day = date(2025, 11, 1)
    while day <= date(2026, 8, 31):
        yield day
        day += timedelta(days=1)


def _sliver_shop(kind: str) -> pd.DataFrame:
    rows, i = [], 0
    for day in _days():
        for k, price in enumerate((10, 10, 10, 10, 10, 5)):
            sku, price = ("P5", 5) if (day == date(2026, 8, 15) and k == 0) else (f"P{k}", price)
            rows.append((day.isoformat(), f"C{i % 12}", sku, f"PRODUCT {sku}", "1", str(price)))
            i += 1
        august = day.month == 8
        if kind == "discount":
            rows.append((day.isoformat(), f"C{i % 12}", "D", "Discount", "-1", "30" if august else "5"))
        else:
            rows.append((day.isoformat(), f"C{i % 12}", "POST", "POSTAGE", "1", "5" if august else "30"))
        i += 1
    rows.append(("2026-09-01", "C1", "P1", "PRODUCT P1", "1", "10"))
    return pd.DataFrame(rows, columns=COLUMNS)


def _run(df: pd.DataFrame, classes: dict[str, str]):
    confirmations = OrderConfirmations(line_classes=[
        LineClassAnswer(value=value, field="sku", line_class=line_class)  # type: ignore[arg-type]  # a str from the dict
        for value, line_class in classes.items()])
    metrics = assemble_metrics(df, MAPPING, NOW, confirmations)
    inputs = step7(build_run_data(df, MAPPING, metrics, confirmations))
    hypotheses = evaluate_hypotheses(inputs)
    headline = choose_headline(inputs.trust, hypotheses, inputs.tree, changes(inputs))
    return inputs, by_id(hypotheses), headline


# --- F1: the headline ---------------------------------------------------------

def test_a_promotion_month_headlines_the_discounts_not_a_mix_sliver() -> None:
    _, results, headline = _run(_sliver_shop("discount"), {"D": "discount"})

    # P2 still explains the GROSS change (-5 of -5); it is no headline for -780.
    assert (results["P2"].verdict, results["P2"].contribution) == ("supported", pytest.approx(-5.0))
    assert results["P4"].contribution == pytest.approx(-775.0)
    assert (headline.rule, headline.hypothesis_id) == (6, "P4")
    assert headline.message == (
        "Revenue went from 1,550.00 to 770.00 (-780.00). The best-supported explanation: "
        "discounts and other deductions took more revenue away (returns lens, 99% of the change).")


def test_a_month_of_cheaper_postage_headlines_the_charges_not_a_mix_sliver() -> None:
    _, results, headline = _run(_sliver_shop("postage"), {"POST": "charge"})

    assert results["P2"].verdict == "supported"
    assert results["P5"].contribution == pytest.approx(-775.0)
    assert (headline.rule, headline.hypothesis_id) == (6, "P5")
    assert "customers paid less in charges (postage, delivery)" in headline.message


def _product_lens_headline(gross: float, holds: bool) -> tuple[int, str | None]:
    # P1 explains all of the gross change; the net change is -200. Whether
    # the products hold more than half of it is breadth's decision (Thach,
    # 2E-m: one definition - the products' NET change over the net change;
    # its exact half and residue are tested at breadth, below).
    hypotheses = []
    for spec in CATALOG:
        supported = spec.id == "P1"
        hypotheses.append(Hypothesis(
            id=spec.id, family=spec.family, lens=spec.lens, statement=spec.statement,
            verdict="supported" if supported else "ruled_out",
            contribution=gross if supported else None, share=1.0 if supported else None,
            evidence={}, rule="test"))
    moved = Changes(revenue_prev=1000.0, revenue_cur=800.0, net=-200.0, gross=gross, alert=False,
                    products_hold_the_change=holds)
    headline = choose_headline(trust(), hypotheses, None, moved)
    return headline.rule, headline.hypothesis_id


def test_a_product_lens_cause_headlines_only_when_the_lens_holds_more_than_half() -> None:
    assert _product_lens_headline(-101.0, holds=True) == (6, "P1")
    # Since 2E-m the gross change no longer decides: more than half of the
    # net change in gross, but not in the products' own change - no P1...
    assert _product_lens_headline(-101.0, holds=False) == (7, None)
    # ...and the products holding the change opens it at any gross.
    assert _product_lens_headline(-100.0, holds=True) == (6, "P1")
    # A gross change the other way moves against the change: never named.
    assert _product_lens_headline(150.0, holds=True) == (7, None)


# --- F4: breadth's "more than half" above residue -----------------------------

def test_a_share_of_minus_zero_is_zero() -> None:
    # 2E-n review cycle 2: sales that did not move over a change that did
    # divide to -0.0, which JSON writes as "-0.0".
    empty = pd.Series(dtype=float)
    totals = MemberTotals(rev_prev=pd.Series({"a": 1.0}), rev_cur=pd.Series({"a": 1.0}),
                          orders_prev=empty, orders_cur=empty, labels={"a": "A"}, gap_keys=frozenset())

    share = compute_breadth(totals, -5.0, products_change=0.0).products_share_of_change

    assert (share, math.copysign(1.0, share)) == (0.0, 1.0)


def test_exactly_half_by_floating_point_residue_is_not_more_than_half() -> None:
    # A moves 1.0 -> 1.3 (0.30000000000000004 in binary) of a 0.60 change:
    # the ratio is 0.5000000000000001.
    empty = pd.Series(dtype=float)
    totals = MemberTotals(rev_prev=pd.Series({"a": 1.0, "b": 1.0}), rev_cur=pd.Series({"a": 1.3, "b": 1.0}),
                          orders_prev=empty, orders_cur=empty, labels={"a": "A", "b": "B"},
                          gap_keys=frozenset())

    assert compute_breadth(totals, 0.6).classification == "outside_products"


# --- F2: the lines with no product identity -----------------------------------

def _pooled_shop(bucket: str, july_price: str, august_price: str, from_march: bool) -> pd.DataFrame:
    """Six products at 10, one unit each a day; one more line a day holding
    unrelated items - M "Manual" (pooled) or a line with neither SKU nor
    name - at `july_price` until July and `august_price` in August."""
    sku, name = ("M", "Manual") if bucket == "pooled" else (None, None)
    rows, i = [], 0
    for day in _days():
        for k in range(6):
            rows.append((day.isoformat(), f"C{i % 12}", f"P{k}", f"PRODUCT {k}", "1", "10"))
            i += 1
        if from_march or day.month == 8:
            price = august_price if day.month == 8 else july_price
            rows.append((day.isoformat(), f"C{i % 12}", sku, name, "1", price))
            i += 1
    rows.append(("2026-09-01", "C1", "P1", "PRODUCT 1", "1", "10"))
    return pd.DataFrame(rows, columns=COLUMNS)


@pytest.mark.parametrize("bucket", ["pooled", "blank"])
def test_unidentified_lines_are_no_like_for_like_price(bucket: str) -> None:
    # The bucket: 31 x 20 in July, 31 x 40 in August (+620); every product's
    # price is unchanged, so no like-for-like price moved.
    inputs, results, _ = _run(_pooled_shop(bucket, "20", "40", from_march=True), {"M": "pooled"})

    products = inputs.tree.products
    assert (products.price, products.mix, products.volume) == (0.0, 0.0, 0.0)
    assert products.unidentified == pytest.approx(620.0)
    assert (results["P1"].contribution, results["P1"].verdict) == (0.0, "ruled_out")
    assert results["P1"].evidence["products_in_both_periods"] == 6


@pytest.mark.parametrize("bucket", ["pooled", "blank"])
def test_unidentified_lines_appearing_are_no_product_launched(bucket: str) -> None:
    # The bucket first appears in August: 31 x 20 = +620 of a +620 month.
    inputs, results, headline = _run(_pooled_shop(bucket, "0", "20", from_march=False), {"M": "pooled"})

    products = inputs.tree.products
    assert (products.new_products, products.discontinued_products) == (0.0, 0.0)
    assert products.unidentified == pytest.approx(620.0)
    assert (results["R2"].contribution, results["R2"].verdict) == (0.0, "ruled_out")
    assert headline.hypothesis_id != "R2"


def test_the_product_decomposition_counts_the_unidentified_term() -> None:
    # Under the masked-shift alert a product-lens share is taken of the lens's
    # gross: every term's size, the unidentified lines' too.
    # |1| + |-2| + |3| + |4| + |-5| + |-6| = 21.
    products = SimpleNamespace(volume=1.0, mix=-2.0, price=3.0, new_products=4.0,
                               discontinued_products=-5.0, unidentified=-6.0)

    assert decomposition_gross(SimpleNamespace(products=products), "product") == pytest.approx(21.0)


def test_nothing_holds_more_than_half_of_no_change() -> None:
    assert products_hold_most(-1.0, 0.0, 10.0) is False
    assert products_hold_most(-6.0, -10.0, 10.0) is True
    assert products_hold_most(6.0, -10.0, 10.0) is False
