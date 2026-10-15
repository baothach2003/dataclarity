"""Thach's Q8 (2026-10-16): a column naming or locating a person is NEVER
offered to split sales - by its header or by the profile's evidence - and is
removed before the AI's input is built, so its values never reach the AI
(method C:/Users/Happy/dashboard-q678-method.txt section 3). Personal data on
a shareable report, and no use to a shop owner."""

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from contracts.breakdowns import BreakdownSuggestion, EligibleColumn
from shared.run_registry import create_run
from stages.ingest.breakdown_review import measure_lines
from stages.ingest.breakdowns import breakdown_question_run
from stages.ingest.profiling import profile_run, read_csv_text
from tests.stages.ingest.test_dashboard_q345_stage1 import BASE, _csv, _eligible, _plan, _why

NOW = datetime(2026, 10, 16, tzinfo=UTC)
PERSON = "it names or locates a person"


def _with(header: str, values: list[str]) -> bytes:
    rows = [[f"2024-12-{1 + i % 28:02d}", "Mug", 1, 2.5, values[i % len(values)]] for i in range(40)]
    return _csv([*BASE, header], rows)


def _fields(header: str) -> dict[str, tuple[str, str]]:
    return BASE | {header: ("ignore", "categorical_nominal")}


# Two people, each written many times: by count and blanks a perfect split - only Q8 refuses it.
TWO = ["Ann Lee", "Bo Chan"]


@pytest.mark.parametrize("header", [
    "Email", "E-mail", "Customer Email", "Billing Phone", "Phone", "Telephone", "Mobile", "Fax",
    "Shipping Address1", "Billing Address 2", "Address", "Street", "Billing Street", "Shipping Zip", "Zip Code",
    "Postcode", "Post Code", "Postal Code", "Name", "Billing Name", "Shipping Name", "Ship To Name",
    "First Name", "Last Name", "Full Name", "Customer Name", "Client Name", "Cardholder Name", "Staff Name",
    "Employee", "Cashier", "Salesperson", "Sold By", "Served By", "Username",
])
def test_a_header_naming_or_locating_a_person_is_never_offered(header: str) -> None:
    content = _with(header, TWO)
    assert _eligible(content, _plan(_fields(header))) == []
    assert _why(content, _plan(_fields(header)), header) == f'column "{header}" cannot split sales: {PERSON}'


@pytest.mark.parametrize(("values", "what"), [
    (["ann@example.com", "bo@example.org"], "an e-mail"),
    (["+44 20 7946 0958", "(555) 123-4567"], "a phone"),
    (["SW1A 1AA", "EC1A 1BB"], "a UK postcode"),
    (["K1A 0B1", "M5V 3L9"], "a Canadian postcode"),
    (["1012 AB", "3511 LX"], "a Dutch postcode"),
    (["90210-1234", "01310-100"], "digits, a dash, digits"),
])
def test_a_value_naming_or_locating_a_person_is_never_offered(values: list[str], what: str) -> None:
    # The header says nothing ("Ref"): the profile's top values do.
    content = _with("Ref", values)
    assert _why(content, _plan(_fields("Ref")), "Ref") == f'column "Ref" cannot split sales: {PERSON}', what


@pytest.mark.parametrize("header", [
    "Customer Type", "Customer Segment", "Device Name", "Location Name", "Store Name", "Country", "Shipping City",
    "Billing Country", "Billing Province", "Channel", "Payment Method",
])
def test_a_column_that_names_no_person_is_still_offered(header: str) -> None:
    # Decision made alone (Thach's list only): a city, a province, a country and a company are not refused; a
    # person word beside another word ("Customer Type") is not a name.
    content = _with(header, ["North", "South"])
    assert _eligible(content, _plan(_fields(header))) == [header]


def test_a_personal_column_never_reaches_the_ai(tmp_path: Path) -> None:
    rows = [[f"2024-12-{1 + i % 28:02d}", "Mug", 1, 2.5, ["ann@example.com", "bo@example.org"][i % 2],
             ["Main St", "Harbour"][i % 2]] for i in range(40)]
    header = [*BASE, "Contact", "Store"]
    content = _csv(header, rows)
    fields = BASE | {"Contact": ("ignore", "text"), "Store": ("ignore", "categorical_nominal")}
    run = create_run(tmp_path)
    (run.path / "raw.csv").write_bytes(content)
    profile_run(tmp_path, run.run_id, now=NOW)
    seen: list[list[EligibleColumn]] = []

    def ask(eligible: list[EligibleColumn]) -> BreakdownSuggestion:
        seen.append(eligible)
        return BreakdownSuggestion(schema_version="1.0", generated_at=NOW, eligible=[c.column for c in eligible],
                                   chosen=[], status="ai_unavailable", model_used=None)

    measured = measure_lines(read_csv_text(content).frame, _plan(fields))
    shown = breakdown_question_run(tmp_path, run.run_id, _plan(fields), measured, ask)
    assert [c.column for c in shown.eligible] == ["Store"]
    asked: Any = seen[0]
    assert [c.column for c in asked] == ["Store"]
    assert "example.com" not in repr(asked)


