"""Decision 1 redesigned (Thach, 2026-10-03), with its second amendment
(Thach, 2026-10-04, on the thirteenth report): when 4A's rule claims a season
- computed once, by one shared function on one window, for stages 3 and 4 -
this month's change is compared with the same calendar month's change in the
earlier years, against the typical size of such year-on-year differences; no
seasonal index is estimated. Three bands on |gap| / typical: under 2 the
season fact, 2 to under 4 the raw gate exactly as before, 4 or more a stated
shortfall or excess naming no cause. Written before the code (method:
C:/Users/Happy/season-fact-method.txt, amendment 2). Every figure worked by
hand."""

import pytest

from contracts.diagnosis import HeadlineMovement, SeasonChange
from shared.periods import shift_month
from stages.diagnose.movement import band, compare_with_season
from stages.diagnose.season_headline import beyond, consistent

SEASON = dict(zip([f"{m:02d}" for m in range(1, 13)],
                  [0.7, 0.7, 0.8, 0.9, 1.0, 1.0, 0.9, 0.9, 1.0, 1.1, 1.6, 1.4]))
# Review 1, H2: "the tested causes do not explain the shortfall" was false in
# S13 itself - lapsed customers, a tested cause, ARE the shortfall; they are
# measured against last month, where they moved against the change. Review 2,
# #6: "measured against last month" was false of T2, measured against the
# same months a year earlier.
STATED = "None of the tested causes measures this gap from the season, so none is named for the shortfall."


def _months(first: str, count: int) -> list[str]:
    return [shift_month(first, i) for i in range(count)]


def _revenue(months: list[str], wobble: dict[str, float] | None = None) -> dict[str, float]:
    # 1,000 x the month's season, x (1 + wobble) where a month is given one.
    return {m: 1000.0 * SEASON[m[5:]] * (1 + (wobble or {}).get(m, 0.0)) for m in months}


def _noisy(months: list[str]) -> dict[str, float]:
    # Every month but October and November off its season by -2%, 0 or +2%,
    # cycling with the year, so a month rarely repeats its year-ago change and
    # the typical gap is above 0 (review 3: a typical of 0 sizes nothing);
    # each October -> November change stays the season's +45.45...%.
    return _revenue(months, {m: 0.02 * ((int(m[:4]) + int(m[5:])) % 3 - 1) for m in months
                             if m[5:] not in ("10", "11")})


# --- the bands (Thach: "under 2", "2 to under 4", "4 or more") ----------------------------------


@pytest.mark.parametrize("gap,typical,expected", [
    (0.0, 0.0, "consistent"),      # a season repeated exactly: nothing to explain
    (0.1, 0.0, "excess"),          # any gap beyond a typical of 0 is more than four times it
    (-0.1, 0.0, "shortfall"),
    (3.99, 2.0, "consistent"),     # r = 1.995
    (4.0, 2.0, "inconclusive"),    # r = 2: "2 to under 4"
    (-7.99, 2.0, "inconclusive"),  # r = 3.995
    (-8.0, 2.0, "shortfall"),      # r = 4: "4 or more"
    (8.0, 2.0, "excess"),
])
def test_the_band_of_a_gap(gap: float, typical: float, expected: str) -> None:
    assert band(gap, typical) == expected


def test_an_exactly_repeated_season_has_no_gap_however_it_grows() -> None:
    # Review 1, M1: 1% growth every month on an exactly repeating season -
    # every month's change equals its year-ago change but for float residue,
    # which read as a gap "at least four times" a residue typical.
    months = _months("2009-12", 24)
    revenue = {m: 1000.0 * SEASON[m[5:]] * 1.01 ** i for i, m in enumerate(months)}
    found = compare_with_season(months, revenue, "2011-11")
    assert found is not None
    assert (found.difference_pct, found.typical_pct, found.band) == (0.0, 0.0, "consistent")


# --- the comparison -------------------------------------------------------------------------------


def test_a_month_that_moves_as_last_year_is_consistent_with_the_season() -> None:
    """Two years of the same season: every month moves exactly as its year-ago
    month, so every difference is 0, and November's +45.45...% (1.6 / 1.1)
    is last November's."""
    months = _months("2009-12", 24)
    found = compare_with_season(months, _revenue(months), "2011-11")
    assert found is not None
    assert found.expected_change_pct == pytest.approx(100 * (1.6 / 1.1 - 1))
    assert (found.years, found.difference_pct, found.typical_pct) == (1, pytest.approx(0.0), pytest.approx(0.0))
    # 2011-01 .. 2011-11 have their year-ago pair in the window (2010-12's
    # needs 2009-11); the current month aside: 10.
    assert found.differences == 10
    assert (found.band, found.beyond_factor) == ("consistent", 4.0)


def test_the_typical_difference_is_the_median_over_the_other_months() -> None:
    """Every month of the second year moved 2 points more than its year-ago
    month: the typical difference is 2; November moved 3 points more - under
    2 x 2."""
    months = _months("2009-12", 24)
    revenue = _revenue(months)
    # Year two: every month's change 2 points above last year's, November 3.
    for i, month in enumerate(months[13:], start=13):  # the months with a year-ago pair
        before = months[i - 1]
        last = revenue[shift_month(month, -12)] / revenue[shift_month(before, -12)] - 1
        bump = 0.03 if month == "2011-11" else 0.02
        revenue[month] = revenue[before] * (1 + last + bump)
    found = compare_with_season(months, revenue, "2011-11")
    assert found is not None
    assert found.typical_pct == pytest.approx(2.0)
    assert found.difference_pct == pytest.approx(3.0)
    assert found.band == "consistent"


