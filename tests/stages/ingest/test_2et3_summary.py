"""Session 2E-t3 (Thach, 2026-09-28): Review's whole-file view of the line
taxonomy, computed by stage 1 - written before the code.
docs/LINE_TAXONOMY.md section 5: "Review shows [the identity] for the whole
file, computed by stage 1 (pandas) for the answers as they stand, with the
outside-revenue totals beside it"; the unclassified and unmeasurable counts,
the notes, and the reserved-name rename (Q24) in Review.

The file is 2E-t2's (tests/stages/analyze/test_2et2_stage2.py), through a
flag-only plan. Over the whole file, by hand - the counted, dated lines 1-9
and 17:
  gross 20 + 5 + 30 + 10 = 65; returns 10 + 3 = 13; discounts 5; other
  deductions 2; other revenue 4; net 65 - 13 - 5 - 2 + 4 = 49; money moved
  20 + 5 + 30 + 10 + 5 + 2 + 4 + 0 + 3 + 10 = 89; the returns on DOT, which
  nobody confirmed: 3.
  Outside revenue: the AMAZON FEE cost, 1 line -7; stock received +10 on
  line 11, and line 12 with no price. Unmeasurable: lines 13 and 16 with no
  quantity, 14 with no price. Undated: line 15 (16 is unmeasurable).
"""

from datetime import UTC, datetime

import numpy as np
import pandas as pd
import pytest

from contracts.cleaning import CleaningPlanContract, LineClassAnswer, OrderConfirmations
from contracts.lines import LineSummary
from stages.analyze.assemble import analyze_run
from stages.ingest.cleaning import execute_run
from stages.ingest.line_summary import DATE_QUESTION, NO_DATE, NOT_CLASSED, TOO_LARGE, line_summary
from stages.ingest.plan_validation import InvalidPlanError
from stages.ingest.profiling import read_csv_text
from tests.stages.analyze.test_2et2_stage2 import ROWS

NOW = datetime(2026, 9, 26, tzinfo=UTC)
COLUMNS = [("Day", "datetime", "transaction_date"), ("Order", "identifier", "order_id"),
           ("Who", "identifier", "customer"), ("Sku", "identifier", "sku"), ("Name", "text", "product_name"),
           ("Qty", "numeric_discrete", "quantity"), ("Price", "numeric_continuous", "unit_price"),
           ("Type", "categorical_nominal", "transaction_type")]
ANSWERS = OrderConfirmations(line_classes=[
    LineClassAnswer(value="D", field="sku", line_class="discount"),
    LineClassAnswer(value="POST", field="sku", line_class="charge"),
    LineClassAnswer(value="AMZ", field="sku", line_class="cost")])


def _raw(rows=ROWS, names=None) -> bytes:
    frame = pd.DataFrame(rows, columns=names or [name for name, _, _ in COLUMNS])
    return frame.to_csv(index=False).encode("utf-8")


def _plan(columns=COLUMNS, answers: OrderConfirmations = ANSWERS) -> CleaningPlanContract:
    return CleaningPlanContract.model_validate({
        "schema_version": "4.0", "generated_at": "2026-09-26T00:00:00Z", "source": "manual",
        "dataset_actions": [],
        "column_actions": [{"source_name": n, "semantic_type": t, "canonical_field": f, "action": "flag_only",
                            "params": {"note": ""}, "rationale": "", "alternatives": [], "edited_by_user": False}
                           for n, t, f in columns],
        "confirmations": answers.model_dump(mode="json")})


@pytest.fixture(scope="module")
def summary() -> LineSummary:
    found = line_summary(read_csv_text(_raw()).frame, _plan())
    assert (found.reserved_renames, found.unavailable) == ([], None)
    assert found.summary is not None
    return found.summary


def test_the_identity_of_the_whole_file(summary: LineSummary) -> None:
    terms = summary.identity
    assert (terms.gross_sales, terms.returns, terms.discounts, terms.other_deductions, terms.other_revenue,
            terms.net_revenue, terms.returns_on_suggested_keys, terms.money_moved) == pytest.approx(
        (65.0, 13.0, 5.0, 2.0, 4.0, 49.0, 3.0, 89.0))
    assert (summary.lines, summary.undated_lines) == (17, 1)


