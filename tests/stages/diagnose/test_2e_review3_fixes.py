"""The 2E doubt-review cycle 3 findings, each written from the reviewer's
reproduction before the fix (Thach's decisions, 2E).

C1  B2 is refused on any return LINE, not only on refunded money: zero-price
    write-off lines carry units but no money, and B2 headlined "baskets got
    bigger" while baskets shrank from 3 units to 1.
M1  localization's member shares and breadth judge residue against the
    money moved, as stage 2's contribution_pct does.
L1  stage 3's scale is the per-row money moved, the same sum stage 2 uses.
M2  the tree's reconciliation tolerates float error on the money moved,
    not a billionth of it: a real bug of 100 on a file with a reversed
    13-digit price typo passed.
L2  pct_change's reason says what the test is: residue next to the money.
"""

from datetime import date, timedelta

import pytest

from shared.transactions import pct_change
from stages.diagnose.frame import history_window
from stages.diagnose.headline import choose_headline
from stages.diagnose.hypotheses import evaluate_hypotheses
from stages.diagnose.step7_inputs import changes
from stages.diagnose.tree import ReconciliationError, _check_reconciliation, compute_tree
from tests.stages.diagnose.diagnose_fixtures import MAPPING, row, run_data
from tests.stages.diagnose.test_hypotheses import by_id, step7


def _month(year: int, month: int):
    day = date(year, month, 1)
    while day.month == month:
        yield day
        day += timedelta(days=1)


def _history(rows: list[dict], price: float = 100.0, **extra) -> None:
    for year, month in [(2025, m) for m in range(9, 13)] + [(2026, m) for m in range(1, 7)]:
        rows += [dict(row(day, qty=1.0, price=price, customer=f"C{day.day % 10}"), **extra)
                 for day in _month(year, month)]


def _diagnose(rows, mapping=MAPPING):
    data = run_data(rows, mapping)
    inputs = step7(data)
    results = evaluate_hypotheses(inputs)
    headline = choose_headline(inputs.trust, results, inputs.tree, changes(inputs))
    return data, inputs, by_id(results), headline


def test_b2_is_refused_on_zero_price_return_lines() -> None:
    """r1b: July orders are 3 units at 120, plus four zero-price lines of -20
    units; August orders are 1 unit at 120. Baskets shrank 3 -> 1, and B2
    headlined "baskets got bigger (+27,641.54)"."""
    rows: list[dict] = []
    _history(rows)
    rows += [row(day, qty=3.0, price=120.0, customer=f"C{day.day % 5}") for day in _month(2026, 7)]
    rows += [row(date(2026, 7, d), qty=-20.0, price=0.0, customer="") for d in (4, 11, 18, 25)]
    for day in _month(2026, 8):
        rows += [row(day, qty=1.0, price=120.0, customer=f"C{(day.day + k) % 30}") for k in range(5)]
    rows.append(row(date(2026, 9, 1), qty=1.0, price=100.0, customer="C1"))

    _, _, verdicts, headline = _diagnose(rows)

    assert verdicts["B2"].verdict == "inconclusive"
    assert "bigger" not in headline.message


def test_member_shares_of_a_change_that_is_nothing_are_zero() -> None:
    """r3b: about 1.55e9 a month; category A +2,000,000, B -1,999,999: net +1.
    Stage 2 says no member has a share of it; stage 3's localization read
    A at 2,000,000x the change and breadth "concentrated"."""
    mapping = {**MAPPING, "Cat": "category"}

    def pair(day, a, b):
        return [dict(row(day, qty=1.0, price=a, customer=f"C{day.day % 10}", product="PA"), Cat="A"),
                dict(row(day, qty=1.0, price=b, customer=f"C{(day.day + 5) % 10}", product="PB"), Cat="B")]

    rows: list[dict] = []
    for year, month in [(2025, m) for m in range(9, 13)] + [(2026, m) for m in range(1, 8)]:
        for day in _month(year, month):
            rows += pair(day, 25_000_000.0, 25_000_000.0)
    for day in _month(2026, 8):
        extra = (2_000_000.0, -1_999_999.0) if day.day == 10 else (0.0, 0.0)
        rows += pair(day, 25_000_000.0 + extra[0], 25_000_000.0 + extra[1])
    rows.append(dict(row(date(2026, 9, 1), qty=1.0, price=100.0, customer="C1", product="PA"),
                     Cat="A"))

    data, inputs, _, _ = _diagnose(rows, mapping)
    shares = [m.share_of_change for d in inputs.localization.dimensions for m in d.members]

    assert all(c.contribution_pct is None for c in data.metrics.by_dimension.category)
    assert all(abs(share) <= 1.0 for share in shares)
    assert inputs.localization.breadth.classification != "concentrated"


