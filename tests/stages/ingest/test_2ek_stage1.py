"""Session 2E-k (Thach), stage 1, written before the change.

- The customer column is never imputed, keyed on the canonical field whatever
  its semantic type: an imputed "Unknown" became the top customer carrying
  every walk-in's money, and let an unconfirmed batch code pass as a receipt
  number (2E-e2 doubt-review cycle 2 F11, cycle 3 F1).
- Walk-in placeholders: stage 1 measures, on the raw file and the AI's
  mapping, the customer values that are a known placeholder word or carry 10%
  or more of the counted lines or of the sale revenue. Review asks about each.
  10% sits in the measured gap: the largest real customer is 4.4% on either
  demo file, Online Retail II's walk-ins are 22.8% of its lines.
- schema_inference, plan and cleaning_report go to 2.2 (optional fields).
"""

from pathlib import Path

import pandas as pd
import pytest

from contracts.cleaning import CleaningPlanContract, ColumnAction, OrderConfirmations
from contracts.profile import CustomerPlaceholder, SchemaInferenceContract
from stages.ingest import ai_plan, ai_schema, cleaning
from stages.ingest.customer_placeholders import PLACEHOLDER_SHARE, placeholder_candidates
from stages.ingest.plan_validation import InvalidPlanError
from stages.ingest.transform_catalog import is_legal
from tests.ai_fakes import FakeMessages
from tests.stages.ingest.cleaning_fixtures import NOW, column_action, make_plan, raw_run
from tests.stages.ingest.schema_answers import answer, column, profiled_run, run

MAPPING = {"Day": "transaction_date", "Qty": "quantity", "Price": "unit_price", "Cust": "customer"}


@pytest.mark.parametrize("semantic", ["text", "categorical_nominal", "identifier", "numeric_discrete"])
@pytest.mark.parametrize("action", ["impute_mode", "impute_constant", "impute_median", "impute_mean"])
def test_a_customer_column_is_never_imputed(semantic: str, action: str) -> None:
    assert not is_legal(action, semantic, "customer")  # type: ignore[arg-type]  # plain strs for the Literals


def test_a_customer_column_can_still_be_dropped_or_trimmed() -> None:
    assert is_legal("drop_rows_missing", "text", "customer")
    assert is_legal("trim_whitespace", "text", "customer")


def test_the_prompt_says_the_customer_column_is_never_imputed() -> None:
    text = Path("prompts/cleaning_plan.md").read_text(encoding="utf-8")

    assert "customer" in text.split("STRICT RULES")[1].split("Every rationale")[0]


def test_a_plan_imputing_the_customer_column_is_refused_at_execution(tmp_path: Path) -> None:
    csv = b"sku,name,qty,price,day,cust\nA1,Mug,3,9.99,2024-01-05,Ann\nB2,Cup,1,5,2024-01-06,\n"
    run_id = raw_run(tmp_path, csv)
    plan = make_plan([*_default_actions(), ColumnAction.model_validate({
        "source_name": "cust", "semantic_type": "text", "canonical_field": "customer",
        "action": "impute_constant", "params": {"value": "Unknown"}, "rationale": "",
        "alternatives": [], "edited_by_user": True})])

    with pytest.raises(InvalidPlanError, match="customer"):
        cleaning.execute_run(tmp_path, run_id, plan, now=NOW)


def _default_actions():
    return [column_action("sku", "trim_whitespace"), column_action("name", "trim_whitespace"),
            column_action("qty", "flag_only"), column_action("price", "flag_only"),
            column_action("day", "parse_datetime")]


# --- placeholder candidates ---------------------------------------------------------


def _sales(customers: list[str | None], prices: list[str] | None = None) -> pd.DataFrame:
    n = len(customers)
    return pd.DataFrame({"Day": ["2026-08-03"] * n, "Qty": "1",
                         "Price": prices or ["10"] * n, "Cust": customers})


def test_a_placeholder_word_is_a_candidate_at_any_share() -> None:
    customers = [f"C{i}" for i in range(99)] + [" Walk-In "]

    found = placeholder_candidates(_sales(customers), MAPPING)

    assert [(c.value, c.lines, c.why) for c in found] == [(" Walk-In ", 1, "word")]


