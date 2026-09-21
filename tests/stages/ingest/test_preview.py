"""The before/after preview (stages/ingest/preview.py, docs/SPECS.md section 4.2 C
and section 8): a bounded sample, the same engine as execute, 20 rows chosen to
include the affected ones, and per-column deltas."""

from collections.abc import Collection
from io import StringIO
from pathlib import Path

import pandas as pd
import pytest

from stages.ingest import transforms
from stages.ingest.cleaning import CleaningError, execute_run
from stages.ingest.plan_validation import InvalidPlanError
from stages.ingest.preview import (
    MAX_CELL_CHARS,
    PREVIEW_ROWS,
    PREVIEW_SAMPLE_MAX,
    preview_frame,
    preview_run,
    select_sample,
)
from stages.ingest.profiling import read_csv_text
from tests.stages.ingest.cleaning_fixtures import (
    NOW,
    RAW_CSV,
    column_action,
    dataset_action,
    make_plan,
    raw_run,
)

DEDUPLICATING = make_plan(dataset_actions=[dataset_action("remove_exact_duplicates")])


def frame_of(csv: bytes = RAW_CSV) -> pd.DataFrame:
    return read_csv_text(csv).frame


def big_csv(rows: int = 5000, missing_name_at: tuple[int, ...] = (1233, 4320)) -> bytes:
    lines = ["sku,name,qty,price,day"]
    for i in range(rows):
        name = "" if i in missing_name_at else f"Item {i}"
        lines.append(f"S{i},{name},{1 + i % 9},{1 + i % 50}.50,2024-01-{1 + i % 28:02d}")
    return ("\n".join(lines) + "\n").encode()


NOOP = make_plan([column_action(n) for n in ("sku", "name", "qty", "price", "day")])


# --- a small file is previewed whole, and the numbers are right --------------------------


def test_a_small_file_is_previewed_whole() -> None:
    result = preview_frame(frame_of(), DEDUPLICATING)

    assert (result.rows_in_file, result.sample_rows, result.sampled, result.rows_after) == (5, 5, False, 4)
    assert [r.row for r in result.rows] == [1, 2, 3, 4, 5]  # 5 rows, well under 20


def test_each_row_shows_before_after_and_which_cells_changed() -> None:
    rows = {r.row: r for r in preview_frame(frame_of(), DEDUPLICATING).rows}

    assert rows[1].before["name"] == " Mug " and rows[1].after is not None
    assert rows[1].after["name"] == "Mug"
    assert rows[1].changed == ["name"]
    # Row 2: the price is filled with the median, the date is parsed, the negative
    # quantity is flagged (the quantity itself stays).
    assert rows[2].before["price"] is None and rows[2].after is not None
    assert (rows[2].after["price"], rows[2].after["day"]) == ("9.99", "2024-01-15")
    assert rows[2].after["__flag_negative__qty"] == "True"
    assert rows[2].changed == ["price", "day", "__flag_negative__qty"]
    # Row 3 is a copy of row 1 and is dropped.
    assert rows[3].after is None and rows[3].changed == []
    # Row 4 needs nothing: a missing name stays missing.
    assert rows[4].before["name"] is None and rows[4].changed == []
    # Row 5's date is not a date: empty, and flagged.
    assert rows[5].after is not None and rows[5].after["day"] is None
    assert rows[5].changed == ["day", "__flag_invalid_date__day"]


def test_deltas_compare_missing_share_and_distinct_values_before_and_after() -> None:
    deltas = {d.column: d for d in preview_frame(frame_of(), DEDUPLICATING).deltas}

    assert (deltas["name"].null_pct_before, deltas["name"].null_pct_after) == (20.0, 25.0)  # 1 of 5, 1 of 4
    assert (deltas["name"].unique_before, deltas["name"].unique_after) == (3, 3)
    assert (deltas["price"].null_pct_before, deltas["price"].null_pct_after) == (20.0, 0.0)
    assert (deltas["day"].null_pct_before, deltas["day"].null_pct_after) == (0.0, 25.0)
    assert (deltas["day"].unique_before, deltas["day"].unique_after) == (4, 3)
    assert (deltas["sku"].unique_before, deltas["sku"].unique_after) == (4, 4)


