"""Tests for the StopWatch class."""

import time
from unittest.mock import Mock

import pytest

from ticko.stop_watch import AlreadyRunningError, NotStartedError, StopWatch


@pytest.fixture
def mock_timer() -> Mock:
    """Create a mock timer function."""
    return Mock(side_effect=[0.0, 1.0, 2.0, 3.0, 4.0, 5.0])


@pytest.fixture
def stopwatch(mock_timer: Mock) -> StopWatch:
    """Create a StopWatch instance with mock timer."""
    return StopWatch(timer_func=mock_timer)


class TestStopWatchBasicOperations:
    """Test basic StopWatch operations."""

    def test_initial_state(self, stopwatch: StopWatch) -> None:
        """Test stopwatch initial state."""
        assert not stopwatch.is_running
        assert stopwatch.time_start is None
        assert stopwatch.time_stop is None
        assert stopwatch.time_last_lap_start is None

    def test_start(self, stopwatch: StopWatch) -> None:
        """Test starting the stopwatch."""
        start_time = stopwatch.start()
        assert start_time == 0.0
        assert stopwatch.is_running
        assert stopwatch.time_start == 0.0
        assert stopwatch.time_last_lap_start == 0.0
        assert stopwatch.time_stop is None

    def test_start_already_running(self, stopwatch: StopWatch) -> None:
        """Test starting an already running stopwatch raises error."""
        stopwatch.start()
        with pytest.raises(AlreadyRunningError, match="already running"):
            stopwatch.start()

    def test_stop(self, stopwatch: StopWatch) -> None:
        """Test stopping the stopwatch."""
        stopwatch.start()  # time = 0.0
        elapsed = stopwatch.stop()  # time = 1.0
        assert elapsed == 1.0
        assert not stopwatch.is_running
        assert stopwatch.time_stop == 1.0

    def test_stop_not_started(self, stopwatch: StopWatch) -> None:
        """Test stopping a non-running stopwatch raises error."""
        with pytest.raises(NotStartedError, match="not running"):
            stopwatch.stop()

    def test_reset(self, stopwatch: StopWatch) -> None:
        """Test resetting the stopwatch."""
        stopwatch.start()
        stopwatch.lap()
        stopwatch.stop()
        stopwatch.reset()

        assert not stopwatch.is_running
        assert stopwatch.time_start is None
        assert stopwatch.time_stop is None
        assert stopwatch.time_last_lap_start is None

    def test_reset_and_restart(self, stopwatch: StopWatch) -> None:
        """Test resetting and restarting the stopwatch."""
        stopwatch.start()  # time = 0.0
        stopwatch.stop()  # time = 1.0
        stopwatch.reset()
        start_time = stopwatch.start()  # time = 2.0
        assert start_time == 2.0
        assert stopwatch.is_running


class TestStopWatchLapFunctionality:
    """Test lap recording functionality."""

    def test_lap(self, stopwatch: StopWatch) -> None:
        """Test recording lap times."""
        stopwatch.start()  # time = 0.0
        lap1 = stopwatch.lap()  # time = 1.0
        assert lap1 == 1.0
        assert stopwatch.time_last_lap_start == 1.0

        lap2 = stopwatch.lap()  # time = 2.0
        assert lap2 == 1.0
        assert stopwatch.time_last_lap_start == 2.0

    def test_lap_not_started(self, stopwatch: StopWatch) -> None:
        """Test recording lap on non-running stopwatch raises error."""
        with pytest.raises(NotStartedError, match="not running"):
            stopwatch.lap()


class TestStopWatchProperties:
    """Test StopWatch property accessors."""

    def test_time_elapsed_while_running(self, stopwatch: StopWatch) -> None:
        """Test getting elapsed time while running."""
        stopwatch.start()  # time = 0.0
        elapsed = stopwatch.time_elapsed  # time = 1.0
        assert elapsed == 1.0

    def test_time_elapsed_after_stop(self, stopwatch: StopWatch) -> None:
        """Test getting elapsed time after stopping."""
        stopwatch.start()  # time = 0.0
        stopwatch.stop()  # time = 1.0
        elapsed = stopwatch.time_elapsed  # Should not call timer
        assert elapsed == 1.0

    def test_time_elapsed_not_started(self, stopwatch: StopWatch) -> None:
        """Test getting elapsed time before starting raises error."""
        with pytest.raises(NotStartedError, match="not been started"):
            _ = stopwatch.time_elapsed

    def test_time_last_lap_while_running(self, stopwatch: StopWatch) -> None:
        """Test getting last lap time while running."""
        stopwatch.start()  # time = 0.0
        stopwatch.lap()  # time = 1.0
        last_lap = stopwatch.time_last_lap  # time = 2.0
        assert last_lap == 1.0

    def test_time_last_lap_after_stop(self, stopwatch: StopWatch) -> None:
        """Test getting last lap time after stopping."""
        stopwatch.start()  # time = 0.0
        stopwatch.lap()  # time = 1.0
        stopwatch.stop()  # time = 2.0
        last_lap = stopwatch.time_last_lap  # Should not call timer
        assert last_lap == 1.0

    def test_time_last_lap_no_laps(self, stopwatch: StopWatch) -> None:
        """Test getting last lap time with no laps raises error."""
        with pytest.raises(NotStartedError, match="No laps"):
            _ = stopwatch.time_last_lap