def test_what_is_outside_revenue_across_the_file(summary: LineSummary) -> None:
    assert [(r.line_class, r.scope, r.sign, r.lines, r.amount, r.lines_without_amount)
            for r in summary.outside_revenue] == [
        ("cost", "file", None, 1, -7.0, 0), ("stock_in", "file", "positive", 1, 10.0, 0),
        ("stock_in", "file", "no_money", 1, 0.0, 1)]


def test_the_unclassified_and_unmeasurable_lines(summary: LineSummary) -> None:
    assert (summary.unclassified.lines, summary.unclassified.amount,
            summary.unclassified.share_of_money_moved) == (0, 0.0, 0.0)
    assert [(r.reason, r.lines) for r in summary.unmeasurable] == [("no quantity", 2), ("no price", 1)]


def test_the_notes_with_their_file_measures(summary: LineSummary) -> None:
    assert [n.code for n in summary.notes] == [
        "same_day_cancellations", "returns_booked_as_in", "unconfirmed_suggestions", "unconfirmed_deductions",
        "discounts_in_prices"]
    measures = {(n.code, m.name): (m.lines, m.amount, m.orders, m.keys) for n in summary.notes for m in n.measures}
    assert measures[("same_day_cancellations", "returns")] == (1, -10.0, 1, None)
    assert measures[("same_day_cancellations", "sales")] == (1, 30.0, 1, None)
    assert measures[("returns_booked_as_in", "unknown")] == (1, None, None, None)
    assert measures[("unconfirmed_suggestions", "lines")] == (2, 2.0, 1, 1)
    assert measures[("unconfirmed_suggestions", "returns")] == (1, -3.0, 1, None)
    assert measures[("unconfirmed_deductions", "lines")] == (1, -2.0, None, None)
    assert {m.scope for n in summary.notes for m in n.measures} == {"file"}


def test_the_answers_as_they_stand_move_the_figures() -> None:
    # Unanswered, POSTAGE is a sale (+4 to gross sales, 0 other revenue),
    # the -1 @ 5 Discount a return (+5 to returns, 0 discounts) and the
    # AMAZON FEE at -7 an allowance, back in revenue (+7 to the other
    # deductions): 69 - 18 - 0 - 9 + 0 = 42.
    found = line_summary(read_csv_text(_raw()).frame, _plan(answers=OrderConfirmations())).summary
    assert found is not None
    terms = found.identity
    assert (terms.gross_sales, terms.returns, terms.discounts, terms.other_deductions, terms.other_revenue,
            terms.net_revenue) == pytest.approx((69.0, 18.0, 0.0, 9.0, 0.0, 42.0))
    assert [r.line_class for r in found.outside_revenue] == ["stock_in", "stock_in"]


def test_the_summary_is_what_metrics_json_says_of_the_whole_file(tmp_path) -> None:
    # One definition: execute then stage 2, on the same file and answers, give
    # the same file-scope blocks, and the months' revenue adds up to its net.
    run_id = "0a000000-0000-4000-8000-0000000000e3"
    (tmp_path / run_id).mkdir()
    (tmp_path / run_id / "raw.csv").write_bytes(_raw())
    execute_run(tmp_path, run_id, _plan(), now=NOW)
    core = analyze_run(tmp_path, run_id, NOW).core
    found = line_summary(read_csv_text(_raw()).frame, _plan()).summary
    assert found is not None
    assert found.outside_revenue == [r for r in core.outside_revenue if r.scope == "file"]
    assert found.unmeasurable == [r for r in core.unmeasurable if r.scope == "file"]
    assert found.unclassified == core.unclassified
    assert [n.model_copy(update={"measures": [m for m in n.measures if m.scope == "file"]}) for n in core.notes] \
        == found.notes
    assert found.undated_lines == core.undated_lines
    assert sum(m.revenue for m in core.revenue_by_month) == pytest.approx(found.identity.net_revenue)


def _same_day(found) -> dict:
    [note] = [n for n in found.summary.notes if n.code == "same_day_cancellations"]
    return {m.name: m.lines for m in note.measures}


