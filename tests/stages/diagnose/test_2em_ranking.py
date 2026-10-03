"""Session 2E-m (Thach, 2026-09-27, after the third overnight run), written
before the change.

(a) Headline rule 6 RANKS every supported cause by its share of the NET
    change the headline states - superseding 3E1's per-lens share, under
    which a product-lens cause (a share of the GROSS change) beat a larger
    returns-lens cause "only because its denominator is smaller". Verdicts
    keep their own lens totals.
One definition of "the share of the change that sits in the products": the
net change of the products over the total net change - breadth's, read by
R1 and by the D8 gate alike (2E-l's gate read gross over net: 62% where
breadth read 7% on one month).

Both shops: seven products P0-P6 at 10, one unit a day each, March to
August; the current month is August, 31 days like July.
"""

from datetime import date

import pandas as pd
import pytest
from pydantic import ValidationError

from contracts.diagnosis import Breadth, DiagnosisContract, Hypothesis
from stages.diagnose.catalog import CATALOG, HypothesisSpec
from stages.diagnose.headline import choose_headline
from stages.diagnose.localization import products_hold_the_change
from stages.diagnose.step7_inputs import Changes, changes
from tests.contracts.test_diagnosis import diagnosis_payload
from tests.stages.diagnose.test_2el_review1 import COLUMNS, _days, _run
from tests.stages.diagnose.test_headline import MOVED, catalog, tree, trust


def _shop(p0_price: str, p0_days: int, refunds_july: int, refunds_august: int,
          discounts_august: int, p7_july_days: int = 0) -> pd.DataFrame:
    """In August P0 sells at `p0_price` on its first `p0_days` days; P3 is
    refunded -1 @ 5 on the first `refunds_*` days of July / August; a
    discount line -1 @ 5 on the first `discounts_august` days of August; P7,
    1 @ 10, on the first `p7_july_days` days of July only (discontinued)."""
    rows, i = [], 0
    for day in _days():
        august, july = day.month == 8, day.month == 7
        for k in range(7):
            price = p0_price if (august and k == 0 and day.day <= p0_days) else "10"
            rows.append((day.isoformat(), f"C{i % 12}", f"P{k}", f"PRODUCT {k}", "1", price))
            i += 1
        if (july and day.day <= refunds_july) or (august and day.day <= refunds_august):
            rows.append((day.isoformat(), f"C{i % 12}", "P3", "PRODUCT 3", "-1", "5"))
            i += 1
        if july and day.day <= p7_july_days:
            rows.append((day.isoformat(), f"C{i % 12}", "P7", "PRODUCT 7", "1", "10"))
            i += 1
        if august and day.day <= discounts_august:
            rows.append((day.isoformat(), f"C{i % 12}", "D", "Discount", "-1", "5"))
            i += 1
    rows.append((date(2026, 9, 1).isoformat(), "C1", "P1", "PRODUCT 1", "1", "10"))
    return pd.DataFrame(rows, columns=COLUMNS)


def _ranked(df, classes):
    """The ranking alone: these shops' planted changes sit inside a flat
    shop's own days-in-month movement, so the size gate (tested in
    test_3e1b_headline_gate.py and test_3e1b_size_note.py) would keep
    every cause out - since their history became long enough to measure it
    (Thach, 2026-10-03, decision 5). A Changes with no movement is ungated."""
    from dataclasses import replace

    inputs, results, _ = _run(df, classes)
    headline = choose_headline(inputs.trust, list(results.values()), inputs.tree,
                               replace(changes(inputs), movement=None))
    return inputs, results, headline


def test_rule_6_ranks_by_the_share_of_the_net_change() -> None:
    # P0 at 6 on 10 days: P1 = -40; P7 sold 3 days in July only: R2 = -30;
    # gross 2,200 -> 2,130 (-70). 12 refunds at 5 in August: P3 = -60. Net
    # 2,200 -> 2,070 (-130). Gross is 54% of it and the products carry all of
    # it, so the gate is open under either reading.
    inputs, results, headline = _ranked(_shop("6", 10, 0, 12, 0, p7_july_days=3), {})

    # P1 is 40 of 70 gross (0.57) but 40 of 130 net (0.31); P3 is 60 of 130.
    assert (results["P1"].verdict, results["P1"].contribution, results["P1"].share) == (
        "supported", pytest.approx(-40.0), pytest.approx(-40 / 70))
    assert (results["P3"].verdict, results["P3"].contribution) == ("supported", pytest.approx(-60.0))
    assert results["R2"].contribution == pytest.approx(-30.0)
    # 46% of the net change beats 31% of it; before, P1's 57% of gross won.
    assert (headline.rule, headline.hypothesis_id) == (6, "P3")
    assert changes(inputs).products_hold_the_change is True


