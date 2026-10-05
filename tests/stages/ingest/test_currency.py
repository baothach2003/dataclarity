"""The report redesign's step 2 (Thach, 2026-10-05): stage 1 reads the file's
currency on strong evidence only - anything doubtful is "not found" and
Review asks (the principle); evidence only from the plan's money column and a
column whose header names a currency, at execute (Q26); a bare "$" or the
yen sign narrows (Q5, Q9), a "$" beside one dollar code is that code (Q27);
a currency column's values decide by one rule (Q28, Q29); more than one
currency blocks the plan (Q7 = A). docs/REPORT_REDESIGN.md section 6, as
built in section 12; method C:/Users/Happy/redesign-step2b-method.txt."""

import time
import unicodedata
from pathlib import Path

import pandas as pd
import pytest
from pydantic import ValidationError

from contracts.cleaning import ColumnAction, OrderConfirmations
from contracts.currency import CurrencyFinding, CurrencyPart
from stages.ingest import currency
from stages.ingest.cleaning import execute_run
from stages.ingest.currency import currency_finding
from stages.ingest.currency_apply import MixedCurrencies, apply_currency
from stages.ingest.profiling import read_csv_text
from tests.stages.ingest.cleaning_fixtures import COLUMN_TYPES, NOW, column_action, make_plan, raw_run

BASE = ["sku", "name", "qty", "price", "day"]


def csv(rows: list[list[str]], header: list[str]) -> bytes:
    lines = [",".join(header)] + [",".join(f'"{cell}"' if "," in cell else cell for cell in row) for row in rows]
    return ("\n".join(lines) + "\n").encode("utf-8")


def rows_of(prices: list[str], *extra: list[str]) -> list[list[str]]:
    """A row per price cell; each extra list gives one more column's cells."""
    return [["A1", "Mug", "2", price, f"2024-01-{index % 28 + 1:02d}", *(column[index] for column in extra)]
            for index, price in enumerate(prices)]


def _ignored(name: str) -> ColumnAction:
    return ColumnAction.model_validate({"source_name": name, "semantic_type": "categorical_nominal",
                                        "canonical_field": "ignore", "action": "flag_only", "params": {},
                                        "rationale": "chosen by the user", "alternatives": [], "edited_by_user": True})


def plan(header: list[str], price: str = "price", answer: str | None = None):
    """The base columns mapped as the fixtures map them, `price` (any header) the unit price, the rest ignored."""
    actions = [column_action("price", source_name=name) if name == price else
               column_action(name) if name in COLUMN_TYPES and name != "price" else _ignored(name) for name in header]
    return make_plan(actions).model_copy(update={"confirmations": OrderConfirmations(currency=answer)})


def execute(tmp_path: Path, rows: list[list[str]], header: list[str], price: str = "price", answer: str | None = None):
    run_id = raw_run(tmp_path, csv(rows, header))
    return execute_run(tmp_path, run_id, plan(header, price, answer), now=NOW).currency


def finding(rows: list[list[str]], header: list[str], price: str = "price") -> CurrencyFinding:
    return currency_finding(read_csv_text(csv(rows, header)).frame, [price])


def found(rows: list[list[str]], header: list[str], price: str = "price") -> tuple:
    result = finding(rows, header, price)
    return result.kind, result.code


def refusal(tmp_path: Path, rows: list[list[str]], header: list[str], price: str = "price") -> str:
    with pytest.raises(MixedCurrencies) as refused:
        execute(tmp_path, rows, header, price)
    (sentence,) = refused.value.problems
    return sentence


# --- Thach's cases (2026-10-05): each failed on the work in progress ------------------------------------


def test_a_sku_like_top_001_is_no_currency(tmp_path: Path) -> None:
    applied = execute(tmp_path, [["TOP-001", "Mug", "2", "9.99", "2024-01-01"],
                                 ["TOP-002", "Cup", "1", "3.00", "2024-01-02"]], BASE)

    assert (applied.code, applied.source) == (None, "not_stated")


def test_a_weight_in_kgs_is_no_currency(tmp_path: Path) -> None:
    applied = execute(tmp_path, rows_of(["9.99", "3.00"], ["2.5 kgs", "0.5 kgs"]), BASE + ["Weight"])

    assert (applied.code, applied.source) == (None, "not_stated")


