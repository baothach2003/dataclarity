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


def test_rule_6_ranks_by_the_share_of_the_net_change() -> None:
    # P0 at 6 on 10 days: P1 = -40; P7 sold 3 days in July only: R2 = -30;
    # gross 2,200 -> 2,130 (-70). 12 refunds at 5 in August: P3 = -60. Net
    # 2,200 -> 2,070 (-130). Gross is 54% of it and the products carry all of
    # it, so the gate is open under either reading.
    inputs, results, headline = _run(_shop("6", 10, 0, 12, 0, p7_july_days=3), {})

    # P1 is 40 of 70 gross (0.57) but 40 of 130 net (0.31); P3 is 60 of 130.
    assert (results["P1"].verdict, results["P1"].contribution, results["P1"].share) == (
        "supported", pytest.approx(-40.0), pytest.approx(-40 / 70))
    assert (results["P3"].verdict, results["P3"].contribution) == ("supported", pytest.approx(-60.0))
    assert results["R2"].contribution == pytest.approx(-30.0)
    # 46% of the net change beats 31% of it; before, P1's 57% of gross won.
    assert (headline.rule, headline.hypothesis_id) == (6, "P3")
    assert changes(inputs).products_hold_the_change is True


def test_the_gate_reads_the_products_net_change_as_breadth_does() -> None:
    # P0 at 2 on 10 days: gross -80, P1 = -80; July's 9 refunds of P3 do not
    # recur: +45; 13 discount lines in August: P4 = -65. Net 2,125 -> 2,025
    # (-100). Gross is 80% of it, but the products' net change is -80 + 45 =
    # -35: 35%, not more than half.
    inputs, results, headline = _run(_shop("2", 10, 9, 0, 13), {"D": "discount"})

    breadth = inputs.localization.breadth
    assert breadth.products_share_of_change == pytest.approx(0.35)
    assert (breadth.classification, results["R1"].verdict) == ("outside_products", "ruled_out")
    assert changes(inputs).products_hold_the_change is False
    assert (results["P1"].verdict, results["P1"].contribution) == ("supported", pytest.approx(-80.0))
    assert results["P4"].contribution == pytest.approx(-65.0)
    # Before: gross over net (80%) opened the gate and P1 (0.8) was named.
    assert (headline.rule, headline.hypothesis_id) == (6, "P4")


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


def test_terms_that_both_overshoot_the_change_rank_by_their_share_of_it() -> None:
    # Online Retail II 2011-07 unanswered: P1 -23.8k and P2 -26.8k on a net
    # change of -9.8k - both past the change, both capped at a fit of 1. The
    # tie went to catalog order and named the SMALLER cause (P1); among terms
    # the larger share of the net change decides (Thach, 2E-m). Here P1 is
    # -240 and P2 -270 of -200.
    headline = choose_headline(trust(), catalog(P1=("supported", -1.20, {}), P2=("supported", -1.35, {})),
                               tree(False), MOVED)

    assert headline.hypothesis_id == "P2"


def test_an_overshooting_term_still_ties_an_exact_expectation_to_catalog_order() -> None:
    # 3E1's cap, kept: B1 at 1.5 and P2 at 1.35 do not beat C1 explaining the
    # change exactly - a tie with an expectation goes to catalog order.
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


def test_a_supported_expectation_far_past_the_change_still_ranks_before_a_directional_cause() -> None:
    # R3 is judged against gross (-3,000: 100%, supported) but ranked against
    # net (-900): 3.33 times the change, so min(size, 2 - size) is -1.33 -
    # below a directional cause's -1. Every share cause ranks first (#2).
    moved = Changes(revenue_prev=10000.0, revenue_cur=9100.0, net=-900.0, gross=-3000.0, alert=False)

    assert _supported(moved, R3=-3000.0, R1=None) == "R3"
    assert _supported(moved, R3=-2700.0, C4=None) == "R3"


def test_the_tie_among_terms_reads_the_share_of_the_net_change_not_the_verdicts_share() -> None:
    # Gross -100, net -200: B1 -300 (1.5 of net) and P2 -270 (1.35 of net;
    # 2.7 of gross, the share its verdict stores) - both capped (#4).
    moved = Changes(revenue_prev=1000.0, revenue_cur=800.0, net=-200.0, gross=-100.0, alert=False)

    assert _supported(moved, B1=-300.0, P2=-270.0) == "B1"
    # Equal shares of the net change: catalog order.
    assert _supported(moved, P1=-240.0, P2=-240.0) == "P1"


def test_an_exact_term_is_not_beaten_by_an_overshooting_one() -> None:
    # The larger share decides only among terms that ALL overshoot: B1
    # explaining the -200 exactly ties P2 at 1.35 on the cap, and a tie with
    # an exact explanation goes to catalog order (#5; 3E1).
    assert _supported(MOVED, B1=-200.0, P2=-270.0) == "B1"


def test_diagnosis_json_is_major_12_and_refuses_an_11_file() -> None:
    # The same data can name a different cause (Online Retail II 2010-03: T1
    # under 11.0, R2 now) - a change of meaning, a major bump (CONTRACTS 10).
    payload = diagnosis_payload()
    payload["schema_version"] = "12.0"
    assert DiagnosisContract.supported_major == 12
    assert DiagnosisContract.model_validate(payload).schema_version == "12.0"

    payload["schema_version"] = "11.0"
    with pytest.raises(ValidationError, match="re-analyse"):
        DiagnosisContract.model_validate(payload)


def test_a_term_equal_to_the_change_up_to_residue_is_not_past_it() -> None:
    # 800.1 - 1000.3 is -200.19999999999993 in binary: B1 at -200.20, exact to
    # the cent, is no overshoot, so its tie with P2 stays catalog order (2E-m
    # review cycle 2).
    moved = Changes(revenue_prev=1000.3, revenue_cur=800.1, net=800.1 - 1000.3, gross=800.1 - 1000.3, alert=False)

    assert _supported(moved, B1=-200.20, P2=-270.0) == "B1"
