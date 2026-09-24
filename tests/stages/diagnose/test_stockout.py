"""R3's detector (stages/diagnose/stockout.py): a steady seller that stops while
the store keeps trading. Two months, October 2011 (31 days) and November 2011
(30 days); product B sells every trading day so the store always trades."""

from datetime import date, timedelta

import pytest

from stages.diagnose.stockout import detect_stockouts
from tests.stages.diagnose.diagnose_fixtures import row, run_data


def _days(start: date, end: date, closed: tuple[int, ...] = ()):
    day = start
    while day <= end:
        if day.weekday() not in closed:
            yield day
        day += timedelta(days=1)


def shop(a_sells_on, closed: tuple[int, ...] = ()) -> list[dict]:
    rows = []
    for day in _days(date(2011, 10, 1), date(2011, 11, 30), closed):
        rows.append(row(day, qty=1, price=10.0, product="B"))
        if a_sells_on(day):
            rows.append(row(day, qty=1, price=100.0, product="A"))
    return rows


def test_a_steady_seller_that_stops_for_ten_days_is_flagged() -> None:
    """A sells every day of October (31 of 31, rate 1.0) and November 1-20,
    then nothing for 21-30: a run of 10 trading days >= 7.
    Contribution = -(3,100 / 31 trading days) * 10 = -1,000."""
    data = run_data(shop(lambda d: d.month == 10 or d.day <= 20))

    found = detect_stockouts(data)

    assert [item.product for item in found] == ["A"]
    assert found[0].zero_run_days == 10
    assert found[0].contribution == pytest.approx(-1000.0)


def test_six_days_is_not_a_stockout() -> None:
    data = run_data(shop(lambda d: d.month == 10 or d.day <= 24))

    assert detect_stockouts(data) == []


def test_an_irregular_seller_is_not_a_candidate() -> None:
    """A sold on 15 of 31 October days (rate 0.48 < 0.50), then stopped for
    the whole of November. It never sold steadily enough to 'run out'."""
    data = run_data(shop(lambda d: d.month == 10 and d.day <= 15))

    assert detect_stockouts(data) == []


def test_the_run_is_counted_over_days_the_store_traded() -> None:
    """The store is closed on Sundays. A misses Monday 14 - Saturday 19
    November and Monday 21 (Sunday 20 is closed): 7 trading days, flagged.
    Missing Monday 14 - Saturday 19 only is 6 trading days even though the
    Sunday after it makes 7 calendar days: not flagged."""
    closed = (6,)
    seven = run_data(shop(lambda d: d.month == 10 or not (14 <= d.day <= 21), closed))
    six = run_data(shop(lambda d: d.month == 10 or not (14 <= d.day <= 19), closed))

    assert [item.zero_run_days for item in detect_stockouts(seven)] == [7]
    assert detect_stockouts(six) == []
