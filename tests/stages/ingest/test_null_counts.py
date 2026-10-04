"""A null issue count where the AI has no figure to copy (Thach, 2026-10-05, on the seventeenth report),
written before the code. The real-AI smoke test refused 7 of 7 first schema answers on one cause: the
prompt says "never invent counts" while the answer schema demanded an integer where the profile holds
none - a contradiction in our own design, not a model fault. The fakes never returned null, so no test
met it: the real Kaggle answers are kept here as fixtures (real_answers/, public data), with fakes in the
shapes the real model produced. A count may be null for the codes stage 1 recounts with pandas (1E: their
count is overwritten anyway) and for dataset-level issues the profile gives no count for; a code the
profile counts still requires the profile's figure. No stored count is ever null: every null is filled by
pandas or dropped as the wrong level before schema_inference.json is written, so Review, the plan step and
the cleaning report never see one."""

import json
from pathlib import Path

import pytest

from contracts.profile import ProfileContract, SchemaInferenceContract
from shared.ai_client import AIClient
from stages.ingest.ai_input import build_plan_variables
from stages.ingest.ai_schema import SchemaInferenceAnswer, check_answer
from tests.ai_fakes import FakeMessages
from tests.stages.ingest.schema_answers import (
    CANONICAL,
    COLUMNS,
    answer,
    column,
    profiled_run,
    run,
)

REAL = Path(__file__).parent / "real_answers"
KAGGLE_PROFILE = ProfileContract.model_validate_json((REAL / "kaggle_profile.json").read_text(encoding="utf-8"))
FIRST_ANSWERS = sorted(REAL.glob("kaggle_first_answer_*.txt"))
PASSED_ANSWERS = sorted(REAL.glob("kaggle_passed_answer_*.txt"))


def test_the_fixtures_are_the_six_real_first_answers() -> None:
    # 5 measurement calls and the Kaggle flow's first call (the seventeenth run); each carries the shape
    # that was refused: a dataset-level issue with "count": null. (That run's passed retries were not
    # kept; the passed answers below come from the eighteenth run's confirmation.) No fixture quotes a
    # cell of the file: two details quoting "Discount Applied"'s 'True'/'False' were emptied.
    assert len(FIRST_ANSWERS) == 6
    for path in FIRST_ANSWERS:
        body = json.loads(path.read_text(encoding="utf-8").strip().removeprefix("```json").removesuffix("```"))
        assert any(issue["count"] is None for issue in body["dataset_issues"]), path.name


@pytest.mark.parametrize("path", FIRST_ANSWERS, ids=lambda p: p.stem)
def test_each_real_first_answer_is_accepted(path: Path) -> None:
    # Through the client's own check (strict parse, then check_answer), exactly as the call is made.
    accepted = AIClient._parse(path.read_text(encoding="utf-8"), SchemaInferenceAnswer,
                               lambda value: check_answer(value, KAGGLE_PROFILE))

    assert [c.source_name for c in accepted.columns] == [c.name for c in KAGGLE_PROFILE.columns]


def test_the_fixtures_hold_the_three_real_passed_answers() -> None:
    # The confirmation smoke test (the eighteenth run, on 7fe6e7d): three Kaggle schema calls, each
    # accepted first time with no retry.
    assert len(PASSED_ANSWERS) == 3


@pytest.mark.parametrize("path", PASSED_ANSWERS, ids=lambda p: p.stem)
def test_each_real_passed_answer_is_accepted_by_todays_check(path: Path) -> None:
    # A real, valid answer the model gave: a future check that refused it would refuse the real model's
    # valid output - every run's retry spent again, as the seventeenth run found - and fails the build here.
    accepted = AIClient._parse(path.read_text(encoding="utf-8"), SchemaInferenceAnswer,
                               lambda value: check_answer(value, KAGGLE_PROFILE))

    assert [c.source_name for c in accepted.columns] == [c.name for c in KAGGLE_PROFILE.columns]
    assert [(i.code, i.count) for i in accepted.dataset_issues] == [("duplicate_rows", 0)]


