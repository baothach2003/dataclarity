"""Thach's Q6 and Q7 (2026-10-16) on the export shapes (method
C:/Users/Happy/dashboard-q678-method.txt): a column whose values differ
between the lines of one order (a vendor, a product category) is a LINE
attribute - each line's sales to its own value, blanks per line - and is
offered with an order id; a column written on each order's first line only is
offered only once the user answers that it applies to the whole order
(Review asks, worded by code). Shapes built from the published export layouts
(Shopify, WooCommerce, Online Retail II, Kaggle), no customer data."""

import json
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from contracts.metrics import MetricsContract
from shared.run_registry import create_run
from stages.analyze.assemble import analyze_run
from stages.ingest.breakdown_review import measure_lines
from stages.ingest.breakdowns import whole_order_questions
from stages.ingest.cleaning import execute_run
from stages.ingest.profiling import profile_csv, profile_run, read_csv_text
from tests.stages.ingest.test_dashboard_q345_stage1 import RECEIPT, _csv, _eligible, _plan, _why

NOW = datetime(2026, 10, 16, tzinfo=UTC)
CAT = ("ignore", "categorical_nominal")


def _questions(content: bytes, plan) -> list[tuple[str, str, bool | None]]:
    measured = measure_lines(read_csv_text(content).frame, plan)
    return [(q.column, q.question, q.answer) for q in whole_order_questions(profile_csv(content, now=NOW), plan,
                                                                            measured)]


# --- Shopify: the order's fields on its first line, the line's fields on every line ------------------------------

SHOPIFY = {"Name": ("order_id", "identifier"), "Email": ("customer", "identifier"),
           "Financial Status": CAT, "Created at": ("transaction_date", "datetime"),
           "Lineitem quantity": ("quantity", "numeric_discrete"), "Lineitem name": ("product_name", "text"),
           "Lineitem price": ("unit_price", "numeric_continuous"), "Billing Name": ("ignore", "text"),
           "Shipping Method": CAT, "Payment Method": CAT, "Vendor": CAT, "Source": CAT}


def _shopify() -> bytes:
    rows = []
    for order in range(12):
        lines = 1 + order % 3  # orders of one, two and three lines
        for line in range(lines):
            first = line == 0
            # Vendor on every line: a shirt from Acme and a bag from Bolt can share an order - two values in one
            # order (Q6). The order's fields on its first line only (Shopify's export).
            rows.append([f"#{1000 + order}", f"c{order % 5}@example.com", "paid" if first else None,
                         f"2024-12-{1 + order * 30 // 11:02d}", 1, ["Shirt", "Bag", "Cap"][line], [20.0, 35.0, 9.0][line],
                         f"Buyer {order % 5}" if first else None,
                         ["Standard", "Express"][order % 2] if first else None,
                         ["Shopify Payments", "PayPal"][order % 2] if first else None,
                         ["Acme", "Bolt", "Core"][line], ["web", "pos"][order % 2] if first else None])
    return _csv(list(SHOPIFY), rows)


QUESTION = "{} is only on each order's first line: does it apply to the whole order?"


def test_shopify_asks_once_per_first_line_column_and_offers_the_line_attribute() -> None:
    plan = _plan(SHOPIFY, RECEIPT)
    # Vendor: three values, two or three in an order - a line attribute, every line valued: offered.
    assert _eligible(_shopify(), plan) == ["Vendor"]
    # Asked in the file's order; Financial Status (one value) and Billing Name (a person, Q8) never asked.
    assert _questions(_shopify(), plan) == [(c, QUESTION.format(c), None)
                                            for c in ("Shipping Method", "Payment Method", "Source")]


def test_shopify_a_yes_offers_the_column_and_a_no_does_not() -> None:
    plan = _plan(SHOPIFY, RECEIPT, whole_order={"Payment Method": True, "Source": False})
    assert _eligible(_shopify(), plan) == ["Payment Method", "Vendor"]
    assert [(c, a) for c, _, a in _questions(_shopify(), plan)] == [
        ("Shipping Method", None), ("Payment Method", True), ("Source", False)]
    assert _why(_shopify(), plan, "Source") == (
        'column "Source" cannot split sales: it is only on each order\'s first line, and it was not confirmed to '
        "apply to the whole order")