def test_a_flag_column_the_run_adds_has_no_before() -> None:
    deltas = {d.column: d for d in preview_frame(frame_of(), DEDUPLICATING).deltas}

    flag = deltas["__flag_negative__qty"]
    assert (flag.null_pct_before, flag.unique_before) == (None, None)
    assert (flag.null_pct_after, flag.unique_after) == (0.0, 2)  # False and True


def test_a_dropped_column_has_no_after() -> None:
    plan = make_plan([column_action("sku"), column_action("name"), column_action("qty"),
                      column_action("price", "drop_column"), column_action("day")])

    deltas = {d.column: d for d in preview_frame(frame_of(), plan).deltas}

    assert (deltas["price"].null_pct_after, deltas["price"].unique_after) == (None, None)
    assert deltas["price"].unique_before == 3
    assert "price" not in preview_frame(frame_of(), plan).columns_after


def test_the_deltas_follow_the_columns_in_order_and_then_the_new_ones() -> None:
    columns = [d.column for d in preview_frame(frame_of(), DEDUPLICATING).deltas]

    assert columns == ["sku", "name", "qty", "price", "day",
                       "__flag_invalid_date__day", "__flag_negative__qty"]


# --- the preview is the execution, on fewer rows --------------------------------------------------


def test_for_a_file_of_500_rows_or_fewer_the_preview_is_exactly_what_execute_writes(
    tmp_path: Path,
) -> None:
    run_id = raw_run(tmp_path)
    preview = preview_frame(frame_of(), DEDUPLICATING)
    execute_run(tmp_path, run_id, DEDUPLICATING, now=NOW)
    written = pd.read_csv(tmp_path / run_id / "cleaned.csv", dtype=str, keep_default_na=False)

    kept = [r for r in preview.rows if r.after is not None]
    assert len(kept) == len(written) == preview.rows_after
    for shown, saved in zip(kept, written.to_dict("records"), strict=True):
        assert shown.after == {name: (value or None) for name, value in saved.items()}


def test_the_same_plan_gives_the_same_preview_every_time() -> None:
    first = preview_frame(frame_of(big_csv()), DEDUPLICATING)

    assert preview_frame(frame_of(big_csv()), DEDUPLICATING) == first


# --- a large file is sampled, and the sample is not head() ------------------------------------------


def test_a_large_file_is_previewed_on_at_most_500_rows() -> None:
    result = preview_frame(frame_of(big_csv()), NOOP)

    assert (result.rows_in_file, result.sample_rows, result.sampled) == (5000, PREVIEW_SAMPLE_MAX, True)


def test_the_rows_the_plan_affects_are_shown_even_when_they_are_far_from_the_top() -> None:
    plan = make_plan([column_action("sku"), column_action("name", "drop_rows_missing"),
                      column_action("qty"), column_action("price"), column_action("day")])

    result = preview_frame(frame_of(big_csv()), plan)

    shown = {r.row: r for r in result.rows}
    # The two rows with no name are rows 1234 and 4321: nowhere near head().
    assert shown[1234].after is None and shown[4321].after is None
    assert len(result.rows) == PREVIEW_ROWS
    assert result.rows_after == PREVIEW_SAMPLE_MAX - 2


def test_the_sample_is_sorted_bounded_and_spans_the_whole_file() -> None:
    sample = select_sample(frame_of(big_csv()), 500)

    assert len(sample) == 500
    assert sample.index.is_monotonic_increasing and sample.index.is_unique
    assert sample.index[0] == 0 and sample.index[-1] == 4999


