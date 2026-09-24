"""Step 7's headline rules, one test per rule, first match wins
(docs/AI_PIPELINE.md 7.8). Hypotheses are hand-built from the catalog so each
rule is exercised in isolation and every number in a message is known."""

from types import SimpleNamespace

import pytest

from contracts.diagnosis import Hypothesis
from stages.diagnose.catalog import CATALOG
from stages.diagnose.headline import choose_headline
from stages.diagnose.step7_inputs import Changes

MOVED = Changes(revenue_prev=1000.0, revenue_cur=800.0, net=-200.0, gross=-200.0, alert=False)


def catalog(**overrides) -> list[Hypothesis]:
    """Every catalog id ruled_out with no share, except the overrides, given as
    id=(verdict, share, evidence)."""
    result = []
    for spec in CATALOG:
        verdict, share, evidence = overrides.get(spec.id, ("ruled_out", None, {}))
        result.append(Hypothesis(id=spec.id, family=spec.family, lens=spec.lens,
                                 statement=spec.statement, verdict=verdict,
                                 # share = contribution / D, D = |MOVED.net| = 200
                                 contribution=None if share is None else share * 200.0,
                                 share=share, evidence=evidence, rule="test"))
    return result


def trust(verdict: str = "trusted", message: str = "ok"):
    status = "blocked" if verdict == "blocked" else "ok"
    return SimpleNamespace(verdict=verdict, checks=[SimpleNamespace(status=status, message=message)])


def tree(alert: bool, orders: float = 0.0, aov: float = 0.0):
    pair = SimpleNamespace(factors=[SimpleNamespace(name="orders", contribution=orders),
                                    SimpleNamespace(name="aov", contribution=aov)])
    return SimpleNamespace(lever=SimpleNamespace(masked_shift_alert=alert, masked_shift_pair=pair))


def test_rule_1_a_blocked_run_states_the_data_problem() -> None:
    headline = choose_headline(trust("blocked", "29 of 30 days have no rows."),
                               catalog(), None, MOVED)

    assert headline.rule == 1
    assert "29 of 30 days have no rows." in headline.message


def test_rule_2_missing_days_explain_most_of_the_change() -> None:
    hypotheses = catalog(D1=("supported", -0.60, {"estimated_revenue_gap": 120.0}))

    headline = choose_headline(trust(), hypotheses, tree(False), MOVED)

    assert headline.rule == 2
    assert "120.00" in headline.message


def test_rule_2_needs_half_the_change_not_just_supported() -> None:
    """Supported at 0.40 is not "most of the change": HEADLINE_CONTEXT_MIN_SHARE
    is 0.50. The headline falls through to rule 6, naming D1."""
    hypotheses = catalog(D1=("supported", -0.40, {"estimated_revenue_gap": 80.0}))

    headline = choose_headline(trust(), hypotheses, tree(False), MOVED)

    assert (headline.rule, headline.hypothesis_id) == (6, "D1")


def test_rule_3_is_dormant_because_t3_is_never_supported() -> None:
    """ADR-0007. The rule is kept for the Backlog's unusualness verdicts: a
    hand-built T3 `supported` still reaches it, which pins its place in the
    order; the engine never produces one (test_hypotheses)."""
    assert choose_headline(trust(), catalog(), tree(False), MOVED).rule == 7
    assert choose_headline(trust(), catalog(T3=("supported", None, {})), tree(False),
                           MOVED).rule == 3


def test_rule_4_states_the_real_change_beside_the_pair_and_is_hedged() -> None:
    """ADR-0007 and 3D6b: the alert never says "stable" without the real net
    change, names the orders x AOV pair, and always says "may be seasonal"."""
    moved = Changes(1000.0, 840.0, -160.0, -160.0, True)

    headline = choose_headline(trust(), catalog(), tree(True, -480.0, 320.0), moved)

    assert headline.rule == 4
    assert "1,000.00 to 840.00 (-160.00)" in headline.message
    assert "orders contributed -480.00" in headline.message
    assert "average order value +320.00" in headline.message
    assert headline.message.endswith("This may be seasonal.")
    assert headline.hypothesis_id is None


