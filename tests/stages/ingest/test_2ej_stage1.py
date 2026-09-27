"""Session 2E-j (Thach), stage 1, written before the change: the date order
is decided at stage 1.

- profile.json measures, per column, the cells written day-month-year or
  month-day-year and what they prove (a first number 13-31: day first; a
  second: month first). Review reads it for the mapped date column.
- Execution decides the order on the RAW file: the user's answer, else the
  proof. Both or neither prove and no answer: the plan is refused - either
  default fabricates dates. The order applied is recorded in
  cleaning_report.json (`date_order`) for stages 2 and 3; the answers stay
  as submitted.
- A parse step on the date column that reads some cell other than the
  decided order does is refused (it would write wrong dates to cleaned.csv).
  Readings are compared, not flags: a step that is right is never refused.
- Stage 1 contracts 3.1: optional fields.
"""

from pathlib import Path

import pandas as pd
import pytest
from pydantic import ValidationError

from contracts.cleaning import CleaningPlanContract, OrderConfirmations
from contracts.profile import DateOrderMeasure
from stages.ingest import ai_plan, ai_schema, cleaning
from stages.ingest.ai_input import build_profile_json
from stages.ingest.cleaning import execute_run
from stages.ingest.plan_validation import InvalidPlanError
from stages.ingest.profiling import SCHEMA_VERSION as PROFILE_VERSION
from stages.ingest.profiling import profile_csv
from stages.ingest.transforms import apply_action
from tests.stages.ingest.cleaning_fixtures import NOW, column_action, make_plan, raw_run

# The same five columns as cleaning_fixtures.RAW_CSV; every date is ambiguous.
AMBIGUOUS = (b"sku,name,qty,price,day\n"
             b"A1,Mug,3,9.99,05/01/2026\nB2,Cup,1,5.00,06/02/2026\nC3,Bowl,2,4.00,2026-03-07\n")


def _plan(day_params: dict | None = None, day_first: bool | None = None,
          day_action: str = "parse_datetime") -> CleaningPlanContract:
    actions = [column_action("sku", "trim_whitespace"), column_action("name", "trim_whitespace"),
               column_action("qty", "flag_only"), column_action("price", "flag_only"),
               column_action("day", day_action, day_params or {})]
    return make_plan(actions).model_copy(
        update={"confirmations": OrderConfirmations(dates_day_first=day_first)})


def _cleaned_days(root: Path, run_id: str) -> list[str]:
    cleaned = pd.read_csv(root / run_id / "cleaned.csv", dtype=str, keep_default_na=False)
    return cleaned["day"].tolist()


# --- the measure ---------------------------------------------------------------------


def test_the_profile_measures_the_order_per_column() -> None:
    profile = profile_csv(b"Day,Other,Qty\n13/01/2026,01/13/2026,1\n05/01/2026,x,2\n2026-01-05,y,1\n",
                          now=NOW)
    day, other, qty = profile.columns

    assert day.date_order is not None
    assert (day.date_order.shaped, day.date_order.day_first, day.date_order.month_first) == (2, 1, 0)
    assert (day.date_order.decision, day.date_order.day_first_example) == ("day_first", "13/01/2026")
    assert other.date_order is not None and other.date_order.decision == "month_first"
    assert qty.date_order is None


def test_a_column_with_no_such_cell_carries_no_measure() -> None:
    profile = profile_csv(b"Day,Qty\n2026-01-05,1\nMar 2024,2\n", now=NOW)

    assert profile.columns[0].date_order is None


def test_the_hint_is_recorded_for_the_first_of_each_month() -> None:
    profile = profile_csv(b"Day,Qty\n01/03/2024,1\n01/04/2024,2\n01/05/2024,1\n", now=NOW)
    measure = profile.columns[0].date_order

    assert measure is not None
    assert (measure.decision, measure.hint) == ("ask", "day_first")


# --- execution decides ---------------------------------------------------------------


def test_an_unanswered_ambiguous_file_is_refused(tmp_path: Path) -> None:
    run_id = raw_run(tmp_path, AMBIGUOUS)

    with pytest.raises(InvalidPlanError, match="column 'day' can be read day first or month first"):
        execute_run(tmp_path, run_id, _plan({"dayfirst": True}), now=NOW)
    assert not (tmp_path / run_id / "cleaned.csv").exists()


def test_the_answer_decides_and_is_recorded(tmp_path: Path) -> None:
    run_id = raw_run(tmp_path, AMBIGUOUS)

    report = execute_run(tmp_path, run_id, _plan({"dayfirst": True}, day_first=True), now=NOW)

    assert report.date_order == "day_first"
    assert report.confirmations.dates_day_first is True
    assert _cleaned_days(tmp_path, run_id) == ["2026-01-05", "2026-02-06", "2026-03-07"]


