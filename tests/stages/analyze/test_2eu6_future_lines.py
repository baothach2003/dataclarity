"""2E-u6 (Thach, 2026-10-02; 2E-u F6, before deploy): lines dated after the
upload date are left out of period selection, counted and reported; the
upload date is the reference (method: C:/Users/Happy/2E-u6-method.txt).
Written before the code; every figure worked by hand."""

from datetime import UTC, date, datetime

import pandas as pd
import pytest

from contracts.metrics import MetricsContract
from stages.analyze.assemble import assemble_metrics
from stages.diagnose.inputs import build_run_data

MAPPING = {"Date": "transaction_date", "Qty": "quantity", "Price": "unit_price", "Product": "product_name"}
NOW = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)


def _frame(rows: list[tuple[str, int, float]]) -> pd.DataFrame:
    return pd.DataFrame([{"Date": d, "Qty": str(q), "Price": str(p), "Product": "Mug"} for d, q, p in rows])


# Two whole months, January 300.00 and February 200.00, then one line typed in the future.
SHOP = [("2024-01-05", 1, 100.0), ("2024-01-31", 2, 100.0), ("2024-02-03", 1, 150.0), ("2024-02-29", 1, 50.0)]


def test_a_line_typed_in_the_future_no_longer_moves_the_period() -> None:
    """DF-B15's shape: before 2E-u6 the 2042 line made 2042-01 the current month."""
    found = assemble_metrics(_frame([*SHOP, ("2042-02-10", 1, 10.0)]), MAPPING, now=NOW,
                             uploaded_at=datetime(2024, 3, 5, 9, 0, tzinfo=UTC))
    assert (found.period.current, found.period.previous) == ("2024-02", "2024-01")
    assert (found.period.data_start, found.period.data_end) == (date(2024, 1, 5), date(2024, 2, 29))
    assert (found.core.revenue_current, found.core.revenue_previous) == (200.0, 300.0)
    assert found.period.upload_cutoff == date(2024, 3, 5)  # 09:00 + 14 h is still the 5th
    assert (found.core.future_lines, found.core.future_revenue) == (1, 10.0)
    assert found.core.future_lines_reason == (
        "1 line is dated after this file was uploaded - later than 2024-03-05 on any clock - the latest "
        "2042-02-10, so it is left out of choosing the months compared and the dates the file covers; its "
        "revenue (10.00) stays in its own month, outside both compared months.")
    # Every other figure keeps it (the standing no-guess rule): its own month.
    assert [(m.period, m.revenue) for m in found.core.revenue_by_month][-1] == ("2042-02", 10.0)


def test_several_lines_are_counted_with_their_revenue() -> None:
    found = assemble_metrics(_frame([*SHOP, ("2042-02-10", 1, 10.0), ("2031-07-01", 3, 5.0)]), MAPPING,
                             now=NOW, uploaded_at=datetime(2024, 3, 5, tzinfo=UTC))
    assert (found.core.future_lines, found.core.future_revenue) == (2, 25.0)
    assert found.core.future_lines_reason is not None
    assert found.core.future_lines_reason.startswith(
        "2 lines are dated after this file was uploaded - later than 2024-03-05 on any clock - the latest "
        "2042-02-10, so they are left out of choosing the months compared and the dates the file covers; their "
        "revenue (25.00) ")


def test_nothing_after_the_upload_reports_nothing() -> None:
    found = assemble_metrics(_frame(SHOP), MAPPING, now=NOW, uploaded_at=datetime(2024, 3, 5, tzinfo=UTC))
    assert (found.core.future_lines, found.core.future_revenue, found.core.future_lines_reason) == (0, 0.0, None)


@pytest.mark.parametrize("uploaded,cutoff", [
    (datetime(2026, 10, 1, 12, 0, tzinfo=UTC), date(2026, 10, 2)),   # 12:00 + 14 h: the 2nd somewhere
    (datetime(2026, 10, 1, 9, 59, tzinfo=UTC), date(2026, 10, 1)),   # 23:59 on the 1st at UTC+14
    (datetime(2026, 10, 1, 10, 0, tzinfo=UTC), date(2026, 10, 2)),   # midnight on the 2nd at UTC+14
])
def test_the_cutoff_is_the_upload_day_on_the_clock_furthest_ahead(uploaded: datetime, cutoff: date) -> None:
    found = assemble_metrics(_frame(SHOP), MAPPING, now=NOW, uploaded_at=uploaded)
    assert found.period.upload_cutoff == cutoff


