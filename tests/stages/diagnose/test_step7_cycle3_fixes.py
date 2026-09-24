"""Fabrications the 3E1 doubt-review cycle 3 reproduced, each fixed by a
decision of Thach's (3E1), written from the reproduction before the fix.

1. Missing days under D1's threshold were credited to B1 ("customers bought
   less often", 100%), because an order is a row count. B1 is refused
   whenever D1's evidence shows any excess zero day, or D1 could not run.
   B2 is kept: a missing day removes whole orders and leaves units per order
   unchanged (measured: 0 movement over 48 identical-day shops).
1b. A partly-empty history month taught "closed" as normal and hid a gap.
2. An export starting mid-month compared a whole month with half of one.
   Frame measures the leading gap; the trust gate blocks on it.
3. T2 read a year-ago month with missing days as the season.
4. Headline rule 6 named a price RISE as the best explanation of a FALL.
5. C4 read segment counts anchored at the file's end, not the two months.
7-10. Wording: a day with no sales is missing data OR a closure; a part is
   never printed as larger than the whole; one pace for one gap; a rule text
   that says what the check actually found.
"""

from datetime import date, timedelta
from types import SimpleNamespace as NS

from stages.diagnose.catalog import BY_ID
from stages.diagnose.headline import choose_headline
from stages.diagnose.hypotheses import evaluate_hypotheses
from stages.diagnose.step7_inputs import Changes, changes
from tests.stages.diagnose.diagnose_fixtures import daily_rows, row, run_data
from tests.stages.diagnose.test_hypotheses import by_id, step7


def _run(rows):
    inputs = step7(run_data(rows))
    results = evaluate_hypotheses(inputs)
    headline = choose_headline(inputs.trust, results, inputs.tree, changes(inputs))
    d1_check = next(c for c in inputs.trust.checks if c.id == "D1")
    return inputs, by_id(results), headline, d1_check


# --- 1. B1 and missing days -------------------------------------------------------


def test_b1_is_refused_when_days_are_missing_below_the_d1_threshold() -> None:
    """The reproduction: 13 clean daily months, then two missing January days
    (2.0 excess, under D1_CAUTION_DAYS). 310 -> 290: the whole -20 is the gap.
    It headlined "customers bought less often (100% of the change)"."""
    rows = daily_rows(date(2010, 12, 1), date(2012, 1, 31),
                      skip=(date(2012, 1, 10), date(2012, 1, 11)))

    _, verdicts, headline, check = _run(rows)

    assert check.evidence["excess_zero_days_cur"] == 2.0
    assert verdicts["B1"].verdict == "inconclusive"
    assert "less often" not in headline.message


def test_b1_is_refused_when_d1_cannot_run() -> None:
    """Two months, so the only history month is the previous one, which D1
    never learns from: no way to tell a gap from normal trading."""
    _, verdicts, _, check = _run(daily_rows(date(2011, 1, 1), date(2011, 2, 28)))

    assert check.status == "inconclusive"
    assert verdicts["B1"].verdict == "inconclusive"


def test_b2_keeps_its_verdict_across_a_gap() -> None:
    """Every day is the same three sales; January's quantities are x1.3 (a real
    basket change) and two January days are missing. Units per order are 1.3x
    whatever the gap, so B2 is not refused and still says baskets grew."""
    rows = []
    day = date(2010, 12, 1)
    while day <= date(2012, 1, 31):
        if day not in (date(2012, 1, 10), date(2012, 1, 11)):
            factor = 1.3 if day.year == 2012 else 1.0
            rows += [row(day, qty=q * factor, price=10.0, product="A", customer=c)
                     for q, c in ((1, "Ann"), (2, "Bob"), (3, "Cy"))]
        day += timedelta(days=1)

    _, verdicts, _, _ = _run(rows)

    assert verdicts["B1"].verdict == "inconclusive"
    assert verdicts["B2"].verdict == "supported"
    assert verdicts["B2"].statement == "Baskets got bigger"


# --- 1b. learning from a partly-empty history month -------------------------------


