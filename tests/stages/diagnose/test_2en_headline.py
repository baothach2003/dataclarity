"""Session 2E-n (Thach, 2026-09-27, after the fourth overnight run), written
before the change.

Q1 reading G: the products' share of the change is the change in the SALE
    lines of the product members over the net change; customer returns are
    their own class (P3). Breadth, R1 and the headline's product-lens gate
    read it (2E-m: one definition).
Q2 one fit measure for every cause: fit = max(0, 1 - |1 - share of the net
    change|), superseding 3E1's cap on terms and 2E-m's D1. With no
    positive fit the headline names the largest contribution each way, in
    money. An exact tie names every tied cause, never catalog order.
Q4 the headline prints the share of the NET change, and only up to 100%.
"""

from datetime import date

import pandas as pd
import pytest
from pydantic import ValidationError

from contracts.diagnosis import DiagnosisContract, Hypothesis
from stages.diagnose.catalog import CATALOG
from stages.diagnose.headline import choose_headline
from stages.diagnose.step7_inputs import Changes, changes
from tests.contracts.test_diagnosis import diagnosis_payload
from tests.stages.diagnose.test_2el_review1 import COLUMNS, _days, _run
from tests.stages.diagnose.test_headline import catalog, tree, trust




def _headline(moved: Changes, **causes: tuple[str, float | None]):
    """Every catalog cause ruled out with no contribution except `causes`:
    id -> (verdict, contribution); the stored share is the verdict's own
    (of |gross| for the product lens, of |net| otherwise)."""
    hypotheses = []
    for spec in CATALOG:
        verdict, contribution = causes.get(spec.id, ("ruled_out", None))
        total = abs(moved.gross if spec.lens == "product" else moved.net)
        hypotheses.append(Hypothesis(
            id=spec.id, family=spec.family, lens=spec.lens, statement=spec.statement, verdict=verdict,
            contribution=contribution, share=None if contribution is None else contribution / total,
            evidence={}, rule="test"))
    return choose_headline(trust(), hypotheses, tree(False), moved)


def _moved(prev: float, cur: float, gross: float | None = None, holds: bool = True) -> Changes:
    return Changes(revenue_prev=prev, revenue_cur=cur, net=cur - prev,
                   gross=cur - prev if gross is None else gross, alert=False, products_hold_the_change=holds)


# --- Q2: one fit measure --------------------------------------------------------

def test_a_cause_close_to_the_change_beats_a_term_far_past_it() -> None:
    # Online Retail II 2011-08 unanswered, rounded: prices +26,700 on a +1,400
    # month (19x: fit 0) against new customers +1,680 (1.2x: fit 0.8). 3E1's
    # cap gave the term a fit of 1 and named it.
    headline = _headline(_moved(10_000.0, 11_400.0), P1=("supported", 26_700.0), C1=("supported", 1_680.0))

    assert (headline.rule, headline.hypothesis_id) == (6, "C1")


def test_a_cause_at_1_14x_beats_one_at_7_8x() -> None:
    # The 2E-m sweep's seed 537: net +11.90; returns +13.53 (1.14x, fit 0.86)
    # against charges +93.00 (7.8x, fit 0). D1 named the larger.
    moved = _moved(2_635.61, 2_647.51, gross=-94.63)
    headline = _headline(moved, P3=("supported", 13.53), P5=("supported", 93.0))

    assert (headline.rule, headline.hypothesis_id) == (6, "P3")
    # 1.14x is no percentage: the contribution against the change.
    assert "+13.53 against the change of +11.90" in headline.message


def test_two_terms_past_the_change_rank_by_how_close_they_come() -> None:
    # Net -9,800: P1 -15,000 (1.53x, fit 0.47) and P2 -18,000 (1.84x, fit
    # 0.16). D1 named the larger share (P2); the closer one fits better.
    headline = _headline(_moved(50_000.0, 40_200.0), P1=("supported", -15_000.0), P2=("supported", -18_000.0))

    assert headline.hypothesis_id == "P1"


