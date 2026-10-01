"""The conformance suite of docs/DATA_FAILURE_MODES.md (session 2E-u), part 1:
DF-A file structure and DF-B dates. One rule: each mode's sample gives the
correct result or an explicit refusal - never a silent wrong figure. A case
works its figure by hand (the base: 42.00 a day, 1,218.00 in 2024-02,
1,302.00 in 2024-01) or asserts the refusal's code, reason or note; a mode
v1 accepts as it is (LIMIT) is pinned as test_known_limit_df_<id>, so a fix
fails it loudly - never xfail (CONSTRAINTS F1, F2). Parts 2-4:
test_conformance_amounts_lines.py, test_conformance_people_coverage.py,
test_catalog.py.
"""

from pathlib import Path

import pandas as pd
import pytest

from contracts.cleaning import CleaningPlanContract, ColumnAction, OrderConfirmations
from shared.dates import as_dates
from shared.line_numbers import RequiredColumnMissingError
from stages.ingest.date_order import DateQuestionUnanswered, execution_order
from stages.ingest.issue_counts import count_column_issues
from stages.ingest.profiling import CsvParseError, EmptyCsvError, profile_csv, read_csv_text
from tests.data_failures.flow import (CAST_PRICE, FEB, JAN, NOW, check, diagnosis, metrics, real_flow, sample,
                                      verdicts)

# --- A. file structure ----------------------------------------------------------------------------


def test_df_a3_a_header_only_file_is_refused() -> None:
    with pytest.raises(EmptyCsvError):
        profile_csv(sample("DF-A3").raw or b"", now=NOW)


def test_df_a4_bytes_that_are_no_csv_are_refused() -> None:
    with pytest.raises(CsvParseError):
        profile_csv(sample("DF-A4").raw or b"", now=NOW)


def test_df_a5_a_latin_1_file_is_read_and_says_so() -> None:
    profile = profile_csv(sample("DF-A5").raw or b"", now=NOW)
    product = next(c for c in profile.columns if c.name == "Product")
    assert profile.dataset.encoding_used == "latin-1"
    assert "Café au lait" in {v.value for v in product.top_values}


def test_df_a6_a_semicolon_file_is_split_on_its_semicolons() -> None:
    profile = profile_csv(sample("DF-A6").raw or b"", now=NOW)
    assert (profile.dataset.delimiter, profile.dataset.columns) == (";", 5)


def test_df_a6b_a_european_export_is_read_with_its_decimal_commas(tmp_path: Path) -> None:
    """Was a LIMIT (2E-u F1): stage 1's cast read no "10,0", so every price
    was lost and the run blocked saying the export was cut short. Since
    2E-u1 "10,0" proves a decimal comma (one separator, not followed by three
    digits) and stage 1 rewrites it: February 2024 is 29 x 42.00 = 1,218.00,
    January 31 x 42.00 = 1,302.00, as the clean file."""
    found, diagnosed = real_flow(sample("DF-A6B"), tmp_path, CAST_PRICE)
    assert (found.core.revenue_current, found.core.revenue_previous) == (1218.0, 1302.0)
    assert diagnosed.headline.rule != 1


def test_df_a7_duplicate_rows_are_counted() -> None:
    assert profile_csv(sample("DF-A7").raw or b"", now=NOW).dataset.duplicate_rows == 3


def test_df_a8_an_empty_column_is_measured_by_the_profile() -> None:
    profile = profile_csv(sample("DF-A8").raw or b"", now=NOW)
    assert next(c.null_pct for c in profile.columns if c.name == "Note") == 100.0


@pytest.mark.parametrize("mode,column,code,count", [("DF-A9", "Store", "constant_column", 12),
                                                    ("DF-A10", "Qty", "mixed_types", 2)])
def test_a_column_shape_is_counted_by_stage_1(mode: str, column: str, code: str, count: int) -> None:
    # The AI may propose the issue; stage 1 keeps only what the cells prove.
    frame = read_csv_text(sample(mode).raw or b"").frame
    assert count_column_issues(frame[column]).get(code) == count  # type: ignore[call-overload]  # an IssueCode


def test_df_a12_metrics_without_a_price_column_are_refused() -> None:
    with pytest.raises(RequiredColumnMissingError, match="unit_price"):
        metrics(sample("DF-A12"))


