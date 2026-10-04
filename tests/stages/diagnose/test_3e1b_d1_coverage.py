"""Session 3E1b: the D1 check on whole files (trust.d1_coverage), each shape
the method swept, worked by hand. The arithmetic of the rule is in
test_3e1b_d1_pattern.py; here, what a shop's rows make of it."""

from datetime import date, timedelta

from tests.stages.diagnose.diagnose_fixtures import daily_rows
from tests.stages.diagnose.test_step7_cycle3_fixes import _run


def _days(year: int, month: int, first: int, last: int) -> tuple[date, ...]:
    return tuple(date(year, month, day) for day in range(first, last + 1))


def test_one_lost_day_in_a_shop_that_never_misses_one_cautions() -> None:
    """2E-u F5. Thirteen daily months; January 2012 loses the 10th. Nothing
    learned has a zero day, so the expectation and the spread are 0, and one
    whole day cautions: 31 x 10 = 310 against 300, the gap 10."""
    _, verdicts, headline, check = _run(daily_rows(date(2010, 12, 1), date(2012, 1, 31),
                                                   skip=(date(2012, 1, 10),)))
    evidence = check.evidence
    assert (check.status, evidence["excess_zero_days_cur"], evidence["caution_bar_days_cur"],
            evidence["estimated_revenue_gap"]) == ("caution", 1.0, 0.0, 10.0)
    assert check.message.startswith("About 1 day in the current month has no sales")
    assert verdicts["D1"].verdict == "supported" and headline.rule == 2


def test_a_half_gapped_history_month_no_longer_hides_a_lost_week() -> None:
    """3E1 cycle 4's reproduction (scratchpad review9/r6): November full,
    December missing the 1st-14th (17 active days of 31, above half the
    median, so it was learned from), January the previous month, February
    missing the 10th-16th. December taught 14/31 of every weekday as closed,
    so February expected 6.7 zero days, found 7, and read "ok" while rule 6
    named B1. Now December's 14 against November's 0 excludes it; February
    expects 0 and the 7 days caution."""
    rows = daily_rows(date(2011, 11, 1), date(2012, 2, 29),
                      skip=_days(2011, 12, 1, 14) + _days(2012, 2, 10, 16))
    _, verdicts, headline, check = _run(rows)
    assert check.evidence["gapped_history_months"] == ["2011-12"]
    assert (check.status, check.evidence["expected_zero_days_cur"], check.evidence["excess_zero_days_cur"]) \
        == ("caution", 0.0, 7.0)
    assert verdicts["B1"].verdict == "inconclusive" and headline.hypothesis_id != "B1"


def test_an_annual_closure_is_no_gap_but_still_moves_the_month() -> None:
    """Closed 25-26 December every year, daily otherwise; the current month is
    December 2023. The weekday pattern alone expects 0.128 zero days (6 over
    the 36 months D1 learns from), so 2 are 1.872 beyond it. The Decembers
    2021 and 2022 held 2 each: the same calendar month of other years expects
    2, so nothing is unexplained and the badge is "ok". But the closure still
    took two days from December against November: the excess beyond the
    PATTERN is what B1's refusal reads, so B1 stays refused (3E1b review 1,
    F1: an annual closure once lifted B1 to "bought more lines, 100%")."""
    closed = tuple(date(year, 12, day) for year in (2021, 2022, 2023) for day in (25, 26))
    _, verdicts, _, check = _run(daily_rows(date(2021, 1, 1), date(2023, 12, 31), skip=closed))
    evidence = check.evidence
    assert (check.status, evidence["zero_days_cur"], evidence["unexplained_zero_days_cur"]) == ("ok", 2, 0.0)
    assert evidence["excess_zero_days_cur"] == 1.872
    assert verdicts["B1"].verdict == "inconclusive"
    # T2's year-ago December is read on the pattern too: its closure refuses
    # last year's season (1.937 beyond the pattern), as before 3E1b.
    assert (verdicts["T2"].verdict, verdicts["T2"].evidence["excess_zero_days_year_ago_cur"])         == ("inconclusive", 1.937)