def test_a_partly_empty_history_month_does_not_teach_its_gap() -> None:
    """13 daily months; March 2011 misses 20 days, January 2012 misses 4. With
    March in the learning set the expectation absorbed 1.7 days and the gap
    fell under the threshold. March has 11 active days against a history
    median of 30-31, under half: it is not learned from."""
    hole = tuple(date(2011, 3, d) for d in range(5, 25))
    gap = tuple(date(2012, 1, d) for d in range(10, 14))

    _, _, headline, check = _run(daily_rows(date(2010, 12, 1), date(2012, 1, 31), skip=hole + gap))

    assert check.evidence["expected_zero_days_cur"] == 0.0
    assert check.evidence["sparse_history_months"] == ["2011-03"]
    assert check.status == "caution"
    assert headline.rule == 2


def test_a_near_empty_history_month_does_not_hide_a_twelve_day_gap() -> None:
    """History October (daily), November (ONE row), December (daily, the
    previous month, never learned from). January misses 12 of 31 days. The
    single-row November taught a ~48% closing rate and the gap vanished."""
    rows = daily_rows(date(2011, 10, 1), date(2011, 10, 31))
    rows += [row(date(2011, 11, 1))]
    rows += daily_rows(date(2011, 12, 1), date(2012, 1, 31),
                       skip=tuple(date(2012, 1, d) for d in range(10, 22)))

    _, verdicts, headline, check = _run(rows)

    assert check.evidence["excess_zero_days_cur"] == 12.0
    assert check.status == "caution"
    assert headline.rule == 2
    assert verdicts["B1"].verdict == "inconclusive"


# --- 2. an export that starts mid-month ------------------------------------------


def test_an_export_starting_mid_month_blocks_and_says_what_to_do() -> None:
    """The reproduction: identical daily trading from 15 January to 28
    February 2011. January holds 17 days, February 28: "+110, customers
    bought more often (100%)". The previous month is half a month."""
    inputs, _, headline, check = _run(daily_rows(date(2011, 1, 15), date(2011, 2, 28)))

    assert inputs.frame.previous_leading_days_missing == 14
    assert check.status == "blocked"
    assert headline.rule == 1
    assert "2011-01-01" in headline.message
    assert "re-export" in headline.message.lower()


def test_a_file_whose_first_sale_is_on_the_second_is_not_blocked() -> None:
    """One leading day - a New Year's Day closure looks exactly like this - is
    under D1's caution threshold, so it is not treated as a cut export."""
    inputs, _, headline, _ = _run(daily_rows(date(2011, 1, 2), date(2011, 2, 28)))

    assert inputs.frame.previous_leading_days_missing == 1
    assert headline.rule != 1


def test_a_file_with_no_previous_month_at_all_blocks_with_a_true_message() -> None:
    """A single-month file (January 2011): before the block it headlined
    "products were launched or discontinued (100%)" for 0 -> 310. The message
    must not claim the file started "31 days into" December."""
    _, _, headline, check = _run(daily_rows(date(2011, 1, 1), date(2011, 1, 31)))

    assert check.status == "blocked"
    assert headline.rule == 1
    assert "no sales in 2010-12" in headline.message
    assert "days into" not in headline.message


# --- 3. T2 and a year-ago month with missing days --------------------------------


def test_t2_is_refused_when_a_year_ago_month_has_missing_days() -> None:
    """The reproduction: February 2011 misses 10 days; February 2012 is
    complete but baskets really shrank (quantity 0.65). T2 priced the season
    from last year's gap and headlined rule 5."""
    rows = daily_rows(date(2010, 1, 1), date(2012, 1, 31),
                      skip=tuple(date(2011, 2, d) for d in range(5, 15)))
    rows += daily_rows(date(2012, 2, 1), date(2012, 2, 29), qty=0.65)

    _, verdicts, headline, _ = _run(rows)

    assert verdicts["T2"].verdict == "inconclusive"
    # 10 missing days less the 0.401 February 2011 taught as normal: with 18
    # active days it is above half the history median, so it stays in D1's
    # learning window and absorbs a little of its own gap.
    assert verdicts["T2"].evidence["excess_zero_days_year_ago_cur"] == 9.599
    assert headline.rule != 5


# --- 4. rule 6 names a cause that moved with the headline's change ---------------