def test_one_service_line_in_a_pound_file_is_no_second_currency(tmp_path: Path) -> None:
    rows = rows_of(["£2.50", "£3.00", "£4.00"])
    rows[2][0] = "SVC-100"

    applied = execute(tmp_path, rows, BASE)

    assert (applied.code, applied.source) == ("GBP", "symbol")


def test_two_currency_names_in_a_currency_column_block_by_their_names(tmp_path: Path) -> None:
    rows = rows_of(["9.99", "3.00", "4.00"], ["Euro", "US Dollar", "euro"])

    assert refusal(tmp_path, rows, BASE + ["Currency"]) == (
        "Your file has amounts in more than one currency (Euro: 2 lines, US Dollar: 1 line). DataClarity cannot "
        "add different currencies together. Split the file by currency and upload each part.")


def test_a_code_beside_a_cell_that_reads_as_a_number_is_that_code() -> None:
    result = finding(rows_of(["9.99", "3.00", "4.00"], ["GBP", "0", "GBP"]), BASE + ["Currency"])

    assert (result.kind, result.code, result.unreadable) == ("found", "GBP", 1)


def test_two_codes_beside_a_cell_that_reads_as_a_number_block(tmp_path: Path) -> None:
    rows = rows_of(["9.99", "3.00", "4.00", "5.00"], ["GBP", "EUR", "0", "GBP"])

    assert "(GBP: 2 lines, EUR: 1 line)" in refusal(tmp_path, rows, BASE + ["Currency"])


@pytest.mark.parametrize("empty", ["-", "none", "NONE", " n/a ", ""])
def test_a_placeholder_in_a_currency_column_is_empty(empty: str) -> None:
    result = finding(rows_of(["9.99", "3.00"], ["GBP", empty]), BASE + ["Currency"])

    assert (result.kind, result.code, result.unreadable) == ("found", "GBP", 0)


def test_a_single_name_that_is_no_code_is_a_hint_not_evidence(tmp_path: Path) -> None:
    rows = rows_of(["9.99", "3.00"], ["Euro", "Euro"])
    result = finding(rows, BASE + ["Currency"])

    assert (result.kind, result.hint) == ("none", "Euro")
    assert execute(tmp_path, rows, BASE + ["Currency"]).source == "not_stated"


# --- where evidence is read (Q26) ------------------------------------------------------------------------


def test_a_code_in_a_header_that_is_not_the_money_column_is_not_read() -> None:
    assert found(rows_of(["9.99", "3.00"], ["1.00", "2.00"]), BASE + ["Shipping (USD)"]) == ("none", None)


def test_a_sign_in_a_column_that_is_not_the_money_column_is_not_read() -> None:
    assert found(rows_of(["9.99", "3.00"], ["£5", "£6"]), BASE + ["Discount"]) == ("none", None)


def test_the_money_column_is_the_one_the_plan_maps() -> None:
    rows = rows_of(["£9.99", "£3.00"], ["€1.00", "€2.00"])

    assert found(rows, BASE + ["Fee"], price="Fee") == ("found", "EUR")


@pytest.mark.parametrize("header", ["Country", "Code"])
def test_a_column_of_codes_whose_header_names_no_currency_is_not_read(header: str) -> None:
    assert found(rows_of(["9.99", "3.00"], ["CAD", "FR"]), BASE + [header]) == ("none", None)


def test_generic_cleaning_reads_no_currency(tmp_path: Path) -> None:
    run_id = raw_run(tmp_path, csv(rows_of(["£2.50", "€3.00"]), BASE))

    report = execute_run(tmp_path, run_id, plan(BASE), now=NOW, require_required_fields=False)

    assert report.currency is None


# --- the money column: signs ---------------------------------------------------------------------------


def test_a_pound_sign_in_the_prices_is_found() -> None:
    result = finding(rows_of(["£2.50", "£3.00"]), BASE)

    assert (result.kind, result.code, result.source, result.evidence) == (
        "found", "GBP", "symbol", "GBP, from the £ in column price")


