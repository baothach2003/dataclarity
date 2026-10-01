"""2E-u1 (Thach, 2026-10-02; 2E-u F1): how stage 1 reads a number written for
people - the method's N2 and N3 (C:/Users/Happy/2E-u1-method.txt). Every
reading worked by hand."""

import pandas as pd
import pytest

from stages.ingest.number_format import FormatEvidence, format_evidence, read_cell


@pytest.mark.parametrize("cell,shape,point,comma", [
    # (cell, shape, its value read decimal point, its value read decimal comma)
    ("1234", "plain", 1234.0, 1234.0),
    ("-12", "plain", -12.0, -12.0),
    ("10.5", "point", 10.5, None),
    ("0.25", "point", 0.25, None),
    (".5", "point", 0.5, None),
    ("1.0000", "point", 1.0, None),          # four digits after: no thousands group
    ("10,5", "comma", None, 10.5),
    ("3,25", "comma", None, 3.25),
    ("1,0000", "comma", None, 1.0),
    ("1,000.00", "point", 1000.0, None),    # the last mark is the decimal one
    ("1.000,00", "comma", None, 1000.0),
    ("1,000,000", "point", 1000000.0, None),  # a repeated mark groups: the other is decimal
    ("1.000.000", "comma", None, 1000000.0),
    ("1,000", "ambiguous", 1000.0, 1.0),
    ("1.000", "ambiguous", 1.0, 1000.0),
    ("2,500", "ambiguous", 2500.0, 2.5),
    ("1 000", "plain", 1000.0, 1000.0),      # a space only groups
    ("1\u00a0000,50", "comma", None, 1000.5),  # a no-break space groups too
    ("1'000.50", "point", 1000.5, None),     # an apostrophe groups
    ("$10.00", "point", 10.0, None),
    ("10.00 \u20ac", "point", 10.0, None),
    ("\u00a31,000", "ambiguous", 1000.0, 1.0),
    ("-$1,000.50", "point", -1000.5, None),
    ("$-5", "plain", -5.0, -5.0),
    ("10-", "plain", -10.0, -10.0),          # a trailing minus
])
def test_a_cells_shape_and_both_readings(cell: str, shape: str, point: float | None, comma: float | None) -> None:
    reading = read_cell(cell)
    assert reading is not None and reading.shape == shape
    assert (reading.as_point, reading.as_comma) == (point, comma)


@pytest.mark.parametrize("cell", ["", "abc", "1,00,0", "1.000,000.5", "10..5", "1,000.000,00", "1 00",
                                  "12abc", "--5", "1,000.5,0", "USD 10", "$", "1.5e3"])
def test_a_cell_no_rule_reads_is_left_unreadable(cell: str) -> None:
    assert read_cell(cell) is None


def test_a_column_proving_a_decimal_point() -> None:
    """"1,000.00" proves the point; "250" says nothing; "1,500" is ambiguous on
    its own but the column's proof decides it."""
    evidence = format_evidence(pd.Series(["1,000.00", "250", "1,500", None, "1,500"]))
    assert evidence == FormatEvidence(readable=4, point=1, comma=0, ambiguous=2, signed_currency=0,
                                      point_example="1,000.00", comma_example=None, ambiguous_example="1,500",
                                      unreadable=0, unreadable_example=None)
    assert evidence.decision == "decimal_point"


def test_a_column_proving_a_decimal_comma() -> None:
    evidence = format_evidence(pd.Series(["10,5", "3", "\u20ac2,25"]))
    assert (evidence.decision, evidence.comma, evidence.signed_currency) == ("decimal_comma", 2, 1)


def test_a_column_that_proves_neither_but_reads_two_ways_asks() -> None:
    evidence = format_evidence(pd.Series(["1,000", "2,500", "12"]))
    assert (evidence.decision, evidence.ambiguous, evidence.ambiguous_example) == ("ask", 2, "1,000")


def test_a_column_proving_both_asks_only_for_its_ambiguous_cells() -> None:
    # Each proving cell is read by its own proof; only "1,000" needs a word.
    evidence = format_evidence(pd.Series(["10.5", "10,5"]))
    assert (evidence.decision, evidence.point_example, evidence.comma_example) == (None, "10.5", "10,5")
    assert format_evidence(pd.Series(["10.5", "10,5", "1,000"])).decision == "ask"


def test_plain_numbers_need_no_decision() -> None:
    assert format_evidence(pd.Series(["1", "-2", "300", None])).decision is None
    # Unreadable cells decide nothing either: they stay as written.
    assert format_evidence(pd.Series(["1", "abc"])).decision is None


def test_currency_signs_alone_decide_nothing_but_are_counted() -> None:
    evidence = format_evidence(pd.Series(["$10", "$20"]))
    assert (evidence.decision, evidence.signed_currency) == (None, 2)


# --- mutation check ---------------------------------------------------------------------------------


def test_two_signs_are_no_number() -> None:
    assert read_cell("-5-") is None


def test_a_first_group_of_four_digits_is_no_thousands_grouping() -> None:
    # "1000,000" cannot group thousands (a first group has 1-3 digits): only a
    # decimal comma reads it - 1000.000.
    reading = read_cell("1000,000")
    assert reading is not None and (reading.shape, reading.comma_text) == ("comma", "1000.000")


def test_a_leading_decimal_mark_is_written_back_with_its_zero() -> None:
    reading = read_cell(".5")
    assert reading is not None and reading.point_text == "0.5"


# --- review 1 ------------------------------------------------------------------------------------------


@pytest.mark.parametrize("cell,shape", [("0,500", "comma"), ("0.125", "point"), ("-0,250", "comma"),
                                        ("0.500", "point")])