def test_known_limit_df_a13_a_nul_past_the_first_8_kb_cuts_a_price(tmp_path: Path) -> None:
    """LIMIT (2E-u review #5; 8D's "unreachable from a file" was wrong): the
    upload refuses a NUL in the first 8 KB (backend's binary check), but one
    further on ends its cell - "1", NUL, "0.0" reads 1: Ann's Mug 10.00
    becomes 1.00, revenue 1,218.00 - 9.00, nothing flagged."""
    found, _ = real_flow(sample("DF-A13"), tmp_path)
    assert found.core.revenue_current == FEB - 9.0


def test_df_a14_a_row_longer_than_the_header_is_refused() -> None:
    with pytest.raises(CsvParseError):
        profile_csv(sample("DF-A14").raw or b"", now=NOW)


def test_df_a15_a_utf_16_file_is_read() -> None:
    profile = profile_csv(sample("DF-A15").raw or b"", now=NOW)
    assert (profile.dataset.encoding_used, profile.dataset.rows) == ("utf-16", 12)


# --- B. dates -----------------------------------------------------------------------------------


def test_df_b1_unparseable_dates_are_left_out_and_counted() -> None:
    found = metrics(sample("DF-B1"))
    assert (found.core.undated_lines, found.core.revenue_current) == (5, FEB - 38.0)
    assert found.core.undated_lines_reason


def test_df_b2_two_date_formats_read_as_one_calendar() -> None:
    found = metrics(sample("DF-B2"))
    assert (found.core.revenue_previous, found.core.revenue_current, found.core.undated_lines) == (JAN, FEB, 0)


def _date_plan(answer: bool | None) -> CleaningPlanContract:
    from tests.stages.ingest.cleaning_fixtures import make_plan

    actions = [ColumnAction.model_validate({
        "source_name": name, "semantic_type": kind, "canonical_field": field, "action": "flag_only", "params": {},
        "rationale": "chosen by the user", "alternatives": [], "edited_by_user": True})
        for name, kind, field in (("Date", "datetime", "transaction_date"),
                                  ("Qty", "numeric_discrete", "quantity"), ("Price", "numeric_continuous", "unit_price"),
                                  ("Product", "categorical_nominal", "product_name"),
                                  ("Cust", "identifier", "customer"))]
    return make_plan(actions).model_copy(update={"confirmations": OrderConfirmations(dates_day_first=answer)})


@pytest.mark.parametrize("mode", ["DF-B3", "DF-B7"])
def test_an_order_no_cell_proves_is_asked_and_never_guessed(mode: str) -> None:
    frame = pd.DataFrame(sample(mode).rows)
    with pytest.raises(DateQuestionUnanswered):
        execution_order(_date_plan(None), frame)
    assert execution_order(_date_plan(True), frame) == "day_first"


@pytest.mark.parametrize("mode", ["DF-B4", "DF-B5"])
def test_a_month_grain_file_compares_months_and_tests_no_calendar(mode: str) -> None:
    found = metrics(sample(mode))
    assert (found.period.month_grain, found.core.revenue_current) == (True, FEB)
    assert verdicts(diagnosis(sample(mode)))["T1"] == "not_testable"


def test_known_limit_df_b6_a_dotted_time_beside_a_year() -> None:
    """LIMIT (8D, Thach's Q12): one "10.05.30 2026" in an ISO file asks the
    date question for the whole file; answered day first it reads 10 May
    2030 (20:26), which moves the file's end - and its current month - to
    2030 (review #6)."""
    frame = pd.DataFrame(sample("DF-B6").rows)
    with pytest.raises(DateQuestionUnanswered):
        execution_order(_date_plan(None), frame)
    read = as_dates(pd.Series(["10.05.30 2026"]), offsets="wall_clock", order="day_first").iloc[0]
    assert read.date().isoformat() == "2030-05-10"


def test_df_b8_a_file_ending_mid_month_compares_the_last_whole_month() -> None:
    found = metrics(sample("DF-B8"))
    assert (found.period.current, found.core.revenue_current) == ("2024-02", FEB)


def test_df_b9_a_file_starting_mid_month_keeps_that_month_out_of_the_history() -> None:
    from stages.diagnose.inputs import build_run_data

    case = sample("DF-B9")
    data = build_run_data(pd.DataFrame(case.rows), case.mapping, metrics(case))
    assert (data.complete_months[0], data.metrics.core.revenue_current) == ("2023-02", FEB)