def test_a_euro_sign_after_the_number_is_found() -> None:
    assert found(rows_of(["2,50 €", "3,00 €"]), BASE) == ("found", "EUR")


@pytest.mark.parametrize("sign", sorted(currency.SYMBOL_CODES))
def test_every_named_sign_is_its_code(sign: str) -> None:
    assert found(rows_of([f"{sign}12"]), BASE) == ("found", currency.SYMBOL_CODES[sign])


def test_a_bare_dollar_narrows_to_the_dollars_and_runs_as_not_stated(tmp_path: Path) -> None:
    result = finding(rows_of(["$2.50"]), BASE)

    assert (result.kind, result.candidates[:6]) == ("narrowed", ["USD", "AUD", "CAD", "NZD", "SGD", "HKD"])
    assert execute(tmp_path, rows_of(["$2.50"]), BASE).source == "not_stated"


@pytest.mark.parametrize("cell", ["¥300", "￥300"])
def test_the_yen_sign_narrows_to_jpy_and_cny(cell: str) -> None:
    result = finding(rows_of([cell]), BASE)

    assert (result.kind, result.candidates) == ("narrowed", ["JPY", "CNY"])


def test_a_cent_sign_is_part_of_a_dollar() -> None:
    assert finding(rows_of(["$2.50", "50¢"]), BASE).kind == "narrowed"


def test_a_sign_this_version_does_not_name_alone_is_not_found() -> None:
    assert found(rows_of(["₨300", "₨450"]), BASE) == ("none", None)


def test_one_odd_cell_does_not_hide_a_sign() -> None:
    assert found(rows_of(["£2.50", "-", "TBD", "(£2.00)"]), BASE) == ("found", "GBP")


# --- the money column: its header ----------------------------------------------------------------------


@pytest.mark.parametrize("header", ["Price (AUD)", "Price [AUD]", "Price AUD", "price_AUD", "TotalAUD"])
def test_a_code_in_capitals_in_brackets_or_last_is_read(header: str) -> None:
    result = finding(rows_of(["9.99", "3.00"]), ["sku", "name", "qty", header, "day"], price=header)

    assert (result.kind, result.code, result.source, result.evidence) == (
        "found", "AUD", "header", f"AUD, from the header {header}")


@pytest.mark.parametrize("header", ["amount_gbp", "Price (aud)", "PRICE_AUD", "Total (ALL)", "TOP Price",
                                    "Price per Cup", "AUD Price old", "EUR_to_GBP"])
def test_a_doubtful_header_names_nothing(header: str) -> None:
    assert found(rows_of(["9.99", "3.00"]), ["sku", "name", "qty", header, "day"], price=header) == ("none", None)


def test_a_sign_in_the_header_is_read() -> None:
    result = finding(rows_of(["9.99"]), ["sku", "name", "qty", "Price (€)", "day"], price="Price (€)")

    assert (result.kind, result.code, result.source) == ("found", "EUR", "header")


def test_the_column_is_named_before_the_signs_and_the_signs_before_the_header() -> None:
    header = ["sku", "name", "qty", "Price (GBP)", "day", "Currency"]
    by_column = finding(rows_of(["£9.99"], ["GBP"]), header, price="Price (GBP)")
    by_sign = finding(rows_of(["£9.99"]), header[:5], price="Price (GBP)")

    assert (by_column.source, by_sign.source) == ("column", "symbol")


# --- the currency column (Q28, Q29) -----------------------------------------------------------------------


def test_a_currency_column_of_one_code_is_found_trimmed_and_upper_cased() -> None:
    result = finding(rows_of(["9.99", "3.00"], [" aud ", "AUD"]), BASE + ["currency"])

    assert (result.kind, result.code, result.source, result.evidence) == (
        "found", "AUD", "column", "AUD, from column currency")


@pytest.mark.parametrize("name", sorted(currency.CURRENCY_NAMES))
def test_every_currency_name_makes_a_currency_column(name: str) -> None:
    assert found(rows_of(["9.99", "3.00"], ["GBP", "EUR"]), BASE + [name.title()])[0] == "mixed"


@pytest.mark.parametrize("header", ["Currency Code", "currency_code", "TransactionCurrency", "currencycode",
                                    "CURRENCYCODE", "WährungCode", "Tiền tệ"])
