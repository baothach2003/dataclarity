"""A stage run again makes every later stage's output describe data that is
no longer there: a diagnosis of the metrics a re-analysis replaced keeps its
headline about another month (3G-lite review 1 #2). They are set aside
around the new output's rename and deleted once it succeeds
(docs/CONTRACTS.md section 1), so which files a run holds still says how far
it went (SPECS section 3); if anything fails they are put back - all or
nothing (DEMO review #2). The stages never edit a file they did not write.

Infrastructure, in shared/ since 5D (CLAUDE.md 3.1): the backend's services
and stage 5's own CLI set outputs aside with this one implementation - the
CLI's copy of it had drifted (5D review 2 #1, #2).
"""

import logging
import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from contracts import DiagnosisContract, ForecastContract, ReportContract
from shared.run_registry import run_file

# The presentation layer beside report.json (CONTRACTS section 1); no model.
REPORT_HTML = "report.html"

# Newest first, so a crash part way (the one case not put back) leaves the
# earlier outputs, which still describe each other.
_OUTPUTS = [(ReportContract.written_by_stage, REPORT_HTML)]
_OUTPUTS += [(model.written_by_stage, model.filename) for model in (ReportContract, ForecastContract, DiagnosisContract)]


ASIDE = ".aside-"  # nothing reads a file named so

logger = logging.getLogger(__name__)


@contextmanager
def set_aside(runs_root: Path, run_id: str, *, after_stage: int) -> Iterator[None]:
    """The outputs of every stage after `after_stage`, moved aside for the
    block (a stage's new output being renamed into place), deleted once it
    succeeds, put back if it - or a move - fails."""
    moved: list[tuple[Path, Path]] = []
    try:
        for stage, filename in _OUTPUTS:
            path = run_file(runs_root, run_id, filename) if filename is not None and stage > after_stage else None
            if path is not None and path.exists():
                aside = path.with_name(ASIDE + path.name)
                os.replace(path, aside)
                moved.append((aside, path))
        yield
    except BaseException:
        for aside, path in reversed(moved):
            os.replace(aside, path)
        raise
    for aside, _ in moved:
        # The new output is in place; an old one set aside is hidden (nothing
        # reads ".aside-"): a delete another program blocks fails nothing
        # (4A review 1 #14), and is logged - the next re-run replaces it once
        # the other program lets go, and fails until then (8D).
        try:
            aside.unlink(missing_ok=True)
        except OSError as error:
            logger.warning("set-aside file not removed: %s (%s)", aside.name, type(error).__name__)