def test_a_month_far_below_last_years_change_is_a_shortfall() -> None:
    # November's rise cut to +3% against last year's +45.45%: a gap of about
    # -42 points against a typical of 0.
    months = _months("2009-12", 24)
    revenue = _noisy(months)
    revenue["2011-11"] = revenue["2011-10"] * 1.03
    found = compare_with_season(months, revenue, "2011-11")
    assert found is not None and found.band == "shortfall"
    assert found.difference_pct == pytest.approx(3.0 - 100 * (1.6 / 1.1 - 1))


def test_a_month_far_above_last_years_change_is_an_excess() -> None:
    # November up 80% against last year's +45.45%: +34.5 points.
    months = _months("2009-12", 24)
    revenue = _noisy(months)
    revenue["2011-11"] = revenue["2011-10"] * 1.80
    found = compare_with_season(months, revenue, "2011-11")
    assert found is not None and found.band == "excess" and found.typical_pct > 0
    assert found.difference_pct == pytest.approx(80.0 - 100 * (1.6 / 1.1 - 1))


def test_with_three_years_the_expected_change_is_the_median_of_the_earlier_years() -> None:
    months = _months("2008-12", 36)
    revenue = _noisy(months)
    # The two earlier Novembers rose 40% and 50% (October unchanged): median 45%.
    revenue["2009-11"] = revenue["2009-10"] * 1.40
    revenue["2010-11"] = revenue["2010-10"] * 1.50
    found = compare_with_season(months, revenue, "2011-11")
    assert found is not None and found.years == 2
    assert found.expected_change_pct == pytest.approx(45.0)


def test_a_window_reaching_two_years_back_by_one_month_compares_both() -> None:
    # 26 months, 2009-10 .. 2011-11 (the scenarios' shape): the November two
    # years back has its October in the window, so both earlier Novembers
    # count - 40% and 50% (October unchanged): median 45%.
    months = _months("2009-10", 26)
    revenue = _noisy(months)
    revenue["2009-11"] = revenue["2009-10"] * 1.40
    revenue["2010-11"] = revenue["2010-10"] * 1.50
    found = compare_with_season(months, revenue, "2011-11")
    assert found is not None and (found.years, found.expected_change_pct) == (2, pytest.approx(45.0))


def test_an_older_year_is_never_passed_off_as_last_years() -> None:
    # Review 1, L3: last October had no revenue, so last November's change has
    # no base; November two years back has one, but it is not "a year earlier"
    # - no comparison, the raw gate decides.
    months = _months("2008-12", 36)
    revenue = _revenue(months)
    revenue["2010-10"] = 0.0
    assert compare_with_season(months, revenue, "2011-11") is None


def test_changes_near_zero_have_no_gap_from_residue() -> None:
    # Review 2, #2: July and August equal in both years, this August one ulp
    # above July - "+0.000000% far above +0.000000%" before the percent scale.
    months = _months("2009-12", 24)
    revenue = {m: 900.0 if m[5:] in ("07", "08") else 1000.0 * SEASON[m[5:]] for m in months}
    months = months[:-3]  # the window ends in August 2011
    revenue = {m: revenue[m] for m in months}
    revenue["2011-08"] = 900.0 + 1.137e-13
    found = compare_with_season(months, revenue, "2011-08")
    assert found is not None and (found.difference_pct, found.band) == (0.0, "consistent")


def test_a_gap_on_a_bound_but_for_residue_is_on_the_bound() -> None:
    """Review 2, #3: revenue in cents - year one flat at 100.00, year two
    alternating 595.00 and 625.00, November 653.56. Every year-one change is
    0, so this November's gap is its change; exactly, it is 2 x the median of
    the other months' gaps - "2 to under 4", inconclusive - but in floats it
    fell a hair under and read "within"."""
    months = _months("2009-12", 24)
    revenue = {m: 100.0 for m in months[:13]}
    for i, m in enumerate(months[13:-1], start=13):
        revenue[m] = 595.0 if i % 2 == 0 else 625.0
    revenue["2011-11"] = 653.56
    found = compare_with_season(months, revenue, "2011-11")
    assert found is not None and found.band == "inconclusive"
    assert abs(found.difference_pct) == 2 * found.typical_pct


def test_a_typical_of_zero_sizes_no_gap() -> None:
    # Review 3, #2: every other month repeated its year-ago change exactly
    # (fixed fees) - a typical of 0 read any gap, +0.2 points included, as
    # "far". No comparison: the raw gate decides.
    months = _months("2009-12", 24)
    revenue = _revenue(months)
    revenue["2011-11"] *= 1.002
    assert compare_with_season(months, revenue, "2011-11") is None


def test_a_gap_four_times_the_typical_but_for_residue_is_four_times_it() -> None:
    # Review 3, #5: the bound test's shop with November at 1306.12 - 594.00,
    # one ulp under the revenue whose gap is exactly 4 x the typical.
    months = _months("2009-12", 24)
    revenue = {m: 100.0 for m in months[:13]}
    for i, m in enumerate(months[13:-1], start=13):
        revenue[m] = 595.0 if i % 2 == 0 else 625.0
    revenue["2011-11"] = 1306.12 - 594.0
    found = compare_with_season(months, revenue, "2011-11")
    assert found is not None and found.band == "excess"
    assert found.difference_pct == 4 * found.typical_pct


def test_too_few_differences_make_no_comparison() -> None:
    # 18 months: 5 months of year two have a year-ago pair - under 7.
    months = _months("2010-06", 18)
    assert compare_with_season(months, _revenue(months), "2011-11") is None


def test_no_year_ago_change_makes_no_comparison() -> None:
    months = _months("2009-12", 24)
    revenue = _revenue(months)
    revenue["2010-10"] = 0.0  # last October had no revenue: last November's change has no base
    assert compare_with_season(months, revenue, "2011-11") is None


def _season(band: str, *, expected: float = 25.0, gap: float = 2.2, typical: float = 3.0, years: int = 1,
            differences: int = 11) -> SeasonChange:
    return SeasonChange(expected_change_pct=expected, years=years, difference_pct=gap, typical_pct=typical,
                        differences=differences, band=band, beyond_factor=4.0)