def test_a_currency_column_header_is_read_however_written(header: str) -> None:
    assert found(rows_of(["9.99", "3.00"], ["GBP", "EUR"]), BASE + [header])[0] == "mixed"


def test_a_header_stored_decomposed_is_read() -> None:
    header = unicodedata.normalize("NFD", "Währung")

    assert found(rows_of(["9.99", "3.00"], ["GBP", "EUR"]), BASE + [header])[0] == "mixed"


@pytest.mark.parametrize("header", ["Amount in Local Currency", "Currency Rate", "curr_price", "Accurate",
                                    "Currency Converted"])
def test_a_header_that_only_mentions_a_currency_is_no_currency_column(header: str) -> None:
    assert found(rows_of(["9.99", "3.00"], ["Yes", "No"]), BASE + [header]) == ("none", None)


def test_a_column_of_dates_under_a_currency_name_is_no_evidence_but_counted() -> None:
    # Q29 to the letter (the fourth review #8): every such cell is counted, so Review can say so.
    result = finding(rows_of(["9.99", "3.00"], ["05.01.2024", "06.01.2024"]), BASE + ["Valuta"])

    assert (result.kind, result.unreadable) == ("none", 2)


@pytest.mark.parametrize("cell", ["826", "36", "2024-01-05", "05.01.2024", "1,000.50", "(12)"])
def test_a_cell_that_reads_as_a_number_or_a_date_is_unreadable(cell: str) -> None:
    result = finding(rows_of(["9.99", "3.00"], ["GBP", cell]), BASE + ["Currency"])

    assert (result.code, result.unreadable) == ("GBP", 1)


@pytest.mark.parametrize("pair", [("£", "€"), ("Pound", "Euro"), ("HRK", "EUR"), ("AUD", "various")])
def test_any_two_values_in_a_currency_column_block(pair: tuple[str, str]) -> None:
    assert found(rows_of(["9.99", "3.00"], list(pair)), BASE + ["Currency"])[0] == "mixed"


def test_a_single_sign_in_a_currency_column_is_no_code_but_a_hint() -> None:
    result = finding(rows_of(["9.99"], ["£"]), BASE + ["Currency"])

    assert (result.kind, result.hint) == ("none", "£")


# --- the one block rule ----------------------------------------------------------------------------------


@pytest.mark.parametrize("cells", [["£2.50", "€3.00"], ["$2.50", "£3.00"], ["£2.50", "₨300"], ["$2.50", "¥300"]])
def test_two_signs_in_the_money_column_block(cells: list[str]) -> None:
    assert finding(rows_of(cells), BASE).kind == "mixed"


def test_a_header_code_that_disagrees_with_the_signs_blocks() -> None:
    header = ["sku", "name", "qty", "Price (EUR)", "day"]

    assert finding(rows_of(["£2.50"]), header, price="Price (EUR)").kind == "mixed"


def test_a_currency_column_that_disagrees_with_the_signs_blocks(tmp_path: Path) -> None:
    rows = rows_of(["€2.50", "€3.00"], ["GBP", "GBP"])

    # A tie is listed in the file's column order: the prices come before the Currency column.
    assert "(EUR: 2 lines, GBP: 2 lines)" in refusal(tmp_path, rows, BASE + ["Currency"])


def test_a_dollar_beside_its_dollar_header_is_that_dollar() -> None:
    header = ["sku", "name", "qty", "Price (AUD)", "day"]

    assert found(rows_of(["$2.50"]), header, price="Price (AUD)") == ("found", "AUD")


def test_a_dollar_beside_a_peso_in_the_currency_column_is_that_peso() -> None:
    assert found(rows_of(["$120.00", "$80.50"], ["MXN", "MXN"]), BASE + ["Moneda"]) == ("found", "MXN")


def test_a_dollar_named_on_an_orders_first_line_only_is_that_code(tmp_path: Path) -> None:
    # Q27: never refused; pre-selected with where it was found, and Review always asks.
    applied = execute(tmp_path, rows_of(["$2.50", "$3.00", "$4.00"], ["USD", "", ""]), BASE + ["Currency"])

    assert (applied.code, applied.source, applied.evidence) == ("USD", "column", "USD, from column Currency")


