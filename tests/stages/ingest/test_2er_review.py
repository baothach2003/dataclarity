"""Session 2E-r (Thach, 2026-09-27): the scoped review of 2E-k's and
2E-d2's unreviewed cycle-3 fixes, written before its fixes.

- F1 (K1): a value found by the 4-times rule still shielded the value behind
  it - an off-list "99999" at 9.85% hid "88888" at 2.2% (25 times any real
  customer), and a real key account the user will answer No about hid a
  placeholder. The rule is applied again after each value it finds. Two
  equal off-list codes still shield each other (recorded, 8D).
- F2 (K2): common placeholder spellings were missed - words joined by an
  underscore, a hyphen or two spaces ("Retail_Customer", "No-Customer",
  "Khach_Le"), the Chinese default inside a longer name ("门店散客"), "n/a"
  forms ("#n/a", "n / a"), a decomposed "Khach le", "Diverse", "Laufkunden",
  "Walk - In".
- F6 (K5): two finite amounts whose sum overflows showed two customers at
  "100%" of the sale revenue; an unmeasurable revenue is not measured.
"""

import unicodedata

import pandas as pd
import pytest

from stages.ingest.customer_placeholders import placeholder_candidates

MAPPING = {"Day": "transaction_date", "Qty": "quantity", "Price": "unit_price", "Cust": "customer"}


def _sales(customers: list[str], prices: list[str] | None = None) -> pd.DataFrame:
    n = len(customers)
    return pd.DataFrame({"Day": ["2026-08-03"] * n, "Qty": "1", "Price": prices or "10", "Cust": customers})


def _real(count: int, lines: int) -> list[str]:
    return [f"R{i}" for i in range(count) for _ in range(lines)]


def test_a_value_found_by_the_ratio_does_not_shield_the_next() -> None:
    customers = ["99999"] * 560 + ["88888"] * 125 + _real(1000, 5)

    found = placeholder_candidates(_sales(customers), MAPPING)

    assert [c.value for c in found] == ["99999", "88888"]


def test_three_stacked_codes_are_all_asked() -> None:
    # Mutation check R1: one pass each over lines and revenue found two of
    # three; the ratio is taken again until no value dominates the rest.
    customers = ["99999"] * 560 + ["88888"] * 125 + ["77777"] * 30 + _real(1000, 5)

    found = placeholder_candidates(_sales(customers), MAPPING)

    assert [c.value for c in found] == ["99999", "88888", "77777"]


def test_a_key_account_asked_by_the_ratio_does_not_hide_a_placeholder() -> None:
    customers = ["KEYACC"] * 560 + ["99999"] * 125 + _real(1000, 5)

    assert [c.value for c in placeholder_candidates(_sales(customers), MAPPING)] == ["KEYACC", "99999"]


@pytest.mark.parametrize("spelling", [
    "Retail_Customer", "No_Customer", "No-Customer", "CONSUMIDOR_FINAL", "Pelanggan_Umum", "Khach_Le",
    "Retail  Customer", "门店散客", "零售散客", "散客户", "N/A", "#n/a", "n / a",
    unicodedata.normalize("NFD", "Khách lẻ"), "Diverse", "Laufkunden", "Walk - In"])
def test_more_placeholder_spellings_are_words(spelling: str) -> None:
    customers = _real(31, 3) + [spelling] * 7

    found = placeholder_candidates(_sales(customers), MAPPING)

    assert [(c.value, c.why) for c in found] == [(spelling, "word")]


@pytest.mark.parametrize("name", ["Walker", "Guesthouse Ltd", "Retailer Co", "Nana"])
def test_ordinary_names_are_still_not_words(name: str) -> None:
    customers = _real(31, 3) + [name] * 7

    assert placeholder_candidates(_sales(customers), MAPPING) == []


def test_a_sale_revenue_that_overflows_is_not_measured() -> None:
    customers = ["A", "B"] + _real(31, 3)
    prices = ["1e154", "1e154"] + ["10"] * 93
    df = _sales(customers, prices).assign(Qty=["1e154", "1e154"] + ["1"] * 93)

    found = placeholder_candidates(df, MAPPING)

    assert all(c.revenue_pct is None for c in found)