def test_the_contract_holds_the_comparison_together() -> None:
    with pytest.raises(ValueError):
        _season("consistent", years=0)
    with pytest.raises(ValueError):
        _season("shortfall", gap=12.0)  # a shortfall is below the season
    with pytest.raises(ValueError):
        _season("excess", gap=-12.0)  # an excess above it
    for band in ("shortfall", "excess"):
        with pytest.raises(ValueError):
            _season(band, gap=0.0)  # a gap of 0 is consistent with the season, never beyond it
    with pytest.raises(ValueError):
        _season("matches")  # the band is a closed vocabulary
    movement = HeadlineMovement(change_pct=45.0, typical_pct=16.0, movements=22, factor=2.0, singled_out=True,
                                reason=None, season=_season("consistent"))
    assert movement.season is not None and movement.season.band == "consistent"
    # Review 1, M5: a band its own numbers contradict - consumers decide on it.
    for wrong in (_season("shortfall", gap=-33.9, typical=8.5),   # 33.9 < 4 x 8.5: inconclusive
                  _season("consistent", gap=7.0, typical=3.0)):   # 7.0 >= 2 x 3.0
        with pytest.raises(ValueError, match="contradict"):
            HeadlineMovement(change_pct=45.0, typical_pct=16.0, movements=22, factor=2.0, singled_out=True,
                             reason=None, season=wrong)


# --- the headline ---------------------------------------------------------------------------------


def _gate(season: SeasonChange | None, *, singled_out: bool = True, typical: float = 16.2) -> HeadlineMovement:
    return HeadlineMovement(change_pct=27.2, typical_pct=typical, movements=22, factor=2.0,
                            singled_out=singled_out, reason=None, season=season)


def test_a_change_consistent_with_the_season_states_both_changes_and_the_gap() -> None:
    from stages.diagnose.headline import choose_headline, hypotheses_note
    from tests.stages.diagnose.test_3e1b_headline_gate import _all, _h, _moved, _trust

    headline = choose_headline(_trust(), _all(_h("T2", "supported", 12.0, 1.0)), None,
                               _moved(_gate(_season("consistent"))))
    assert (headline.rule, headline.hypothesis_id, headline.lens) == (7, None, None)
    assert headline.message == (
        "Revenue went from 1,000.00 to 1,012.00 (+12.00). This month's change (+27.2%) compares with +25.0% in "
        "the same month a year earlier (one earlier year compared); the gap (+2.2 points) is within this "
        "shop's usual year-on-year difference: under twice its median of about 3.0 points over the 11 other "
        "months compared. The change is consistent with the season; no other cause is singled out.")
    # Review 1, M2: the note does not say the change IS seasonal - a real
    # cause can sit inside the season's usual difference.
    assert hypotheses_note(headline) == (
        "This month's change is consistent with the season, so none of the verdicts below is named as the cause: "
        "each shows what its hypothesis measured.")


def test_with_more_years_it_says_the_median_and_how_many() -> None:
    from stages.diagnose.headline import choose_headline
    from tests.stages.diagnose.test_3e1b_headline_gate import _all, _h, _moved, _trust

    headline = choose_headline(_trust(), _all(_h("B1", "supported", 12.0, 1.0)), None,
                               _moved(_gate(_season("consistent", years=3, gap=-1.5))))
    assert ("This month's change (+23.5%) compares with a median of +25.0% in the same month of the 3 earlier "
            "years; the gap (-1.5 points) is within") in headline.message


@pytest.mark.parametrize("singled_out", [True, False])
def test_between_two_and_four_the_raw_gate_decides_exactly_as_before(singled_out: bool) -> None:
    """2 to under 4: HEAD 6e9b224's headline and note, word for word - the
    raw gate is never lifted (Thach, 2026-10-04: lifting it named a cause not
    planted in 29 of 30 S13 seeds)."""
    from stages.diagnose.headline import choose_headline, hypotheses_note
    from tests.stages.diagnose.test_3e1b_headline_gate import _all, _h, _moved, _trust

    hypotheses = _all(_h("C2", "supported", 12.0, 1.0))
    without = choose_headline(_trust(), hypotheses, None, _moved(_gate(None, singled_out=singled_out)))
    within = choose_headline(_trust(), hypotheses, None,
                             _moved(_gate(_season("inconclusive", gap=-7.0), singled_out=singled_out)))
    assert (within.rule, within.hypothesis_id, within.lens, within.message) == (
        without.rule, without.hypothesis_id, without.lens, without.message)
    assert hypotheses_note(within) == hypotheses_note(without)
    assert within.rule == (6 if singled_out else 7)


def test_a_clear_shortfall_is_stated_and_names_no_cause() -> None:
    """4 or more below, where the raw gate keeps every cause out (S13's
    shape): the headline states the shortfall and names nothing - the
    hypotheses measure the change from last month, not the gap from the
    season. True even where the cause the gate kept out does explain the gap
    (review 1, H1 - C2 supported here: "the tested causes do not explain the
    shortfall" was false)."""
    from stages.diagnose.headline import choose_headline, hypotheses_note
    from tests.stages.diagnose.test_3e1b_headline_gate import _all, _h, _moved, _trust

    season = _season("shortfall", expected=48.5, gap=-21.3, typical=4.9, years=2, differences=12)
    headline = choose_headline(_trust(), _all(_h("C2", "supported", 12.0, 1.0)), None,
                               _moved(_gate(season, singled_out=False)))
    assert (headline.rule, headline.hypothesis_id, headline.lens) == (7, None, None)
    assert headline.message == (
        "Revenue went from 1,000.00 to 1,012.00 (+12.00). This month's change (+27.2%) compares with the same "
        "month in the 2 earlier years (median +48.5%): the gap (-21.3 points) is 4.3 times this shop's median "
        f"year-on-year difference of about 4.9 points. {STATED}")
    assert "do not explain" not in headline.message
    # Thach, 2026-10-04 (8D a): the numbers and the multiple, never "far".
    # 8D review, #9: no "far", no bound it may not show, no plural for one year.
    assert hypotheses_note(headline) == (
        "The headline compares this month's change with the same calendar month's change in the year or years "
        "before; the verdicts below describe the change from last month, not that gap: each shows what its "
        "hypothesis measured, and none is named as the cause.")


