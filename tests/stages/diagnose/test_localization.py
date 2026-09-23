"""Step 6: where the change happened.

Every dimension must account for its whole change - named members, Other, and
nothing lost in between. That property is tested per dimension rather than by
checking individual numbers, because a dimension that silently drops a member
still reports plausible figures for the ones it kept.
"""

from datetime import date

import pandas as pd
import pytest

from contracts.diagnosis import DiagnosisContract, Localization
from stages.diagnose.bridge import compute_bridge, customer_classes
from stages.diagnose.lever import month_revenue
from stages.diagnose.localization import compute_breadth, compute_localization
from stages.diagnose.members import (
    UNCATEGORISED_LABEL,
    MemberTotals,
    build_dimension,
    category_totals,
    customer_type_totals,
    product_totals,
)
from stages.diagnose.mix_rate import compute_mix_rate
from stages.diagnose.thresholds import MEMBERS_PER_DIMENSION
from tests.contracts.test_diagnosis import diagnosis_payload
from tests.stages.diagnose.diagnose_fixtures import MAPPING, run_data
from tests.stages.diagnose.test_shapley_and_lever import reconciles

CATEGORY_MAPPING = {**MAPPING, "Cat": "category"}
SKU_MAPPING = {**CATEGORY_MAPPING, "SKU": "sku"}


def sku_row(day: date, qty: float, product: str, sku: str) -> dict:
    """A row carrying a SKU, for the case where two SKUs share one name."""
    return {**row(day, qty=qty, price=10.0, product=product), "SKU": sku}


def row(day: date, *, qty: float = 1.0, price: float = 10.0, product: str = "Widget",
        customer: str = "Alice", category: str | None = "Home") -> dict:
    entry = {"Date": day.isoformat(), "Qty": str(qty), "Price": str(price),
             "Product": product, "Cust": customer}
    entry["Cat"] = category
    return entry


def dimension_total(dimension) -> float:
    """Named members plus Other. New and removed members are already inside
    those figures - they are listed separately for the narration, not added
    again - so this is the whole dimension."""
    parts = [member.delta for member in dimension.members]
    if dimension.other is not None:
        parts.append(dimension.other.delta)
    return sum(parts)


def _two_category_rows() -> list[dict]:
    """October 400 -> November 310, so every dimension must total -90.

    Home     Oct 300 (A 200, B 100)   Nov 210 (A 150, B 60)
    Kitchen  Oct 100 (C 100)          Nov 100 (C 100)
    """
    return [
        row(date(2011, 10, 1), qty=20, price=10.0, product="A", category="Home"),
        row(date(2011, 10, 5), qty=10, price=10.0, product="B", category="Home"),
        row(date(2011, 10, 9), qty=10, price=10.0, product="C", category="Kitchen"),
        row(date(2011, 11, 5), qty=15, price=10.0, product="A", category="Home"),
        row(date(2011, 11, 9), qty=6, price=10.0, product="B", category="Home"),
        row(date(2011, 11, 30), qty=10, price=10.0, product="C", category="Kitchen"),
    ]


# --- reconciliation, per dimension --------------------------------------------


def test_every_dimension_accounts_for_the_whole_change() -> None:
    data = run_data(_two_category_rows(), CATEGORY_MAPPING)
    delta = month_revenue(data, "2011-11") - month_revenue(data, "2011-10")
    assert delta == pytest.approx(-90.0)

    localization = compute_localization(data, delta)

    assert [d.name for d in localization.dimensions] == [
        "category", "product", "customer_type"]
    for dimension in localization.dimensions:
        assert reconciles([dimension_total(dimension)], delta), dimension.name


def test_a_dimension_reconciles_even_when_members_are_pushed_into_other() -> None:
    """Six products, so one falls outside the five named slots and must land
    in Other rather than disappearing."""
    rows = []
    for index in range(6):
        rows.append(row(date(2011, 10, index + 1), qty=10 + index, price=10.0,
                        product=f"P{index}"))
        rows.append(row(date(2011, 11, index + 1), qty=5, price=10.0, product=f"P{index}"))
    rows.append(row(date(2011, 11, 30), qty=5, price=10.0, product="P0"))
    data = run_data(rows, CATEGORY_MAPPING)
    delta = month_revenue(data, "2011-11") - month_revenue(data, "2011-10")

    dimension = build_dimension("product", product_totals(data), delta)

    assert len(dimension.members) == MEMBERS_PER_DIMENSION
    assert dimension.other is not None
    assert reconciles([dimension_total(dimension)], delta)