def test_a_dollar_beside_two_dollar_codes_blocks() -> None:
    assert finding(rows_of(["$2.50", "$3.00"], ["USD", "CAD"]), BASE + ["Currency"]).kind == "mixed"


def test_a_line_carrying_a_currency_twice_is_counted_once(tmp_path: Path) -> None:
    rows = rows_of(["£2.50", "£3.00", "€4.00"], ["GBP", "GBP", "GBP"])

    assert "(GBP: 3 lines, EUR: 1 line)" in refusal(tmp_path, rows, BASE + ["Currency"])


def test_many_currencies_are_listed_ten_and_the_rest_counted() -> None:
    codes = ["GBP", "EUR", "USD", "AUD", "CAD", "JPY", "CHF", "SEK", "NOK", "DKK", "PLN", "CZK"]
    result = finding(rows_of(["9.99"] * len(codes), codes), BASE + ["Currency"])

    assert (len(result.parts), result.more_parts) == (10, 2)
    with pytest.raises(MixedCurrencies, match=r"\(GBP: 1 line, .*, DKK: 1 line and 2 more\)"):
        apply_currency(result, None)


def test_the_lines_are_written_without_a_thousands_separator() -> None:
    result = finding(rows_of(["9.99"] * 1001, ["GBP"] * 1000 + ["EUR"]), BASE + ["Currency"])

    with pytest.raises(MixedCurrencies, match=r"\(GBP: 1000 lines, EUR: 1 line\)"):
        apply_currency(result, None)


def test_a_long_value_is_shown_cut_never_a_crash() -> None:
    result = finding(rows_of(["9.99", "3.00"], ["Schweizerfrankengroß" * 3, "GBP"]), BASE + ["Currency"])

    assert result.kind == "mixed" and all(len(part.label) <= 40 for part in result.parts)


# --- the demo shapes -------------------------------------------------------------------------------------


def test_the_online_retail_ii_shape_names_no_currency() -> None:
    header = ["Invoice", "StockCode", "Description", "Quantity", "InvoiceDate", "Price", "Customer ID", "Country"]
    rows = [["489434", "85048", "15CM CHRISTMAS GLASS BALL 20 LIGHTS", "12", "2009-12-01 07:45", "6.95", "13085",
             "United Kingdom"],
            ["C489449", "22087", "PAPER BUNTING WHITE LACE", "-12", "2009-12-01 10:33", "2.95", "16321", "France"],
            ["489436", "POST", "POSTAGE", "1", "2009-12-01 09:06", "18.00", "13078", "Australia"]]

    assert found(rows, header, price="Price") == ("none", None)


def test_the_kaggle_shape_names_no_currency() -> None:
    header = ["Transaction ID", "Customer ID", "Category", "Item", "Price Per Unit", "Quantity", "Total Spent",
              "Payment Method", "Location", "Transaction Date", "Discount Applied"]
    rows = [["TXN_1", "CUST_09", "Patisserie", "Item_10_PAT", "18.5", "10.0", "185.0", "Digital Wallet", "Online",
             "2024-04-08", "True"]]

    assert found(rows, header, price="Price Per Unit") == ("none", None)


# --- the answer and what runs (6.2-6.4) ------------------------------------------------------------------


def test_mixed_currencies_block_whatever_the_answer(tmp_path: Path) -> None:
    run_id = raw_run(tmp_path, csv(rows_of(["£2.50", "€3.00"]), BASE))

    with pytest.raises(MixedCurrencies):
        execute_run(tmp_path, run_id, plan(BASE, answer="GBP"), now=NOW)
    assert not (tmp_path / run_id / "cleaning_report.json").exists()


def test_a_found_currency_unanswered_is_the_one_found(tmp_path: Path) -> None:
    applied = execute(tmp_path, rows_of(["£2.50"]), BASE)

    assert (applied.code, applied.source, applied.evidence) == ("GBP", "symbol", "GBP, from the £ in column price")


def test_an_answer_that_is_the_found_currency_keeps_where_it_was_found(tmp_path: Path) -> None:
    applied = execute(tmp_path, rows_of(["£2.50"]), BASE, answer="GBP")

    assert (applied.code, applied.source) == ("GBP", "symbol")


