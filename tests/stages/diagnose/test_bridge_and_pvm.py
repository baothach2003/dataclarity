"""Step 5: the customer bridge and the product price-volume-mix lens.

Both are exact by construction, so every test that checks a number also checks
that the parts still add up to the total they decompose - a lens can be wrong
in a way that leaves individual figures plausible.
"""

from datetime import date

import pytest

from stages.diagnose.bridge import compute_bridge, customer_classes
from stages.diagnose.lever import month_revenue, period_totals
from stages.diagnose.pvm import compute_products
from stages.diagnose.frame import history_window
from stages.diagnose.tree import ReconciliationError, _assert_sums, compute_tree
from tests.stages.diagnose.diagnose_fixtures import MAPPING, daily_rows, row, run_data
from tests.stages.diagnose.test_shapley_and_lever import reconciles

# --- customer bridge ----------------------------------------------------------


def _bridge_rows() -> list[dict]:
    """October (prev) 250, November (cur) 280, so the bridge must total +30.

    Alice   100 -> 150   retained, expanded        +50
    Bob      80 ->  30   retained, contracted      -50
    Cara     60 ->   -   lapsed                    -60
    Dan       - ->  40   first ever purchase, new  +40
    Eve  (Aug 90) ->  25 away in October, back     +25   resurrected
    (blank)  10 ->  35   no customer on the row    +25   unattributed

    September carries real rows (Alice 70, Sam 30) so that the September ->
    October transition is a comparison of two months that happened, rather
    than a decomposition of an empty month in which everyone looks new.
    """
    return [
        row(date(2011, 8, 15), qty=1, price=90.0, customer="Eve"),
        row(date(2011, 9, 10), qty=1, price=70.0, customer="Alice"),
        row(date(2011, 9, 20), qty=1, price=30.0, customer="Sam"),
        row(date(2011, 10, 5), qty=1, price=100.0, customer="Alice"),
        row(date(2011, 10, 10), qty=1, price=80.0, customer="Bob"),
        row(date(2011, 10, 20), qty=1, price=60.0, customer="Cara"),
        row(date(2011, 10, 25), qty=1, price=10.0, customer=""),
        row(date(2011, 11, 5), qty=1, price=150.0, customer="Alice"),
        row(date(2011, 11, 10), qty=1, price=30.0, customer="Bob"),
        row(date(2011, 11, 15), qty=1, price=40.0, customer="Dan"),
        row(date(2011, 11, 20), qty=1, price=25.0, customer="Eve"),
        row(date(2011, 11, 30), qty=1, price=35.0, customer=""),
    ]


def test_the_bridge_classifies_every_customer_and_totals_the_change() -> None:
    data = run_data(_bridge_rows())

    bridge = compute_bridge(data)

    assert bridge is not None
    assert bridge.new == pytest.approx(40.0)
    assert bridge.resurrected == pytest.approx(25.0)
    assert bridge.expansion == pytest.approx(50.0)
    assert bridge.contraction == pytest.approx(-50.0)
    assert bridge.lapsed == pytest.approx(-60.0)
    assert bridge.unattributed == pytest.approx(25.0)


def test_the_bridge_reconciles_to_the_revenue_change() -> None:
    data = run_data(_bridge_rows())

    bridge = compute_bridge(data)

    assert bridge is not None
    delta = month_revenue(data, "2011-11") - month_revenue(data, "2011-10")
    assert delta == pytest.approx(30.0)
    assert reconciles(
        [bridge.new, bridge.resurrected, bridge.expansion,
         bridge.contraction, bridge.lapsed, bridge.unattributed],
        delta,
    )


def test_a_customer_who_skipped_a_month_is_resurrected_not_new() -> None:
    """The distinction C1 rests on: "new" is first activity anywhere in the
    file, not merely absence from last month."""
    data = run_data(_bridge_rows())

    bridge = compute_bridge(data)

    assert bridge is not None
    assert bridge.evidence["new_customers"] == 1  # Dan only; Eve bought in August
    assert bridge.resurrected == pytest.approx(25.0)


