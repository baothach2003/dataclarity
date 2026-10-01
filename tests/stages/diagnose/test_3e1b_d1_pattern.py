"""Session 3E1b, parts A and B and 2E-u F5: how D1 learns a shop's pattern of
days with no sales, and when it cautions (stages/diagnose/d1_pattern.py).

Every figure below is worked by hand from the MonthZeros given: zero-sale
days and calendar days per weekday (Monday first). The rule, chosen by the
method's pre-registered sweep (C:\\Users\\Happy\\3E1b-method.txt, amendment 3
after review 1): caution when the excess is at least the floor (one whole day
with a full year of history, 3E1's 3 days before) AND above the shop's own
spread - the larger of median + K x 1.4826 x MAD of the learned months'
leave-one-out excesses, and K x the binomial standard deviation of the
month's zero days (K = D1_SPREAD_K, 2.5).
"""

import math

import pytest

from stages.diagnose.d1_pattern import (MonthZeros, cautions, expected_zero_days, floor_for, judge, learn,
                                        loo_excess, pattern_zero_days, spread, weekday_months, zero_rates)
from stages.diagnose.thresholds import (D1_CAUTION_MIN_DAYS, D1_CAUTION_MIN_DAYS_SHORT, D1_FULL_YEAR_MONTHS,
                                        D1_HISTORY_MAX_MONTHS, D1_SPREAD_K)

FOUR = (4,) * 7  # a 28-day month: four of each weekday


def month(zeros: tuple[int, ...] = (0,) * 7, days: tuple[int, ...] = FOUR) -> MonthZeros:
    return MonthZeros(zeros=zeros, days=days)


def mondays(closed: int) -> MonthZeros:
    """A 28-day month whose only zero-sale days are `closed` Mondays."""
    return month((closed, 0, 0, 0, 0, 0, 0))


def test_the_constants_are_the_ones_the_sweep_chose() -> None:
    assert (D1_CAUTION_MIN_DAYS, D1_SPREAD_K) == (1.0, 2.5)
    # Amendment 3 (review 1): the one-day floor from a full year; D1's window.
    assert (D1_FULL_YEAR_MONTHS, D1_CAUTION_MIN_DAYS_SHORT, D1_HISTORY_MAX_MONTHS) == (12, 3.0, 36)


@pytest.mark.parametrize("candidates,floor", [(11, 3.0), (12, 1.0), (24, 1.0), (0, 3.0)])
def test_one_whole_day_needs_a_full_year_of_history(candidates: int, floor: float) -> None:
    assert floor_for(candidates) == floor


# --- the learned rates and the expectation -------------------------------------------------------


def test_zero_rates_pool_the_learned_months_per_weekday() -> None:
    # Mondays: 1 + 3 zero days over 4 + 4 Mondays = 0.5; Sundays 2 of 8 = 0.25.
    months = {"2023-01": month((1, 0, 0, 0, 0, 0, 2)), "2023-02": month((3, 0, 0, 0, 0, 0, 0))}
    assert zero_rates(months, ["2023-01", "2023-02"]) == (0.5, 0.0, 0.0, 0.0, 0.0, 0.0, 0.25)


def test_the_expectation_is_the_rates_times_the_months_weekdays() -> None:
    # Rates (0.5, 0, .., 0.25) on a month with five Mondays and four Sundays: 2.5 + 1.0.
    months = {"2023-01": month((1, 0, 0, 0, 0, 0, 2)), "2023-02": month((3, 0, 0, 0, 0, 0, 0)),
              "2023-05": month(days=(5, 5, 5, 4, 4, 4, 4))}
    assert expected_zero_days(months, "2023-05", ["2023-01", "2023-02"]) == pytest.approx(3.5)


def test_the_same_month_of_another_year_raises_the_expectation() -> None:
    """A seasonal shop's off-season month (Thach, 3E1: D1 needs a notion of the
    shop's season): November 2022 had 27 zero days of 30, so November 2023's
    27 are expected, not 'missing'. Two Novembers: their mean, 23."""
    off = (4, 4, 4, 4, 4, 4, 3)  # 27 zero days in a 30-day month (5 Mondays, Tuesdays)
    thirty = (5, 5, 4, 4, 4, 4, 4)
    months = {"2023-06": month(days=(4, 4, 4, 5, 5, 4, 4)), "2022-11": month(off, thirty),
              "2021-11": month((3, 3, 3, 3, 3, 3, 1), thirty), "2023-11": month(off, thirty)}
    # The pattern pools June with November 2022 (13.5 here); the allowance gives November 2022's 27.
    assert expected_zero_days(months, "2023-11", ["2023-06", "2022-11"]) == 27.0
    # Both Novembers learned: (19 + 27) / 2 = 23; the pattern now gives less.
    learned = ["2023-06", "2022-11", "2021-11"]
    pattern = sum(r * d for r, d in zip(zero_rates(months, learned), thirty))
    assert pattern < 23
    assert expected_zero_days(months, "2023-11", learned) == 23.0