def test_a_clear_shortfall_with_no_cause_found_is_stated_too() -> None:
    # Nothing supported: the ranking's own rule 7 ("no single tested cause")
    # names no cause either, so the shortfall is stated in its place.
    from stages.diagnose.headline import choose_headline, hypotheses_note
    from tests.stages.diagnose.test_3e1b_headline_gate import _all, _moved, _trust

    season = _season("shortfall", expected=48.5, gap=-21.3, typical=4.9, years=2, differences=12)
    headline = choose_headline(_trust(), _all(), None, _moved(_gate(season)))
    assert headline.rule == 7 and headline.message.endswith(STATED)
    assert hypotheses_note(headline) is not None and "not that gap" in hypotheses_note(headline)


def test_where_the_raw_gate_names_a_cause_it_stands_and_the_gap_is_added() -> None:
    """CLAUDE.md 3.3a, decided alone (method amendment 2, B8): a seasonal shop
    losing customers in a month its season leaves flat - the change from last
    month IS the gap, and HEAD names C2 truly (30 of 30 seeds); "the tested
    causes do not explain the shortfall" would be false there. The engine
    cannot tell that case from a season masking the cause, so the existing
    headline stands, word for word, and the gap is stated after it."""
    from stages.diagnose.headline import choose_headline, hypotheses_note
    from tests.stages.diagnose.test_3e1b_headline_gate import _all, _h, _moved, _trust

    hypotheses = _all(_h("C2", "supported", 12.0, 1.0))
    season = _season("shortfall", expected=48.5, gap=-21.3, typical=4.9, years=2, differences=12)
    head = choose_headline(_trust(), hypotheses, None, _moved(_gate(None)))
    headline = choose_headline(_trust(), hypotheses, None, _moved(_gate(season)))
    assert (headline.rule, headline.hypothesis_id, headline.lens) == (head.rule, "C2", head.lens) == (6, "C2",
                                                                                                    "customers")
    # Review 1, M4: no "also" - it read as if the named cause explained the gap.
    assert headline.message == (
        f"{head.message} This month's change (+27.2%) compares with the same month in the 2 earlier years "
        "(median +48.5%): the gap (-21.3 points) is 4.3 times this shop's median year-on-year difference of "
        "about 4.9 points.")
    assert "do not explain" not in headline.message and " also " not in headline.message
    assert hypotheses_note(headline) is None  # a cause is named: no table note, as before


def test_a_clear_excess_is_stated_the_other_way() -> None:
    from stages.diagnose.headline import choose_headline
    from tests.stages.diagnose.test_3e1b_headline_gate import _all, _h, _moved, _trust

    season = _season("excess", expected=-2.8, gap=30.0, typical=3.0)
    headline = choose_headline(_trust(), _all(_h("B1", "supported", 12.0, 1.0)), None,
                               _moved(_gate(season, singled_out=False)))
    assert headline.rule == 7 and headline.hypothesis_id is None
    assert headline.message.endswith(
        "This month's change (+27.2%) compares with the same month a year earlier (-2.8%): the gap (+30.0 "
        "points) is 10 times this shop's median year-on-year difference of about 3.0 points. None of the tested "
        "causes measures this gap from the season, so none is named for the excess.")


# --- what is printed agrees with what is decided (review 1, L1) -----------------------------------


def test_the_demos_numbers_print_a_gap_that_is_their_difference() -> None:
    # The unanswered plan's 2011-11 (this run's measurement): the gap rounded
    # on its own (-12.1) is not +27.1 - (+39.1); printed as the printed
    # changes' difference it is (review 3, #3).
    season = _season("consistent", expected=39.14152352999991, gap=-12.06382064331202, typical=8.54560525372709,
                     differences=10)
    assert consistent(season, 2.0) == (
        "This month's change (+27.1%) compares with +39.1% in the same month a year earlier (one earlier year "
        "compared); the gap (-12.0 points) is within this shop's usual year-on-year difference: under twice its "
        "median of about 8.5 points over the 10 other months compared. The change is consistent with the "
        "season; no other cause is singled out.")


def test_thirds_print_a_gap_that_is_their_difference() -> None:
    # Review 3, #3: last year 300 -> 400 (+33.33...%), this year 300 -> 500
    # (+66.66...%) - rounded on its own the gap (+33.3...) never matched the
    # printed changes' difference, at any precision.
    season = _season("excess", expected=100 / 3, gap=200 / 3 - 100 / 3, typical=5.43)
    assert ("This month's change (+66.7%) compares with the same month a year earlier (+33.3%): the gap (+33.4 "
            "points) is 6.2 times this shop's median year-on-year difference of about 5.4 points."
            ) in beyond(season, stated=True)


@pytest.mark.parametrize("gap,typical,multiple", [
    (-27.4, 3.9, "7"),       # 27.4 / 3.9 = 7.03
    (-21.3, 4.9, "4.3"),     # 4.35 to one place
    (-33.86, 8.46, "4"),     # 4.002 - never printed under four
    (40.0, 9.9, "4"),        # 4.04
])
def test_the_multiple_is_the_printed_gap_over_the_printed_typical(gap: float, typical: float, multiple: str) -> None:
    band = "shortfall" if gap < 0 else "excess"
    sentence = beyond(_season(band, expected=10.0, gap=gap, typical=typical), stated=False)
    assert f" is {multiple} times this shop's median year-on-year difference" in sentence