def test_members_are_ranked_by_absolute_delta_not_by_revenue() -> None:
    """A large, steady member must not crowd out a small, moving one: the
    question is where the change is, not who is biggest."""
    rows = [
        # Steady: huge revenue, no change at all.
        row(date(2011, 10, 1), qty=100, price=10.0, product="Steady"),
        row(date(2011, 11, 1), qty=100, price=10.0, product="Steady"),
        # Mover: small revenue, all of the change.
        row(date(2011, 10, 2), qty=10, price=10.0, product="Mover"),
        row(date(2011, 11, 30), qty=1, price=10.0, product="Mover"),
    ]
    data = run_data(rows, CATEGORY_MAPPING)
    delta = month_revenue(data, "2011-11") - month_revenue(data, "2011-10")

    dimension = build_dimension("product", product_totals(data), delta)

    assert dimension.members[0].name == "Mover"
    assert dimension.members[0].delta == pytest.approx(-90.0)


# --- the three edge cases Thach settled ---------------------------------------


def test_when_no_member_clears_the_bar_the_top_movers_are_named_and_flagged() -> None:
    """Thach, 3D: a dimension that names nobody answers nothing, and a
    fragmented shop is exactly where the biggest movers matter most. The
    waiver is a structured field so step 7 can tell this apart from a
    genuinely concentrated dimension."""
    rows = []
    for index in range(60):  # each ~1.7% of revenue, one order each
        rows.append(row(date(2011, 10, 1), qty=10, price=10.0, product=f"P{index}"))
        rows.append(row(date(2011, 11, 30), qty=9, price=10.0, product=f"P{index}"))
    data = run_data(rows, CATEGORY_MAPPING)
    delta = month_revenue(data, "2011-11") - month_revenue(data, "2011-10")

    dimension = build_dimension("product", product_totals(data), delta)

    assert dimension.size_filter_waived is True
    assert dimension.member_count == 60
    assert len(dimension.members) == MEMBERS_PER_DIMENSION
    assert reconciles([dimension_total(dimension)], delta)


def test_a_busy_member_stays_named_even_though_its_revenue_is_tiny() -> None:
    """The size rule collapses a member only if it is small AND quiet, and the
    orders half asks whether it was busy in EITHER period - a line that sold
    40 times last month and twice this month is exactly the kind of collapse a
    shop owner wants named, not hidden inside Other.

    Six members, so the filter really applies (with five or fewer everything
    fits and the bar is not consulted). Bulk is 0.8% of previous revenue, well
    under the bar, and is named only because of its 40 orders.
    """
    rows = []
    for index in range(5):
        rows.append(row(date(2011, 10, 1), qty=100, price=10.0, product=f"Big{index}"))
        rows.append(row(date(2011, 11, 30), qty=100, price=10.0, product=f"Big{index}"))
    rows += [row(date(2011, 10, 2), qty=1, price=1.0, product="Bulk") for _ in range(40)]
    rows += [row(date(2011, 11, 30), qty=1, price=1.0, product="Bulk") for _ in range(2)]
    data = run_data(rows, CATEGORY_MAPPING)
    delta = month_revenue(data, "2011-11") - month_revenue(data, "2011-10")

    dimension = build_dimension("product", product_totals(data), delta)

    assert dimension.member_count == 6
    assert "Bulk" in {member.name for member in dimension.members}
    assert reconciles([dimension_total(dimension)], delta)


def test_a_dimension_with_large_members_does_not_report_a_waiver() -> None:
    data = run_data(_two_category_rows(), CATEGORY_MAPPING)
    delta = month_revenue(data, "2011-11") - month_revenue(data, "2011-10")

    dimension = build_dimension("category", category_totals(data), delta)

    assert dimension.size_filter_waived is False
    assert dimension.member_count == 2


def test_blank_categories_are_a_named_member_flagged_as_a_data_gap() -> None:
    """Thach, 3D: visible, ranked like any other member, and flagged so step 7
    never writes a recommendation about "(uncategorised)" as if it were a real
    product group. Dropping it would leave the dimension reconciling to a
    subtotal - the shape of 3C's first critical."""
    rows = [
        row(date(2011, 10, 1), qty=20, price=10.0, category="Home"),
        row(date(2011, 10, 5), qty=10, price=10.0, category=None),
        row(date(2011, 11, 5), qty=15, price=10.0, category="Home"),
        row(date(2011, 11, 30), qty=2, price=10.0, category="   "),
    ]
    data = run_data(rows, CATEGORY_MAPPING)
    delta = month_revenue(data, "2011-11") - month_revenue(data, "2011-10")

    dimension = build_dimension("category", category_totals(data), delta)

    gap = [member for member in dimension.members if member.is_data_gap]
    assert [member.name for member in gap] == [UNCATEGORISED_LABEL]
    assert gap[0].rev_prev == pytest.approx(100.0)
    assert gap[0].rev_cur == pytest.approx(20.0)
    assert reconciles([dimension_total(dimension)], delta)