def test_an_unparsed_date_column_is_read_by_stage_2_in_the_order_recorded(tmp_path: Path) -> None:
    run_id = raw_run(tmp_path, AMBIGUOUS)

    report = execute_run(tmp_path, run_id, _plan(day_first=False, day_action="flag_only"),
                         now=NOW)

    assert report.date_order == "month_first"
    assert report.applied_confirmations().dates_day_first is False
    assert _cleaned_days(tmp_path, run_id) == ["05/01/2026", "06/02/2026", "2026-03-07"]


def test_the_proof_decides_when_nothing_is_asked(tmp_path: Path) -> None:
    """RAW_CSV's "15/01/2024" proves day first. Its default plan parses per
    cell, and that reads every one of its cells as day first does: it runs.
    The report records the order; the answers stay as submitted."""
    run_id = raw_run(tmp_path)

    report = execute_run(tmp_path, run_id, make_plan(), now=NOW)

    assert report.date_order == "day_first"
    assert report.confirmations == OrderConfirmations()
    assert report.applied_confirmations().dates_day_first is True
    final = CleaningPlanContract.model_validate_json(
        (tmp_path / run_id / "plan_final.json").read_text(encoding="utf-8"))
    assert final.confirmations == OrderConfirmations()


def test_a_file_with_no_such_cell_records_no_order(tmp_path: Path) -> None:
    run_id = raw_run(tmp_path, b"sku,name,qty,price,day\nA1,Mug,3,9.99,2026-01-05\n")

    report = execute_run(tmp_path, run_id, _plan(), now=NOW)

    assert report.date_order is None


# --- the parse step must read what the order reads -------------------------------------


def test_a_parse_step_reading_month_first_is_refused_on_a_day_first_answer(tmp_path: Path) -> None:
    run_id = raw_run(tmp_path, AMBIGUOUS)

    with pytest.raises(InvalidPlanError, match=r"05/01/2026.*2026-05-01.*day first.*2026-01-05"):
        execute_run(tmp_path, run_id, _plan({}, day_first=True), now=NOW)


def test_a_format_against_the_order_is_refused(tmp_path: Path) -> None:
    run_id = raw_run(tmp_path, AMBIGUOUS)

    with pytest.raises(InvalidPlanError, match="parse_datetime on column 'day'"):
        execute_run(tmp_path, run_id, _plan({"format": "%m/%d/%Y"}, day_first=True), now=NOW)


def test_a_format_that_agrees_runs(tmp_path: Path) -> None:
    run_id = raw_run(tmp_path, AMBIGUOUS)

    report = execute_run(tmp_path, run_id, _plan({"format": "%d/%m/%Y"}, day_first=True), now=NOW)

    assert report.date_order == "day_first"
    # The ISO cell does not match the format: flagged, as any cell a format misses.
    assert _cleaned_days(tmp_path, run_id)[:2] == ["2026-01-05", "2026-02-06"]


def test_dayfirst_on_a_proven_month_first_file_is_refused(tmp_path: Path) -> None:
    run_id = raw_run(tmp_path, b"sku,name,qty,price,day\nA1,Mug,3,9.99,01/13/2026\n"
                               b"B2,Cup,1,5.00,05/01/2026\n")

    with pytest.raises(InvalidPlanError, match="month first"):
        execute_run(tmp_path, run_id, _plan({"dayfirst": True}), now=NOW)


# --- stage 1's own parse and the change log ----------------------------------------------


def test_parse_datetime_with_dayfirst_leaves_iso_cells_alone() -> None:
    frame = pd.DataFrame({"day": pd.Series(["2026-01-05", "05/01/2026"], dtype="str")})

    parsed, _ = apply_action("parse_datetime", frame, "day", {"dayfirst": True})

    assert parsed["day"].dt.strftime("%Y-%m-%d").tolist() == ["2026-01-05", "2026-01-05"]


def test_the_change_log_notes_a_basic_offset() -> None:
    frame = pd.DataFrame({"day": pd.Series(["20240330T101500+1100", "20240407T101500+1000"],
                                           dtype="str")})

    parsed, entry = apply_action("parse_datetime", frame, "day", {"format": "%Y%m%dT%H%M%S%z"})

    assert parsed["day"].dt.strftime("%Y-%m-%d %H:%M").tolist() == ["2024-03-30 10:15",
                                                                     "2024-04-07 10:15"]
    assert "UTC offsets dropped" in entry.detail


def test_stage_1_contracts_are_3_1() -> None:
    assert (ai_schema.SCHEMA_VERSION, ai_plan.SCHEMA_VERSION, cleaning.SCHEMA_VERSION,
            PROFILE_VERSION) == ("3.1", "3.1", "3.1", "1.1")


def test_a_step_reading_a_date_the_order_cannot_hold_is_refused(tmp_path: Path) -> None:
    """Per cell, pandas reads 01/13/2026 as 13 January; answered day first,
    that cell is no date - the step would write a date the file does not
    hold (mutation check)."""
    run_id = raw_run(tmp_path, b"sku,name,qty,price,day\nA1,Mug,3,9.99,13/01/2026\n"
                               b"B2,Cup,1,5.00,01/13/2026\n")

    with pytest.raises(InvalidPlanError, match=r"'01/13/2026' as 2026-01-13.*day first \(no date\)"):
        execute_run(tmp_path, run_id, _plan({}, day_first=True), now=NOW)


