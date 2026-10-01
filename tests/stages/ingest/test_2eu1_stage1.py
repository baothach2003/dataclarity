"""2E-u1 (Thach, 2026-10-02; 2E-u F1), stage 1, written before the wiring:

- profile.json measures, per text column, what its cells prove about their
  number format (Review reads it for the quantity and price columns);
- the plan carries the user's answer per source column
  (`confirmations.number_formats`);
- execution decides on the RAW file - the cells' proof, else the answer;
  unanswered and unproven the plan is refused, nothing written - and
  rewrites the readable cells of the quantity and price columns as plain
  numbers before the plan runs; cleaning_report.json records what ran.
- Stage 1 contracts: optional fields (profile 1.2, plan and report 4.1).
"""

from pathlib import Path

import pandas as pd
import pytest
from pydantic import ValidationError

from contracts.cleaning import CleaningReportContract, OrderConfirmations
from stages.analyze.assemble import analyze_run
from stages.ingest.cleaning import execute_run
from stages.ingest.number_apply import NumberQuestionUnanswered
from stages.ingest.profiling import SCHEMA_VERSION as PROFILE_VERSION
from stages.ingest.profiling import profile_csv
from tests.stages.ingest.cleaning_fixtures import NOW, column_action, make_plan, raw_run

# The fixture's five columns; prices written for people.
PEOPLE = (b'sku,name,qty,price,day\n'
          b'A1,Mug,3,"1,000.00",2024-01-05\n'
          b'B2,Cup,1,$12.50,2024-01-06\n'
          b'C3,Bowl,2,250,2024-01-07\n')
AMBIGUOUS = (b'sku,name,qty,price,day\n'
             b'A1,Mug,3,"1,000",2024-01-05\n'
             b'B2,Cup,1,"2,500",2024-01-06\n')


def _plan(answers: dict[str, str] | None = None):
    actions = [column_action("sku", "trim_whitespace"), column_action("name", "trim_whitespace"),
               column_action("qty", "flag_only"), column_action("price", "flag_only"),
               column_action("day", "parse_datetime")]
    return make_plan(actions).model_copy(
        update={"confirmations": OrderConfirmations(number_formats=answers or {})})


def _cleaned(root: Path, run_id: str) -> pd.DataFrame:
    return pd.read_csv(root / run_id / "cleaned.csv", dtype=str, keep_default_na=False)


def test_the_profile_measures_the_number_format_of_a_text_column() -> None:
    profile = profile_csv(PEOPLE, now=NOW)
    price = next(c for c in profile.columns if c.name == "price")
    qty = next(c for c in profile.columns if c.name == "qty")
    assert price.number_format is not None
    assert (price.number_format.decision, price.number_format.point, price.number_format.currency,
            price.number_format.point_example) == ("decimal_point", 2, 1, "1,000.00")
    assert qty.number_format is None  # plain numbers: nothing to decide
    assert PROFILE_VERSION == "1.2"


def test_an_unproven_column_is_measured_as_a_question() -> None:
    price = next(c for c in profile_csv(AMBIGUOUS, now=NOW).columns if c.name == "price")
    assert price.number_format is not None
    assert (price.number_format.decision, price.number_format.ambiguous_example) == ("ask", "1,000")


def test_the_answers_are_one_of_two_formats() -> None:
    assert OrderConfirmations(number_formats={"price": "decimal_comma"}).number_formats == {"price": "decimal_comma"}
    with pytest.raises(ValidationError):
        OrderConfirmations(number_formats={"price": "comma"})  # type: ignore[dict-item]  # the refusal under test


def test_execution_rewrites_the_prices_and_records_it(tmp_path: Path) -> None:
    run_id = raw_run(tmp_path, PEOPLE)
    report = execute_run(tmp_path, run_id, _plan(), now=NOW)
    assert _cleaned(tmp_path, run_id)["price"].tolist() == ["1000.00", "12.50", "250"]
    applied = report.number_formats["price"]
    assert (applied.format, applied.rewritten, applied.unreadable, applied.answered) == ("decimal_point", 2, 0, False)
    assert "qty" in report.number_formats and report.number_formats["qty"].rewritten == 0
    assert CleaningReportContract.model_validate_json(
        (tmp_path / run_id / "cleaning_report.json").read_text(encoding="utf-8")).number_formats == report.number_formats