def test_stage_3s_scale_is_the_money_moved_row_by_row() -> None:
    """r2: a +1,000,000 / -1,000,000 negative-price pair each month; stage 3's
    gross netted it away, stage 2 counted it. Stage 2 called the change
    nothing; stage 3 headlined "like-for-like prices changed" on +0.00."""
    mapping = {**MAPPING, "Cat": "category"}
    rows: list[dict] = []
    _history(rows, Cat="A")
    for (y, m), price in (((2026, 7), 0.1), ((2026, 8), 0.1001)):
        for day in _month(y, m):
            rows += [dict(row(day, qty=q, price=10.0, customer=f"C{day.day % 10}"), Cat="A")
                     for q in (1.0, -1.0)]
        rows.append(dict(row(date(y, m, 10), qty=1.0, price=price, customer="C3"), Cat="A"))
        rows += [dict(row(date(y, m, 11), qty=1.0, price=p, customer="C4", product="Big"), Cat="A")
                 for p in (1_000_000.0, -1_000_000.0)]
    rows.append(dict(row(date(2026, 9, 1), qty=1.0, price=100.0, customer="C1"), Cat="A"))

    data, inputs, _, headline = _diagnose(rows, mapping)

    assert data.metrics.by_dimension.contribution_reason is not None
    assert changes(inputs).scale > 4_000_000  # the pair counted, as in stage 2
    assert headline.rule == 7


def test_the_tree_still_catches_a_real_bug_beside_a_huge_reversed_typo() -> None:
    """r4: a 999,999,999,999 sale reversed the same day. Scaling the
    tolerance by a billionth of the money moved let a bridge error of 1,500
    on a 310 change pass."""
    rows: list[dict] = []
    _history(rows)
    rows += [row(day, qty=1.0, price=100.0, customer=f"C{day.day % 10}") for day in _month(2026, 7)]
    rows += [row(day, qty=1.0, price=110.0, customer=f"C{day.day % 10}") for day in _month(2026, 8)]
    rows += [row(date(2026, 8, 20), qty=q, price=999_999_999_999.0, customer="C2") for q in (1.0, -1.0)]
    rows.append(row(date(2026, 9, 1), qty=1.0, price=100.0, customer="C1"))
    data = run_data(rows)
    tree = compute_tree(data, history_window(data))
    broken = tree.model_copy(deep=True)
    broken.customers.new += 100.0

    with pytest.raises(ReconciliationError):
        _check_reconciliation(data, broken)


def test_the_pct_reason_says_residue_next_to_the_money_and_nothing_more() -> None:
    """A real 0.01 base next to 3,100 is a base: +30,999,900% is true (a
    usable-base floor is a scheduled stage 2 item, not this session). Only
    a base under a billionth of the money moved is refused, and the reason
    says exactly that."""
    real = pct_change(3100.0, 0.01, 6200.0)
    residue = pct_change(1000.0, 1.39e-17, 1000.0)

    assert real.value == pytest.approx(30_999_900.0)
    assert residue.value is None
    assert "residue next to the money compared" in residue.reason
    assert "too small" not in residue.reason


def test_the_other_slice_of_a_change_that_is_nothing_has_no_share() -> None:
    """Twelve products at 25,000,000 a day. In August P0 gains 2,000,000 on
    the 10th and P1-P5 each lose 400,000: -2,000,000, net 0 - plus P6 gains
    1: the whole month moved by 1 on 9.3e9 of trade. Five products are named
    (MEMBERS_PER_DIMENSION); the sixth loser falls into "Other" with a delta
    of about -400,000, which divided by 1 read -40,000,000% (mutation check,
    2E cycle 3)."""
    def day_rows(day, extra):
        return [row(day, qty=1.0, price=25_000_000.0 + extra.get(p, 0.0),
                    customer=f"C{p}", product=f"P{p}") for p in range(12)]

    rows: list[dict] = []
    for year, month in [(2025, m) for m in range(9, 13)] + [(2026, m) for m in range(1, 8)]:
        for day in _month(year, month):
            rows += day_rows(day, {})
    moves = {0: 2_000_000.0, 1: -400_000.0, 2: -400_000.0, 3: -400_000.0,
             4: -400_000.0, 5: -400_000.0, 6: 1.0}
    for day in _month(2026, 8):
        rows += day_rows(day, moves if day.day == 10 else {})
    rows.append(row(date(2026, 9, 1), qty=1.0, price=100.0, customer="C1", product="P0"))

    _, inputs, _, _ = _diagnose(rows)
    product = next(d for d in inputs.localization.dimensions if d.name == "product")

    assert product.other is not None and abs(product.other.delta) > 100_000
    assert abs(product.other.share_of_change) <= 1.0
