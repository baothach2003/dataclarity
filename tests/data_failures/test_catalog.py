"""The conformance suite, part 4: the catalog (docs/DATA_FAILURE_MODES.md)
and the suite kept in step - every row has its case, a reference or a
stated reason for none; every test a row cites exists; the list of modes
with no test before 2E-u is the rows that cite none; the generator cannot
see the engine."""

import ast
from pathlib import Path

import pytest

from tests.data_failures.dirty import SAMPLES
from tests.data_failures.flow import ROOT

CATALOG = ROOT / "docs" / "DATA_FAILURE_MODES.md"
HERE = Path(__file__).parent

# Covered at the request or at the AI step: the existing test is the case.
REFERENCED = {
    "DF-A1": "tests/backend/test_upload_service.py::test_rejects_one_byte_over_the_limit_and_removes_the_run",
    "DF-A2": "tests/backend/test_upload_service.py::test_rejects_other_extensions_without_creating_a_run",
    "DF-A11": "tests/backend/test_api_analyze.py::test_not_inventory_run_is_analysis_failed",
    "DF-A16": "tests/stages/ingest/test_2et1_execute.py::test_the_rename_is_numbered_when_the_suffixed_name_is_taken",
}
# No sample, each for the reason its row states.
NO_CASE = {"DF-E10", "DF-E12", "DF-F6", "DF-G12"}


def _rows() -> dict[str, str]:
    """The catalog's rows: id -> its "Covered by" cell."""
    rows = {}
    for line in CATALOG.read_text(encoding="utf-8").splitlines():
        cells = [cell.strip() for cell in line.split("|")]
        if len(cells) > 2 and cells[1].startswith("DF-"):
            rows[cells[1].upper()] = cells[-2]
    return rows


def _defined(path: Path) -> set[str]:
    return {n.name for n in ast.walk(ast.parse(path.read_text(encoding="utf-8"))) if isinstance(n, ast.FunctionDef)}


@pytest.mark.parametrize("mode,node", sorted(REFERENCED.items()))
def test_a_referenced_mode_names_a_test_that_exists(mode: str, node: str) -> None:
    path, name = node.split("::")
    assert name in _defined(ROOT / path), mode


def test_every_catalog_row_has_its_case_and_every_case_its_row() -> None:
    assert set(_rows()) == set(SAMPLES) | set(REFERENCED) | NO_CASE
    assert not set(SAMPLES) & (set(REFERENCED) | NO_CASE)


def test_every_sample_is_checked_by_a_case() -> None:
    source = "".join(path.read_text(encoding="utf-8") for path in HERE.glob("test_conformance*.py"))
    assert [mode for mode in SAMPLES if f'"{mode}"' not in source] == []


def test_every_test_the_catalog_cites_exists() -> None:
    for mode, cell in _rows().items():
        for reference in (part.strip() for part in cell.split(", ")):
            if not reference.startswith(("backend/", "shared/", "stages/", "scenarios/")):
                continue
            path, _, name = reference.partition("::")
            file = ROOT / "tests" / path.split(" ")[0]
            assert file.exists(), (mode, path)
            if name:
                assert name.split(" ")[0] in _defined(file), (mode, name)


def test_the_list_of_modes_with_no_earlier_test_is_the_rows_citing_none() -> None:
    text = CATALOG.read_text(encoding="utf-8")
    listed = text.split("## Modes with no test before 2E-u", 1)[1].split(" - each", 1)[0]
    named = {part.strip().strip(",").upper() for part in listed.replace("\n", " ").split(", ") if part.strip()}
    assert named == {mode for mode, cell in _rows().items() if cell == "-"}


GENERATOR = ("dirty.py", "dirty_base.py", "dirty_files_dates.py", "dirty_amounts_lines.py", "dirty_people_coverage.py")
LIBRARIES = {"calendar", "collections", "csv", "dataclasses", "datetime", "io", "types"}
OWN = {"tests.data_failures", "tests.data_failures.dirty_base", "tests.data_failures.dirty_files_dates",
       "tests.data_failures.dirty_amounts_lines", "tests.data_failures.dirty_people_coverage"}
DYNAMIC = {"exec", "eval", "compile", "__import__", "getattr", "open", "__builtins__"}
READERS = {"import_module", "read_json", "read_csv", "read_text", "read_bytes", "read_parquet", "read_excel"}


@pytest.mark.parametrize("module", GENERATOR)
def test_the_generator_cannot_see_the_engine(module: str) -> None:
    # As 3E2's store (tests/scenarios/test_store.py): every import, and the
    # dynamic routes a parse knows.
    names: set[str] = set()
    for node in ast.walk(ast.parse((HERE / module).read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names |= {alias.name for alias in node.names}
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0 and node.module, "no relative import"
            names.add(node.module)
        elif isinstance(node, ast.Name) and node.id in DYNAMIC:
            names.add(node.id)
        elif isinstance(node, ast.Attribute) and node.attr in READERS:
            names.add(node.attr)
    assert {name for name in names if name.split(".")[0] not in LIBRARIES and name not in OWN} == set()
