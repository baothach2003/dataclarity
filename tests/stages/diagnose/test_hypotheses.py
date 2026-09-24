"""Step 7: verdicts for the fixed catalog (docs/AI_PIPELINE.md 7.8).

End-to-end tests build steps 1-6 from real rows and hand the blocks to step 7
exactly as the engine will. Unit tests of a single rule use small stand-ins
for the blocks, with every expected number derived by hand in the docstring.
"""

from datetime import date, timedelta
from types import SimpleNamespace

import pytest

import stages.diagnose.hypothesis_evidence_customers as customers_module
from stages.diagnose.calendar_effect import compute_calendar
from stages.diagnose.catalog import CATALOG
from stages.diagnose.frame import build_frame, history_window
from stages.diagnose.hypotheses import decomposition_gross, evaluate_hypotheses, share_verdict
from stages.diagnose.hypothesis_evidence import c4
from stages.diagnose.lever import month_revenue
from stages.diagnose.localization import compute_localization
from stages.diagnose.signals import compute_signals
from stages.diagnose.step7_inputs import Changes, Step7Inputs
from stages.diagnose.tree import compute_tree
from stages.diagnose.trust import evaluate_trust
from tests.stages.diagnose.diagnose_fixtures import daily_months, full_months, row, run_data
from tests.stages.diagnose.test_rule_one_reliability import months


def step7(data) -> Step7Inputs:
    history = history_window(data)
    trust = evaluate_trust(data, history)
    if trust.verdict == "blocked":
        return Step7Inputs(data, history, build_frame(data), trust, None, None, None, None)
    period = data.metrics.period
    delta = month_revenue(data, period.current) - month_revenue(data, period.previous)
    return Step7Inputs(data, history, build_frame(data), trust,
                       compute_calendar(data, history), compute_signals(data, history),
                       compute_tree(data, history), compute_localization(data, delta))


def by_id(results):
    return {h.id: h for h in results}


# --- the whole catalog, every run ---------------------------------------------


def test_every_catalog_id_is_reported_in_catalog_order() -> None:
    """ADR-0005: every hypothesis appears every run, including the ones that
    fail - ids, families, lenses and statements straight from the catalog."""
    data = run_data(full_months(months([1000.0] * 26)))

    results = evaluate_hypotheses(step7(data))

    # On basis "lines" (no order_id here) B1 and B2 carry their lines
    # statements (2E-e); every other hypothesis its one statement.
    assert [(h.id, h.family, h.lens, h.statement) for h in results] == \
        [(s.id, s.family, s.lens, s.lines_statement or s.statement) for s in CATALOG]


def test_directional_hypotheses_carry_no_share() -> None:
    data = run_data(full_months(months([1000.0] * 25 + [800.0])))

    results = by_id(evaluate_hypotheses(step7(data)))

    for hypothesis_id in ("D2", "D3", "T3", "C4", "R1"):
        assert results[hypothesis_id].contribution is None
        assert results[hypothesis_id].share is None


def test_t3_is_inconclusive_and_lists_every_series_without_a_verdict() -> None:
    """ADR-0007: no step-4 row is a verdict, so T3 is inconclusive on every
    file, and its evidence names every series in the run - all eight here,
    since the fixture maps a customer column."""
    data = run_data(full_months(months([1000.0] * 26)))
    inputs = step7(data)

    t3 = by_id(evaluate_hypotheses(inputs))["T3"]

    assert t3.verdict == "inconclusive"
    assert t3.evidence["series_without_verdict"] == [s.series for s in inputs.signals]


# --- T2 and the base guard ------------------------------------------------------


def _seasonal(ly_prev: float) -> dict[str, float]:
    """26 months ending 2012-02. The year-ago pair is 2011-01 -> 2011-02 and
    this year's 2012-01 -> 2012-02 repeats it: 1,000 -> 1,500."""
    values = months([1000.0] * 26)
    values["2011-01"] = ly_prev
    values["2011-02"] = 1500.0
    values["2012-02"] = 1500.0
    return values


def test_seasonality_explains_a_repeat_of_last_years_move() -> None:
    """T2 = revenue_prev * (LY_cur / LY_prev - 1) = 1,000 * (1,500 / 1,000 - 1)
    = +500, against a change of +500: share 1.0, supported. Daily rows, so the
    year-ago months pass T2's coverage check (3E1)."""
    data = run_data(daily_months(_seasonal(1000.0)))

    t2 = by_id(evaluate_hypotheses(step7(data)))["T2"]

    assert t2.contribution == pytest.approx(500.0)
    assert t2.share == pytest.approx(1.0)
    assert t2.verdict == "supported"