# --- what stays required ---------------------------------------------------------------------------


def _rejection(messages: FakeMessages) -> str:
    return messages.calls[1]["messages"][0]["content"].split("rejected for these reasons:", 1)[1]


def test_a_code_the_profile_counts_still_requires_its_figure(tmp_path: Path) -> None:
    run_id = profiled_run(tmp_path)
    columns = [column(n, CANONICAL[n]) for n in COLUMNS]
    columns[1]["issues"] = [{"code": "missing_values", "count": None, "pct": None, "examples": []}]
    messages = FakeMessages(answer(columns), answer([column(n, CANONICAL[n]) for n in COLUMNS]))

    run(tmp_path, run_id, messages)

    assert "name: missing_values count must be the profile's figure (1), not null" in _rejection(messages)
    assert "None" not in _rejection(messages)


ALL_NULL = b"sku,name,note\nA1,Mug,\nB2,Cup,\n"


def test_an_all_null_column_still_requires_its_figure(tmp_path: Path) -> None:
    run_id = profiled_run(tmp_path, ALL_NULL)
    columns = [column("sku", "sku"), column("name", "product_name"),
               column("note", "note", issues=[{"code": "all_null_column", "count": None, "pct": None,
                                                "examples": []}])]
    messages = FakeMessages(answer(columns, dataset_issues=[]),
                            answer([column("sku", "sku"), column("name", "product_name"), column("note", "note")],
                                   dataset_issues=[]))

    run(tmp_path, run_id, messages)

    assert "note: all_null_column count must be the profile's figure (2), not null" in _rejection(messages)


def test_every_code_the_profile_counts_refuses_a_null() -> None:
    # Tied to issue_counts.PROFILED_CODES (review, finding 1): a code added there and forgotten in
    # check_answer would let a null through to the contract's conversion - an error after a paid call.
    from contracts.profile import ProfileContract
    from stages.ingest.issue_counts import PROFILED_CODES
    from stages.ingest.profiling import profile_csv
    from tests.stages.ingest.schema_answers import NOW

    profile: ProfileContract = profile_csv(b"sku,note\nA1,\nA1,\n", now=NOW)  # note all null; 1 duplicate row
    for code in sorted(PROFILED_CODES):
        issue = {"code": code, "count": None, "pct": None, "examples": []}
        dataset = code == "duplicate_rows"
        body = {"domain_confidence": 0.9, "domain_reasoning": "r",
                "dataset_issues": [{"code": code, "count": None, "severity": "low", "detail": "x"}] if dataset else [],
                "columns": [column("sku", "sku"), column("note", "note", issues=[] if dataset else [issue])]}
        with pytest.raises(ValueError, match="not null"):
            check_answer(SchemaInferenceAnswer.model_validate(body), profile)


def test_the_profiles_duplicate_rows_still_requires_its_figure(tmp_path: Path) -> None:
    run_id = profiled_run(tmp_path)
    nulled = answer([column(n, CANONICAL[n]) for n in COLUMNS],
                    dataset_issues=[{"code": "duplicate_rows", "count": None, "severity": "low", "detail": "x"}])
    messages = FakeMessages(nulled, answer([column(n, CANONICAL[n]) for n in COLUMNS]))

    run(tmp_path, run_id, messages)

    assert "duplicate_rows count must be the profile's figure (1), not null" in _rejection(messages)


# --- the shapes the real model produced, end to end --------------------------------------------------


def kaggle_shape(columns: list[dict]) -> dict:
    """Kaggle's: dataset-level issues the profile gives no count for, null (missing values across
    columns; a type). The test file also has one duplicate row, reported with the profile's figure (the
    real Kaggle answers had none: its profile counts 0)."""
    return {"columns": columns, "dataset_issues": [
        {"code": "duplicate_rows", "count": 1, "severity": "low", "detail": "row 3 repeats row 1"},
        {"code": "missing_values", "count": None, "severity": "medium", "detail": "several columns have gaps"},
        {"code": "mixed_types", "count": None, "severity": "low", "detail": "a flag stored as text"}]}


