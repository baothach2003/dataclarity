"""Session 2E-k doubt-review cycle 2, written before the fixes.

- F1 (blocking: FABRICATE on the walk-in placeholder shape): a placeholder
  spelled off the word list and under 10% of the lines became the top
  customer, 15 times the next one. Thach's rule is an UNUSUAL share: the
  largest value is also asked about when it carries PLACEHOLDER_RATIO (4)
  times the next value's lines or sale revenue. Measured: the largest real
  customer is 1.01-1.15 times the next on both demo files; Online Retail II's
  walk-ins are 18.5 times its largest customer. The word list also covers the
  common international spellings, matched on word boundaries, and a number
  at or below zero ("-1").
- F4: word boundaries, so the surname "Walker" or "Cashmere Ltd" is not a
  placeholder question.
- F5: the search reads no dates, so a file without an order id is not parsed
  at the schema step (day-first dates cost ~20 s at 650,000 rows).
- F7: a placeholder line is counted once, as a placeholder, not also as an
  unfilled receipt line.
"""

from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pytest

from contracts.cleaning import OrderConfirmations
from shared import transactions
from stages.analyze.assemble import assemble_metrics
from stages.ingest.customer_placeholders import PLACEHOLDER_RATIO, placeholder_candidates
from tests.ai_fakes import FakeMessages
from tests.stages.ingest.schema_answers import answer, column, profiled_run, run

MAPPING = {"Day": "transaction_date", "Qty": "quantity", "Price": "unit_price", "Cust": "customer"}


def _sales(customers: list[str | None], prices: list[str] | None = None) -> pd.DataFrame:
    n = len(customers)
    return pd.DataFrame({"Day": ["2026-08-03"] * n, "Qty": "1",
                         "Price": prices or ["10"] * n, "Cust": customers})


def _shop_with(placeholder: str) -> pd.DataFrame:
    """200 real customers with 3 lines each (600), and a placeholder on 45
    lines - 7% of the lines, 15 times the next customer."""
    return _sales([f"C{i}" for i in range(200) for _ in range(3)] + [placeholder] * 45)


@pytest.mark.parametrize("spelling", ["Consumidor Final", "Publico en General", "Público en general",
                                      "Khách lẻ", "One-time customer", "Default Customer", "Laufkunde",
                                      "Client divers", "none", "Null", "(blank)", "N.A.", "-1"])
def test_international_and_missing_value_spellings_are_words(spelling: str) -> None:
    found = placeholder_candidates(_sales([f"C{i}" for i in range(93)] + [spelling] * 7), MAPPING)

    assert [(c.value, c.why) for c in found] == [(spelling, "word")]


def test_a_value_many_times_the_next_one_is_asked_whatever_its_spelling() -> None:
    found = placeholder_candidates(_shop_with("999999990"), MAPPING)

    assert [(c.value, c.why) for c in found] == [("999999990", "share")]
    assert PLACEHOLDER_RATIO == 4


def test_the_ratio_is_to_the_next_value_by_revenue_too() -> None:
    # Lines equal (one each); "Office" sells at exactly 4 times the next one
    # (40 against 10), 3.9% of the revenue - the ratio alone decides
    # (mutation checks R10, R11).
    customers = [f"C{i}" for i in range(99)] + ["Office"]
    prices = ["10"] * 99 + ["40"]

    found = placeholder_candidates(_sales(customers, prices), MAPPING)

    assert [c.value for c in found] == ["Office"]


def test_just_under_the_ratio_is_not_asked() -> None:
    customers = [f"C{i}" for i in range(99)] + ["Big"]
    prices = ["10"] * 99 + ["39"]  # 3.9 times the next customer, 3.8% of the revenue

    assert placeholder_candidates(_sales(customers, prices), MAPPING) == []


def test_customers_close_to_each_other_are_not_asked() -> None:
    # The demos' shape: the largest customer 1.01-1.15 times the next.
    customers = [f"C{i}" for i in range(40) for _ in range(3)] + ["Top"] * 4

    assert placeholder_candidates(_sales(customers), MAPPING) == []


@pytest.mark.parametrize("name", ["Walker", "Ann Walker", "Cashmere Ltd", "Guesthouse Ltd", "Bigcash Ltd"])
def test_a_word_inside_another_word_is_not_a_placeholder(name: str) -> None:
    # 31 customers of 3 lines: the name's 7 lines are 2.3 times the next one.
    customers = [f"C{i}" for i in range(31) for _ in range(3)] + [name] * 7

    assert placeholder_candidates(_sales(customers), MAPPING) == []


def test_the_search_reads_no_dates(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("dates parsed")

    monkeypatch.setattr(transactions, "as_dates", refuse)

    customers = ["Guest"] + [f"C{i}" for i in range(20)]

    assert [c.value for c in placeholder_candidates(_sales(customers), MAPPING)] == ["Guest"]


def test_a_file_without_an_order_id_is_not_parsed_at_the_schema_step(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    csv = "\n".join(["Day,Qty,Price,Cust", "2026-08-03,1,10,Guest"]
                    + [f"2026-08-03,1,10,C{i}" for i in range(20)]).encode()
    run_id = profiled_run(tmp_path, csv)

    def refuse(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("parsed a file with no order id")

    monkeypatch.setattr(transactions, "parse_transactions", refuse)
    schema = run(tmp_path, run_id, FakeMessages(answer(
        [column(n, MAPPING[n]) for n in MAPPING], dataset_issues=[])))

    assert [c.value for c in schema.customer_placeholders] == ["Guest"]


def test_a_placeholder_line_is_not_also_an_unfilled_receipt_line() -> None:
    rows = [("2026-08-03", "R1", "Ann"), ("2026-08-03", "R1", "Guest"), ("2026-08-03", "R1", None),
            ("2026-08-04", "R2", "Bob"), ("2026-08-05", "R3", "Cy"), ("2026-09-01", "R4", "Dee")]
    df = pd.DataFrame([{"Date": d, "Qty": "1", "Price": "10", "Inv": i, "Cust": c, "Prod": "Mug"}
                       for d, i, c in rows])
    mapping = {"Date": "transaction_date", "Qty": "quantity", "Price": "unit_price",
               "Inv": "order_id", "Cust": "customer", "Prod": "product_name"}
    answers = OrderConfirmations(customer_placeholders=["Guest"], customer_on_first_line_only=False)

    customers = assemble_metrics(df, mapping, datetime(2026, 9, 26, tzinfo=UTC), answers).customers

    assert (customers.placeholder_lines, customers.unfilled_receipt_lines) == (1, 1)