def test_rule_4_outranks_a_supported_hypothesis() -> None:
    hypotheses = catalog(C2=("supported", -0.9, {}))

    headline = choose_headline(trust(), hypotheses, tree(True, -480.0, 320.0), MOVED)

    assert headline.rule == 4


@pytest.mark.parametrize("t1,t2,expected_word", [
    (("supported", -0.70, {}), ("supported", -0.55, {}), "calendar"),
    (("supported", -0.52, {}), ("supported", -0.80, {}), "seasonality"),
])
def test_rule_5_the_larger_context_share_wins(t1, t2, expected_word) -> None:
    headline = choose_headline(trust(), catalog(T1=t1, T2=t2), tree(False), MOVED)

    assert headline.rule == 5
    assert expected_word in headline.message


def test_rule_5_needs_half_the_change() -> None:
    headline = choose_headline(trust(), catalog(T2=("supported", -0.45, {})),
                               tree(False), MOVED)

    assert (headline.rule, headline.hypothesis_id) == (6, "T2")


def test_rule_6_names_the_largest_supported_share_and_its_lens() -> None:
    hypotheses = catalog(C2=("supported", -0.30, {}), P2=("supported", -0.45, {}),
                         D3=("supported", None, {}))

    headline = choose_headline(trust(), hypotheses, tree(False), MOVED)

    assert (headline.rule, headline.hypothesis_id, headline.lens) == (6, "P2", "product")
    assert "45% of the change" in headline.message


def test_rule_6_ranks_a_directional_finding_after_every_share() -> None:
    """A directional hypothesis has no share to compare, so it names the
    headline only when nothing with a share is supported."""
    alone = choose_headline(trust(), catalog(R1=("supported", None, {})), tree(False), MOVED)
    beaten = choose_headline(trust(), catalog(R1=("supported", None, {}),
                                              R2=("supported", -0.21, {})), tree(False), MOVED)

    assert (alone.rule, alone.hypothesis_id) == (6, "R1")
    assert beaten.hypothesis_id == "R2"


def test_rule_7_invents_no_cause_and_lists_the_partial_ones() -> None:
    hypotheses = catalog(C2=("partial", -0.10, {}), P3=("partial", -0.06, {}))

    headline = choose_headline(trust(), hypotheses, tree(False), MOVED)

    assert headline.rule == 7
    assert headline.hypothesis_id is None
    assert "No single tested cause explains most of the change." in headline.message
    assert "(C2)" in headline.message and "(P3)" in headline.message


def test_rule_3_yields_to_an_alert_even_if_t3_were_supported() -> None:
    """7.8 rule 3 is "T3 supported AND no masked-shift alert". A routine total
    with a masked shift under it is not routine; the alert's rule 4 speaks
    (mutation check: the "no alert" half was unpinned)."""
    moved = Changes(1000.0, 1000.0, 0.0, 0.0, True)

    headline = choose_headline(trust(), catalog(T3=("supported", None, {})),
                               tree(True, -300.0, 300.0), moved)

    assert headline.rule == 4


def test_rule_5_prefers_the_closer_expectation_even_when_it_comes_second() -> None:
    """Fit, not |share| capped at 1: T1 at 1.30 overshoots by 30% (fit 0.70),
    T2 at 0.90 falls 10% short (fit 0.90). Capping both at 1 ties them at
    (1.00, 0.90) the wrong way round and would name T1, the worse fit."""
    headline = choose_headline(trust(), catalog(T1=("supported", -1.30, {}),
                                                T2=("supported", -0.90, {})), tree(False), MOVED)

    assert headline.rule == 5
    assert "seasonality" in headline.message


def test_rule_6_caps_a_term_so_an_exact_expectation_is_not_beaten_by_an_overshoot() -> None:
    """A term's share of the NET change can exceed 1 when other terms offset
    it: B1 at 1.50. Its fit is capped at 1, level with C1 explaining the
    change exactly, and the tie goes to catalog order (C1 first). Uncapped,
    the overshooting term would outrank the exact explanation."""
    headline = choose_headline(trust(), catalog(C1=("supported", -1.00, {}),
                                                B1=("supported", -1.50, {})), tree(False), MOVED)

    assert headline.hypothesis_id == "C1"
