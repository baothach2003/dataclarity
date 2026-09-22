"""State the server keeps in memory for the runs it is working on.

All of it is lost when the process restarts, which is safe:

* `FrameCache`: the parsed `raw.csv` of a run, so the review screen's preview (a
  request on every edit, debounced to 400 ms) does not read and parse the file each
  time. Reading a 54 MB file alone costs 2.6 s against the 3 s preview budget (1F
  measurements). Losing it costs one slower preview.
* `RetryBudgets`: the run's one shared AI retry (AI_PIPELINE section 2), which spans
  the schema step and the plan step, two separate requests. Losing it (a restart in
  the middle of a run) can allow one extra retry, which costs one AI call.
* `RunWork`: which runs this process is working on right now, and how many AI
  attempts each step of a run has used.

Single process only: with several workers each would hold its own copy. v1 runs one
(CLAUDE.md section 2: no infrastructure "for scale").
"""

import threading
import time
from collections import OrderedDict
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field

import pandas as pd

from app.errors import ApiError
from shared.ai_client import RetryBudget

# SPECS section 11 allows one AI call per step and one shared retry. A step is
# attempted again after it produced no answer (the AI was down, AI_PIPELINE section
# 9.3), so a few attempts are allowed; without a bound one caller could spend the
# whole AI budget on a single run.
MAX_AI_ATTEMPTS_PER_STEP = 3
BYTES_PER_MB = 1_048_576


def frame_bytes(frame: pd.DataFrame) -> int:
    """What the frame holds in memory, strings included. Measured, not estimated from
    rows x columns: a cell is about 16 bytes for a short value and 5,000 for a 5 KB one
    (measured in the 1G review), so a budget in cells cannot bound memory."""
    return int(frame.memory_usage(deep=True).sum())


@dataclass
class _Entry:
    frame: pd.DataFrame
    size: int
    last_used: float


@dataclass
class _Load:
    """A read of one run's file in progress. Its lock makes the run's simultaneous
    previews share one parse; `evicted` records that the run was dropped while the
    read was running, so the frame it returns is not stored (it would be stale)."""

    lock: threading.Lock = field(default_factory=threading.Lock)
    users: int = 0
    evicted: bool = False