def test_the_lines_are_read_as_cleaned_csvs_text_holds_them() -> None:
    # " N/A " trimmed is "N/A", which cleaned.csv reads back as missing (the
    # text_reads_as_missing warning): the return names no customer, and no
    # match can check it - as execute and stage 2 read it (mutation K3).
    rows = [("2026-07-01", "O1", "Ann", "A1", "Mug", "2", "10", "out"),
            ("2026-08-03", "O2", " N/A ", "A1", "Mug", "-1", "10", "out"),
            ("2026-09-01", "O3", "Ann", "A1", "Mug", "1", "10", "out")]
    plan = _plan(answers=OrderConfirmations())
    plan.column_actions[2] = plan.column_actions[2].model_copy(update={"action": "trim_whitespace", "params": {}})
    found = line_summary(read_csv_text(_raw(rows)).frame, plan)
    assert _same_day(found)["returns_unchecked"] == 1


def test_the_dates_are_read_in_the_order_the_run_applies() -> None:
    # 13/02/2026 proves the file day first: 05/03/2026 is 5 March, the day the
    # return dated 2026-03-05 was rung - a same-day match. Read in the order
    # submitted (none), 05/03 was 3 May (mutation K6).
    rows = [("13/02/2026", "O1", "Bo", "A2", "Cup", "1", "5", "out"),
            ("05/03/2026", "O2", "Ann", "A1", "Mug", "2", "10", "out"),
            ("2026-03-05", "O3", "Ann", "A1", "Mug", "-1", "10", "out")]
    found = line_summary(read_csv_text(_raw(rows)).frame, _plan(answers=OrderConfirmations()))
    assert (_same_day(found)["returns"], _same_day(found)["sales"]) == (1, 1)


def test_a_source_column_named_like_a_class_column_is_said_before_the_run() -> None:
    rows = [row + ("keep me",) for row in ROWS]
    names = [name for name, _, _ in COLUMNS] + ["line_class"]
    columns = COLUMNS + [("line_class", "text", "ignore")]
    found = line_summary(read_csv_text(_raw(rows, names)).frame, _plan(columns))
    assert [(r.source, r.written_as) for r in found.reserved_renames] == [("line_class", "line_class_source")]
    assert found.summary is not None and found.summary.identity.net_revenue == pytest.approx(49.0)


def test_without_a_quantity_and_a_price_nothing_is_classed_or_renamed() -> None:
    rows = [row + ("keep me",) for row in ROWS]
    names = [name for name, _, _ in COLUMNS] + ["line_class"]
    columns = [c if c[0] != "Price" else ("Price", "numeric_continuous", "ignore") for c in COLUMNS]
    columns.append(("line_class", "text", "ignore"))
    found = line_summary(read_csv_text(_raw(rows, names)).frame, _plan(columns))
    assert (found.reserved_renames, found.summary, found.unavailable) == ([], None, NOT_CLASSED)


def test_without_a_date_the_renames_are_said_and_the_figures_wait() -> None:
    rows = [row + ("keep me",) for row in ROWS]
    names = [name for name, _, _ in COLUMNS] + ["line_class"]
    columns = [c if c[0] != "Day" else ("Day", "text", "ignore") for c in COLUMNS] + [("line_class", "text", "ignore")]
    found = line_summary(read_csv_text(_raw(rows, names)).frame, _plan(columns))
    assert (found.summary, found.unavailable) == (None, NO_DATE)
    assert [(r.source, r.written_as, r.holds) for r in found.reserved_renames] == [
        ("line_class", "line_class_source", "each line's class")]


# --- review 1 (2E-t3) ----------------------------------------------------------------------


def test_an_open_date_question_is_said_not_refused() -> None:
    # 05/03 and 06/04 read either way: Review asks, Confirm waits - and the
    # summary says so, the renames still said (review 1 #2).
    rows = [("05/03/2026", "O1", "Ann", "A1", "Mug", "2", "10", "out", "x"),
            ("06/04/2026", "O2", "Bo", "A1", "Mug", "1", "10", "out", "x")]
    names = [name for name, _, _ in COLUMNS] + ["line_class"]
    columns = COLUMNS + [("line_class", "text", "ignore")]
    found = line_summary(read_csv_text(_raw(rows, names)).frame, _plan(columns, OrderConfirmations()))
    assert (found.summary, found.unavailable) == (None, DATE_QUESTION)
    assert [r.source for r in found.reserved_renames] == ["line_class"]
    answered = OrderConfirmations(dates_day_first=True)
    assert line_summary(read_csv_text(_raw(rows, names)).frame, _plan(columns, answered)).summary is not None