def test_a_leading_zero_is_no_thousands_group(cell: str, shape: str) -> None:
    # Nobody writes 500 as "0,500" (2E-u1 review 1, F2: read as a group it
    # rewrote 0.5 as 500).
    reading = read_cell(cell)
    assert reading is not None and reading.shape == shape


def test_only_ascii_digits_are_read() -> None:
    # pandas reads no other digits (review 1, F9).
    assert read_cell("１２") is None and read_cell("١٢٣") is None
    assert read_cell("1２") is None  # one ASCII digit beside a full-width one
    assert read_cell("1.２") is None  # a full-width decimal digit


def test_unreadable_counts_only_what_stage_2_cannot_read_either() -> None:
    # "1e3" and "+5" are left as written and pandas reads them (review 1, F6).
    evidence = format_evidence(pd.Series(["1e3", "+5", "n/a!", "10.5"]))
    assert (evidence.unreadable, evidence.unreadable_example) == (1, "n/a!")


# --- review 2 ------------------------------------------------------------------------------------------


@pytest.mark.parametrize("cell,shape,point,comma", [
    ("+5", "plain", 5.0, 5.0),
    ("+2.500", "ambiguous", 2.5, 2500.0),
    ("+1,000.50", "point", 1000.5, None),
    ("+$10,5", "comma", None, 10.5),
])
def test_a_leading_plus_is_read_as_a_sign(cell: str, shape: str, point: float | None, comma: float | None) -> None:
    """Review 2, N1: "+2.500" was read by no rule and counted nowhere (pandas
    reads it), so stage 2 read it with a decimal point whatever the column
    proved or the user answered - x1000 under a decimal comma."""
    reading = read_cell(cell)
    assert reading is not None and reading.shape == shape
    assert (reading.as_point, reading.as_comma) == (point, comma)


@pytest.mark.parametrize("cell", ["+-5", "-+5", "+5-", "++5", "5+"])
def test_one_sign_at_most(cell: str) -> None:
    assert read_cell(cell) is None


def test_a_column_signed_with_plus_throughout_is_asked() -> None:
    assert format_evidence(pd.Series(["+1.000", "+2.500"])).decision == "ask"


def _one_by_one(values: list[str | None]) -> FormatEvidence:
    """The evidence cell by cell, with no shortcut: the reference the fast
    path must equal (review 2, N4)."""
    from stages.ingest.number_format import has_currency

    tally = {"plain": 0, "point": 0, "comma": 0, "ambiguous": 0}
    examples: dict[str, str] = {}
    currency = unreadable = 0
    unreadable_example = None
    for cell in values:
        if cell is None or not cell.strip():
            continue
        reading = read_cell(cell)
        if reading is None:
            if pd.isna(pd.to_numeric(cell, errors="coerce")):
                unreadable += 1
                unreadable_example = unreadable_example or cell
            continue
        tally[reading.shape] += 1
        examples.setdefault(reading.shape, cell)
        currency += has_currency(cell)
    return FormatEvidence(readable=sum(tally.values()), point=tally["point"], comma=tally["comma"],
                          ambiguous=tally["ambiguous"], signed_currency=currency,
                          point_example=examples.get("point"), comma_example=examples.get("comma"),
                          ambiguous_example=examples.get("ambiguous"), unreadable=unreadable,
                          unreadable_example=unreadable_example)


@pytest.mark.parametrize("values", [
    ["12", "-3", "+4", " 7 ", "0012", "1,000", "abc", "10.5", "", None, "$5", "5-", "1e3", "n/a"],
    ["100245", "100246", "100245", "C100247", "1 000", "１２", "+-5"],
    ["x", "y", "-", "+", "0", "00"],
])
def test_the_whole_number_shortcut_reads_exactly_as_cell_by_cell(values: list[str | None]) -> None:
    assert format_evidence(pd.Series(values, dtype=object)) == _one_by_one(values)


def test_an_example_is_cut_like_every_other_cell_text() -> None:
    # Review 2, N8: a 400-digit cell was copied whole into profile.json.
    from stages.ingest.ai_input import MAX_VALUE_CHARS, TRUNCATION_MARK

    long = "9" * 400 + ".5"
    evidence = format_evidence(pd.Series([long, "1,000.00"]))
    assert evidence.point_example is not None
    assert len(evidence.point_example) == MAX_VALUE_CHARS and evidence.point_example.endswith(TRUNCATION_MARK)


# --- review 3 ------------------------------------------------------------------------------------------


def test_a_line_break_at_either_end_is_stripped_like_a_space() -> None:
    """Review 3, R3-3: a quoted cell keeps its carriage return; pandas reads
    "2.500" with one and no rule did, so it was counted nowhere and read with
    a point."""
    reading = read_cell("2.500\r")
    assert reading is not None and reading.shape == "ambiguous"
    assert format_evidence(pd.Series(["1.000", "\n2.500\r\n"])).ambiguous == 2


@pytest.mark.parametrize("values", [
    ["SO-00000001", "user1@example.com", "abc", "1,000.00", "n/a!", "USD 10", "12"],
    ["x", "1e3", "-", "€", "1,5", "y"],
    # Digits only, read by no rule: pandas reads "5." (not unreadable), not "1,00,0".
    ["5.", "1,00,0", "12"],
])
def test_cells_with_letters_are_counted_as_cell_by_cell(values: list[str]) -> None:
    # Review 3, R3-2: such cells are never read one by one any more.
    assert format_evidence(pd.Series(values, dtype=object)) == _one_by_one(values)


def test_an_example_is_cut_after_its_spaces() -> None:
    # Review 3, R3-7: 120 spaces then "1,000" read as "   ...[truncated]".
    evidence = format_evidence(pd.Series([" " * 120 + "1,000"]))
    assert evidence.ambiguous_example == "1,000"
