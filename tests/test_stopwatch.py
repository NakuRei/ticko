"""Tests for the Stopwatch class."""

import logging
import time
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
from unittest.mock import Mock

import pytest
from _timing_output_assertions import assert_elapsed_seconds_displayed

from ticko import (
    AlreadyRunningError,
    NoLapsRecordedError,
    NotPausedError,
    NotRunningError,
    NotStartedError,
    PausedStateError,
    Stopwatch,
    StopwatchError,
)


@pytest.fixture
def stopwatch(mock_timer: Mock) -> Stopwatch:
    """Create a Stopwatch instance with mock timer."""
    return Stopwatch(timer_func=mock_timer)


@pytest.fixture
def root_logger_without_handlers() -> Callable[
    [],
    AbstractContextManager[logging.Logger],
]:
    """Create a context manager that clears root logger handlers."""

    @contextmanager
    def clear_root_logger_handlers() -> Iterator[logging.Logger]:
        root_logger = logging.getLogger()
        previous_handlers = root_logger.handlers[:]
        root_logger.handlers.clear()
        try:
            yield root_logger
        finally:
            root_logger.handlers[:] = previous_handlers

    return clear_root_logger_handlers


def repr_contract_timer() -> float:
    """Return a stable timer value for repr contract tests."""
    return 0.0


def repr_contract_callback(_elapsed: float) -> None:
    """Accept elapsed time for repr contract tests."""


class DiagnosticRecordHandler(logging.Handler):
    """Collect application-observed diagnostic log records."""

    def __init__(self) -> None:
        """Initialize the record collection handler."""
        super().__init__(level=logging.ERROR)
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        """Store an emitted log record."""
        self.records.append(record)


class TestStopwatchExceptionHierarchy:
    """Test public Stopwatch exception relationships."""

    @pytest.mark.parametrize(
        "specific_error",
        [
            AlreadyRunningError,
            NotRunningError,
            NotStartedError,
            NoLapsRecordedError,
            PausedStateError,
            NotPausedError,
        ],
    )
    def test_specific_errors_are_stopwatch_errors(
        self,
        specific_error: type[StopwatchError],
    ) -> None:
        """Test specific Stopwatch errors can be caught as StopwatchError."""
        assert issubclass(specific_error, StopwatchError)


class TestLifecycleOperations:
    """Test Stopwatch lifecycle state changes."""

    def test_initial_state(self, stopwatch: Stopwatch) -> None:
        """Test stopwatch initial state."""
        assert not stopwatch.is_running
        with pytest.raises(NotStartedError):
            _ = stopwatch.time_elapsed

    def test_start(self, stopwatch: Stopwatch) -> None:
        """Test starting the stopwatch."""
        stopwatch.start()  # time = 0.0
        assert stopwatch.is_running
        assert stopwatch.time_elapsed == 1.0  # time = 1.0

    def test_stop_returns_elapsed_time_and_freezes_it(
        self, stopwatch: Stopwatch
    ) -> None:
        """Test stop() returns the elapsed time and freezes it."""
        stopwatch.start()  # time = 0.0
        elapsed = stopwatch.stop()  # time = 1.0

        assert elapsed == 1.0
        assert stopwatch.time_elapsed == 1.0
        assert not stopwatch.is_running

    def test_reset(self, stopwatch: Stopwatch) -> None:
        """Test resetting the stopwatch."""
        stopwatch.start()
        stopwatch.lap()
        stopwatch.stop()
        stopwatch.reset()

        assert not stopwatch.is_running
        with pytest.raises(NotStartedError):
            _ = stopwatch.time_elapsed
        with pytest.raises(NoLapsRecordedError):
            _ = stopwatch.time_since_last_lap

    def test_reset_while_running_discards_measurement_and_allows_restart(
        self, mock_timer: Mock
    ) -> None:
        """Test running reset() discards state without calling callback."""
        callback = Mock()
        stopwatch = Stopwatch(timer_func=mock_timer, exit_callback=callback)

        stopwatch.start()
        stopwatch.lap()
        stopwatch.reset()

        assert not stopwatch.is_running
        with pytest.raises(NotStartedError):
            _ = stopwatch.time_elapsed
        with pytest.raises(NoLapsRecordedError):
            _ = stopwatch.time_since_last_lap
        callback.assert_not_called()

        stopwatch.start()
        elapsed_after_restart = stopwatch.stop()
        assert elapsed_after_restart == 1.0

    def test_start_after_reset(self, stopwatch: Stopwatch) -> None:
        """Test start() after reset()."""
        stopwatch.start()  # time = 0.0
        stopwatch.stop()  # time = 1.0
        stopwatch.reset()
        stopwatch.start()  # time = 2.0
        assert stopwatch.is_running

    def test_start_after_stop_starts_new_session(
        self, stopwatch: Stopwatch
    ) -> None:
        """Test stop() -> start() begins a new measurement session."""
        stopwatch.start()  # time = 0.0
        stopwatch.stop()  # time = 1.0
        stopwatch.start()  # time = 2.0

        assert stopwatch.is_running
        # A new measurement counts from the second start(), not the first.
        assert stopwatch.time_elapsed == 1.0  # time = 3.0


class TestRestart:
    """Test restart() beginning a fresh measurement from any state."""

    def test_restart_from_initial_state_starts_measurement(
        self, stopwatch: Stopwatch
    ) -> None:
        """Test restart() before start() begins a measurement."""
        stopwatch.restart()  # time = 0.0
        assert stopwatch.is_running
        assert stopwatch.time_elapsed == 1.0  # time = 1.0

    def test_restart_while_running_discards_measurement(self) -> None:
        """Test restart() while running counts from the restart."""
        timer = Mock(side_effect=[0.0, 2.0, 5.0])
        callback = Mock()
        stopwatch = Stopwatch(timer_func=timer, exit_callback=callback)

        stopwatch.start()  # time = 0.0
        stopwatch.restart()  # time = 2.0
        callback.assert_not_called()

        elapsed = stopwatch.stop()  # time = 5.0
        assert elapsed == 3.0
        callback.assert_called_once_with(3.0)

    def test_restart_after_stop_begins_new_measurement(
        self, stopwatch: Stopwatch
    ) -> None:
        """Test restart() after stop() begins a new measurement."""
        stopwatch.start()  # time = 0.0
        stopwatch.stop()  # time = 1.0
        stopwatch.restart()  # time = 2.0

        assert stopwatch.is_running
        assert stopwatch.time_elapsed == 1.0  # time = 3.0

    def test_restart_from_paused_discards_pause_state(self) -> None:
        """Test restart() from paused resumes measuring immediately."""
        timer = Mock(side_effect=[0.0, 2.0, 5.0, 9.0])
        stopwatch = Stopwatch(timer_func=timer)

        stopwatch.start()  # time = 0.0
        stopwatch.pause()  # time = 2.0
        stopwatch.restart()  # time = 5.0

        assert stopwatch.is_running
        assert not stopwatch.is_paused
        assert stopwatch.stop() == 4.0  # time = 9.0

    def test_restart_clears_lap_history(self, stopwatch: Stopwatch) -> None:
        """Test restart() clears previously recorded laps."""
        stopwatch.start()  # time = 0.0
        stopwatch.lap()  # time = 1.0
        stopwatch.restart()  # time = 2.0

        assert stopwatch.laps == ()
        with pytest.raises(NoLapsRecordedError):
            _ = stopwatch.time_since_last_lap


