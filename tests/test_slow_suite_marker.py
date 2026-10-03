"""The quick run (Thach, 2026-10-02): `pytest -m "not slow_suite"` leaves out
the scenario and data failure-mode suites and nothing else; plain `pytest`
collects everything."""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _collected(*args: str) -> set[str]:
    out = subprocess.run([sys.executable, "-m", "pytest", "--co", "-q", "-p", "no:cacheprovider", *args],
                         cwd=ROOT, capture_output=True, text=True, check=True).stdout
    return {line.split("::")[0] for line in out.splitlines() if "::" in line}


def test_the_quick_run_leaves_out_the_slow_suites_and_only_them() -> None:
    everything = _collected("tests")
    quick = _collected("tests", "-m", "not slow_suite")
    left_out = everything - quick
    assert left_out and all(path.startswith(("tests/scenarios/", "tests/data_failures/",
                                             "tests/stages/diagnose/test_3e2_")) for path in left_out)
    assert {"tests/scenarios/test_store.py", "tests/stages/diagnose/test_3e2_scenarios.py",
            "tests/data_failures/test_conformance.py"} <= left_out
    assert "tests/stages/diagnose/test_3e1b_d1_pattern.py" in quick
