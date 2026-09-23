"""One rule, one home - checked, not encouraged.

Twice a rule has lived in two catalogs and the copies have drifted into
opposite answers:

  3C   the C2 bridge sign convention, where CONTRACTS said signed and
       DIAGNOSE_DESIGN said magnitude;
  3D5b the T3 verdict rule, where DIAGNOSE_DESIGN was updated for ADR-0006 and
       AI_PIPELINE's own catalog row was not - and the stale row evaluated to
       "within normal variation" on the very file the session wrote a test
       about.

Both were found by a human reading two documents side by side. This file makes
the second copy mechanical to find instead.

The rule it enforces is narrow on purpose: a table whose rows are hypothesis
ids (`| D1 |`, `| T3 |`, `| C4 |` ...) is a CATALOG, and a catalog is a
statement of live behaviour. Exactly one document may carry one without a
freeze banner, and that document is the live source.
"""

import re
from pathlib import Path

import pytest

DOCS = Path(__file__).resolve().parent.parent / "docs"

# The live home for hypothesis behaviour. Everything else must be frozen.
LIVE_SOURCE = "AI_PIPELINE.md"

# `| D1 | data | ... |` - a catalog row, not a prose mention of an id.
CATALOG_ROW = re.compile(r"^\|\s*([DTCBPRX]\d)\s*\|", re.MULTILINE)
FREEZE_BANNER = "FROZEN"


def _markdown_files() -> list[Path]:
    return sorted(path for path in DOCS.rglob("*.md"))


def _section_of(text: str, index: int) -> str:
    """The `##`/`###` heading governing the character at `index`."""
    headings = [match for match in re.finditer(r"^#{2,3} .*$", text, re.MULTILINE)
                if match.start() < index]
    return headings[-1].group(0) if headings else "(no heading)"


def test_only_one_document_carries_a_live_hypothesis_catalog() -> None:
    """A catalog row outside the live source must sit under a freeze banner.

    The banner is what says "this is history, not behaviour". Without it a
    reader - or a session implementing from the wrong file - has no way to
    tell which of two tables is current, which is exactly how the T3 rule
    diverged.
    """
    offenders = []
    for path in _markdown_files():
        if path.name == LIVE_SOURCE:
            continue
        text = path.read_text(encoding="utf-8")
        for match in CATALOG_ROW.finditer(text):
            heading = _section_of(text, match.start())
            # The banner must appear between that heading and the row.
            heading_at = text.rindex(heading, 0, match.start())
            if FREEZE_BANNER not in text[heading_at:match.start()]:
                offenders.append(
                    f"{path.relative_to(DOCS.parent)} :: {heading} :: "
                    f"{match.group(1)}")
    assert not offenders, (
        "hypothesis-catalog rows outside docs/" + LIVE_SOURCE + " without a "
        "freeze banner - a rule with two live homes:\n  "
        + "\n  ".join(sorted(set(offenders))))


def test_the_live_source_actually_carries_the_catalog() -> None:
    """The mirror of the test above, so it cannot pass by the catalog having
    been deleted or renamed rather than kept in one place."""
    text = (DOCS / LIVE_SOURCE).read_text(encoding="utf-8")
    ids = {match.group(1) for match in CATALOG_ROW.finditer(text)}
    assert {"D1", "T1", "T3", "C1", "B1", "P1", "R1"} <= ids, (
        f"docs/{LIVE_SOURCE} no longer carries the hypothesis catalog; it is "
        f"the live source and this test is what pins that")


@pytest.mark.parametrize("heading", [
    "## 5. Step specifications",
    "## 6. `diagnosis.json` shape (replaces CONTRACTS section 7)",
    "## 7. Hypothesis catalog (fixed, evaluated in this order every run)",
    "## 8. Validation: planted-cause scenario suite",
    "## 9. Constants (`stages/diagnose/thresholds.py`)",
])
def test_the_frozen_design_record_keeps_its_banners(heading: str) -> None:
    """DIAGNOSE_DESIGN.md is the historical record as of session 3A. Its rule
    sections carry a banner saying so; removing one silently restores a second
    live copy of whatever that section describes."""
    text = (DOCS / "DIAGNOSE_DESIGN.md").read_text(encoding="utf-8")
    assert heading in text, f"{heading!r} was renamed; update this test with it"
    body = text[text.index(heading):]
    following = body[len(heading):]
    assert FREEZE_BANNER in following[:800], (
        f"{heading!r} lost its freeze banner")
