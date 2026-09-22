"""FrameCache: the parsed-raw.csv cache behind the preview (services/run_memory.py)."""

import threading
import time

import pandas as pd
import pytest

from app.services.run_memory import FrameCache, frame_bytes


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def frame_of(size: int = 10) -> pd.DataFrame:
    """A one-cell frame whose cell is `size` characters long."""
    return pd.DataFrame({"c": ["x" * size]})


class Loader:
    """Counts how often the file would have been read."""

    def __init__(self, size: int = 10) -> None:
        self.calls = 0
        self.size = size

    def __call__(self) -> pd.DataFrame:
        self.calls += 1
        return frame_of(self.size)


ONE = frame_bytes(frame_of())  # what a frame of the default size costs


def make_cache(
    room_for: float = 10, ttl: float = 900, clock: Clock | None = None
) -> FrameCache:
    """A cache with room for `room_for` frames of the default size."""
    return FrameCache(max_bytes=int(ONE * room_for), ttl_seconds=ttl, clock=clock or Clock())


# --- the frame cache: hits and misses ------------------------------------------


def test_the_file_is_read_once_for_repeated_previews() -> None:
    cache, loader = make_cache(), Loader()

    first = cache.get_or_load("run-a", loader)
    second = cache.get_or_load("run-a", loader)

    assert loader.calls == 1
    assert second is first


def test_runs_do_not_share_a_frame() -> None:
    cache, loader = make_cache(), Loader()

    a = cache.get_or_load("run-a", loader)
    b = cache.get_or_load("run-b", loader)

    assert loader.calls == 2
    assert a is not b


def test_evict_makes_the_next_call_read_the_file_again() -> None:
    cache, loader = make_cache(), Loader()
    cache.get_or_load("run-a", loader)

    cache.evict("run-a")
    cache.get_or_load("run-a", loader)

    assert loader.calls == 2


def test_evicting_a_run_that_is_not_cached_is_harmless() -> None:
    make_cache().evict("never-seen")


# --- the frame cache: idle time ------------------------------------------------


def test_an_idle_frame_is_dropped_after_the_ttl() -> None:
    clock = Clock()
    cache, loader = make_cache(ttl=900, clock=clock), Loader()
    cache.get_or_load("run-a", loader)

    clock.now += 901
    cache.get_or_load("run-a", loader)

    assert loader.calls == 2


def test_each_use_restarts_the_idle_time() -> None:
    # The review screen previews on every edit: a frame in use must not expire
    # just because it was first loaded a long time ago.
    clock = Clock()
    cache, loader = make_cache(ttl=900, clock=clock), Loader()
    cache.get_or_load("run-a", loader)

    for _ in range(5):
        clock.now += 600
        cache.get_or_load("run-a", loader)

    assert loader.calls == 1


def test_a_frame_nobody_asks_for_again_is_freed_by_the_next_visit_of_any_run() -> None:
    # No background thread: expiry happens when the cache is next used. Without
    # this, a run the user abandoned would hold its frame until the process ends.
    clock = Clock()
    cache = make_cache(room_for=100, ttl=900, clock=clock)
    cache.get_or_load("abandoned", Loader(size=5000))
    assert cache.cached_bytes > 5000

    clock.now += 901
    cache.get_or_load("other", Loader())

    assert cache.cached_bytes == ONE
    assert cache.cached_runs == ["other"]


# --- the frame cache: the size bound -------------------------------------------


def test_the_least_recently_used_frame_is_evicted_to_make_room() -> None:
    cache = make_cache(room_for=2)
    cache.get_or_load("a", Loader())
    cache.get_or_load("b", Loader())
    cache.get_or_load("a", Loader())  # a is now the more recent

    cache.get_or_load("c", Loader())

    assert sorted(cache.cached_runs) == ["a", "c"]
    assert cache.cached_bytes == 2 * ONE


def test_a_frame_bigger_than_the_whole_budget_is_used_but_not_kept() -> None:
    cache, loader = make_cache(room_for=2), Loader(size=100_000)

    frame = cache.get_or_load("big", loader)
    cache.get_or_load("big", loader)

    assert frame.shape == (1, 1)
    assert loader.calls == 2  # every preview reads the file: slower, still correct
    assert cache.cached_bytes == 0


