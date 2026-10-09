"""Q68 (Thach, 2026-10-09, a deploy blocker): two locks guard the whole-file
work - the frame cache's per-run load lock (FrameCache.get_or_load) and the
heavy-step slot (RunWork.heavy, one at a time by default). Every path takes
them in ONE order: the load lock first, the slot inside it; the slot is never
held while waiting for the load lock. The line summary took them the other
way round (the slot, then the load), so beside the preview or the currency
question both requests could wait forever - and every later heavy step of
every run behind them, silently, until a restart (step 5's scoped review).

Each test drives two real requests at once through the API, behind a third
heavy step that holds the one slot, and wants both answered within a timeout.
Written before the fix: the line summary's pairs hang on the code before it."""

import threading
import time
from typing import Any

import pytest

from tests.backend.api_support import MakeApi, make_api_with_plan

TIMEOUT = 10


def _queued(work: Any) -> int:
    """How many threads wait for the heavy slot."""
    return len(work._heavy._cond._waiters)  # noqa: SLF001 - the test watches the semaphore's queue


def _until(condition: Any, seconds: float = 5) -> None:
    deadline = time.monotonic() + seconds
    while not condition():
        assert time.monotonic() < deadline, "the request never reached the point the test waits for"
        time.sleep(0.01)


@pytest.mark.parametrize(("first", "second"), [
    ("line-summary", "preview"),   # hung before the fix
    ("line-summary", "currency"),  # hung before the fix
    ("currency", "preview"),
    ("preview", "line-summary"),
])
def test_two_whole_file_requests_never_deadlock(make_api: MakeApi, first: str, second: str) -> None:
    api, run_id, plan = make_api_with_plan(make_api)
    work, cache = api.app.state.run_work, api.app.state.frame_cache
    answered: dict[str, int] = {}

    def second_is_waiting() -> bool:
        # On the slot (it took the load lock first), or on the load lock the first request holds - a state,
        # never a guess of how long it takes to get there (the review: a 0.5 s sleep could miss it).
        reading = cache._loads.get(run_id)  # noqa: SLF001 - the test watches the cache's load table
        return _queued(work) >= 2 or (reading is not None and reading.users >= 2)

    def ask(step: str) -> None:
        answered[step] = api.post(run_id, step, plan).status_code

    threads = [threading.Thread(target=ask, args=(step,), daemon=True) for step in (first, second)]
    with work.heavy():  # another run's execute, holding the one slot
        threads[0].start()
        _until(lambda: _queued(work) >= 1)  # the first request waits for the slot
        threads[1].start()
        _until(second_is_waiting)
    for thread in threads:
        thread.join(timeout=TIMEOUT)

    assert not any(thread.is_alive() for thread in threads), f"{first} and {second} wait for each other forever"
    assert answered == {first: 200, second: 200}
    with work.heavy():  # and the slot is free for the next heavy step
        pass


# --- the rule, enforced where it can break: a heavy step never waits on another one in its own thread ----------


def test_a_heavy_step_inside_a_heavy_step_is_refused_not_a_silent_wait() -> None:
    from app.services.run_memory import RunWork

    work = RunWork(heavy_steps=2)
    with work.heavy():
        assert work.holds_heavy()
        with pytest.raises(RuntimeError, match="heavy step inside a heavy step"):
            with work.heavy():
                pass
    assert not work.holds_heavy()
    with work.heavy():  # the slot came back
        pass


def test_the_frame_is_never_asked_for_while_the_slot_is_held(tmp_path: Any) -> None:
    # The inversion itself: asking the cache for the frame inside a slot takes the slot before the load lock.
    from app.services.plan_execution import frame_of_run
    from app.services.run_memory import FrameCache, RunWork
    from shared.run_registry import create_run

    run = create_run(tmp_path)
    (run.path / "raw.csv").write_bytes(b"a,b\n1,2\n")
    work = RunWork(heavy_steps=2)
    cache = FrameCache(max_bytes=10_000_000, ttl_seconds=900)

    assert len(frame_of_run(work, cache, tmp_path, run.run_id)) == 1
    with work.heavy(), pytest.raises(RuntimeError, match="load lock first"):
        frame_of_run(work, cache, tmp_path, run.run_id)


def test_only_one_path_asks_the_cache_for_a_frame() -> None:
    # The review: the guard lives in frame_of_run; another caller of the cache inside a slot would bring the
    # deadlock back unrefused.
    import re
    from pathlib import Path

    app = Path(__file__).resolve().parents[2] / "backend" / "app"
    callers = [f"{path.name}:{number}" for path in sorted(app.rglob("*.py"))
               for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
               if re.search(r"\.get_or_load\(", line) and "def get_or_load" not in line]

    assert len(callers) == 1 and callers[0].startswith("plan_execution.py:")


def test_identical_currency_asks_share_one_reading(make_api: MakeApi, monkeypatch: pytest.MonkeyPatch) -> None:
    # The review: every ask took 10-16 s of the one slot on a large file, the browser's abort never stopping the
    # server, and Confirm waited behind them all. Asks of one run about the same money column share one reading.
    from app.services import plan_execution

    api, run_id, plan = make_api_with_plan(make_api)
    real = plan_execution.plan_currency
    readings: list[int] = []
    inside = threading.Event()
    go_on = threading.Event()

    def slow(*args: Any) -> Any:
        readings.append(1)
        inside.set()
        assert go_on.wait(timeout=10)
        return real(*args)

    monkeypatch.setattr(plan_execution, "plan_currency", slow)
    answers: list[int] = []
    asks = [threading.Thread(target=lambda: answers.append(api.post(run_id, "currency", plan).status_code), daemon=True)
            for _ in range(3)]
    asks[0].start()
    assert inside.wait(timeout=10)
    for ask in asks[1:]:
        ask.start()
    time.sleep(0.3)  # the later asks arrive while the first reads
    go_on.set()
    for ask in asks:
        ask.join(timeout=TIMEOUT)

    assert answers == [200, 200, 200]
    assert len(readings) == 1


def test_analysis_and_diagnosis_hold_no_database_connection_while_they_wait_for_the_slot(make_api: MakeApi) -> None:
    # The review: a read transaction held through the wait for the slot, while a step inside the slot needs a
    # connection, is the same shape between the slot and the pool (bounded by the pool's timeout, still a 500).
    from tests.backend.test_api_analyze import _cleaned_run

    api, run_id = _cleaned_run(make_api)
    work = api.app.state.run_work
    real = work.heavy
    seen: list[int] = []

    def watched() -> Any:
        seen.append(api.engine.pool.checkedout())
        return real()

    work.heavy = watched
    assert api.post(run_id, "analyze").status_code == 200
    assert api.post(run_id, "diagnose").status_code == 200

    assert seen and all(count == 0 for count in seen)
