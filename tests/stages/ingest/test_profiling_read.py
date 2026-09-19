import math

import pytest

from stages.ingest.profiling import CsvParseError, EmptyCsvError, read_csv_text

# --- encoding -----------------------------------------------------------------


def test_reads_utf8() -> None:
    parsed = read_csv_text("sku,name\nA1,Café\n".encode("utf-8"))

    assert parsed.encoding == "utf-8"
    assert parsed.frame["name"].tolist() == ["Café"]


def test_strips_a_utf8_bom_from_the_first_column_name() -> None:
    parsed = read_csv_text(b"\xef\xbb\xbfsku,qty\nA1,3\n")

    assert parsed.encoding == "utf-8"
    assert list(parsed.frame.columns) == ["sku", "qty"]


def test_falls_back_to_latin1_when_the_bytes_are_not_utf8() -> None:
    # 0xE9 is "é" in latin-1 and an invalid lone byte in UTF-8 (SPECS section 10).
    parsed = read_csv_text(b"sku,name\nA1,Caf\xe9\n")

    assert parsed.encoding == "latin-1"
    assert parsed.frame["name"].tolist() == ["Café"]


def test_reads_utf16_with_a_bom() -> None:
    parsed = read_csv_text("sku,qty\r\nA1,3\r\n".encode("utf-16"))

    assert parsed.encoding == "utf-16"
    assert parsed.frame["qty"].tolist() == ["3"]


# --- delimiter ----------------------------------------------------------------


@pytest.mark.parametrize("delimiter", [",", ";", "\t", "|"])
def test_detects_the_delimiter(delimiter: str) -> None:
    text = f"sku{delimiter}qty{delimiter}price\nA1{delimiter}3{delimiter}9.99\n"

    parsed = read_csv_text(text.encode())

    assert parsed.delimiter == delimiter
    assert list(parsed.frame.columns) == ["sku", "qty", "price"]


def test_semicolon_file_with_decimal_commas_is_not_split_on_commas() -> None:
    parsed = read_csv_text(b"sku;price\nA1;1,50\nB2;2,75\n")

    assert parsed.delimiter == ";"
    assert parsed.frame["price"].tolist() == ["1,50", "2,75"]


def test_quoted_commas_stay_inside_their_field() -> None:
    parsed = read_csv_text(b'sku,name\nA1,"Mug, blue"\nB2,"Cup, red"\n')

    assert parsed.frame["name"].tolist() == ["Mug, blue", "Cup, red"]


def test_single_column_file_needs_no_delimiter() -> None:
    parsed = read_csv_text(b"sku\nA1\nB2\n")

    assert list(parsed.frame.columns) == ["sku"]
    assert parsed.frame["sku"].tolist() == ["A1", "B2"]


# --- values are kept as raw text ----------------------------------------------


def test_values_keep_their_raw_text() -> None:
    parsed = read_csv_text(b"sku,price\n0012,12.50\n")

    assert parsed.frame["sku"].tolist() == ["0012"]
    assert parsed.frame["price"].tolist() == ["12.50"]


@pytest.mark.parametrize("token", ["", "NA", "N/A", "NULL", "null", "nan", "#N/A", "None"])
def test_pandas_default_na_tokens_become_missing(token: str) -> None:
    parsed = read_csv_text(f"sku,qty\nA1,{token}\nB2,3\n".encode())

    first = parsed.frame["qty"].tolist()[0]
    assert isinstance(first, float) and math.isnan(first)


def test_other_placeholder_text_stays_a_value() -> None:
    parsed = read_csv_text(b"sku,qty\nA1,unknown\nB2,-\n")

    assert parsed.frame["qty"].tolist() == ["unknown", "-"]


# --- rejected -----------------------------------------------------------------


def test_header_only_file_is_empty() -> None:
    with pytest.raises(EmptyCsvError) as caught:
        read_csv_text(b"sku,qty,price\n")

    assert caught.value.code == "EMPTY_FILE"


def test_file_without_any_line_is_empty() -> None:
    with pytest.raises(EmptyCsvError):
        read_csv_text(b"\n\n")


def test_row_with_more_fields_than_the_header_fails_to_parse() -> None:
    with pytest.raises(CsvParseError) as caught:
        read_csv_text(b"sku,qty\nA1,3\nB2,4,extra,fields\n")

    assert caught.value.code == "PARSE_FAILED"


def test_odd_length_utf16_fails_to_parse() -> None:
    with pytest.raises(CsvParseError):
        read_csv_text(b"\xff\xfes\x00k\x00u")