def test_a_real_category_spelled_like_the_gap_label_stays_separate() -> None:
    # The bucket is identified by its flag, not by its name.
    rows = [
        row(date(2011, 10, 1), qty=20, price=10.0, category=UNCATEGORISED_LABEL),
        row(date(2011, 10, 5), qty=10, price=10.0, category=None),
        row(date(2011, 11, 30), qty=15, price=10.0, category=UNCATEGORISED_LABEL),
    ]
    data = run_data(rows, CATEGORY_MAPPING)
    delta = month_revenue(data, "2011-11") - month_revenue(data, "2011-10")

    dimension = build_dimension("category", category_totals(data), delta)

    flags = sorted(member.is_data_gap for member in dimension.members)
    assert flags == [False, True]
    assert reconciles([dimension_total(dimension)], delta)


def test_a_member_zero_in_both_periods_is_neither_new_nor_removed() -> None:
    """Thach, 3D: presence means having a revenue-counted row, the same
    definition the bridge uses, so a product whose sales and returns cancelled
    is an ordinary member with delta 0 - not a discontinued line."""
    rows = [
        row(date(2011, 10, 1), qty=20, price=10.0, product="Real"),
        row(date(2011, 10, 2), qty=5, price=10.0, product="Cancels"),
        row(date(2011, 10, 3), qty=-5, price=10.0, product="Cancels"),
        row(date(2011, 11, 5), qty=15, price=10.0, product="Real"),
        row(date(2011, 11, 6), qty=5, price=10.0, product="Cancels"),
        row(date(2011, 11, 30), qty=-5, price=10.0, product="Cancels"),
    ]
    data = run_data(rows, CATEGORY_MAPPING)
    delta = month_revenue(data, "2011-11") - month_revenue(data, "2011-10")

    dimension = build_dimension("product", product_totals(data), delta)

    assert dimension.new_members == []
    assert dimension.removed_members == []
    assert reconciles([dimension_total(dimension)], delta)


def test_new_and_removed_members_are_listed() -> None:
    rows = [
        row(date(2011, 10, 1), qty=20, price=10.0, product="Stays"),
        row(date(2011, 10, 2), qty=5, price=10.0, product="Gone"),
        row(date(2011, 11, 5), qty=15, price=10.0, product="Stays"),
        row(date(2011, 11, 30), qty=5, price=10.0, product="Fresh"),
    ]
    data = run_data(rows, CATEGORY_MAPPING)
    delta = month_revenue(data, "2011-11") - month_revenue(data, "2011-10")

    dimension = build_dimension("product", product_totals(data), delta)

    assert dimension.new_members == ["Fresh"]
    assert dimension.removed_members == ["Gone"]
    assert reconciles([dimension_total(dimension)], delta)


# --- what the 3D doubt-review found -------------------------------------------


def test_two_products_sharing_one_name_both_survive_into_the_dimension() -> None:
    """3D doubt-review C1: the set logic keyed on the DISPLAY NAME, so when two
    keys shared a label the second matched the first's entry, was excluded from
    the remainder, and appeared in neither the named members nor Other. It
    simply vanished, and 6.4% of the change went with it.

    Two SKUs under one product name is the commonest shape in retail. Six
    members, so the filter really runs - with five or fewer everything fits and
    the collision never surfaces, which is why the existing
    "spelled like the gap label" test passed while the bug was live.
    """
    rows = []
    for index in range(5):
        rows.append(sku_row(date(2011, 10, 1), 100, f"P{index}", f"S{index}"))
        rows.append(sku_row(date(2011, 11, 30), 30, f"P{index}", f"S{index}"))
    rows.append(sku_row(date(2011, 10, 2), 90, "Variant", "V-RED"))
    rows.append(sku_row(date(2011, 11, 30), 1, "Variant", "V-RED"))
    rows.append(sku_row(date(2011, 10, 3), 30, "Variant", "V-BLUE"))
    rows.append(sku_row(date(2011, 11, 30), 1, "Variant", "V-BLUE"))
    data = run_data(rows, SKU_MAPPING)
    delta = month_revenue(data, "2011-11") - month_revenue(data, "2011-10")

    dimension = build_dimension("product", product_totals(data), delta)

    assert dimension.member_count == 7
    assert reconciles([dimension_total(dimension)], delta)


