"""One customer, however they were typed (session 3C2).

Spans both stages on purpose. The point of normalising the customer key is
that stage 2 and stage 3 agree about who is one person, so a test that
exercised only one of them would not be testing the thing that matters.
"""

from datetime import date

import pandas as pd
import pytest

from shared.text import customer_identity, merged_identity_count
from stages.diagnose.bridge import compute_bridge
from stages.diagnose.lever import period_totals
from stages.diagnose.signals import monthly_series
from tests.stages.diagnose.diagnose_fixtures import row, run_data

# --- the helper ---------------------------------------------------------------


def test_case_and_surrounding_whitespace_do_not_make_a_second_customer() -> None:
    values = pd.Series(["CUST_01", " cust_01", "Cust_01 ", " CUST_01 "])

    identity = customer_identity(values)

    # Including the non-breaking spaces: `str.strip()` treats U+00A0 as
    # whitespace, and a POS export is a common source of them.
    assert identity.nunique() == 1
    assert identity.iloc[0] == "cust_01"


def test_genuinely_different_ids_stay_different() -> None:
    values = pd.Series(["CUST_01", "CUST_010", "CUST_1", "CUST-01"])

    assert customer_identity(values).nunique() == 4


def test_blank_values_stay_blank_so_they_remain_unattributed() -> None:
    # `is_blank` must still select these afterwards: a row with no customer is
    # not a customer named "".
    identity = customer_identity(pd.Series([None, "", "   ", " "]))

    assert identity.isna().iloc[0]
    assert (identity.iloc[1:] == "").all()


def test_the_merged_count_is_distinct_raw_minus_distinct_identities() -> None:
    values = pd.Series(["CUST_01", " cust_01", "Cust_01 ",  # 3 spellings -> 1
                        "CUST_02", "cust_02",               # 2 spellings -> 1
                        "CUST_03",                          # 1 spelling  -> 1
                        "CUST_03", None, "  "])             # repeat + blanks
    # 6 distinct raw values, 3 distinct identities.
    assert merged_identity_count(values) == 3


# --- both stages, on one file -------------------------------------------------


def _three_spellings() -> list[dict]:
    """One customer written three ways, buying 100 in each month, plus two
    more customers so that an off-by-one in the merged count changes the
    answer (the 3C lesson: counting is not identifying).

    CUST_01   Oct 60 + 40 (two spellings)      Nov 100 (a third spelling)
    CUST_02   Oct 50                           Nov 50   (two spellings)
    CUST_03   Oct 25                           Nov 25   (one spelling)

    The file opens on 1 October so that October is a *complete* month and
    therefore appears in the monthly series the XmR charts are built from
    (3B's stricter definition: a month counts only if the file covers all of
    it). October is also the month where two spellings of CUST_01 coexist,
    which is what makes the per-month counts discriminating.

    Distinct raw values 6, distinct identities 3, so 3 were merged. An
    implementation reporting "identities that absorbed a merge" would say 2,
    and "raw minus one" would say 5.
    """
    return [
        row(date(2011, 10, 1), qty=1, price=60.0, customer="CUST_01"),
        row(date(2011, 10, 6), qty=1, price=40.0, customer="Cust_01 "),
        row(date(2011, 10, 7), qty=1, price=50.0, customer="CUST_02"),
        row(date(2011, 10, 8), qty=1, price=25.0, customer="CUST_03"),
        row(date(2011, 11, 5), qty=1, price=100.0, customer=" cust_01"),
        row(date(2011, 11, 6), qty=1, price=50.0, customer="cust_02"),
        row(date(2011, 11, 30), qty=1, price=25.0, customer="CUST_03"),
    ]


def test_stage_2_counts_three_customers_not_six() -> None:
    data = run_data(_three_spellings())

    core = data.metrics.core

    assert core.active_customers_current == 3
    assert core.active_customers_previous == 3