def test_a_line_on_the_cutoff_day_stays_and_one_a_day_later_is_left_out() -> None:
    uploaded = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)  # cutoff 2026-10-02
    rows = [("2026-08-01", 1, 10.0), ("2026-09-30", 1, 10.0)]
    on_the_day = assemble_metrics(_frame([*rows, ("2026-10-02 23:30", 1, 10.0)]), MAPPING, now=NOW,
                                  uploaded_at=uploaded)
    assert (on_the_day.period.data_end, on_the_day.core.future_lines) == (date(2026, 10, 2), 0)
    a_day_later = assemble_metrics(_frame([*rows, ("2026-10-03 00:00", 1, 10.0)]), MAPPING, now=NOW,
                                   uploaded_at=uploaded)
    assert (a_day_later.period.data_end, a_day_later.core.future_lines) == (date(2026, 9, 30), 1)


def test_without_an_upload_time_now_is_the_reference() -> None:
    found = assemble_metrics(_frame([*SHOP, ("2042-02-10", 1, 10.0)]), MAPPING, now=NOW)
    assert found.period.upload_cutoff == date(2026, 10, 2)
    assert (found.period.current, found.core.future_lines) == ("2024-02", 1)


def test_a_file_dated_entirely_after_the_upload_selects_as_a_file_with_no_date() -> None:
    found = assemble_metrics(_frame([("2042-01-05", 1, 10.0), ("2042-02-10", 1, 20.0)]), MAPPING, now=NOW,
                             uploaded_at=datetime(2024, 3, 5, tzinfo=UTC))
    # select_period's fallback, judged as of the upload (review 1, #1): its
    # day, the last month complete by it.
    assert (found.period.data_start, found.period.data_end, found.period.current) == (
        date(2024, 3, 5), date(2024, 3, 5), "2024-02")
    assert (found.core.future_lines, found.core.future_revenue) == (2, 30.0)


def test_any_class_of_line_counts_when_it_moved_the_dates() -> None:
    # An undated line stays undated, never "future"; a dated line of any
    # class after the cutoff is counted, its revenue only when counted.
    frame = _frame([*SHOP, ("2042-02-10", 1, 10.0), ("", 1, 7.0)])
    found = assemble_metrics(frame, MAPPING, now=NOW, uploaded_at=datetime(2024, 3, 5, tzinfo=UTC))
    assert (found.core.future_lines, found.core.undated_lines) == (1, 1)


GRAIN = [(f"2023-{m:02d}-01", 1, 100.0 + m) for m in range(1, 13)] + [("2024-01-01", 1, 50.0)]


def test_a_month_grain_file_stays_month_grain() -> None:
    """A future line not on the 1st broke the month-grain test, so the whole
    file read as daily data."""
    found = assemble_metrics(_frame([*GRAIN, ("2042-02-10", 1, 10.0)]), MAPPING, now=NOW,
                             uploaded_at=datetime(2024, 3, 5, tzinfo=UTC))
    assert found.period.month_grain is True
    assert (found.period.current, found.period.previous) == ("2024-01", "2023-12")


def test_stage_3_ends_its_month_grain_coverage_where_stage_2_does() -> None:
    """One definition: stage 3 reads the cutoff from metrics.json, so a 2042
    line (on the 1st, still month grain) adds no empty months 2024-02..2042-01
    to its history."""
    frame = _frame([*GRAIN, ("2042-02-01", 1, 10.0)])
    found = assemble_metrics(frame, MAPPING, now=NOW, uploaded_at=datetime(2024, 3, 5, tzinfo=UTC))
    data = build_run_data(frame, MAPPING, found)
    assert data.complete_months[-1] == "2024-01"
    assert len(data.complete_months) == 13


def test_a_metrics_file_written_before_2eu6_still_reads() -> None:
    found = assemble_metrics(_frame(SHOP), MAPPING, now=NOW, uploaded_at=datetime(2024, 3, 5, tzinfo=UTC))
    old = found.model_dump(mode="json")
    old["schema_version"] = "16.0"
    del old["period"]["upload_cutoff"]
    for name in ("future_lines", "future_revenue", "future_lines_reason"):
        del old["core"][name]
    restored = MetricsContract.model_validate(old)
    assert (restored.period.upload_cutoff, restored.core.future_lines, restored.core.future_lines_reason) == (
        None, 0, None)
    assert found.schema_version == "16.1"