def test_a_flat_month_gives_no_member_an_enormous_share() -> None:
    """3D doubt-review C2: `share_of_change` divided by the total under an
    exact-zero guard, so on a month that is flat in business terms but -5.6e-17
    in floating point, a member's share came out as -5.4e15 - which step 8
    would narrate as a percentage with seventeen digits."""
    rows = [
        row(date(2011, 10, 1), qty=1, price=0.1, product="A"),
        row(date(2011, 10, 2), qty=1, price=0.2, product="B"),
        row(date(2011, 10, 3), qty=1, price=0.3, product="C"),
        row(date(2011, 11, 30), qty=1, price=0.3, product="A"),
        row(date(2011, 11, 30), qty=1, price=0.2, product="B"),
        row(date(2011, 11, 30), qty=1, price=0.1, product="C"),
    ]
    data = run_data(rows, CATEGORY_MAPPING)
    delta = month_revenue(data, "2011-11") - month_revenue(data, "2011-10")
    assert delta != 0.0  # float residue, not a real move

    dimension = build_dimension("product", product_totals(data), delta)

    assert all(member.share_of_change == 0.0 for member in dimension.members)


def test_a_refunds_line_is_judged_on_the_size_of_its_movement() -> None:
    """3D doubt-review C3: the size test compared a SIGNED share against a
    SIGNED base. A line whose previous month netted below zero got a negative
    share, which is "below 2%", so the largest movement in the dimension was
    judged small and quiet - and a negative base inverted the test outright,
    burying six ordinary products in Other."""
    rows = []
    for index in range(6):
        rows.append(row(date(2011, 10, 1), qty=10, price=10.0, product=f"P{index}"))
        rows.append(row(date(2011, 11, 30), qty=5, price=10.0, product=f"P{index}"))
    rows.append(row(date(2011, 10, 2), qty=-250, price=10.0, product="Refunds"))
    data = run_data(rows, CATEGORY_MAPPING)
    delta = month_revenue(data, "2011-11") - month_revenue(data, "2011-10")

    dimension = build_dimension("product", product_totals(data), delta)

    named = {member.name for member in dimension.members}
    assert "Refunds" in named  # +2500, by far the largest movement
    assert len(named & {f"P{index}" for index in range(6)}) >= 4
    assert reconciles([dimension_total(dimension)], delta)


def test_a_whitespace_only_product_name_is_the_same_gap_bucket() -> None:
    """3D doubt-review R1: `isna()` caught only the missing half, because
    `product_identity` maps "   " to the perfectly non-null key "name:". That
    produced a second, unflagged bucket displayed as blank space, which step 7
    would write recommendations about as a real product line."""
    rows = [
        row(date(2011, 10, 1), qty=20, price=10.0, product="Real"),
        row(date(2011, 10, 2), qty=10, price=10.0, product="   "),
        {**row(date(2011, 10, 3), qty=10, price=10.0), "Product": None},
        row(date(2011, 11, 30), qty=15, price=10.0, product="Real"),
    ]
    data = run_data(rows, CATEGORY_MAPPING)
    delta = month_revenue(data, "2011-11") - month_revenue(data, "2011-10")

    dimension = build_dimension("product", product_totals(data), delta)

    gaps = [member for member in dimension.members if member.is_data_gap]
    assert len(gaps) == 1  # one bucket, not two
    assert gaps[0].rev_prev == pytest.approx(200.0)
    assert all(member.name.strip() for member in dimension.members)
    assert reconciles([dimension_total(dimension)], delta)


def test_the_gap_bucket_is_never_announced_as_a_new_member() -> None:
    """3D doubt-review R3: `new_members` carries bare strings with no flag, so
    a gap bucket appearing only this month was reported as "a new category
    launched: (uncategorised)" - decision (b) defeated through the side door."""
    rows = [
        row(date(2011, 10, 1), qty=20, price=10.0, category="Home"),
        row(date(2011, 11, 5), qty=15, price=10.0, category="Home"),
        row(date(2011, 11, 30), qty=2, price=10.0, category=None),
    ]
    data = run_data(rows, CATEGORY_MAPPING)
    delta = month_revenue(data, "2011-11") - month_revenue(data, "2011-10")

    dimension = build_dimension("category", category_totals(data), delta)

    assert dimension.new_members == []
    assert any(member.is_data_gap for member in dimension.members)
    assert reconciles([dimension_total(dimension)], delta)