def test_shopify_end_to_end_each_line_to_its_vendor_and_each_order_to_its_payment(tmp_path: Path) -> None:
    run = create_run(tmp_path)
    (run.path / "raw.csv").write_bytes(_shopify())
    profile_run(tmp_path, run.run_id, now=NOW)
    plan = _plan(SHOPIFY, RECEIPT, breakdowns=["Vendor", "Payment Method"], whole_order={"Payment Method": True})
    execute_run(tmp_path, run.run_id, plan, now=NOW)
    analyze_run(tmp_path, run.run_id, now=NOW)
    metrics = MetricsContract.model_validate_json((run.path / "metrics.json").read_text(encoding="utf-8"))
    vendor, payment = metrics.by_dimension.breakdowns
    # December 2024 holds every order, the 1st to the 31st (the month whole; nothing compared). Orders 0..11 have 1, 2, 3, 1, 2, 3...
    # lines: four orders of each length. Acme sells the shirt (line 1) in all 12 orders: 12 x 20.00 = 240.00;
    # Bolt the bag in the 8 orders of two lines or more: 8 x 35.00 = 280.00; Core the cap in the 4 orders of
    # three lines: 4 x 9.00 = 36.00. Total 556.00.
    assert [(m.name, m.revenue_current) for m in vendor.members] == [("Acme", 240.0), ("Bolt", 280.0),
                                                                      ("Core", 36.0)]
    # Payment: each order's lines take its first line's method. Even orders (0, 2, ..., 10) Shopify Payments,
    # odd PayPal. Order lengths by number: 0:1, 1:2, 2:3, 3:1, 4:2, 5:3, 6:1, 7:2, 8:3, 9:1, 10:2, 11:3.
    # Even: 0 (20.00), 2 (64.00), 4 (55.00), 6 (20.00), 8 (64.00), 10 (55.00) = 278.00; odd: the rest, 278.00.
    assert [(m.name, m.revenue_current) for m in payment.members] == [("PayPal", 278.0), ("Shopify Payments", 278.0)]
    assert metrics.core.revenue_current == 556.0


# --- WooCommerce: the order's fields repeated on every line ------------------------------------------------------

WOO = {"Order Number": ("order_id", "identifier"), "Order Status": CAT, "Order Date": ("transaction_date", "datetime"),
       "Billing Email": ("customer", "identifier"), "First Name (Billing)": ("ignore", "text"),
       "Billing Country": CAT, "Payment Method Title": CAT,
       "Shipping Method Title": CAT, "Item Name": ("product_name", "text"), "Item Category": CAT,
       "Quantity": ("quantity", "numeric_discrete"), "Item Cost": ("unit_price", "numeric_continuous")}


def _woo() -> bytes:
    rows = []
    for order in range(12):
        for line in range(2):
            # Each order a mug (Kitchen) and a candle (Home): two categories in one order.
            rows.append([1000 + order, ["completed", "processing"][order % 2], f"2024-12-{1 + order:02d}",
                         f"c{order % 4}@example.com", ["Ann", "Bo", "Cy", "Di"][order % 4], ["GB", "FR", "DE"][order % 3],
                         ["Credit card", "PayPal"][order % 2], ["Flat rate", "Free shipping"][order % 2],
                         ["Mug", "Candle"][line], ["Kitchen", "Home"][line], 1, [8.0, 12.0][line]])
    return _csv(list(WOO), rows)


def test_woocommerce_offers_every_split_and_asks_nothing() -> None:
    # The billing first name (four repeat customers) is a person (Q8): never offered.
    plan = _plan(WOO, RECEIPT)
    assert _eligible(_woo(), plan) == ["Order Status", "Billing Country", "Payment Method Title",
                                       "Shipping Method Title", "Item Category"]
    assert _questions(_woo(), plan) == []


# --- Online Retail II: one country per invoice, on every line ------------------------------------------------------