def test_an_unanswered_question_refuses_the_plan_and_writes_nothing(tmp_path: Path) -> None:
    run_id = raw_run(tmp_path, AMBIGUOUS)
    with pytest.raises(NumberQuestionUnanswered):
        execute_run(tmp_path, run_id, _plan(), now=NOW)
    assert not (tmp_path / run_id / "cleaned.csv").exists()


def test_the_answer_reads_the_column(tmp_path: Path) -> None:
    run_id = raw_run(tmp_path, AMBIGUOUS)
    report = execute_run(tmp_path, run_id, _plan({"price": "decimal_comma"}), now=NOW)
    assert _cleaned(tmp_path, run_id)["price"].tolist() == ["1.000", "2.500"]
    assert report.number_formats["price"].answered is True


def test_stage_2_counts_the_revenue_the_people_wrote(tmp_path: Path) -> None:
    """DF-C4b's shape end to end: 3 x 1,000.00 + 1 x 12.50 + 2 x 250 = 3,512.50
    of January sales - before 2E-u1, "1,000.00" and "$12.50" were no number and
    only 500 counted."""
    csv = PEOPLE + b"D4,Plate,1,5.00,2024-02-29\n"
    run_id = raw_run(tmp_path, csv)
    execute_run(tmp_path, run_id, _plan(), now=NOW)
    metrics = analyze_run(tmp_path, run_id, NOW)
    january = next(m for m in metrics.core.revenue_by_month if m.period == "2024-01")
    assert january.revenue == pytest.approx(3512.5)


def test_the_preview_reads_the_numbers_as_execution_will(tmp_path: Path) -> None:
    from stages.ingest.preview import preview_run

    run_id = raw_run(tmp_path, PEOPLE)
    result = preview_run(tmp_path, run_id, _plan())
    first = next(row for row in result.rows if row.before.get("price") == "1,000.00")
    assert first.after["price"] == "1000.00"


def test_the_preview_shows_an_open_question_as_written(tmp_path: Path) -> None:
    from stages.ingest.preview import preview_run

    run_id = raw_run(tmp_path, AMBIGUOUS)
    prices = {row.after["price"] for row in preview_run(tmp_path, run_id, _plan()).rows}
    assert prices == {"1,000", "2,500"}


def test_the_lenient_reading_leaves_an_open_column_as_written() -> None:
    from stages.ingest.number_apply import apply_number_formats

    frame = pd.DataFrame({"price": ["1,000"]}, dtype=object)
    cleaned, applied = apply_number_formats(frame, {"price": "unit_price"}, {}, refuse=False)
    assert (cleaned["price"].tolist(), applied) == (["1,000"], {})


def test_a_column_of_currency_signs_alone_is_measured() -> None:
    # Nothing to ask, but Review says the signs are stripped: a measure with
    # no decision.
    profile = profile_csv(b"sku,price\nA,$10\nB,$20\n", now=NOW)
    price = next(c for c in profile.columns if c.name == "price")
    assert price.number_format is not None
    assert (price.number_format.decision, price.number_format.currency) == (None, 2)


THREE_DECIMALS = (b'sku,name,qty,price,day\n'
                  b'A1,Mug,3,1.000,2024-01-05\n'
                  b'B2,Cup,1,2.500,2024-01-06\n')


