"""The small, local fabrications 3E1 doubt-review cycle 4 reproduced, fixed
under Thach's stop rule (no fifth cycle; the non-local finding - a
half-gapped history month still hiding a gap - went to 3E1c instead).

1. A previous month with no counted sale, in a file WITH history, only
   cautioned ("worth roughly 0"), and a product sold for eleven months was
   headlined as "launched" (100%).
2. The leading-days block counted from the first row of ANY kind: a stock-in
   row on the 1st hid the missing month; one on the 10th printed a false
   "first sale" date.
4. Rule 6's sign filter let every negative cause through when the net change
   was exactly zero.
6. D1's inconclusive message said no complete history month held rows on a
   two-month file whose first month is complete.
"""

from datetime import date

from stages.diagnose.headline import choose_headline
from stages.diagnose.hypotheses import evaluate_hypotheses
from stages.diagnose.step7_inputs import changes
from tests.stages.diagnose.diagnose_fixtures import MAPPING, daily_rows, row, run_data
from tests.stages.diagnose.test_hypotheses import by_id, step7
from tests.stages.diagnose.test_step7_cycle3_fixes import _run

TYPED = dict(MAPPING, Type="transaction_type")


def _typed_run(rows):
    inputs = step7(run_data(rows, TYPED))
    results = evaluate_hypotheses(inputs)
    headline = choose_headline(inputs.trust, results, inputs.tree, changes(inputs))
    return inputs, by_id(results), headline


def _tag(rows, kind="out"):
    return [dict(r, Type=kind) for r in rows]


def test_a_previous_month_with_no_sale_blocks_even_with_history() -> None:
    """The reproduction: one product sold daily through November 2011, no row
    in December, daily again in January 2012. It cautioned "31 days ...
    worth roughly 0" and headlined "products were launched or discontinued
    (100%)" for a product eleven months old."""
    rows = daily_rows(date(2011, 1, 1), date(2011, 11, 30), product="Old")
    rows += daily_rows(date(2012, 1, 1), date(2012, 1, 31), product="Old")

    _, _, headline, check = _run(rows)

    assert check.status == "blocked"
    assert headline.rule == 1
    assert "no sales in 2011-12" in headline.message
    assert "launched" not in headline.message


def test_a_stock_in_row_does_not_hide_a_missing_previous_month() -> None:
    """Case D: a stock-in row on 1 January, sales only from 1 February. The
    first row covers January's first day, so nothing blocked and the
    headline read "products were launched or discontinued (100%)"."""
    feb = _tag(daily_rows(date(2011, 2, 1), date(2011, 2, 28), products=3))
    stock_in = _tag([row(date(2011, 1, 1), qty=100, product="Widget0")], "in")

    inputs, _, headline = _typed_run(stock_in + feb)

    assert inputs.frame.previous_leading_days_missing == 31
    assert headline.rule == 1


def test_the_block_prints_the_first_sale_not_the_first_row() -> None:
    """Case E: stock-in on 10 January, first sale 20 January: 19 days of
    January are before the first sale, not 9."""
    jan = _tag(daily_rows(date(2011, 1, 20), date(2011, 2, 28), products=3))
    stock_in = _tag([row(date(2011, 1, 10), qty=100, product="Widget0")], "in")

    inputs, _, headline = _typed_run(stock_in + jan)

    assert inputs.frame.previous_leading_days_missing == 19
    assert "first sale is on 2011-01-20, 19 days into 2011-01" in headline.message


def test_rule_6_names_nothing_when_the_net_change_is_zero() -> None:
    """Prices fall 12 -> 10 while December's 62.00 refund does not recur:
    net exactly 0. P1 (-62 of gross) passed the sign filter because
    (c > 0) == (0 > 0) admits every negative contribution; the mirror case
    got rule 7. A change of zero has no best explanation either way."""
    rows = daily_rows(date(2010, 12, 1), date(2011, 12, 31), price=12.0)
    rows += [row(date(2011, 12, 15), qty=-1.0, price=62.0)]
    rows += daily_rows(date(2012, 1, 1), date(2012, 1, 31), price=10.0)

    _, verdicts, headline, _ = _run(rows)

    assert verdicts["P1"].verdict == "supported"
    assert headline.rule == 7


def test_d1_inconclusive_says_why_truthfully_on_a_two_month_file() -> None:
    """January is complete and holds 31 days of sales; it is the previous
    month, which D1 never learns from. The message said no complete month
    held any rows."""
    _, _, _, check = _run(daily_rows(date(2011, 1, 1), date(2011, 2, 28)))

    assert check.status == "inconclusive"
    assert "No complete month before the current one holds any rows" not in check.message
    assert check.evidence["history_months_with_rows"] == 1
    assert check.evidence["learned_from_months"] == 0


def test_leading_days_never_exceed_the_previous_month() -> None:
    """Stock-in on 1 January; sales only 5-31 March, so March is current and
    February the previous month. The first sale is 32 days after 1 February;
    the count is of FEBRUARY's days, so it stops at 28."""
    march = _tag(daily_rows(date(2011, 3, 5), date(2011, 3, 31)))
    stock_in = _tag([row(date(2011, 1, 1), qty=100)], "in")

    inputs, _, headline = _typed_run(stock_in + march)

    assert (inputs.frame.previous, inputs.frame.previous_leading_days_missing) == ("2011-02", 28)
    assert headline.rule == 1
