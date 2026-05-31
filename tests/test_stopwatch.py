"""Tests for the Stopwatch class."""

import logging
import time
from unittest.mock import Mock

import pytest
from _timing_output_assertions import assert_elapsed_seconds_displayed

from ticko import (
    AlreadyRunningError,
    NoLapsRecordedError,
    NotRunningError,
    NotStartedError,
    Stopwatch,
)


@pytest.fixture
def mock_timer() -> Mock:
    """Create a mock timer function."""
    return Mock(side_effect=[0.0, 1.0, 2.0, 3.0, 4.0, 5.0])


@pytest.fixture
def stopwatch(mock_timer: Mock) -> Stopwatch:
    """Create a Stopwatch instance with mock timer."""
    return Stopwatch(timer_func=mock_timer)


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

    def test_stop(self, stopwatch: Stopwatch) -> None:
        """Test stopping the stopwatch."""
        stopwatch.start()  # time = 0.0
        elapsed = stopwatch.stop()  # time = 1.0
        assert elapsed == 1.0
        assert not stopwatch.is_running
        assert stopwatch.time_stop == 1.0

    def test_reset(self, stopwatch: Stopwatch) -> None:
        """Test resetting the stopwatch."""
        stopwatch.start()
        stopwatch.lap()
        stopwatch.stop()
        stopwatch.reset()

        assert not stopwatch.is_running
        assert stopwatch.time_start is None
        assert stopwatch.time_stop is None

    def test_reset_and_restart(self, stopwatch: Stopwatch) -> None:
        """Test resetting and restarting the stopwatch."""
        stopwatch.start()  # time = 0.0
        stopwatch.stop()  # time = 1.0
        stopwatch.reset()
        stopwatch.start()  # time = 2.0
        assert stopwatch.is_running


class TestInvalidLifecycleOperations:
    """Test invalid lifecycle transitions."""

    def test_start_already_running(self, stopwatch: Stopwatch) -> None:
        """Test starting an already running stopwatch raises error."""
        stopwatch.start()
        with pytest.raises(AlreadyRunningError, match="already running"):
            stopwatch.start()

    def test_stop_not_started(self, stopwatch: Stopwatch) -> None:
        """Test stopping a non-running stopwatch raises error."""
        with pytest.raises(NotRunningError, match="not running"):
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

    def test_lap_not_started(self, stopwatch: Stopwatch) -> None:
        """Test recording lap on non-running stopwatch raises error."""
        with pytest.raises(NotRunningError, match="not running"):
            stopwatch.lap()


class TestElapsedTime:
    """Test total elapsed time property access."""

    def test_time_elapsed_while_running(self, stopwatch: Stopwatch) -> None:
        """Test getting elapsed time while running."""
        stopwatch.start()  # time = 0.0
        elapsed = stopwatch.time_elapsed  # time = 1.0
        assert elapsed == 1.0

    def test_time_elapsed_after_stop(self, stopwatch: Stopwatch) -> None:
        """Test getting elapsed time after stopping."""
        stopwatch.start()  # time = 0.0
        stopwatch.stop()  # time = 1.0
        elapsed = stopwatch.time_elapsed  # Should not call timer
        assert elapsed == 1.0

    def test_time_elapsed_not_started(self, stopwatch: Stopwatch) -> None:
        """Test getting elapsed time before starting raises error."""
        with pytest.raises(NotStartedError, match="not been started"):
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

    def test_time_since_last_lap_after_stop(self, stopwatch: Stopwatch) -> None:
        """Test getting elapsed time since last lap after stopping."""
        stopwatch.start()  # time = 0.0
        stopwatch.lap()  # time = 1.0
        stopwatch.stop()  # time = 2.0
        last_lap = stopwatch.time_since_last_lap  # Should not call timer
        assert last_lap == 1.0

    def test_time_since_last_lap_no_laps(self, stopwatch: Stopwatch) -> None:
        """Test no laps raises error."""
        with pytest.raises(NoLapsRecordedError, match="No laps"):
            _ = stopwatch.time_since_last_lap

    def test_time_since_last_lap_no_laps_after_start(
        self, stopwatch: Stopwatch
    ) -> None:
        """Test time_since_last_lap before any lap() raises error."""
        stopwatch.start()
        with pytest.raises(NoLapsRecordedError, match="No laps"):
            _ = stopwatch.time_since_last_lap

    def test_time_since_last_lap_no_laps_after_restart(
        self, stopwatch: Stopwatch
    ) -> None:
        """Test raises after stop() -> start() without lap()."""
        stopwatch.start()
        stopwatch.lap()
        stopwatch.stop()
        stopwatch.start()
        with pytest.raises(NoLapsRecordedError, match="No laps"):
            _ = stopwatch.time_since_last_lap