def test_an_expectation_and_a_term_are_judged_by_the_same_measure() -> None:
    # Net -200: an expectation at 0.90 (fit 0.90) against a term at 1.20
    # (fit 0.80). The cap gave the term 1 and named it; the closer one wins,
    # whatever its kind.
    headline = _headline(_moved(1_000.0, 800.0), C1=("supported", -180.0), B1=("supported", -240.0))

    assert headline.hypothesis_id == "C1"
    # ...and the other way round: a term at 0.90 beats an expectation at 1.20.
    headline = _headline(_moved(1_000.0, 800.0), C1=("supported", -240.0), B1=("supported", -180.0))

    assert headline.hypothesis_id == "B1"


def test_an_exact_expectation_still_beats_an_overshooting_term() -> None:
    # 3E1's case: C1 explains -200 exactly (fit 1), B1 is at 1.50 (fit 0.5).
    headline = _headline(_moved(1_000.0, 800.0), C1=("supported", -200.0), B1=("supported", -300.0))

    assert headline.hypothesis_id == "C1"


# --- Q2: an exact tie names every tied cause ---------------------------------------

def test_an_exact_tie_names_both_causes_and_no_single_hypothesis() -> None:
    headline = _headline(_moved(1_000.0, 800.0), P1=("supported", -240.0), P2=("supported", -240.0))

    assert (headline.rule, headline.hypothesis_id, headline.lens) == (6, None, None)
    assert "like-for-like prices changed" in headline.message
    assert "sales mix shifted" in headline.message


def test_causes_equally_far_either_side_of_the_change_tie() -> None:
    # 0.9x and 1.1x of the change: 20.02 short and 20.02 past it. In binary
    # 1 - |1 - 0.9| and 1 - |1 - 1.1| differ, so the tie is judged in money
    # above residue. Net 800.1 - 1000.3 is -200.19999999999993.
    moved = _moved(1_000.3, 800.1)
    headline = _headline(moved, B1=("supported", -180.18), P3=("supported", -220.22))

    assert headline.hypothesis_id is None
    assert "purchase frequency changed" in headline.message
    assert "returns changed" in headline.message


@pytest.mark.parametrize("prev, cur", [(1_000.3, 800.1), (1_000.6, 800.4), (1_000.0, 799.8)])
def test_a_cause_exact_to_the_cent_beats_an_overshoot_however_the_net_rounds(prev: float, cur: float) -> None:
    # The Q5 review of 2E-m's cycle-2 fixes: fits compared float-exactly let
    # the rounding of the net decide. On 800.4 - 1000.6 (-200.20000000000005)
    # B1 at -200.20 fit 0.9999999999999997 and lost to P2 at 1.35x; C1 exact
    # to the cent lost to B1 at 1.5x on either residue net. Judged as money
    # above residue, exact is exact.
    moved = _moved(prev, cur)

    assert _headline(moved, B1=("supported", -200.20), P2=("supported", -270.27)).hypothesis_id == "B1"
    assert _headline(moved, C1=("supported", -200.20), B1=("supported", -300.30)).hypothesis_id == "C1"


def test_equal_shares_up_to_residue_are_a_tie() -> None:
    # P1 -240.0 and P2 -(0.1 + 0.2) * 800 = -240.00000000000003 are equal
    # shares; float-exact, P2 won (Q5 review).
    headline = _headline(_moved(1_000.0, 800.0), P1=("supported", -240.0), P2=("supported", -(0.1 + 0.2) * 800))

    assert headline.hypothesis_id is None
    assert "like-for-like prices changed" in headline.message and "sales mix shifted" in headline.message


def test_an_exact_cause_later_in_the_catalog_beats_two_overshoots() -> None:
    # The Q5 review's case D: P1 -240 and P2 -270 past a -200.20 change, P5
    # exact to the cent. The cap tied all three and catalog order named P1.
    headline = _headline(_moved(1_000.3, 800.1), P1=("supported", -240.0), P2=("supported", -270.0),
                         P5=("supported", -200.20))

    assert headline.hypothesis_id == "P5"


