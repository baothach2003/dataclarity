"""Session 2E-e2 (Thach), stage 1, written before the change.

- The schema step measures, on the raw file and the AI's mapping, how many
  lines the customer fill would give their receipt's customer
  (`receipt_fill_lines`): Review asks its question only when that happens.
  Stage 1's own measure, never the AI's.
- The AI never answers for the user: its proposal carries no confirmation.
- Execution records the answers that ran in cleaning_report.json, where
  stages 2 and 3 read them.
- Every stage 1 contract gains an optional field: 2.1 (a minor bump).
"""

import json
from pathlib import Path

from contracts.cleaning import CleaningPlanContract, OrderConfirmations
from stages.ingest import ai_plan, ai_schema, cleaning
from stages.ingest.cleaning import execute_run
from tests.ai_fakes import FakeMessages, FakeResponse
from tests.stages.ingest.cleaning_fixtures import NOW, make_plan, raw_run
from tests.stages.ingest.plan_answers import good_plan, planned_run, run_plan
from tests.stages.ingest.schema_answers import answer, column, profiled_run, run

HEADER_STYLE = (b"Inv,Day,Qty,Price,Cust\n"
                b"R1,2026-08-03,1,10,Ann\nR1,2026-08-03,1,40,\nR1,2026-08-03,2,5,\n"
                b"R2,2026-08-04,1,30,Bob\n")
MAPPED = {"Inv": "order_id", "Day": "transaction_date", "Qty": "quantity",
          "Price": "unit_price", "Cust": "customer"}


def _schema_answer(mapping: dict[str, str]):
    return answer([column(name, mapping.get(name, "ignore")) for name in MAPPED], dataset_issues=[])


def test_the_schema_step_measures_the_fill_on_the_raw_file(tmp_path: Path) -> None:
    run_id = profiled_run(tmp_path, HEADER_STYLE)

    schema = run(tmp_path, run_id, FakeMessages(_schema_answer(MAPPED)))

    assert schema.receipt_fill_lines == 2


def test_no_customer_mapped_means_no_fill_to_ask_about(tmp_path: Path) -> None:
    run_id = profiled_run(tmp_path, HEADER_STYLE)
    mapping = {k: v for k, v in MAPPED.items() if v != "customer"}

    schema = run(tmp_path, run_id, FakeMessages(_schema_answer(mapping)))

    assert schema.receipt_fill_lines == 0


def test_the_ai_proposal_answers_nothing_for_the_user(tmp_path: Path) -> None:
    run_id = planned_run(tmp_path)
    body = json.loads(good_plan().text)
    body["confirmations"] = {"order_id_is_receipt": True, "customer_on_first_line_only": True}

    proposal = run_plan(tmp_path, run_id, FakeMessages(FakeResponse(json.dumps(body))))

    assert proposal.confirmations == OrderConfirmations()


def test_execution_records_the_answers_that_ran(tmp_path: Path) -> None:
    run_id = raw_run(tmp_path)
    answers = OrderConfirmations(order_id_is_receipt=False, customer_on_first_line_only=True)
    plan = make_plan().model_copy(update={"confirmations": answers})

    report = execute_run(tmp_path, run_id, plan, now=NOW)

    assert report.confirmations == answers
    final = CleaningPlanContract.model_validate_json(
        (tmp_path / run_id / "plan_final.json").read_text(encoding="utf-8"))
    assert final.confirmations == answers


def test_stage_1_contracts_are_2_1_or_later() -> None:
    # 2.1 in 2E-e2; 2.2 since 2E-k; 2.3 since 2E-d2 (test_2ed2_stage1.py).
    assert (ai_schema.SCHEMA_VERSION, ai_plan.SCHEMA_VERSION, cleaning.SCHEMA_VERSION) == (
        "2.3", "2.3", "2.3")