def test_df_b10_a_previous_month_the_file_starts_inside_withholds_every_comparison() -> None:
    found = metrics(sample("DF-B10"))
    assert (found.period.previous_complete, found.core.revenue_change_pct) == (False, None)
    assert found.core.revenue_change_pct_reason


def test_df_b10b_days_lost_inside_the_previous_month_are_a_trust_caution() -> None:
    # Stage 2 cannot tell a gap from quiet days and compares: (1,218 - 1,092)
    # / 1,092 = +11.5%; stage 3's D1 checks the previous month too and
    # cautions (3E1) - the standing rule's visible note (CLAUDE.md 3.3a).
    assert round(metrics(sample("DF-B10B")).core.revenue_change_pct or 0, 1) == 11.5
    assert check(diagnosis(sample("DF-B10B")), "D1") == "caution"


def test_known_limit_df_b10c_two_leading_days_are_tolerated_without_a_note() -> None:
    """LIMIT (8D "From 5A": stage 2 tolerates two missing leading days): a
    file starting on 2024-01-03 compares January's 29 days (1,218.00) with
    February's - "no change" if the export was cut short (review #2)."""
    found = metrics(sample("DF-B10C"))
    assert (found.period.previous_complete, found.core.revenue_previous, found.core.revenue_change_pct) == (
        True, FEB, 0.0)


def test_df_b11_a_placeholder_date_is_no_date() -> None:
    found = metrics(sample("DF-B11"))
    assert (found.core.undated_lines, found.core.revenue_current) == (1, FEB - 10.0)


@pytest.mark.parametrize("mode", ["DF-B12", "DF-B13", "DF-B16", "DF-B17"])
def test_known_limit_a_cell_naming_no_day_is_no_date(mode: str) -> None:
    """LIMIT (8D "From 2E-j", "From 2E-o"): Excel's "Feb-24" and its serial
    "45332", a time with a word ("klo 10.30"), a Vietnamese AM marker
    ("SA") - the line is left out and counted, though some were readable."""
    found = metrics(sample(mode))
    assert (found.core.undated_lines, found.core.revenue_current) == (1, FEB - 10.0)


def test_known_limit_df_b14_year_first_two_digit_dates_are_misread(tmp_path: Path) -> None:
    """LIMIT, a FABRICATE (8D "From 2E-j" and "From 2E-u", Thach's F2:
    YY/MM/DD without a year-first format reads as D/M/Y): no question is
    asked and the calendar lands in 2001-2031. Since 2E-u6 the misread lines
    after the upload choose no period, so the months compared are misread
    ones before it - 2026-08, a rule-7 headline (it was 2031-11 and rule 6,
    "products were launched or discontinued"); which months depends on the
    upload date."""
    found, diagnosed = real_flow(sample("DF-B14"), tmp_path)
    assert (found.period.current, diagnosed.headline.rule) == ("2026-08", 7)
    assert found.core.future_lines > 0


def test_df_b15_a_line_dated_after_the_upload_chooses_no_period() -> None:
    """HANDLED since 2E-u6 (Thach, 2026-10-02; was a LIMIT: 2042-01 became
    the current month and the run blocked, saying the export was cut short).
    The line is left out of choosing the period, counted with its revenue,
    and keeps its own month; February is compared with January as without
    it, and nothing blocks."""
    found = metrics(sample("DF-B15"))
    assert (found.period.current, found.period.data_end.isoformat()) == ("2024-02", "2024-02-29")
    assert (found.core.revenue_current, found.core.future_lines, found.core.future_revenue) == (FEB, 1, 10.0)
    assert found.core.revenue_by_month[-1].period == "2042-02"
    assert diagnosis(sample("DF-B15")).headline.rule == 7  # within the shop's usual movement


def test_known_limit_df_b15b_a_year_typo_before_the_upload_still_moves_the_period() -> None:
    """LIMIT (2E-u6 review 1, #10; for Thach): a line typed 2025 in a 2024
    file is before the upload, so no rule tells it from a late sale - the
    period moves to 2025-01 and the run blocks, saying the export was cut
    short."""
    found = metrics(sample("DF-B15B"))
    assert (found.period.current, found.core.future_lines) == ("2025-01", 0)
    assert diagnosis(sample("DF-B15B")).headline.rule == 1
