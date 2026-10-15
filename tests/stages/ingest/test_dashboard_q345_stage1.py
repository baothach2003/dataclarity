"""Thach's Q3, Q4 and Q5 (2026-10-15) in stage 1's eligibility (method
C:/Users/Happy/dashboard-q345-method.txt): measured on the lines execute would
write, through the one definition of a line's value (shared/split_values.py).
Q4: with a trusted order id, blanks are counted per order and two values in
one order make a column ineligible; Q3: above 9 values a column is eligible
unless nearly every line (order) is its own value; Q5: a column whose every
value holds only sale lines or only return lines is ineligible. Shapes built
from the published export layouts (no customer data)."""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from contracts.breakdowns import BreakdownSuggestion
from contracts.cleaning import CleaningPlanContract, ColumnAction, OrderConfirmations
from shared.run_registry import create_run
from stages.ingest.breakdown_review import measure_lines
from stages.ingest.breakdowns import breakdown_question_run, breakdowns_problem, eligible_columns
from stages.ingest.cleaning import execute_run
from stages.ingest.plan_validation import InvalidPlanError
from stages.ingest.profiling import profile_csv, profile_run, read_csv_text

NOW = datetime(2026, 10, 15, tzinfo=UTC)
RECEIPT = OrderConfirmations(order_id_is_receipt=True)


def _csv(header: list[str], rows: list[list[Any]]) -> bytes:
    lines = [",".join(header)] + [",".join("" if v is None else str(v) for v in row) for row in rows]
    return ("\n".join(lines) + "\n").encode()


def _action(name: str, field: str, kind: str, action: str = "flag_only", params: dict | None = None) -> ColumnAction:
    return ColumnAction(source_name=name, semantic_type=kind, canonical_field=field, action=action,
                        params={"note": "n"} if params is None else params, rationale="r", alternatives=[],
                        edited_by_user=False)


def _plan(fields: dict[str, tuple[str, str]], confirmations: OrderConfirmations | None = None,
          breakdowns: list[str] | None = None, actions: dict[str, ColumnAction] | None = None,
          ) -> CleaningPlanContract:
    """`fields`: column -> (canonical field, semantic type); `actions` replaces a column's action."""
    column_actions = [(actions or {}).get(name) or _action(name, field, kind) for name, (field, kind) in fields.items()]
    return CleaningPlanContract(schema_version="4.4", generated_at=NOW, source="manual", dataset_actions=[],
                                column_actions=column_actions, confirmations=confirmations or OrderConfirmations(),
                                breakdowns=breakdowns or [])


def _eligible(content: bytes, plan: CleaningPlanContract) -> list[str]:
    measured = measure_lines(read_csv_text(content).frame, plan)
    return [c.column for c in eligible_columns(profile_csv(content, now=NOW), plan, measured)]


def _why(content: bytes, plan: CleaningPlanContract, column: str) -> str | None:
    measured = measure_lines(read_csv_text(content).frame, plan)
    return breakdowns_problem(profile_csv(content, now=NOW), plan.model_copy(update={"breakdowns": [column]}),
                              measured)


# --- Q4: Shopify's order fields, written on an order's first line only ------------------------------------------

SHOPIFY = {"Name": ("order_id", "identifier"), "Created at": ("transaction_date", "datetime"),
           "Lineitem name": ("product_name", "text"), "Lineitem quantity": ("quantity", "numeric_discrete"),
           "Lineitem price": ("unit_price", "numeric_continuous"),
           "Financial Status": ("ignore", "categorical_nominal"), "Payment Method": ("ignore", "categorical_nominal"),
           "Source": ("ignore", "categorical_nominal"), "Vendor": ("ignore", "categorical_nominal")}


def _shopify() -> bytes:
    rows = []
    for order in range(10):
        for line in range(3):  # three lines an order; Shopify writes the order's fields on its first line only
            first = line == 0
            rows.append([f"#10{order}", f"2024-12-{1 + order:02d}", f"Item {line}", 1, 9.99,
                         "paid" if first else None, ["Shopify Payments", "PayPal"][order % 2] if first else None,
                         ["web", "pos"][order % 2] if first else None, ["Acme", "Bolt", "Core"][line]])
    return _csv(list(SHOPIFY), rows)


