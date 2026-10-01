"""The generator's own guarantees (3E2 method C1-C3): engine-independent,
calendar-neutral where it says so, one cause per scenario, deterministic."""

import ast
import calendar
from pathlib import Path

import pandas as pd
import pytest

from tests.scenarios.scenarios import SCENARIOS
from tests.scenarios.store import SEED, WEEKDAY_WEIGHTS, generate

HERE = Path(__file__).parent


LIBRARIES = {"calendar", "collections", "dataclasses", "datetime", "numpy", "pandas"}
# Routes no import statement shows (review 3 #8): code run from a string, a
# name looked up at run time, a file read - an engine output on disk is a
# way in too. Not every route there is: the parse refuses the ones it knows.
DYNAMIC = {"exec", "eval", "compile", "__import__", "getattr", "open", "__builtins__"}
READERS = {"import_module", "read_json", "read_csv", "read_text", "read_bytes", "read_parquet", "read_excel"}


def _modules(tree: ast.Module) -> set[str]:
    """Every module an import statement names, `from x import y` as x.y too
    (so `from tests import stages` reads tests.stages) - relative imports
    refused outright, and so is importing by name at run time (review 2
    #10: `__import__`, `importlib`), which no parse can follow."""
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id in DYNAMIC:
            names.add(node.id)
        if isinstance(node, ast.Attribute) and node.attr in READERS:
            names.add(node.attr)
        if isinstance(node, ast.Import):
            names |= {alias.name for alias in node.names}
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0 and node.module, "no relative import"
            names |= {node.module} | {f"{node.module}.{alias.name}" for alias in node.names}
    return names


def _reaching_out(source: str) -> list[str]:
    """The imports that are neither a library the store uses nor the store
    (the module itself or a name in it - never a prefix: review 2 #10)."""
    return sorted(name for name in _modules(ast.parse(source))
                  if name.split(".")[0] not in LIBRARIES
                  and not (name == "tests.scenarios.store" or name.startswith("tests.scenarios.store.")))


@pytest.mark.parametrize("module", ["__init__.py", "store.py", "scenarios.py"])
def test_the_generator_cannot_see_the_engine(module: str) -> None:
    # C1: no engine figure can reach a planted cause - not directly, nor
    # through the tests that run the engine (review 1 #12).
    assert _reaching_out((HERE / module).read_text(encoding="utf-8")) == []


@pytest.mark.parametrize("source", ["import tests.stages.diagnose.scenario_runs as engine", "from tests import stages",
                                    "import stages.diagnose", "from contracts.diagnosis import Headline",
                                    "from tests.scenarios import scenarios_runs",
                                    "import tests.scenarios.store_engine",
                                    "from tests.scenarios.stores import diagnose",
                                    "x = __import__('stages.diagnose.assemble')",
                                    "import importlib",
                                    "exec('import stages.diagnose.assemble as engine')",
                                    "eval('1')",
                                    "loader = getattr(__builtins__, 'open')",
                                    "pd.read_json('runs/x/diagnosis.json')"])
def test_the_guard_refuses_the_routes_it_knows(source: str) -> None:
    assert _reaching_out(source) != []


def _expected_trading(year: int, month: int) -> float:
    """E(m), AI_PIPELINE 7.4, with the store's weekday weights."""
    return sum(WEEKDAY_WEIGHTS[calendar.weekday(year, month, day)]
               for day in range(1, calendar.monthrange(year, month)[1] + 1))


def test_the_compared_months_and_their_year_ago_pair_hold_no_calendar() -> None:
    # C2: 4 x 7.15 + Tue .85 + Wed .90 + Thu 1.05 = 31.40 in August 2023,
    # 4 x 7.15 + Fri 1.30 + Sat 1.50 = 31.40 in September; in 2022 August's
    # extra Mon, Tue, Wed (2.35) against September's Thu, Fri (2.35).
    assert _expected_trading(2023, 9) == pytest.approx(_expected_trading(2023, 8))
    assert _expected_trading(2022, 9) == pytest.approx(_expected_trading(2022, 8))
    assert _expected_trading(2023, 8) == pytest.approx(31.40)


def test_s1_is_the_calendar_alone() -> None:
    # Aug -> Sep 2024: August's extra Thursday, Friday and Saturday (3.85)
    # against September's Sunday and Monday (1.55): (28.60 + 1.55) /
    # (28.60 + 3.85) - 1 = 30.15 / 32.45 - 1 = -7.09%; its year-ago pair neutral.
    assert _expected_trading(2024, 9) / _expected_trading(2024, 8) - 1 == pytest.approx(-0.0709, abs=5e-4)
    assert _expected_trading(2023, 9) == pytest.approx(_expected_trading(2023, 8))


def test_the_same_seed_writes_the_same_file() -> None:
    first, second = generate("2023-07", "2023-09"), generate("2023-07", "2023-09")
    pd.testing.assert_frame_equal(first, second)
    assert not first.equals(generate("2023-07", "2023-09", seed=SEED + 1))


@pytest.mark.parametrize("scenario", [s for s in SCENARIOS if s.id in {"S2", "S3", "S4", "S5", "S6", "S7", "S8",
                                                                        "S10"}], ids=lambda s: s.id)
def test_a_planted_scenario_is_the_base_until_september(scenario) -> None:  # type: ignore[no-untyped-def]  # a Scenario
    # C3: one stream per month, every draw made before a plant drops a line -
    # so the history the engine learns from is the base's, line for line.
    base, planted = SCENARIOS[0].build(SEED), scenario.build(SEED)
    before = "2023-09-01"
    pd.testing.assert_frame_equal(base[base["Date"] < before].reset_index(drop=True),
                                  planted[planted["Date"] < before].reset_index(drop=True))
    assert not base[base["Date"] >= before].reset_index(drop=True).equals(
        planted[planted["Date"] >= before].reset_index(drop=True))


@pytest.mark.parametrize("scenario", [s for s in SCENARIOS if s.id in {"S4", "S5", "S7", "S8"}], ids=lambda s: s.id)
def test_a_plant_that_drops_lines_drops_only_them(scenario) -> None:  # type: ignore[no-untyped-def]  # a Scenario
    # C3 inside September: every draw is made before a line is dropped, so
    # the month is the base's month minus the dropped lines - not a new draw
    # from wherever the stream had drifted.
    base, planted = SCENARIOS[0].build(SEED), scenario.build(SEED)
    september = "2023-09-01"
    base_rows = set(base[base["Date"] >= september].itertuples(index=False, name=None))
    planted_rows = set(planted[planted["Date"] >= september].itertuples(index=False, name=None))
    assert planted_rows < base_rows