class TestInvalidLifecycleOperations:
    """Test invalid lifecycle transitions."""

    def test_start_already_running(self, stopwatch: Stopwatch) -> None:
        """Test starting an already running stopwatch raises error."""
        stopwatch.start()
        with pytest.raises(AlreadyRunningError):
            stopwatch.start()

    def test_stop_not_started(self, stopwatch: Stopwatch) -> None:
        """Test stopping a non-running stopwatch raises error."""
        with pytest.raises(NotRunningError):
            stopwatch.stop()

    def test_stop_already_stopped(self, stopwatch: Stopwatch) -> None:
        """Test stopping an already stopped stopwatch raises error."""
        stopwatch.start()
        stopwatch.stop()

        with pytest.raises(NotRunningError):
            stopwatch.stop()


class TestLapOperations:
    """Test lap recording functionality."""

    def test_lap(self, stopwatch: Stopwatch) -> None:
        """Test recording lap times."""
        stopwatch.start()  # time = 0.0
        lap1 = stopwatch.lap()  # time = 1.0
        assert lap1 == 1.0

        lap2 = stopwatch.lap()  # time = 2.0
        assert lap2 == 1.0

    def test_lap_keeps_total_elapsed_time_running(self) -> None:
        """Test lap() returns interval times without resetting total elapsed."""
        timer = Mock(side_effect=[0.0, 1.0, 3.0, 5.0, 8.0])
        stopwatch = Stopwatch(timer_func=timer)

        stopwatch.start()  # time = 0.0
        lap1 = stopwatch.lap()  # time = 1.0
        lap2 = stopwatch.lap()  # time = 3.0
        elapsed = stopwatch.time_elapsed  # time = 5.0
        stopped = stopwatch.stop()  # time = 8.0

        assert lap1 == 1.0
        assert lap2 == 2.0
        assert elapsed == 5.0
        assert stopped == 8.0

    def test_lap_not_started(self, stopwatch: Stopwatch) -> None:
        """Test recording lap on non-running stopwatch raises error."""
        with pytest.raises(NotRunningError):
            stopwatch.lap()

    def test_lap_after_stop_raises_not_running(
        self, stopwatch: Stopwatch
    ) -> None:
        """Test recording lap after stop() raises NotRunningError."""
        stopwatch.start()
        stopwatch.stop()

        with pytest.raises(NotRunningError):
            stopwatch.lap()

    def test_first_lap_after_restart_is_measured_from_restart(self) -> None:
        """Test first lap after restart uses the restart time."""
        timer = Mock(side_effect=[0.0, 1.0, 2.0, 3.0, 4.0])
        stopwatch = Stopwatch(timer_func=timer)

        stopwatch.start()  # time = 0.0
        stopwatch.lap()  # time = 1.0
        stopwatch.stop()  # time = 2.0
        stopwatch.start()  # time = 3.0
        lap_after_restart = stopwatch.lap()  # time = 4.0

        assert lap_after_restart == 1.0


class TestElapsedTime:
    """Test total elapsed time property access."""

    def test_running_returns_current_time_minus_start_time(self) -> None:
        """Test running elapsed time is computed from the start time."""
        timer = Mock(side_effect=[10.0, 13.0])
        stopwatch = Stopwatch(timer_func=timer)

        stopwatch.start()

        assert stopwatch.time_elapsed == 3.0

    def test_running_reflects_each_timer_read(self) -> None:
        """Test running elapsed time uses the current timer value."""
        timer = Mock(side_effect=[10.0, 13.0, 18.0])
        stopwatch = Stopwatch(timer_func=timer)

        stopwatch.start()

        assert stopwatch.time_elapsed == 3.0
        assert stopwatch.time_elapsed == 8.0

    def test_stopped_returns_stop_time_minus_start_time(self) -> None:
        """Test stopped elapsed time is computed from the stop time."""
        timer = Mock(side_effect=[10.0, 13.0])
        stopwatch = Stopwatch(timer_func=timer)

        stopwatch.start()
        stopwatch.stop()

        assert stopwatch.time_elapsed == 3.0

    def test_stopped_remains_fixed_across_reads(self) -> None:
        """Test stopped elapsed time remains the same after stop."""
        timer = Mock(side_effect=[10.0, 13.0, 18.0, 21.0])
        stopwatch = Stopwatch(timer_func=timer)

        stopwatch.start()
        stopwatch.stop()

        assert stopwatch.time_elapsed == 3.0
        assert stopwatch.time_elapsed == 3.0

    def test_stopped_does_not_depend_on_timer_after_stop(self) -> None:
        """Test stopped elapsed time does not require further timer reads."""
        timer = Mock(
            side_effect=[
                10.0,
                13.0,
                AssertionError("timer read after stop"),
            ],
        )
        stopwatch = Stopwatch(timer_func=timer)

        stopwatch.start()
        stopwatch.stop()

        assert stopwatch.time_elapsed == 3.0
        assert stopwatch.time_elapsed == 3.0

    def test_not_started_raises_not_started_error(
        self,
        stopwatch: Stopwatch,
    ) -> None:
        """Test getting elapsed time before starting raises error."""
        with pytest.raises(NotStartedError):
            _ = stopwatch.time_elapsed