def test_a_column_pandas_reads_as_numbers_is_asked_when_it_reads_two_ways() -> None:
    """2E-u1 review 1, F1: "1.000" and "2.500" are numbers to pandas, so the
    profile measured nothing and Review asked nothing - while execution,
    rightly, refused to guess. Now the question reaches Review."""
    price = next(c for c in profile_csv(THREE_DECIMALS, now=NOW).columns if c.name == "price")
    assert price.number_format is not None and price.number_format.decision == "ask"
    # An ordinary price column pandas reads ("9.99" proves the point) shows nothing.
    plain = b"sku,name,qty,price,day\nA1,Mug,3,9.99,2024-01-05\nB2,Cup,1,4.50,2024-01-06\n"
    assert next(c for c in profile_csv(plain, now=NOW).columns if c.name == "price").number_format is None


def test_the_ai_never_sees_the_measure() -> None:
    # Its examples are cells beyond the bounded sample (review 1, F3; 2E-j's rule).
    from stages.ingest.ai_input import build_profile_json

    assert "number_format" not in build_profile_json(profile_csv(PEOPLE, now=NOW))


def test_a_column_proving_both_marks_says_so_when_it_asks(tmp_path: Path) -> None:
    run_id = raw_run(tmp_path, b'sku,name,qty,price,day\nA1,Mug,3,10.5,2024-01-05\nB2,Cup,1,"10,5",2024-01-06\n'
                               b'C3,Bowl,2,"1,000",2024-01-07\n')
    with pytest.raises(NumberQuestionUnanswered, match="its other numbers prove both marks"):
        execute_run(tmp_path, run_id, _plan(), now=NOW)


def _off_the_sample() -> pd.DataFrame:
    # 2,000 rows of "1,200" and ten "1,299.99" off the 500-row sample's grid.
    n = 2000
    grid = {i * (n - 1) // 499 for i in range(500)}
    prices = ["1,200"] * n
    for i in [i for i in range(1, n) if i not in grid][:10]:
        prices[i] = "1,299.99"
    return pd.DataFrame({"sku": [f"S{i}" for i in range(n)], "name": ["Lamp"] * n, "qty": ["1"] * n,
                         "price": prices, "day": ["2024-01-05"] * n}, dtype="str")


def test_the_preview_reads_by_the_whole_files_proof(tmp_path: Path) -> None:
    """Review 2, N3: the file proves the point, execution writes 1200, and the
    preview, deciding on the sample alone, showed "1,200" as written. The
    whole file's proof is profile.json's (review 3, R3-1: deciding on the
    whole column again cost 4 s a preview on a 36 MB file)."""
    from stages.ingest.preview import preview_run, select_sample

    frame = _off_the_sample()
    assert int((select_sample(frame)["price"] == "1,299.99").sum()) == 0  # the case: no proof in the sample
    run_id = raw_run(tmp_path, frame.to_csv(index=False).encode())
    result = preview_run(tmp_path, run_id, _plan())
    row = next(r for r in result.rows if r.before["price"] == "1,200")
    assert row.after is not None and row.after["price"] == "1200"


def test_the_preview_reads_no_more_than_its_sample(monkeypatch: pytest.MonkeyPatch) -> None:
    """Review 3, R3-1: the proof comes in decided; the preview reads its
    sample's cells only."""
    import stages.ingest.number_apply as number_apply
    from stages.ingest.preview import preview_frame

    read: list[int] = []
    real = number_apply.format_evidence
    monkeypatch.setattr(number_apply, "format_evidence", lambda values: read.append(len(values)) or real(values))
    result = preview_frame(_off_the_sample(), _plan(), proven={"price": "decimal_point"})
    assert read and max(read) <= 500
    row = next(r for r in result.rows if r.before["price"] == "1,200")
    assert row.after is not None and row.after["price"] == "1200"


def test_the_proven_formats_are_the_profiles_directions() -> None:
    from stages.ingest.number_format import proven_formats

    profile = profile_csv(PEOPLE + b'D4,Plate,1,"1,500",2024-01-08\n', now=NOW)
    assert proven_formats(profile) == {"price": "decimal_point"}
    assert proven_formats(profile_csv(AMBIGUOUS, now=NOW)) == {}  # a question is no proof