def test_the_user_may_change_a_found_currency(tmp_path: Path) -> None:
    applied = execute(tmp_path, rows_of(["£2.50"]), BASE, answer="EUR")

    assert (applied.code, applied.source, applied.evidence) == ("EUR", "user", "GBP, from the £ in column price")


def test_the_user_may_pick_a_currency_the_file_does_not_name(tmp_path: Path) -> None:
    applied = execute(tmp_path, rows_of(["2.50"]), BASE, answer="VND")

    assert (applied.code, applied.source, applied.evidence) == ("VND", "user", None)


def test_not_stated_is_an_answer(tmp_path: Path) -> None:
    applied = execute(tmp_path, rows_of(["£2.50"]), BASE, answer="not_stated")

    assert (applied.code, applied.source) == (None, "not_stated")


def test_nothing_found_and_unanswered_is_not_stated(tmp_path: Path) -> None:
    applied = execute(tmp_path, rows_of(["2.50"]), BASE)

    assert (applied.code, applied.source, applied.evidence) == (None, "not_stated", None)


def test_an_answer_is_an_iso_code_or_not_stated() -> None:
    for wrong in ("gbp", "XYZ", "pounds", ""):
        with pytest.raises(ValidationError):
            OrderConfirmations(currency=wrong)


# --- the contract and the cost ---------------------------------------------------------------------------


def test_currencies_are_counted_past_the_list_only_once_it_is_full() -> None:
    two = [CurrencyPart(label="GBP", lines=1), CurrencyPart(label="EUR", lines=1)]

    with pytest.raises(ValidationError):
        CurrencyFinding(kind="mixed", parts=two, more_parts=1)


def test_a_hint_and_unreadable_cells_never_stand_beside_a_block() -> None:
    two = [CurrencyPart(label="GBP", lines=1), CurrencyPart(label="EUR", lines=1)]

    with pytest.raises(ValidationError):
        CurrencyFinding(kind="mixed", parts=two, hint="Euro")
    with pytest.raises(ValidationError):
        CurrencyFinding(kind="mixed", parts=two, unreadable=1)
    assert CurrencyFinding(kind="found", code="GBP", source="column", evidence="GBP, from column Currency",
                           hint="Euro").hint == "Euro"


def test_the_versions() -> None:
    from stages.ingest import ai_plan, ai_schema, cleaning, profiling

    assert (ai_schema.SCHEMA_VERSION, ai_plan.SCHEMA_VERSION, cleaning.SCHEMA_VERSION) == ("4.3", "4.3", "4.3")
    assert profiling.SCHEMA_VERSION == "1.2"  # the profile carries no currency (Q26: read at execute)


