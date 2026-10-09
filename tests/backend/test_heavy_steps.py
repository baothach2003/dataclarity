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



def _currency_and_preview(holder_reads: bool, cache_bytes: int, tmp_path) -> dict[str, object]:  # type: ignore[no-untyped-def]  # pytest's tmp_path
    """Review open, as it happens: a step holds the one slot, the currency question is asked at once, the
    preview 400 ms later; then the slot is released. What finished within 5 s."""
    from app.services.plan_execution import currency_question_for, frame_of_run
    from app.services.run_memory import FrameCache
    from shared.run_registry import create_run
    from tests.stages.ingest.test_currency import plan

    run = create_run(tmp_path)
    (run.path / "raw.csv").write_bytes(b"sku,name,qty,price,day\nA1,Mug,2,\xc2\xa32.50,2024-01-05\n")
    work = RunWork(heavy_steps=1)
    cache = FrameCache(max_bytes=cache_bytes, ttl_seconds=900)
    done: dict[str, object] = {}
    release = threading.Event()

    def hold() -> None:
        if holder_reads:  # the line summary's shape since Q68: the frame first, then its own slot
            frame_of_run(work, cache, tmp_path, run.run_id)
        with work.heavy():
            release.wait()

    def currency() -> None:
        done["currency"] = currency_question_for(
            work, cache, tmp_path, run.run_id, plan(["sku", "name", "qty", "price", "day"])).finding.kind

    def preview() -> None:
        done["preview"] = len(frame_of_run(work, cache, tmp_path, run.run_id))  # the preview's own path

    threads = [threading.Thread(target=step, daemon=True) for step in (hold, currency, preview)]
    for thread in threads:
        thread.start()
        time.sleep(0.2)
    release.set()
    for thread in threads[1:]:
        thread.join(timeout=5)
    return done


@pytest.mark.parametrize(("holder_reads", "cache_bytes"), [(False, 10_000_000), (True, 1), (True, 10_000_000)])
def test_reviews_currency_question_and_the_preview_never_deadlock(holder_reads, cache_bytes, tmp_path) -> None:  # type: ignore[no-untyped-def]  # pytest's
    # Step 5's scoped review: the reading inside the slot took the slot before the cache's lock, the preview
    # the other way round - with one slot both waited forever, and every later heavy step behind them.
    assert _currency_and_preview(holder_reads, cache_bytes, tmp_path) == {"currency": "found", "preview": 1}


def test_reviews_currency_question_loads_the_file_in_a_slot(tmp_path) -> None:  # type: ignore[no-untyped-def]  # pytest's tmp_path
    from app.services.plan_execution import currency_question_for
    from app.services.run_memory import FrameCache
    from shared.run_registry import create_run
    from tests.stages.ingest.test_currency import plan

    run = create_run(tmp_path)
    (run.path / "raw.csv").write_bytes(b"sku,name,qty,price,day\nA1,Mug,2,\xc2\xa32.50,2024-01-05\n")
    work = RunWork(heavy_steps=1)
    asked: list[str] = []
    cache = FrameCache(max_bytes=10_000_000, ttl_seconds=900)
    with work.heavy():
        reader = threading.Thread(target=lambda: asked.append(
            currency_question_for(work, cache, tmp_path, run.run_id, plan(["sku", "name", "qty", "price", "day"]))
            .finding.kind))
        reader.start()
        reader.join(timeout=0.3)
        assert reader.is_alive() and asked == []  # the whole-file load waits for the slot
    reader.join(timeout=5)
    assert asked == ["found"]