def test_the_previous_transition_is_computed_and_also_reconciles() -> None:
    data = run_data(_bridge_rows())

    bridge = compute_bridge(data)

    assert bridge is not None
    earlier = bridge.previous_transition
    assert earlier is not None
    # September 100 -> October 250. Hand-checked: Bob and Cara are first seen
    # in October (+140), Alice grows 70 -> 100 (+30), Sam lapses (-30), and the
    # blank-customer row adds 10.
    delta = month_revenue(data, "2011-10") - month_revenue(data, "2011-09")
    assert delta == pytest.approx(150.0)
    assert earlier.new == pytest.approx(140.0)
    assert earlier.expansion == pytest.approx(30.0)
    assert earlier.lapsed == pytest.approx(-30.0)
    assert earlier.unattributed == pytest.approx(10.0)
    assert reconciles(
        [earlier.new, earlier.resurrected, earlier.expansion,
         earlier.contraction, earlier.lapsed, earlier.unattributed],
        delta,
    )


def test_an_empty_month_is_not_offered_as_a_previous_transition() -> None:
    """3C doubt-review R3: a calendar-complete month with no rows produced an
    all-zero bridge, presented to C1-C3 as a real comparison of flows. The
    lever lens refuses such a period outright; the bridge must not quietly
    decompose it either (3B doubt-review finding 2, in a new place)."""
    rows = [
        row(date(2011, 8, 1), qty=1, price=50.0, customer="Alice"),
        row(date(2011, 10, 5), qty=1, price=100.0, customer="Alice"),
        row(date(2011, 11, 30), qty=1, price=120.0, customer="Alice"),
    ]
    data = run_data(rows)  # September is complete by the calendar and empty

    bridge = compute_bridge(data)

    assert bridge is not None
    assert "2011-09" in data.complete_months
    assert "2011-09" not in data.months_with_rows
    assert bridge.previous_transition is None
    assert "2011-09" in bridge.evidence["previous_transition_reason"]


def test_a_transition_with_an_empty_side_says_so_in_its_evidence() -> None:
    rows = [
        row(date(2011, 9, 1), qty=1, price=100.0, customer="Alice"),
        row(date(2011, 11, 5), qty=1, price=100.0, customer="Alice"),
        row(date(2011, 11, 30), qty=1, price=60.0, customer="Bob"),
    ]
    data = run_data(rows)  # October, the `previous` period, holds nothing

    bridge = compute_bridge(data)

    assert bridge is not None
    assert bridge.evidence["empty_period"] == ["previous"]


def test_a_returns_only_arrival_keeps_the_identity_and_is_flagged() -> None:
    """Thach's call, 3C: the term carries the sign the arithmetic gives, with
    no clamping - returning goods never bought inside the file usually means
    the purchase predates it. 3C left Rita in `new` with a note; SUPERSEDED
    (Thach, 2E-c, rule C): she has no first purchase in the file, so she is
    resurrected, and the note counts her there."""
    rows = [
        *_bridge_rows(),
        row(date(2011, 11, 28), qty=-1, price=30.0, customer="Rita"),
    ]
    data = run_data(rows)

    bridge = compute_bridge(data)

    assert bridge is not None
    # Was 10 (Dan's +40 and Rita's -30); now Dan's +40 alone.
    assert bridge.new == pytest.approx(40.0)
    assert bridge.evidence["arrivals_with_no_first_purchase_in_the_file"] == 1
    delta = month_revenue(data, "2011-11") - month_revenue(data, "2011-10")
    assert reconciles(
        [bridge.new, bridge.resurrected, bridge.expansion,
         bridge.contraction, bridge.lapsed, bridge.unattributed],
        delta,
    )