def test_with_a_trusted_order_id_the_order_fields_are_offered_and_a_per_line_field_is_not() -> None:
    # Payment Method and Source: one value per order, no order without one (0% blank by order). Financial
    # Status: one value in the file. Vendor: three values inside every order - Q4 makes it ineligible.
    assert _eligible(_shopify(), _plan(SHOPIFY, RECEIPT)) == ["Payment Method", "Source"]
    assert _why(_shopify(), _plan(SHOPIFY, RECEIPT), "Vendor") == (
        'column "Vendor" cannot split sales: an order holds two different values of it')


def test_without_a_trusted_order_id_the_per_line_rule_stands() -> None:
    # Unconfirmed, the order id is checked by date only and not trusted: blanks are counted per line (two thirds
    # blank), and Vendor - a value on every line - is offered, as before Q4.
    assert _eligible(_shopify(), _plan(SHOPIFY)) == ["Vendor"]
    assert _why(_shopify(), _plan(SHOPIFY), "Payment Method") == (
        'column "Payment Method" cannot split sales: too many of its cells are blank')


def test_an_order_with_no_value_counts_against_few_blanks() -> None:
    # 10 orders; Payment Method blank on every line of 2 of them: 20% of orders - too many.
    rows = []
    for order in range(10):
        for line in range(2):
            pay = None if line or order < 2 else ["Card", "Cash"][order % 2]
            rows.append([f"#{order}", f"2024-12-{1 + order:02d}", f"Item {line}", 1, 5.0, pay])
    fields = {k: SHOPIFY[k] for k in ("Name", "Created at", "Lineitem name", "Lineitem quantity", "Lineitem price")}
    fields |= {"Pay": ("ignore", "categorical_nominal")}
    content = _csv(list(fields), rows)
    assert _why(content, _plan(fields, RECEIPT), "Pay") == 'column "Pay" cannot split sales: too many of its cells ' \
                                                             "are blank"
    rows[2][5] = "Card"  # order #1 now has a value: 1 order of 10 blank, 10% - few blanks
    assert _eligible(_csv(list(fields), rows), _plan(fields, RECEIPT)) == ["Pay"]


KAGGLE = {"Transaction ID": ("order_id", "identifier"), "Customer ID": ("customer", "identifier"),
          "Item": ("product_name", "text"), "Price Per Unit": ("unit_price", "numeric_continuous"),
          "Quantity": ("quantity", "numeric_discrete"), "Location": ("ignore", "categorical_nominal"),
          "Transaction Date": ("transaction_date", "datetime"), "Discount Applied": ("ignore", "boolean")}


def test_a_blank_the_plan_fills_is_still_a_blank_of_the_file() -> None:
    # Kaggle's Discount Applied: a third of its cells blank, imputed "Unknown" by the plan. One line an order, so
    # a third of the orders have no value of the FILE's - not offered (the cleaned cells would say 0% blank).
    rows = [[f"TXN_{i}", f"CUST_{i % 7}", f"Item_{i % 5}", 10.5, 2, ["Online", "In-store"][i % 2],
             f"2024-12-{1 + i % 28:02d}", None if i % 3 == 0 else ["True", "False"][i % 2]] for i in range(30)]
    imputed = {"Discount Applied": _action("Discount Applied", "ignore", "boolean", "impute_constant",
                                           {"value": "Unknown"})}
    plan = _plan(KAGGLE, RECEIPT, actions=imputed)
    content = _csv(list(KAGGLE), rows)
    assert _eligible(content, plan) == ["Location"]
    assert _why(content, plan, "Discount Applied") == (
        'column "Discount Applied" cannot split sales: too many of its cells are blank')


# --- Q3: many values, unless nearly every line is its own ---------------------------------------------------------