def test_a_dimension_dominated_by_one_large_member_reports_no_waiver() -> None:
    """3D doubt-review R4: the waiver also fired on the "everything fits"
    branch, so a dimension where one member holds 99.9% of revenue reported
    `size_filter_waived=True` - the opposite of the signal step 7 reads it
    for."""
    rows = [
        row(date(2011, 10, 1), qty=100, price=10.0, category="Home"),
        row(date(2011, 10, 2), qty=1, price=1.0, category="Trinkets"),
        row(date(2011, 11, 30), qty=60, price=10.0, category="Home"),
        row(date(2011, 11, 30), qty=1, price=1.0, category="Trinkets"),
    ]
    data = run_data(rows, CATEGORY_MAPPING)
    delta = month_revenue(data, "2011-11") - month_revenue(data, "2011-10")

    dimension = build_dimension("category", category_totals(data), delta)

    assert dimension.size_filter_waived is False
    assert {member.name for member in dimension.members} == {"Home", "Trinkets"}


def test_a_month_swamped_by_returns_gets_no_mix_rate_split() -> None:
    """3D doubt-review R5: selecting the metric by "moved most" hands the split
    to whichever metric a negative denominator has made meaningless - a sign
    flip is the largest relative move on the page. The reported result was
    "price per unit rose from 10 to 115, +1050%", all of it attributed to mix,
    on a month that sold 50 and refunded 165."""
    rows = [
        row(date(2011, 10, 1), qty=10, price=5.0, category="Cheap"),
        row(date(2011, 10, 2), qty=10, price=15.0, category="Dear"),
        row(date(2011, 11, 5), qty=10, price=5.0, category="Cheap"),
        row(date(2011, 11, 30), qty=-11, price=15.0, category="Dear"),
    ]
    data = run_data(rows, CATEGORY_MAPPING)

    mix_rate = compute_mix_rate(data)

    assert mix_rate is None or mix_rate.metric == "aov"


def test_a_flat_month_is_not_called_concentrated() -> None:
    """3D doubt-review R8: a total of exactly 0.0 made `delta_total > 0` False,
    so breadth counted every member that fell and returned `concentrated` on a
    month where one product rose 50 and another fell 50."""
    rows = [
        row(date(2011, 10, 1), qty=10, price=10.0, product="Up"),
        row(date(2011, 10, 2), qty=10, price=10.0, product="Down"),
        row(date(2011, 11, 30), qty=15, price=10.0, product="Up"),
        row(date(2011, 11, 30), qty=5, price=10.0, product="Down"),
    ]
    data = run_data(rows, CATEGORY_MAPPING)
    delta = month_revenue(data, "2011-11") - month_revenue(data, "2011-10")
    assert delta == pytest.approx(0.0)

    breadth = compute_breadth(product_totals(data), delta)

    assert breadth.classification == "mixed"
    # And the share itself, not only the label it feeds: a total that did not
    # move has no direction, so no part of the base can be "moving with it".
    # Asserting the classification alone left this unpinned, because the flat
    # case is guarded twice and either guard alone produces "mixed".
    assert breadth.declining_base_share == 0.0


def test_one_rule_decides_who_is_new_for_both_the_bridge_and_step_6() -> None:
    """3D doubt-review R9: the rule was stated twice, under a docstring saying
    that step 6 taking its classes from step 5 made divergence impossible. Two
    copies diverge the moment one is edited, and nothing compared them."""
    data = run_data(_bridge_style_rows(), CATEGORY_MAPPING)

    classes = customer_classes(data)
    bridge = compute_bridge(data)

    assert bridge is not None
    assert sum(1 for value in classes.values() if value == "new") == \
        bridge.evidence["new_customers"]


def _bridge_style_rows() -> list[dict]:
    return [
        row(date(2011, 8, 15), qty=1, price=90.0, customer="Eve"),
        row(date(2011, 10, 5), qty=1, price=100.0, customer="Alice"),
        row(date(2011, 10, 6), qty=1, price=60.0, customer="Cara"),
        row(date(2011, 11, 30), qty=1, price=150.0, customer="Alice"),
        row(date(2011, 11, 30), qty=1, price=40.0, customer="Dan"),
        row(date(2011, 11, 30), qty=1, price=25.0, customer="Eve"),
    ]


# --- contract round-trip ------------------------------------------------------


def _round_trip(localization) -> Localization:
    """Put a real Localization through the whole contract and back.

    Step 6 has no caller in the engine yet - 3G assembles `diagnosis.json` -
    so nothing else proves a computed `Localization` is actually valid inside
    `DiagnosisContract`, or survives being written to JSON and read back
    (Thach, after 3D). That is not a theoretical gap: 3C's second critical was
    an infinity that pydantic serialised to `null` in a field typed as a
    required float, producing a file that would not validate on the way in.
    Reloading is the assertion - a null in a required float fails there.
    """
    payload = diagnosis_payload()
    payload["localization"] = localization.model_dump(mode="json")
    contract = DiagnosisContract.model_validate(payload)
    text = contract.model_dump_json()
    assert "NaN" not in text and "Infinity" not in text
    reloaded = DiagnosisContract.model_validate_json(text)
    assert reloaded.localization is not None
    return reloaded.localization