def test_the_returns_first_count_asks_about_the_first_row_not_the_month() -> None:
    """3C doubt-review R2: the count is of customers whose FIRST-EVER activity
    is a return, which is not the same set as customers whose month nets
    negative. The first version tested the month and was wrong in both
    directions; a fixture where the two definitions coincide cannot tell.

    Nora buys on the 5th and refunds more on the 20th: negative month, but she
    did not start with a return.
    Rita refunds on the 6th and buys on the 21st: positive month, and she did.
    Tom simply buys, so that the RIGHT answer and the INVERTED answer are
    different numbers - with only Nora and Rita, both a correct implementation
    and one with the sign flipped report "1", and the test cannot tell them
    apart. That was the original defect's hiding place; counting is not
    identifying.
    """
    rows = [
        row(date(2011, 10, 5), qty=1, price=100.0, customer="Alice"),
        row(date(2011, 11, 5), qty=1, price=100.0, customer="Nora"),
        row(date(2011, 11, 20), qty=-2, price=100.0, customer="Nora"),
        row(date(2011, 11, 6), qty=-1, price=30.0, customer="Rita"),
        row(date(2011, 11, 21), qty=1, price=100.0, customer="Rita"),
        row(date(2011, 11, 22), qty=1, price=40.0, customer="Tom"),
        row(date(2011, 11, 30), qty=1, price=10.0, customer="Alice"),
    ]
    data = run_data(rows)

    bridge = compute_bridge(data)

    assert bridge is not None
    # Was 3 (Nora, Rita and Tom) with Rita noted. Since 2E-c (rule C) Rita's
    # history opens with a refund, so she is not new: Nora and Tom. Inverted
    # (the sign of the month), Nora would be out and Rita in - the classes
    # tell the two apart, as the count did.
    assert bridge.evidence["new_customers"] == 2
    classes = customer_classes(data)
    assert (classes["nora"], classes["tom"], classes["rita"]) == ("new", "new", "resurrected")
    assert bridge.evidence["arrivals_with_no_first_purchase_in_the_file"] == 1


def test_the_bridge_flags_left_censoring_near_the_start_of_the_file() -> None:
    rows = [
        row(date(2011, 10, 5), qty=1, price=100.0, customer="Alice"),
        row(date(2011, 11, 30), qty=1, price=120.0, customer="Bob"),
    ]
    data = run_data(rows)

    bridge = compute_bridge(data)

    assert bridge is not None
    # The file starts in October and `cur` is November: everyone looks new.
    assert bridge.evidence["left_censored"] is True
    assert bridge.evidence["months_since_file_start"] == 1


def test_there_is_no_bridge_without_a_mapped_customer_column() -> None:
    mapping = {key: value for key, value in MAPPING.items() if value != "customer"}
    data = run_data(_bridge_rows(), mapping)

    assert compute_bridge(data) is None


# --- product lens (price / volume / mix) --------------------------------------


def _pvm_rows() -> list[dict]:
    """October gross 300, November gross 290, so the lens must total -10.

    A   10 units @ 10 = 100  ->  12 units @ 10 = 120   like-for-like
    B    5 units @ 20 = 100  ->   4 units @ 20 =  80   like-for-like
    Gone 2 units @ 50 = 100  ->   -                    discontinued
    New   -                  ->   3 units @ 30 =  90   new
    """
    return [
        row(date(2011, 10, 5), qty=10, price=10.0, product="A"),
        row(date(2011, 10, 10), qty=5, price=20.0, product="B"),
        row(date(2011, 10, 20), qty=2, price=50.0, product="Gone"),
        row(date(2011, 11, 5), qty=12, price=10.0, product="A"),
        row(date(2011, 11, 10), qty=4, price=20.0, product="B"),
        row(date(2011, 11, 30), qty=3, price=30.0, product="New"),
    ]


def test_pvm_separates_new_and_discontinued_products_from_like_for_like() -> None:
    data = run_data(_pvm_rows())

    products = compute_products(data)

    assert products.new_products == pytest.approx(90.0)
    assert products.discontinued_products == pytest.approx(-100.0)