def _word(number: int) -> str:
    return "".join(chr(97 + number // 26 ** place % 26) for place in range(4))


def test_the_pass_is_linear_in_rows_and_in_cell_length() -> None:
    rows = 200_000
    frame = pd.DataFrame({"price": [f"£{i / 100:.2f}" if i % 2 else "a" * 2000 for i in range(rows)],
                          "Currency": [_word(i) for i in range(rows)]})
    started = time.perf_counter()

    assert currency_finding(frame, ["price"]).kind == "mixed"
    assert time.perf_counter() - started < 10


# --- the rules the mutants found unpinned ---------------------------------------------------------------


def test_a_sign_this_version_does_not_name_is_listed_as_written() -> None:
    assert [(part.label, part.lines) for part in finding(rows_of(["£2.50", "₨300"]), BASE).parts] == [
        ("GBP", 1), ("₨", 1)]


def test_an_english_word_in_lower_case_beside_a_code_is_no_second_code() -> None:
    header = ["sku", "name", "qty", "Price (EUR) all in", "day"]

    assert found(rows_of(["9.99"]), header, price="Price (EUR) all in") == ("found", "EUR")


def test_a_dollar_beside_two_dollar_codes_is_neither() -> None:
    header = ["sku", "name", "qty", "Price (CAD)", "day", "Currency"]
    result = finding(rows_of(["$2.50", "$3.00"], ["USD", "USD"]), header, price="Price (CAD)")

    assert sorted(part.label for part in result.parts) == ["$", "CAD", "USD"]


def test_the_lines_are_lines_whatever_the_frame_index() -> None:
    frame = read_csv_text(csv(rows_of(["£2.50", "£3.00", "€4.00"]), BASE)).frame
    frame.index = [10, 10, 11]

    assert [(part.label, part.lines) for part in currency_finding(frame, ["price"]).parts] == [("GBP", 2), ("EUR", 1)]


def test_the_currencies_are_listed_largest_first() -> None:
    result = finding(rows_of(["9.99"] * 3, ["EUR", "GBP", "GBP"]), BASE + ["Currency"])

    assert [(part.label, part.lines) for part in result.parts] == [("GBP", 2), ("EUR", 1)]


# --- the fourth review (Q31): each fix more conservative, or a signal for Review -------------------------


def test_a_brazilian_real_beside_its_code_is_that_code() -> None:
    assert found(rows_of(["R$ 12,90", "R$ 5,00"], ["BRL", "BRL"]), BASE + ["Moeda"]) == ("found", "BRL")


def test_two_currency_columns_each_of_one_different_code_are_doubtful_not_blocked(tmp_path: Path) -> None:
    rows = rows_of(["9.99", "3.00"], ["EUR", "EUR"], ["USD", "USD"])
    header = BASE + ["Currency", "Settlement Currency"]
    result = finding(rows, header)

    assert (result.kind, result.hint) == ("none", "EUR, USD")
    assert execute(tmp_path, rows, header).source == "not_stated"


def test_two_currency_columns_of_one_same_code_are_that_code() -> None:
    assert found(rows_of(["9.99", "3.00"], ["EUR", "EUR"], ["EUR", ""]), BASE + ["Currency", "Billing Currency"]) == (
        "found", "EUR")


def test_one_currency_column_of_two_values_blocks_whatever_the_other_says() -> None:
    rows = rows_of(["9.99", "3.00"], ["EUR", "EUR"], ["USD", "GBP"])

    assert finding(rows, BASE + ["Currency", "Settlement Currency"]).kind == "mixed"


def test_a_repeated_header_line_is_empty() -> None:
    result = finding(rows_of(["£9.99", "price", "£3.00"], ["GBP", "Currency", "GBP"]), BASE + ["Currency"])

    assert (result.kind, result.code) == ("found", "GBP")


@pytest.mark.parametrize("cell", ["05-Jan-2024", "2024-01-05T10:00:00Z", "1 Jan 2024"])
def test_a_date_written_with_words_is_unreadable(cell: str) -> None:
    result = finding(rows_of(["9.99", "3.00"], ["GBP", cell]), BASE + ["Currency"])

    assert (result.code, result.unreadable) == ("GBP", 1)


@pytest.mark.parametrize("empty", ["—", "–", " NULL", "nan", "​"])
def test_what_stage_1_reads_as_missing_is_empty(empty: str) -> None:
    result = finding(rows_of(["9.99", "3.00"], ["USD", empty]), BASE + ["Currency"])

    assert (result.kind, result.code, result.unreadable) == ("found", "USD", 0)


@pytest.mark.parametrize("header", ["Price per KGS", "Price (KGS)", "Price per CUP", "Cost (MOP)", "Price (BOB)",
                                    "Price (PEN)", "Price (WST)"])
def test_a_code_that_is_also_a_word_or_a_unit_is_never_read_in_a_header(header: str) -> None:
    assert found(rows_of(["9.99"]), ["sku", "name", "qty", header, "day"], price=header) == ("none", None)


def test_a_currency_column_of_numeric_codes_is_counted_unreadable(tmp_path: Path) -> None:
    rows = rows_of(["9.99", "3.00", "4.00"], ["840", "978", "978"])
    result = finding(rows, BASE + ["Currency Code"])

    assert (result.kind, result.unreadable) == ("none", 3)


def test_a_name_beside_a_code_found_elsewhere_is_shown_as_a_hint() -> None:
    result = finding(rows_of(["9.99", "3.00", "€4.00", "€5.00"], ["Pound", "Pound", "", ""]), BASE + ["Currency"])

    assert (result.kind, result.code, result.hint) == ("found", "EUR", "Pound")