def test_the_allowance_scales_by_the_months_length_and_never_lowers_the_expectation() -> None:
    """February 2024 (29 days) was closed throughout; January 2023 never. The
    rates: Monday 5 / 10, Tuesday and Wednesday 4 / 9, the rest 4 / 8. The
    pattern for February 2023 (four of each): 4 x (0.5 + 8/9 + 2) = 13.556;
    for February 2024: 2.5 + 32/9 + 8 = 14.056, so it held 29 - 14.056 =
    14.944 beyond it, x 28 / 29 = 14.429. Expected 13.556 + 14.429."""
    leap = (5, 4, 4, 4, 4, 4, 4)
    months = {"2024-02": month(leap, leap), "2023-01": month(days=(5, 5, 5, 4, 4, 4, 4)), "2023-02": month()}
    pattern = 4 * (0.5 + 8 / 9 + 2)
    beyond = (29 - (2.5 + 32 / 9 + 8)) * 28 / 29
    assert expected_zero_days(months, "2023-02", ["2024-02", "2023-01"]) == pytest.approx(pattern + beyond)
    # A same-month partner with fewer zeros than its pattern expects changes nothing.
    months2 = {"2022-03": month(), "2023-01": month((4,) * 7), "2023-03": month(days=(4, 4, 5, 5, 5, 4, 4))}
    # Rates: (0 + 4) / (4 + 4) = 0.5 everywhere; March 31 days -> 15.5; the partner's 0 is lower.
    assert expected_zero_days(months2, "2023-03", ["2022-03", "2023-01"]) == 15.5


def test_the_allowance_is_what_the_same_month_held_beyond_its_own_weekdays() -> None:
    """3E1b review 2, N4: a shop closed on Sundays. October 2017 had five
    Sundays (5 zero days), October 2018 four: its raw count expected 5 and a
    lost Wednesday hid. October 2017 held nothing beyond its own pattern
    (rate 1 on Sundays), so October 2018 expects its own 4 Sundays."""
    months = {"2017-10": month((0, 0, 0, 0, 0, 0, 5), (5, 4, 4, 4, 4, 5, 5)),
              "2018-06": month((0, 0, 0, 0, 0, 0, 4)),
              "2018-10": month((0, 0, 0, 0, 0, 0, 4), (5, 5, 5, 4, 4, 4, 4))}
    assert expected_zero_days(months, "2018-10", ["2017-10", "2018-06"]) == 4.0


def test_the_pattern_alone_ignores_the_same_month_of_other_years() -> None:
    # The two expectations (review 1, F1): November 2022's 27 raise the
    # season-adjusted one; the pattern alone is the rates' 13.5.
    off = (4, 4, 4, 4, 4, 4, 3)
    thirty = (5, 5, 4, 4, 4, 4, 4)
    months = {"2023-06": month(days=(4, 4, 4, 5, 5, 4, 4)), "2022-11": month(off, thirty), "2023-11": month(off, thirty)}
    learned = ["2023-06", "2022-11"]
    assert pattern_zero_days(months, "2023-11", learned) == pytest.approx(13.5)
    assert expected_zero_days(months, "2023-11", learned) == 27.0


# --- the spread: the shop's own month-to-month variation -------------------------------------------


def test_leave_one_out_excess_is_each_month_against_the_others() -> None:
    """Four 28-day months closed on 0, 1, 2, 3 Mondays. Without month h the
    Monday rate is (6 - z_h) / 12, so the expectation is 4 x that = (6 - z) / 3
    and e = z - (6 - z) / 3 = (4z - 6) / 3: -2, -2/3, 2/3, 2."""
    months = {f"2023-0{i + 1}": mondays(z) for i, z in enumerate((0, 1, 2, 3))}
    e = loo_excess(months, list(months))
    assert [round(e[m], 6) for m in months] == [-2.0, round(-2 / 3, 6), round(2 / 3, 6), 2.0]


def test_the_spread_takes_the_larger_of_the_mad_and_the_binomial_terms() -> None:
    """Same four months. Median of e is 0; |e| are 2, 2/3, 2/3, 2, so the MAD is
    4/3 and the MAD term 2.5 x 1.4826 x 4/3 = 4.942. The binomial term for a
    28-day month: Monday rate 6/16 = 0.375, 4 x 0.375 x 0.625 = 0.9375,
    sqrt = 0.9682, x 2.5 = 2.4206. The spread is the larger, 4.942."""
    months = {f"2023-0{i + 1}": mondays(z) for i, z in enumerate((0, 1, 2, 3))}
    months["2023-05"] = month()
    assert spread(months, "2023-05", ["2023-01", "2023-02", "2023-03", "2023-04"]) == pytest.approx(
        2.5 * 1.4826 * 4 / 3)


