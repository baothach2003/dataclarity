"""Thach, 2026-10-04, on the fifteenth report - written before the code (the sixteenth run's stage 5
review, findings 3 and 4). (vii) "Moved against the change" is stage 3's own sign test, stated once - here
- and written into diagnosis.json, so stage 5 and the page print it from one source and never re-derive it
from another total. (vi) Rule 2's table keeps one line saying the missing days affect the verdicts below:
stage 3's table note, so report.html and the page print the same words."""

from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from contracts.diagnosis import Headline, Hypothesis
from stages.diagnose.catalog import BY_ID
from stages.diagnose.hypotheses import evaluate_hypotheses, share_verdict
from stages.diagnose.step7_inputs import Changes

B1, P1 = BY_ID["B1"], BY_ID["P1"]
FELL = Changes(revenue_prev=1000.0, revenue_cur=800.0, net=-200.0, gross=-200.0, alert=False)
GROSS_ROSE = Changes(1000.0, 800.0, -200.0, 100.0, False)


@pytest.mark.parametrize("spec,contribution,moved,against", [
    (B1, 120.0, FELL, True),        # large, the opposite sign to the fall: ruled out against it
    (B1, -9.0, FELL, False),        # ruled out for its size, the same sign
    (B1, -40.0, FELL, False),       # supported
    (B1, 0.0, FELL, False),         # no movement is not "against"
    (P1, 50.0, GROSS_ROSE, False),  # the product lens is measured on gross sales, which rose
    (P1, -50.0, GROSS_ROSE, True),  # ... so a fall moved against it, though revenue fell too
])
def test_against_is_the_share_rules_own_sign_test(spec, contribution, moved, against) -> None:
    from stages.diagnose.hypotheses import against_the_change

    verdict, share, _ = share_verdict(spec, contribution, SimpleNamespace(tree=None), moved)

    assert against_the_change(spec, contribution, moved) is against
    if against:
        assert (verdict, share is not None) == ("ruled_out", True)


def test_nothing_measured_is_never_against() -> None:
    # No gross for the product lens, or a total that did not move: share_verdict measures no share.
    from stages.diagnose.hypotheses import against_the_change

    assert against_the_change(P1, -50.0, Changes(1000.0, 800.0, -200.0, None, False)) is False
    flat = Changes(1000.0, 1000.0, 0.0, 0.0, False)
    assert share_verdict(B1, 300.0, SimpleNamespace(tree=None), flat)[1] is None
    assert against_the_change(B1, 300.0, flat) is False


def test_every_run_writes_it_for_a_measured_share_only() -> None:
    from stages.diagnose.step7_inputs import changes
    from tests.stages.diagnose.diagnose_fixtures import full_months, run_data
    from tests.stages.diagnose.test_hypotheses import step7
    from tests.stages.diagnose.test_rule_one_reliability import months

    # 25 months of 100 units at 10, then 50 at 16: revenue -200, and P1 (price, measured on gross) +450 -
    # against the fall.
    by_month = months([1000.0] * 26)
    last = list(by_month)[-1]
    rows = full_months({m: v for m, v in by_month.items() if m != last}) + full_months({last: 800.0}, price=16.0)
    inputs = step7(run_data(rows))
    moved = changes(inputs)
    results = evaluate_hypotheses(inputs)

    for h in results:
        total = moved.gross if h.lens == "product" else moved.net
        expected = (h.share is not None and h.contribution is not None and h.contribution != 0
                    and (h.contribution > 0) != (total > 0))
        assert h.against_the_change is expected, h.id
    assert [h.id for h in results if h.against_the_change] == ["P1"]


def test_no_share_measured_is_never_against(monkeypatch) -> None:
    # share_verdict's "D = ... is zero" branch measures no share (review 2, #4): the flag needs a share.
    import stages.diagnose.hypotheses as module
    from tests.stages.diagnose.diagnose_fixtures import full_months, run_data
    from tests.stages.diagnose.test_hypotheses import step7
    from tests.stages.diagnose.test_rule_one_reliability import months

    by_month = months([1000.0] * 26)
    last = list(by_month)[-1]
    rows = full_months({m: v for m, v in by_month.items() if m != last}) + full_months({last: 800.0}, price=16.0)
    monkeypatch.setattr(module, "share_verdict", lambda *args: ("ruled_out", None, "D = gross of level1 is zero"))

    assert not any(h.against_the_change for h in evaluate_hypotheses(step7(run_data(rows))))


def test_the_contract_refuses_against_where_the_sign_test_could_not_say_it() -> None:
    base = dict(id="B1", family="customer_behavior", lens="customers", statement="s", verdict="ruled_out",
                contribution=120.0, share=0.6, evidence={}, rule="r")

    assert Hypothesis(**base, against_the_change=True).against_the_change is True
    assert Hypothesis(**base).against_the_change is False  # 18.2's files: absent, never claimed
    for wrong in (dict(verdict="supported"), dict(share=None), dict(contribution=None), dict(contribution=0.0)):
        with pytest.raises(ValidationError, match="against"):
            Hypothesis(**{**base, **wrong, "against_the_change": True})


def test_rule_2s_table_carries_the_missing_days_line() -> None:
    from stages.diagnose.headline import GAPS_NOTE, choose_headline, hypotheses_note
    from tests.stages.diagnose.test_3e1b_headline_gate import INSIDE, _all, _h, _moved, _trust

    gaps = choose_headline(_trust(), _all(_h("D1", "supported", 12.0, 1.0)), None, _moved(INSIDE))

    assert gaps.rule == 2
    # The headline names no particular day, only "days that have no sales at all" (review 2, #11).
    assert hypotheses_note(gaps) == GAPS_NOTE == (
        "The days with no sales at all affect the verdicts below: each measures a change that includes them.")
    assert hypotheses_note(gaps.model_copy(update={"movement": None})) == GAPS_NOTE
    for rule in (1, 3, 4):
        assert hypotheses_note(Headline(rule=rule, hypothesis_id=None, lens=None, message="m",
                                        movement=INSIDE)) is None
