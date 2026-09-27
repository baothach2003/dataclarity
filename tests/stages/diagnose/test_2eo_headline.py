"""Session 2E-o (Thach, 2026-09-28, answering the fifth run's report),
written before the change.

Q1 rules 5 and 6 are ranked together under the one fit measure: a context
    cause (the calendar T1, seasonality T2) no longer wins by coming first -
    the closest positive fit wins, whatever rule it belongs to. Kaggle's
    headline moves from T2 at 1.48x (fit 0.52) to B1 at 0.96x (fit 0.96).
Q4 a supported directional cause (a directional R1) comes before the
    movements sentence, which is the last resort.
"""

from stages.diagnose.headline import CONTEXT
from tests.stages.diagnose.test_2en_headline import _headline, _moved

# Kaggle 2024-12: 41,367.50 -> 46,292.50 (+4,925.00).
KAGGLE = _moved(41_367.50, 46_292.50)


def test_a_context_cause_no_longer_wins_by_coming_first() -> None:
    """T2 +7,289 (1.48x, fit 0.52) against B1 +4,728 (0.96x, fit 0.96): the
    closer fit is named (Thach's Q1)."""
    headline = _headline(KAGGLE, T2=("supported", 7_289.0), B1=("supported", 4_728.0))

    assert (headline.rule, headline.hypothesis_id) == (6, "B1")
    assert "96% of the change" in headline.message


def test_a_context_cause_that_fits_best_keeps_rule_5s_words() -> None:
    headline = _headline(KAGGLE, T2=("supported", 4_900.0), B1=("supported", 6_000.0))

    assert headline.rule == 5
    assert headline.message.endswith(f"The change is consistent with {CONTEXT['T2']}: 99% of the change.")


def test_a_tie_across_the_two_rules_names_both_in_rule_6s_words() -> None:
    """0.9x and 1.1x land equally far from the change: an exact tie names
    every tied cause, never one by the order of the rules."""
    headline = _headline(_moved(1_000.0, 2_000.0), T2=("supported", 900.0), B1=("supported", 1_100.0))

    assert (headline.rule, headline.hypothesis_id) == (6, None)
    assert headline.message.startswith("Revenue went from 1,000.00 to 2,000.00 (+1,000.00). Equally well supported: ")
    assert "(time lens, 90% of the change)" in headline.message
    assert "(lever lens, +1,100.00 against the change of +1,000.00)" in headline.message


def test_two_context_causes_tied_keep_rule_5() -> None:
    headline = _headline(_moved(1_000.0, 2_000.0), T1=("supported", 900.0), T2=("supported", 1_100.0))

    assert headline.rule == 5
    assert "; and equally with " in headline.message


def test_a_supported_directional_cause_comes_before_the_movements() -> None:
    """P1 at 3x fits nothing; R1 is supported with no number (directional):
    it is named, and the movements sentence stays the last resort (Q4)."""
    headline = _headline(_moved(1_000.0, 900.0), P1=("supported", -300.0), R1=("supported", None))

    assert (headline.rule, headline.hypothesis_id) == (6, "R1")
    assert "movements in opposite directions" not in headline.message


def test_the_movements_remain_when_nothing_supported_fits() -> None:
    headline = _headline(_moved(1_000.0, 900.0), P1=("supported", -300.0), P2=("ruled_out", 200.0))

    assert headline.rule == 6 and headline.hypothesis_id is None
    assert "movements in opposite directions" in headline.message


# --- Q5 #1: the movements sentence ----------------------------------------------------


def _signed(moved, **causes):
    """As `_headline`, with each statement rendered from its sign as stage 3
    renders it (hypotheses._make)."""
    from contracts.diagnosis import Hypothesis
    from stages.diagnose.catalog import CATALOG
    from stages.diagnose.headline import choose_headline
    from tests.stages.diagnose.test_headline import tree, trust

    hypotheses = []
    for spec in CATALOG:
        verdict, contribution = causes.get(spec.id, ("ruled_out", None))
        sign = 0 if contribution is None else (1 if contribution > 0 else -1)
        total = abs(moved.gross if spec.lens == "product" else moved.net)
        hypotheses.append(Hypothesis(
            id=spec.id, family=spec.family, lens=spec.lens, statement=spec.render(sign, "order_id"),
            verdict=verdict, contribution=contribution,
            share=None if contribution is None else contribution / total, evidence={}, rule="test"))
    return choose_headline(trust(), hypotheses, tree(False), moved)


def test_fewer_refunds_read_as_fewer_refunds() -> None:
    """Online Retail II 2011-07 unanswered: refunds fell 70,616.78 ->
    37,921.08 (P3 +32,695.70) and the sentence read "up, returns changed" -
    as if returns rose (Q5 #1). The words carry the direction."""
    headline = _signed(_moved(691_123.12, 681_300.11), P2=("supported", -26_932.24),
                       P3=("ruled_out", 32_695.70))

    assert "up, returns took less revenue away (returns lens, +32,695.70)" in headline.message
    assert "down, sales mix shifted towards cheaper products (product lens, -26,932.24)" in headline.message


def test_the_movements_named_are_among_them_not_all_of_it() -> None:
    """-26,932.24 and +32,695.70 add to +5,763.46 beside a -9,823.01 change:
    the two named are the largest measured each way, not the whole change."""
    headline = _signed(_moved(691_123.12, 681_300.11), P2=("supported", -26_932.24),
                       P3=("ruled_out", 32_695.70))

    assert "The change is what remains of movements in opposite directions, among them: down, " in headline.message
