"""Session 2E-f, stage 3 (Thach, after 2E-e), written before the change: the
bridge classifies "new" by the same per-product opening-day netting as stage
2, and every stage 3 reader of the customer column - the bridge, the lever,
the monthly series, the customer-type members - reads the one per-row
customer, filled from the receipt on header-style exports. diagnosis.json
5.0: the bridge's terms and the customer counts changed meaning.
"""

from datetime import date

import pandas as pd
import pytest

from contracts.diagnosis import DiagnosisContract
from stages.diagnose.bridge import compute_bridge, customer_classes
from stages.diagnose.lever import period_totals
from stages.diagnose.members import customer_type_totals
from stages.diagnose.signals import monthly_series
from tests.stages.diagnose.diagnose_fixtures import MAPPING, daily_rows, row, run_data

WITH_ORDERS = {**MAPPING, "Inv": "order_id"}


def test_a_chair_bought_and_part_returned_on_the_first_day_is_new_in_both_stages() -> None:
    """The 2E-c2 file, but X's chair was bought that day: 2 chairs at 500 and
    1 returned on 7 August, X's first day. Stage 2: August's new customers
    are N11 (40) and X (1,000 - 500 = 500), so 2 and 540. The bridge calls X
    new too. Under "any return line on the first day" X was resurrected and
    stage 2 counted 1 and 40."""
    rows = daily_rows(date(2025, 9, 1), date(2026, 8, 31), customer="Regular")
    for index in range(12):
        year, month = (2025, 9 + index) if index < 4 else (2026, index - 3)
        rows.append(row(date(year, month, 15), qty=1.0, price=40.0, customer=f"N{index}"))
    rows.append(row(date(2026, 8, 7), qty=2.0, price=500.0, product="Chair", customer="X"))
    rows.append(row(date(2026, 8, 7), qty=-1.0, price=500.0, product="Chair", customer="X"))
    rows.append(row(date(2026, 9, 1), customer="Regular"))

    data = run_data(rows)
    split = data.metrics.customers.new_vs_returning

    assert (split.new_customers, split.new_revenue) == (2, pytest.approx(540.0))
    assert customer_classes(data)["x"] == "new"


def _receipts(header_style: bool) -> list[dict]:
    """Twelve months of receipts, three lines at 10 each: A and B every month,
    C from March 2026 (two lines in August), D only in July 2026 (so August
    has a lapsed and a retained customer), and E new in August: a free
    sample (1 @ 0) first, then five lines at 10. A buys every day of the
    file so each month is covered. Header-style: only a receipt's first line
    names its customer - for E, the free sample, so read raw E bought
    nothing and the unnamed lines moved `unattributed` by +20."""
    rows = []
    for index, line in enumerate(daily_rows(date(2025, 9, 1), date(2026, 8, 31), customer="A")):
        rows.append({**line, "Inv": f"day{index}"})
    receipts = []
    months = [(2025, m) for m in range(9, 13)] + [(2026, m) for m in range(1, 9)]
    for year, month in months:
        receipts.append((f"B{year}{month}", date(year, month, 14), "B", 3))
        if (year, month) >= (2026, 3):
            receipts.append((f"C{year}{month}", date(year, month, 20), "C", 3 if month != 8 else 2))
    receipts.append(("DJ", date(2026, 7, 22), "D", 3))
    receipts.append(("E1", date(2026, 8, 25), "E", 6))
    for receipt, day, customer, lines in receipts:
        for line in range(lines):
            name = customer if line == 0 or not header_style else ""
            price = 0.0 if receipt == "E1" and line == 0 else 10.0
            rows.append({**row(day, price=price, product=f"P{line}", customer=name), "Inv": receipt})
    rows.append({**row(date(2026, 9, 1), customer="A"), "Inv": "S"})
    return rows


def _terms(data):
    lens = compute_bridge(data)
    return {name: getattr(lens, name) for name in
            ("new", "resurrected", "expansion", "contraction", "lapsed", "unattributed")}


def test_the_bridge_reads_a_header_style_export_as_the_fully_named_file() -> None:
    """By hand, July -> August: E new +50; D lapsed -30; C contracted 30 ->
    20 = -10; nothing unattributed. Read raw, the header-style copy put every
    unnamed line in `unattributed` (+20) and E's new revenue at 0."""
    named = run_data(_receipts(header_style=False), WITH_ORDERS)
    header = run_data(_receipts(header_style=True), WITH_ORDERS)

    terms = _terms(header)

    assert terms == _terms(named)
    assert (terms["new"], terms["lapsed"], terms["contraction"], terms["unattributed"]) == (
        pytest.approx(50.0), pytest.approx(-30.0), pytest.approx(-10.0), pytest.approx(0.0))


def test_the_lever_and_the_monthly_series_count_the_same_customers() -> None:
    """E is named only on a free sample: read raw, E was no buyer in August
    (3 buyers, not 4) and customers x frequency x AOV moved with it."""
    named = run_data(_receipts(header_style=False), WITH_ORDERS)
    header = run_data(_receipts(header_style=True), WITH_ORDERS)

    assert period_totals(header, "2026-08") == period_totals(named, "2026-08")
    pd.testing.assert_frame_equal(monthly_series(header), monthly_series(named))


def test_customer_type_members_carry_every_line_of_a_receipt() -> None:
    """August by class, by hand: new E 50, retained A (31 days x 10 = 310) +
    B 30 + C 20 = 360, lapsed D 0; no line without a customer."""
    header = run_data(_receipts(header_style=True), WITH_ORDERS)

    totals = customer_type_totals(header, customer_classes(header))

    assert totals.rev_cur.get("new") == pytest.approx(50.0)
    assert totals.rev_cur.get("retained") == pytest.approx(360.0)
    assert totals.rev_cur.drop(["new", "retained"], errors="ignore").sum() == pytest.approx(0.0)


def test_diagnosis_json_is_version_5_or_the_current_one() -> None:
    # 5.0 in 2E-f; 6.0 since 2E-g (test_2eg_stage3.py).
    assert DiagnosisContract.supported_major == 6