class TestContextManager:
    """Test context manager functionality."""

    def test_context_manager(self, stopwatch: Stopwatch) -> None:
        """Test using stopwatch as context manager."""
        with stopwatch as sw:
            assert sw.is_running
            assert sw is stopwatch
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

    def test_exit_callback_not_called_on_reset_while_running(
        self, mock_timer: Mock
    ) -> None:
        """Test exit callback is not called on reset() while running."""
        callback = Mock()
        sw = Stopwatch(timer_func=mock_timer, exit_callback=callback)
        sw.start()
        sw.reset()
        callback.assert_not_called()

    def test_exit_callback_with_exception(self, mock_timer: Mock) -> None:
        """Test exit callback that raises exception is handled."""
        callback = Mock(side_effect=RuntimeError("Callback error"))
        sw = Stopwatch(timer_func=mock_timer, exit_callback=callback)
        sw.start()
        # Should not raise, exception should be logged
        sw.stop()
        callback.assert_called_once()


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
    """Test Stopwatch string representation."""

    def test_repr_with_default_timer(self, stopwatch: Stopwatch) -> None:
        """Test __repr__ shows constructor parameters."""
        repr_str = repr(stopwatch)
        assert "Stopwatch" in repr_str
        assert "timer_func=" in repr_str
        assert "exit_callback=" in repr_str

    def test_repr_includes_name(self, mock_timer: Mock) -> None:
        """Test __repr__ includes name when set."""
        sw = Stopwatch(name="db", timer_func=mock_timer)
        assert "name='db'" in repr(sw)

    def test_repr_omits_name_when_none(self, stopwatch: Stopwatch) -> None:
        """Test __repr__ omits name when not set."""
        assert "name=" not in repr(stopwatch)

    def test_repr_with_callback(self, mock_timer: Mock) -> None:
        """Test __repr__ with exit callback."""
        callback = Mock()
        callback.__name__ = "test_callback"
        callback.__qualname__ = "test_callback"
        callback.__module__ = "test_module"
        sw = Stopwatch(timer_func=mock_timer, exit_callback=callback)
        repr_str = repr(sw)
        assert "Stopwatch" in repr_str
        assert "timer_func=" in repr_str
        assert "exit_callback=test_module.test_callback" in repr_str

    def test_repr_uses_fully_qualified_name(self) -> None:
        """Test __repr__ outputs fully qualified callable names."""
        sw = Stopwatch()
        repr_str = repr(sw)
        assert "timer_func=time.perf_counter" in repr_str

    def test_repr_without_callback(self, mock_timer: Mock) -> None:
        """Test __repr__ without exit callback."""
        sw = Stopwatch(timer_func=mock_timer, exit_callback=None)
        repr_str = repr(sw)
        assert "Stopwatch" in repr_str
        assert "timer_func=" in repr_str
        assert "exit_callback=None" in repr_str

    def test_repr_independent_of_state(self, stopwatch: Stopwatch) -> None:
        """Test __repr__ is same regardless of stopwatch state."""
        repr_not_started = repr(stopwatch)
        stopwatch.start()
        repr_running = repr(stopwatch)
        stopwatch.stop()
        repr_stopped = repr(stopwatch)
        # All should show the same constructor info
        assert "timer_func=" in repr_not_started
        assert "timer_func=" in repr_running
        assert "timer_func=" in repr_stopped


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