def test_null_counts_in_the_real_shapes_cost_no_retry_and_never_reach_the_file(tmp_path: Path) -> None:
    """Online Retail II's shape on the test file: computed codes' counts null on qty (3, -1, 3, 5) -
    negative_values: pandas counts B2's -1, so 1; outliers_iqr: q1 2.0, q3 3.5, IQR 1.5, the lower fence
    2.0 - 2.25 = -0.25, so -1 again, 1 - and Kaggle's dataset-level nulls (dropped: no dataset-level count
    exists for them). One call, no retry; every count written is an integer."""
    run_id = profiled_run(tmp_path)
    columns = [column(n, CANONICAL[n]) for n in COLUMNS]
    columns[2]["issues"] = [{"code": "negative_values", "count": None, "pct": None, "examples": ["row 2"]},
                            {"code": "outliers_iqr", "count": None, "pct": None, "examples": []}]
    messages = FakeMessages(answer(**kaggle_shape(columns)))

    contract = run(tmp_path, run_id, messages)

    assert len(messages.calls) == 1  # accepted first time: no retry spent
    qty = next(c for c in contract.columns if c.source_name == "qty")
    assert [(i.code, i.count) for i in qty.issues] == [("negative_values", 1), ("outliers_iqr", 1)]
    assert [(i.code, i.count) for i in contract.dataset_issues] == [("duplicate_rows", 1)]
    from tests.stages.ingest.schema_answers import written

    stored = written(tmp_path, run_id).read_text(encoding="utf-8")
    assert '"count": null' not in stored and '"count": 1' in stored


DATED = (b"Invoice,StockCode,Quantity,InvoiceDate,Price\n"
         b"536365,85123A,6,2010-12-01 08:26,2.55\n"
         b"536366,85123A,2,2010-12-01 08:26,2.55\n"
         b"536367,22728,24,2010-12-01 09:41,3.75\n")
DATED_FIELDS = {"Invoice": "ignore", "StockCode": "sku", "Quantity": "quantity", "InvoiceDate": "transaction_date",
                "Price": "unit_price"}


def test_a_null_filled_by_pandas_is_not_counted_as_replaced() -> None:
    from contracts.profile import ColumnInference
    from stages.ingest.ai_schema import AnswerColumn
    from stages.ingest.issue_recount import recount_issues
    from stages.ingest.profiling import read_csv_text
    from tests.stages.ingest.schema_answers import CSV

    qty = AnswerColumn.model_validate(column("qty", "quantity", issues=[
        {"code": "negative_values", "count": None, "pct": None, "examples": []}]))
    others = [ColumnInference.model_validate(column(n, CANONICAL[n])) for n in ("sku", "name", "price")]
    columns, _, stats = recount_issues([others[0], others[1], qty, others[2]], [], read_csv_text(CSV).frame,
                                       order_check=None)

    assert [(i.code, i.count) for i in columns[2].issues] == [("negative_values", 1)]
    assert (stats.replaced, stats.dropped) == (0, 0)


def test_a_null_business_key_count_is_pandas_count(tmp_path: Path) -> None:
    # 85123A at 2010-12-01 08:26 twice: 2 rows share their StockCode, InvoiceDate key (Invoice ignored).
    run_id = profiled_run(tmp_path, DATED)
    columns = [column(name, field) for name, field in DATED_FIELDS.items()]
    messages = FakeMessages(answer(columns, dataset_issues=[
        {"code": "duplicate_business_key", "count": None, "severity": "medium", "detail": "keys repeat"}]))

    contract = run(tmp_path, run_id, messages)

    assert len(messages.calls) == 1
    assert [(i.code, i.count) for i in contract.dataset_issues] == [("duplicate_business_key", 2)]