def test_pvm_attributes_a_pure_mix_shift_with_prices_unchanged() -> None:
    """Hand-checked. Like-for-like gross is 200 in both months, so the three
    effects must cancel. Q 15 -> 16; shares A 2/3 -> 3/4, B 1/3 -> 1/4; prices
    unchanged, so the price effect is exactly zero and the volume and mix
    effects are the two-player Shapley values:
    v(none)=200, v(vol)=16*13.333=213.333, v(mix)=15*12.5=187.5, v(both)=200.
    phi_volume = [(213.333-200) + (200-187.5)] / 2 = +12.917
    phi_mix    = [(187.5-200) + (200-213.333)] / 2 = -12.917"""
    data = run_data(_pvm_rows())

    products = compute_products(data)

    assert products.price == pytest.approx(0.0, abs=1e-9)
    assert products.volume == pytest.approx(12.917, abs=0.001)
    assert products.mix == pytest.approx(-12.917, abs=0.001)


def test_pvm_reconciles_to_the_change_in_gross_sales() -> None:
    data = run_data(_pvm_rows())

    products = compute_products(data)

    assert reconciles(
        [products.volume, products.mix, products.price,
         products.new_products, products.discontinued_products],
        290.0 - 300.0,
    )


def test_pvm_finds_a_real_price_move_when_there_is_one() -> None:
    # Same units and same mix, one product's price up 50%: the whole change
    # must land on price, with nothing on volume or mix.
    rows = [
        row(date(2011, 10, 5), qty=10, price=10.0, product="A"),
        row(date(2011, 10, 10), qty=10, price=20.0, product="B"),
        row(date(2011, 11, 5), qty=10, price=15.0, product="A"),
        row(date(2011, 11, 30), qty=10, price=20.0, product="B"),
    ]
    data = run_data(rows)

    products = compute_products(data)

    assert products.price == pytest.approx(50.0)
    assert products.volume == pytest.approx(0.0, abs=1e-9)
    assert products.mix == pytest.approx(0.0, abs=1e-9)


def test_pvm_ignores_returns_because_they_belong_to_the_returns_lens() -> None:
    """The refund is at a DIFFERENT price from the sale, which is what makes
    this test able to fail: an earlier version refunded at the same price, so
    folding returns into the lens left product A's average price at 10.0 and
    the test stayed green under the exact bug it is named after (3C
    doubt-review R4).

    Gross A is 100 units-worth in both months, so every effect must be zero.
    Were the -5 @ 2 refund counted, A would show 5 units at an average 18.0 and
    the lens would report a large price effect that did not happen.
    """
    rows = [
        row(date(2011, 10, 5), qty=10, price=10.0, product="A"),
        row(date(2011, 11, 5), qty=10, price=10.0, product="A"),
        row(date(2011, 11, 20), qty=-5, price=2.0, product="A"),
        row(date(2011, 11, 30), qty=-1, price=50.0, product="A"),
    ]
    data = run_data(rows)

    products = compute_products(data)

    assert products.price == pytest.approx(0.0, abs=1e-9)
    assert products.volume == pytest.approx(0.0, abs=1e-9)
    assert products.mix == pytest.approx(0.0, abs=1e-9)
    assert products.new_products == 0.0
    assert products.discontinued_products == 0.0


def test_rows_with_no_product_name_stay_in_the_lens_as_one_bucket() -> None:
    """3C doubt-review C1: a missing product_name cell gave a NaN identity,
    `groupby` dropped it silently, and those rows left the lens while staying
    in the gross total it reconciles against. On the reproduction gross sales
    had fallen 49 and the lens reported a RISE of 1 - a direction flip in the
    numbers the headline is chosen from. Stage 1 can legitimately produce such
    a file: `flag_only` leaves missing values in place.
    """
    def unnamed(entry: dict) -> dict:
        return {**entry, "Product": None}

    rows = [
        row(date(2011, 10, 5), qty=10, price=10.0, product="A"),
        unnamed(row(date(2011, 10, 20), qty=2, price=50.0)),
        row(date(2011, 11, 5), qty=12, price=10.0, product="A"),
        unnamed(row(date(2011, 11, 30), qty=3, price=30.0)),
    ]
    data = run_data(rows)

    products = compute_products(data)

    # gross 200 -> 210, so the five terms must total +10 and not +(-80).
    assert reconciles(
        [products.volume, products.mix, products.price,
         products.new_products, products.discontinued_products],
        10.0,
    )