def test_the_documented_sentence_is_one_the_code_prints() -> None:
    # Thach's example (-26.9% against +0.6%, a gap of -27.4) does not subtract:
    # printed, the gap is the changes' difference (8D review, #4). CONTRACTS 7
    # quotes this one.
    season = _season("shortfall", expected=0.6, gap=-27.4, typical=3.9, years=2, differences=12)
    assert beyond(season, stated=False) == (
        "This month's change (-26.8%) compares with the same month in the 2 earlier years (median +0.6%): the gap "
        "(-27.4 points) is 7 times this shop's median year-on-year difference of about 3.9 points.")


def test_a_small_typical_prints_close_to_itself() -> None:
    # 8D review, #7: a typical of 0.05 printed "about 0.1" made "300 times"
    # of a gap 600 times it.
    sentence = beyond(_season("excess", expected=10.0, gap=30.0, typical=0.05), stated=True)
    assert "is 600 times this shop's median year-on-year difference of about 0.05 points" in sentence
    # 0.149 to one place is 0.1 - a third off: printed to two (0.15, within 5%).
    sentence = beyond(_season("excess", expected=10.0, gap=30.0, typical=0.149), stated=True)
    assert "is 200 times this shop's median year-on-year difference of about 0.15 points" in sentence


def test_another_factor_is_never_printed_under() -> None:
    # 8D review, #8: at a factor of 4.25 a gap of exactly 4.25 x the typical
    # printed "4.2 times" to one place.
    season = SeasonChange(expected_change_pct=10.0, years=1, difference_pct=-42.5, typical_pct=10.0, differences=11,
                          band="shortfall", beyond_factor=4.25)
    sentence = beyond(season, stated=True)
    assert " 4.2 times" not in sentence and " 4.25 times" in sentence


@pytest.mark.parametrize("stated", [True, False])
@pytest.mark.parametrize("band,gap", [("shortfall", -30.0), ("excess", 30.0)])
def test_no_band_3_sentence_says_far(band: str, gap: float, stated: bool) -> None:
    # Thach, 2026-10-04 (8D a): "far" is the misleading word - about 6-10% of
    # ordinary peak months reach 4x (review 1's simulation).
    from stages.diagnose.headline import BEYOND_NOTE

    for typical in (3.0, 0.0):
        assert "far" not in beyond(_season(band, expected=10.0, gap=gap, typical=typical), stated=stated)
    assert "far" not in BEYOND_NOTE


@pytest.mark.parametrize("gap,typical,shown", [
    (-16.86, 8.44, "the gap (-16.86 points) is within this shop's usual year-on-year difference: under twice its "
                   "median of about 8.44 points"),   # to one place: -16.9 "under twice" 8.4
])
def test_a_consistent_gap_never_prints_over_its_bound(gap: float, typical: float, shown: str) -> None:
    assert shown in consistent(_season("consistent", expected=40.0, gap=gap, typical=typical), 2.0)


def test_a_beyond_gap_never_prints_under_its_bound() -> None:
    # To one place -33.9 "at least four times" 8.5 (34.0) - false.
    sentence = beyond(_season("shortfall", expected=48.5, gap=-33.86, typical=8.46), stated=True)
    assert "the gap (-33.86 points) is 4 times this shop's median year-on-year difference of about 8.46" in sentence


def test_a_change_that_moved_is_never_printed_as_zero() -> None:
    sentence = consistent(_season("consistent", expected=0.0, gap=-0.04, typical=0.5), 2.0)
    assert "This month's change (-0.04%)" in sentence and "-0.0%" not in sentence


def test_a_gap_beyond_a_typical_of_zero_is_not_called_four_times_it() -> None:
    # Every other month repeated its year-ago change exactly: "at least four
    # times ... about 0.0 points" would be true and say nothing.
    sentence = beyond(_season("shortfall", expected=40.8, gap=-28.2, typical=0.0), stated=True)
    assert "the gap (-28.2 points) is beyond this shop's median year-on-year difference of 0 points." in sentence
    assert "four times" not in sentence


def test_a_gap_of_zero_says_so_plainly() -> None:
    # "the gap (+0.0 points) is within ... under twice about 0.0" is false.
    assert consistent(_season("consistent", expected=45.5, gap=0.0, typical=0.0), 2.0) == (
        "This month's change (+45.5%) is the same as in the same month a year earlier (one earlier year "
        "compared). The change is consistent with the season; no other cause is singled out.")


def test_a_typical_under_a_twentieth_of_a_point_is_not_printed_as_zero() -> None:
    # Review 2, #4: "about 0.0 points" for a typical of 0.004.
    sentence = beyond(_season("shortfall", expected=40.8, gap=-28.2, typical=0.004), stated=True)
    assert "about 0.004 points" in sentence and "about 0.0 points" not in sentence


def test_no_precision_agreeing_drops_the_bound_claim() -> None:
    # Review 2, #3: a gap 1e-11 under twice the typical - consistent - prints
    # equal to the bound at every precision up to MOST_PLACES; the sentence
    # then claims no "under twice".
    sentence = consistent(_season("consistent", expected=40.0, gap=-9.99999999999, typical=5.0), 2.0)
    assert "under twice" not in sentence
    assert "compares with this shop's median year-on-year difference of about 5 points" in sentence


def test_a_beyond_gap_with_no_agreeing_precision_claims_no_bound() -> None:
    # Last year's change of 1e-12% prints as 0 at every precision up to
    # MOST_PLACES: the sentence then states the numbers to ten significant
    # digits - never "+0.0000000000%" (review 3, #3) - without "at least four
    # times".
    sentence = beyond(_season("excess", expected=1e-12, gap=30.0, typical=3.0), stated=True)
    assert "four times" not in sentence and "0.0000000000" not in sentence
    assert "the same month a year earlier (+1e-12%)" in sentence
    assert "the gap (+30 points) compares with this shop's median year-on-year difference of about 3 points" \
        in sentence


