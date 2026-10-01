"""2E-u1, the method's N4-N6 (C:/Users/Happy/2E-u1-method.txt): per numeric
column the format is the cells' proof, else the user's answer; unanswered and
unproven the plan is refused with the true reason; an answer contradicting a
proof is refused; readable cells are rewritten as plain numbers, the rest left
as written. Never a default either way."""

import pandas as pd
import pytest

from stages.ingest.number_apply import (AppliedFormat, NumberAnswerContradicted, NumberQuestionUnanswered,
                                        apply_number_formats)
from stages.ingest.plan_validation import InvalidPlanError


def _frame(**columns: list) -> pd.DataFrame:
    return pd.DataFrame({name: pd.Series(values, dtype=object) for name, values in columns.items()})


def test_a_proven_column_is_rewritten_as_plain_numbers() -> None:
    frame = _frame(Price=["1,000.00", "$12.50", "250", None, "n/a"], Qty=["1", "2", "3", "4", "5"])
    cleaned, applied = apply_number_formats(frame, {"Price": "unit_price", "Qty": "quantity"}, {})
    assert cleaned["Price"].tolist() == ["1000.00", "12.50", "250", None, "n/a"]
    # "250" reads the same but is not rewritten - nothing changed; the
    # unreadable "n/a" is left for stage 2 to list.
    assert applied["Price"] == AppliedFormat(format="decimal_point", rewritten=2, unreadable=1, answered=False)
    assert applied["Qty"] == AppliedFormat(format=None, rewritten=0, unreadable=0, answered=False)
    assert cleaned["Qty"].tolist() == ["1", "2", "3", "4", "5"]


def test_a_decimal_comma_column_is_read_as_one() -> None:
    frame = _frame(Prix=["10,5", "3,25", "1.000,00", "7"])
    cleaned, applied = apply_number_formats(frame, {"Prix": "unit_price"}, {})
    assert cleaned["Prix"].tolist() == ["10.5", "3.25", "1000.00", "7"]
    assert applied["Prix"].format == "decimal_comma"


def test_an_unproven_column_unanswered_refuses_the_plan_with_the_reason() -> None:
    frame = _frame(Price=["1,000", "2,500", "12"])
    with pytest.raises(NumberQuestionUnanswered) as raised:
        apply_number_formats(frame, {"Price": "unit_price"}, {})
    assert isinstance(raised.value, InvalidPlanError)
    assert raised.value.problems == [
        "The numbers in column 'Price' can be read two ways - '1,000' is one thousand with a thousands "
        "comma, or one with a decimal comma - and nothing in the file says which: answer the number "
        "question in Review"]


def test_the_answer_decides_the_ambiguous_cells() -> None:
    frame = _frame(Price=["1,000", "2,500", "12"])
    as_point, applied = apply_number_formats(frame, {"Price": "unit_price"}, {"Price": "decimal_point"})
    assert as_point["Price"].tolist() == ["1000", "2500", "12"]
    assert applied["Price"] == AppliedFormat(format="decimal_point", rewritten=2, unreadable=0, answered=True)
    as_comma, _ = apply_number_formats(frame, {"Price": "unit_price"}, {"Price": "decimal_comma"})
    assert as_comma["Price"].tolist() == ["1.000", "2.500", "12"]


def test_a_cell_that_proves_its_format_is_read_by_its_own_proof() -> None:
    # A column merged from two locales: "10.5" can only be a decimal point,
    # "10,5" only a decimal comma - each cell proves itself, no question.
    frame = _frame(Price=["10.5", "10,5", "3"])
    cleaned, applied = apply_number_formats(frame, {"Price": "unit_price"}, {})
    assert cleaned["Price"].tolist() == ["10.5", "10.5", "3"]
    assert applied["Price"] == AppliedFormat(format=None, rewritten=1, unreadable=0, answered=False)


def test_a_column_proving_both_with_an_ambiguous_cell_asks() -> None:
    # Then the column's proof is no guide for "1,000": the answer decides it.
    frame = _frame(Price=["10.5", "10,5", "1,000"])
    with pytest.raises(NumberQuestionUnanswered):
        apply_number_formats(frame, {"Price": "unit_price"}, {})
    cleaned, applied = apply_number_formats(frame, {"Price": "unit_price"}, {"Price": "decimal_comma"})
    assert cleaned["Price"].tolist() == ["10.5", "10.5", "1.000"]
    assert (applied["Price"].format, applied["Price"].answered) == ("decimal_comma", True)


def test_an_answer_against_the_files_proof_is_refused() -> None:
    frame = _frame(Price=["1,000.00", "5"])
    with pytest.raises(NumberAnswerContradicted) as raised:
        apply_number_formats(frame, {"Price": "unit_price"}, {"Price": "decimal_comma"})
    assert raised.value.problems == [
        "The answer for column 'Price' says the decimal mark is a comma, but '1,000.00' can only be read "
        "with a decimal point: change the answer in Review"]


def test_only_the_numeric_fields_are_touched() -> None:
    frame = _frame(Name=["1,000", "Mug"], Price=["2", "3"])
    cleaned, applied = apply_number_formats(frame, {"Name": "product_name", "Price": "unit_price"}, {})
    assert cleaned["Name"].tolist() == ["1,000", "Mug"] and set(applied) == {"Price"}


def test_an_answer_for_a_column_that_needs_none_is_ignored() -> None:
    frame = _frame(Qty=["1", "2"])
    _, applied = apply_number_formats(frame, {"Qty": "quantity"}, {"Qty": "decimal_comma"})
    assert applied["Qty"] == AppliedFormat(format=None, rewritten=0, unreadable=0, answered=False)


def test_the_frame_given_is_not_modified() -> None:
    frame = _frame(Price=["$1", "$2"])
    cleaned, _ = apply_number_formats(frame, {"Price": "unit_price"}, {})
    assert frame["Price"].tolist() == ["$1", "$2"] and cleaned["Price"].tolist() == ["1", "2"]


def test_whole_numbers_are_rewritten_exactly_as_before_the_shortcut() -> None:
    """Review 2, N4: whole numbers skip the reading - but only those the
    reading would leave as written ("-3", "0012"); " 7 " and "+4" are still
    rewritten."""
    frame = pd.DataFrame({"qty": ["12", "-3", "+4", " 7 ", "0012", "1,000.5", None]}, dtype=object)
    cleaned, applied = apply_number_formats(frame, {"qty": "quantity"}, {})
    assert cleaned["qty"].tolist() == ["12", "-3", "4", "7", "0012", "1000.5", None]
    assert applied["qty"].rewritten == 3


def test_a_column_of_numbers_is_left_as_it_is() -> None:
    # Review 3, R3-4: the whole-number shortcut read `.str` on a float column.
    frame = pd.DataFrame({"qty": [1.0, 2.5, None], "price": [3, 4, 5]})
    cleaned, applied = apply_number_formats(frame, {"qty": "quantity", "price": "unit_price"}, {})
    assert cleaned.equals(frame) and applied["qty"].rewritten == applied["price"].rewritten == 0