def test_a_gap_in_a_month_the_season_explains_shows_in_the_cause_not_the_badge() -> None:
    """The same shop also loses 10-11 December 2023: four zero days; the
    pattern expects 0.128, the earlier Decembers held 1.889 beyond theirs on
    average, so 1.983 are unexplained - under December's floor once its season
    is counted (a 1.89-day annual closure makes the month vary like a rate of
    0.06 a day: 2.5 x sqrt(31 x 0.06 x 0.94) = 3.3; review 3, R1's fix). A
    known limit, the badge's: the days beyond the weekday PATTERN (3.872) are
    what B1 and the D1 hypothesis read, so B1 stays refused and D1 is found."""
    closed = tuple(date(year, 12, day) for year in (2021, 2022, 2023) for day in (25, 26))
    _, verdicts, _, check = _run(daily_rows(date(2021, 1, 1), date(2023, 12, 31),
                                            skip=closed + (date(2023, 12, 10), date(2023, 12, 11))))
    evidence = check.evidence
    assert (check.status, evidence["unexplained_zero_days_cur"], evidence["excess_zero_days_cur"])         == ("ok", 1.983, 3.872)
    assert evidence["caution_bar_days_cur"] > evidence["unexplained_zero_days_cur"]
    assert verdicts["B1"].verdict == "inconclusive" and verdicts["D1"].verdict != "ruled_out"


# --- Q3 (Thach, 2026-10-05, option C): the badge says what the D1 hypothesis reads --------------------
# One judge, two measures (3E1b review 1, F1): the badge reads the days beyond the weekday pattern AND the
# month's season, the D1 hypothesis the days beyond the weekday pattern. Where the season explains days the
# hypothesis still finds, an "ok" badge saying "Coverage matches this store's normal trading pattern" sat
# beside rule 2's "days with no sales ... explain the change". Both measures stay; the badge says so.

USUAL = "Days with no sales match this store's usual {month}: {n} beyond its weekday pattern, as in other years."
# Review (the seventeenth run), finding 1 - 3.3a's shape: the data cannot tell whether this month's days
# beyond what its season held in other years are lost or ordinary variation, so the badge states both
# measured figures rather than "as in other years" (Thach's sentence, kept wherever the two agree).
AGAINST = ("Days with no sales match this store's usual {month}: {n} beyond its weekday pattern, against about {m} "
           "in other years.")


def _christmas(days: tuple[int, ...], lost: bool = False, last: date = date(2023, 12, 31)):
    closed = tuple(date(year, 12, day) for year in (2021, 2022, 2023) for day in days)
    extra = (date(2023, 12, 10), date(2023, 12, 11)) if lost else ()
    return _run(daily_rows(date(2021, 1, 1), last, skip=closed + extra))


def test_the_reproduction_closed_25_26_december_every_year_and_two_days_lost() -> None:
    """The seventeenth run's reproduction: 3.872 days beyond the weekday pattern (over December's bar of
    3.432, so D1 is found and rule 2 fires), 1.983 beyond the pattern and the season (under it: "ok"); the
    earlier Decembers held 1.889 beyond their pattern - about 2, not 4."""
    _, verdicts, headline, check = _christmas((25, 26), lost=True)

    assert (check.status, verdicts["D1"].verdict, headline.rule) == ("ok", "supported", 2)
    assert check.message == AGAINST.format(month="December", n=4, m=2)


def test_a_christmas_closure_moves_january_against_its_december() -> None:
    # Closed 24-31 December every year: January against December finds December's 8 days (rule 2); the
    # badge names the month it means - the previous one.
    _, verdicts, headline, check = _christmas(tuple(range(24, 32)), last=date(2024, 1, 31))

    assert (check.status, verdicts["D1"].verdict, headline.rule) == ("ok", "supported", 2)
    assert check.message == USUAL.format(month="December", n=8)