def test_the_reason_is_paired_with_the_count() -> None:
    found = assemble_metrics(_frame(SHOP), MAPPING, now=NOW, uploaded_at=datetime(2024, 3, 5, tzinfo=UTC))
    broken = found.model_dump(mode="json")
    broken["core"]["future_lines"] = 2
    with pytest.raises(ValueError, match="future_lines_reason"):
        MetricsContract.model_validate(broken)


def test_a_naive_upload_time_is_utc() -> None:
    # The app stores UTC; a naive 10:30 read on a UTC+7 machine's clock would
    # be 03:30 UTC and give the 1st.
    found = assemble_metrics(_frame(SHOP), MAPPING, now=NOW, uploaded_at=datetime(2026, 10, 1, 10, 30))
    assert found.period.upload_cutoff == date(2026, 10, 2)


# --- review 1 ------------------------------------------------------------------------------------------


def test_a_month_grain_file_is_judged_by_its_upload_not_the_day_it_is_analysed() -> None:
    """Review 1, #1 (a FABRICATE on monthly exports): uploaded on 15 February
    with February's month-to-date row, the file compares January with
    December - re-analysed in March, the analysis clock made February a whole
    month (-36.7% on the reviewer's case)."""
    rows = [*GRAIN, ("2024-02-01", 1, 20.0)]
    found = assemble_metrics(_frame(rows), MAPPING, now=datetime(2024, 3, 10, tzinfo=UTC),
                             uploaded_at=datetime(2024, 2, 15, 9, 0, tzinfo=UTC))
    assert (found.period.month_grain, found.period.current) == (True, "2024-01")


def test_without_an_upload_time_the_analysis_clock_still_judges_month_grain() -> None:
    found = assemble_metrics(_frame([*GRAIN, ("2024-02-01", 1, 20.0)]), MAPPING,
                             now=datetime(2024, 3, 10, tzinfo=UTC))
    assert found.period.current == "2024-02"


def test_a_line_with_no_revenue_is_said_to_count_in_none() -> None:
    # Review 1, #7: an unpriced line typed 2042 read "its revenue (0.00)".
    frame = _frame([*SHOP]).assign(Price=["100.0", "100.0", "150.0", "50.0"])
    frame = pd.concat([frame, pd.DataFrame([{"Date": "2042-02-10", "Qty": "1", "Price": "", "Product": "Mug"}])],
                      ignore_index=True)
    found = assemble_metrics(frame, MAPPING, now=NOW, uploaded_at=datetime(2024, 3, 5, tzinfo=UTC))
    assert found.core.future_lines == 1
    assert found.core.future_lines_reason is not None
    assert found.core.future_lines_reason.endswith("; it counts in no revenue figure.")


@pytest.mark.parametrize("change,message", [
    ({"core": {"future_lines": 0, "future_revenue": 5.0, "future_lines_reason": None}}, "future_revenue"),
    ({"period": {"upload_cutoff": None}}, "upload_cutoff"),
    ({"period": {"upload_cutoff": "2024-02-01"}}, "upload_cutoff"),
])
def test_the_contract_holds_the_rules_together(change: dict, message: str) -> None:
    """Review 1, #9: revenue with no line, lines with no cutoff, a cutoff
    before the last date the period covers."""
    found = assemble_metrics(_frame([*SHOP, ("2042-02-10", 1, 10.0)]), MAPPING, now=NOW,
                             uploaded_at=datetime(2024, 3, 5, tzinfo=UTC))
    payload = found.model_dump(mode="json")
    for block, fields in change.items():
        payload[block].update(fields)
    with pytest.raises(ValueError, match=message):
        MetricsContract.model_validate(payload)


def test_each_block_alone_chooses_the_same_period(tmp_path) -> None:
    """Review 1, #8: the products and customers blocks run alone chose their
    period without the cutoff (2042-01 on DF-B15)."""
    from stages.analyze.metrics_customers import customer_metrics_for_run
    from stages.ingest.cleaning import execute_run
    from tests.stages.ingest.cleaning_fixtures import column_action, make_plan, raw_run

    csv = (b"sku,name,qty,price,day\nA1,Mug,1,10.00,2024-01-05\nA1,Mug,1,10.00,2024-02-29\n"
           b"A1,Mug,1,10.00,2042-02-10\n")
    run_id = raw_run(tmp_path, csv)
    execute_run(tmp_path, run_id, make_plan([column_action("sku"), column_action("name"), column_action("qty"),
                                             column_action("price"), column_action("day", "parse_datetime")]))
    assert customer_metrics_for_run(tmp_path, run_id, NOW).rfm_reference_date == date(2024, 3, 1)