BASE = {"day": ("transaction_date", "datetime"), "name": ("product_name", "text"),
        "qty": ("quantity", "numeric_discrete"), "price": ("unit_price", "numeric_continuous")}


def _values(values: list[str]) -> list[str]:
    rows = [[f"2024-12-{1 + i % 28:02d}", "Mug", 1, 2.5, value] for i, value in enumerate(values)]
    fields = BASE | {"store": ("ignore", "categorical_nominal")}
    return _eligible(_csv(list(fields), rows), _plan(fields))


def test_more_than_twelve_values_is_now_eligible() -> None:
    # Online Retail II's shape: 38 countries over many more lines (Q3: the top 8 and "Other" are drawn).
    assert _values([f"Country {i % 38}" for i in range(200)]) == ["store"]


def test_a_column_where_nearly_every_line_is_its_own_value_is_not() -> None:
    assert _values([f"Note {i}" for i in range(30)]) == []        # 30 values, 30 lines


@pytest.mark.parametrize(("values", "lines", "offered"), [
    (10, 20, True),    # 10 values in 20 lines: exactly half - offered
    (11, 20, False),   # more than half
    (9, 10, True),     # nine values are never grouped, so never id-like
])
def test_the_id_like_bound(values: int, lines: int, offered: bool) -> None:
    # Every value at least once, the rest repeating the first.
    column = [f"S{i}" for i in range(values)] + ["S0"] * (lines - values)
    assert _values(column) == (["store"] if offered else [])


def test_with_an_order_id_the_values_are_counted_against_orders() -> None:
    # 12 orders of 3 lines each, every order its own value: 12 values, 12 orders - id-like, though 36 lines.
    rows = [[f"#{o}", f"2024-12-{1 + o:02d}", f"Item {line}", 1, 5.0, f"Ref {o}"] for o in range(12)
            for line in range(3)]
    fields = {k: SHOPIFY[k] for k in ("Name", "Created at", "Lineitem name", "Lineitem quantity", "Lineitem price")}
    fields |= {"Ref": ("ignore", "categorical_nominal")}
    assert _eligible(_csv(list(fields), rows), _plan(fields, RECEIPT)) == []


# --- Q5: a column that says sale or return ------------------------------------------------------------------------

SQUARE = {"Date": ("transaction_date", "datetime"), "Item": ("product_name", "text"),
          "Qty": ("quantity", "numeric_discrete"), "Gross Sales": ("unit_price", "numeric_continuous"),
          "Event Type": ("ignore", "categorical_nominal"), "Location": ("ignore", "categorical_nominal")}


def _square(refund_location: str | None = None) -> bytes:
    # Square's item sales: a refund is a line of -1 at the item's price, Event Type "Refund".
    rows = []
    for i in range(30):
        refund = i % 5 == 0
        rows.append([f"2024-12-{1 + i % 28:02d}", f"Latte {i % 3}", -1 if refund else 1, 4.5,
                     "Refund" if refund else "Payment",
                     refund_location if refund and refund_location else ["Main St", "Harbour"][i % 2]])
    return _csv(list(SQUARE), rows)


def test_event_type_separates_sales_from_returns_and_is_not_offered() -> None:
    assert _eligible(_square(), _plan(SQUARE)) == ["Location"]
    assert _why(_square(), _plan(SQUARE), "Event Type") == (
        'column "Event Type" cannot split sales: each of its values holds only sales or only returns')


def test_a_location_whose_values_happen_to_split_sales_and_returns_is_not_offered_either() -> None:
    # Every refund at the returns desk: by the data alone it cannot be told from Event Type (doubtful = not offered).
    assert _eligible(_square("Returns desk"), _plan(SQUARE)) == []


def test_a_file_with_no_return_line_has_nothing_to_separate() -> None:
    rows = [[f"2024-12-{1 + i % 28:02d}", "Latte", 1, 4.5, ["Payment", "Gift"][i % 2], "Main St"] for i in range(20)]
    assert _eligible(_csv(list(SQUARE), rows), _plan(SQUARE)) == ["Event Type"]


