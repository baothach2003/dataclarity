"""Executing a plan on the whole file (stages/ingest/cleaning.execute_run,
docs/SPECS.md section 5, docs/CONTRACTS.md section 5)."""

import json
from pathlib import Path

import pytest

from contracts import CleaningPlanContract, CleaningReportContract
from stages.ingest import contract_files, transforms
from stages.ingest.cleaning import CleaningError, execute_run
from stages.ingest.plan_validation import InvalidPlanError
from tests.stages.ingest.cleaning_fixtures import (
    NOW,
    RAW_CSV,
    column_action,
    dataset_action,
    make_plan,
    raw_run,
)

OUTPUTS = ("cleaned.csv", "plan_final.json", "cleaning_report.json")
DEDUPLICATING = make_plan(dataset_actions=[dataset_action("remove_exact_duplicates")])


def written(root: Path, run_id: str) -> dict[str, bytes]:
    return {n: (root / run_id / n).read_bytes() for n in OUTPUTS if (root / run_id / n).exists()}


def edited(plan: CleaningPlanContract, name: str, **changes: object) -> CleaningPlanContract:
    columns = [{**a.model_dump(), **changes} if a.source_name == name else a.model_dump()
               for a in plan.column_actions]
    return CleaningPlanContract.model_validate({
        **plan.model_dump(), "source": "user_edited", "column_actions": columns})


# --- what is written -----------------------------------------------------------------------


def test_writes_the_cleaned_file_the_plan_and_the_report(tmp_path: Path) -> None:
    run_id = raw_run(tmp_path)

    report = execute_run(tmp_path, run_id, DEDUPLICATING, now=NOW)

    files = written(tmp_path, run_id)
    assert sorted(files) == sorted(OUTPUTS)
    assert files["cleaned.csv"].decode() == (
        "sku,name,qty,price,day,__flag_invalid_date__day,__flag_negative__qty\n"
        "A1,Mug,3,9.99,2024-01-05,False,False\n"
        "B2,Cup,-1,9.99,2024-01-15,False,True\n"
        "C3,,5,12.50,2024-01-07,False,False\n"
        "D4,Plate,4,7.00,,True,False\n")
    assert CleaningReportContract.model_validate_json(files["cleaning_report.json"]) == report


def test_the_report_holds_what_ran_in_the_order_it_ran(tmp_path: Path) -> None:
    run_id = raw_run(tmp_path)

    report = execute_run(tmp_path, run_id, DEDUPLICATING, now=NOW)

    assert (report.schema_version, report.generated_at) == ("1.0", NOW)
    assert (report.rows_in, report.rows_out) == (5, 4)
    # 5 source columns, plus the two flag columns the run added.
    assert (report.columns_in, report.columns_out) == (5, 7)
    assert [(c.action, c.column) for c in report.changes] == [
        ("remove_exact_duplicates", None), ("trim_whitespace", "sku"), ("trim_whitespace", "name"),
        ("parse_datetime", "day"), ("impute_median", "price"), ("fix_negative", "qty")]
    assert report.warnings == []


def test_the_column_mapping_names_the_columns_later_stages_need(tmp_path: Path) -> None:
    run_id = raw_run(tmp_path)
    plan = edited(edited(DEDUPLICATING, "sku", canonical_field="ignore"),
                  "price", action="drop_column", params={})

    report = execute_run(tmp_path, run_id, plan, now=NOW)

    # An ignored column is not in the mapping, and neither is one that was dropped
    # (cleaned.csv no longer has it).
    assert report.column_mapping == {
        "name": "product_name", "qty": "quantity", "day": "transaction_date"}


def test_the_plan_that_ran_is_recorded_as_plan_final(tmp_path: Path) -> None:
    run_id = raw_run(tmp_path)

    execute_run(tmp_path, run_id, DEDUPLICATING, now=NOW)

    on_disk = CleaningPlanContract.model_validate_json(
        (tmp_path / run_id / "plan_final.json").read_bytes())
    assert on_disk == DEDUPLICATING


