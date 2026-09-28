"""A stage run again makes every later stage's output describe data that is
no longer there: a diagnosis of the metrics a re-analysis replaced keeps its
headline about another month (3G-lite review 1 #2). The backend removes
them when the stage succeeds (docs/CONTRACTS.md section 1), so which files a
run holds still says how far it went (SPECS section 3) - the stages never
edit a file they did not write.
"""

from pathlib import Path

from contracts import DiagnosisContract, ForecastContract, ReportContract
from shared.run_registry import run_file

# The presentation layer beside report.json (CONTRACTS section 1); no model.
REPORT_HTML = "report.html"
# Newest first: a removal that fails part way leaves the earlier outputs,
# which still describe each other (review 2 #1).
_OUTPUTS = [(ReportContract.written_by_stage, REPORT_HTML)]
_OUTPUTS += [(model.written_by_stage, model.filename) for model in (ReportContract, ForecastContract, DiagnosisContract)]


def discard(runs_root: Path, run_id: str, *, after_stage: int) -> None:
    """Remove the outputs of every stage after `after_stage`, newest first.
    Called by the services before a stage writes its new output, so a
    removal that fails writes nothing new."""
    for stage, filename in _OUTPUTS:
        if stage > after_stage and filename is not None:
            run_file(runs_root, run_id, filename).unlink(missing_ok=True)