def test_amounts_too_large_to_add_up_are_said_not_a_crash() -> None:
    # Each amount is finite, their sum is not (review 1 #3).
    rows = [("2026-08-01", "O1", "Ann", "A1", "Mug", "1", "1e308", "out"),
            ("2026-08-02", "O2", "Bo", "A1", "Mug", "1", "1e308", "out")]
    found = line_summary(read_csv_text(_raw(rows)).frame, _plan(answers=OrderConfirmations()))
    assert (found.summary, found.unavailable) == (None, TOO_LARGE)


def test_an_illegal_plan_is_refused_whatever_it_maps() -> None:
    # Quantity unmapped, and a date step on a number column: the preview
    # refuses it, and so does the summary - not "map a quantity" (review 1 #4).
    columns = [c if c[0] != "Qty" else ("Qty", "numeric_discrete", "ignore") for c in COLUMNS]
    plan = _plan(columns)
    plan.column_actions[5] = plan.column_actions[5].model_copy(update={"action": "parse_datetime", "params": {}})
    with pytest.raises(InvalidPlanError):
        line_summary(read_csv_text(_raw()).frame, plan)


def test_a_price_mapped_and_dropped_is_told_to_be_kept() -> None:
    plan = _plan()
    plan.column_actions[6] = plan.column_actions[6].model_copy(update={"action": "drop_column", "params": {}})
    found = line_summary(read_csv_text(_raw()).frame, plan)
    assert found.unavailable == NOT_CLASSED
    assert "keep both columns" in NOT_CLASSED


def test_the_summary_is_the_whole_files() -> None:
    found = line_summary(read_csv_text(_raw()).frame, _plan()).summary
    assert found is not None
    payload = found.model_dump(mode="json")
    payload["unmeasurable"][0]["scope"] = "current"
    with pytest.raises(ValueError, match="whole file"):
        LineSummary.model_validate(payload)


# --- review 2 (2E-t3) ----------------------------------------------------------------------


def test_too_large_is_said_exactly_when_metrics_json_refuses_the_figure(tmp_path) -> None:
    # Two undated sales of 1e308 are in no figure, and stock received of
    # +1e308 and -1e308 adds up by sign: Review shows them, as stage 2 does.
    # Two +1e308 receipts overflow their sign's sum: both refuse (review 2 #4).
    from pydantic import ValidationError

    from contracts.lines import TOO_LARGE_TO_ADD

    around = [("2026-07-01", "O0", "Ann", "A1", "Mug", "1", "10", "out"),
              ("2026-08-01", "O9", "Ann", "A1", "Mug", "2", "10", "out"),
              ("2026-09-01", "O8", "Ann", "A1", "Mug", "1", "10", "out")]
    undated = [("not a date", "O1", "Bo", "A1", "Mug", "1", "1e308", "out"),
               ("not a date", "O2", "Bo", "A1", "Mug", "1", "1e308", "out")]
    both_signs = [("2026-08-02", "O3", None, "A1", "Mug", "1", "1e308", "in"),
                  ("2026-08-03", "O4", None, "A1", "Mug", "-1", "1e308", "in")]
    one_sign = [("2026-08-02", "O3", None, "A1", "Mug", "1", "1e308", "in"),
                ("2026-08-03", "O4", None, "A1", "Mug", "1", "1e308", "in")]
    plan = _plan(answers=OrderConfirmations())
    for rows in (around + undated, around + both_signs):
        found = line_summary(read_csv_text(_raw(rows)).frame, plan)
        assert found.summary is not None and found.summary.identity.net_revenue == pytest.approx(40.0)
    assert line_summary(read_csv_text(_raw(around + one_sign)).frame, plan).unavailable == TOO_LARGE

    run_id = "0a000000-0000-4000-8000-0000000000e4"
    (tmp_path / run_id).mkdir()
    (tmp_path / run_id / "raw.csv").write_bytes(_raw(around + one_sign))
    execute_run(tmp_path, run_id, plan, now=NOW)
    with np.errstate(over="ignore"), pytest.raises(ValidationError, match=TOO_LARGE_TO_ADD):
        analyze_run(tmp_path, run_id, NOW)


