"""Tests for thread safety of Stopwatch."""

import threading
import time
from collections.abc import Callable
from typing import Any

import pytest

from ticko import (
    AlreadyPausedError,
    AlreadyRunningError,
    NoLapsRecordedError,
    NotPausedError,
    NotRunningError,
    NotStartedError,
    Stopwatch,
)

_THREAD_TIMEOUT = 1.0
Outcome = tuple[str, Any]
GetterSnapshot = dict[str, Outcome]


class MonotonicTimer:
    """Return monotonically increasing values across threads."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._value = 0.0

    def __call__(self) -> float:
        """Return the next timer value."""
        with self._lock:
            current = self._value
            self._value += 1.0
            return current


def make_stopwatch() -> Stopwatch:
    """Create a stopwatch backed by a deterministic timer."""
    return Stopwatch(timer_func=MonotonicTimer())


def capture_outcome(operation: Callable[[], Any]) -> Outcome:
    """Return either the operation result or the raised exception."""
    try:
        return ("return", operation())
    except Exception as exc:
        return ("raise", exc)


def run_concurrently(*operations: Callable[[], Any]) -> list[Outcome]:
    """Run operations together and collect their outcomes."""
    barrier = threading.Barrier(len(operations) + 1, timeout=_THREAD_TIMEOUT)
    worker_failures: list[Exception] = []
    worker_failures_lock = threading.Lock()
    outcomes: list[Outcome | None] = [None] * len(operations)

    def run_operation(index: int, operation: Callable[[], Any]) -> None:
        try:
            barrier.wait()
            outcomes[index] = capture_outcome(operation)
        except Exception as exc:
            with worker_failures_lock:
                worker_failures.append(exc)

    threads = [
        threading.Thread(target=run_operation, args=(index, operation))
        for index, operation in enumerate(operations)
    ]
    for thread in threads:
        thread.start()

    try:
        barrier.wait()
    except threading.BrokenBarrierError as exc:  # pragma: no cover - assertion
        pytest.fail(f"Failed to start concurrent operations: {exc}")

    for thread in threads:
        thread.join(timeout=_THREAD_TIMEOUT)

    still_running = [thread.name for thread in threads if thread.is_alive()]
    assert not still_running, f"Threads did not finish: {still_running}"
    assert not worker_failures, f"Unexpected worker failures: {worker_failures}"
    assert all(outcome is not None for outcome in outcomes)
    return [outcome for outcome in outcomes if outcome is not None]


def collect_getter_outcomes(sw: Stopwatch) -> GetterSnapshot:
    """Read the public Stopwatch getters and capture each result separately."""
    return {
        "is_running": capture_outcome(lambda: sw.is_running),
        "time_start": capture_outcome(lambda: sw.time_start),
        "time_stop": capture_outcome(lambda: sw.time_stop),
        "time_elapsed": capture_outcome(lambda: sw.time_elapsed),
        "time_since_last_lap": capture_outcome(lambda: sw.time_since_last_lap),
    }


def assert_non_negative_number(value: Any) -> None:
    """Assert that a value is a non-negative numeric duration or timestamp."""
    assert isinstance(value, int | float)
    assert not isinstance(value, bool)
    assert value >= 0


def assert_returned(outcome: Outcome) -> Any:
    """Assert that a concurrent call returned successfully."""
    kind, value = outcome
    assert kind == "return"
    return value


def assert_raised(outcome: Outcome, exc_type: type[Exception]) -> Exception:
    """Assert that a concurrent call raised the expected exception type."""
    kind, value = outcome
    assert kind == "raise"
    assert isinstance(value, exc_type)
    return value


def assert_reset_state(sw: Stopwatch) -> None:
    """Assert that the stopwatch is back in its public initial state."""
    assert not sw.is_running
    assert sw.time_start is None
    assert sw.time_stop is None
    with pytest.raises(NotStartedError):
        _ = sw.time_elapsed
    with pytest.raises(NoLapsRecordedError):
        _ = sw.time_since_last_lap


def assert_running_state(sw: Stopwatch) -> None:
    """Assert that the stopwatch is in a valid running state."""
    assert sw.is_running
    assert sw.time_start is not None
    assert_non_negative_number(sw.time_start)
    assert sw.time_stop is None


def assert_stopped_state(sw: Stopwatch, expected_elapsed: float) -> None:
    """Assert that the stopwatch is in a valid stopped state."""
    assert not sw.is_running
    assert sw.time_start is not None
    assert_non_negative_number(sw.time_start)
    assert sw.time_stop is not None
    assert_non_negative_number(sw.time_stop)
    assert sw.time_elapsed == expected_elapsed


def assert_getter_snapshot_during_running_reset(
    snapshot: GetterSnapshot,
) -> None:
    """Validate getter outcomes while reset() races with readers."""
    assert_returned(snapshot["is_running"])
    assert isinstance(snapshot["is_running"][1], bool)

    time_start = assert_returned(snapshot["time_start"])
    if time_start is not None:
        assert_non_negative_number(time_start)

    assert snapshot["time_stop"] == ("return", None)

    time_elapsed = snapshot["time_elapsed"]
    if time_elapsed[0] == "return":
        assert_non_negative_number(time_elapsed[1])
    else:
        assert_raised(time_elapsed, NotStartedError)

    assert_raised(snapshot["time_since_last_lap"], NoLapsRecordedError)


def assert_getter_snapshot_during_stop(snapshot: GetterSnapshot) -> None:
    """Validate getter outcomes while stop() races with readers."""
    is_running = assert_returned(snapshot["is_running"])
    assert isinstance(is_running, bool)

    time_start = assert_returned(snapshot["time_start"])
    assert_non_negative_number(time_start)

    time_stop = assert_returned(snapshot["time_stop"])
    if time_stop is not None:
        assert_non_negative_number(time_stop)

    time_elapsed = assert_returned(snapshot["time_elapsed"])
    assert_non_negative_number(time_elapsed)

    assert_raised(snapshot["time_since_last_lap"], NoLapsRecordedError)


def assert_getter_snapshot_during_lap(snapshot: GetterSnapshot) -> None:
    """Validate getter outcomes while lap() races with readers."""
    is_running = assert_returned(snapshot["is_running"])
    assert is_running is True

    time_start = assert_returned(snapshot["time_start"])
    assert_non_negative_number(time_start)

    assert snapshot["time_stop"] == ("return", None)

    time_elapsed = assert_returned(snapshot["time_elapsed"])
    assert_non_negative_number(time_elapsed)

    time_since_last_lap = snapshot["time_since_last_lap"]
    if time_since_last_lap[0] == "return":
        assert_non_negative_number(time_since_last_lap[1])
    else:
        assert_raised(time_since_last_lap, NoLapsRecordedError)


class TestThreadSafety:
    """Test cases for public thread-safety guarantees."""

    def test_getters_allow_public_outcomes_during_running_reset(self) -> None:
        """Getter races with reset() should expose only public states."""
        sw = make_stopwatch()
        sw.start()

        def getter_reader() -> GetterSnapshot:
            return collect_getter_outcomes(sw)

        outcomes = run_concurrently(
            getter_reader,
            getter_reader,
            getter_reader,
            sw.reset,
        )

        for snapshot_outcome in outcomes[:3]:
            snapshot = assert_returned(snapshot_outcome)
            assert_getter_snapshot_during_running_reset(snapshot)

        reset_outcome = outcomes[3]
        assert assert_returned(reset_outcome) is None
        assert_reset_state(sw)

    def test_getters_allow_public_outcomes_during_stop(self) -> None:
        """Getter races with stop() should expose only public states."""
        sw = make_stopwatch()
        sw.start()

        def getter_reader() -> GetterSnapshot:
            return collect_getter_outcomes(sw)

        outcomes = run_concurrently(
            getter_reader,
            getter_reader,
            getter_reader,
            sw.stop,
        )

        for snapshot_outcome in outcomes[:3]:
            snapshot = assert_returned(snapshot_outcome)
            assert_getter_snapshot_during_stop(snapshot)

        stop_outcome = outcomes[3]
        stop_elapsed = assert_returned(stop_outcome)
        assert_non_negative_number(stop_elapsed)
        assert_stopped_state(sw, stop_elapsed)

    def test_getters_allow_public_outcomes_during_lap(self) -> None:
        """Getter races with lap() should expose only public states."""
        sw = make_stopwatch()
        sw.start()

        def getter_reader() -> GetterSnapshot:
            return collect_getter_outcomes(sw)

        outcomes = run_concurrently(
            getter_reader,
            getter_reader,
            getter_reader,
            sw.lap,
        )

        for snapshot_outcome in outcomes[:3]:
            snapshot = assert_returned(snapshot_outcome)
            assert_getter_snapshot_during_lap(snapshot)

        lap_outcome = outcomes[3]
        lap_duration = assert_returned(lap_outcome)
        assert_non_negative_number(lap_duration)
        assert_running_state(sw)
        assert_non_negative_number(sw.time_since_last_lap)

    def test_concurrent_laps(self) -> None:
        """Concurrent lap() calls should record non-negative lap durations."""
        sw = make_stopwatch()
        sw.start()

        def record_laps() -> list[float]:
            return [sw.lap() for _ in range(10)]

        outcomes = run_concurrently(*(record_laps for _ in range(3)))
        lap_times = [
            lap_time
            for outcome in outcomes
            for lap_time in assert_returned(outcome)
        ]
        assert len(lap_times) == 30
        for lap_time in lap_times:
            assert_non_negative_number(lap_time)

    def test_concurrent_laps_history_length_matches_lap_count(self) -> None:
        """Concurrent lap() calls should record one history entry each."""
        sw = make_stopwatch()
        sw.start()

        def record_laps() -> None:
            for _ in range(10):
                sw.lap()

        outcomes = run_concurrently(*(record_laps for _ in range(3)))
        for outcome in outcomes:
            assert assert_returned(outcome) is None

        laps = sw.laps
        assert len(laps) == 30
        for lap_duration in laps:
            assert_non_negative_number(lap_duration)

    def test_laps_snapshot_is_consistent_under_concurrent_mutation(
        self,
    ) -> None:
        """Reading laps while lap() runs should yield a clean snapshot."""
        sw = make_stopwatch()
        sw.start()

        def reader() -> list[tuple[float, ...]]:
            return [sw.laps for _ in range(20)]

        outcomes = run_concurrently(
            reader,
            *(sw.lap for _ in range(15)),
        )

        snapshots = assert_returned(outcomes[0])
        for snapshot in snapshots:
            assert isinstance(snapshot, tuple)
            for lap_duration in snapshot:
                assert_non_negative_number(lap_duration)

        for lap_outcome in outcomes[1:]:
            assert_non_negative_number(assert_returned(lap_outcome))

        assert len(sw.laps) == 15

    def test_concurrent_start_attempts(self) -> None:
        """Only one concurrent start() should succeed on a shared stopwatch."""
        sw = make_stopwatch()
        outcomes = run_concurrently(*(sw.start for _ in range(10)))

        success_count = sum(
            1 for outcome in outcomes if outcome == ("return", None)
        )
        error_count = sum(
            1
            for outcome in outcomes
            if outcome[0] == "raise"
            and isinstance(outcome[1], AlreadyRunningError)
        )

        assert success_count == 1
        assert error_count == 9
        assert_running_state(sw)

    def test_concurrent_stop_attempts(self) -> None:
        """Only one concurrent stop() should succeed on a shared stopwatch."""
        sw = make_stopwatch()
        sw.start()
        outcomes = run_concurrently(*(sw.stop for _ in range(10)))

        successful_stops = [
            outcome[1] for outcome in outcomes if outcome[0] == "return"
        ]
        stop_errors = [
            outcome[1]
            for outcome in outcomes
            if outcome[0] == "raise" and isinstance(outcome[1], NotRunningError)
        ]

        assert len(successful_stops) == 1
        assert_non_negative_number(successful_stops[0])
        assert len(stop_errors) == 9
        assert_stopped_state(sw, successful_stops[0])

    def test_running_reset_and_stop_race(self) -> None:
        """reset() and stop() should expose only legal public outcomes."""
        sw = make_stopwatch()
        sw.start()
        reset_outcome, stop_outcome = run_concurrently(sw.reset, sw.stop)

        assert assert_returned(reset_outcome) is None

        if stop_outcome[0] == "return":
            assert_non_negative_number(stop_outcome[1])
        else:
            assert_raised(stop_outcome, NotRunningError)

        assert_reset_state(sw)

    def test_running_start_and_reset_race(self) -> None:
        """start() and reset() should expose only legal public outcomes."""
        sw = make_stopwatch()
        sw.start()
        start_outcome, reset_outcome = run_concurrently(sw.start, sw.reset)

        assert assert_returned(reset_outcome) is None

        if start_outcome[0] == "return":
            assert start_outcome[1] is None
            assert_running_state(sw)
        else:
            assert_raised(start_outcome, AlreadyRunningError)
            assert_reset_state(sw)

    def test_lap_and_stop_race(self) -> None:
        """lap() and stop() should expose only legal public outcomes."""
        sw = make_stopwatch()
        sw.start()
        lap_outcome, stop_outcome = run_concurrently(sw.lap, sw.stop)

        stop_elapsed = assert_returned(stop_outcome)
        assert_non_negative_number(stop_elapsed)
        assert_stopped_state(sw, stop_elapsed)

        if lap_outcome[0] == "return":
            assert_non_negative_number(lap_outcome[1])
            assert_non_negative_number(sw.time_since_last_lap)
        else:
            assert_raised(lap_outcome, NotRunningError)
            with pytest.raises(NoLapsRecordedError):
                _ = sw.time_since_last_lap

    def test_lap_and_reset_race(self) -> None:
        """lap() and reset() should expose only legal public outcomes."""
        sw = make_stopwatch()
        sw.start()
        lap_outcome, reset_outcome = run_concurrently(sw.lap, sw.reset)

        assert assert_returned(reset_outcome) is None

        if lap_outcome[0] == "return":
            assert_non_negative_number(lap_outcome[1])
        else:
            assert_raised(lap_outcome, NotRunningError)

        assert_reset_state(sw)

    def test_context_manager_in_threads(self) -> None:
        """Using independent context managers in threads remains safe."""
        results: list[float] = []
        errors: list[Exception] = []

        def use_context_manager() -> None:
            try:
                sw = Stopwatch()
                with sw:
                    time.sleep(0.01)
                    elapsed = sw.time_elapsed
                results.append(elapsed)
            except Exception as exc:
                errors.append(exc)

        threads = [
            threading.Thread(target=use_context_manager) for _ in range(5)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert len(errors) == 0, f"Unexpected errors: {errors}"
        assert len(results) == 5
        for elapsed in results:
            assert elapsed > 0.009

    def test_callback_thread_safety(self) -> None:
        """Using exit callbacks across independent instances remains safe."""
        callback_calls: list[float] = []
        callback_calls_lock = threading.Lock()

        def thread_safe_callback(elapsed: float) -> None:
            with callback_calls_lock:
                callback_calls.append(elapsed)

        def run_stopwatch() -> None:
            sw = Stopwatch(exit_callback=thread_safe_callback)
            sw.start()
            time.sleep(0.001)
            sw.stop()

        threads = [threading.Thread(target=run_stopwatch) for _ in range(10)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert len(callback_calls) == 10

    def test_concurrent_pause_attempts(self) -> None:
        """Only one concurrent pause() should succeed on a running stopwatch."""
        sw = make_stopwatch()
        sw.start()
        outcomes = run_concurrently(*(sw.pause for _ in range(10)))

        success_count = sum(
            1 for outcome in outcomes if outcome == ("return", None)
        )
        error_count = sum(
            1
            for outcome in outcomes
            if outcome[0] == "raise"
            and isinstance(outcome[1], AlreadyPausedError)
        )

        assert success_count == 1
        assert error_count == 9
        assert not sw.is_running
        assert sw.time_start is not None

    def test_concurrent_resume_attempts(self) -> None:
        """Only one concurrent resume() should succeed on a paused stopwatch."""
        sw = make_stopwatch()
        sw.start()
        sw.pause()
        outcomes = run_concurrently(*(sw.resume for _ in range(10)))

        success_count = sum(
            1 for outcome in outcomes if outcome == ("return", None)
        )
        error_count = sum(
            1
            for outcome in outcomes
            if outcome[0] == "raise" and isinstance(outcome[1], NotPausedError)
        )

        assert success_count == 1
        assert error_count == 9
        assert sw.is_running

    def test_pause_and_resume_race(self) -> None:
        """pause() and resume() should expose only legal public outcomes."""
        sw = make_stopwatch()
        sw.start()
        pause_outcome, resume_outcome = run_concurrently(sw.pause, sw.resume)

        # pause() always sees a running stopwatch (resume() never stops it),
        # so it succeeds. resume() succeeds only if it ran after pause().
        assert pause_outcome == ("return", None)

        if resume_outcome[0] == "return":
            assert resume_outcome[1] is None
            assert sw.is_running
        else:
            assert_raised(resume_outcome, NotPausedError)
            assert not sw.is_running

        assert sw.time_start is not None


class TestBehaviorUnderLoad:
    """Behavior tests that still exercise the shared stopwatch repeatedly."""

    def test_lap_property_consistency(self) -> None:
        """time_since_last_lap should reset close to zero after lap()."""
        sw = Stopwatch()
        sw.start()

        for _ in range(50):
            sw.lap()
            last_lap_property = sw.time_since_last_lap
            assert last_lap_property < 0.01

        sw.stop()