def test_days_the_d1_test_does_not_find_leave_the_badge_as_it_was() -> None:
    # Closed 25-26 December only: 1.872 beyond the pattern, under the bar - D1 ruled out, nothing to say.
    _, verdicts, _, check = _christmas((25, 26))

    assert (check.status, verdicts["D1"].verdict) == ("ok", "ruled_out")
    assert check.message == "Coverage matches this store's normal trading pattern."


def test_the_badge_reads_the_d1_hypothesis_own_test_month_by_month() -> None:
    # One predicate on the same evidence (trust.months_beyond_pattern): the badge and D1 agree at the
    # boundary; both months found -> the current month first.
    from stages.diagnose.trust import months_beyond_pattern, usual_days_sentence

    evidence = {"excess_zero_days_cur": 3.872, "caution_bar_days_cur": 3.432,
                "excess_zero_days_prev": 3.432, "caution_bar_days_prev": 3.432, "caution_min_days": 1.0,
                "expected_zero_days_cur": 0.128, "seasonal_expected_zero_days_cur": 2.017,
                "expected_zero_days_prev": 0.0, "seasonal_expected_zero_days_prev": 5.2}
    assert months_beyond_pattern(evidence) == ["cur"]  # 3.432 is not MORE than its bar
    both = evidence | {"excess_zero_days_prev": 5.4}
    assert months_beyond_pattern(both) == ["cur", "prev"]
    # The current month 4 beyond its pattern against 1.889 its season held (about 2); the previous 5 and 5.2.
    assert usual_days_sentence(both, "2023-12", "2023-11") == " ".join(
        (AGAINST.format(month="December", n=4, m=2), USUAL.format(month="November", n=5)))
    # A shop closed some weekdays: its pattern expects 0.6 of them; the season 2.9 in all - 2.3 beyond the
    # pattern, so "about 2", never the season's whole 2.9 (review mutation: the pattern not subtracted).
    weekdays = evidence | {"expected_zero_days_cur": 0.6, "seasonal_expected_zero_days_cur": 2.9}
    assert usual_days_sentence(weekdays, "2023-12", "2023-11") == AGAINST.format(month="December", n=4, m=2)
    assert months_beyond_pattern(evidence | {"caution_min_days": 4.0}) == []  # under the floor


def test_a_seasonal_shops_off_season_month_is_expected() -> None:
    """Daily April to September; October to March only on the 1st and the
    15th. The file's last sale is 15 November 2023, so the current month is
    October: 29 zero days of 31; Octobers 2021 and 2022 held as many beyond
    their weekdays, so none is unexplained. Until 3E1b the year-round
    weekday pattern expected about 14 and the month was BLOCKED as 'too few
    trading days'. The off-season months teach no weekday habit (review 3,
    R1): the pattern is the in-season one, 0, and its excess - all 29 days -
    is what the D1 hypothesis reads: the shop closing for the season is what
    took September's revenue away (29 x 10 = 290 against the change of 280)."""
    first, last = date(2021, 1, 1), date(2023, 11, 30)
    every = [first + timedelta(days=i) for i in range((last - first).days + 1)]
    closed = tuple(d for d in every if not (4 <= d.month <= 9 or d.day in (1, 15)))
    _, verdicts, headline, check = _run(daily_rows(first, last, skip=closed))
    evidence = check.evidence
    assert (check.status, evidence["zero_days_cur"], evidence["unexplained_zero_days_cur"]) == ("ok", 29, 0.0)
    assert evidence["excess_zero_days_cur"] == 29.0 and verdicts["D1"].verdict == "supported"
    assert headline.rule != 1
    # Q3: the off-season the hypothesis reads, said by the badge too.
    assert check.message == USUAL.format(month="October", n=29)