def test_an_infinite_price_is_not_a_measurement_and_never_reaches_the_lens() -> None:
    """3C doubt-review C2: `pd.to_numeric` parses "inf" into a real float that
    passed the `notna()` validity check, and since JSON cannot represent
    infinity pydantic serialised the result as `null` in a required float
    field. Excluded at the boundary now, like any other unusable cell."""
    rows = [
        row(date(2011, 10, 5), qty=10, price=10.0, product="A"),
        row(date(2011, 11, 5), qty=10, price=10.0, product="A"),
        row(date(2011, 11, 30), qty=1, price=1.0, product="B"),
    ]
    rows[2]["Price"] = "inf"
    data = run_data(rows)

    products = compute_products(data)

    assert products.new_products == 0.0
    assert "null" not in products.model_dump_json()


def test_pvm_is_all_zeroes_when_no_product_sold_in_both_months() -> None:
    rows = [
        row(date(2011, 10, 5), qty=10, price=10.0, product="Old"),
        row(date(2011, 11, 30), qty=5, price=10.0, product="Fresh"),
    ]
    data = run_data(rows)

    products = compute_products(data)

    assert (products.volume, products.mix, products.price) == (0.0, 0.0, 0.0)
    assert reconciles(
        [products.volume, products.mix, products.price,
         products.new_products, products.discontinued_products],
        50.0 - 100.0,
    )


# --- the assembled tree -------------------------------------------------------


def _tree_rows() -> list[dict]:
    """A file where the two totals are DIFFERENT, which is the whole point.

    October   A 10 @ 10 = 100 (Alice), B 5 @ 20 = 100 (Bob), A -2 @ 10 = -20 (Alice)
    November  A 12 @ 10 = 120 (Alice), B 4 @ 20 =  80 (Cara), B -3 @ 20 = -60 (Bob)

    gross   200 -> 200   delta_gross   =   0
    returns  20 ->  60   delta_returns = +40
    net     180 -> 140   delta_net     = -40

    An earlier version of this fixture had no returns at all, so delta_gross
    and delta_net were both +20 and every lens reconciled to the same number:
    an implementation that totalled the product lens to NET revenue passed the
    one test whose job is to keep them apart (3C doubt-review R5).
    """
    return [
        row(date(2011, 10, 5), qty=10, price=10.0, product="A", customer="Alice"),
        row(date(2011, 10, 10), qty=5, price=20.0, product="B", customer="Bob"),
        row(date(2011, 10, 20), qty=-2, price=10.0, product="A", customer="Alice"),
        row(date(2011, 11, 5), qty=12, price=10.0, product="A", customer="Alice"),
        row(date(2011, 11, 10), qty=4, price=20.0, product="B", customer="Cara"),
        row(date(2011, 11, 30), qty=-3, price=20.0, product="B", customer="Bob"),
    ]