def test_a_frame_too_big_to_keep_does_not_push_out_the_others() -> None:
    cache = make_cache(room_for=2)
    cache.get_or_load("small", Loader())

    cache.get_or_load("big", Loader(size=100_000))

    assert cache.cached_runs == ["small"]


def test_the_budget_holds_however_many_runs_come_through() -> None:
    cache = make_cache(room_for=5)

    for number in range(200):
        cache.get_or_load(f"run-{number}", Loader(size=1 + number % 700))
        assert cache.cached_bytes <= cache.max_bytes


def test_a_frame_is_charged_for_the_text_it_holds_not_for_its_cell_count() -> None:
    # The 1G review: a budget in cells let 100 GB of 5 KB cells in. Bytes cannot.
    assert frame_bytes(frame_of(5000)) > 5000
    cache = FrameCache(max_bytes=2 * frame_bytes(frame_of(5000)) - 1, ttl_seconds=900)

    cache.get_or_load("a", Loader(size=5000))
    cache.get_or_load("b", Loader(size=5000))

    assert cache.cached_runs == ["b"]  # one such frame fits, two do not


# --- the frame cache: many threads ---------------------------------------------


def test_simultaneous_first_previews_read_the_file_once() -> None:
    # Two edits in quick succession both miss while the first read is still
    # running; without a guard both parse the same 50 MB file.
    cache = make_cache()
    calls = 0
    counter = threading.Lock()

    def slow_load() -> pd.DataFrame:
        nonlocal calls
        with counter:
            calls += 1
        time.sleep(0.05)
        return frame_of()

    start = threading.Barrier(6)
    frames: list[pd.DataFrame] = []

    def preview() -> None:
        start.wait()
        frames.append(cache.get_or_load("run-a", slow_load))

    workers = [threading.Thread(target=preview) for _ in range(6)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join()

    assert calls == 1
    assert all(frame is frames[0] for frame in frames)


def test_a_slow_read_of_one_run_does_not_hold_up_another_runs_read() -> None:
    # The 1G review: one global lock parked every thread behind the first parse.
    cache = make_cache()
    b_started = threading.Event()
    result: list[str] = []

    def load_a() -> pd.DataFrame:
        # Only returns once run B's read has begun: with one lock for all runs
        # that never happens, and the wait below times out.
        result.append("b started" if b_started.wait(timeout=5) else "b was blocked")
        return frame_of()

    def load_b() -> pd.DataFrame:
        b_started.set()
        return frame_of()

    worker = threading.Thread(target=lambda: cache.get_or_load("run-a", load_a))
    worker.start()
    time.sleep(0.05)  # run A is inside its read
    cache.get_or_load("run-b", load_b)
    worker.join(timeout=10)

    assert result == ["b started"]


def test_a_run_evicted_during_its_read_is_not_stored_afterwards() -> None:
    # The 1G review: execute evicts the run's frame, a preview already reading the
    # file then stored its stale frame, and it stayed until the ttl.
    cache = make_cache()
    reading, proceed = threading.Event(), threading.Event()

    def slow_load() -> pd.DataFrame:
        reading.set()
        assert proceed.wait(timeout=10)
        return frame_of()

    returned: list[pd.DataFrame] = []
    worker = threading.Thread(target=lambda: returned.append(cache.get_or_load("run-a", slow_load)))
    worker.start()
    assert reading.wait(timeout=10)

    cache.evict("run-a")
    proceed.set()
    worker.join(timeout=10)

    assert len(returned) == 1  # the caller still gets its frame
    assert cache.cached_runs == []  # but nothing stale is kept


def test_an_eviction_does_not_stop_the_run_being_cached_later() -> None:
    cache, loader = make_cache(), Loader()
    cache.get_or_load("run-a", loader)
    cache.evict("run-a")

    cache.get_or_load("run-a", loader)

    assert cache.cached_runs == ["run-a"]


def test_a_loader_that_fails_caches_nothing_and_leaves_no_trace() -> None:
    cache = make_cache()

    def broken() -> pd.DataFrame:
        raise OSError("disk gone")

    with pytest.raises(OSError, match="disk gone"):
        cache.get_or_load("run-a", broken)

    assert cache.cached_runs == []
    assert cache.get_or_load("run-a", Loader()).shape == (1, 1)
