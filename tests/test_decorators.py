"""Tests for the stopwatch decorator."""

import io
import time
from contextlib import redirect_stdout
from unittest.mock import Mock

import pytest

from ticko.decorators import stopwatch
from ticko.stop_watch import StopWatch


@pytest.fixture
def mock_timer() -> Mock:
    """Create a mock timer function."""
    return Mock(side_effect=[0.0, 1.0, 2.0, 3.0, 4.0, 5.0])


class TestStopwatchDecorator:
    """Test cases for the stopwatch decorator."""

    def test_basic_decoration(self, mock_timer: Mock) -> None:
        """Test basic function decoration."""
        callback = Mock()

        @stopwatch(timer_func=mock_timer, exit_callback=callback)
        def sample_func(x: int) -> int:
            return x * 2

        result: int = sample_func(5)

        assert result == 10
        callback.assert_called_once()
        sw_arg = callback.call_args[0][0]
        assert sw_arg.time_elapsed == 1.0

    def test_decorator_without_parentheses(self) -> None:
        """Test decorator used without parentheses."""

        @stopwatch
        def sample_func(x: int) -> int:
            return x + 1

        # When using @stopwatch without parentheses, it uses default callback
        f = io.StringIO()
        with redirect_stdout(f):
            result = sample_func(10)

        assert result == 11
        output = f.getvalue()
        assert "sample_func" in output

    def test_decorator_with_custom_callback(self, mock_timer: Mock) -> None:
        """Test decorator with custom exit callback."""
        callback = Mock()

        @stopwatch(timer_func=mock_timer, exit_callback=callback)
        def sample_func(x: int, y: int) -> int:
            return x + y

        result = sample_func(3, 4)
        assert result == 7
        callback.assert_called_once()
        sw_arg = callback.call_args[0][0]
        assert isinstance(sw_arg, StopWatch)
        assert sw_arg.time_elapsed == 1.0

    def test_decorator_preserves_function_metadata(self) -> None:
        """Test decorator preserves function name and docstring."""

        @stopwatch(exit_callback=lambda sw: None)
        def documented_func(x: int) -> int:
            """This is a documented function."""
            return x

        assert documented_func.__name__ == "documented_func"
        assert documented_func.__doc__ == "This is a documented function."

    def test_decorator_with_exception(self, mock_timer: Mock) -> None:
        """Test decorator behavior when function raises exception."""
        callback = Mock()

        @stopwatch(timer_func=mock_timer, exit_callback=callback)
        def failing_func() -> None:
            raise ValueError("Test error")

        with pytest.raises(ValueError, match="Test error"):
            failing_func()

        # Callback should still be called
        callback.assert_called_once()
        sw_arg = callback.call_args[0][0]
        assert not sw_arg.is_running

    def test_decorator_with_args_and_kwargs(self) -> None:
        """Test decorator with various argument types."""
        callback = Mock()

        @stopwatch(exit_callback=callback)
        def complex_func(a: int, b: int, *args: int, **kwargs: str) -> str:
            return f"{a}-{b}-{args}-{kwargs}"

        result = complex_func(1, 2, 3, 4, x="hello", y="world")
        assert result == "1-2-(3, 4)-{'x': 'hello', 'y': 'world'}"
        callback.assert_called_once()

    def test_decorator_with_custom_timer(self) -> None:
        """Test decorator with custom timer function."""
        custom_timer = Mock(side_effect=[100.0, 200.0])
        callback = Mock()

        @stopwatch(timer_func=custom_timer, exit_callback=callback)
        def sample_func() -> str:
            return "done"

        result = sample_func()
        assert result == "done"
        callback.assert_called_once()
        sw_arg = callback.call_args[0][0]
        assert sw_arg.time_elapsed == 100.0

    def test_default_callback_format(self, mock_timer: Mock) -> None:
        """Test the default callback output format."""

        @stopwatch(timer_func=mock_timer)
        def my_function() -> None:
            pass

        f = io.StringIO()
        with redirect_stdout(f):
            my_function()

        output = f.getvalue()
        # Check for proper formatting (the bug we fixed)
        assert "'my_function'" in output
        assert "1.000000" in output
        # Should NOT contain the format string
        assert "%r" not in output
        assert "%f" not in output


class TestStopwatchDecoratorRealTime:
    """Test stopwatch decorator with real time."""

    def test_real_time_measurement(self) -> None:
        """Test decorator with actual time delays."""
        times: list[float] = []

        def capture_callback(sw: StopWatch) -> None:
            times.append(sw.time_elapsed)

        @stopwatch(exit_callback=capture_callback)
        def delayed_func() -> str:
            time.sleep(0.1)
            return "done"

        result: str = delayed_func()
        assert result == "done"
        assert len(times) == 1
        assert 0.09 < times[0] < 0.15