def test_only_the_cells_the_order_concerns_are_compared(tmp_path: Path) -> None:
    """A format that reads a compact cell its own way says nothing about the
    day-month order: "20260105" read by "%Y%d%m" is the user's format's
    business, not a misread order (mutation check)."""
    run_id = raw_run(tmp_path, b"sku,name,qty,price,day\nA1,Mug,3,9.99,13/01/2026\n"
                               b"B2,Cup,1,5.00,20260105\n")

    report = execute_run(tmp_path, run_id, _plan({"format": "%Y%d%m"}), now=NOW)

    assert report.date_order == "day_first"


def test_the_measure_contract_follows_its_counts() -> None:
    base = {"shaped": 3, "day_first": 1, "month_first": 0, "ambiguous": 2,
            "day_first_example": "13/01/2026", "month_first_example": None, "hint": None}
    assert DateOrderMeasure(**base, decision="day_first").decision == "day_first"
    with pytest.raises(ValidationError, match="decision must be 'day_first'"):
        DateOrderMeasure(**base, decision="ask")
    with pytest.raises(ValidationError, match="an example is given exactly"):
        DateOrderMeasure(**(base | {"day_first_example": None}), decision="day_first")
    # Nothing depends on the order (review cycle 1 #10): no measure at all.
    with pytest.raises(ValidationError, match="carries no measure"):
        DateOrderMeasure(**(base | {"day_first": 0, "day_first_example": None, "ambiguous": 0}),
                         decision="ask")


def test_an_answer_about_a_column_with_no_such_cell_records_no_order(tmp_path: Path) -> None:
    """CONTRACTS section 5: null when no cell is written so (review cycle 1 #9)."""
    run_id = raw_run(tmp_path, b"sku,name,qty,price,day\nA1,Mug,3,9.99,2026-01-05\n")

    report = execute_run(tmp_path, run_id, _plan(day_first=True), now=NOW)

    assert report.date_order is None


def test_the_ai_never_sees_the_measure() -> None:
    """Its examples are cells beyond the bounded sample (CLAUDE.md 3.2;
    review cycle 1 #5)."""
    profile = profile_csv(b"Day,Notes\n13/01/2026,a\n05/01/2026,b\n", now=NOW)
    assert profile.columns[0].date_order is not None

    assert "date_order" not in build_profile_json(profile)


def test_the_refusal_names_the_fix_the_step_needs(tmp_path: Path) -> None:
    """Both orders proven, answered month first, the step per cell: pandas
    reads 13/01/2026 day first, so leaving dayfirst out cannot help - a
    format can (review cycle 1 #9)."""
    run_id = raw_run(tmp_path, b"sku,name,qty,price,day\nA1,Mug,3,9.99,13/01/2026\n"
                               b"B2,Cup,1,5.00,01/13/2026\n")

    with pytest.raises(InvalidPlanError, match="give it a format such as '%m/%d/%Y'"):
        execute_run(tmp_path, run_id, _plan({}, day_first=False), now=NOW)


def test_a_year_first_format_is_not_compared(tmp_path: Path) -> None:
    """YY/MM/DD looks like day-month-year; its own format "%y/%m/%d" was
    refused whatever the answer, and the fix the refusal gave wrote 2005 for
    2026 (2E-j review cycle 2 #2)."""
    run_id = raw_run(tmp_path, b"sku,name,qty,price,day\nA1,Mug,3,9.99,26/01/05\n"
                               b"B2,Cup,1,5.00,26/01/13\n")

    execute_run(tmp_path, run_id, _plan({"format": "%y/%m/%d"}), now=NOW)

    assert _cleaned_days(tmp_path, run_id) == ["2026-01-05", "2026-01-13"]


def test_a_proven_order_names_no_answer_to_change(tmp_path: Path) -> None:
    """A proven order has no question in Review (review cycle 2 #2)."""
    run_id = raw_run(tmp_path, b"sku,name,qty,price,day\nA1,Mug,3,9.99,13/01/2026\n"
                               b"B2,Cup,1,5.00,05/01/2026\n")

    with pytest.raises(InvalidPlanError) as refused:
        execute_run(tmp_path, run_id, _plan({}), now=NOW)

    assert "set its dayfirst to true" in str(refused.value)
    assert "change the answer" not in str(refused.value)


def test_a_hint_goes_only_with_a_question() -> None:
    with pytest.raises(ValidationError, match="only when the order is asked"):
        DateOrderMeasure(shaped=2, day_first=1, month_first=0, ambiguous=1,
                         day_first_example="13/01/2026", month_first_example=None,
                         decision="day_first", hint="month_first")
