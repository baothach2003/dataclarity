"""The dashboard's step 4, stage 1's part (Thach's D4, 2026-10-14;
docs/DASHBOARD_DESIGN.md section 5; method C:/Users/Happy/dashboard-step4-method.txt):
which columns can split sales (code, from profile.json and the plan), the AI's
choice among them - FAKED, no real call - and execute's check. Shapes built
from the published export layouts (no customer data)."""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import anthropic
import httpx
import pytest

from contracts.breakdowns import BreakdownSuggestion
from contracts.cleaning import CleaningPlanContract, ColumnAction
from shared.ai_client import AIClient
from shared.run_registry import create_run
from stages.ingest.breakdowns import (MAX_AI_COLUMNS, MESSAGES, breakdown_question_run, breakdowns_problem,
                                      eligible_columns, question, run_suggestion, suggest_breakdowns,
                                      why_not_eligible)
from stages.ingest.cleaning import SCHEMA_VERSION, execute_run
from stages.ingest.plan_validation import InvalidPlanError, validate_final_plan
from stages.ingest.profiling import profile_csv, profile_run
from tests.ai_fakes import FakeMessages, FakeResponse

NOW = datetime(2026, 10, 14, tzinfo=UTC)


def _csv(header: list[str], rows: list[list[Any]]) -> bytes:
    lines = [",".join(header)] + [",".join("" if v is None else str(v) for v in row) for row in rows]
    return ("\n".join(lines) + "\n").encode()


def _plan(fields: dict[str, tuple[str, str]], drop: tuple[str, ...] = (), breakdowns: list[str] | None = None,
          ) -> CleaningPlanContract:
    """`fields`: column -> (canonical field, semantic type)."""
    actions = [ColumnAction(source_name=name, semantic_type=kind, canonical_field=field,
                            action="drop_column" if name in drop else "flag_only", params={} if name in drop else
                            {"note": "n"}, rationale="r", alternatives=[], edited_by_user=False)
               for name, (field, kind) in fields.items()]
    return CleaningPlanContract(schema_version="4.4", generated_at=NOW, source="manual", dataset_actions=[],
                                column_actions=actions, breakdowns=breakdowns or [])


def _eligible(content: bytes, fields: dict[str, tuple[str, str]], **plan: Any) -> list[str]:
    return [c.column for c in eligible_columns(profile_csv(content, now=NOW), _plan(fields, **plan))]


# --- the shapes (design 6.1, 6.3) --------------------------------------------------------------------------------

KAGGLE_FIELDS = {"Transaction ID": ("order_id", "identifier"), "Customer ID": ("customer", "identifier"),
                 "Category": ("category", "categorical_nominal"), "Item": ("product_name", "text"),
                 "Price Per Unit": ("unit_price", "numeric_continuous"), "Quantity": ("quantity", "numeric_discrete"),
                 "Total Spent": ("ignore", "numeric_continuous"), "Payment Method": ("ignore", "categorical_nominal"),
                 "Location": ("ignore", "categorical_nominal"), "Transaction Date": ("transaction_date", "datetime"),
                 "Discount Applied": ("ignore", "boolean")}


def _kaggle() -> bytes:
    rows = [[f"TXN_{i}", f"CUST_{i % 5}", ["Food", "Furniture"][i % 2], f"Item_{i % 7}", 10.5, 2, 21.0,
             ["Cash", "Credit Card", "Digital Wallet"][i % 3], ["Online", "In-store"][i % 2],
             f"2024-{11 + i % 2}-{1 + i % 28:02d}", None if i % 3 == 0 else ["True", "False"][i % 2]]
            for i in range(30)]
    return _csv(list(KAGGLE_FIELDS), rows)


def test_kaggle_offers_payment_method_and_location_only() -> None:
    # Discount Applied: a third blank (as the real file's 33%); Total Spent: amounts.
    assert _eligible(_kaggle(), KAGGLE_FIELDS) == ["Payment Method", "Location"]