class TestStopWatchContextManager:
    """Test context manager functionality."""

    def test_context_manager(self, stopwatch: StopWatch) -> None:
        """Test using stopwatch as context manager."""
        with stopwatch as sw:
            assert sw.is_running
            assert sw is stopwatch
        assert not stopwatch.is_running

    def test_context_manager_with_exception(self, stopwatch: StopWatch) -> None:
        """Test context manager stops even on exception."""
        with (  # noqa: PT012
            pytest.raises(ValueError, match="Test exception"),
            stopwatch,
        ):
            assert stopwatch.is_running
            raise ValueError("Test exception")
        assert not stopwatch.is_running
        assert stopwatch.time_stop is not None


class TestStopWatchCallbacks:
    """Test callback functionality."""

    def test_exit_callback(self, mock_timer: Mock) -> None:
        """Test exit callback is called when stopping."""
        callback = Mock()
        sw = StopWatch(timer_func=mock_timer, exit_callback=callback)
        sw.start()
        sw.stop()
        callback.assert_called_once_with(sw)

    def test_exit_callback_with_exception(self, mock_timer: Mock) -> None:
        """Test exit callback that raises exception is handled."""
        callback = Mock(side_effect=RuntimeError("Callback error"))
        sw = StopWatch(timer_func=mock_timer, exit_callback=callback)
        sw.start()
        # Should not raise, exception should be logged
        sw.stop()
        callback.assert_called_once()

    def test_custom_timer_func(self) -> None:
        """Test using custom timer function."""
        custom_timer = Mock(side_effect=[10.0, 20.0, 30.0])
        sw = StopWatch(timer_func=custom_timer)
        sw.start()
        elapsed = sw.stop()
        assert elapsed == 10.0
        assert custom_timer.call_count == 2


class TestStopWatchRepr:
    """Test StopWatch string representation."""

    def test_repr_with_default_timer(self, stopwatch: StopWatch) -> None:
        """Test __repr__ shows constructor parameters."""
        repr_str = repr(stopwatch)
        assert "StopWatch" in repr_str
        assert "timer_func=" in repr_str
        assert "exit_callback=" in repr_str

    def test_repr_with_callback(self, mock_timer: Mock) -> None:
        """Test __repr__ with exit callback."""
        callback = Mock()
        callback.__name__ = "test_callback"
        sw = StopWatch(timer_func=mock_timer, exit_callback=callback)
        repr_str = repr(sw)
        assert "StopWatch" in repr_str
        assert "timer_func=" in repr_str
        assert "exit_callback=test_callback" in repr_str

    def test_repr_without_callback(self, mock_timer: Mock) -> None:
        """Test __repr__ without exit callback."""
        sw = StopWatch(timer_func=mock_timer, exit_callback=None)
        repr_str = repr(sw)
        assert "StopWatch" in repr_str
        assert "timer_func=" in repr_str
        assert "exit_callback=None" in repr_str

    def test_repr_independent_of_state(self, stopwatch: StopWatch) -> None:
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


class TestStopWatchStr:
    """Test StopWatch human-readable string representation."""

    def test_str_not_started(self, stopwatch: StopWatch) -> None:
        """Test __str__ when not started."""
        str_str = str(stopwatch)
        assert "StopWatch" in str_str
        assert "not started" in str_str

    def test_str_running(self, stopwatch: StopWatch) -> None:
        """Test __str__ while running."""
        stopwatch.start()  # time = 0.0
        str_str = str(stopwatch)  # time = 1.0
        assert "StopWatch" in str_str
        assert "running" in str_str
        assert "elapsed=" in str_str
        assert "1.000000s" in str_str

    def test_str_stopped(self, stopwatch: StopWatch) -> None:
        """Test __str__ after stopping."""
        stopwatch.start()  # time = 0.0
        stopwatch.stop()  # time = 1.0
        str_str = str(stopwatch)
        assert "StopWatch" in str_str
        assert "stopped" in str_str
        assert "elapsed=" in str_str
        assert "1.000000s" in str_str

    def test_str_changes_with_state(self, stopwatch: StopWatch) -> None:
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

    def test_str_vs_repr(self, stopwatch: StopWatch) -> None:
        """Test that __str__ and __repr__ return different values."""
        str_str = str(stopwatch)
        repr_str = repr(stopwatch)
        # They should be different
        assert str_str != repr_str
        # str should have state info
        assert "not started" in str_str
        # repr should have constructor info
        assert "timer_func=" in repr_str


class TestStopWatchRealTime:
    """Test StopWatch with real time functions."""

    def test_real_elapsed_time(self) -> None:
        """Test with real time.perf_counter."""
        sw = StopWatch()
        sw.start()
        time.sleep(0.1)
        elapsed = sw.stop()
        # Allow some tolerance for timing
        assert 0.09 < elapsed < 0.15

    def test_real_lap_time(self) -> None:
        """Test lap times with real timer."""
        sw = StopWatch()
        sw.start()
        time.sleep(0.05)
        lap1 = sw.lap()
        time.sleep(0.05)
        lap2 = sw.lap()
        sw.stop()

        assert lap1 > 0.04
        assert lap2 > 0.04