# --- the lines cannot be read yet: nothing offered, the reason said -----------------------------------------------

def test_an_unanswered_date_question_offers_nothing_and_says_why(tmp_path: Path) -> None:
    rows = [[f"{1 + i % 12:02d}/{1 + i % 12:02d}/2024", "Mug", 1, 2.5, ["North", "South"][i % 2]] for i in range(24)]
    rows[0][0] = "03/04/2024"  # day and month both 12 or less in every row: the order cannot be proven
    fields = BASE | {"store": ("ignore", "categorical_nominal")}
    content = _csv(list(fields), rows)
    run = create_run(tmp_path)
    (run.path / "raw.csv").write_bytes(content)
    profile_run(tmp_path, run.run_id, now=NOW)

    def never(eligible: Any) -> BreakdownSuggestion:
        # Nothing offered, so nothing to ask: the service builds no client for an empty list.
        assert eligible == [], "the AI is not asked while the lines cannot be read"
        return BreakdownSuggestion(schema_version="1.0", generated_at=NOW, eligible=[], chosen=[],
                                   status="none_eligible", model_used=None)

    measured = measure_lines(read_csv_text(content).frame, _plan(fields))
    shown = breakdown_question_run(tmp_path, run.run_id, _plan(fields), measured, never)
    assert (shown.eligible, shown.status) == ([], "none_eligible")
    assert shown.message == "Answer how the dates are written to see which columns can split sales."


def test_no_date_mapped_offers_nothing_and_says_why() -> None:
    fields = BASE | {"day": ("ignore", "text"), "store": ("ignore", "categorical_nominal")}
    rows = [[f"2024-12-{1 + i % 28:02d}", "Mug", 1, 2.5, ["North", "South"][i % 2]] for i in range(20)]
    measured = measure_lines(read_csv_text(_csv(list(fields), rows)).frame, _plan(fields))
    assert measured.unavailable == "Map a date, and keep its column, to see which columns can split sales."
    assert measured.columns == {}


# --- execute checks the same lines ----------------------------------------------------------------------------------

def test_execute_refuses_a_column_with_two_values_in_one_order(tmp_path: Path) -> None:
    run = create_run(tmp_path)
    (run.path / "raw.csv").write_bytes(_shopify())
    profile_run(tmp_path, run.run_id, now=NOW)
    with pytest.raises(InvalidPlanError) as refused:
        execute_run(tmp_path, run.run_id, _plan(SHOPIFY, RECEIPT, breakdowns=["Vendor"]), now=NOW)
    assert refused.value.problems == ['column "Vendor" cannot split sales: an order holds two different values of it']
    execute_run(tmp_path, run.run_id, _plan(SHOPIFY, RECEIPT, breakdowns=["Payment Method"]), now=NOW)
    report = json.loads((run.path / "cleaning_report.json").read_text(encoding="utf-8"))
    assert report["breakdowns"] == ["Payment Method"]


# --- mutation's survivors (each its own test) ---------------------------------------------------------------------

def test_values_on_lines_not_counted_do_not_make_a_column_id_like() -> None:
    # 20 counted lines, 10 values: exactly half - offered. Five more lines with no price (counted in no figure)
    # carry five more values: they are not what is split, so they do not count.
    values = [f"S{i}" for i in range(10)] * 2
    rows = [[f"2024-12-{1 + i % 28:02d}", "Mug", 1, 2.5, value] for i, value in enumerate(values)]
    rows += [[f"2024-12-{1 + i:02d}", "Mug", 1, None, f"X{i}"] for i in range(5)]
    fields = BASE | {"store": ("ignore", "categorical_nominal")}
    assert _eligible(_csv(list(fields), rows), _plan(fields)) == ["store"]