def test_online_retail_ii_country_has_too_many_values() -> None:
    fields = {"Invoice": ("order_id", "identifier"), "Description": ("product_name", "text"),
              "Quantity": ("quantity", "numeric_discrete"), "InvoiceDate": ("transaction_date", "datetime"),
              "Price": ("unit_price", "numeric_continuous"), "Country": ("ignore", "categorical_nominal")}
    rows = [[f"5{i}", f"Product {i}", 1, f"2011-11-{1 + i % 28:02d}", 1.25, f"Country {i % 15}"] for i in range(40)]
    profile = profile_csv(_csv(list(fields), rows), now=NOW)
    assert eligible_columns(profile, _plan(fields)) == []
    country = next(c for c in profile.columns if c.name == "Country")
    assert why_not_eligible(country, _plan(fields), "Country") == "it needs 2 to 12 values"


def test_shopify_order_fields_on_first_lines_only_are_too_blank_vendor_is_offered() -> None:
    fields = {"Name": ("order_id", "identifier"), "Created at": ("transaction_date", "datetime"),
              "Lineitem name": ("product_name", "text"), "Lineitem quantity": ("quantity", "numeric_discrete"),
              "Lineitem price": ("unit_price", "numeric_continuous"),
              "Financial Status": ("ignore", "categorical_nominal"), "Payment Method": ("ignore", "categorical_nominal"),
              "Source": ("ignore", "categorical_nominal"), "Vendor": ("ignore", "categorical_nominal")}
    rows = []
    for order in range(10):
        for line in range(3):  # three lines an order; Shopify writes the order's fields on its first line only
            first = line == 0
            rows.append([f"#10{order}", f"2024-12-{1 + order:02d}", f"Item {line}", 1, 9.99,
                         "paid" if first else None, ["Shopify Payments", "PayPal"][order % 2] if first else None,
                         ["web", "pos"][order % 2] if first else None, ["Acme", "Bolt", "Core"][line]])
    assert _eligible(_csv(list(fields), rows), fields) == ["Vendor"]


def test_woocommerce_and_square_offer_their_channel_columns() -> None:
    woo = {"Order Number": ("order_id", "identifier"), "Order Date": ("transaction_date", "datetime"),
           "Order Status": ("ignore", "categorical_nominal"), "Payment Method Title": ("ignore", "categorical_nominal"),
           "Shipping Method Title": ("ignore", "categorical_nominal"), "Item Name": ("product_name", "text"),
           "Quantity": ("quantity", "numeric_discrete"), "Item Cost": ("unit_price", "numeric_continuous"),
           "Billing Country": ("ignore", "categorical_nominal")}
    rows = [[i, f"2024-12-{1 + i % 28:02d}", ["completed", "refunded"][i % 2], ["Card", "PayPal", "Bank"][i % 3],
             ["Flat rate", "Free shipping"][i % 2], f"Item {i % 4}", 1, 12.0, ["AU", "NZ", "US"][i % 3]]
            for i in range(30)]
    assert _eligible(_csv(list(woo), rows), woo) == ["Order Status", "Payment Method Title", "Shipping Method Title",
                                                     "Billing Country"]
    square = {"Date": ("transaction_date", "datetime"), "Item": ("product_name", "text"),
              "Qty": ("quantity", "numeric_discrete"), "Gross Sales": ("unit_price", "numeric_continuous"),
              "Transaction ID": ("order_id", "identifier"), "Event Type": ("ignore", "categorical_nominal"),
              "Location": ("ignore", "categorical_nominal"), "Channel": ("ignore", "categorical_nominal"),
              "Card Brand": ("ignore", "categorical_nominal")}
    rows = [[f"2024-12-{1 + i % 28:02d}", f"Latte {i % 3}", 1, 4.5, f"T{i}", ["Payment", "Refund"][i % 2],
             ["Main St", "Harbour"][i % 2], ["Point of Sale", "Online Store"][i % 2], ["Visa", "Mastercard"][i % 2]]
            for i in range(30)]
    assert _eligible(_csv(list(square), rows), square) == ["Event Type", "Location", "Channel", "Card Brand"]


def test_a_date_and_amount_file_cannot_be_analysed_in_v1() -> None:
    # Stripe's shape (design 6.4, Q2): no product and no quantity - stage 1's required fields - so the plan
    # cannot run and there is no dashboard. A known limit, pinned.
    fields = {"Created (UTC)": ("transaction_date", "datetime"), "Amount": ("unit_price", "numeric_continuous")}
    with pytest.raises(InvalidPlanError, match="required field"):
        validate_final_plan(_plan(fields), list(fields), for_execution=True)


# --- each rule alone (design 5.1) ---------------------------------------------------------------------------------