def test_a_file_that_was_not_utf8_is_warned_about(tmp_path: Path) -> None:
    latin = b"sku,name,qty,price,day\nA1,Caf\xe9,3,9.99,2024-01-05\n"
    run_id = raw_run(tmp_path, latin)

    report = execute_run(tmp_path, run_id, make_plan(), now=NOW)

    assert [(w.code, w.detail) for w in report.warnings] == [
        ("encoding_fallback", "file decoded as latin-1")]
    # The output is UTF-8 whatever the input was.
    assert "Café" in (tmp_path / run_id / "cleaned.csv").read_bytes().decode("utf-8")


def test_a_utf8_file_gets_no_encoding_warning(tmp_path: Path) -> None:
    run_id = raw_run(tmp_path, "sku,name,qty,price,day\nA1,Café,3,9.99,2024-01-05\n".encode())

    assert execute_run(tmp_path, run_id, make_plan(), now=NOW).warnings == []


# --- the same plan on the same file gives the same result --------------------------------------------


def test_running_it_twice_gives_byte_identical_files(tmp_path: Path) -> None:
    run_id = raw_run(tmp_path)

    execute_run(tmp_path, run_id, DEDUPLICATING, now=NOW)
    first = written(tmp_path, run_id)
    execute_run(tmp_path, run_id, DEDUPLICATING, now=NOW)

    assert written(tmp_path, run_id) == first


def test_another_run_of_the_same_file_and_plan_gives_the_same_cleaned_file(tmp_path: Path) -> None:
    one, two = raw_run(tmp_path), raw_run(tmp_path)

    execute_run(tmp_path, one, DEDUPLICATING, now=NOW)
    execute_run(tmp_path, two, DEDUPLICATING, now=NOW)

    assert written(tmp_path, one) == written(tmp_path, two)


def test_the_raw_file_is_never_touched(tmp_path: Path) -> None:
    run_id = raw_run(tmp_path)

    execute_run(tmp_path, run_id, DEDUPLICATING, now=NOW)

    assert (tmp_path / run_id / "raw.csv").read_bytes() == RAW_CSV


# --- the plan is checked again, whoever wrote it ---------------------------------------------------------


def test_an_edit_that_makes_the_plan_illegal_is_rejected_although_the_proposal_was_legal(
    tmp_path: Path,
) -> None:
    proposal = make_plan(source="ai")
    run_id = raw_run(tmp_path)
    execute_run(tmp_path, raw_run(tmp_path), proposal, now=NOW)  # the proposal itself runs

    with pytest.raises(InvalidPlanError) as caught:
        execute_run(tmp_path, run_id, edited(proposal, "qty", action="impute_mean", params={}), now=NOW)

    assert any("impute_mean is not legal for quantity" in p for p in caught.value.problems)
    assert written(tmp_path, run_id) == {}  # nothing ran, nothing was written


def test_execution_needs_the_required_fields_mapped_and_kept(tmp_path: Path) -> None:
    run_id = raw_run(tmp_path)

    with pytest.raises(InvalidPlanError, match="mapped to the required field quantity"):
        execute_run(tmp_path, run_id, edited(make_plan(), "qty", action="drop_column", params={}))

    assert written(tmp_path, run_id) == {}


def test_a_plan_for_other_columns_is_rejected_against_the_real_file(tmp_path: Path) -> None:
    run_id = raw_run(tmp_path, b"sku,name,qty,price\nA1,Mug,3,9.99\n")  # no `day` column

    with pytest.raises(InvalidPlanError, match="columns missing from the plan|columns not in the file"):
        execute_run(tmp_path, run_id, make_plan())


# --- nothing half-written -------------------------------------------------------------------------------------