def test_identical_months_leave_only_the_binomial_term() -> None:
    """Four months each closed on 2 of 4 days of every weekday: rate 0.5, every
    leave-one-out excess 0, MAD 0. Binomial: 28 x 0.25 = 7, sqrt 2.6458, x 2.5."""
    months = {f"2023-0{i + 1}": month((2,) * 7) for i in range(4)}
    months["2023-05"] = month()
    assert spread(months, "2023-05", list(months)[:4]) == pytest.approx(2.5 * math.sqrt(7))


def test_a_shop_that_never_misses_a_day_has_no_spread() -> None:
    months = {f"2023-0{i + 1}": month() for i in range(5)}
    assert spread(months, "2023-05", list(months)[:4]) == 0.0


# --- caution --------------------------------------------------------------------------------------


@pytest.mark.parametrize("excess,bar,floor,expected", [
    (1.0, 0.0, 1.0, True),    # one whole lost day where the shop never misses one (2E-u F5)
    (0.99, 0.0, 1.0, False),  # under a whole day
    (5.0, 5.0, 1.0, False),   # at the spread: within the shop's own variation
    (5.01, 5.0, 1.0, True),
    (3.0, 6.9, 1.0, False),   # the old rule's 3 days, inside a sparse shop's spread (part A)
    (2.0, 0.0, 3.0, False),   # under a year of history: a bank holiday is not a gap (review 1, F3)
    (3.0, 0.0, 3.0, True),
])
def test_caution_needs_the_floor_and_more_than_the_spread(excess: float, bar: float, floor: float,
                                                          expected: bool) -> None:
    assert cautions(excess, bar, floor) is expected


# --- learning: which history months teach the pattern (part B) -------------------------------------


def test_a_half_gapped_history_month_is_not_learned_from() -> None:
    """Five 28-day months that never miss a day and one missing 14 (2 of each
    weekday): against the others it expects 0 and finds 14 - over the floor
    (3 days: six months are under a year) and over the others' spread of 0. It
    is excluded; the rest stay."""
    months = {f"2023-0{i + 1}": month() for i in range(5)}
    months["2023-06"] = month((2,) * 7)
    learned, excluded = learn(months, list(months))
    assert (learned, excluded) == (["2023-01", "2023-02", "2023-03", "2023-04", "2023-05"], ["2023-06"])


def test_under_a_year_a_closed_day_or_two_is_no_gap_to_exclude() -> None:
    # Six months, one with 2 zero days (a bank holiday and a closed Monday):
    # over the others' spread of 0, but under the 3-day floor of a history
    # shorter than a year - it stays learned (review 1, F3).
    months = {f"2023-0{i + 1}": month() for i in range(5)}
    months["2023-06"] = month((2, 0, 0, 0, 0, 0, 0))
    assert learn(months, list(months))[1] == []


def test_months_that_disagree_among_themselves_exclude_nothing() -> None:
    """Three 28-day months with 0, 21 and 7 zero days. The largest excess is
    February's: 21 against the others' rate (0 + 1) / 8 x 28 = 3.5, so 17.5.
    The two left disagree too - January -7 against March's rate, March +7
    against January's - so their spread is 2.5 x 1.4826 x 7 = 25.9, and 17.5
    is inside it: with a history this short and this uneven there is no
    pattern to call February a gap against (a known limit of short files)."""
    months = {"2023-01": month(), "2023-02": month((3,) * 7), "2023-03": month((1,) * 7)}
    assert learn(months, list(months)) == (["2023-01", "2023-02", "2023-03"], [])


def test_a_month_its_same_month_of_another_year_explains_is_kept() -> None:
    """October 2021 and October 2022 have 28 zero days each (off-season); the
    other history months none. Each expects the other's 28: the shop's season,
    both stay. One October alone is excluded as a gap."""
    months = {"2023-06": month(), "2023-07": month(), "2023-08": month(),
              "2021-10": month((4,) * 7), "2022-10": month((4,) * 7)}
    both = ["2023-06", "2023-07", "2023-08", "2021-10", "2022-10"]
    assert learn(months, both) == (both, [])
    assert learn(months, both[:-1])[1] == ["2021-10"]


# --- mutation check (3E1b): each test pins a line a mutant changed ------------------------------------


def test_a_month_never_vouches_for_itself() -> None:
    # Even when the month is among those passed, its own count is no "same
    # month of another year": learned with June, every weekday's rate is
    # 4 / 8 = 0.5, so the pattern's 14 - not its own 28.
    months = {"2023-06": month(), "2023-11": month((4,) * 7)}
    assert expected_zero_days(months, "2023-11", ["2023-06", "2023-11"]) == 14.0