def test_a_near_tie_is_no_tie() -> None:
    # 20.00 against 20.02 short of the change: a cent is money, not residue.
    headline = _headline(_moved(1_000.0, 800.0), B1=("supported", -180.0), P3=("supported", -179.98))

    assert headline.hypothesis_id == "B1"


def test_rule_5_names_the_calendar_and_seasonality_when_they_tie() -> None:
    moved = _moved(1_000.0, 800.0)
    headline = _headline(moved, T1=("supported", -180.0), T2=("supported", -220.0))

    assert headline.rule == 5
    assert "the calendar" in headline.message and "seasonality" in headline.message
    assert "90% of the change" in headline.message
    assert "-220.00 against the change of -200.00" in headline.message


# --- Q2: no cause fits ---------------------------------------------------------------

def test_no_cause_with_a_positive_fit_names_the_largest_movement_each_way() -> None:
    # Net -200. P1 -600 is supported (3x: fit 0). The mix moved +380 the other
    # way (ruled out: it opposes the change). Money, no percentage over 100.
    headline = _headline(_moved(1_000.0, 800.0), P1=("supported", -600.0), P2=("ruled_out", 380.0))

    assert (headline.rule, headline.hypothesis_id, headline.lens) == (6, None, None)
    assert headline.message == (
        "Revenue went from 1,000.00 to 800.00 (-200.00). The change is what remains of movements in "
        "opposite directions, among them: down, like-for-like prices changed (product lens, -600.00); up, "
        "sales mix shifted (product lens, +380.00).")  # 2E-o Q5 #1: "among them"


def test_twice_the_change_is_no_fit() -> None:
    # Exactly 2x: fit max(0, 1 - |1 - 2|) = 0.
    headline = _headline(_moved(1_000.0, 800.0), P3=("supported", -400.0))

    assert headline.hypothesis_id is None
    assert "The change is what remains of movements in opposite directions" in headline.message


def test_twice_the_change_to_the_cent_is_no_fit_however_the_net_rounds() -> None:
    # -400.40 on 800.4 - 1000.6 = -200.20000000000005: the distance
    # 200.19999999999996 is under |net| by 9e-14 - residue, not a fit
    # (mutation check F2).
    headline = _headline(_moved(1_000.6, 800.4), P3=("supported", -400.40))

    assert headline.hypothesis_id is None
    assert "The change is what remains of movements in opposite directions" in headline.message


def test_an_expectation_that_failed_its_test_is_no_movement() -> None:
    # Seasonality predicting -5,000 (ruled out: 25x the change) is an
    # estimate that failed, not a movement: the largest down stays P1's -600.
    # Online Retail II 2011-07 unanswered would name T2 at -106k (mutation N1).
    headline = _headline(_moved(1_000.0, 800.0), P1=("supported", -600.0), P2=("ruled_out", 380.0),
                         T2=("ruled_out", -5_000.0))

    assert "down, like-for-like prices changed (product lens, -600.00)" in headline.message
    assert "5,000" not in headline.message
    # ...nor against the change: the calendar estimated at +500, ruled out.
    headline = _headline(_moved(1_000.0, 800.0), P3=("supported", -600.0), T1=("ruled_out", 500.0),
                         B1=("ruled_out", 300.0))

    assert "up, purchase frequency changed (lever lens, +300.00)" in headline.message


def test_a_movement_is_named_whatever_the_product_lens_gate() -> None:
    # The gate guards naming an EXPLANATION; the no-fit message names
    # movements, each with its lens. It is closed whenever the products'
    # sales carry at most half of the change - also when the products
    # moved against the change - when they are the opposing movement (review
    # cycle 1 #1: "no tested cause moved revenue up" beside a supported
    # price rise).
    headline = _headline(_moved(1_000.0, 800.0, holds=False), P3=("supported", -600.0),
                         P2=("ruled_out", 900.0), B1=("ruled_out", 300.0))

    assert "up, sales mix shifted (product lens, +900.00)" in headline.message


