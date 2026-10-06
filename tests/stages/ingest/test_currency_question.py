"""Review's currency question (the report redesign's step 5; design 6.2 and
6.3; section 12, step 2's "what step 5 needs"): stage 1 reads the raw file
on the plan's money column with the same function execute uses, and words
what Review shows - the page words no figure. Written before the code."""

import pytest

from contracts.currency import ISO_4217, NOT_STATED, CurrencyFinding, CurrencyPart
from stages.ingest.currency_question import COMMON, currency_question, plan_currency
from stages.ingest.profiling import read_csv_text
from tests.stages.ingest.test_currency import BASE, csv, plan, rows_of


def _question(rows: list[list[str]], header: list[str], price: str = "price"):
    frame = read_csv_text(csv(rows, header)).frame
    return currency_question(plan_currency(frame, plan(header, price)))


def test_the_plans_money_column_is_read_as_execute_reads_it() -> None:
    header = [*BASE, "cost"]
    rows = rows_of(["£2.50", "£3.00"], ["€1.00", "€1.00"])
    frame = read_csv_text(csv(rows, header)).frame

    assert plan_currency(frame, plan(header)).code == "GBP"
    assert plan_currency(frame, plan(header, price="cost")).code == "EUR"


def test_a_found_currency_is_preselected_with_where_it_was_found() -> None:
    question = _question(rows_of(["£2.50", "£3.00"]), BASE)

    assert question.selected == "GBP"
    assert question.finding.evidence is not None
    assert question.blocked is None and question.unreadable is None
    assert question.options[:len(COMMON)] == list(COMMON)


def test_nothing_found_preselects_not_stated_and_offers_the_common_codes_first() -> None:
    question = _question(rows_of(["2.50", "3.00"]), BASE)

    assert question.finding.kind == "none"
    assert question.selected == NOT_STATED
    assert question.options[:5] == ["GBP", "EUR", "USD", "AUD", "CAD"]
    assert sorted(question.options) == sorted(ISO_4217) and len(question.options) == len(ISO_4217)
    rest = question.options[len(COMMON):]
    assert rest == sorted(rest)


def test_a_bare_dollar_offers_the_dollars_first_and_preselects_nothing_but_not_stated() -> None:
    question = _question(rows_of(["$2.50", "$3.00"]), BASE)

    assert question.finding.kind == "narrowed"
    assert question.selected == NOT_STATED
    assert question.options[:len(question.finding.candidates)] == question.finding.candidates
    assert question.options[0] == "USD" and len(question.options) == len(ISO_4217)


def test_more_than_one_currency_is_the_block_with_stage_1s_sentence_and_no_answer() -> None:
    question = _question(rows_of(["£2.50", "€3.00", "€1.00"]), BASE)

    assert question.finding.kind == "mixed"
    assert question.options == [] and question.selected is None
    assert question.blocked is not None and question.blocked.startswith(
        "Your file has amounts in more than one currency (")
    assert "Split the file by currency and upload each part." in question.blocked


def test_the_block_is_the_sentence_execute_refuses_with() -> None:
    finding = CurrencyFinding(kind="mixed", parts=[CurrencyPart(label="EUR", lines=300),
                                                   CurrencyPart(label="USD", lines=1)])

    assert currency_question(finding).blocked == (
        "Your file has amounts in more than one currency (EUR: 300 lines, USD: 1 line). DataClarity cannot add "
        "different currencies together. Split the file by currency and upload each part.")


# The review: a hint or a count can span two currency columns - no "column" in the singular.
@pytest.mark.parametrize(("count", "sentence"), [(1, "1 cell where the file names its currency could not be read."),
                                                  (3, "3 cells where the file names its currency could not be read.")])
def test_unreadable_cells_are_worded_by_stage_1(count: int, sentence: str) -> None:
    assert currency_question(CurrencyFinding(kind="none", unreadable=count)).unreadable == sentence


def test_a_hint_is_worded_by_stage_1() -> None:
    question = currency_question(CurrencyFinding(kind="none", hint="Euro"))

    assert question.hint == "Where your file names its currency, it says: Euro"
    assert currency_question(CurrencyFinding(kind="none")).hint is None