ORII = {"Invoice": ("order_id", "identifier"), "StockCode": ("ignore", "identifier"),
        "Description": ("product_name", "text"), "Quantity": ("quantity", "numeric_discrete"),
        "InvoiceDate": ("transaction_date", "datetime"), "Price": ("unit_price", "numeric_continuous"),
        "Customer ID": ("customer", "identifier"), "Country": CAT, "Product Group": CAT}


def _orii() -> bytes:
    rows = []
    for invoice in range(30):
        for line in range(3):
            rows.append([f"5{36000 + invoice}", f"2{2000 + line}", ["MUG", "BAG", "CANDLE"][line], 2,
                         f"2011-11-{1 + invoice % 28:02d} 10:00", [1.25, 2.5, 3.75][line], 12000 + invoice % 9,
                         ["United Kingdom", "France", "Germany", "EIRE"][invoice % 4],
                         ["Kitchen", "Bags", "Home"][line]])
    return _csv(list(ORII), rows)


def test_online_retail_ii_offers_country_and_the_product_group_and_asks_nothing() -> None:
    plan = _plan(ORII)  # a customer column: the invoice id is trusted without the receipt answer
    assert _eligible(_orii(), plan) == ["Country", "Product Group"]
    assert _questions(_orii(), plan) == []


# --- Kaggle: one line per order -----------------------------------------------------------------------------------

def test_one_line_orders_ask_nothing() -> None:
    fields = {"Transaction ID": ("order_id", "identifier"), "Item": ("product_name", "text"),
              "Price Per Unit": ("unit_price", "numeric_continuous"), "Quantity": ("quantity", "numeric_discrete"),
              "Transaction Date": ("transaction_date", "datetime"), "Payment Method": CAT, "Location": CAT}
    rows = [[f"TXN_{i}", f"Item_{i % 5}", 10.5, 2, f"2024-12-{1 + i % 28:02d}", ["Cash", "Card"][i % 2],
             ["Online", "In-store"][i % 3 % 2]] for i in range(30)]
    content = _csv(list(fields), rows)
    assert _eligible(content, _plan(fields, RECEIPT)) == ["Payment Method", "Location"]
    assert _questions(content, _plan(fields, RECEIPT)) == []


# --- a question only where the answer matters ----------------------------------------------------------------------

def test_a_first_line_column_refused_anyway_is_never_asked_about() -> None:
    # Shopify's Financial Status: one value ("paid") - it splits nothing whatever the answer; Billing Name: a
    # person (Q8).
    asked = [c for c, _, _ in _questions(_shopify(), _plan(SHOPIFY, RECEIPT))]
    assert "Financial Status" not in asked and "Billing Name" not in asked


def test_a_first_line_column_with_too_many_orders_blank_is_not_asked_about() -> None:
    # Payment Method only on the first line of 3 orders of 12: 9 of 12 orders blank even if it applies to the
    # whole order - refused anyway, so never asked.
    frame = pd.read_csv(pd.io.common.BytesIO(_shopify()), dtype=str, keep_default_na=False)
    names = frame["Name"].tolist()
    keep = {"#1000", "#1001", "#1002"}
    frame.loc[[n not in keep for n in names], "Payment Method"] = ""
    content = frame.to_csv(index=False).encode()
    asked = [c for c, _, _ in _questions(content, _plan(SHOPIFY, RECEIPT))]
    assert "Payment Method" not in asked
    report = json.dumps(asked)  # Shipping Method and Source still asked
    assert "Shipping Method" in report and "Source" in report


# --- mutation's survivors (each its own test) ---------------------------------------------------------------------

def test_a_first_line_column_saying_sale_or_return_is_refused_as_drawn_filled() -> None:
    # Square-like, Event Type on each order's first line: refund orders hold only returns, sale orders only sales.
    # Measured as it would be drawn (filled, once answered yes), each value holds one kind - refused (Q5). Read
    # line by line, the blank bucket would hold both kinds and hide it.
    fields = {"Order": ("order_id", "identifier"), "Date": ("transaction_date", "datetime"),
              "Item": ("product_name", "text"), "Qty": ("quantity", "numeric_discrete"),
              "Price": ("unit_price", "numeric_continuous"), "Event Type": CAT}
    rows = []
    for order in range(12):
        refund = order % 4 == 0
        for line in range(2):
            rows.append([f"T{order}", f"2024-12-{1 + order:02d}", "Latte", -1 if refund else 1, 4.5,
                         ("Refund" if refund else "Payment") if line == 0 else None])
    content = _csv(list(fields), rows)
    plan = _plan(fields, RECEIPT, whole_order={"Event Type": True})
    assert _why(content, plan, "Event Type") == (
        'column "Event Type" cannot split sales: each of its values holds only sales or only returns')