BASE = {"day": ("transaction_date", "datetime"), "name": ("product_name", "text"),
        "qty": ("quantity", "numeric_discrete"), "price": ("unit_price", "numeric_continuous")}


def _one(values: list[Any], kind: str = "categorical_nominal", field: str = "ignore", header: str = "store",
         drop: bool = False) -> str | None:
    rows = [[f"2024-12-{1 + i % 28:02d}", "Mug", 1, 2.5, value] for i, value in enumerate(values)]
    fields = BASE | {header: (field, kind)}
    profile = profile_csv(_csv(list(fields), rows), now=NOW)
    column = next(c for c in profile.columns if c.name == header)
    return why_not_eligible(column, _plan(fields, drop=(header,) if drop else ()), header)


THREE = ["North", "South", "East"] * 10


@pytest.mark.parametrize(("case", "expected"), [
    (dict(values=THREE), None),
    (dict(values=THREE, drop=True), "the plan drops it"),
    (dict(values=THREE, field="category"), "the plan already uses it as a field"),
    (dict(values=THREE, header="Unnamed: 5"), "it has no header"),
    (dict(values=THREE, kind="identifier"), "it is not a column of categories"),
    (dict(values=THREE, kind="numeric_discrete"), "it is not a column of categories"),
    (dict(values=["North"] * 30), "it needs 2 to 12 values"),
    (dict(values=[f"S{i % 12}" for i in range(30)]), None),
    (dict(values=[f"S{i % 13}" for i in range(30)]), "it needs 2 to 12 values"),
    (dict(values=THREE[:27] + [None] * 3), None),            # 10% blank: few blanks
    (dict(values=THREE[:26] + [None] * 4), "too many of its cells are blank"),  # 13.3%
    (dict(values=[1, 2, 3] * 10), "its values are numbers"),
    (dict(values=['"1,000"', '"2,000"', '"3,500"'] * 10), "its values are numbers"),  # quoted in the CSV
    (dict(values=["2024-01-05", "2024-02-05", "2024-03-05"] * 10), "its values are dates"),
    (dict(values=["Yes", "No"] * 15, kind="boolean"), None),
])
def test_each_rule_alone(case: dict[str, Any], expected: str | None) -> None:
    assert _one(**case) == expected


def test_a_column_not_profiled_is_not_eligible() -> None:
    assert why_not_eligible(None, _plan(BASE), "store") == "it is not one of the file's profiled columns"


# --- the AI's choice, faked (design 5.3) --------------------------------------------------------------------------


def _suggest(*outcomes: FakeResponse | Exception, content: bytes | None = None) -> tuple[BreakdownSuggestion,
                                                                                     FakeMessages]:
    messages = FakeMessages(*outcomes)
    eligible = eligible_columns(profile_csv(content or _kaggle(), now=NOW), _plan(KAGGLE_FIELDS))
    return suggest_breakdowns(lambda: AIClient(messages), "test-model", eligible, now=NOW), messages


def _reply(*names: str) -> FakeResponse:
    return FakeResponse(json.dumps({"breakdowns": list(names)}))


def test_a_valid_answer_is_the_suggestion() -> None:
    suggestion, messages = _suggest(_reply("Location", "Payment Method"))
    assert (suggestion.status, suggestion.chosen, suggestion.model_used) == (
        "chosen", ["Location", "Payment Method"], "served-model")
    assert suggestion.eligible == ["Payment Method", "Location"] and len(messages.calls) == 1


def test_the_ai_sees_only_the_eligible_columns_and_their_top_values() -> None:
    _, messages = _suggest(_reply("Location"))
    prompt = messages.calls[0]["messages"][0]["content"]
    sent = json.loads(prompt.split("THE COLUMNS\n", 1)[1].split("\n\nOUTPUT SCHEMA", 1)[0])
    assert [c["column"] for c in sent["columns"]] == ["Payment Method", "Location"]
    assert sorted(sent["columns"][1]["values"]) == ["In-store", "Online"]
    assert "TXN_" not in prompt and "CUST_" not in prompt and "Item_" not in prompt  # no other cell of the file
    assert messages.calls[0]["max_tokens"] == 300


def test_choosing_none_is_an_answer() -> None:
    suggestion, _ = _suggest(_reply())
    assert (suggestion.status, suggestion.chosen) == ("chosen", [])