def test_a_file_within_the_limit_is_the_whole_sample() -> None:
    frame = frame_of()

    assert select_sample(frame, 500).index.tolist() == frame.index.tolist()


def test_problem_rows_are_taken_from_the_sample_window_not_only_evenly_spaced_rows() -> None:
    # Row 1235 of 5000 is not on the even grid (a multiple of 10 apart), but its
    # missing name is a problem row.
    sample = select_sample(frame_of(big_csv(missing_name_at=(1234,))), 500)

    assert 1234 in sample.index


# --- which 20 rows are shown --------------------------------------------------------------------------------


def test_every_kind_of_effect_is_shown_before_any_repeats() -> None:
    # 100 rows all change in `name` (padding); only row 90 is dropped (no price).
    lines = ["sku,name,qty,price,day"] + [
        f"S{i}, x ,1,{'' if i == 89 else '1.00'},2024-01-05" for i in range(100)]
    plan = make_plan([column_action("sku"), column_action("name", "trim_whitespace"),
                      column_action("qty"), column_action("price", "drop_rows_missing"),
                      column_action("day")])

    result = preview_frame(frame_of(("\n".join(lines) + "\n").encode()), plan)

    shown = [r.row for r in result.rows]
    assert len(shown) == PREVIEW_ROWS
    assert 90 in shown and 1 in shown  # the drop and the first padded name, whatever follows
    assert shown == sorted(shown)


def test_when_nothing_changes_the_rows_shown_are_spread_over_the_file_not_the_top_20() -> None:
    lines = ["sku,name,qty,price,day"] + [f"S{i},Item,1,1.00,2024-01-05" for i in range(100)]

    result = preview_frame(frame_of(("\n".join(lines) + "\n").encode()), NOOP)

    shown = [r.row for r in result.rows]
    assert len(shown) == PREVIEW_ROWS and shown[0] == 1 and shown[-1] == 100
    assert {b - a for a, b in zip(shown, shown[1:], strict=False)} <= {5, 6}


def test_a_very_long_cell_is_cut_for_display_but_a_change_in_it_is_still_seen() -> None:
    long_cell = "x" * 500
    frame = frame_of(f"sku,name,qty,price,day\nA1, {long_cell} ,1,1.00,2024-01-05\n".encode())
    plan = make_plan([column_action("sku"), column_action("name", "trim_whitespace"),
                      column_action("qty"), column_action("price"), column_action("day")])

    shown = preview_frame(frame, plan).rows[0]

    assert shown.after is not None and len(shown.after["name"] or "") == MAX_CELL_CHARS
    assert len(shown.before["name"] or "") == MAX_CELL_CHARS
    assert shown.changed == ["name"]  # only the padding differs, beyond the cut


# --- what preview_run adds: the file, the checks, no side effects ---------------------------------------------


def test_preview_run_reads_the_raw_file_and_writes_nothing(tmp_path: Path) -> None:
    run_id = raw_run(tmp_path)
    before = sorted(p.name for p in (tmp_path / run_id).iterdir())

    result = preview_run(tmp_path, run_id, DEDUPLICATING)

    assert result.rows_in_file == 5
    assert sorted(p.name for p in (tmp_path / run_id).iterdir()) == before
    assert (tmp_path / run_id / "raw.csv").read_bytes() == RAW_CSV


def test_an_illegal_edit_is_rejected_by_the_preview_too(tmp_path: Path) -> None:
    run_id = raw_run(tmp_path)
    plan = make_plan([column_action("sku"), column_action("name"),
                      column_action("qty", "impute_median"), column_action("price"),
                      column_action("day")])

    with pytest.raises(InvalidPlanError, match="impute_median is not legal for quantity"):
        preview_run(tmp_path, run_id, plan)