def test_the_plan_step_never_reads_a_null_count(tmp_path: Path) -> None:
    from stages.ingest.profiling import profile_csv
    from tests.stages.ingest.schema_answers import CSV, NOW

    run_id = profiled_run(tmp_path)
    columns = [column(n, CANONICAL[n]) for n in COLUMNS]
    columns[2]["issues"] = [{"code": "negative_values", "count": None, "pct": None, "examples": []}]
    contract = run(tmp_path, run_id, FakeMessages(answer(**kaggle_shape(columns))))

    sent = build_plan_variables(profile_csv(CSV, now=NOW), contract)["schema_inference_json"]
    assert '"count": 1' in sent and '"count": null' not in sent and "None" not in sent


def test_the_stored_contract_still_refuses_a_null_count() -> None:
    # The guarantee for Review, the plan step and the cleaning report: schema_inference.json cannot hold one.
    base = {"schema_version": "4.2", "generated_at": "2026-10-05T00:00:00Z", "model_used": "m",
            "domain_confidence": 0.9, "domain_reasoning": "r", "columns": [],
            "receipt_fill_lines": 0, "customer_placeholders": [], "order_id_date_only": False,
            "non_product_candidates": []}
    with pytest.raises(ValueError):
        SchemaInferenceContract.model_validate(base | {"dataset_issues": [
            {"code": "duplicate_business_key", "count": None, "severity": "low", "detail": "x"}]})


def test_the_prompt_says_the_profiles_figure_or_null() -> None:
    prompt = " ".join((Path(__file__).parents[3] / "prompts" / "schema_inference.md").read_text(encoding="utf-8").split())
    assert ('Give "count" as the profile\'s figure, or null when it holds none: the column\'s null_count for '
            '"missing_values" and "all_null_column", the dataset\'s duplicate_rows for "duplicate_rows". For every '
            'other code the profile holds no count: use null. Never invent a count.') in prompt
    assert '"count": <int|null>' in prompt
    assert '"count": <int>' not in prompt


@pytest.mark.parametrize("where", ["column", "dataset"])
def test_a_null_the_recount_left_would_be_refused_never_written(tmp_path: Path, monkeypatch, where: str) -> None:
    # The guard behind "no stored count is ever null": were the recount ever to leave one (a code it
    # neither fills nor drops), the conversion into the contract's own models refuses it, and no file is
    # written - the run fails loudly instead of Review printing "None".
    import stages.ingest.ai_schema as ai_schema
    from tests.stages.ingest.schema_answers import written

    def leaves_a_null(columns, dataset_issues, frame, order_check):
        return columns, list(dataset_issues), None

    monkeypatch.setattr(ai_schema, "recount_issues", leaves_a_null)
    run_id = profiled_run(tmp_path)
    columns = [column(n, CANONICAL[n]) for n in COLUMNS]
    if where == "column":
        columns[2]["issues"] = [{"code": "negative_values", "count": None, "pct": None, "examples": []}]
        reply = answer(columns)
    else:
        reply = answer(columns, dataset_issues=[
            {"code": "duplicate_business_key", "count": None, "severity": "low", "detail": "keys repeat"}])

    with pytest.raises(ValueError):
        run(tmp_path, run_id, FakeMessages(reply))
    assert not written(tmp_path, run_id).exists()


def test_a_null_business_key_filled_by_pandas_is_not_counted_as_replaced() -> None:
    from contracts.profile import ColumnInference
    from stages.ingest.ai_schema import AnswerDatasetIssue
    from stages.ingest.issue_recount import recount_issues
    from stages.ingest.profiling import read_csv_text

    columns = [ColumnInference.model_validate(column(name, field)) for name, field in DATED_FIELDS.items()]
    nulled = AnswerDatasetIssue.model_validate(
        {"code": "duplicate_business_key", "count": None, "severity": "medium", "detail": "keys repeat"})
    _, dataset, stats = recount_issues(columns, [nulled], read_csv_text(DATED).frame, order_check=None)

    assert [(i.code, i.count) for i in dataset] == [("duplicate_business_key", 2)]
    assert (stats.replaced, stats.dropped) == (0, 0)