@pytest.mark.parametrize("reply", [
    _reply("Location", "Store"),                  # a name off the list
    _reply("Location", "Location"),               # twice
    _reply("Location", "Payment Method", "Category"),  # three
    _reply("location"),                           # not as written
    FakeResponse("this is not json"),
    FakeResponse('{"columns": ["Location"]}'),     # another shape
    FakeResponse('{"breakdowns": ["Location"]}', stop_reason="max_tokens"),
])
def test_any_invalid_answer_is_no_suggestion_and_never_retried(reply: FakeResponse) -> None:
    suggestion, messages = _suggest(reply, _reply("Location"))
    assert (suggestion.status, suggestion.chosen, suggestion.model_used) == ("ai_unavailable", [], None)
    assert len(messages.calls) == 1  # no retry: the second reply is never asked for


def test_a_timeout_is_no_suggestion() -> None:
    error = anthropic.APITimeoutError(request=httpx.Request("POST", "https://api.anthropic.com"))
    suggestion, messages = _suggest(error)
    assert suggestion.status == "ai_unavailable" and len(messages.calls) == 1


def test_no_eligible_column_asks_no_ai_and_builds_no_client() -> None:
    def no_client() -> AIClient:
        raise AssertionError("the AI must not be asked")

    suggestion = suggest_breakdowns(no_client, "test-model", [], now=NOW)
    assert (suggestion.status, suggestion.eligible, suggestion.chosen) == ("none_eligible", [], [])


# --- Review's question and the stored answer ----------------------------------------------------------------------


def test_the_question_words_where_the_suggestion_came_from() -> None:
    suggestion, _ = _suggest(_reply("Location"))
    eligible = eligible_columns(profile_csv(_kaggle(), now=NOW), _plan(KAGGLE_FIELDS))
    asked = question(suggestion, eligible)
    assert (asked.suggested, asked.status, asked.message) == (["Location"], "chosen", MESSAGES["chosen"])
    remapped = _plan(KAGGLE_FIELDS | {"Location": ("category", "categorical_nominal")})
    after = question(suggestion, eligible_columns(profile_csv(_kaggle(), now=NOW), remapped))
    # Mapped since: no longer offered, so no longer suggested (and "none chosen" said).
    assert (after.suggested, after.message) == ([], MESSAGES["none_chosen"])
    failed, _ = _suggest(FakeResponse("x"))
    assert question(failed, eligible).message == MESSAGES["ai_unavailable"]
    assert question(suggest_breakdowns(lambda: AIClient(FakeMessages()), "m", [], now=NOW), []).message == \
        MESSAGES["none_eligible"]


def _profiled(tmp_path: Path, content: bytes) -> str:
    run = create_run(tmp_path)
    (run.path / "raw.csv").write_bytes(content)
    profile_run(tmp_path, run.run_id, now=NOW)
    return run.run_id


def test_the_ai_is_asked_once_per_run_and_the_answer_stored_even_when_it_failed(tmp_path: Path) -> None:
    run_id = _profiled(tmp_path, _kaggle())
    asked: list[int] = []

    def ask(eligible: Any) -> BreakdownSuggestion:
        asked.append(1)
        return suggest_breakdowns(lambda: AIClient(FakeMessages(FakeResponse("not json"))), "m", eligible, now=NOW)

    def stored(eligible: Any) -> BreakdownSuggestion:
        return run_suggestion(tmp_path, run_id, eligible, ask)

    first = breakdown_question_run(tmp_path, run_id, _plan(KAGGLE_FIELDS), stored)
    second = breakdown_question_run(tmp_path, run_id, _plan(KAGGLE_FIELDS), stored)
    assert asked == [1] and first == second and first.status == "ai_unavailable"
    stored = json.loads((tmp_path / run_id / "breakdown_suggestion.json").read_text(encoding="utf-8"))
    assert (stored["status"], stored["schema_version"]) == ("ai_unavailable", "1.0")


# --- execute (design 5.5) ------------------------------------------------------------------------------------------


def _executed(tmp_path: Path, breakdowns: list[str]) -> dict[str, Any]:
    run_id = _profiled(tmp_path, _kaggle())
    fields = KAGGLE_FIELDS | {"Transaction Date": ("transaction_date", "datetime")}
    execute_run(tmp_path, run_id, _plan(fields, breakdowns=breakdowns), now=NOW)
    return {name: json.loads((tmp_path / run_id / name).read_text(encoding="utf-8"))
            for name in ("cleaning_report.json", "plan_final.json")}


