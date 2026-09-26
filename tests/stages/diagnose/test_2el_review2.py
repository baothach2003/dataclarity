"""Session 2E-l, doubt-review cycle 2 finding 1, written before the fix.

The product dimension's two buckets - "(no product name)" (the gap, and
since 2E-l the pooled items) and "(not a product)" (charges, discounts) -
were keyed "\\x00UNNAMED_PRODUCT" and "\\x00NOT_A_PRODUCT". pandas reads an
object key only up to a NUL, so `groupby` made them ONE member under
whichever label came first: on Online Retail II 2011-09 -> 2011-10 with
Thach's classes, "(no product name)" showed -20,745.75 for a pooled change
of -405.48 (shared/orders.py records the same pitfall for `nunique`).

The shop: six products at 10, M "Manual" 1 @ 20 (pooled) and postage
1 @ 5 (a charge), one of each a day from March to August - nothing changes:
July and August both hold 31 days, so each bucket is 620 -> 620 and
155 -> 155.
"""

import pandas as pd
import pytest

from tests.stages.diagnose.test_2el_review1 import COLUMNS, _days, _run


def _shop() -> pd.DataFrame:
    rows, i = [], 0
    for day in _days():
        for k in range(6):
            rows.append((day.isoformat(), f"C{i % 12}", f"P{k}", f"PRODUCT {k}", "1", "10"))
            i += 1
        rows.append((day.isoformat(), f"C{i % 12}", "M", "Manual", "1", "20"))
        rows.append((day.isoformat(), f"C{(i + 1) % 12}", "POST", "POSTAGE", "1", "5"))
        i += 2
    rows.append(("2026-09-01", "C1", "P1", "PRODUCT 1", "1", "10"))
    return pd.DataFrame(rows, columns=COLUMNS)


def test_the_gap_and_the_lines_not_products_stay_two_members() -> None:
    inputs, _, _ = _run(_shop(), {"M": "pooled", "POST": "charge"})

    members = next(d for d in inputs.localization.dimensions if d.name == "product").members
    gap = [(m.rev_prev, m.rev_cur) for m in members if m.is_data_gap]
    not_products = [(m.rev_prev, m.rev_cur) for m in members if m.is_not_a_product]
    assert gap == [(pytest.approx(620.0), pytest.approx(620.0))]
    assert not_products == [(pytest.approx(155.0), pytest.approx(155.0))]
