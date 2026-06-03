"""Tests for the Stopwatch class."""

import logging
import time
from typing import Literal
from unittest.mock import Mock

import pytest
from _timing_output_assertions import assert_elapsed_seconds_displayed

from ticko import (
    AlreadyRunningError,
    NoLapsRecordedError,
    NotRunningError,
    NotStartedError,
    Stopwatch,
    StopwatchError,
)


@pytest.fixture
def mock_timer() -> Mock:
    """Create a mock timer function."""
    return Mock(side_effect=[0.0, 1.0, 2.0, 3.0, 4.0, 5.0])


@pytest.fixture
def stopwatch(mock_timer: Mock) -> Stopwatch:
    """Create a Stopwatch instance with mock timer."""
    return Stopwatch(timer_func=mock_timer)


def repr_contract_timer() -> float:
    """Return a stable timer value for repr contract tests."""
    return 0.0


def repr_contract_callback(_elapsed: float) -> None:
    """Accept elapsed time for repr contract tests."""


class TestStopwatchExceptionHierarchy:
    """Test public Stopwatch exception relationships."""

    @pytest.mark.parametrize(
        "specific_error",
        [
            AlreadyRunningError,
            NotRunningError,
            NotStartedError,
            NoLapsRecordedError,
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
        assert stopwatch.time_start is None
        assert stopwatch.time_stop is None

    def test_start(self, stopwatch: Stopwatch) -> None:
        """Test starting the stopwatch."""
        stopwatch.start()
        assert stopwatch.is_running
        assert stopwatch.time_start == 0.0
        assert stopwatch.time_stop is None

    def test_stop_records_stop_time_and_returns_elapsed_time(
        self, stopwatch: Stopwatch
    ) -> None:
        """Test stop() stores the stop time and returns the elapsed time."""
        stopwatch.start()  # time = 0.0
        elapsed = stopwatch.stop()  # time = 1.0

        time_start = stopwatch.time_start
        time_stop = stopwatch.time_stop

        assert time_start is not None
        assert time_stop is not None
        assert time_start == 0.0
        assert time_stop == 1.0
        assert elapsed == time_stop - time_start
        assert not stopwatch.is_running

    def test_reset(self, stopwatch: Stopwatch) -> None:
        """Test resetting the stopwatch."""
        stopwatch.start()
        stopwatch.lap()
        stopwatch.stop()
        stopwatch.reset()

        assert not stopwatch.is_running
        assert stopwatch.time_start is None
        assert stopwatch.time_stop is None
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
        assert stopwatch.time_start is None
        assert stopwatch.time_stop is None
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
        assert stopwatch.time_start == 2.0
        assert stopwatch.time_stop is None


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
        with (  # noqa: PT012
            pytest.raises(ValueError, match="Test exception"),
            stopwatch,
        ):
            assert stopwatch.is_running
            raise ValueError("Test exception")
        assert not stopwatch.is_running
        assert stopwatch.time_stop is not None

    def test_context_manager_early_stop(self, stopwatch: Stopwatch) -> None:
        """Test context manager does not raise when stop() already called."""
        with stopwatch:
            stopwatch.stop()
        # __exit__ should not raise even though stopwatch is already stopped
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


class TestExitCallbacks:
    """Test callback functionality."""

    def test_exit_callback(self, mock_timer: Mock) -> None:
        """Test exit callback is called when stopping."""
        callback = Mock()
        sw = Stopwatch(timer_func=mock_timer, exit_callback=callback)
        sw.start()
        sw.stop()
        callback.assert_called_once_with(1.0)

    @pytest.mark.parametrize(
        "stop_failure_state",
        ["not_started", "already_stopped"],
    )
    def test_exit_callback_not_called_when_stop_is_not_running(
        self,
        mock_timer: Mock,
        stop_failure_state: Literal["not_started", "already_stopped"],
    ) -> None:
        """Test exit callback is not called when stop() fails."""
        callback = Mock()
        sw = Stopwatch(timer_func=mock_timer, exit_callback=callback)

        if stop_failure_state == "already_stopped":
            sw.start()
            sw.stop()
            callback.reset_mock()

        with pytest.raises(NotRunningError):
            sw.stop()

        callback.assert_not_called()

    def test_exit_callback_not_called_when_stop_timer_fails(self) -> None:
        """Test exit callback is not called when stop() cannot read time."""
        timer = Mock(side_effect=[0.0, RuntimeError("timer error")])
        callback = Mock()
        sw = Stopwatch(timer_func=timer, exit_callback=callback)
        sw.start()

        with pytest.raises(RuntimeError, match="timer error"):
            sw.stop()

        callback.assert_not_called()

    def test_exit_callback_not_called_on_reset_before_start(
        self, mock_timer: Mock
    ) -> None:
        """Test exit callback is not called on reset() before start()."""
        callback = Mock()
        sw = Stopwatch(timer_func=mock_timer, exit_callback=callback)

        sw.reset()

        callback.assert_not_called()

    def test_exit_callback_not_called_on_reset_while_running(
        self, mock_timer: Mock
    ) -> None:
        """Test exit callback is not called on reset() while running."""
        callback = Mock()
        sw = Stopwatch(timer_func=mock_timer, exit_callback=callback)
        sw.start()
        sw.reset()
        callback.assert_not_called()

    def test_exit_callback_not_called_on_reset_after_stop(
        self, mock_timer: Mock
    ) -> None:
        """Test exit callback is not called on reset() after stop()."""
        callback = Mock()
        sw = Stopwatch(timer_func=mock_timer, exit_callback=callback)
        sw.start()
        sw.stop()
        callback.reset_mock()

        sw.reset()

        callback.assert_not_called()

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

    def test_custom_timer_values_are_exposed_as_raw_timestamps(
        self,
    ) -> None:
        """Test custom timer values are exposed as raw timestamps."""
        custom_timer = Mock(side_effect=[1000.0, 1003.5])
        sw = Stopwatch(timer_func=custom_timer)

        sw.start()
        assert sw.time_start == 1000.0

        elapsed = sw.stop()

        assert sw.time_start == 1000.0
        assert sw.time_stop == 1003.5
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

        state_timer.__module__ = "test_module"
        state_timer.__qualname__ = "state_timer"
        sw = Stopwatch(timer_func=state_timer)
        expected = (
            "Stopwatch(timer_func=test_module.state_timer, exit_callback=None)"
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
        # All should be different
        assert "not started" in str_not_started
        assert "running" in str_running
        assert "stopped" in str_stopped

    def test_str_vs_repr(self, stopwatch: Stopwatch) -> None:
        """Test that __str__ and __repr__ return different values."""
        str_str = str(stopwatch)
        repr_str = repr(stopwatch)
        # They should be different
        assert str_str != repr_str
        # str should have state info
        assert "not started" in str_str
        # repr should have constructor info
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