def test_a_sparse_shops_ordinary_variation_is_no_caution() -> None:
    """Part A. A shop trading every other day (alternate weekdays each week,
    so every weekday's zero-rate is about one half) misses four more trading
    days in January 2012 (the 1st, 3rd, 5th, 7th): 19 zero days where 16 are
    expected (31 days at a rate of one half; the same January a year earlier
    held 16), an excess of 3.0 - the old fixed 3 days, which such noise
    reached on 27% of sparse shops. Its binomial spread is 2.5 x sqrt(31 x
    0.25) = 6.96, so 3 is ordinary for this shop."""
    start, end = date(2010, 12, 1), date(2012, 1, 31)
    odd = tuple(start + timedelta(days=2 * i + 1) for i in range(((end - start).days + 1) // 2))
    _, _, _, check = _run(daily_rows(start, end, skip=odd + _days(2012, 1, 1, 1) + _days(2012, 1, 3, 3)
                                       + _days(2012, 1, 5, 5) + _days(2012, 1, 7, 7)))
    evidence = check.evidence
    assert check.status == "ok"
    assert (evidence["unexplained_zero_days_cur"], evidence["caution_bar_days_cur"]) == (3.0, 6.956)


def test_d1_learns_from_up_to_three_years_so_the_previous_months_season_is_known() -> None:
    """The seasonal shop, the file running to 15 December 2023: the current
    month is November, the previous October. The frame's 24-month window
    holds one other October (2022); D1's 36-month window also holds October
    2021, so each history October has its partner, both are learned, and
    October 2023's 29 zero days are expected: "ok" with nothing missing. (At
    exactly two years the one October has no partner but the month under
    test, which never vouches for itself - the badge then cautions, review 1
    F2: a gap repeated a year apart cannot be told from a closure.)"""
    first, last = date(2021, 1, 1), date(2023, 12, 15)
    every = [first + timedelta(days=i) for i in range((last - first).days + 1)]
    closed = tuple(d for d in every if not (4 <= d.month <= 9 or d.day in (1, 15)))
    _, _, _, check = _run(daily_rows(first, last, skip=closed))
    evidence = check.evidence
    assert (check.status, evidence["gapped_history_months"], evidence["learned_from_months"]) == ("ok", [], 33)
    assert (evidence["zero_days_prev"], evidence["unexplained_zero_days_prev"]) == (29, 0.0)


def test_a_gap_repeated_a_year_apart_is_not_read_as_the_season() -> None:
    """3E1b review 1, F2: both Marches miss the 10th-19th, daily otherwise.
    With the compared month allowed to vouch for its year-ago copy, March
    2022 stayed learned and then expected March 2023's 10 zero days: "ok".
    Now March 2022 is measured against the other learned months - March 2021
    has none - and excluded; March 2023 expects 0 and cautions, 10 days."""
    gap = tuple(date(y, 3, d) for y in (2022, 2023) for d in range(10, 20))
    _, _, headline, check = _run(daily_rows(date(2021, 1, 1), date(2023, 3, 31), skip=gap))
    evidence = check.evidence
    assert (check.status, evidence["gapped_history_months"], evidence["unexplained_zero_days_cur"]) \
        == ("caution", ["2022-03"], 10.0)
    assert headline.rule == 2


def test_a_bank_holiday_in_a_short_history_is_no_caution() -> None:
    """3E1b review 1, F3: a shop open daily but on the first Monday of May,
    exported from January 2010 - four months before. Nothing it learned from
    has a zero day, so its spread is 0; with under a year of history the
    floor is 3E1's 3 days, and one closed Monday is no caution (at one day it
    was, on the Online Retail II sample's bank holidays)."""
    _, _, _, check = _run(daily_rows(date(2010, 1, 1), date(2010, 5, 31), skip=(date(2010, 5, 3),)))
    evidence = check.evidence
    assert (check.status, evidence["caution_min_days"], evidence["unexplained_zero_days_cur"]) == ("ok", 3.0, 1.0)


def test_a_year_ago_month_is_measured_against_the_other_learned_months() -> None:
    """A shop closed on the first Monday of every month; January 2011 (the
    year-ago current month) also closes the 10th. D1 learns from the 24
    months before January 2012 but December 2011 (it holds 25 complete
    months back to December 2009). Against the 23 others - 23 closed Mondays
    of 99 - January 2011's five Mondays expect 5 x 23 / 99 = 1.162 and it has
    2: 0.838 excess, so T2 is refused. Counting January 2011 among its own
    expectation would lower it."""
    closed = []
    for year, number in [(2009, 12)] + [(y, m) for y in (2010, 2011) for m in range(1, 13)] + [(2012, 1)]:
        day = date(year, number, 1)
        closed.append(day + timedelta(days=(7 - day.weekday()) % 7))
    _, verdicts, _, check = _run(daily_rows(date(2009, 12, 1), date(2012, 1, 31),
                                            skip=(*closed, date(2011, 1, 10))))
    assert check.evidence["learned_from_months"] == 24
    assert verdicts["T2"].verdict == "inconclusive"
    assert verdicts["T2"].evidence["excess_zero_days_year_ago_cur"] == round(2 - 5 * 23 / 99, 3)


def test_a_new_year_closure_seen_once_explains_the_next_one() -> None:
    """3E1b review 2, N1 (the Online Retail II sample's 2011-01): closed 2-3
    January every year, a 13-month file, the current month January 2024. The
    learned months' only zero days are January 2023's Monday and Tuesday, so
    the pattern expects 5 x 1/52 for each of January 2024's five Mondays and
    Tuesdays: 0.192, and 2 are 1.808 beyond it. January 2023 held the same
    1.808 beyond its own pattern - under 3E1's 3 days, it stays learned (at
    one day it was excluded as a gap, and this month cautioned) - so the
    season expects 2.0 and nothing is unexplained."""
    closed = (date(2023, 1, 2), date(2023, 1, 3), date(2024, 1, 2), date(2024, 1, 3))
    _, _, _, check = _run(daily_rows(date(2022, 12, 1), date(2024, 1, 31), skip=closed))
    evidence = check.evidence
    assert (check.status, evidence["gapped_history_months"], evidence["learned_from_months"]) == ("ok", [], 12)
    assert (evidence["excess_zero_days_cur"], evidence["seasonal_expected_zero_days_cur"],
            evidence["unexplained_zero_days_cur"]) == (1.808, 2.0, 0.0)


def test_an_annual_closure_teaches_no_weekday_habit() -> None:
    """3E1b review 3, R1: closed 1-21 August every year, daily otherwise, 36
    months; April 2019 (the previous month) loses the 10th. Spread over every
    weekday, the Augusts made the pattern expect about 0.8 zero days in April,
    so the lost day was no excess, B1's refusal lifted and B1 took the
    headline. The Augusts are learned for their season but teach no weekday:
    April expects 0, the day is 1.0 beyond it, B1 is refused and D1 cautions
    on the previous month."""
    closed = tuple(date(y, 8, d) for y in (2016, 2017, 2018) for d in range(1, 22)) + (date(2019, 4, 10),)
    _, verdicts, headline, check = _run(daily_rows(date(2016, 4, 1), date(2019, 5, 31), skip=closed))
    evidence = check.evidence
    assert sorted(set(evidence["learned_months"]) - set(evidence["weekday_months"])) == [
        "2016-08", "2017-08", "2018-08"]
    assert set(evidence["zero_rate_by_weekday"].values()) == {0.0}
    assert (evidence["expected_zero_days_prev"], evidence["excess_zero_days_prev"]) == (0.0, 1.0)
    assert (check.status, verdicts["B1"].verdict) == ("caution", "inconclusive")
    assert headline.hypothesis_id != "B1"


def test_t2_reads_a_year_ago_month_on_the_weekday_months_too() -> None:
    """The same shop; May 2018, the year-ago current month, loses the 15th.
    Against the weekday months other than itself - the Augusts set aside - it
    expects 0, so the day is 1.0 beyond and T2 is refused."""
    closed = tuple(date(y, 8, d) for y in (2016, 2017, 2018) for d in range(1, 22)) + (date(2018, 5, 15),)
    _, verdicts, _, _ = _run(daily_rows(date(2016, 4, 1), date(2019, 5, 31), skip=closed))
    assert (verdicts["T2"].verdict, verdicts["T2"].evidence["excess_zero_days_year_ago_cur"]) == ("inconclusive", 1.0)
