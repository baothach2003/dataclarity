"""Session 2E-g, stage 3's product lens (Thach), written before the change:
the same keys and labels as stage 2 (shared/products.py). A line with a SKU
and no name is its product, not the gap; the gap - neither SKU nor name - is
never a stockout (R3) or a price-check product (D2). R3 reads the sales
pattern, not stock, so the stock-in question of stage 2's velocity does not
touch it. diagnosis.json 6.0.
"""

from datetime import date, timedelta

from contracts.diagnosis import DiagnosisContract
from stages.diagnose.members import UNNAMED_PRODUCT_KEY, product_totals
from stages.diagnose.stockout import detect_stockouts
from stages.diagnose.trust_checks import _price_ratios
from tests.stages.diagnose.diagnose_fixtures import MAPPING, row, run_data

WITH_SKU = {**MAPPING, "Sku": "sku"}


def _days(start: date, end: date):
    day = start
    while day <= end:
        yield day
        day += timedelta(days=1)


def test_a_line_with_a_sku_and_no_name_is_its_product_not_the_gap() -> None:
    """Online Retail II has 4,275 such lines. M1 sells as "Mug" and once with
    no name: all of it is Mug's, nothing is in the gap."""
    rows = [{**row(day, product="Mug"), "Sku": "M1"} for day in _days(date(2026, 7, 1), date(2026, 8, 31))]
    rows.append({**row(date(2026, 8, 3), product=""), "Sku": "M1"})
    data = run_data(rows, WITH_SKU)

    totals = product_totals(data)

    assert UNNAMED_PRODUCT_KEY not in totals.rev_cur.index
    assert totals.labels["sku:m1"] == "Mug"


def test_stage_2_and_stage_3_name_a_product_alike() -> None:
    """Renamed product: "Old" in July, "New" twice in August - both stages
    say "New"."""
    rows = [{**row(day, product="Widget"), "Sku": "W"} for day in _days(date(2026, 7, 1), date(2026, 8, 31))]
    rows += [{**row(date(2026, 7, 5), product="Old"), "Sku": "S1"},
             {**row(date(2026, 8, 5), product="New"), "Sku": "S1"},
             {**row(date(2026, 8, 6), product="New"), "Sku": "S1"}]
    data = run_data(rows, WITH_SKU)

    stage_2 = {p.product for p in data.metrics.products.top_products}

    assert product_totals(data).labels["sku:s1"] == "New"
    assert "New" in stage_2


def test_the_gap_is_never_a_stockout() -> None:
    """Unnamed lines sell 100 every day of October 2011 and stop on 21
    November while B keeps trading - a stockout pattern, but not a product."""
    rows = []
    for day in _days(date(2011, 10, 1), date(2011, 11, 30)):
        rows.append(row(day, qty=1, price=10.0, product="B"))
        if day.month == 10 or day.day <= 20:
            rows.append(row(day, qty=1, price=100.0, product="  "))

    assert detect_stockouts(run_data(rows)) == []


def test_r3s_top_product_bar_counts_the_gaps_money() -> None:
    """2E-g doubt-review F4: the gap's key is NaN, so its July revenue left
    R3's total and a 1% product passed the 2% "top product" bar. Widget and
    Mug sell 10 a day in July beside one unnamed line of 30,000; Mug is 310
    of 30,620 (1.0%) - not a top product, so not a stockout."""
    rows = []
    for day in _days(date(2026, 7, 1), date(2026, 8, 31)):
        rows.append(row(day, product="Widget"))
        if day.month == 7 or day.day == 1:
            rows.append(row(day, product="Mug"))
    rows.append(row(date(2026, 7, 15), price=30000.0, product="  "))

    assert detect_stockouts(run_data(rows)) == []


def test_breadth_and_r1_never_name_the_gap_as_the_top_product() -> None:
    """Thach, after 2E-g review cycle 3: six products sell 10 a day, March to
    August; unnamed lines sell 200 a day in July and 20 in August. The change
    moved in the data gap, not in a product: R1's evidence named "(no product
    name)" its top product with a share of 1.0. Breadth is measured over
    products, so no product is the top mover of a change none of them made."""
    from stages.diagnose.hypotheses import evaluate_hypotheses
    from tests.stages.diagnose.test_hypotheses import by_id, step7

    rows = []
    for day in _days(date(2026, 3, 1), date(2026, 8, 31)):
        rows += [row(day, product=f"P{k}") for k in range(6)]
        if day.month == 7:
            rows.append(row(day, price=200.0, product=" "))
        elif day.month == 8:
            rows.append(row(day, price=20.0, product=" "))
    inputs = step7(run_data(rows))

    r1 = by_id(evaluate_hypotheses(inputs))["R1"]

    assert r1.evidence["top_member"] != "(no product name)"
    assert inputs.localization.breadth.top_member_share < 1.0


def test_the_gap_is_never_a_price_check_product() -> None:
    """Unnamed lines at 10 in July and 1,000 in August: D2 compares products,
    and the gap is not one."""
    rows = []
    for day in _days(date(2026, 7, 1), date(2026, 8, 31)):
        rows.append(row(day, product="B"))
        rows.append(row(day, price=10.0 if day.month == 7 else 1000.0, product=" "))

    ratios = _price_ratios(run_data(rows))

    assert list(ratios.index) == ["name:b"]


def test_diagnosis_json_is_version_6_or_the_current_one() -> None:
    # 6.0 in 2E-g; 7.0 in 2E-h; 8.0 since 2E-e2 (test_2ee2_stage2.py).
    assert DiagnosisContract.supported_major == 9  # 8.0 in 2E-e2; 9.0 since 2E-k