def test_rule_6_never_names_a_cause_that_moved_against_the_net_change() -> None:
    """The reproduction: prices rise 10 -> 12 (gross sales UP) while refund
    lines on 20 days take revenue DOWN, 310 -> 108. P1 (+60, a share of the
    gross change) tied P3 (-240) at fit 1 and won on catalog order: a price
    rise named as the best explanation of a fall."""
    rows = daily_rows(date(2010, 12, 1), date(2011, 12, 31))
    for i in range(31):
        day = date(2012, 1, 1) + timedelta(days=i)
        rows.append(row(day, qty=1.0 if i % 10 else 0.5, price=12.0))
        if i < 20:
            rows.append(row(day, qty=-1.0, price=12.0))

    _, verdicts, headline, _ = _run(rows)

    assert verdicts["P1"].verdict == "supported"
    assert headline.hypothesis_id == "P3"


# --- 5. C4 -------------------------------------------------------------------------


def test_c4_is_inconclusive_in_v1_whatever_the_segments_say() -> None:
    """20 points towards weaker segments in a falling month would be
    supported, but stage 2's counts are a snapshot at the file's end,
    including rows after the current month, not the two diagnosed months."""
    def seg(name, now, before):
        return NS(segment=name, customers=now, customers_previous=before)

    segments = [seg("Champions", 10, 15), seg("Loyal", 10, 15), seg("At-risk", 20, 15),
                seg("Hibernating", 20, 15), seg("New", 30, 30), seg("Needs Attention", 10, 10)]
    inputs = NS(data=NS(parsed=NS(reverse={"customer": "Cust"}),
                        metrics=NS(customers=NS(segments=segments))),
                trust=NS(verdict="trusted"))
    from stages.diagnose.hypothesis_evidence import EVIDENCE

    outcome = EVIDENCE["C4"](inputs, Changes(1000.0, 800.0, -200.0, -200.0, False))

    assert outcome.verdict == "inconclusive"
    assert "snapshot" in outcome.rule


# --- 7-10. wording ------------------------------------------------------------------


def test_a_closure_is_not_stated_as_missing_data() -> None:
    """Every row present; the shop stopped trading on Mondays from January
    2012. The engine cannot tell that from missing data, so it must not say
    "missing days of data" - it names both."""
    rows = daily_rows(date(2010, 12, 1), date(2011, 12, 31))
    rows += daily_rows(date(2012, 1, 1), date(2012, 1, 31), closed_weekdays=(0,))

    _, verdicts, headline, _ = _run(rows)

    assert headline.rule == 2
    assert "closed" in headline.message
    assert "missing data" in headline.message
    assert "closure" in BY_ID["D1"].statement


def test_rule_2_never_prints_a_part_larger_than_the_whole() -> None:
    """Five missing days (-53.55 at January's pace) while prices rose 7.1%:
    the change is -31.54. "-53.55 of it" is a part bigger than the whole."""
    rows = daily_rows(date(2010, 12, 1), date(2011, 12, 31))
    rows += daily_rows(date(2012, 1, 1), date(2012, 1, 31), price=10.71,
                       skip=tuple(date(2012, 1, d) for d in range(10, 15)))

    _, _, headline, _ = _run(rows)

    assert headline.rule == 2
    assert "-53.55 against the change of -31.54" in headline.message


def test_the_caution_prices_a_gap_at_its_own_months_pace() -> None:
    """December misses 10 days at 10 a day; January trades at 20 a day. The
    caution said "worth roughly 200" (January's pace) while D1 used 100."""
    rows = daily_rows(date(2010, 12, 1), date(2011, 12, 31),
                      skip=tuple(date(2011, 12, d) for d in range(5, 15)))
    rows += daily_rows(date(2012, 1, 1), date(2012, 1, 31), price=20.0)

    _, verdicts, _, check = _run(rows)

    assert check.evidence["estimated_revenue_gap_prev"] == 100.0
    assert "worth roughly 100" in check.message
    assert verdicts["D1"].contribution == 100.0


def test_d1_ruled_out_text_states_what_the_check_found() -> None:
    """Two excess days under the threshold: the rule said "found no excess
    missing days", next to evidence showing 2.0."""
    rows = daily_rows(date(2010, 12, 1), date(2012, 1, 31),
                      skip=(date(2012, 1, 10), date(2012, 1, 11)))

    _, verdicts, _, _ = _run(rows)

    assert verdicts["D1"].verdict == "ruled_out"
    assert "no excess" not in verdicts["D1"].rule
    assert "2.0" in verdicts["D1"].rule