def test_t2_never_takes_the_headline_beside_a_gap_from_the_season() -> None:
    """Review 2, #1: T2 is the season's own prediction - beside a shortfall
    or an excess it read "consistent with seasonality" then "far above the
    same month". Out of the ranking there: with nothing else named, the gap is
    stated; within the bands, T2 ranks as before."""
    from stages.diagnose.headline import choose_headline
    from tests.stages.diagnose.test_3e1b_headline_gate import _all, _h, _moved, _trust

    hypotheses = _all(_h("T2", "supported", 7.0, 0.58))
    excess = _season("excess", expected=-2.8, gap=30.0, typical=3.0)
    headline = choose_headline(_trust(), hypotheses, None, _moved(_gate(excess)))
    assert (headline.rule, headline.hypothesis_id) == (7, None)
    assert "season" not in headline.message.replace("from the season", "")
    assert "compares with the same month a year earlier (-2.8%)" in headline.message
    inconclusive = _season("inconclusive", gap=-7.0, typical=3.0)
    assert choose_headline(_trust(), hypotheses, None, _moved(_gate(inconclusive))).rule == 5


@pytest.mark.parametrize("band,prev,cur,t2,other,expected,gap,typical", [
    # +50% against last year's +40%: T2 +400 (0.8) beside C1 +150 (0.3).
    ("excess", 1000.0, 1500.0, ("T2", 400.0, 0.8), ("C1", 150.0, 0.3), 40.0, 10.0, 2.0),
    # +40% against last year's +50%: T2 +500 (1.25) beside B1 +240 (0.6).
    ("shortfall", 1000.0, 1400.0, ("T2", 500.0, 1.25), ("B1", 240.0, 0.6), 50.0, -10.0, 2.5),
])
def test_t2_beside_a_weaker_cause_never_promotes_it(band: str, prev: float, cur: float, t2: tuple, other: tuple,
                                                    expected: float, gap: float, typical: float) -> None:
    """Review 3, #1: ranking without T2 named the weaker cause "the
    best-supported explanation" while the table showed T2 fitting better.
    The ranking is 6e9b224's (T2 wins, rule 5); naming T2 beside a gap from
    the season, the gap is stated and nothing is named."""
    from stages.diagnose.headline import choose_headline
    from stages.diagnose.step7_inputs import Changes
    from tests.stages.diagnose.test_3e1b_headline_gate import _all, _h, _trust

    hypotheses = _all(_h(*t2[:1], "supported", *t2[1:]), _h(*other[:1], "supported", *other[1:]))

    def headline(season: SeasonChange | None):
        change = 100 * (cur / prev - 1)
        gate = HeadlineMovement(change_pct=change, typical_pct=10.0, movements=22, factor=2.0, singled_out=True,
                                reason=None, season=season)
        return choose_headline(_trust(), hypotheses, None, Changes(prev, cur, cur - prev, cur - prev, False,
                                                                   movement=gate))

    assert headline(None).rule == 5
    stated = headline(_season(band, expected=expected, gap=gap, typical=typical))
    assert (stated.rule, stated.hypothesis_id) == (7, None)
    assert "best-supported" not in stated.message and "seasonality" not in stated.message
    assert stated.message.endswith(STATED.replace("shortfall", band))


def test_rule_6_naming_t2_beside_a_gap_states_the_gap() -> None:
    # T2 under half the change is ranked as rule 6's, not as context: naming it
    # beside a gap from the season is the same contradiction (review 3, #1).
    from stages.diagnose.headline import choose_headline
    from tests.stages.diagnose.test_3e1b_headline_gate import _all, _h, _moved, _trust

    hypotheses = _all(_h("T2", "supported", 4.8, 0.4))  # under HEADLINE_CONTEXT_MIN_SHARE (0.5)
    without = choose_headline(_trust(), hypotheses, None, _moved(_gate(None)))
    assert (without.rule, without.hypothesis_id) == (6, "T2")
    stated = choose_headline(_trust(), hypotheses, None,
                             _moved(_gate(_season("shortfall", expected=48.5, gap=-21.3, typical=4.9, years=2))))
    assert (stated.rule, stated.hypothesis_id) == (7, None) and stated.message.endswith(STATED)


def test_a_small_gap_is_never_printed_as_zero() -> None:
    # +27.13% against +27.10%: to one place both print 27.1 and the printed
    # difference is 0.0 although the gap is not.
    sentence = consistent(_season("consistent", expected=27.10, gap=0.03, typical=3.0), 2.0)
    assert "the gap (+0.03 points)" in sentence


def test_a_ruled_out_t2_without_a_claim_denies_nothing_true() -> None:
    """8D review, #1: both months rose (+5.6% against last year's +40.8%) but
    T2's share is out of band - "This month moved the same way ... | ruled
    out" denied a true fact. The hypothesis wording's "ruled out" is true:
    last year's change does not explain this one."""
    diagnosis, forecast = _run(_daily_shop("2010-09", 15, SEASON, last_scale=0.75))
    assert forecast.season_years is None
    t2 = next(h for h in diagnosis.hypotheses if h.id == "T2")
    assert (t2.statement, t2.verdict) == ("Last year's change between the same two months explains the change",
                                          "ruled_out")


