"""Session 2E's shared definitions (shared/transactions.py, shared/periods.py),
written from the symptoms before the fix. Both stages read these, so the
definitions are tested once here, where they live.

- A return line is not an order: a sale row is a counted row with quantity
  > 0, a return row one with quantity < 0; a zero-quantity line is neither.
- A percentage change against a non-positive base, or against floating-point
  residue, is unavailable with a reason - never a sign-inverted number. The
  worked examples are PROJECT_PLAN 2E's, verbatim.
- One definition of an incomplete previous month for stage 2 and stage 3.
"""

import pandas as pd
import pytest

from shared.periods import previous_coverage
from shared.transactions import parse_transactions, pct_change

MAPPING = {"Date": "transaction_date", "Qty": "quantity", "Price": "unit_price"}


# --- sale and return rows -------------------------------------------------------


def test_a_return_line_and_a_zero_quantity_line_are_not_sales() -> None:
    df = pd.DataFrame({"Date": ["2011-01-03"] * 3, "Qty": ["2", "-1", "0"], "Price": ["10"] * 3})

    parsed = parse_transactions(df, MAPPING)

    assert parsed.sale.tolist() == [True, False, False]
    assert parsed.returned.tolist() == [False, True, False]
    assert parsed.counted.tolist() == [True, True, True]  # all still count towards revenue


# --- pct_change: PROJECT_PLAN 2E's worked examples --------------------------------


@pytest.mark.parametrize("current,previous,word", [
    (-200.0, -100.0, "negative"),     # was +100%: a doubled loss read as growth
    (500.0, -100.0, "negative"),      # was -600%: a recovery read as a collapse
    (1000.0, 1.39e-17, "residue"),    # was 7.2e21%
    (50.0, 0.0, "no previous"),       # was 0.0 (2A): "nothing moved", which is false
])
def test_a_percentage_against_an_unusable_base_is_unavailable(current, previous, word) -> None:
    change = pct_change(current, previous)

    assert change.value is None
    assert word in change.reason


def test_a_percentage_against_a_positive_base_is_the_plain_ratio() -> None:
    """(110 - 100) / 100 * 100 = +10.0; (50 - 200) / 200 * 100 = -75.0."""
    assert pct_change(110.0, 100.0).value == pytest.approx(10.0)
    assert pct_change(50.0, 200.0).value == pytest.approx(-75.0)
    assert pct_change(110.0, 100.0).reason is None


# --- the previous month's coverage ------------------------------------------------


def _dates(*days: str) -> pd.Series:
    return pd.to_datetime(pd.Series(list(days)))


def test_a_previous_month_starting_on_the_15th_is_incomplete() -> None:
    """Counted rows from 15 January: 14 January days precede the first one."""
    coverage = previous_coverage(_dates("2011-01-15", "2011-02-10"), "2011-01")

    assert (coverage.leading_days_missing, coverage.complete) == (14, False)
    assert "2011-01-01" in coverage.reason and "re-export" in coverage.reason.lower()


def test_one_leading_closed_day_is_not_an_incomplete_month() -> None:
    """First row on 2 January: 1 day, under 3 days and under 10% of 31."""
    coverage = previous_coverage(_dates("2011-01-02", "2011-02-10"), "2011-01")

    assert (coverage.leading_days_missing, coverage.complete, coverage.reason) == (1, True, None)


def test_a_previous_month_with_no_row_is_incomplete_even_with_history() -> None:
    """Rows in November and February, none in January (the previous month)."""
    coverage = previous_coverage(_dates("2010-11-05", "2011-02-10"), "2011-01")

    assert (coverage.has_rows, coverage.complete) == (False, False)
    assert "no sales in 2011-01" in coverage.reason


def test_the_leading_gap_is_capped_at_the_months_length() -> None:
    """First counted row on 5 March, previous month February (28 days)."""
    coverage = previous_coverage(_dates("2011-03-05"), "2011-02")

    assert coverage.leading_days_missing == 28


def test_three_leading_days_is_the_first_incomplete_count() -> None:
    """The boundary: 3 days (1-3 January) before the first row on the 4th."""
    assert previous_coverage(_dates("2011-01-04"), "2011-01").complete is False
    assert previous_coverage(_dates("2011-01-03"), "2011-01").complete is True


def test_coverage_needs_the_rows_it_is_given_not_a_dates_column() -> None:
    """The caller passes COUNTED dates; an empty series means no sale at all."""
    coverage = previous_coverage(pd.Series([], dtype="datetime64[ns]"), "2011-01")

    assert coverage.complete is False and coverage.leading_days_missing == 31
