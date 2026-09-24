"""The catalog has ONE home, and the live document must say the same thing.

`stages/diagnose/catalog.py` defines every hypothesis as data. This test reads
the two tables in `docs/AI_PIPELINE.md` section 7.8 and compares them with the
code cell by cell, so a rule edited in one place and not the other fails the
build - the drift that happened twice in Phase 3 (C2's sign in 3C, T3 in 3D5b)
becomes impossible to ship rather than something to notice by eye.
"""

import re
from pathlib import Path

import pytest

from stages.diagnose.catalog import BY_ID, CATALOG, NOT_TESTABLE

DOC = Path(__file__).resolve().parents[3] / "docs" / "AI_PIPELINE.md"


def _section_78() -> str:
    text = DOC.read_text(encoding="utf-8")
    start = text.index("### 7.8 Step 7: Hypothesis evaluation")
    end = text.index("### 7.9 ", start)
    return text[start:end]


def _rows(prefix: str) -> list[list[str]]:
    rows = []
    for line in _section_78().splitlines():
        if re.match(rf"^\|\s*{prefix}\d+\s*\|", line):
            rows.append([cell.strip() for cell in line.strip().strip("|").split("|")])
    return rows


def test_the_document_table_matches_the_catalog_row_by_row() -> None:
    doc = [tuple(row) for row in _rows("[DTCBPR]")]
    code = [(spec.id, spec.family, spec.lens, spec.kind, spec.statement,
             "-" if spec.rendered is None
             else f"fall: {spec.rendered[0]}; rise: {spec.rendered[1]}",
             spec.test, spec.requires) for spec in CATALOG]

    assert len(doc) == len(code), f"doc has {len(doc)} rows, catalog {len(code)}"
    for doc_row, code_row in zip(doc, code):
        assert doc_row == code_row, (
            f"AI_PIPELINE 7.8 row {doc_row[0]} differs from catalog.py:\n"
            f"  doc : {doc_row}\n  code: {code_row}")


def test_the_not_testable_table_matches_the_catalog_row_by_row() -> None:
    doc = [tuple(row) for row in _rows("X")]
    code = [(spec.id, spec.statement, spec.reason) for spec in NOT_TESTABLE]

    assert doc == code


def test_ids_are_unique_and_in_catalog_order() -> None:
    """Catalog order is contract order (CONTRACTS 7: "in catalog order")."""
    ids = [spec.id for spec in CATALOG]
    # 3 data + 3 time + 4 customer + 2 lever + 3 product/returns + 3
    # localization/lifecycle (ADR-0005). ADR-0006 once said "nineteen"; that
    # miscount was corrected in 3E1.
    assert len(ids) == len(set(ids)) == len(BY_ID) == 18
    assert ids == ["D1", "D2", "D3", "T1", "T2", "T3", "C1", "C2", "C3", "C4",
                   "B1", "B2", "P1", "P2", "P3", "R1", "R2", "R3"]


def test_the_directional_set_is_the_one_the_contract_names() -> None:
    """CONTRACTS section 7 says `contribution` and `share` are null for the
    directional hypotheses and names them. That list and `kind` must agree."""
    directional = {spec.id for spec in CATALOG if spec.kind == "directional"}

    assert directional == {"D2", "D3", "T3", "C4", "R1"}


@pytest.mark.parametrize("spec", CATALOG, ids=lambda spec: spec.id)
def test_every_spec_is_complete(spec) -> None:
    assert all((spec.id, spec.family, spec.lens, spec.statement, spec.test, spec.requires))
    assert "|" not in spec.test + spec.statement + spec.requires, (
        "a pipe would split the markdown cell and break the parity check")