class FrameCache:
    """Parsed frames by run id, bounded two ways so it cannot grow without limit:

    * a budget in bytes across all frames: the least recently used frame is evicted
      to make room;
    * an idle time: a frame nobody asked for within `ttl_seconds` is dropped. There
      is no background thread; expiry is checked whenever the cache is used, by
      any run, so an abandoned run's frame is freed by the next visit of any other.

    A frame larger than the whole budget is handed back but not kept: previews of
    it read the file every time (slower, still correct) and it never displaces the
    frames of other runs.

    The frames are shared between requests, so nothing may modify one in place.
    `preview.preview_frame` and `cleaning.apply_plan` promise that (they copy).
    Reading is serialized per run, not globally: a slow parse of one run's file must
    not hold every other request's thread.
    """

    def __init__(
        self,
        *,
        max_bytes: int,
        ttl_seconds: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._max_bytes = max_bytes
        self._ttl = ttl_seconds
        self._clock = clock
        self._entries: OrderedDict[str, _Entry] = OrderedDict()
        self._loads: dict[str, _Load] = {}
        self._lock = threading.Lock()  # the entries and the loads table

    def get_or_load(self, run_id: str, load: Callable[[], pd.DataFrame]) -> pd.DataFrame:
        cached = self._get(run_id)
        if cached is not None:
            return cached
        with self._lock:
            reading = self._loads.setdefault(run_id, _Load())
            reading.users += 1
        try:
            # Two edits in quick succession both miss while the first read is still
            # running; the second waits here and then finds the frame the first stored.
            with reading.lock:
                cached = self._get(run_id)
                if cached is not None:
                    return cached
                frame = load()  # an error here stores nothing and reaches the caller
                self._put(run_id, frame, reading)
                return frame
        finally:
            with self._lock:
                reading.users -= 1
                if reading.users == 0:
                    del self._loads[run_id]

    def evict(self, run_id: str) -> None:
        """Drop the run's frame, and any frame being read for it right now."""
        with self._lock:
            self._entries.pop(run_id, None)
            reading = self._loads.get(run_id)
            if reading is not None:
                reading.evicted = True

    @property
    def max_bytes(self) -> int:
        return self._max_bytes

    @property
    def ttl_seconds(self) -> float:
        return self._ttl

    @property
    def cached_bytes(self) -> int:
        with self._lock:
            return sum(entry.size for entry in self._entries.values())

    @property
    def cached_runs(self) -> list[str]:
        """Run ids, least recently used first."""
        with self._lock:
            return list(self._entries)

    def _get(self, run_id: str) -> pd.DataFrame | None:
        with self._lock:
            now = self._clock()
            self._drop_idle(now)
            entry = self._entries.get(run_id)
            if entry is None:
                return None
            entry.last_used = now
            self._entries.move_to_end(run_id)
            return entry.frame

    def _put(self, run_id: str, frame: pd.DataFrame, reading: _Load) -> None:
        size = frame_bytes(frame)
        if size > self._max_bytes:
            return
        with self._lock:
            if reading.evicted:
                return
            now = self._clock()
            self._drop_idle(now)
            self._entries.pop(run_id, None)
            used = sum(entry.size for entry in self._entries.values())
            while self._entries and used + size > self._max_bytes:
                _, evicted = self._entries.popitem(last=False)
                used -= evicted.size
            self._entries[run_id] = _Entry(frame, size, now)

    def _drop_idle(self, now: float) -> None:
        idle = [run_id for run_id, e in self._entries.items() if now - e.last_used > self._ttl]
        for run_id in idle:
            del self._entries[run_id]


class RetryBudgets:
    """The run's shared AI retry, one object per run for the run's whole life.

    Entries are a few bytes and dropped when the run leaves the AI phase
    (`forget`); a run abandoned before that keeps its entry until the process
    restarts or the retention cleanup (PROJECT_PLAN 8B) forgets it.
    """

    def __init__(self) -> None:
        self._budgets: dict[str, RetryBudget] = {}
        self._lock = threading.Lock()

    def for_run(self, run_id: str) -> RetryBudget:
        with self._lock:
            return self._budgets.setdefault(run_id, RetryBudget())

    def forget(self, run_id: str) -> None:
        with self._lock:
            self._budgets.pop(run_id, None)

    @property
    def tracked_runs(self) -> list[str]:
        with self._lock:
            return list(self._budgets)


class RunWork:
    """Which runs this process is working on, and the AI attempts each step has used.

    One piece of work at a time per run: an AI step or an execution. A second one that
    arrives while the first runs is refused (INVALID_STATE, 409), so two requests
    cannot both call the AI for one step (the cost bound of SPECS section 11 and the
    schema file one of them would delete under the other), and an execute cannot start
    while a plan is being proposed for the same run.

    It is also how a run left in `cleaning` is recognized as abandoned: the claim is
    in-process work, so a `cleaning` run with no work registered here belongs to a
    process that died, or to a request whose own status update failed
    (`run_state.recover_claim`). Registering happens BEFORE the claim and ends AFTER
    its release, so a run that is really executing is never seen as abandoned.
    """

    def __init__(self, max_ai_attempts: int = MAX_AI_ATTEMPTS_PER_STEP) -> None:
        self._max_attempts = max_ai_attempts
        self._active: set[str] = set()
        self._attempts: dict[tuple[str, str], int] = {}
        self._lock = threading.Lock()

    @contextmanager
    def ai_step(self, run_id: str, step: str) -> Iterator[None]:
        """Exclusive, and counted: the fourth attempt of one step is RATE_LIMITED (429)."""
        with self._lock:
            self._refuse_if_active(run_id)
            if self._attempts.get((run_id, step), 0) >= self._max_attempts:
                raise ApiError(
                    "RATE_LIMITED",
                    f"The AI has already been asked {self._max_attempts} times to {step} for "
                    "this run. Build the plan by hand, or upload the file again.",
                    {"step": step, "attempts": self._max_attempts},
                )
            self._attempts[(run_id, step)] = self._attempts.get((run_id, step), 0) + 1
            self._active.add(run_id)
        try:
            yield
        finally:
            self._end(run_id)

    @contextmanager
    def execution(self, run_id: str) -> Iterator[None]:
        """Exclusive. Entered before the run is claimed, left after it is settled."""
        with self._lock:
            self._refuse_if_active(run_id)
            self._active.add(run_id)
        try:
            yield
        finally:
            self._end(run_id)

    def is_active(self, run_id: str) -> bool:
        with self._lock:
            return run_id in self._active

    def forget(self, run_id: str) -> None:
        """The run is out of the interactive phase: its attempt counts are not needed."""
        with self._lock:
            for key in [k for k in self._attempts if k[0] == run_id]:
                del self._attempts[key]

    def _refuse_if_active(self, run_id: str) -> None:
        if run_id in self._active:
            raise ApiError(
                "INVALID_STATE",
                "Another step is already running for this run. Wait for it to finish.",
                {"reason": "step_in_progress"},
            )

    def _end(self, run_id: str) -> None:
        with self._lock:
            self._active.discard(run_id)