@pytest.mark.parametrize(("values", "why"), [
    (["2024-12-01", "2024-11-30"], "its values are dates"),     # a date has dashes and 8 digits: not a phone
    (["01.12.2024", "30.11.2024"], "its values are numbers"),  # dots and digits read as a number first
    (["1234567", "7654321"], "its values are numbers"),         # no "+" and no separator: not a phone
    (["555 12", "555 13"], "its values are numbers"),           # a separator, but 5 digits: not a phone
])
def test_dates_and_plain_numbers_keep_their_own_reason(values: list[str], why: str) -> None:
    content = _with("Ref", values)
    fields = BASE | {"Ref": ("ignore", "text")}
    assert _why(content, _plan(fields), "Ref") == f'column "Ref" cannot split sales: {why}'


# --- mutation's survivors (each its own test) ---------------------------------------------------------------------

@pytest.mark.parametrize("header", ["billing_name", "customer_email", "Shipping_Zip"])
def test_an_underscore_is_read_as_a_space_in_a_header(header: str) -> None:
    content = _with(header, TWO)
    assert _why(content, _plan(_fields(header)), header) == f'column "{header}" cannot split sales: {PERSON}'


def test_a_seven_digit_phone_is_a_phone() -> None:
    content = _with("Ref", ["555 12 34", "555 98 76"])  # three groups: no postcode shape
    assert _why(content, _plan(_fields("Ref")), "Ref") == f'column "Ref" cannot split sales: {PERSON}'


def test_a_value_with_spaces_around_it_is_read_as_written() -> None:
    content = _with("Ref", ['" ann@example.com "', '" bo@example.org "'])
    assert _why(content, _plan(_fields("Ref")), "Ref") == f'column "Ref" cannot split sales: {PERSON}'


# --- the doubt review's findings (each reproduced first) ------------------------------------------------------------

@pytest.mark.parametrize("header", [
    # F1: WooCommerce's order export and CSV export, Etsy, eBay and others - a person word with other words.
    "First Name (Billing)", "Last Name (Billing)", "Name (Billing)", "Customer Name (Billing)", "billing_first_name",
    "billing_full_name", "shipping_first_name", "Customer First Name", "Customer Full Name", "Ship Name",
    "Buyer Username", "Sales Person", "Salesman", "Seller", "Contact Person", "Delivery Name", "Account Holder",
])
def test_f1_a_person_word_among_other_words_is_still_a_person(header: str) -> None:
    content = _with(header, TWO)
    assert _why(content, _plan(_fields(header)), header) == f'column "{header}" cannot split sales: {PERSON}'


@pytest.mark.parametrize("header", ["Device Name", "Price Point Name", "Item Name", "Tax 1 Name",
                                    "Shipping Province Name", "Shipping Method Title", "Customer Type"])
def test_f1_a_name_of_a_thing_is_not_a_person(header: str) -> None:
    assert _eligible(_with(header, ["North", "South"]), _plan(_fields(header))) == [header]


def test_f1_woocommerce_names_never_reach_the_ai() -> None:
    header = "First Name (Billing)"
    assert _eligible(_with(header, ["Alice", "Bob", "Carol"]), _plan(_fields(header))) == []


@pytest.mark.parametrize("values", [["100-200", "500-1000"], ["10-100", "1000-2000"], ["2023-2024", "2024-2025"],
                                    ["500-750", "750-1000"]])
def test_f2_a_range_or_a_season_is_no_postcode(values: list[str]) -> None:
    # Only the stated shapes: 90210-1234, 01310-100, 100-0001.
    assert _why(_with("Band", values), _plan(_fields("Band")), "Band") != (
        f'column "Band" cannot split sales: {PERSON}')


@pytest.mark.parametrize("values", [["(020)79460958", "(020)79460959"], ["Ann Lee", "Bo Chan"]])
def test_a_phone_in_brackets_alone_is_a_phone(values: list[str]) -> None:
    # Mutation's survivor: brackets with no other separator. The second: a ship-to or delivery name by header.
    header = "Ref" if values[0].startswith("(") else "Delivery Name"
    content = _with(header, values)
    assert _why(content, _plan(_fields(header)), header) == f'column "{header}" cannot split sales: {PERSON}'


# --- its scoped review's findings (each reproduced first) ------------------------------------------------------------

@pytest.mark.parametrize("values", [["500 - 1000", "1000 - 2000"], ["10.00 - 20.00", "20.00 - 30.00"],
                                    ["2023 - 2024", "2024 - 2025"], ["09.00 - 12.00", "0900 - 1200"]])
def test_s1_a_spaced_range_is_no_phone(values: list[str]) -> None:
    assert _why(_with("Band", values), _plan(_fields("Band")), "Band") != (
        f'column "Band" cannot split sales: {PERSON}')


@pytest.mark.parametrize("header", ["Best Seller", "Top Seller", "Seller Fulfilled"])
def test_s2_a_seller_flag_is_no_person(header: str) -> None:
    assert _eligible(_with(header, ["Yes", "No"]), _plan(_fields(header))) == [header]


@pytest.mark.parametrize("header", ["BillingFirstName", "ShipToName", "PhoneNumber", "EmailAddress", "BillingPhone",
                                    "BuyerEmail", "PostalCode", "ContactPhone", "SellerName"])
def test_s3_a_camel_case_header_is_read_as_its_words(header: str) -> None:
    content = _with(header, TWO)
    assert _why(content, _plan(_fields(header)), header) == f'column "{header}" cannot split sales: {PERSON}'