def test_execute_records_the_users_columns(tmp_path: Path) -> None:
    files = _executed(tmp_path, ["Location"])
    assert files["cleaning_report.json"]["breakdowns"] == ["Location"]
    assert files["plan_final.json"]["breakdowns"] == ["Location"]
    assert SCHEMA_VERSION == "4.4"  # 4.4: the sales breakdowns (the dashboard); 4.3 the currency


def test_execute_without_a_breakdown_writes_no_field(tmp_path: Path) -> None:
    files = _executed(tmp_path, [])
    assert "breakdowns" not in files["cleaning_report.json"] and "breakdowns" not in files["plan_final.json"]


@pytest.mark.parametrize(("names", "problem"), [
    (["Total Spent"], 'column "Total Spent" cannot split sales: it is not a column of categories'),
    (["Category"], 'column "Category" cannot split sales: the plan already uses it as a field'),
    (["Nowhere"], 'column "Nowhere" cannot split sales: it is not one of the file\'s profiled columns'),
    (["Location", "Location"], "a column is chosen twice to split sales"),
    (["Location", "Payment Method", "Discount Applied"], "sales can be split by 2 columns at most"),
])
def test_execute_refuses_a_column_that_cannot_split_sales(tmp_path: Path, names: list[str], problem: str) -> None:
    with pytest.raises(InvalidPlanError) as refused:
        _executed(tmp_path, names)
    assert refused.value.problems == [problem]


def test_the_check_reads_the_profile_and_the_final_plan() -> None:
    profile = profile_csv(_kaggle(), now=NOW)
    assert breakdowns_problem(profile, _plan(KAGGLE_FIELDS, breakdowns=["Location"])) is None
    dropped = _plan(KAGGLE_FIELDS, drop=("Location",), breakdowns=["Location"])
    assert breakdowns_problem(profile, dropped) == 'column "Location" cannot split sales: the plan drops it'


# --- the gaps mutation found (each its own test) ------------------------------------------------------------------


def test_a_users_column_named_like_stage_1s_is_recorded_under_its_cleaned_name(tmp_path: Path) -> None:
    # A source column called "line_class" is kept as "line_class_source" (Thach's Q24): stage 2 reads that name.
    rows = [list(row) + [["North", "South", "East"][i % 3]] for i, row in enumerate(
        [line.split(",") for line in _kaggle().decode().splitlines()[1:]])]
    content = _csv([*KAGGLE_FIELDS, "line_class"], rows)
    run_id = _profiled(tmp_path, content)
    fields = KAGGLE_FIELDS | {"line_class": ("ignore", "categorical_nominal")}
    execute_run(tmp_path, run_id, _plan(fields, breakdowns=["line_class"]), now=NOW)
    report = json.loads((tmp_path / run_id / "cleaning_report.json").read_text(encoding="utf-8"))
    assert report["breakdowns"] == ["line_class_source"]
    header = (tmp_path / run_id / "cleaned.csv").read_text(encoding="utf-8").splitlines()[0]
    assert "line_class_source" in header


def test_generic_cleaning_refuses_a_breakdown_and_writes_nothing(tmp_path: Path) -> None:
    # Generic cleaning analyses nothing: names left in its plan are refused, never written unchecked (review #8).
    run_id = _profiled(tmp_path, _kaggle())
    with pytest.raises(InvalidPlanError, match="not analysed as sales data"):
        execute_run(tmp_path, run_id, _plan(KAGGLE_FIELDS, breakdowns=["price", "nope", "x"]), now=NOW,
                    require_required_fields=False)
    assert not (tmp_path / run_id / "plan_final.json").exists()
    execute_run(tmp_path, run_id, _plan(KAGGLE_FIELDS), now=NOW, require_required_fields=False)
    report = json.loads((tmp_path / run_id / "cleaning_report.json").read_text(encoding="utf-8"))
    assert "breakdowns" not in report


def test_a_suggestion_that_is_not_chosen_chooses_nothing() -> None:
    stamp = {"schema_version": "1.0", "generated_at": NOW, "eligible": ["Location"]}
    with pytest.raises(ValueError, match="chooses nothing"):
        BreakdownSuggestion(**stamp, chosen=["Location"], status="ai_unavailable", model_used=None)
    with pytest.raises(ValueError, match="model answered"):
        BreakdownSuggestion(**stamp, chosen=[], status="chosen", model_used=None)


