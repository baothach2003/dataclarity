"""The headline's sentences for a claimed season (Thach, 2026-10-03/04,
decision 1; method C:/Users/Happy/season-fact-method.txt, amendment 2): this
month's change against the same calendar month's change in the earlier
years, stated as a fact. Split from headline.py, which decides WHEN they
stand; this module only words them, from the numbers in
`headline.movement.season` and nothing else.
"""

from contracts.diagnosis import SeasonChange


def consistent(season: SeasonChange, factor: float) -> str:
    """Both changes, the gap and the years compared, so a wide band never
    reads oddly (Thach, 2026-10-04) - in the words of the raw size test's
    "under twice its median"."""
    places = _places(season, factor)
    now, before, gap, typical = _printed(season, places)
    if season.difference_pct == 0:
        same = ("is the same as in the same month a year earlier (one earlier year compared)" if season.years == 1
                else f"is the same as the median of the same month in the {season.years} earlier years")
        return (f"This month's change ({now}) {same}. The change is consistent with the season; no other cause is "
                "singled out.")
    times = "twice" if factor == 2 else f"{factor:g} times"
    earlier = (f"{before} in the same month a year earlier (one earlier year compared)" if season.years == 1 else
               f"a median of {before} in the same month of the {season.years} earlier years")
    bound = (f"is within this shop's usual year-on-year difference: under {times} its median of about {typical} "
             "points" if places else f"compares with this shop's median year-on-year difference of about {typical} "
             "points")
    return (f"This month's change ({now}) compares with {earlier}; the gap ({gap} points) {bound} over the "
            f"{season.differences} other months compared. The change is consistent with the season; no other cause "
            "is singled out.")


def beyond(season: SeasonChange, *, stated: bool) -> str:
    """A clear shortfall or excess against the season. `stated`: the
    headline itself, naming no cause - no tested cause measures the gap from
    the season (the others measure the change from last month, T2 the change
    the season itself predicts), so none is named for it; the sentence must
    stay true where one of them does explain it (reviews 1, H1/H2, and 2,
    #6). Otherwise appended, with no connective, to a headline that names a
    cause (method amendment 2, B8: "also" read as if that cause explained the
    gap)."""
    places = _places(season)
    now, before, gap, typical = _printed(season, places)
    earlier = (f"the same month a year earlier ({before})" if season.years == 1 else
               f"the same month in the {season.years} earlier years (median {before})")
    # Thach, 2026-10-04 (8D a): the numbers and the multiple, never "far" -
    # in review 1's simulation (5% multiplicative noise, a claimed season) 6-10%
    # of ordinary peak months reached 4x.
    if not places:
        size = f"compares with this shop's median year-on-year difference of about {typical} points"
    elif season.typical_pct:
        size = (f"is {_multiple(season, places)} times this shop's median year-on-year difference of about "
                f"{typical} points")
    else:
        size = "is beyond this shop's median year-on-year difference of 0 points"
    sentence = f"This month's change ({now}) compares with {earlier}: the gap ({gap} points) {size}."
    if not stated:
        return sentence
    return (f"{sentence} None of the tested causes measures this gap from the season, so none is named for the "
            f"{season.band}.")


def _multiple(season: SeasonChange, places: int) -> str:
    """|printed gap| / printed typical - the reader's own division - to one
    place ("7 times", "4.3 times"), or to as many more as keep it at or
    beyond `beyond_factor` (`_places` keeps the ratio itself there): a ratio
    of exactly 4.25 at a factor of 4.25 reads "4.25", not "4.2" (8D review,
    #8)."""
    ratio = _ratio(season, places)
    for digits in range(1, 4):
        shown = f"{ratio:.{digits}f}"
        if float(shown) >= season.beyond_factor:
            break
    return shown.rstrip("0").rstrip(".") if "." in shown else shown


def _ratio(season: SeasonChange, places: int) -> float:
    return abs(_printed_gap(season, places)) / round(season.typical_pct, places)


def _printed(season: SeasonChange, places: int | None) -> tuple[str, str, str, str]:
    """The four numbers to `places` decimals, the gap printed as the printed
    changes' difference - "+66.67% ... +33.33%: the gap (+33.34 points)" -
    so a reader's subtraction never disagrees (review 3, #3: thirds and
    sixths carry at every precision). With no agreeing precision, ten
    significant digits, so nothing that moved prints as 0."""
    now = season.expected_change_pct + season.difference_pct
    if places is None:
        return (f"{now:+.10g}%", f"{season.expected_change_pct:+.10g}%", f"{season.difference_pct:+.10g}",
                f"{season.typical_pct:.10g}")
    gap = _printed_gap(season, places)
    return (f"{now:+.{places}f}%", f"{season.expected_change_pct:+.{places}f}%", f"{gap:+.{places}f}",
            f"{season.typical_pct:.{places}f}")


def _printed_gap(season: SeasonChange, places: int) -> float:
    now = season.expected_change_pct + season.difference_pct
    return round(round(now, places) - round(season.expected_change_pct, places), places)


MOST_PLACES = 10


def _places(season: SeasonChange, factor: float = 2.0) -> int | None:
    """Decimal places, one unless rounding would print something the numbers
    do not say (review 1, L1; 3E1b's N5/R5 for the raw test): a gap printed
    under or over its band's bound ("-16.9 ... under twice about 8.4"), or a
    change, gap or typical that is not 0 printed as 0. (The printed gap is
    the printed changes' difference by construction - `_printed_gap`.) None
    when no precision up to MOST_PLACES agrees - the sentence then makes no
    claim about the bound (review 2, #3)."""
    now, before, gap, typical = (season.expected_change_pct + season.difference_pct, season.expected_change_pct,
                                 season.difference_pct, season.typical_pct)
    for places in range(1, MOST_PLACES + 1):
        printed_gap, printed_typical = _printed_gap(season, places), round(typical, places)
        if any(value != 0 and round(value, places) == 0 for value in (now, before, typical)) or (
                gap != 0 and printed_gap == 0):
            continue
        # The printed typical within 5% of the real one: rounded to "about 0.1"
        # a typical of 0.05 made the printed multiple half the real one (8D
        # review, #7).
        if typical and abs(printed_typical - typical) > 0.05 * typical:
            continue
        if season.band == "consistent" and gap != 0 and not abs(printed_gap) < factor * printed_typical:
            continue
        if season.band in ("shortfall", "excess") and not abs(printed_gap) >= season.beyond_factor * printed_typical:
            continue
        return places
    return None