def test_a_customer_flow_that_failed_its_test_is_no_movement_of_the_change() -> None:
    # C1-C3 are differences between two transitions (term(t) - term(t-1)),
    # judged as expectations - no part of this month's change: C2 at +400
    # read "lapsed customers took less revenue away" while this month's
    # lapsed term pulled revenue DOWN (review cycle 3 #1). Only when
    # supported, as every expectation.
    headline = _headline(_moved(1_000.0, 800.0), P3=("supported", -600.0), C2=("ruled_out", 163.0),
                         B1=("ruled_out", 9.88))

    assert headline.message.endswith("up, purchase frequency changed (lever lens, +9.88).")
    assert "163" not in headline.message


def test_a_price_rise_against_a_refund_month_is_named_as_the_movement_up() -> None:
    # Review cycle 1 #1, real pipeline: A sells 5 a day at 10, at 11 in August
    # (+155, P1 supported); 30 units of A are refunded on August 15 under
    # A's SKU (-300, P3 supported). Net -145: returns 2.07x, no fit. The
    # products' sales moved against the change, so the gate is closed - and
    # the price rise is still the movement up.
    rows, i = [], 0
    for day in _days():
        for _ in range(5):
            rows.append((day.isoformat(), f"C{i % 40}", "A", "ITEM A", "1", "11" if day.month == 8 else "10"))
            i += 1
        if day == date(2026, 8, 15):
            rows.append((day.isoformat(), "C3", "A", "ITEM A", "-30", "10"))
    rows.append((date(2026, 9, 1).isoformat(), "C1", "A", "ITEM A", "1", "10"))

    inputs, results, headline = _run(pd.DataFrame(rows, columns=COLUMNS), {})

    assert changes(inputs).products_hold_the_change is False
    assert (results["P1"].verdict, results["P1"].contribution) == ("supported", pytest.approx(155.0))
    assert headline.message == (
        "Revenue went from 1,550.00 to 1,405.00 (-145.00). The change is what remains of movements in "
        "opposite directions, among them: down, returns took more revenue away (returns lens, -300.00); "
        "up, like-for-like prices changed (product lens, +155.00).")  # 2E-o Q5 #1: signed, "among them"


def test_the_no_fit_message_claims_no_fit_a_gated_cause_would_contradict() -> None:
    # Review cycle 2 #1: the products' sales carry less than half of the
    # change, so P1 - exactly the change - is held back by the gate; "no
    # supported cause fits" was false. The message names the movements only.
    headline = _headline(_moved(1_000.0, 845.0, gross=-35.0, holds=False), P1=("supported", -155.0),
                         P3=("supported", -400.0), P5=("ruled_out", 280.0))

    assert headline.message.startswith(
        "Revenue went from 1,000.00 to 845.00 (-155.00). The change is what remains of movements in "
        "opposite directions, among them: down, returns changed")  # 2E-o Q5 #1
    assert "largest" not in headline.message
    assert "fits" not in headline.message


def test_residue_is_no_movement_the_other_way() -> None:
    headline = _headline(_moved(1_000.0, 800.0), P3=("supported", -600.0), P4=("ruled_out", 1e-13))

    # Nothing tested moved it up: only the movement down is named - no claim
    # about the rest (it sits in parts no hypothesis names, such as volume).
    assert headline.message.endswith("opposite directions, among them: down, returns changed (returns lens, "
                                     "-600.00).")  # 2E-o Q5 #1: "among them"