def test_a_tiny_year_ago_month_is_not_a_seasonal_base() -> None:
    """The 3D4/3D6 base guard, applied to T2. Last January took 12.50. Without
    the guard T2 = 1,000 * (1,500 / 12.50 - 1) = +119,000 - "seasonality
    explains 238 times the change", supported, and headline rule 5 would say
    so. 12.50 is under 3% of the typical month (1,000), so it is not a
    denominator and T2 is inconclusive."""
    data = run_data(full_months(_seasonal(12.5)))

    t2 = by_id(evaluate_hypotheses(step7(data)))["T2"]

    assert t2.verdict == "inconclusive"
    assert t2.contribution is None
    assert "base guard" in t2.rule


def test_seasonality_needs_the_year_ago_pair() -> None:
    """13 months, 2010-01 to 2011-01: the year-ago previous month (2009-12) is
    outside the file, so the pair is missing. (14 months would already hold
    it - the first version of this test used 14 and T2 correctly ran.)"""
    data = run_data(full_months(months([1000.0] * 12 + [800.0])))

    t2 = by_id(evaluate_hypotheses(step7(data)))["T2"]

    assert t2.verdict == "inconclusive"


# --- the share rule and D --------------------------------------------------------


SPEC = next(s for s in CATALOG if s.id == "B1")
QUIET = Changes(revenue_prev=1000.0, revenue_cur=800.0, net=-200.0, gross=-200.0, alert=False)


@pytest.mark.parametrize("contribution,verdict,share", [
    (-40.0, "supported", -0.20),    # exactly SUPPORTED_MIN_SHARE of 200
    (-39.0, "partial", -0.195),
    (-10.0, "partial", -0.05),      # exactly PARTIAL_MIN_SHARE
    (-9.0, "ruled_out", -0.045),
    (+120.0, "ruled_out", 0.60),    # large, but the opposite sign to the fall
])
def test_the_share_rule(contribution, verdict, share) -> None:
    """D = |change in revenue| = 200 with no alert. Supported needs the same
    sign as the change and |share| >= 0.20; partial >= 0.05."""
    got, got_share, _ = share_verdict(SPEC, contribution, SimpleNamespace(tree=None), QUIET)

    assert got == verdict
    assert got_share == pytest.approx(share)


def test_a_flat_total_has_nothing_to_explain() -> None:
    flat = Changes(1000.0, 1000.0, 0.0, 0.0, False)

    verdict, share, rule = share_verdict(SPEC, -300.0, SimpleNamespace(tree=None), flat)

    assert (verdict, share) == ("ruled_out", None)
    assert "did not move" in rule


def _tree(customers: float, frequency: float, aov: float, pair: tuple[float, float]):
    level1 = SimpleNamespace(factors=[SimpleNamespace(contribution=v)
                                      for v in (customers, frequency, aov)])
    lever = SimpleNamespace(level1=level1, level2=None, masked_shift_alert=True,
                            masked_shift_pair=SimpleNamespace(factors=[
                                SimpleNamespace(name="orders", contribution=pair[0]),
                                SimpleNamespace(name="aov", contribution=pair[1])]))
    return SimpleNamespace(lever=lever)


def test_under_the_alert_d_is_the_gross_of_the_contributions_own_split() -> None:
    """The decision 3D6b left open. The pair review's S6-like case: customers
    -1,283.3, frequency +756.7, AOV +366.7 (level 1, net -160); the pair
    orders -480, AOV +320. B1's contribution is frequency, +756.7.
      D = level-1 gross = 1,283.3 + 756.7 + 366.7 = 2,406.7 -> share +0.3144
      against the pair's gross (800) it would be +0.9459 - three times larger,
      and a split its numerator did not come from.
    The change is -160, so B1 (+) is the opposite sign: ruled_out either way,
    and the share is the level-1 one."""
    tree = _tree(-1283.3, 756.7, 366.7, (-480.0, 320.0))
    moved = Changes(1000.0, 840.0, -160.0, -160.0, True)

    verdict, share, rule = share_verdict(SPEC, 756.7, SimpleNamespace(tree=tree), moved)

    assert decomposition_gross(tree, "level1") == pytest.approx(2406.7)
    assert share == pytest.approx(756.7 / 2406.7)
    assert abs(share) <= 1.0
    assert "level1" in rule
    assert verdict == "ruled_out"


# --- requirements -----------------------------------------------------------------


def test_customer_hypotheses_are_not_testable_without_a_customer_column() -> None:
    mapping = {"Date": "transaction_date", "Qty": "quantity", "Price": "unit_price",
               "Product": "product_name"}
    rows = full_months(months([1000.0] * 25 + [800.0]))
    for r in rows:
        del r["Cust"]
    data = run_data(rows, mapping)

    results = by_id(evaluate_hypotheses(step7(data)))

    for hypothesis_id in ("C1", "C2", "C3", "C4", "B1"):
        assert results[hypothesis_id].verdict == "not_testable", hypothesis_id