def test_three_names_from_the_list_are_still_refused() -> None:
    woo = {"Order Number": ("order_id", "identifier"), "Order Date": ("transaction_date", "datetime"),
           "Order Status": ("ignore", "categorical_nominal"), "Payment Method Title": ("ignore", "categorical_nominal"),
           "Shipping Method Title": ("ignore", "categorical_nominal"), "Item Name": ("product_name", "text"),
           "Quantity": ("quantity", "numeric_discrete"), "Item Cost": ("unit_price", "numeric_continuous")}
    rows = [[i, f"2024-12-{1 + i % 28:02d}", ["completed", "refunded"][i % 2], ["Card", "PayPal", "Bank"][i % 3],
             ["Flat rate", "Free shipping"][i % 2], f"Item {i % 4}", 1, 12.0] for i in range(30)]
    eligible = eligible_columns(profile_csv(_csv(list(woo), rows), now=NOW), _plan(woo))
    assert len(eligible) == 3
    messages = FakeMessages(_reply("Order Status", "Payment Method Title", "Shipping Method Title"))
    suggestion = suggest_breakdowns(lambda: AIClient(messages), "m", eligible, now=NOW)
    assert (suggestion.status, suggestion.chosen) == ("ai_unavailable", [])


# --- the step 4 review's findings (each reproduced first) ------------------------------------------------------------

MANUAL = {"Order": ("order_id", "identifier"), "Day": ("transaction_date", "datetime"),
          "Qty": ("quantity", "numeric_discrete"), "Price": ("unit_price", "numeric_continuous")}


def _quoted(value: str) -> str:
    return f'"{value}"' if "," in value else value


def _with(column: str, values: list[str], kind: str = "text") -> list[str]:
    rows = [[i, f"2024-12-{1 + i % 28:02d}", 1, 9.5, _quoted(values[i % len(values)])] for i in range(30)]
    return _eligible(_csv([*MANUAL, column], rows), MANUAL | {column: ("ignore", kind)})


@pytest.mark.parametrize("values", [
    ["$4.50", "$0.00", "$12.00"], ["\u20ac4.50", "\u20ac0.00"], ["\u00a34.50", "\u00a30.00"],
    ["-$1.00", "-$0.50", "$0.00"], ["10%", "15%", "0%"], ["4,50 EUR", "0,00 EUR"], ["USD 4.50", "USD 0.00"],
    ["(1.00)", "(2.50)", "0.00"], ["1kg", "2kg", "5kg"], ["1 pc", "2 pc", "6 pc"], ["0", "1", "2", "none"],
    # the scoped review's R2
    ["30.000 \u0111", "15.000 \u0111"], ["30.000\u0111", "0\u0111"], ["R$ 4,90", "R$ 0,00"], ["US$4.90", "US$0.00"],
    ["Rs. 49", "Rs. 0"], ["\u22124.90", "\u22121.00"],
])
def test_an_amount_however_written_is_never_offered(values: list[str]) -> None:
    # A manual plan types every column "text" - only the values can say it is an amount (review #3).
    assert _with("Extra", values) == []
    assert _with("Extra", values, "categorical_nominal") == []


@pytest.mark.parametrize("values", [
    ["Q1", "Q2", "Q3", "Q4"], ["2024-Q1", "2024-Q2"], ["2024-W01", "2024-W02", "2024-W03"],
    ["January", "February", "March"], ["Jan", "Feb", "Mar"], ["2024-12-01", "North"], ["H1", "H2"],
    ["Sept", "Oct."], ["May 2024", "June 2024"],
])
def test_a_period_or_a_date_is_never_offered(values: list[str]) -> None:
    # Two compared months split by a period are no split; one date among the values is doubt enough (review #7).
    assert _with("When", values) == []


@pytest.mark.parametrize("values", [["North", "South", "East"], ["Card", "Cash"], ["Store 12", "Store 7"],
                                    ["Monday", "Tuesday", "Friday"], ["Web", "POS", "Phone"],
                                    # the scoped review's R1: words that begin like a month's name
                                    ["Online", "Marketplace", "Store"], ["Approved", "Declined"],
                                    ["Married", "Single"], ["Yes", "Maybe", "No"], ["Marseille", "Paris", "Lyon"],
                                    ["Decor", "Novelty", "Junior"]])
def test_categories_are_still_offered(values: list[str]) -> None:
    assert _with("Channel", values) == ["Channel"]


