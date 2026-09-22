"""RetryBudgets and RunWork: per-run AI budget and work tracking
(services/run_memory.py)."""

import threading

import pytest

from app.errors import ApiError
from app.services.run_memory import RetryBudgets, RunWork


# --- the retry budgets ---------------------------------------------------------


def test_a_run_gets_one_retry() -> None:
    assert RetryBudgets().for_run("run-a").remaining == 1


def test_the_same_run_always_gets_the_same_budget_object() -> None:
    # The schema step and the plan step are two requests; what the first spends,
    # the second must find spent.
    budgets = RetryBudgets()

    first = budgets.for_run("run-a")
    assert first.take() is True
    second = budgets.for_run("run-a")

    assert second is first
    assert second.remaining == 0
    assert second.take() is False


def test_runs_have_separate_budgets() -> None:
    budgets = RetryBudgets()
    budgets.for_run("run-a").take()

    assert budgets.for_run("run-b").remaining == 1


def test_forget_drops_a_finished_runs_budget() -> None:
    budgets = RetryBudgets()
    budgets.for_run("run-a").take()

    budgets.forget("run-a")

    assert budgets.tracked_runs == []
    assert budgets.for_run("run-a").remaining == 1  # a new object, for a new life


def test_simultaneous_requests_for_a_new_run_share_one_budget() -> None:
    budgets = RetryBudgets()
    start = threading.Barrier(8)
    seen: list[object] = []

    def ask() -> None:
        start.wait()
        seen.append(budgets.for_run("run-a"))

    workers = [threading.Thread(target=ask) for _ in range(8)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join()

    assert len({id(budget) for budget in seen}) == 1


# --- the run work --------------------------------------------------------------


def refused(work: RunWork, run_id: str = "run-a") -> ApiError:
    with pytest.raises(ApiError) as caught, work.ai_step(run_id, "analyze"):
        pass
    return caught.value


def test_a_step_is_refused_while_another_runs_for_the_same_run() -> None:
    work = RunWork()

    with work.ai_step("run-a", "analyze"):
        assert work.is_active("run-a")
        error = refused(work)
        with pytest.raises(ApiError) as also, work.execution("run-a"):
            pass

    assert error.code == "INVALID_STATE"
    assert error.details == {"reason": "step_in_progress"}
    assert also.value.code == "INVALID_STATE"
    assert not work.is_active("run-a")


def test_an_execution_blocks_an_ai_step_for_its_run_only() -> None:
    work = RunWork()

    with work.execution("run-a"):
        assert refused(work).code == "INVALID_STATE"
        with work.ai_step("run-b", "analyze"):  # another run is not affected
            assert work.is_active("run-b")


def test_work_ends_even_when_it_raises() -> None:
    work = RunWork()

    with pytest.raises(RuntimeError), work.execution("run-a"):
        raise RuntimeError("boom")

    assert not work.is_active("run-a")
    with work.execution("run-a"):  # and the run can be worked on again
        pass


def test_a_step_may_be_attempted_three_times_and_then_is_rate_limited() -> None:
    work = RunWork()

    for _ in range(3):
        with work.ai_step("run-a", "analyze"):
            pass
    error = refused(work)

    assert error.code == "RATE_LIMITED"
    assert error.details == {"step": "analyze", "attempts": 3}


def test_attempts_are_counted_per_step_and_per_run() -> None:
    work = RunWork()
    for _ in range(3):
        with work.ai_step("run-a", "analyze"):
            pass

    with work.ai_step("run-a", "plan"):  # the other step of the run has its own count
        pass
    with work.ai_step("run-b", "analyze"):  # so has the same step of another run
        pass


def test_forget_gives_a_run_its_attempts_back() -> None:
    work = RunWork()
    for _ in range(3):
        with work.ai_step("run-a", "analyze"):
            pass

    work.forget("run-a")

    with work.ai_step("run-a", "analyze"):
        pass


def test_of_many_simultaneous_requests_for_one_step_exactly_one_gets_in() -> None:
    work = RunWork()
    start = threading.Barrier(8)
    all_tried = threading.Barrier(8)
    outcomes: list[str] = []
    lock = threading.Lock()

    def request() -> None:
        start.wait()
        try:
            with work.ai_step("run-a", "analyze"):
                # Holds the step until every request has tried, so they truly overlap.
                try:
                    all_tried.wait(timeout=0.5)
                except threading.BrokenBarrierError:
                    pass
                result = "in"
        except ApiError as error:
            result = error.code
            try:
                all_tried.wait(timeout=0.5)
            except threading.BrokenBarrierError:
                pass
        with lock:
            outcomes.append(result)

    workers = [threading.Thread(target=request) for _ in range(8)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join()

    assert sorted(outcomes) == ["INVALID_STATE"] * 7 + ["in"]