def test_rule_6_and_the_partial_list_use_the_same_wording() -> None:
    from stages.diagnose.headline import choose_headline
    from stages.diagnose.step7_inputs import Changes
    from tests.stages.diagnose.test_3e1b_headline_gate import _all, _h, _trust

    from stages.diagnose.catalog import BY_ID

    named = choose_headline(_trust(), _all(_h("T2", "supported", 4.8, 0.4)), None,
                            Changes(1000.0, 1012.0, 12.0, 12.0, False))
    t2 = _h("T2", "supported", 4.8, 0.4).model_copy(update={"statement": BY_ID["T2"].render(4.8)})
    named = choose_headline(_trust(), _all(t2), None, Changes(1000.0, 1012.0, 12.0, 12.0, False))
    assert named.message.endswith("The best-supported explanation: last year's change between the same two months "
                                  "explains the change (time lens, 40% of the change).")
    partial = _h("T2", "partial", 3.0, 0.25).model_copy(update={"statement": BY_ID["T2"].render(3.0)})
    listed = choose_headline(_trust(), _all(partial), None, Changes(1000.0, 1012.0, 12.0, 12.0, False))
    assert "Partly consistent: last year's change between the same two months explains the change (T2)." \
        in listed.message
    assert "season" not in (named.message + listed.message).lower()


def test_t2s_refusal_never_says_season_either() -> None:
    # 8D review, #3: T2's rule text is printed in the table - "so it is not a
    # season to compare" beside a forecast that claims no season. Fifteen
    # months; last November lost ten days (its first ten).
    frame = _daily_shop("2010-09", 15, SEASON)
    frame = frame[~frame["Date"].between("2010-11-01", "2010-11-10")]
    diagnosis, forecast = _run(frame)
    assert forecast.season_years is None
    t2 = next(h for h in diagnosis.hypotheses if h.id == "T2")
    assert t2.verdict == "inconclusive" and "year-ago pair" in t2.rule
    assert "season" not in (t2.statement + t2.rule).lower()


def test_a_claimed_season_in_the_inconclusive_band_keeps_rule_5s_seasonality() -> None:
    # 8D review, #12: the production pairing - a claim, a comparison in the
    # inconclusive band, T2 fitting best - rule 5 may say "seasonality".
    from stages.diagnose.headline import choose_headline
    from tests.stages.diagnose.test_3e1b_headline_gate import _all, _h, _moved, _trust

    headline = choose_headline(_trust(), _all(_h("T2", "supported", 12.0, 1.0)), None,
                               _moved(_gate(_season("inconclusive", gap=-7.0, typical=3.0))))
    assert headline.rule == 5
    assert "consistent with seasonality (the same months a year earlier moved the same way)" in headline.message


def test_rules_1_to_4_are_untouched_by_the_season() -> None:
    from contracts.diagnosis import Trust, TrustCheck
    from stages.diagnose.headline import choose_headline
    from tests.stages.diagnose.test_3e1b_headline_gate import _all, _h, _moved

    blocked = Trust(verdict="blocked", checks=[TrustCheck(id="D1", status="blocked", message="cut short",
                                                          evidence={})], limitations=[])
    for band in ("consistent", "shortfall"):
        season = _season(band, gap=2.2 if band == "consistent" else -30.0)
        headline = choose_headline(blocked, _all(_h("T2", "supported", 12.0, 1.0)), None, _moved(_gate(season)))
        assert headline.rule == 1


# --- one claim for stages 3 and 4 (review F4), the pipeline ------------------------------------------


def _daily_shop(first: str, months: int, season: dict[str, float] | None, last_scale: float = 1.0,
                wobble: dict[str, float] | None = None):
    """One product sold every day: 100 a day x the month's season, the last
    month x `last_scale`, a month in `wobble` x its factor."""
    import calendar

    import pandas as pd

    rows = []
    for index, month in enumerate(_months(first, months)):
        year, number = int(month[:4]), int(month[5:])
        factor = ((season or {}).get(month[5:], 1.0) * (last_scale if index == months - 1 else 1.0)
                  * (wobble or {}).get(month, 1.0))
        for day in range(1, calendar.monthrange(year, number)[1] + 1):
            rows.append({"Date": f"{month}-{day:02d}", "Qty": "1", "Price": f"{100 * factor:.4f}",
                         "Product": "Mug", "Cust": f"C{day % 7}"})
    return pd.DataFrame(rows)


def _run(frame):
    from datetime import UTC, datetime

    from stages.analyze.assemble import assemble_metrics
    from stages.diagnose.assemble import diagnose
    from stages.diagnose.inputs import build_run_data
    from stages.predict.forecast import forecast

    mapping = {"Date": "transaction_date", "Qty": "quantity", "Price": "unit_price", "Product": "product_name",
               "Cust": "customer"}
    now = datetime(2026, 10, 3, tzinfo=UTC)
    metrics = assemble_metrics(frame, mapping, now=now)
    return diagnose(build_run_data(frame, mapping, metrics), now), forecast(metrics)


@pytest.mark.parametrize("months", [24, 40])
def test_the_season_shop_states_the_fact_and_both_stages_claim_it(months: int) -> None:
    # 40 months: stage 3's own history stops at 24 - the claim must not.
    diagnosis, forecast = _run(_daily_shop("2009-12" if months == 24 else "2008-08", months, SEASON))
    movement = diagnosis.headline.movement
    assert forecast.season_years is not None
    assert movement is not None and movement.season is not None and movement.season.band == "consistent"
    assert diagnosis.headline.rule == 7 and "consistent with the season" in diagnosis.headline.message
    assert diagnosis.hypotheses_note is not None
    # Review 2, #9: the season's "this month's change" is the size test's.
    assert movement.season.expected_change_pct + movement.season.difference_pct == pytest.approx(movement.change_pct)