def test_a_column_with_a_number_format_is_not_offered(tmp_path: Path) -> None:
    content = _csv([*MANUAL, "Net"], [[i, f"2024-12-{1 + i % 28:02d}", 1, 9.5, _quoted(["1.234,50", "2.000,00"][i % 2])]
                                      for i in range(30)])
    profile = profile_csv(content, now=NOW)
    net = next(c for c in profile.columns if c.name == "Net")
    assert net.number_format is not None
    assert why_not_eligible(net, _plan(MANUAL | {"Net": ("ignore", "text")}), "Net") == "its values are numbers"


def test_the_ais_input_is_bounded_values_cut_and_twelve_columns_at_most() -> None:
    # A long value is cut as AI_PIPELINE section 1 cuts it; a wide file sends 12 columns (review #1).
    long = ["A" * 5000, "B" * 5000]
    header = [*MANUAL, "Terms", *[f"Flag {n}" for n in range(20)]]
    rows = [[i, f"2024-12-{1 + i % 28:02d}", 1, 9.5, long[i % 2], *[["Yes", "No"][i % 2]] * 20] for i in range(30)]
    fields = MANUAL | {name: ("ignore", "text") for name in header[4:]}
    eligible = eligible_columns(profile_csv(_csv(header, rows), now=NOW), _plan(fields))
    assert len(eligible) == 21 and max(len(v) for v in eligible[0].values) == 100
    messages = FakeMessages(_reply("Terms"))
    suggestion = suggest_breakdowns(lambda: AIClient(messages), "m", eligible, now=NOW)
    sent = messages.calls[0]["messages"][0]["content"]
    assert suggestion.eligible == header[4:4 + MAX_AI_COLUMNS] and "Flag 11" not in sent and "Flag 10" in sent
    assert "A" * 101 not in sent and len(sent) < 12 * 10 * 100 + 3000


def test_an_answer_with_anything_beside_the_names_is_no_answer() -> None:
    eligible = eligible_columns(profile_csv(_kaggle(), now=NOW), _plan(KAGGLE_FIELDS))
    messages = FakeMessages(FakeResponse('{"breakdowns": ["Location"], "why": "shops differ"}'))
    suggestion = suggest_breakdowns(lambda: AIClient(messages), "m", eligible, now=NOW)
    assert (suggestion.status, suggestion.chosen) == ("ai_unavailable", [])


def test_nothing_is_stored_while_nothing_is_eligible_so_a_later_edit_still_asks(tmp_path: Path) -> None:
    run_id = _profiled(tmp_path, _kaggle())
    asked: list[int] = []

    def ask(eligible: Any) -> BreakdownSuggestion:
        asked.append(1)
        return suggest_breakdowns(lambda: AIClient(FakeMessages(_reply("Location"))), "m", eligible, now=NOW)

    def stored(eligible: Any) -> BreakdownSuggestion:
        return run_suggestion(tmp_path, run_id, eligible, ask)

    used = KAGGLE_FIELDS | {"Payment Method": ("ignore", "identifier"), "Location": ("ignore", "identifier")}
    first = breakdown_question_run(tmp_path, run_id, _plan(used), stored)
    assert first.status == "none_eligible" and not (tmp_path / run_id / "breakdown_suggestion.json").exists()
    second = breakdown_question_run(tmp_path, run_id, _plan(KAGGLE_FIELDS), stored)
    assert (second.status, second.suggested, len(asked)) == ("chosen", ["Location"], 2)
    assert json.loads((tmp_path / run_id / "breakdown_suggestion.json").read_text(encoding="utf-8"))["chosen"] == [
        "Location"]


def test_a_stored_file_this_version_cannot_read_is_no_suggestion_and_no_second_call(tmp_path: Path) -> None:
    run_id = _profiled(tmp_path, _kaggle())
    (tmp_path / run_id / "breakdown_suggestion.json").write_text('{"schema_version": "9.0"}', encoding="utf-8")

    def ask(eligible: Any) -> BreakdownSuggestion:
        raise AssertionError("the AI is asked once per run")

    shown = breakdown_question_run(tmp_path, run_id, _plan(KAGGLE_FIELDS),
                                   lambda eligible: run_suggestion(tmp_path, run_id, eligible, ask))
    assert (shown.status, shown.suggested) == ("ai_unavailable", [])