class TestLapElapsedTime:
    """Test elapsed time since the last lap."""

    def test_time_since_last_lap_while_running(
        self, stopwatch: Stopwatch
    ) -> None:
        """Test getting elapsed time since last lap while running."""
        stopwatch.start()  # time = 0.0
        stopwatch.lap()  # time = 1.0
        last_lap = stopwatch.time_since_last_lap  # time = 2.0
        assert last_lap == 1.0

    def test_time_since_last_lap_while_running_uses_most_recent_lap(
        self,
    ) -> None:
        """Test running elapsed time uses the most recent lap."""
        timer = Mock(side_effect=[0.0, 1.0, 3.0, 8.0])
        stopwatch = Stopwatch(timer_func=timer)

        stopwatch.start()
        stopwatch.lap()
        stopwatch.lap()

        assert stopwatch.time_since_last_lap == 5.0

    def test_time_since_last_lap_after_stop(self, stopwatch: Stopwatch) -> None:
        """Test getting elapsed time since last lap after stopping."""
        stopwatch.start()  # time = 0.0
        stopwatch.lap()  # time = 1.0
        stopwatch.stop()  # time = 2.0
        last_lap = stopwatch.time_since_last_lap  # Should not call timer
        assert last_lap == 1.0

    def test_stopped_time_since_last_lap_does_not_read_timer(self) -> None:
        """Test stopped lap elapsed time does not read the timer."""
        timer = Mock(
            side_effect=[
                10.0,
                13.0,
                17.0,
                AssertionError("timer read after stop"),
            ],
        )
        stopwatch = Stopwatch(timer_func=timer)

        stopwatch.start()
        stopwatch.lap()
        stopwatch.stop()

        assert stopwatch.time_since_last_lap == 4.0
        assert stopwatch.time_since_last_lap == 4.0

    def test_time_since_last_lap_after_stop_uses_most_recent_lap(
        self,
    ) -> None:
        """Test stopped elapsed time uses the most recent lap."""
        timer = Mock(side_effect=[0.0, 1.0, 3.0, 10.0, 20.0, 30.0])
        stopwatch = Stopwatch(timer_func=timer)

        stopwatch.start()
        stopwatch.lap()
        stopwatch.lap()
        stopwatch.stop()

        assert stopwatch.time_since_last_lap == 7.0
        assert stopwatch.time_since_last_lap == 7.0

    def test_time_since_last_lap_no_laps(self, stopwatch: Stopwatch) -> None:
        """Test no laps raises error."""
        with pytest.raises(NoLapsRecordedError):
            _ = stopwatch.time_since_last_lap

    def test_time_since_last_lap_no_laps_after_start(
        self, stopwatch: Stopwatch
    ) -> None:
        """Test time_since_last_lap before any lap() raises error."""
        stopwatch.start()
        with pytest.raises(NoLapsRecordedError):
            _ = stopwatch.time_since_last_lap

    def test_time_since_last_lap_no_laps_after_stop(
        self, stopwatch: Stopwatch
    ) -> None:
        """Test stop() without lap() keeps time_since_last_lap unavailable."""
        stopwatch.start()
        stopwatch.stop()

        with pytest.raises(NoLapsRecordedError):
            _ = stopwatch.time_since_last_lap

    def test_start_after_stop_clears_lap_session_state(
        self, stopwatch: Stopwatch
    ) -> None:
        """Test stop() -> start() clears lap state for the new session."""
        stopwatch.start()
        stopwatch.lap()
        stopwatch.stop()
        stopwatch.start()
        with pytest.raises(NoLapsRecordedError):
            _ = stopwatch.time_since_last_lap


class TestLapHistory:
    """Test the recorded lap duration history."""

    def test_laps_returns_recorded_durations_in_order(self) -> None:
        """Test laps returns each lap duration in recording order."""
        timer = Mock(side_effect=[0.0, 1.0, 3.0, 6.0])
        stopwatch = Stopwatch(timer_func=timer)

        stopwatch.start()  # time = 0.0
        stopwatch.lap()  # time = 1.0
        stopwatch.lap()  # time = 3.0
        stopwatch.lap()  # time = 6.0

        assert stopwatch.laps == (1.0, 2.0, 3.0)

    def test_laps_is_empty_before_start(self, stopwatch: Stopwatch) -> None:
        """Test laps is empty before the stopwatch is started."""
        assert stopwatch.laps == ()

    def test_laps_is_empty_while_running_without_lap(
        self, stopwatch: Stopwatch
    ) -> None:
        """Test laps is empty while running with no recorded lap."""
        stopwatch.start()
        assert stopwatch.laps == ()

    def test_lap_appends_one_duration(self) -> None:
        """Test a single lap() records exactly one duration."""
        timer = Mock(side_effect=[0.0, 4.0])
        stopwatch = Stopwatch(timer_func=timer)

        stopwatch.start()  # time = 0.0
        stopwatch.lap()  # time = 4.0

        assert stopwatch.laps == (4.0,)

    def test_lap_records_interval_from_previous_boundary(self) -> None:
        """Test each recorded lap measures from the previous boundary."""
        timer = Mock(side_effect=[10.0, 11.0, 13.0])
        stopwatch = Stopwatch(timer_func=timer)

        stopwatch.start()  # time = 10.0
        stopwatch.lap()  # time = 11.0
        stopwatch.lap()  # time = 13.0

        assert stopwatch.laps == (1.0, 2.0)

    def test_start_clears_lap_history(self) -> None:
        """Test start() clears history from the previous session."""
        timer = Mock(side_effect=[0.0, 1.0, 2.0, 3.0])
        stopwatch = Stopwatch(timer_func=timer)

        stopwatch.start()  # time = 0.0
        stopwatch.lap()  # time = 1.0
        stopwatch.stop()  # time = 2.0
        stopwatch.start()  # time = 3.0

        assert stopwatch.laps == ()

    def test_reset_clears_lap_history(self) -> None:
        """Test reset() clears the recorded history."""
        timer = Mock(side_effect=[0.0, 1.0])
        stopwatch = Stopwatch(timer_func=timer)

        stopwatch.start()  # time = 0.0
        stopwatch.lap()  # time = 1.0
        stopwatch.reset()

        assert stopwatch.laps == ()

    def test_laps_returns_immutable_snapshot(self) -> None:
        """Test a returned laps snapshot is unaffected by later laps."""
        timer = Mock(side_effect=[0.0, 1.0, 3.0])
        stopwatch = Stopwatch(timer_func=timer)

        stopwatch.start()  # time = 0.0
        stopwatch.lap()  # time = 1.0
        snapshot = stopwatch.laps
        stopwatch.lap()  # time = 3.0

        assert snapshot == (1.0,)

    def test_lap_on_not_running_leaves_history_unchanged(self) -> None:
        """Test a failed lap() does not alter a non-empty history."""
        timer = Mock(side_effect=[0.0, 1.0, 3.0])
        stopwatch = Stopwatch(timer_func=timer)

        stopwatch.start()  # time = 0.0
        stopwatch.lap()  # time = 1.0
        stopwatch.stop()  # time = 3.0
        history_before = stopwatch.laps

        with pytest.raises(NotRunningError):
            stopwatch.lap()

        assert stopwatch.laps == history_before
        assert stopwatch.laps == (1.0, 2.0)


