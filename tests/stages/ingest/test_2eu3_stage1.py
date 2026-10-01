"""2E-u3 (Thach, 2026-10-02; 2E-u F3), stage 1, written before the code: an
unanswered walk-in placeholder candidate is marked "suggested, not
confirmed", like Q17 (method: C:/Users/Happy/2E-u3-method.txt).

- the plan carries the values the user answered "a real customer"
  (`confirmations.customer_not_placeholders`, 4.2), so unanswered can be told
  from No;
- execution measures the candidates on the raw file with the plan's own
  mapping and records those neither confirmed nor answered No
  (cleaning_report.json `unconfirmed_placeholders`). Nothing else changes."""

from pathlib import Path

import pytest

from contracts.cleaning import CleaningReportContract, ColumnAction, OrderConfirmations
from stages.ingest.cleaning import SCHEMA_VERSION, execute_run
from tests.stages.ingest.cleaning_fixtures import NOW, column_action, make_plan, raw_run

# Twenty real customers, one line each (under 10% of the lines, and no one
# dominant); "Guest" is a placeholder word, "-" has no letter or digit: both
# asked, whatever their share.
CSV = (b"sku,name,qty,price,day,cust\n"
       + b"".join(b"A%d,Mug,1,5.00,2024-01-%02d,Customer %d\n" % (i, 1 + i, i) for i in range(20))
       + b"B1,Cup,1,5.00,2024-01-06,Guest\nB2,Cup,1,5.00,2024-01-07,guest\nB3,Cup,1,5.00,2024-01-08,-\n")


def _plan(customer: str = "customer", **answers: list[str]):
    cust = ColumnAction.model_validate({
        "source_name": "cust", "semantic_type": "text", "canonical_field": customer, "action": "flag_only",
        "params": {}, "rationale": "", "alternatives": [], "edited_by_user": True})
    actions = [column_action("sku"), column_action("name"), column_action("qty"), column_action("price"),
               column_action("day", "parse_datetime"), cust]
    return make_plan(actions).model_copy(update={"confirmations": OrderConfirmations(**answers)})


def test_the_no_answers_are_part_of_the_plan() -> None:
    answers = OrderConfirmations(customer_not_placeholders=["Ann"])
    assert answers.customer_not_placeholders == ["Ann"]
    assert OrderConfirmations().customer_not_placeholders == []
    assert SCHEMA_VERSION == "4.2"


def test_every_unanswered_candidate_is_recorded_as_written_most_often(tmp_path: Path) -> None:
    report = execute_run(tmp_path, raw_run(tmp_path, CSV), _plan(), now=NOW)
    # "Guest" and "guest" are one customer identity; the first spelling is kept.
    assert report.unconfirmed_placeholders == ["Guest", "-"]


@pytest.mark.parametrize("answers,left", [
    ({"customer_placeholders": ["guest"]}, ["-"]),          # Yes, by identity
    ({"customer_not_placeholders": ["GUEST"]}, ["-"]),      # No, by identity
    ({"customer_placeholders": ["-"], "customer_not_placeholders": ["Guest"]}, []),
])
def test_a_value_answered_either_way_is_not_recorded(tmp_path: Path, answers: dict, left: list[str]) -> None:
    report = execute_run(tmp_path, raw_run(tmp_path, CSV), _plan(**answers), now=NOW)
    assert report.unconfirmed_placeholders == left


def test_no_customer_column_records_nothing(tmp_path: Path) -> None:
    report = execute_run(tmp_path, raw_run(tmp_path, CSV), _plan(customer="ignore"), now=NOW)
    assert report.unconfirmed_placeholders == []


def test_the_report_reads_back_and_an_earlier_one_reads_as_none(tmp_path: Path) -> None:
    run_id = raw_run(tmp_path, CSV)
    report = execute_run(tmp_path, run_id, _plan(), now=NOW)
    on_disk = CleaningReportContract.model_validate_json(
        (tmp_path / run_id / "cleaning_report.json").read_text(encoding="utf-8"))
    assert on_disk.unconfirmed_placeholders == report.unconfirmed_placeholders
    older = on_disk.model_dump(mode="json")
    older["schema_version"] = "4.1"
    del older["unconfirmed_placeholders"]
    del older["confirmations"]["customer_not_placeholders"]
    assert CleaningReportContract.model_validate(older).unconfirmed_placeholders == []


def test_the_cleaned_file_is_the_same_whatever_is_recorded(tmp_path: Path) -> None:
    # The mark changes no figure (CLAUDE.md 3.3a): only Yes does.
    first, second = raw_run(tmp_path, CSV), raw_run(tmp_path, CSV)
    execute_run(tmp_path, first, _plan(), now=NOW)
    execute_run(tmp_path, second, _plan(customer_not_placeholders=["Guest", "-"]), now=NOW)
    assert (tmp_path / first / "cleaned.csv").read_bytes() == (tmp_path / second / "cleaned.csv").read_bytes()