def test_a_localization_survives_the_contract_and_a_json_round_trip() -> None:
    data = run_data(_two_category_rows(), CATEGORY_MAPPING)
    delta = month_revenue(data, "2011-11") - month_revenue(data, "2011-10")

    reloaded = _round_trip(compute_localization(data, delta))

    assert [dimension.name for dimension in reloaded.dimensions] == [
        "category", "product", "customer_type"]
    for dimension in reloaded.dimensions:
        assert reconciles([dimension_total(dimension)], delta), dimension.name


def test_the_awkward_inputs_also_survive_the_contract_round_trip() -> None:
    """The same trip on a file built from the cases that produce edge values:
    blank categories, a returns line that inverts a member's revenue, and a
    product that cancels itself to zero. These are where a non-finite figure
    or an out-of-range share would come from, if one were going to."""
    rows = [
        row(date(2011, 10, 1), qty=20, price=10.0, product="Real", category="Home"),
        row(date(2011, 10, 2), qty=10, price=10.0, product="Gap", category=None),
        row(date(2011, 10, 3), qty=-30, price=10.0, product="Refunds", category="   "),
        row(date(2011, 10, 4), qty=5, price=10.0, product="Cancels", category="Home"),
        row(date(2011, 10, 5), qty=-5, price=10.0, product="Cancels", category="Home"),
        row(date(2011, 11, 30), qty=15, price=10.0, product="Real", category="Home"),
        row(date(2011, 11, 30), qty=2, price=10.0, product="Gap", category=None),
    ]
    data = run_data(rows, CATEGORY_MAPPING)
    delta = month_revenue(data, "2011-11") - month_revenue(data, "2011-10")

    reloaded = _round_trip(compute_localization(data, delta))

    for dimension in reloaded.dimensions:
        assert reconciles([dimension_total(dimension)], delta), dimension.name
    # The shares the contract types as UnitInterval really are in range.
    assert 0.0 <= reloaded.breadth.declining_base_share <= 1.0
    assert 0.0 <= reloaded.breadth.top_member_share <= 1.0


def test_a_flat_month_survives_the_contract_round_trip() -> None:
    """The case that produced a share of -5.4e15 before the guard: a total
    that is float residue rather than a real move."""
    rows = [
        row(date(2011, 10, 1), qty=1, price=0.1, product="A"),
        row(date(2011, 10, 2), qty=1, price=0.2, product="B"),
        row(date(2011, 10, 3), qty=1, price=0.3, product="C"),
        row(date(2011, 11, 30), qty=1, price=0.3, product="A"),
        row(date(2011, 11, 30), qty=1, price=0.2, product="B"),
        row(date(2011, 11, 30), qty=1, price=0.1, product="C"),
    ]
    data = run_data(rows, CATEGORY_MAPPING)
    delta = month_revenue(data, "2011-11") - month_revenue(data, "2011-10")

    reloaded = _round_trip(compute_localization(data, delta))

    products = next(d for d in reloaded.dimensions if d.name == "product")
    assert all(member.share_of_change == 0.0 for member in products.members)


# --- edge cases (CLAUDE.md section 5) -----------------------------------------


def test_a_single_row_file_produces_a_dimension_that_still_reconciles() -> None:
    data = run_data([row(date(2011, 11, 30), qty=1, price=10.0)], CATEGORY_MAPPING)
    delta = month_revenue(data, "2011-11") - month_revenue(data, "2011-10")

    localization = compute_localization(data, delta)

    for dimension in localization.dimensions:
        assert reconciles([dimension_total(dimension)], delta), dimension.name


def test_an_all_blank_category_column_is_one_bucket_holding_everything() -> None:
    rows = [
        row(date(2011, 10, 1), qty=20, price=10.0, category=None),
        row(date(2011, 11, 30), qty=15, price=10.0, category="   "),
    ]
    data = run_data(rows, CATEGORY_MAPPING)
    delta = month_revenue(data, "2011-11") - month_revenue(data, "2011-10")

    dimension = build_dimension("category", category_totals(data), delta)

    assert [member.is_data_gap for member in dimension.members] == [True]
    assert dimension.new_members == [] and dimension.removed_members == []
    assert reconciles([dimension_total(dimension)], delta)


def test_breadth_on_a_dimension_with_no_members_does_not_crash() -> None:
    empty = MemberTotals(
        rev_prev=pd.Series(dtype=float), rev_cur=pd.Series(dtype=float),
        orders_prev=pd.Series(dtype=int), orders_cur=pd.Series(dtype=int),
        labels={}, gap_keys=frozenset())

    breadth = compute_breadth(empty, 0.0)

    assert (breadth.declining_base_share, breadth.top_member_share) == (0.0, 0.0)
    assert breadth.classification == "mixed"