def test_the_season_shop_with_its_peak_cut_states_the_shortfall() -> None:
    # Priced per day, so a month's revenue counts its days: last November rose
    # (30 x 160) / (31 x 110) - 1 = +40.8%; this one, at 0.8 of its season,
    # (30 x 128) / (31 x 110) - 1 = +12.6%; every other month repeats - a
    # typical of 0, so the -28.2-point gap is a shortfall.
    # January to September 2011 alternately 2% up and down: the other months
    # no longer repeat their year-ago change exactly, so the typical is not 0
    # (a typical of 0 sizes nothing - review 3, #2); October and November,
    # untouched, keep both changes.
    wobble = {f"2011-{m:02d}": 1.02 if m % 2 else 0.98 for m in range(1, 10)}
    diagnosis, _ = _run(_daily_shop("2009-12", 24, SEASON, last_scale=0.8, wobble=wobble))
    movement = diagnosis.headline.movement
    assert movement is not None and movement.season is not None and movement.season.band == "shortfall"
    assert movement.season.difference_pct == pytest.approx(100 * (3840 / 3410 - 4800 / 3410))
    assert movement.season.typical_pct > 0
    assert "compares with the same month a year earlier (+40.8%)" in diagnosis.headline.message
    assert "times this shop's median year-on-year difference" in diagnosis.headline.message


def test_a_fixed_fee_shop_gets_no_comparison() -> None:
    """Review 3, #2, end to end: 100 members x 50.00 every month, a seasonal
    gift pack in November and December both years (4A claims the season),
    and one 10.00 card in November 2011 - every other month repeats its
    year-ago change exactly, so the typical is 0 and +0.2 points read "far
    above". No comparison; the raw gate decides."""
    import calendar

    import pandas as pd

    rows = []
    for month in _months("2009-12", 24):
        days = calendar.monthrange(int(month[:4]), int(month[5:]))[1]
        for member in range(100):
            rows.append({"Date": f"{month}-{member % 28 + 1:02d}", "Qty": "1", "Price": "50.00",
                         "Product": "Membership", "Cust": f"M{member}"})
        for i in range({"11": 100, "12": 80}.get(month[5:], 0)):
            rows.append({"Date": f"{month}-{i % days + 1:02d}", "Qty": "1", "Price": "50.00", "Product": "Gift pack",
                         "Cust": f"M{i % 100}"})
    rows.append({"Date": "2011-11-15", "Qty": "1", "Price": "10.00", "Product": "Card", "Cust": "M3"})
    diagnosis, forecast = _run(pd.DataFrame(rows))
    assert forecast.season_years is not None  # the season is claimed
    assert diagnosis.headline.movement is not None and diagnosis.headline.movement.season is None
    assert "far " not in diagnosis.headline.message


def test_without_4as_claim_t2_states_the_fact_and_never_says_season() -> None:
    """Thach, 2026-10-04 (8D b): one definition - only 4A's claim may say
    "season". Fifteen months of the season repeat exactly: T2 (the year-ago
    pair) explains the change, but 4A claims nothing on 15 months, so the
    forecast says no seasonality was claimed - and T2 must not say
    "seasonality" beside it (review 1 of decision 1, M3). Its verdict is
    unchanged."""
    diagnosis, forecast = _run(_daily_shop("2010-09", 15, SEASON))
    assert forecast.season_years is None
    t2 = next(h for h in diagnosis.hypotheses if h.id == "T2")
    assert t2.verdict == "supported"
    assert t2.statement == "Last year's change between the same two months explains the change"
    assert "season" not in diagnosis.headline.message.lower()
    assert "moved the same way" in diagnosis.headline.message


def test_with_4as_claim_t2_may_say_seasonality() -> None:
    diagnosis, forecast = _run(_daily_shop("2009-12", 24, SEASON))
    assert forecast.season_years is not None
    assert next(h for h in diagnosis.hypotheses if h.id == "T2").statement == "Seasonality explains the change"


def test_rule_5s_t2_phrase_follows_the_claim() -> None:
    from stages.diagnose.headline import choose_headline
    from stages.diagnose.step7_inputs import Changes
    from tests.stages.diagnose.test_3e1b_headline_gate import _all, _h, _trust

    hypotheses = _all(_h("T2", "supported", 12.0, 1.0))
    claimed = choose_headline(_trust(), hypotheses, None, Changes(1000.0, 1012.0, 12.0, 12.0, False,
                                                                  season_claimed=True))
    unclaimed = choose_headline(_trust(), hypotheses, None, Changes(1000.0, 1012.0, 12.0, 12.0, False))
    assert claimed.rule == unclaimed.rule == 5
    assert "The change is consistent with seasonality (the same months a year earlier moved the same way)" \
        in claimed.message
    assert "The change is consistent with the same months a year earlier, which moved the same way" \
        in unclaimed.message
    assert "season" not in unclaimed.message.lower()


def test_the_catalog_words_t2_by_the_claim() -> None:
    from stages.diagnose.catalog import BY_ID

    assert BY_ID["T2"].render(-5.0, season_claimed=True) == "Seasonality explains the change"
    assert BY_ID["T2"].render(-5.0, season_claimed=False) == "Last year's change between the same two months explains the change"
    assert BY_ID["T1"].render(-5.0, season_claimed=False) == "The calendar explains the change"  # T2's alone


def test_no_season_claimed_no_comparison() -> None:
    diagnosis, forecast = _run(_daily_shop("2009-12", 24, None, last_scale=1.01))
    assert forecast.season_years is None
    assert diagnosis.headline.movement is not None and diagnosis.headline.movement.season is None


def test_the_shared_window_is_the_forecasts() -> None:
    from datetime import UTC, datetime

    from shared.seasonality import season_claim, season_window
    from stages.analyze.assemble import assemble_metrics

    frame = _daily_shop("2009-12", 24, SEASON)
    mapping = {"Date": "transaction_date", "Qty": "quantity", "Price": "unit_price", "Product": "product_name",
               "Cust": "customer"}
    metrics = assemble_metrics(frame, mapping, now=datetime(2026, 10, 3, tzinfo=UTC))
    months, values, note = season_window(metrics)
    assert (months[0], months[-1], len(values), note) == ("2009-12", "2011-11", 24, None)
    cycles, _ = season_claim(metrics)
    assert cycles is not None and len(cycles) == 2