def test_stage_3_agrees_with_stage_2_about_who_was_active() -> None:
    """Both periods, deliberately. November holds one spelling per customer,
    so a raw count there is 3 anyway and the test would pass against unkeyed
    code; October is where two spellings of CUST_01 coexist and a raw count
    gives 4. Asserting only the current period left this call site
    unprotected, which the mutation check caught."""
    data = run_data(_three_spellings())
    period = data.metrics.period

    current = period_totals(data, period.current)
    previous = period_totals(data, period.previous)

    assert previous.customers == data.metrics.core.active_customers_previous == 3
    assert current.customers == data.metrics.core.active_customers_current == 3


def test_the_monthly_series_behind_the_xmr_charts_counts_the_same_way() -> None:
    """`signals.monthly_series` computes active customers independently of
    `period_totals`, and October is again the month that tells them apart."""
    data = run_data(_three_spellings())

    table = monthly_series(data)

    assert table.loc["2011-10", "active_customers"] == 3.0
    assert table.loc["2011-11", "active_customers"] == 3.0
    # Four orders in October across three customers.
    assert table.loc["2011-10", "frequency"] == pytest.approx(4 / 3)


def test_a_flat_month_shows_no_new_and_no_lapsed_revenue() -> None:
    """The fabrication this session exists to remove. Keyed raw, October's two
    spellings of CUST_01 both vanish and November's third arrives, so the
    bridge reports lapsed -100 and new +100 - "we lost everyone and gained a
    whole new base" printed on a month where nothing happened, feeding the
    C-family hypotheses and possibly the headline."""
    data = run_data(_three_spellings())

    bridge = compute_bridge(data)

    assert bridge is not None
    assert bridge.new == 0.0
    assert bridge.lapsed == 0.0
    assert bridge.resurrected == 0.0
    # Revenue is identical in both months, so every term is zero.
    assert bridge.expansion == 0.0
    assert bridge.contraction == 0.0
    assert bridge.evidence["new_customers"] == 0


def test_the_bridge_reports_how_many_values_normalisation_merged() -> None:
    data = run_data(_three_spellings())

    bridge = compute_bridge(data)

    assert bridge is not None
    assert bridge.evidence["customer_values_merged_by_normalisation"] == 3


def test_a_consistently_typed_file_reports_nothing_merged() -> None:
    # Zero is the answer a clean file must give, so a non-zero count is
    # information rather than noise.
    rows = [
        row(date(2011, 10, 5), qty=1, price=60.0, customer="CUST_01"),
        row(date(2011, 10, 6), qty=1, price=40.0, customer="CUST_02"),
        row(date(2011, 11, 30), qty=1, price=60.0, customer="CUST_01"),
    ]
    data = run_data(rows)

    bridge = compute_bridge(data)

    assert bridge is not None
    assert bridge.evidence["customer_values_merged_by_normalisation"] == 0


def test_rfm_ranks_the_three_spellings_as_one_customer() -> None:
    """Keyed raw, a customer written two ways is two customers with half the
    frequency and half the monetary value each, which moves them down the RFM
    quintiles."""
    data = run_data(_three_spellings())

    segments = data.metrics.customers.segments

    assert sum(segment.customers for segment in segments) == 3


def test_the_normalised_customer_is_not_counted_as_new_in_stage_2_either() -> None:
    data = run_data(_three_spellings())

    new_vs_returning = data.metrics.customers.new_vs_returning

    # Everyone first bought in October, so November has no new customers.
    assert new_vs_returning.new_customers == 0
    assert new_vs_returning.returning_customers == 3


def test_blank_customers_are_still_unattributed_after_normalisation() -> None:
    rows = [
        *_three_spellings(),
        row(date(2011, 10, 9), qty=1, price=10.0, customer=""),
        row(date(2011, 11, 7), qty=1, price=30.0, customer="   "),
    ]
    data = run_data(rows)

    bridge = compute_bridge(data)

    assert bridge is not None
    assert bridge.unattributed == pytest.approx(20.0)  # 30 - 10
    assert data.metrics.core.active_customers_current == 3