def test_a_value_on_a_tenth_of_the_lines_is_a_candidate() -> None:
    # Store's lines are cheap (5 against 10): 10% of the lines, 5.3% of the
    # revenue - the line share alone decides (mutation check K10).
    # 30 customers of 3 lines (Store's 10 lines are 3.3 times the next one:
    # under the ratio of review cycle 2).
    customers = [f"C{i}" for i in range(30) for _ in range(3)] + ["Store"] * 10

    found = placeholder_candidates(_sales(customers, ["10"] * 90 + ["5"] * 10), MAPPING)

    assert [(c.value, c.lines, c.lines_pct, c.why) for c in found] == [("Store", 10, 10.0, "share")]
    assert PLACEHOLDER_SHARE == 0.10


def test_a_value_just_under_a_tenth_is_not() -> None:
    customers = [f"C{i}" for i in range(30) for _ in range(3)] + ["C30"] + ["Store"] * 9

    assert placeholder_candidates(_sales(customers), MAPPING) == []


def test_a_value_with_a_tenth_of_the_sale_revenue_is_a_candidate() -> None:
    customers = [f"C{i}" for i in range(19)] + ["Office"]
    prices = ["10"] * 19 + ["30"]  # Office: 30 of 220 = 13.6% of the revenue, 5% of the lines

    found = placeholder_candidates(_sales(customers, prices), MAPPING)

    assert [(c.value, c.why) for c in found] == [("Office", "share")]
    assert found[0].revenue_pct == pytest.approx(30 / 220 * 100)


def test_blank_lines_count_in_the_share_but_stock_in_lines_do_not() -> None:
    df = _sales([f"C{i}" for i in range(5)] + [None] * 5 + ["Warehouse"] * 3).assign(
        Type=["out"] * 10 + ["in"] * 3)

    found = placeholder_candidates(df, {**MAPPING, "Type": "transaction_type"})

    # 10 counted lines: each C is 1 of 10 (10%); Warehouse's 3 lines are stock-in
    # (counted, they would be 3 of 13 = 23%).
    assert {c.value for c in found} == {f"C{i}" for i in range(5)}
    assert all(c.lines_pct == pytest.approx(10.0) for c in found)


def test_no_customer_column_no_candidates() -> None:
    no_customer = {k: v for k, v in MAPPING.items() if v != "customer"}

    assert placeholder_candidates(_sales(["Guest"]), no_customer) == []


def test_the_schema_step_writes_the_candidates(tmp_path: Path) -> None:
    csv = b"Day,Qty,Price,Cust\n2026-08-03,1,10,Guest\n2026-08-03,1,10,Ann\n" + b"".join(
        f"2026-08-04,1,10,C{i}\n".encode() for i in range(20))
    run_id = profiled_run(tmp_path, csv)

    schema = run(tmp_path, run_id, FakeMessages(answer(
        [column(n, MAPPING[n]) for n in MAPPING], dataset_issues=[])))

    assert [(c.value, c.why) for c in schema.customer_placeholders] == [("Guest", "word")]


def test_contracts_carry_the_placeholders_and_are_2_2() -> None:
    confirmed = OrderConfirmations(customer_placeholders=["Guest"])
    plan = CleaningPlanContract(schema_version="2.2", generated_at=NOW, source="manual",
                                dataset_actions=[], column_actions=[], confirmations=confirmed)

    assert CleaningPlanContract.model_validate_json(plan.model_dump_json()).confirmations == confirmed
    assert OrderConfirmations().customer_placeholders == []
    # None: not measured (review cycle 1 F4; [] in the first RED set).
    assert SchemaInferenceContract.model_fields["customer_placeholders"].default is None
    assert CustomerPlaceholder(value="0", lines=3, lines_pct=12.5, revenue_pct=None, why="word").value == "0"
    assert (ai_schema.SCHEMA_VERSION, ai_plan.SCHEMA_VERSION, cleaning.SCHEMA_VERSION) == (
        "2.2", "2.2", "2.2")