def test_the_movements_named_claim_no_rank_among_parts_no_hypothesis_names() -> None:
    # (Through `_headline`, statements are unsigned; stage 3 signs P3 since
    # 2E-o - test_2eo_headline.py.)
    # Review cycle 3 #2: "The largest down: mix" stood beside a larger
    # level-1 customers factor (Online Retail II 2011-07 unanswered): the
    # tree's parts are not all hypotheses. The movement named each way is the
    # largest tested one, and the sentence says only its direction and money.
    headline = _headline(_moved(1_000.0, 800.0), P2=("supported", -600.0), P3=("ruled_out", 380.0))

    assert "largest" not in headline.message
    assert headline.message.endswith(": down, sales mix shifted (product lens, -600.00); up, returns changed "
                                     "(returns lens, +380.00).")


def test_two_movements_of_the_same_largest_size_are_both_named() -> None:
    headline = _headline(_moved(1_000.0, 800.0), P3=("supported", -600.0), B1=("ruled_out", 380.0),
                         P2=("ruled_out", 380.0))

    assert headline.message.endswith("up, purchase frequency changed (lever lens, +380.00) and "
                                     "sales mix shifted (product lens, +380.00).")


def test_a_cause_equal_to_the_change_up_to_residue_prints_100_percent() -> None:
    # B1 -200.20 on 800.1 - 1000.3 = -200.19999999999993 is 2 ulp "past" the
    # change: residue, so a share - not two equal figures (mutation W2).
    headline = _headline(_moved(1_000.3, 800.1), B1=("supported", -200.20))

    assert headline.message.endswith("(lever lens, 100% of the change).")


# --- Q4: the net share, up to 100% ---------------------------------------------------

def test_a_product_lens_cause_prints_its_share_of_the_net_change() -> None:
    # Net -100, gross -80: P1 -80 is 100% of gross (its verdict's share) and
    # 80% of the change the headline states.
    headline = _headline(_moved(1_000.0, 900.0, gross=-80.0), P1=("supported", -80.0))

    assert headline.message.endswith("(product lens, 80% of the change).")
    assert "gross" not in headline.message


def test_a_product_lens_cause_past_the_change_prints_money_not_a_percentage() -> None:
    headline = _headline(_moved(1_000.0, 900.0, gross=-150.0), P1=("supported", -150.0))

    assert headline.message.endswith("(product lens, -150.00 against the change of -100.00).")


# --- Q1: reading G, real pipeline ------------------------------------------------------

def _refund_shop(b_august: str, refunds_august: int) -> pd.DataFrame:
    """A at 20, B at 5. March-July 2 A + 2 B a day; August 1 A + 3 B a day,
    B at `b_august` (at 5 on the 31st). A is refunded -1 @ 20 on July 1-2 and
    on the first `refunds_august` days of August - under its own SKU."""
    rows, i = [], 0
    for day in _days():
        august, july = day.month == 8, day.month == 7
        a, b = (1, 3) if august else (2, 2)
        b_price = b_august if august and day.day < 31 else "5"
        for sku, name, qty, price in (("A", "ITEM A", a, "20"), ("B", "ITEM B", b, b_price)):
            for _ in range(qty):
                rows.append((day.isoformat(), f"C{i % 40}", sku, name, "1", price))
                i += 1
        if (july and day.day <= 2) or (august and day.day <= refunds_august):
            rows.append((day.isoformat(), f"C{i % 40}", "A", "ITEM A", "-1", "20"))
            i += 1
    rows.append((date(2026, 9, 1).isoformat(), "C1", "A", "ITEM A", "1", "20"))
    return pd.DataFrame(rows, columns=COLUMNS)


def test_the_products_share_counts_their_sale_lines_not_their_refunds() -> None:
    # August: A 31 x 20 = 620 (July 1,240), B 30 x 3 x 8 + 3 x 5 = 735 (July
    # 310): gross 1,355 against 1,550, -195. A's refunds 12 x 20 = 240 against
    # 40: returns -200. Net 1,510 -> 1,115, -395. The products' SALES carry
    # -195 of it: 49%, not more than half. Their net change (sales and
    # refunds) was all of it, and opened the gate for the mix term, -420
    # against -395 - an offset inside gross sales that only looks close.
    inputs, results, headline = _run(_refund_shop("8", 12), {})

    breadth = inputs.localization.breadth
    assert breadth.products_share_of_change == pytest.approx(195 / 395)
    assert breadth.classification == "outside_products"
    assert changes(inputs).products_hold_the_change is False
    assert (results["P2"].verdict, results["P2"].contribution) == ("supported", pytest.approx(-420.0))
    assert (results["P3"].verdict, results["P3"].contribution) == ("supported", pytest.approx(-200.0))
    assert (headline.rule, headline.hypothesis_id) == (6, "P3")
    assert headline.message.endswith("(returns lens, 51% of the change).")