class TestStopFinalSegment:
    """Test the final segment recorded when the stopwatch is stopped."""

    def test_stop_appends_final_segment_to_history(self) -> None:
        """Test stop() appends the last lap-to-stop interval to history."""
        timer = Mock(side_effect=[0.0, 1.0, 3.0, 6.0])
        stopwatch = Stopwatch(timer_func=timer)

        stopwatch.start()  # time = 0.0
        stopwatch.lap()  # time = 1.0
        stopwatch.lap()  # time = 3.0
        stopwatch.stop()  # time = 6.0

        assert stopwatch.laps == (1.0, 2.0, 3.0)

    def test_stop_without_lap_records_single_total_segment(self) -> None:
        """Test stop() without any lap records one segment of total time."""
        timer = Mock(side_effect=[10.0, 14.0])
        stopwatch = Stopwatch(timer_func=timer)

        stopwatch.start()  # time = 10.0
        stopwatch.stop()  # time = 14.0

        assert stopwatch.laps == (4.0,)

    def test_lap_durations_sum_equals_elapsed_after_stop(self) -> None:
        """Test the sum of recorded durations equals the total elapsed time."""
        timer = Mock(side_effect=[0.0, 1.0, 3.0, 6.0])
        stopwatch = Stopwatch(timer_func=timer)

        stopwatch.start()  # time = 0.0
        stopwatch.lap()  # time = 1.0
        stopwatch.lap()  # time = 3.0
        elapsed = stopwatch.stop()  # time = 6.0

        assert sum(stopwatch.laps) == elapsed
        assert sum(stopwatch.laps) == stopwatch.time_elapsed

    def test_stop_on_not_running_leaves_history_unchanged(
        self, stopwatch: Stopwatch
    ) -> None:
        """Test a stop() on a not-running stopwatch does not touch history."""
        with pytest.raises(NotRunningError):
            stopwatch.stop()

        assert stopwatch.laps == ()

    def test_stop_does_not_append_when_stop_time_unavailable(self) -> None:
        """Test a failing stop() timer read leaves history and state intact."""
        timer = Mock(side_effect=[0.0, 1.0, RuntimeError("timer failed")])
        stopwatch = Stopwatch(timer_func=timer)

        stopwatch.start()  # time = 0.0
        stopwatch.lap()  # time = 1.0

        with pytest.raises(RuntimeError):
            stopwatch.stop()  # timer raises

        assert stopwatch.is_running
        assert stopwatch.laps == (1.0,)

    def test_stop_on_not_running_with_history_leaves_history_unchanged(
        self,
    ) -> None:
        """Test a failed stop() does not alter an already recorded history."""
        timer = Mock(side_effect=[0.0, 1.0, 3.0])
        stopwatch = Stopwatch(timer_func=timer)

        stopwatch.start()  # time = 0.0
        stopwatch.lap()  # time = 1.0
        stopwatch.stop()  # time = 3.0
        history_before = stopwatch.laps

        with pytest.raises(NotRunningError):
            stopwatch.stop()

        assert stopwatch.laps == history_before
        assert stopwatch.laps == (1.0, 2.0)