def test_the_gate_reads_the_products_share_as_breadth_does() -> None:
    # P0 at 2 on 10 days: gross -80, P1 = -80; July's 9 refunds of P3 do not
    # recur: +45; 13 discount lines in August: P4 = -65. Net 2,125 -> 2,025
    # (-100). The products' SALES carry -80 of it, 80% (Thach, 2E-n: reading
    # G - the refunds that stopped are the returns class, P3's). Under 2E-m's
    # reading, the products' net change -80 + 45 = 35%, the gate closed and
    # P4 was named; P1 is the closer cause (0.80 against 0.65).
    inputs, results, headline = _ranked(_shop("2", 10, 9, 0, 13), {"D": "discount"})

    breadth = inputs.localization.breadth
    assert breadth.products_share_of_change == pytest.approx(0.80)
    assert breadth.classification != "outside_products"
    assert changes(inputs).products_hold_the_change is True
    assert (results["P1"].verdict, results["P1"].contribution) == ("supported", pytest.approx(-80.0))
    assert results["P4"].contribution == pytest.approx(-65.0)
    assert (headline.rule, headline.hypothesis_id) == (6, "P1")


def _headline(holds: bool) -> tuple[int, str | None]:
    """P1 explains all of a -200 change; only the products' share decides."""
    hypotheses = [Hypothesis(id=spec.id, family=spec.family, lens=spec.lens, statement=spec.statement,
                             verdict="supported" if spec.id == "P1" else "ruled_out",
                             contribution=-200.0 if spec.id == "P1" else None,
                             share=-1.0 if spec.id == "P1" else None, evidence={}, rule="test")
                  for spec in CATALOG]
    moved = Changes(revenue_prev=1000.0, revenue_cur=800.0, net=-200.0, gross=-200.0, alert=False,
                    products_hold_the_change=holds)
    headline = choose_headline(trust(), hypotheses, None, moved)
    return headline.rule, headline.hypothesis_id


def test_a_product_lens_cause_needs_the_products_to_hold_the_change() -> None:
    # Gross equals net here: 2E-l's gross test would open the gate.
    assert _headline(True) == (6, "P1")
    assert _headline(False) == (7, None)


@pytest.mark.parametrize(("classification", "share", "holds"), [
    ("concentrated", 0.9, True), ("broad", 0.51, True),
    ("outside_products", 0.5, False),
    # A flat month has no share: it holds nothing (breadth says "mixed").
    ("mixed", None, False),
])
def test_the_gate_reads_breadths_decision(classification: str, share: float | None, holds: bool) -> None:
    breadth = Breadth(declining_base_share=0.0, top_member_share=0.0, classification=classification,
                      products_share_of_change=share)

    assert products_hold_the_change(breadth) is holds


def test_terms_that_both_overshoot_the_change_rank_by_how_close_they_come() -> None:
    # Both past the change: P1 -240 (1.20x, fit 0.80) and P2 -270 (1.35x,
    # fit 0.65) of -200. 3E1's cap scored both 1, catalog order named P1 and
    # 2E-m's D1 then named the larger share (P2); one fit measure for every
    # cause names the closer (Thach, 2E-n: D1 superseded).
    headline = choose_headline(trust(), catalog(P1=("supported", -1.20, {}), P2=("supported", -1.35, {})),
                               tree(False), MOVED)

    assert headline.hypothesis_id == "P1"


def test_an_exact_expectation_beats_overshooting_terms() -> None:
    # C1 explains the change exactly (fit 1); B1 at 1.5 and P2 at 1.35 fit
    # 0.5 and 0.65 - an overshoot never beats an exact explanation (3E1),
    # now by the one fit measure rather than a cap and a tie.
    headline = choose_headline(trust(), catalog(C1=("supported", -1.00, {}), B1=("supported", -1.50, {}),
                                                P2=("supported", -1.35, {})), tree(False), MOVED)

    assert headline.hypothesis_id == "C1"


# --- review cycle 1 --------------------------------------------------------