def test_c4_counts_a_move_from_strong_to_weak_segments(monkeypatch) -> None:
    """Hand-built segments, all six present (C4 refuses otherwise). Previous:
    40 strong (Champions 20 + Loyal 20), 20 weak, 41 other = 101. Current: 30
    strong, 30 weak, 41 other = 101.
      weak share +10/101, strong share -10/101 -> unfavourable 2,000/101 =
      19.80 points >= C4_SUPPORT_POINTS (5) and revenue fell: supported.
    The same move while revenue ROSE cannot explain the change: ruled_out."""
    # The rule behind C4's v1 switch (3E1 cycle 3): pinned so it is right
    # when stage 2 anchors segments per month and the switch goes on.
    monkeypatch.setattr(customers_module, "SEGMENTS_ANCHORED_TO_THE_PERIOD", True)
    def seg(name, now, before):
        return SimpleNamespace(segment=name, customers=now, customers_previous=before)

    segments = [seg("Champions", 15, 20), seg("Loyal", 15, 20), seg("At-risk", 20, 10),
                seg("Hibernating", 10, 10), seg("New", 40, 40), seg("Needs Attention", 1, 1)]
    inputs = SimpleNamespace(
        data=SimpleNamespace(parsed=SimpleNamespace(reverse={"customer": "Cust"}),
                             metrics=SimpleNamespace(customers=SimpleNamespace(segments=segments))))

    fell = c4(inputs, Changes(1000.0, 800.0, -200.0, -200.0, False))
    rose = c4(inputs, Changes(1000.0, 1200.0, 200.0, 200.0, False))

    assert fell.evidence["unfavourable_points"] == pytest.approx(2000 / 101, abs=1e-4)
    assert fell.verdict == "supported"
    assert rose.verdict == "ruled_out"


# --- the trust gate -----------------------------------------------------------------


def test_a_blocked_run_evaluates_only_the_data_family() -> None:
    """CONTRACTS section 7: when trust blocks, every hypothesis outside the D
    family is inconclusive. A current month with one day of data in a shop
    that trades daily trips D1's block."""
    rows = []
    day = date(2011, 1, 1)
    while day <= date(2011, 11, 30):
        if day.month < 11 or day.day == 30:
            rows.append(row(day, qty=10, price=10.0))
        day += timedelta(days=1)
    data = run_data(rows)

    results = by_id(evaluate_hypotheses(step7(data)))

    assert data.metrics.period.current == "2011-11"
    assert results["D1"].verdict != "inconclusive"
    for spec in CATALOG:
        if spec.family != "data_quality":
            assert results[spec.id].verdict == "inconclusive", spec.id


# --- statements rendered from the data's direction (3E1) ---------------------


def test_a_statement_is_rendered_from_the_direction_the_data_moved() -> None:
    """The reviewer's reproduction. Alice buys one unit daily; in February 2011
    twenty new customers buy five units each. Revenue ROSE, 310 -> 1,280, and
    units per order rose from 1.0 to 2.67. The first version tested one-way
    statements with a sign-blind rule and headlined "baskets got smaller".
    Statements are now rendered from the sign of the contribution: whatever
    is supported says what the data did."""
    from datetime import date

    from stages.diagnose.headline import choose_headline
    from stages.diagnose.step7_inputs import changes
    from tests.stages.diagnose.diagnose_fixtures import daily_rows

    rows = daily_rows(date(2010, 1, 1), date(2011, 2, 28))
    rows += [row(date(2011, 2, 10 + (i % 10)), qty=5, price=10.0, customer=f"New{i}")
             for i in range(20)]
    inputs = step7(run_data(rows))

    results = evaluate_hypotheses(inputs)
    verdicts = by_id(results)
    headline = choose_headline(inputs.trust, results, inputs.tree, changes(inputs))

    assert verdicts["C1"].statement == "New customers brought in more revenue"
    assert verdicts["B2"].statement == "Lines carried more units"  # lines wording (2E-e, Thach): no order_id mapped here
    wrong_way = ("less revenue", "smaller", "less often", "weaker", "cheaper", "more revenue away")
    for hypothesis in results:
        if hypothesis.verdict in ("supported", "partial"):
            assert not any(phrase in hypothesis.statement for phrase in wrong_way), hypothesis
    assert "smaller" not in headline.message and "less often" not in headline.message


def test_a_hypothesis_with_no_number_keeps_its_neutral_statement() -> None:
    """Inconclusive and not_testable carry no contribution, so there is no
    direction to render: the neutral tested statement is shown. Two months:
    there is no transition before the previous one, so C1 is inconclusive."""
    data = run_data(full_months(months([1000.0, 800.0])))

    c1 = by_id(evaluate_hypotheses(step7(data)))["C1"]

    assert c1.verdict == "inconclusive"
    assert c1.statement == "New-customer revenue changed"


def test_every_term_and_only_a_term_has_a_decomposition_for_d() -> None:
    """D under the alert is a term's own split (7.8). An expectation mapped
    there would have its overshoot hidden (F4); a term left out would crash
    on the alert."""
    from stages.diagnose.catalog import CATALOG
    from stages.diagnose.hypotheses import DECOMPOSITION

    assert set(DECOMPOSITION) == {spec.id for spec in CATALOG if spec.kind == "term"}