def test_the_revenue_share_is_of_sale_revenue_not_net() -> None:
    """Mutation check K12: a refund does not shrink a value's share - Office
    sold 30 of 220 (13.6%) and refunded it later; net it would be 0."""
    customers = [f"C{i}" for i in range(19)] + ["Office", "Office"]
    df = _sales(customers, ["10"] * 19 + ["30", "30"]).assign(Qty=["1"] * 20 + ["-1"])

    found = placeholder_candidates(df, MAPPING)

    assert [c.value for c in found] == ["Office"]


def test_the_schema_step_writes_the_per_receipt_verdict(tmp_path: Path) -> None:
    """Mutation checks K18, K19: Review's receipt question reads it."""
    header = "Inv,Day,Qty,Price,Cust"
    batches = "\n".join([header] + [f"Z{d},2026-08-0{d},1,10," for d in range(1, 6)]).encode()
    receipts = "\n".join([header] + [f"R{d},2026-08-0{d},1,10,C{d}" for d in range(1, 6)]).encode()
    mapped = {"Inv": "order_id", "Day": "transaction_date", "Qty": "quantity", "Price": "unit_price",
              "Cust": "customer"}
    verdicts = []
    for content in (batches, receipts):
        root = tmp_path / str(len(verdicts))
        run_id = profiled_run(root, content)
        schema = run(root, run_id, FakeMessages(answer(
            [column(n, mapped[n]) for n in mapped], dataset_issues=[])))
        verdicts.append(schema.order_id_date_only)

    assert verdicts == [True, False]


# --- doubt-review cycle 1 ------------------------------------------------------------------


@pytest.mark.parametrize("spelling", ["0.0", "0000", "-", "Guest Customer", "Cash Sale", "Walk-In Client",
                                      "Retail Customer", "WALKIN CUSTOMER", "Unknown customer",
                                      "Customer"])
def test_common_placeholder_spellings_are_asked_at_any_share(spelling: str) -> None:
    """Review cycle 1 F6 (blocking: a placeholder at 7% of the lines became the
    top customer, 13 times the next one): words match inside a value, and any
    number equal to zero, or a value with no letter or digit, is a word."""
    customers = [f"C{i % 40}" for i in range(93)] + [spelling] * 7

    found = placeholder_candidates(_sales(customers), MAPPING)

    assert [(c.value, c.why) for c in found] == [(spelling, "word")]


def test_an_ordinary_name_is_not_a_word() -> None:
    customers = [f"C{i}" for i in range(40)] + ["Ann Smith", "10023", "Bob's Deli"]

    assert placeholder_candidates(_sales(customers), MAPPING) == []


def test_one_customer_on_every_line_is_at_most_100_percent() -> None:
    """Review cycle 1 F2: the two sums added in a different order gave
    100.00000000000003% and the schema step crashed."""
    import random

    rng = random.Random(0)
    prices = [f"{rng.uniform(1, 50):.2f}" for _ in range(200)]

    found = placeholder_candidates(_sales(["Guest"] * 200, prices), MAPPING)

    assert [(c.lines_pct, c.revenue_pct) for c in found] == [(100.0, 100.0)]


def test_a_raw_file_that_does_not_parse_measured_no_candidates(tmp_path: Path) -> None:
    """Review cycle 1 F4: "not measured" is None, not "none found"."""
    csv = b"Day,Qty,Price,Cust\n2026-08-03,1,$10,Guest\n2026-08-03,1,$10,Ann\n"
    run_id = profiled_run(tmp_path, csv)

    schema = run(tmp_path, run_id, FakeMessages(answer(
        [column(n, MAPPING[n]) for n in MAPPING], dataset_issues=[])))

    assert schema.customer_placeholders is None


def test_a_raw_file_missing_a_required_mapping_measured_no_candidates(tmp_path: Path) -> None:
    """Mutation check L8: the AI left Price unmapped, so the raw file cannot
    be parsed - not measured, and Review reads the profile."""
    csv = "\n".join(["Day,Qty,Price,Cust", "2026-08-03,1,10,Guest", "2026-08-03,1,10,Ann"]).encode()
    run_id = profiled_run(tmp_path, csv)
    mapping = {**MAPPING, "Price": "ignore"}

    schema = run(tmp_path, run_id, FakeMessages(answer(
        [column(n, mapping[n]) for n in mapping], dataset_issues=[])))

    assert schema.customer_placeholders is None