def _share(spec: HypothesisSpec, contribution: float | None, moved: Changes) -> float | None:
    """The share its verdict stores (hypotheses.share_verdict): of |gross|
    for the product lens, of |net| otherwise."""
    if contribution is None:
        return None
    return contribution / abs(moved.gross if spec.lens == "product" else moved.net)


def _supported(moved: Changes, **causes: float | None) -> str | None:
    """Every catalog cause ruled out except `causes`: id -> contribution
    (None: directional), each with the share its verdict would store."""
    hypotheses = [Hypothesis(id=spec.id, family=spec.family, lens=spec.lens, statement=spec.statement,
                             verdict="supported" if spec.id in causes else "ruled_out",
                             contribution=causes.get(spec.id), share=_share(spec, causes.get(spec.id), moved),
                             evidence={}, rule="test") for spec in CATALOG]
    return choose_headline(trust(), hypotheses, tree(False), moved).hypothesis_id


def test_a_directional_cause_comes_before_the_movements_of_a_share_cause_far_past_the_change() -> None:
    # R3 is judged against gross (-3,000: 100%, supported) but ranked against
    # net (-900): 3.33 times the change, no positive fit (Thach, 2E-n). A
    # supported directional cause is named before the movements, which are
    # the last resort (Thach, 2E-o Q4, reversing 3E1's order here; it was
    # "the movements before a directional cause" in 2E-m review cycle 1 #2).
    moved = Changes(revenue_prev=10000.0, revenue_cur=9100.0, net=-900.0, gross=-3000.0, alert=False)

    assert _supported(moved, R3=-3000.0, R1=None) == "R1"
    assert _supported(moved, R3=-2700.0, C4=None) == "C4"
    hypotheses = [Hypothesis(id=spec.id, family=spec.family, lens=spec.lens, statement=spec.statement,
                             verdict="supported" if spec.id in ("R3", "R1") else "ruled_out",
                             contribution=-3000.0 if spec.id == "R3" else None,
                             share=-1.0 if spec.id == "R3" else None, evidence={}, rule="test")
                  for spec in CATALOG]
    message = choose_headline(trust(), hypotheses, tree(False), moved).message
    assert "movements in opposite directions" not in message
    assert "The best-supported explanation: " in message


def test_the_ranking_reads_the_share_of_the_net_change_not_the_verdicts_share() -> None:
    # Gross -100, net -200: B1 -300 (1.5 of net, fit 0.5) and P2 -270 (1.35
    # of net, fit 0.65; 2.7 of gross, the share its verdict stores - which
    # would fit 0) (#4).
    moved = Changes(revenue_prev=1000.0, revenue_cur=800.0, net=-200.0, gross=-100.0, alert=False)

    assert _supported(moved, B1=-300.0, P2=-270.0) == "P2"
    # Equal shares of the net change: an exact tie names both, no single id
    # (Thach, 2E-n: never catalog order).
    assert _supported(moved, P1=-240.0, P2=-240.0) is None


def test_an_exact_term_is_not_beaten_by_an_overshooting_one() -> None:
    # B1 explains the -200 exactly (fit 1); P2 at 1.35 fits 0.65 (#5; 3E1).
    assert _supported(MOVED, B1=-200.0, P2=-270.0) == "B1"


def test_diagnosis_json_is_major_12_or_the_current_one_and_refuses_an_11_file() -> None:
    # The same data can name a different cause (Online Retail II 2010-03: T1
    # under 11.0, R2 since 12.0) - a change of meaning, a major bump
    # (CONTRACTS 10). 12.0 in 2E-m; 13.0 in 2E-n; 14.0 in 2E-i; 15.0 since 2E-j.
    payload = diagnosis_payload()
    assert DiagnosisContract.supported_major == 18  # 18 since 3E1b; 17 since 2E-t2 (the line taxonomy)
    assert DiagnosisContract.model_validate(payload).schema_version == "18.0"

    payload["schema_version"] = "11.0"
    with pytest.raises(ValidationError, match="re-analyse"):
        DiagnosisContract.model_validate(payload)


def test_a_term_equal_to_the_change_up_to_residue_is_not_past_it() -> None:
    # 800.1 - 1000.3 is -200.19999999999993 in binary: B1 at -200.20, exact to
    # the cent, fits the change (2E-m review cycle 2; since 2E-n no tie among
    # overshooting terms needs it).
    moved = Changes(revenue_prev=1000.3, revenue_cur=800.1, net=800.1 - 1000.3, gross=800.1 - 1000.3, alert=False)

    assert _supported(moved, B1=-200.20, P2=-270.0) == "B1"