def test_a_single_line() -> None:
    rows = [("2026-08-03", "O1", "Ann", "A1", "Mug", "2", "10", "out")]
    found = line_summary(read_csv_text(_raw(rows)).frame, _plan(answers=OrderConfirmations())).summary
    assert found is not None
    assert (found.lines, found.identity.net_revenue, found.identity.money_moved) == (1, 20.0, 20.0)
    assert [n.code for n in found.notes] == ["discounts_in_prices"]


def test_an_all_empty_column_and_nothing_moved() -> None:
    # Every price 0, every customer blank: nothing moved, so no share of it.
    rows = [("2026-08-03", "O1", None, "A1", "Mug", "2", "0", "out"),
            ("2026-08-04", "O2", None, "A1", "Mug", "1", "0", "out")]
    found = line_summary(read_csv_text(_raw(rows)).frame, _plan(answers=OrderConfirmations())).summary
    assert found is not None
    assert (found.identity.net_revenue, found.identity.money_moved) == (0.0, 0.0)
    assert (found.unclassified.lines, found.unclassified.share_of_money_moved) == (0, None)


# --- review 3 (2E-t3) ----------------------------------------------------------------------


def test_the_summary_equals_metrics_json_with_a_rename_and_a_transform(tmp_path) -> None:
    # The flag-only plan's check, under a trim of the customer column, rows
    # missing a price dropped (lines 12 and 14: a figure changes) and a source
    # column named line_class the run renames (review 3 #5). Every block
    # compared: a summary read before the plan ran passed on the trim alone
    # (2E-v #10).
    rows = [row[:2] + ((" " + row[2] + " ") if row[2] else row[2],) + row[3:] + ("mine",) for row in ROWS]
    names = [name for name, _, _ in COLUMNS] + ["line_class"]
    plan = _plan(COLUMNS + [("line_class", "text", "ignore")])
    plan.column_actions[2] = plan.column_actions[2].model_copy(update={"action": "trim_whitespace", "params": {}})
    plan.column_actions[6] = plan.column_actions[6].model_copy(update={"action": "drop_rows_missing", "params": {}})
    run_id = "0a000000-0000-4000-8000-0000000000e5"
    (tmp_path / run_id).mkdir()
    (tmp_path / run_id / "raw.csv").write_bytes(_raw(rows, names))
    execute_run(tmp_path, run_id, plan, now=NOW)
    core = analyze_run(tmp_path, run_id, NOW).core
    found = line_summary(read_csv_text(_raw(rows, names)).frame, plan)
    assert found.summary is not None and [r.source for r in found.reserved_renames] == ["line_class"]
    assert (found.summary.lines, found.summary.undated_lines) == (15, core.undated_lines)
    assert found.summary.outside_revenue == [r for r in core.outside_revenue if r.scope == "file"]
    assert found.summary.unmeasurable == [r for r in core.unmeasurable if r.scope == "file"]
    assert found.summary.unclassified == core.unclassified
    assert [n.model_copy(update={"measures": [m for m in n.measures if m.scope == "file"]}) for n in core.notes] \
        == found.summary.notes
    assert sum(m.revenue for m in core.revenue_by_month) == pytest.approx(found.summary.identity.net_revenue)


def test_metrics_json_says_what_the_whole_file_still_counts_of_an_undated_line() -> None:
    # Review 3 #3: an undated line is in no month; one outside revenue is still
    # in the whole file's report of such lines.
    from stages.analyze.assemble import assemble_metrics

    rows = [("2026-07-01", "O1", "Ann", "A1", "Mug", "1", "10", "out"),
            ("not a date", "O2", "Ann", "A1", "Mug", "1", "10", "out"),
            ("2026-09-01", "O3", "Ann", "A1", "Mug", "1", "10", "out")]
    frame = pd.DataFrame(rows, columns=[name for name, _, _ in COLUMNS])
    core = assemble_metrics(frame, {n: f for n, _, f in COLUMNS}, NOW).core
    assert core.undated_lines == 1
    assert core.undated_lines_reason is not None and core.undated_lines_reason.endswith(
        "left out of every month's figures (one outside revenue is still in the whole file's report of such lines)")