def test_a_cell_the_plan_imputes_is_still_blank_line_by_line() -> None:
    # The per-line rule (Q6) reads the FILE's cells: 3 of the 20 counted lines blank (15%), imputed "Unknown" by
    # the plan - still blank; the profile's share (3 of 40 cells, 7.5%) alone would let it through.
    from tests.stages.ingest.test_dashboard_q345_stage1 import BASE, _action

    rows = [[f"2024-12-{1 + i % 28:02d}", "Mug", 1, 2.5, None if i < 3 else ["North", "South"][i % 2]]
            for i in range(20)]
    rows += [[f"2024-12-{1 + i % 28:02d}", "Mug", 1, None, ["North", "South"][i % 2]] for i in range(20)]
    fields = BASE | {"store": CAT}
    imputed = {"store": _action("store", "ignore", "categorical_nominal", "impute_constant", {"value": "Unknown"})}
    assert _why(_csv(list(fields), rows), _plan(fields, actions=imputed), "store") == (
        'column "store" cannot split sales: too many of its cells are blank')


def test_while_a_question_waits_review_says_so_and_once_answered_no_it_says_why(tmp_path: Path) -> None:
    from contracts.breakdowns import BreakdownSuggestion
    from stages.ingest.breakdowns import breakdown_question_run

    fields = {k: SHOPIFY[k] for k in ("Name", "Email", "Created at", "Lineitem quantity", "Lineitem name",
                                      "Lineitem price", "Payment Method")}
    frame = pd.read_csv(pd.io.common.BytesIO(_shopify()), dtype=str, keep_default_na=False)
    content = frame[list(fields)].to_csv(index=False).encode()
    run = create_run(tmp_path)
    (run.path / "raw.csv").write_bytes(content)
    profile_run(tmp_path, run.run_id, now=NOW)

    def none(eligible: list) -> BreakdownSuggestion:
        return BreakdownSuggestion(schema_version="1.0", generated_at=NOW, eligible=[c.column for c in eligible],
                                   chosen=[], status="none_eligible" if not eligible else "ai_unavailable",
                                   model_used=None)

    def ask(plan):
        return breakdown_question_run(tmp_path, run.run_id, plan, measure_lines(read_csv_text(content).frame, plan),
                                      none)

    waiting = ask(_plan(fields, RECEIPT))
    assert (waiting.eligible, waiting.status) == ([], "none_eligible")
    assert waiting.message == "Answer the question below to split sales by a column written on each order's first line."
    assert [(q.column, q.answer) for q in waiting.whole_order] == [("Payment Method", None)]
    refused = ask(_plan(fields, RECEIPT, whole_order={"Payment Method": False}))
    assert refused.message.startswith("No column of your file can split sales")
    assert [(q.column, q.answer) for q in refused.whole_order] == [("Payment Method", False)]
    offered = ask(_plan(fields, RECEIPT, whole_order={"Payment Method": True}))
    assert [c.column for c in offered.eligible] == ["Payment Method"]


def test_execute_lists_only_the_first_line_columns_answered_yes(tmp_path: Path) -> None:
    # A plan may hold a yes for a column that is no first-line column (Vendor): only Payment Method is filled.
    run = create_run(tmp_path)
    (run.path / "raw.csv").write_bytes(_shopify())
    profile_run(tmp_path, run.run_id, now=NOW)
    plan = _plan(SHOPIFY, RECEIPT, breakdowns=["Vendor", "Payment Method"],
                 whole_order={"Payment Method": True, "Vendor": True})
    execute_run(tmp_path, run.run_id, plan, now=NOW)
    report = json.loads((run.path / "cleaning_report.json").read_text(encoding="utf-8"))
    assert report["breakdowns_whole_order"] == ["Payment Method"]