def test_r1_names_the_product_whose_revenue_moved_not_an_order_cancelled() -> None:
    # Review cycle 1 #3: six products at 10, two a day; in August P0 sells
    # one fewer on the first 5 days (-50, the only real movement). On July 10
    # a customer orders 400 of X at 10 and cancels it the same day: X's
    # revenue is 0 in both months. The products' SALES fell 4,050 (the
    # cancelled sale is July's gross), so the share is 81x the -50 change -
    # Thach's reading G. Where the NET change sits is each product's own
    # change: P0, not X (read on sale lines, R1 named X at -4,000).
    rows, i = [], 0
    for when in _days():
        for k in range(6):
            n = 1 if (when.month == 8 and when.day <= 5 and k == 0) else 2
            for _ in range(n):
                rows.append((when.isoformat(), f"C{i % 30}", f"P{k}", f"PRODUCT {k}", "1", "10"))
                i += 1
        if when == date(2026, 7, 10):
            rows.append((when.isoformat(), "C99", "X", "BIG ITEM", "400", "10"))
            rows.append((when.isoformat(), "C99", "X", "BIG ITEM", "-400", "10"))
    rows.append((date(2026, 9, 1).isoformat(), "C1", "P1", "PRODUCT 1", "1", "10"))

    inputs, results, _ = _run(pd.DataFrame(rows, columns=COLUMNS), {})

    breadth = inputs.localization.breadth
    assert breadth.products_share_of_change == pytest.approx(4_050 / 50)
    assert (breadth.classification, breadth.top_member_share) == ("concentrated", pytest.approx(1.0))
    assert results["R1"].verdict == "supported"
    assert (results["R1"].evidence["top_member"], results["R1"].evidence["top_member_delta"]) == (
        "PRODUCT 0", pytest.approx(-50.0))


def test_rule_5_needs_a_context_cause_that_fits_above_residue() -> None:
    # Review cycle 1 #4: a change of 0.004 on a month of 1,000,000 (the money
    # moved 2,000,000): T2 at 1.79x is supported, but its room, 0.2 of the
    # change, is residue - rule 5 printed "consistent with ." and now leaves
    # the month to rule 6.
    moved = Changes(revenue_prev=1_000_000.0, revenue_cur=1_000_000.004, net=1_000_000.004 - 1_000_000.0,
                    gross=1_000_000.004 - 1_000_000.0, alert=False, scale=2_000_000.0)
    headline = _headline(moved, T2=("supported", 1.79 * moved.net))

    assert headline.rule == 6
    assert "consistent with" not in headline.message


# --- the contract ----------------------------------------------------------------------

def test_diagnosis_json_is_major_13_or_the_current_one_and_refuses_a_12_file() -> None:
    # Breadth's products_share_of_change reads sale lines, the same data can
    # name another cause, and rule 6 may name none or two (CONTRACTS 10).
    # 13.0 in 2E-n; 14.0 in 2E-i; 15.0 since 2E-j.
    payload = diagnosis_payload()
    assert DiagnosisContract.supported_major == 18  # 18 since 3E1b; 17 since 2E-t2 (the line taxonomy)
    assert DiagnosisContract.model_validate(payload).schema_version == "18.0"

    payload["schema_version"] = "12.0"
    with pytest.raises(ValidationError, match="re-analyse"):
        DiagnosisContract.model_validate(payload)