def test_a_missing_raw_file_is_a_clear_error(tmp_path: Path) -> None:
    run_id = raw_run(tmp_path)
    (tmp_path / run_id / "raw.csv").unlink()

    with pytest.raises(FileNotFoundError, match="raw.csv"):
        execute_run(tmp_path, run_id, make_plan())


def test_a_transform_that_fails_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_id = raw_run(tmp_path)

    def boom(*args: object) -> object:
        raise ValueError("cannot flag this")

    monkeypatch.setitem(transforms.ACTIONS, "fix_negative", boom)

    with pytest.raises(CleaningError, match="fix_negative on column 'qty' failed"):
        execute_run(tmp_path, run_id, make_plan())

    assert list((tmp_path / run_id).glob("*")) == [
        tmp_path / run_id / "profile.json", tmp_path / run_id / "raw.csv"]


def test_a_failed_rerun_leaves_the_earlier_result_exactly_as_it_was(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_id = raw_run(tmp_path)
    execute_run(tmp_path, run_id, DEDUPLICATING, now=NOW)
    before = written(tmp_path, run_id)
    monkeypatch.setitem(transforms.ACTIONS, "fix_negative", lambda *a: (_ for _ in ()).throw(ValueError("x")))

    with pytest.raises(CleaningError):
        execute_run(tmp_path, run_id, DEDUPLICATING, now=NOW)

    assert written(tmp_path, run_id) == before


def test_a_failure_while_writing_leaves_no_cleaned_file_and_no_temp_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_id = raw_run(tmp_path)
    real, calls = contract_files.tempfile.mkstemp, []

    def full_disk(*args: object, **kwargs: object) -> tuple[int, str]:
        calls.append(1)
        if len(calls) == 3:  # the report, the last of the three
            raise OSError("no space left on device")
        return real(*args, **kwargs)  # type: ignore[arg-type]  # forwarding mkstemp's own arguments

    monkeypatch.setattr(contract_files.tempfile, "mkstemp", full_disk)

    with pytest.raises(OSError, match="no space left"):
        execute_run(tmp_path, run_id, make_plan())

    assert sorted(p.name for p in (tmp_path / run_id).iterdir()) == ["profile.json", "raw.csv"]


def test_a_plan_that_leaves_no_rows_is_refused_and_writes_nothing(tmp_path: Path) -> None:
    run_id = raw_run(tmp_path, b"sku,name,qty,price,day\nA1,,3,9.99,2024-01-05\nB2,,4,1.00,2024-01-06\n")
    plan = make_plan([column_action("sku"), column_action("name", "drop_rows_missing"),
                      column_action("qty"), column_action("price"), column_action("day")])

    with pytest.raises(CleaningError, match="removes every row"):
        execute_run(tmp_path, run_id, plan)

    assert written(tmp_path, run_id) == {}


def test_the_files_are_plain_utf8_json_and_csv(tmp_path: Path) -> None:
    run_id = raw_run(tmp_path)
    execute_run(tmp_path, run_id, DEDUPLICATING, now=NOW)

    report = json.loads((tmp_path / run_id / "cleaning_report.json").read_text(encoding="utf-8"))

    assert set(report) == {"schema_version", "generated_at", "rows_in", "rows_out", "columns_in",
                           "columns_out", "changes", "warnings", "column_mapping"}


# --- cells that read back as missing (1F review) ---------------------------------------------


def named_run(tmp_path: Path, name_cells: list[str]) -> str:
    lines = ["sku,name,qty,price,day"] + [
        f"A{i},{cell},{i},1.00,2024-01-05" for i, cell in enumerate(name_cells)]
    return raw_run(tmp_path, ("\n".join(lines) + "\n").encode())


def test_text_that_reads_back_as_missing_is_counted_in_the_report(tmp_path: Path) -> None:
    # " N/A " is text in raw.csv (only the exact token is missing); trimmed it is "N/A",
    # and "   " becomes an empty cell. Both are gaps the next time the file is read.
    run_id = named_run(tmp_path, [" N/A ", "   ", "Mug", "Cup"])

    report = execute_run(tmp_path, run_id, make_plan(), now=NOW)

    warning = next(w for w in report.warnings if w.code == "text_reads_as_missing")
    assert warning.detail.startswith("2 cells hold text that reads back as missing")
    assert "name" in warning.detail


def test_no_such_warning_when_no_text_reads_back_as_missing(tmp_path: Path) -> None:
    run_id = named_run(tmp_path, ["Mug", "Cup"])

    assert execute_run(tmp_path, run_id, make_plan(), now=NOW).warnings == []


def test_a_cell_that_is_already_missing_is_not_counted(tmp_path: Path) -> None:
    run_id = named_run(tmp_path, ["", "Mug"])  # an empty cell is missing in the raw file too

    assert execute_run(tmp_path, run_id, make_plan(), now=NOW).warnings == []


# --- a trailing delimiter no longer shifts the data (1F review, HIGH) ----------------------------


def trailing_comma_run(tmp_path: Path) -> str:
    lines = ["sku,name,qty,price,day"] + [f"A{i},Mug{i},{i},1.00,2024-01-05," for i in range(40)]
    return raw_run(tmp_path, ("\n".join(lines) + "\n").encode())


def test_execute_keeps_the_names_when_every_row_ends_with_a_delimiter(tmp_path: Path) -> None:
    run_id = trailing_comma_run(tmp_path)

    report = execute_run(tmp_path, run_id, make_plan(), now=NOW)

    lines = (tmp_path / run_id / "cleaned.csv").read_text(encoding="utf-8").splitlines()
    assert lines[0] == "sku,name,qty,price,day"
    assert lines[1] == "A0,Mug0,0,1.00,2024-01-05"
    assert (report.rows_in, report.columns_in) == (40, 5)


def test_preview_works_on_the_same_file_and_numbers_its_rows(tmp_path: Path) -> None:
    from stages.ingest.preview import preview_run

    run_id = trailing_comma_run(tmp_path)

    result = preview_run(tmp_path, run_id, make_plan())

    assert result.rows_in_file == 40 and result.rows[0].row == 1
    assert result.rows[0].before["name"] == "Mug0"


# --- a file that is not inventory data (1G): generic cleaning has no required fields ------------


def unmapped(plan: CleaningPlanContract) -> CleaningPlanContract:
    """The plan of a file that is not inventory data: nothing maps to a canonical field."""
    columns = [{**a.model_dump(), "canonical_field": "ignore"} for a in plan.column_actions]
    return CleaningPlanContract.model_validate({**plan.model_dump(), "column_actions": columns})


def test_a_plan_that_maps_no_required_field_is_refused_by_default(tmp_path: Path) -> None:
    run_id = raw_run(tmp_path)

    with pytest.raises(InvalidPlanError, match="required field product_name is not mapped"):
        execute_run(tmp_path, run_id, unmapped(make_plan()))

    assert written(tmp_path, run_id) == {}


def test_generic_cleaning_runs_without_the_required_fields_when_asked(tmp_path: Path) -> None:
    run_id = raw_run(tmp_path)

    report = execute_run(tmp_path, run_id, unmapped(DEDUPLICATING),
                         now=NOW, require_required_fields=False)

    assert sorted(written(tmp_path, run_id)) == sorted(OUTPUTS)
    assert report.rows_out == 4  # the same result as the mapped plan: only the guard is waived
    assert report.column_mapping == {}  # nothing maps, so later stages find nothing to read


def test_waiving_the_required_fields_does_not_waive_the_other_plan_rules(tmp_path: Path) -> None:
    run_id = raw_run(tmp_path)
    illegal = edited(unmapped(make_plan()), "price", action="normalize_case", params={"case": "lower"})

    with pytest.raises(InvalidPlanError, match="normalize_case is not legal"):
        execute_run(tmp_path, run_id, illegal, require_required_fields=False)

    assert written(tmp_path, run_id) == {}