def test_every_lens_reconciles_to_its_own_total_and_the_totals_differ() -> None:
    """The property, stated once over the whole tree: each lens totals what it
    decomposes, and the lenses do NOT total each other (CONTRACTS section 7).

    Both totals are written as hand-calculated literals rather than read back
    out of the tree, so the test cannot agree with a wrong implementation.
    """
    data = run_data(_tree_rows())

    tree = compute_tree(data, history_window(data))

    delta_net = -40.0
    delta_gross = 0.0
    assert month_revenue(data, "2011-11") - month_revenue(data, "2011-10") == delta_net
    assert tree.returns.gross_prev == 200.0 and tree.returns.gross_cur == 200.0
    assert tree.returns.returns_prev == 20.0 and tree.returns.returns_cur == 60.0

    assert tree.lever.level1 is not None
    assert reconciles([f.contribution for f in tree.lever.level1.factors], delta_net)
    assert tree.customers is not None
    assert reconciles(
        [tree.customers.new, tree.customers.resurrected, tree.customers.expansion,
         tree.customers.contraction, tree.customers.lapsed, tree.customers.unattributed],
        delta_net,
    )
    # The product lens totals GROSS, which here is zero while net fell 40.
    assert reconciles(
        [tree.products.volume, tree.products.mix, tree.products.price,
         tree.products.new_products, tree.products.discontinued_products],
        delta_gross,
    )
    assert delta_gross - (tree.returns.returns_cur - tree.returns.returns_prev) == delta_net


def test_the_runtime_check_catches_a_lens_that_does_not_add_up() -> None:
    """3C doubt-review R6: `RECONCILE_REL_TOLERANCE` lived in production
    thresholds but was read only by tests, so "every decomposition reconciles"
    held on seven fixtures and was unchecked on every real file. Both
    criticals that review found produced a non-reconciling tree."""
    _assert_sums([10.0, -4.0], 6.0, "a lens")  # exact: no complaint
    _assert_sums([1e20, 1.0], 1e20 + 1.0, "a lens")  # float residue: tolerated

    with pytest.raises(ReconciliationError, match="does not reconcile"):
        _assert_sums([10.0, -4.0], 7.0, "a lens")


def test_period_totals_agree_with_stage_2() -> None:
    """`lever.period_totals` and `signals.monthly_series` compute the same four
    figures independently, and only the latter was pinned against stage 2
    (3C doubt-review, optional). Stage 3 disagreeing with metrics.json about
    the current month would make the report contradict itself."""
    data = run_data(_bridge_rows())

    totals = period_totals(data, data.metrics.period.current)

    assert totals.revenue == pytest.approx(data.metrics.core.revenue_current)
    assert totals.orders == data.metrics.core.orders_current
    assert totals.customers == data.metrics.core.active_customers_current


def test_period_totals_count_orders_as_stage_2_does_on_a_month_with_returns() -> None:
    """2E: a return line is not an order in either stage. October: three
    sales and two return lines - orders 3 in both, not 5."""
    rows = daily_rows(date(2011, 9, 1), date(2011, 10, 31), customer="Alice")
    rows += [row(date(2011, 10, 5), qty=-1.0, customer="Alice"),
             row(date(2011, 10, 6), qty=-1.0, customer="Bob")]
    data = run_data(rows)

    totals = period_totals(data, data.metrics.period.current)

    assert totals.orders == data.metrics.core.orders_current == 31
    assert totals.revenue == pytest.approx(data.metrics.core.revenue_current)
    # The lever counts BUYERS since the 2E doubt-review (F1): Bob only
    # returned goods, so he is active (2) but not a buyer (1).
    assert totals.customers == data.metrics.core.buyers_current == 1
    assert data.metrics.core.active_customers_current == 2


def test_a_retained_customer_can_go_negative_without_breaking_the_bridge() -> None:
    """Bob buys 100 in October and only refunds in November: the bridge must
    carry that as a 160 contraction, not clamp it (Thach, 3C)."""
    data = run_data(_tree_rows())

    bridge = compute_bridge(data)

    assert bridge is not None
    assert bridge.contraction == pytest.approx(-160.0)  # Bob: 100 -> -60
    assert bridge.expansion == pytest.approx(40.0)  # Alice: 80 -> 120
    assert bridge.new == pytest.approx(80.0)  # Cara
    assert reconciles(
        [bridge.new, bridge.resurrected, bridge.expansion,
         bridge.contraction, bridge.lapsed, bridge.unattributed],
        -40.0,
    )