class TestContextManager:
    """Test context manager functionality."""

    def test_context_manager(self, stopwatch: Stopwatch) -> None:
        """Test using stopwatch as context manager."""
        with stopwatch as sw:
            assert sw.is_running
            assert sw is stopwatch
        assert not stopwatch.is_running

    def test_nested_same_context_manager_raises_already_running(
        self,
        stopwatch: Stopwatch,
    ) -> None:
        """Test nesting the same stopwatch context manager raises error."""
        with (
            pytest.raises(AlreadyRunningError),
            stopwatch,
            stopwatch,
        ):
            pass

        assert not stopwatch.is_running

    def test_context_manager_with_exception(self, stopwatch: Stopwatch) -> None:
        """Test context manager stops even on exception."""

        def _raise_while_stopwatch_running() -> None:
            with stopwatch:
                assert stopwatch.is_running
                raise ValueError("Test exception")

        with pytest.raises(ValueError, match="Test exception"):
            _raise_while_stopwatch_running()

        assert not stopwatch.is_running
        assert stopwatch.time_elapsed == 1.0

    def test_context_manager_early_stop(self, stopwatch: Stopwatch) -> None:
        """Test context manager does not raise when stop() already called."""
        with stopwatch:
            stopwatch.stop()
        assert not stopwatch.is_running

    def test_context_manager_early_stop_with_exception(
        self, stopwatch: Stopwatch
    ) -> None:
        """Test original exception is not masked when stop() called early."""

        def _trigger() -> None:
            with stopwatch:
                stopwatch.stop()
                raise ValueError("early stop")

        with pytest.raises(ValueError, match="early stop"):
            _trigger()

    def test_context_manager_preserves_exception_when_stop_timer_fails(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Test stop timer failure does not replace block exception."""
        timer = Mock(side_effect=[0.0, RuntimeError("timer failed")])
        callback = Mock()
        stopwatch = Stopwatch(timer_func=timer, exit_callback=callback)

        def _trigger() -> None:
            with stopwatch:
                raise ValueError("body failed")

        with (
            caplog.at_level(logging.ERROR, logger="ticko"),
            pytest.raises(ValueError, match="body failed"),
        ):
            _trigger()

        callback.assert_not_called()
        assert stopwatch.is_running
        assert any(
            record.levelno >= logging.ERROR
            and (record.name == "ticko" or record.name.startswith("ticko."))
            and record.exc_info is not None
            and isinstance(record.exc_info[1], RuntimeError)
            and str(record.exc_info[1]) == "timer failed"
            for record in caplog.records
        )

    def test_exception_cleanup_failure_stderr_is_silent_by_default(
        self,
        capsys: pytest.CaptureFixture[str],
        root_logger_without_handlers: Callable[
            [],
            AbstractContextManager[logging.Logger],
        ],
    ) -> None:
        """Test cleanup diagnostics stay silent without application logging."""
        timer = Mock(side_effect=[0.0, RuntimeError("timer failed")])
        stopwatch = Stopwatch(timer_func=timer)

        with root_logger_without_handlers() as root_logger:
            assert root_logger.handlers == []
            with (
                pytest.raises(ValueError, match="body failed"),
                stopwatch,
            ):
                raise ValueError("body failed")

        captured = capsys.readouterr()
        assert captured.err == ""

    def test_context_manager_raises_stop_failure_without_active_exception(
        self,
    ) -> None:
        """Test context manager raises stop failure without block exception."""
        timer = Mock(side_effect=[0.0, RuntimeError("timer failed")])
        callback = Mock()
        stopwatch = Stopwatch(timer_func=timer, exit_callback=callback)

        with (
            pytest.raises(RuntimeError, match="timer failed"),
            stopwatch,
        ):
            pass

        callback.assert_not_called()
        assert stopwatch.is_running


class TestExitCallbacks:
    """Test callback functionality."""

    @pytest.fixture
    def exit_callback_mock(self) -> Mock:
        """Create an exit callback mock."""
        return Mock()

    @pytest.fixture
    def stopwatch_with_exit_callback(
        self,
        mock_timer: Mock,
        exit_callback_mock: Mock,
    ) -> Stopwatch:
        """Create a stopwatch with a mock exit callback."""
        return Stopwatch(
            timer_func=mock_timer,
            exit_callback=exit_callback_mock,
        )

    def test_exit_callback(
        self,
        stopwatch_with_exit_callback: Stopwatch,
        exit_callback_mock: Mock,
    ) -> None:
        """Test exit callback is called when stopping."""
        stopwatch_with_exit_callback.start()
        stopwatch_with_exit_callback.stop()
        exit_callback_mock.assert_called_once_with(1.0)

    def test_exit_callback_not_called_when_stop_not_started(
        self,
        stopwatch_with_exit_callback: Stopwatch,
        exit_callback_mock: Mock,
    ) -> None:
        """Test exit callback is not called when stop() before start()."""
        with pytest.raises(NotRunningError):
            stopwatch_with_exit_callback.stop()

        exit_callback_mock.assert_not_called()

    def test_exit_callback_not_called_when_stop_already_stopped(
        self,
        stopwatch_with_exit_callback: Stopwatch,
        exit_callback_mock: Mock,
    ) -> None:
        """Test exit callback is not called when stop() after stop()."""
        stopwatch_with_exit_callback.start()
        stopwatch_with_exit_callback.stop()
        exit_callback_mock.reset_mock()

        with pytest.raises(NotRunningError):
            stopwatch_with_exit_callback.stop()

        exit_callback_mock.assert_not_called()

    def test_exit_callback_not_called_when_stop_timer_fails(self) -> None:
        """Test exit callback is not called when stop() cannot read time."""
        timer = Mock(side_effect=[0.0, RuntimeError("timer error")])
        callback = Mock()
        sw = Stopwatch(timer_func=timer, exit_callback=callback)
        sw.start()

        with pytest.raises(RuntimeError, match="timer error"):
            sw.stop()

        callback.assert_not_called()
        assert sw.is_running

    def test_exit_callback_not_called_on_reset_before_start(
        self,
        stopwatch_with_exit_callback: Stopwatch,
        exit_callback_mock: Mock,
    ) -> None:
        """Test exit callback is not called on reset() before start()."""
        stopwatch_with_exit_callback.reset()

        exit_callback_mock.assert_not_called()

    def test_exit_callback_not_called_on_reset_while_running(
        self,
        stopwatch_with_exit_callback: Stopwatch,
        exit_callback_mock: Mock,
    ) -> None:
        """Test exit callback is not called on reset() while running."""
        stopwatch_with_exit_callback.start()
        stopwatch_with_exit_callback.reset()
        exit_callback_mock.assert_not_called()

    def test_exit_callback_not_called_on_reset_after_stop(
        self,
        stopwatch_with_exit_callback: Stopwatch,
        exit_callback_mock: Mock,
    ) -> None:
        """Test exit callback is not called on reset() after stop()."""
        stopwatch_with_exit_callback.start()
        stopwatch_with_exit_callback.stop()
        exit_callback_mock.reset_mock()

        stopwatch_with_exit_callback.reset()

        exit_callback_mock.assert_not_called()

    def test_exit_callback_with_exception(
        self, mock_timer: Mock, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test exit callback that raises exception is handled."""
        callback = Mock(side_effect=RuntimeError("Callback error"))
        sw = Stopwatch(timer_func=mock_timer, exit_callback=callback)
        sw.start()
        with caplog.at_level(logging.ERROR, logger="ticko"):
            elapsed = sw.stop()

        assert elapsed == 1.0
        callback.assert_called_once_with(1.0)
        assert any(
            record.levelno >= logging.ERROR
            and (record.name == "ticko" or record.name.startswith("ticko."))
            and record.exc_info is not None
            and isinstance(record.exc_info[1], RuntimeError)
            for record in caplog.records
        )

    def test_exit_callback_exception_stderr_is_silent_by_default(
        self,
        capsys: pytest.CaptureFixture[str],
        root_logger_without_handlers: Callable[
            [],
            AbstractContextManager[logging.Logger],
        ],
    ) -> None:
        """Test unconfigured applications do not receive stderr logs."""

        def raise_callback(_elapsed: float) -> None:
            raise RuntimeError("callback failed")

        timer_values = iter([0.0, 1.0])
        sw = Stopwatch(
            timer_func=timer_values.__next__,
            exit_callback=raise_callback,
        )

        with root_logger_without_handlers() as root_logger:
            assert root_logger.handlers == []
            sw.start()
            assert sw.stop() == 1.0

        captured = capsys.readouterr()
        assert captured.err == ""

    def test_exit_callback_exception_reaches_application_handler(
        self,
        mock_timer: Mock,
    ) -> None:
        """Test application-owned ticko handlers receive diagnostics."""
        callback = Mock(side_effect=RuntimeError("Callback error"))
        sw = Stopwatch(timer_func=mock_timer, exit_callback=callback)
        handler = DiagnosticRecordHandler()
        ticko_logger = logging.getLogger("ticko")
        previous_level = ticko_logger.level

        sw.start()
        ticko_logger.addHandler(handler)
        ticko_logger.setLevel(logging.ERROR)
        try:
            elapsed = sw.stop()
        finally:
            ticko_logger.removeHandler(handler)
            ticko_logger.setLevel(previous_level)

        assert elapsed == 1.0
        assert any(
            record.levelno >= logging.ERROR
            and (record.name == "ticko" or record.name.startswith("ticko."))
            and record.exc_info is not None
            and isinstance(record.exc_info[1], RuntimeError)
            for record in handler.records
        )


class TestTimerFunction:
    """Test custom timer function behavior."""

    def test_custom_timer_func(self) -> None:
        """Test using custom timer function."""
        custom_timer = Mock(side_effect=[10.0, 20.0, 30.0])
        sw = Stopwatch(timer_func=custom_timer)
        sw.start()
        elapsed = sw.stop()
        assert elapsed == 10.0
        assert custom_timer.call_count == 2

    def test_custom_timer_values_drive_elapsed_time(self) -> None:
        """Test elapsed time is computed from custom timer values."""
        custom_timer = Mock(side_effect=[1000.0, 1003.5])
        sw = Stopwatch(timer_func=custom_timer)

        sw.start()
        elapsed = sw.stop()

        assert elapsed == 3.5
        assert sw.time_elapsed == 3.5


class TestNameOption:
    """Test Stopwatch name parameter."""

    def test_name_default_is_none(self, stopwatch: Stopwatch) -> None:
        """Test default name is None."""
        assert stopwatch.name is None

    def test_name_set(self, mock_timer: Mock) -> None:
        """Test name is stored correctly."""
        sw = Stopwatch(name="my_sw", timer_func=mock_timer)
        assert sw.name == "my_sw"

    def test_log_includes_name_on_start(
        self, mock_timer: Mock, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test log message includes name on start."""
        sw = Stopwatch(name="timer_a", timer_func=mock_timer)
        with caplog.at_level(logging.DEBUG, logger="ticko"):
            sw.start()
        assert any(
            record.levelno == logging.DEBUG
            and (record.name == "ticko" or record.name.startswith("ticko."))
            and "timer_a" in record.getMessage()
            for record in caplog.records
        )

    def test_log_includes_name_on_stop(
        self, mock_timer: Mock, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test log message includes name on stop."""
        sw = Stopwatch(name="timer_b", timer_func=mock_timer)
        sw.start()
        with caplog.at_level(logging.DEBUG, logger="ticko"):
            sw.stop()
        assert any(
            record.levelno == logging.DEBUG
            and (record.name == "ticko" or record.name.startswith("ticko."))
            and "timer_b" in record.getMessage()
            for record in caplog.records
        )


class TestRepr:
    """Test Stopwatch constructor-style representation contract."""

    def test_repr_returns_default_constructor_form(self) -> None:
        """Test default __repr__ uses the public constructor form."""
        assert repr(Stopwatch()) == (
            "Stopwatch(timer_func=time.perf_counter, exit_callback=None)"
        )

    def test_repr_includes_name_argument_when_set(self) -> None:
        """Test __repr__ includes name as a constructor argument."""
        sw = Stopwatch(name="db", timer_func=repr_contract_timer)
        assert repr(sw) == (
            "Stopwatch("
            f"name='db', timer_func={__name__}.repr_contract_timer, "
            "exit_callback=None)"
        )

    def test_repr_omits_name_argument_when_none(self) -> None:
        """Test __repr__ omits the name argument when name is None."""
        sw = Stopwatch(timer_func=repr_contract_timer)
        assert repr(sw) == (
            "Stopwatch("
            f"timer_func={__name__}.repr_contract_timer, "
            "exit_callback=None)"
        )

    def test_repr_includes_qualified_callback_name(self) -> None:
        """Test __repr__ includes callback as a qualified callable name."""
        sw = Stopwatch(
            timer_func=repr_contract_timer,
            exit_callback=repr_contract_callback,
        )
        assert repr(sw) == (
            "Stopwatch("
            f"timer_func={__name__}.repr_contract_timer, "
            f"exit_callback={__name__}.repr_contract_callback)"
        )

    def test_repr_is_independent_of_state(self) -> None:
        """Test __repr__ only represents construction inputs."""
        timer_values = iter([0.0, 1.0])

        def state_timer() -> float:
            """Return the next state-transition timer value."""
            return next(timer_values)

        sw = Stopwatch(timer_func=state_timer)
        expected_timer_name = (
            f"{state_timer.__module__}.{state_timer.__qualname__}"
        )
        expected = (
            f"Stopwatch(timer_func={expected_timer_name}, exit_callback=None)"
        )

        repr_not_started = repr(sw)
        sw.start()
        repr_running = repr(sw)
        sw.stop()
        repr_stopped = repr(sw)

        assert repr_not_started == expected
        assert repr_running == expected
        assert repr_stopped == expected


class TestStr:
    """Test Stopwatch human-readable string representation."""

    def test_str_not_started(self, stopwatch: Stopwatch) -> None:
        """Test __str__ when not started."""
        str_str = str(stopwatch)
        assert "Stopwatch" in str_str
        assert "not started" in str_str

    def test_str_running(self, stopwatch: Stopwatch) -> None:
        """Test __str__ while running."""
        stopwatch.start()  # time = 0.0
        str_str = str(stopwatch)  # time = 1.0
        assert "Stopwatch" in str_str
        assert "running" in str_str
        assert_elapsed_seconds_displayed(str_str, 1.0)

    def test_str_stopped(self, stopwatch: Stopwatch) -> None:
        """Test __str__ after stopping."""
        stopwatch.start()  # time = 0.0
        stopwatch.stop()  # time = 1.0
        str_str = str(stopwatch)
        assert "Stopwatch" in str_str
        assert "stopped" in str_str
        assert_elapsed_seconds_displayed(str_str, 1.0)

    def test_str_includes_name_not_started(self, mock_timer: Mock) -> None:
        """Test __str__ includes name when not started."""
        sw = Stopwatch(name="db", timer_func=mock_timer)
        assert "'db'" in str(sw)
        assert "not started" in str(sw)

    def test_str_includes_name_running(self, mock_timer: Mock) -> None:
        """Test __str__ includes name while running."""
        sw = Stopwatch(name="db", timer_func=mock_timer)
        sw.start()  # time = 0.0
        result = str(sw)  # time = 1.0
        assert "'db'" in result
        assert "running" in result

    def test_str_includes_name_stopped(self, mock_timer: Mock) -> None:
        """Test __str__ includes name after stopping."""
        sw = Stopwatch(name="db", timer_func=mock_timer)
        sw.start()  # time = 0.0
        sw.stop()  # time = 1.0
        result = str(sw)
        assert "'db'" in result
        assert "stopped" in result

    def test_str_changes_with_state(self, stopwatch: Stopwatch) -> None:
        """Test __str__ changes based on stopwatch state."""
        str_not_started = str(stopwatch)
        stopwatch.start()
        str_running = str(stopwatch)
        stopwatch.stop()
        str_stopped = str(stopwatch)
        assert "not started" in str_not_started
        assert "running" in str_running
        assert "stopped" in str_stopped

    def test_str_vs_repr(self, stopwatch: Stopwatch) -> None:
        """Test that __str__ and __repr__ return different values."""
        str_str = str(stopwatch)
        repr_str = repr(stopwatch)
        assert str_str != repr_str
        assert "not started" in str_str
        assert "timer_func=" in repr_str


class TestRealTimeMeasurement:
    """Test Stopwatch with real time functions."""

    def test_real_elapsed_time(self) -> None:
        """Test with real time.perf_counter."""
        sw = Stopwatch()
        sw.start()
        time.sleep(0.1)
        elapsed = sw.stop()
        assert elapsed > 0.09

    def test_real_lap_time(self) -> None:
        """Test lap times with real timer."""
        sw = Stopwatch()
        sw.start()
        time.sleep(0.05)
        lap1 = sw.lap()
        time.sleep(0.05)
        lap2 = sw.lap()
        sw.stop()

        assert lap1 > 0.04
        assert lap2 > 0.04


class TestPauseResume:
    """Test pause/resume measurement behavior."""

    def test_pause_freezes_elapsed_and_clears_running(self) -> None:
        """Test pause() stops elapsed from advancing and clears running."""
        timer = Mock(side_effect=[0.0, 2.0, 5.0, 9.0])
        stopwatch = Stopwatch(timer_func=timer)

        stopwatch.start()  # time = 0.0
        stopwatch.pause()  # time = 2.0

        assert not stopwatch.is_running
        assert stopwatch.time_elapsed == 2.0  # frozen, no timer read
        assert stopwatch.time_elapsed == 2.0

    def test_resume_restores_running_and_continues_measuring(self) -> None:
        """Test resume() restores running and measurement continues."""
        timer = Mock(side_effect=[0.0, 2.0, 5.0, 8.0])
        stopwatch = Stopwatch(timer_func=timer)

        stopwatch.start()  # time = 0.0
        stopwatch.pause()  # time = 2.0
        stopwatch.resume()  # time = 5.0

        assert stopwatch.is_running
        assert stopwatch.time_elapsed == 5.0  # time = 8.0, active = 8-5+2

    def test_time_elapsed_excludes_paused_interval(self) -> None:
        """Test time_elapsed excludes the pause interval."""
        timer = Mock(side_effect=[0.0, 2.0, 5.0, 9.0])
        stopwatch = Stopwatch(timer_func=timer)

        stopwatch.start()  # time = 0.0
        stopwatch.pause()  # time = 2.0, active = 2.0
        stopwatch.resume()  # time = 5.0, paused interval = 3.0

        # time = 9.0; active = (9 - 5) + 2 = 6, paused 3.0 excluded
        assert stopwatch.time_elapsed == 6.0

    def test_stop_return_excludes_paused_interval(self) -> None:
        """Test stop() return value excludes the pause interval."""
        timer = Mock(side_effect=[0.0, 2.0, 5.0, 9.0])
        stopwatch = Stopwatch(timer_func=timer)

        stopwatch.start()  # time = 0.0
        stopwatch.pause()  # time = 2.0
        stopwatch.resume()  # time = 5.0
        elapsed = stopwatch.stop()  # time = 9.0

        assert elapsed == 6.0
        assert stopwatch.time_elapsed == 6.0

    def test_time_since_last_lap_excludes_paused_interval(self) -> None:
        """Test time_since_last_lap excludes a pause after the last lap."""
        timer = Mock(side_effect=[0.0, 1.0, 4.0, 7.0, 11.0])
        stopwatch = Stopwatch(timer_func=timer)

        stopwatch.start()  # time = 0.0
        stopwatch.lap()  # time = 1.0
        stopwatch.pause()  # time = 4.0, active since lap = 3.0
        stopwatch.resume()  # time = 7.0, paused interval = 3.0

        # time = 11.0; active since lap = (11 - 7) + 3 = 7
        assert stopwatch.time_since_last_lap == 7.0

    def test_time_since_last_lap_frozen_while_paused(self) -> None:
        """Test time_since_last_lap is frozen while paused."""
        timer = Mock(side_effect=[0.0, 1.0, 4.0])
        stopwatch = Stopwatch(timer_func=timer)

        stopwatch.start()  # time = 0.0
        stopwatch.lap()  # time = 1.0
        stopwatch.pause()  # time = 4.0, active since lap = 3.0

        # Read while still paused: frozen, no further timer call.
        assert stopwatch.time_since_last_lap == 3.0
        assert stopwatch.time_since_last_lap == 3.0

    def test_laps_sum_equals_elapsed_with_pause(self) -> None:
        """Test sum(laps) equals time_elapsed across a pause."""
        timer = Mock(side_effect=[0.0, 2.0, 5.0, 7.0, 11.0])
        stopwatch = Stopwatch(timer_func=timer)

        stopwatch.start()  # time = 0.0
        stopwatch.lap()  # time = 2.0
        stopwatch.pause()  # time = 5.0
        stopwatch.resume()  # time = 7.0, paused interval = 2.0
        elapsed = stopwatch.stop()  # time = 11.0

        assert sum(stopwatch.laps) == elapsed
        assert sum(stopwatch.laps) == stopwatch.time_elapsed

    def test_elapsed_excludes_all_pause_intervals(self) -> None:
        """Test elapsed excludes every pause across multiple cycles."""
        timer = Mock(side_effect=[0.0, 2.0, 5.0, 8.0, 12.0, 15.0])
        stopwatch = Stopwatch(timer_func=timer)

        stopwatch.start()  # t=0
        stopwatch.pause()  # t=2, active 2
        stopwatch.resume()  # t=5, paused 3
        stopwatch.pause()  # t=8, active +3 = 5
        stopwatch.resume()  # t=12, paused 4
        elapsed = stopwatch.stop()  # t=15, active +3 = 8

        # Both pauses (3 + 4) excluded; active total is 2 + 3 + 3 = 8.
        assert elapsed == 8.0
        assert stopwatch.time_elapsed == 8.0
        assert sum(stopwatch.laps) == 8.0

    def test_lap_after_resume_excludes_paused_interval(self) -> None:
        """Test a lap() spanning a pause excludes the paused interval."""
        timer = Mock(side_effect=[0.0, 2.0, 5.0, 9.0, 12.0])
        stopwatch = Stopwatch(timer_func=timer)

        stopwatch.start()  # t=0
        stopwatch.lap()  # t=2, first segment = 2
        stopwatch.pause()  # t=5
        stopwatch.resume()  # t=9, paused 4
        second_lap = stopwatch.lap()  # t=12, active since lap = 3 + 3 = 6

        assert second_lap == 6.0

    def test_reset_clears_paused_state(self) -> None:
        """Test reset() from paused returns to the not-started state."""
        timer = Mock(side_effect=[0.0, 2.0])
        stopwatch = Stopwatch(timer_func=timer)

        stopwatch.start()  # time = 0.0
        stopwatch.pause()  # time = 2.0
        stopwatch.reset()

        assert not stopwatch.is_running
        assert stopwatch.laps == ()
        with pytest.raises(NotStartedError):
            _ = stopwatch.time_elapsed


class TestPauseResumeStr:
    """Test __str__ while paused."""

    def test_str_paused_reports_paused_without_raising(self) -> None:
        """Test str() of a paused stopwatch reports a pause-excluded time."""
        timer = Mock(side_effect=[0.0, 2.0])
        stopwatch = Stopwatch(timer_func=timer)

        stopwatch.start()  # time = 0.0
        stopwatch.pause()  # time = 2.0
        result = str(stopwatch)

        assert "Stopwatch" in result
        assert "paused" in result
        assert_elapsed_seconds_displayed(result, 2.0)


class TestIsPausedProperty:
    """Test the is_paused state observer."""

    @pytest.mark.parametrize(
        ("operations", "expected"),
        [
            ([], False),
            (["start"], False),
            (["start", "pause"], True),
            (["start", "pause", "resume"], False),
            (["start", "stop"], False),
            (["start", "pause", "reset"], False),
        ],
        ids=["initial", "running", "paused", "resumed", "stopped", "reset"],
    )
    def test_is_paused_reflects_state(
        self,
        stopwatch: Stopwatch,
        operations: list[str],
        expected: bool,  # noqa: FBT001 - parametrized expected value
    ) -> None:
        """Test is_paused is True exactly while paused."""
        for operation in operations:
            getattr(stopwatch, operation)()
        assert stopwatch.is_paused is expected


class TestPauseResumeErrors:
    """Test degenerate transitions involving pause/resume."""

    @pytest.fixture
    def paused_stopwatch(self) -> Stopwatch:
        """Create a stopwatch in the paused state."""
        timer = Mock(side_effect=[0.0, 2.0, 5.0])
        stopwatch = Stopwatch(timer_func=timer)

        stopwatch.start()
        stopwatch.pause()
        return stopwatch

    @pytest.mark.parametrize(
        "operation",
        [
            Stopwatch.pause,
            Stopwatch.start,
            Stopwatch.lap,
            Stopwatch.stop,
        ],
        ids=["pause", "start", "lap", "stop"],
    )
    def test_operations_while_paused_raise_paused_state(
        self,
        paused_stopwatch: Stopwatch,
        operation: Callable[[Stopwatch], object],
    ) -> None:
        """Test paused-only blocked operations raise PausedStateError."""
        with pytest.raises(PausedStateError):
            operation(paused_stopwatch)
        assert not paused_stopwatch.is_running
        assert paused_stopwatch.time_elapsed == 2.0
        # Still paused (not stopped), so resume must succeed.
        paused_stopwatch.resume()
        assert paused_stopwatch.is_running

    def test_resume_not_started_raises_not_paused(
        self, stopwatch: Stopwatch
    ) -> None:
        """Test resume() before start raises NotPausedError."""
        with pytest.raises(NotPausedError):
            stopwatch.resume()
        # State preserved: still not-started.
        assert not stopwatch.is_running
        with pytest.raises(NotStartedError):
            _ = stopwatch.time_elapsed

    def test_resume_while_running_raises_not_paused(
        self, stopwatch: Stopwatch
    ) -> None:
        """Test resume() while running raises NotPausedError."""
        stopwatch.start()
        with pytest.raises(NotPausedError):
            stopwatch.resume()
        assert stopwatch.is_running

    def test_resume_after_stop_raises_not_paused(
        self, stopwatch: Stopwatch
    ) -> None:
        """Test resume() after stop raises NotPausedError."""
        stopwatch.start()
        stopwatch.stop()
        elapsed_before = stopwatch.time_elapsed
        with pytest.raises(NotPausedError):
            stopwatch.resume()
        # State preserved: still stopped with unchanged elapsed.
        assert not stopwatch.is_running
        assert stopwatch.time_elapsed == elapsed_before

    def test_pause_not_started_raises_not_running(
        self, stopwatch: Stopwatch
    ) -> None:
        """Test pause() before start raises NotRunningError."""
        with pytest.raises(NotRunningError):
            stopwatch.pause()
        # State preserved: still not-started.
        assert not stopwatch.is_running
        with pytest.raises(NotStartedError):
            _ = stopwatch.time_elapsed

    def test_pause_after_stop_raises_not_running(
        self, stopwatch: Stopwatch
    ) -> None:
        """Test pause() after stop raises NotRunningError."""
        stopwatch.start()
        stopwatch.stop()
        elapsed_before = stopwatch.time_elapsed
        with pytest.raises(NotRunningError):
            stopwatch.pause()
        # State preserved: still stopped with unchanged elapsed.
        assert not stopwatch.is_running
        assert stopwatch.time_elapsed == elapsed_before


class TestPauseExitCallback:
    """Test exit_callback interaction with pause/resume."""

    def test_pause_does_not_invoke_exit_callback(
        self, mock_timer: Mock
    ) -> None:
        """Test pause() does not invoke exit_callback."""
        callback = Mock()
        stopwatch = Stopwatch(timer_func=mock_timer, exit_callback=callback)

        stopwatch.start()
        stopwatch.pause()

        callback.assert_not_called()

    def test_context_manager_exit_finalizes_paused_watch(self) -> None:
        """Test exiting a context manager while paused stops and reports."""
        timer = Mock(side_effect=[0.0, 2.0, 5.0])
        callback = Mock()
        stopwatch = Stopwatch(timer_func=timer, exit_callback=callback)

        with stopwatch:  # start, time = 0.0
            stopwatch.pause()  # time = 2.0

        assert not stopwatch.is_running
        assert stopwatch.time_elapsed == 2.0
        with pytest.raises(NotPausedError):
            stopwatch.resume()

    def test_paused_exit_callback_exception_is_logged_not_raised(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test a raising callback on paused exit logs without propagating."""
        timer = Mock(side_effect=[0.0, 2.0])
        callback = Mock(side_effect=RuntimeError("Callback error"))
        stopwatch = Stopwatch(timer_func=timer, exit_callback=callback)

        with caplog.at_level(logging.ERROR, logger="ticko"), stopwatch:
            stopwatch.pause()  # time = 2.0

        callback.assert_called_once_with(2.0)
        assert stopwatch.time_elapsed == 2.0
        assert any(
            record.levelno >= logging.ERROR
            and (record.name == "ticko" or record.name.startswith("ticko."))
            and record.exc_info is not None
            and isinstance(record.exc_info[1], RuntimeError)
            for record in caplog.records
        )
        callback.assert_called_once_with(2.0)