def test_an_empty_dimension_names_nobody_and_reports_no_waiver() -> None:
    empty = MemberTotals(
        rev_prev=pd.Series(dtype=float), rev_cur=pd.Series(dtype=float),
        orders_prev=pd.Series(dtype=int), orders_cur=pd.Series(dtype=int),
        labels={}, gap_keys=frozenset())

    dimension = build_dimension("product", empty, -100.0)

    assert dimension.members == [] and dimension.other is None
    assert dimension.member_count == 0
    assert dimension.size_filter_waived is False  # nothing to waive a bar for


# --- customer type ------------------------------------------------------------


def test_the_customer_type_dimension_takes_its_classes_from_the_bridge() -> None:
    rows = [
        row(date(2011, 10, 1), qty=10, price=10.0, customer="Stays"),
        row(date(2011, 10, 2), qty=5, price=10.0, customer="Leaves"),
        row(date(2011, 11, 30), qty=8, price=10.0, customer="Stays"),
        row(date(2011, 11, 30), qty=4, price=10.0, customer="Arrives"),
    ]
    data = run_data(rows, CATEGORY_MAPPING)
    delta = month_revenue(data, "2011-11") - month_revenue(data, "2011-10")

    dimension = build_dimension(
        "customer_type", customer_type_totals(data, customer_classes(data)), delta)

    members = {member.name: member for member in dimension.members}
    assert members["lapsed"].rev_prev == pytest.approx(50.0)
    assert members["new"].rev_cur == pytest.approx(40.0)
    assert members["retained"].delta == pytest.approx(-20.0)
    assert reconciles([dimension_total(dimension)], delta)


# --- mix vs rate --------------------------------------------------------------


def test_mix_and_rate_reconcile_to_the_metric_change() -> None:
    """DIAGNOSE_DESIGN 1.3's case: both categories' AOV rises while overall
    AOV falls, because orders shifted towards the cheap one. Only this split
    says so, and the two effects must sum to the whole move."""
    rows = []
    # Units per order differ between the categories, so AOV and price per unit
    # are genuinely different metrics here. With one unit per line they are the
    # same number and the choice between them is a tie.
    # October: 5 cheap orders worth 20, 5 dear orders worth 100 -> AOV 60.
    for index in range(5):
        rows.append(row(date(2011, 10, index + 1), qty=1, price=20.0, category="Cheap"))
        rows.append(row(date(2011, 10, index + 10), qty=5, price=20.0, category="Dear"))
    # November: 8 cheap orders worth 22, 2 dear worth 105. Both categories'
    # own AOV rose (20->22, 100->105) and the overall AOV fell 60 -> 38.6.
    for index in range(8):
        rows.append(row(date(2011, 11, 30), qty=1, price=22.0, category="Cheap"))
    for index in range(2):
        rows.append(row(date(2011, 11, 30), qty=5, price=21.0, category="Dear"))
    data = run_data(rows, CATEGORY_MAPPING)

    mix_rate = compute_mix_rate(data)

    assert mix_rate is not None
    assert mix_rate.metric == "aov"  # AOV moved -35.7%, price per unit +7.2%
    aov_prev = (5 * 20 + 5 * 100) / 10
    aov_cur = (8 * 22 + 2 * 105) / 10
    assert (aov_prev, aov_cur) == (60.0, 38.6)
    assert reconciles([mix_rate.mix, mix_rate.rate], aov_cur - aov_prev)
    # The mix effect carries the fall; the rate effect is positive, because
    # every category's own AOV rose.
    assert mix_rate.mix < 0
    assert mix_rate.rate > 0


def test_the_split_covers_uncategorised_revenue_too() -> None:
    """The weighted average only equals the overall AOV while every order is
    in some category. Drop the blank ones and the split silently becomes a
    split of a different number - it still sums to something, just not to the
    change the report names. Here the two differ: 58.33 -> 37.82 with the
    blanks, 60.00 -> 38.60 without.
    """
    rows = []
    for index in range(5):
        rows.append(row(date(2011, 10, index + 1), qty=1, price=20.0, category="Cheap"))
        rows.append(row(date(2011, 10, index + 10), qty=5, price=20.0, category="Dear"))
    rows += [row(date(2011, 10, 20), qty=1, price=50.0, category=None) for _ in range(2)]
    rows += [row(date(2011, 11, 30), qty=1, price=22.0, category="Cheap") for _ in range(8)]
    rows += [row(date(2011, 11, 30), qty=5, price=21.0, category="Dear") for _ in range(2)]
    rows.append(row(date(2011, 11, 30), qty=1, price=30.0, category="   "))
    data = run_data(rows, CATEGORY_MAPPING)

    mix_rate = compute_mix_rate(data)

    assert mix_rate is not None
    aov_prev = (5 * 20 + 5 * 100 + 2 * 50) / 12
    aov_cur = (8 * 22 + 2 * 105 + 30) / 11
    assert reconciles([mix_rate.mix, mix_rate.rate], aov_cur - aov_prev)