def test_returns_only_on_blank_lines_make_the_blank_a_value_of_its_own() -> None:
    # Every sale names its till; every refund leaves it blank: the blank bucket holds only returns, each till
    # only sales - by the data alone, the column says sale or return (Q5). One line in ten: few blanks.
    rows = []
    for i in range(30):
        refund = i % 10 == 0
        rows.append([f"2024-12-{1 + i % 28:02d}", f"Latte {i % 3}", -1 if refund else 1, 4.5,
                     "Refund" if refund else "Payment", None if refund else ["Till 1", "Till 2"][i % 2]])
    content = _csv(list(SQUARE), rows)
    assert _why(content, _plan(SQUARE), "Location") == (
        'column "Location" cannot split sales: each of its values holds only sales or only returns')


def test_an_id_like_column_with_an_order_id_says_order() -> None:
    rows = [[f"#{o}", f"2024-12-{1 + o:02d}", f"Item {line}", 1, 5.0, f"Ref {o}"] for o in range(12)
            for line in range(3)]
    fields = {k: SHOPIFY[k] for k in ("Name", "Created at", "Lineitem name", "Lineitem quantity", "Lineitem price")}
    fields |= {"Ref": ("ignore", "categorical_nominal")}
    assert _why(_csv(list(fields), rows), _plan(fields, RECEIPT), "Ref") == (
        'column "Ref" cannot split sales: nearly every order has its own value')


def test_without_an_order_id_blanks_are_counted_on_the_whole_file_and_on_the_lines_split() -> None:
    # The per-line rule stands (Q4): the profile's share of the file's cells - 3 blanks in 40 cells (7.5%). The
    # scoped review's #4: they are 3 of the 20 lines counted in revenue (15%), which the split draws as a
    # "(blank)" bar - either share above 10% refuses (doubtful = not offered).
    rows = [[f"2024-12-{1 + i % 28:02d}", "Mug", 1, 2.5, None if i < 3 else ["North", "South"][i % 2]]
            for i in range(20)]
    rows += [[f"2024-12-{1 + i % 28:02d}", "Mug", 1, None, ["North", "South"][i % 2]] for i in range(20)]
    fields = BASE | {"store": ("ignore", "categorical_nominal")}
    assert _why(_csv(list(fields), rows), _plan(fields), "store") == (
        'column "store" cannot split sales: too many of its cells are blank')
    rows[0][4] = "North"  # 2 of 20 counted lines (10%), 2 of 40 cells: few blanks both ways
    assert _eligible(_csv(list(fields), rows), _plan(fields)) == ["store"]


# --- the doubt review's findings (each reproduced first) -------------------------------------------------------------

def test_a_per_line_attribute_with_blank_lines_is_never_filled_from_its_order() -> None:
    # F1 (probe V2): a value only on an order's second line - not Shopify's first-line field - is read per line:
    # its blank lines are blanks (half the lines here), so it is not offered.
    rows = []
    for order in range(10):
        rows.append([f"#{order}", f"2024-12-{1 + order:02d}", "Bag", 1, 90.0, None])
        rows.append([f"#{order}", f"2024-12-{1 + order:02d}", "Shirt", 1, 35.0, ["Acme", "Bolt"][order % 2]])
    fields = {k: SHOPIFY[k] for k in ("Name", "Created at", "Lineitem name", "Lineitem quantity", "Lineitem price")}
    fields |= {"Vendor": ("ignore", "categorical_nominal")}
    assert _why(_csv(list(fields), rows), _plan(fields, RECEIPT), "Vendor") == (
        'column "Vendor" cannot split sales: too many of its cells are blank')


def test_a_second_value_only_on_lines_not_counted_is_no_split() -> None:
    # O3: the file holds two values, but the second only on lines with no price (counted in no figure).
    rows = [[f"2024-12-{1 + i % 28:02d}", "Mug", 1, 2.5, "North"] for i in range(20)]
    rows += [[f"2024-12-{1 + i:02d}", "Mug", 1, None, "South"] for i in range(2)]
    fields = BASE | {"store": ("ignore", "categorical_nominal")}
    assert _why(_csv(list(fields), rows), _plan(fields), "store") == (
        'column "store" cannot split sales: it needs at least 2 values')