def test_the_preview_does_not_need_the_required_fields_mapped_yet(tmp_path: Path) -> None:
    # The preview refreshes on every edit, including while the user maps columns.
    run_id = raw_run(tmp_path)
    plan = make_plan([column_action("sku"), column_action("name"),
                      column_action("qty", canonical_field="ignore"), column_action("price"),
                      column_action("day")])

    assert preview_run(tmp_path, run_id, plan).rows_in_file == 5


def test_a_failure_on_the_data_is_reported_like_in_execute(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_id = raw_run(tmp_path)
    monkeypatch.setitem(transforms.ACTIONS, "fix_negative",
                        lambda *a: (_ for _ in ()).throw(ValueError("nope")))

    with pytest.raises(CleaningError, match="fix_negative on column 'qty' failed"):
        preview_run(tmp_path, run_id, make_plan())


def test_a_missing_raw_file_is_a_clear_error(tmp_path: Path) -> None:
    run_id = raw_run(tmp_path)
    (tmp_path / run_id / "raw.csv").unlink()

    with pytest.raises(FileNotFoundError, match="raw.csv"):
        preview_run(tmp_path, run_id, make_plan())


def test_a_plan_that_leaves_no_rows_in_the_sample_still_previews() -> None:
    # Unlike execute (which refuses), the preview shows the user what they are about
    # to do: every row dropped.
    lines = "sku,name,qty,price,day\nA1,,1,1.00,2024-01-05\nB2,,2,2.00,2024-01-06\n"
    plan = make_plan([column_action("sku"), column_action("name", "drop_rows_missing"),
                      column_action("qty"), column_action("price"), column_action("day")])

    result = preview_frame(frame_of(lines.encode()), plan)

    assert result.rows_after == 0 and all(r.after is None for r in result.rows)
    assert all(d.null_pct_after is None for d in result.deltas)


# --- wide files: the search for problem rows is bounded by cells, not only by rows (1F review) ---


def test_the_problem_row_search_reads_fewer_rows_when_the_file_is_wide(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Reading 50,000 rows of 400 columns took 11 s; the budget is cells.
    from stages.ingest import problem_rows
    from stages.ingest.preview import PROBLEM_CELL_BUDGET

    seen: list[int] = []
    real = problem_rows.problem_masks

    def spy(frame: pd.DataFrame, numeric: Collection[str]) -> list[pd.Series]:
        seen.append(len(frame))
        return real(frame, numeric)

    monkeypatch.setattr(problem_rows, "problem_masks", spy)
    wide = pd.DataFrame({f"c{i}": ["x"] * 12_000 for i in range(200)}, dtype="str")

    select_sample(wide, 500)

    assert seen == [PROBLEM_CELL_BUDGET // 200] == [10_000]  # 10,000 rows of 200 columns, not 50,000


def test_a_narrow_file_still_searches_the_whole_window(monkeypatch: pytest.MonkeyPatch) -> None:
    from stages.ingest import problem_rows
    from stages.ingest.preview import PROBLEM_WINDOW

    seen: list[int] = []
    real = problem_rows.problem_masks

    def spy(frame: pd.DataFrame, numeric: Collection[str]) -> list[pd.Series]:
        seen.append(len(frame))
        return real(frame, numeric)

    monkeypatch.setattr(problem_rows, "problem_masks", spy)

    select_sample(pd.DataFrame({"a": ["x"] * (PROBLEM_WINDOW + 10)}, dtype="str"), 500)

    assert seen == [PROBLEM_WINDOW]


def test_the_search_window_never_shrinks_below_the_sample() -> None:
    # 5,000 columns would leave a window of 400 rows: fewer than the sample asked for.
    from stages.ingest.preview import search_window

    assert search_window(columns=5000, limit=500) == 500


def test_a_tiny_limit_does_not_divide_by_zero() -> None:
    frame = frame_of(big_csv(missing_name_at=(10,)))

    assert len(select_sample(frame, 2)) == 2 and select_sample(frame, 2).index[-1] == 4999
    assert len(select_sample(frame, 3)) == 3