def test_there_is_no_mix_rate_split_without_a_category_column() -> None:
    data = run_data(_two_category_rows())  # MAPPING has no category

    assert compute_mix_rate(data) is None


# --- breadth ------------------------------------------------------------------


def test_breadth_is_broad_when_most_of_the_base_moves_together() -> None:
    rows = []
    for index in range(10):
        rows.append(row(date(2011, 10, 1), qty=10, price=10.0, product=f"P{index}"))
        # Every November row on the 30th: the file must reach the end of the
        # month for November to be the current period, and putting that row on
        # one product would skew the very member breadth is measuring.
        rows.append(row(date(2011, 11, 30), qty=8, price=10.0, product=f"P{index}"))
    data = run_data(rows, CATEGORY_MAPPING)
    delta = month_revenue(data, "2011-11") - month_revenue(data, "2011-10")

    breadth = compute_breadth(product_totals(data), delta)

    assert breadth.declining_base_share == pytest.approx(1.0)
    assert breadth.classification == "broad"


def test_breadth_is_concentrated_when_one_member_carries_the_move() -> None:
    rows = [row(date(2011, 10, index + 1), qty=10, price=10.0, product=f"P{index}")
            for index in range(10)]
    rows += [row(date(2011, 11, index + 1), qty=10, price=10.0, product=f"P{index}")
             for index in range(10)]
    # One product collapses; the other nine are unchanged.
    rows.append(row(date(2011, 11, 30), qty=-9, price=10.0, product="P0"))
    data = run_data(rows, CATEGORY_MAPPING)
    delta = month_revenue(data, "2011-11") - month_revenue(data, "2011-10")

    breadth = compute_breadth(product_totals(data), delta)

    assert breadth.top_member_share == pytest.approx(1.0)
    assert breadth.classification == "concentrated"


def test_when_a_change_is_both_broad_and_concentrated_it_is_called_broad() -> None:
    """The two conditions are not exclusive, and which is tested first is a
    decision, not an implementation detail. One dominant product can fall
    while the whole base drifts the same way: "this is happening across the
    business" is the more useful thing to say, because it redirects attention
    away from the one product and towards a cause that could affect
    everything.

    Hand-checked: prev 800/100/100, cur 400/90/90. Every member moves down, so
    declining_base_share is 1.0 (>= 0.70), and the big one carries 400 of the
    420 total movement, so top_member_share is 0.952 (>= 0.50).
    """
    rows = [
        row(date(2011, 10, 1), qty=80, price=10.0, product="Big"),
        row(date(2011, 10, 1), qty=10, price=10.0, product="Small1"),
        row(date(2011, 10, 1), qty=10, price=10.0, product="Small2"),
        row(date(2011, 11, 30), qty=40, price=10.0, product="Big"),
        row(date(2011, 11, 30), qty=9, price=10.0, product="Small1"),
        row(date(2011, 11, 30), qty=9, price=10.0, product="Small2"),
    ]
    data = run_data(rows, CATEGORY_MAPPING)
    delta = month_revenue(data, "2011-11") - month_revenue(data, "2011-10")

    breadth = compute_breadth(product_totals(data), delta)

    assert breadth.declining_base_share == pytest.approx(1.0)
    assert breadth.top_member_share == pytest.approx(400 / 420)
    assert breadth.classification == "broad"


def test_breadth_is_measured_over_every_member_not_the_named_five() -> None:
    """Measured over the top five, every change looks concentrated - they are
    chosen for being the largest movers."""
    rows = []
    for index in range(20):
        rows.append(row(date(2011, 10, 1), qty=10, price=10.0, product=f"P{index}"))
        rows.append(row(date(2011, 11, 30), qty=9, price=10.0, product=f"P{index}"))
    data = run_data(rows, CATEGORY_MAPPING)
    delta = month_revenue(data, "2011-11") - month_revenue(data, "2011-10")

    breadth = compute_breadth(product_totals(data), delta)

    # Twenty equal movers: no one of them is half the movement.
    assert breadth.top_member_share < 0.10
    assert breadth.classification == "broad"