def test_the_mad_term_is_centred_on_the_median_excess() -> None:
    """Four 28-day months closed on 0, 0, 1, 4 Mondays: e = (4z - 5) / 3 =
    -5/3, -5/3, -1/3, 11/3; median -1; |e + 1| = 2/3, 2/3, 2/3, 14/3, MAD 2/3.
    The target month has no Monday, so its binomial term is 0 (every other
    weekday's rate is 0) and the spread is -1 + 2.5 x 1.4826 x 2/3 = 1.471."""
    months = {f"2023-0{i + 1}": mondays(z) for i, z in enumerate((0, 0, 1, 4))}
    months["2023-05"] = month(days=(0, 4, 4, 4, 4, 4, 4))
    assert spread(months, "2023-05", ["2023-01", "2023-02", "2023-03", "2023-04"]) == pytest.approx(
        -1 + 2.5 * 1.4826 * 2 / 3)


def test_a_weekday_no_learned_month_holds_has_no_zero_rate() -> None:
    assert zero_rates({"2023-01": month(days=(0, 4, 4, 4, 4, 4, 4))}, ["2023-01"]) == (0.0,) * 7


# --- review 2 --------------------------------------------------------------------------------------


def test_judge_keys_the_floor_on_the_months_it_learned() -> None:
    """Twelve candidates, two of them missing 14 days: both are excluded (14
    over 3 days and a spread of 0), ten are learned - under a full year, so
    the floor is 3E1's 3 days and two lost days in the current month do not
    caution (review 2, N1: keyed on candidates the floor was one day)."""
    months = {f"2022-{m:02d}": month() for m in range(1, 13)}
    months["2022-03"] = months["2022-07"] = month((2,) * 7)
    months["2023-01"] = month((1, 1, 0, 0, 0, 0, 0))
    months["2022-12"] = month()
    candidates = [f"2022-{m:02d}" for m in range(1, 12)] + ["2021-12"]
    months["2021-12"] = month()
    judged = judge(months, candidates, "2023-01", "2022-12")
    assert judged is not None
    assert (sorted(judged.excluded), len(judged.learned), judged.floor) == (["2022-03", "2022-07"], 10, 3.0)
    assert (judged.current.unexplained, judged.current.flagged, judged.blocked) == (2.0, False, False)


def test_judge_blocks_on_half_a_month_unexplained_and_says_nothing_when_nothing_is_learned() -> None:
    months = {f"2022-{m:02d}": month() for m in range(1, 13)}
    months["2023-01"] = month((2,) * 7)   # 14 of 28
    judged = judge(months, [f"2022-{m:02d}" for m in range(1, 12)], "2023-01", "2022-12")
    assert judged is not None and judged.blocked and judged.current.flagged
    months["2023-01"] = month((2, 2, 2, 2, 2, 2, 1))  # 13 of 28: under half
    assert not judge(months, [f"2022-{m:02d}" for m in range(1, 12)], "2023-01", "2022-12").blocked
    assert judge(months, [], "2023-01", "2022-12") is None


def test_the_binomial_floor_reads_the_months_own_expected_rate() -> None:
    """Review 3, R1's fix: six 28-day months that never close and October 2022
    closed on 21 of 28 days (3 of each weekday). October is learned for its
    season but teaches no weekday: the rates are 0. October 2023 expects
    0 + 21 = 21, a rate of 0.75 on every day, so its binomial floor is
    2.5 x sqrt(28 x 0.75 x 0.25) = 5.73 - not the in-season rates' 0, which
    cautioned an off-season month's ordinary 1-5 trading days."""
    months = {f"2022-0{i}": month() for i in range(1, 7)}
    months["2022-10"] = month((3,) * 7)
    months["2023-10"] = month((3,) * 7)
    learned = [*[f"2022-0{i}" for i in range(1, 7)], "2022-10"]
    weekdays = learned[:-1]
    assert expected_zero_days(months, "2023-10", learned, weekdays) == 21.0
    assert spread(months, "2023-10", learned, weekdays) == pytest.approx(2.5 * math.sqrt(28 * 0.75 * 0.25))


def test_a_short_annual_closure_teaches_no_weekday_either() -> None:
    """Two Augusts each closed five days (Monday to Friday once), six months
    that never close. Against the others' weekday pattern each August holds
    5 - (the other August's 1 in 28 Mondays-to-Fridays x 20 such days) = 4.29
    days, over 3 and over a pattern spread with no season in it (0): both are
    set aside from the weekday rates. Judged with the season's own variance
    (about 4.8) they stayed."""
    months = {f"2022-0{i}": month() for i in range(1, 7)}
    months["2021-08"] = months["2022-08"] = month((1, 1, 1, 1, 1, 0, 0))
    assert weekday_months(months, list(months)) == [f"2022-0{i}" for i in range(1, 7)]
