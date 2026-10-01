"""2E-u4 (Thach, 2026-10-02; 2E-u F4, before deploy), stage 1, written before
the code (method: C:/Users/Happy/2E-u4-method.txt):

- the AI never proposes exact-duplicate removal: the prompt says so, its
  legal dataset actions do not list it, and ai_plan strips it from the AI's
  answer, as an action and as an alternative;
- a user who adds it in Review is shown what it removes: the whole-file line
  summary's `duplicates_removed`, the lines and their revenue."""

from pathlib import Path

import pandas as pd
import pytest

from stages.ingest.line_summary import line_summary
from stages.ingest.profiling import read_csv_text
from stages.ingest.transform_catalog import ai_legal_dataset_actions, legal_dataset_actions
from tests.ai_fakes import FakeMessages
from tests.stages.ingest.cleaning_fixtures import column_action, dataset_action, make_plan
from tests.stages.ingest.plan_answers import dataset_action as answer_action
from tests.stages.ingest.plan_answers import (SCHEMA_COLUMNS, good_actions, make_schema, plan_answer, planned_run,
                                              run_plan, schema_column)


def test_the_ai_is_never_offered_the_removal() -> None:
    assert ai_legal_dataset_actions() == ["flag_duplicate_keys"]
    # The user's plan may still hold it.
    assert legal_dataset_actions() == ["remove_exact_duplicates", "flag_duplicate_keys"]


def test_the_prompt_says_never() -> None:
    text = " ".join(Path("prompts/cleaning_plan.md").read_text(encoding="utf-8").split())
    assert "Never propose remove_exact_duplicates, as an action or as an alternative" in text
    assert "remove_exact_duplicates when the dataset issues report duplicate_rows" not in text


def test_an_ai_answer_proposing_it_is_stripped(tmp_path: Path) -> None:
    run_id = planned_run(tmp_path)
    returned = run_plan(tmp_path, run_id, FakeMessages(plan_answer(
        dataset_actions=[answer_action("remove_exact_duplicates")])))
    assert returned.dataset_actions == []


def test_it_is_stripped_as_an_alternative_too(tmp_path: Path) -> None:
    # A file with a date, so it has a business key (sku, day) to flag.
    csv = b"sku,name,qty,price,day\nA1,Mug,3,9.99,2024-01-05\nA1,Mug,3,9.99,2024-01-05\n"
    columns = [*SCHEMA_COLUMNS, schema_column("day", "datetime", "transaction_date")]
    run_id = planned_run(tmp_path, csv, make_schema(columns))
    keyed = answer_action("flag_duplicate_keys", params={"keys": ["sku", "day"]},
                          alternatives=["remove_exact_duplicates"])
    day = {"source_name": "day", "action": "parse_datetime", "params": {}, "rationale": "1 date column",
           "alternatives": []}
    returned = run_plan(tmp_path, run_id, FakeMessages(plan_answer(
        column_actions=[*good_actions(), day], dataset_actions=[keyed])))
    assert [(a.action, a.alternatives) for a in returned.dataset_actions] == [("flag_duplicate_keys", [])]


# Mug sold twice the same way (a genuine repeat or a repeated export line -
# the data cannot tell), Cup once: 3 lines, 2 x 10.00 + 4.00 = 24.00.
REPEATED = (b"sku,name,qty,price,day\n"
            b"A1,Mug,1,10.00,2024-01-05\n"
            b"A1,Mug,1,10.00,2024-01-05\n"
            b"B2,Cup,2,2.00,2024-01-06\n")


def _actions():
    return [column_action("sku"), column_action("name"), column_action("qty"), column_action("price"),
            column_action("day", "parse_datetime")]


def _frame(csv: bytes) -> pd.DataFrame:
    return read_csv_text(csv).frame


def test_the_summary_shows_the_lines_and_revenue_the_removal_takes() -> None:
    plan = make_plan(_actions(), [dataset_action("remove_exact_duplicates")])
    summary = line_summary(_frame(REPEATED), plan).summary
    assert summary is not None and summary.duplicates_removed is not None
    assert (summary.duplicates_removed.lines, summary.duplicates_removed.revenue) == (1, 10.0)
    assert summary.identity.net_revenue == pytest.approx(14.0)  # what stays


def test_no_removal_in_the_plan_shows_none() -> None:
    summary = line_summary(_frame(REPEATED), make_plan(_actions())).summary
    assert summary is not None and summary.duplicates_removed is None
    assert summary.identity.net_revenue == pytest.approx(24.0)


def test_a_removal_with_nothing_to_remove_shows_zero() -> None:
    plan = make_plan(_actions(), [dataset_action("remove_exact_duplicates")])
    once = REPEATED.replace(b"A1,Mug,1,10.00,2024-01-05\nB2", b"B2")
    summary = line_summary(_frame(once), plan).summary
    assert summary is not None and summary.duplicates_removed is not None
    assert (summary.duplicates_removed.lines, summary.duplicates_removed.revenue) == (0, 0.0)
