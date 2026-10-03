"""Thach, 2026-10-02 (for deploy): the number of heavy steps one process runs
at a time is an environment setting, MAX_CONCURRENT_HEAVY_STEPS - one at a
time by default (.env.example): each heavy step on a 50 MB file needs about
0.5-0.7 GB of its own (PROJECT_PLAN Phase 9's memory measurement). A step
over the limit waits for a slot rather than failing."""

import threading
import time

import pytest
from pydantic import ValidationError

from app.config import Settings
from app.services.run_memory import RunWork


def test_the_limit_comes_from_the_environment(settings: Settings) -> None:
    assert settings.max_concurrent_heavy_steps == 1


@pytest.mark.parametrize("value", ["0", "-1"])
def test_a_limit_that_is_not_positive_stops_startup(value: str) -> None:
    with pytest.raises(ValidationError, match="max_concurrent_heavy_steps"):
        Settings(_env_file=None, max_concurrent_heavy_steps=value)  # type: ignore[call-arg]  # rest from env


def _overlap(limit: int, steps: int) -> int:
    """How many of `steps` threads were inside a heavy step at once, at most."""
    work = RunWork(heavy_steps=limit)
    inside, most, lock = [0], [0], threading.Lock()

    def step() -> None:
        with work.heavy():
            with lock:
                inside[0] += 1
                most[0] = max(most[0], inside[0])
            time.sleep(0.05)
            with lock:
                inside[0] -= 1

    threads = [threading.Thread(target=step) for _ in range(steps)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    return most[0]


def test_one_heavy_step_at_a_time_by_default() -> None:
    assert _overlap(1, 4) == 1


def test_the_limit_lets_that_many_run_together() -> None:
    assert _overlap(2, 4) == 2


def test_a_step_that_fails_gives_its_slot_back() -> None:
    work = RunWork(heavy_steps=1)
    with pytest.raises(RuntimeError):
        with work.heavy():
            raise RuntimeError("a stage failed")
    with work.heavy():
        pass  # would block forever had the slot been kept


def test_the_app_builds_its_run_work_with_the_limit(settings: Settings) -> None:
    from app.main import create_app

    app = create_app(settings.model_copy(update={"max_concurrent_heavy_steps": 3}))
    assert app.state.run_work.heavy_steps == 3


def test_the_previews_whole_file_load_waits_for_a_slot(tmp_path) -> None:  # type: ignore[no-untyped-def]  # pytest's tmp_path
    from shared.run_registry import create_run
    from app.services.plan_execution import _read_frame_heavy

    run = create_run(tmp_path)
    (run.path / "raw.csv").write_bytes(b"a,b\n1,2\n")
    work = RunWork(heavy_steps=1)
    loaded: list[int] = []
    with work.heavy():
        reader = threading.Thread(target=lambda: loaded.append(len(_read_frame_heavy(work, tmp_path, run.run_id))))
        reader.start()
        reader.join(timeout=0.3)
        assert reader.is_alive() and loaded == []  # waiting for the slot
    reader.join(timeout=5)
    assert loaded == [1]

