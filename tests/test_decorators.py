"""Tests for the stopwatch decorator."""

import asyncio
import io
import time
from contextlib import redirect_stdout
from unittest.mock import Mock

import pytest

from ticko.decorators import stopwatch


@pytest.fixture
def mock_timer() -> Mock:
    """Create a mock timer function."""
    return Mock(side_effect=[0.0, 1.0, 2.0, 3.0, 4.0, 5.0])


class TestDecorationForms:
    """Test supported ways to apply the decorator."""

    def test_configured_decorator_wraps_function(
        self,
        mock_timer: Mock,
    ) -> None:
        """Test @stopwatch(...) decoration."""
        callback = Mock()

        @stopwatch(timer_func=mock_timer, exit_callback=callback)
        def sample_func(x: int) -> int:
            return x * 2

        result: int = sample_func(5)

        assert result == 10
        callback.assert_called_once()
        assert callback.call_args[0][0] == 1.0

    def test_bare_decorator_wraps_function(self) -> None:
        """Test @stopwatch decoration."""

        @stopwatch
        def sample_func(x: int) -> int:
            return x + 1

        f = io.StringIO()
        with redirect_stdout(f):
            result = sample_func(10)

        assert result == 11
        output = f.getvalue()
        assert "sample_func" in output

    def test_direct_decoration_with_custom_options(
        self,
        mock_timer: Mock,
    ) -> None:
        """Test stopwatch(func, ...) decoration."""
        callback = Mock()

        def sample_func(x: int) -> int:
            return x * 2

        decorated = stopwatch(
            sample_func,
            timer_func=mock_timer,
            exit_callback=callback,
        )

        result: int = decorated(5)

        assert result == 10
        callback.assert_called_once()
        assert callback.call_args[0][0] == 1.0


class TestWrappedFunctionBehavior:
    """Test behavior preserved by the wrapper."""

    def test_decorator_preserves_function_metadata(self) -> None:
        """Test decorator preserves function name and docstring."""

        @stopwatch(exit_callback=lambda elapsed: None)
        def documented_func(x: int) -> int:
            """This is a documented function."""
            return x

        assert documented_func.__name__ == "documented_func"
        assert documented_func.__doc__ == "This is a documented function."

    def test_decorator_with_args_and_kwargs(self) -> None:
        """Test decorator with various argument types."""
        callback = Mock()

        @stopwatch(exit_callback=callback)
        def complex_func(a: int, b: int, *args: int, **kwargs: str) -> str:
            return f"{a}-{b}-{args}-{kwargs}"

        result = complex_func(1, 2, 3, 4, x="hello", y="world")
        assert result == "1-2-(3, 4)-{'x': 'hello', 'y': 'world'}"
        callback.assert_called_once()


class TestExitCallbackTiming:
    """Test elapsed time passed to exit callbacks."""

    def test_decorator_with_custom_callback(self, mock_timer: Mock) -> None:
        """Test decorator with custom exit callback."""
        callback = Mock()

        @stopwatch(timer_func=mock_timer, exit_callback=callback)
        def sample_func(x: int, y: int) -> int:
            return x + y

        result = sample_func(3, 4)
        assert result == 7
        callback.assert_called_once()
        assert callback.call_args[0][0] == 1.0

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
        assert callback.call_args[0][0] == 100.0

    def test_decorator_with_exception(self, mock_timer: Mock) -> None:
        """Test decorator behavior when function raises exception."""
        callback = Mock()

        @stopwatch(timer_func=mock_timer, exit_callback=callback)
        def failing_func() -> None:
            raise ValueError("Test error")

        with pytest.raises(ValueError, match="Test error"):
            failing_func()

        callback.assert_called_once()
        assert isinstance(callback.call_args[0][0], float)


class TestDefaultCallbackOutput:
    """Test output written by the default callback."""

    def test_default_callback_format(self, mock_timer: Mock) -> None:
        """Test the default callback output format."""

        @stopwatch(timer_func=mock_timer)
        def my_function() -> None:
            pass

        f = io.StringIO()
        with redirect_stdout(f):
            my_function()

        output = f.getvalue()
        assert "'my_function'" in output
        assert "exited after" in output
        assert "1.000000" in output
        assert "%r" not in output
        assert "%f" not in output

    def test_default_callback_format_with_callable_object(
        self,
        mock_timer: Mock,
    ) -> None:
        """Test the default callback output for callable objects."""

        class Work:
            def __call__(self) -> str:
                return "ok"

        decorated = stopwatch(Work(), timer_func=mock_timer)

        f = io.StringIO()
        with redirect_stdout(f):
            result = decorated()

        output = f.getvalue()
        assert result == "ok"
        assert "'Work'" in output
        assert "exited after" in output
        assert "1.000000" in output

    def test_default_callback_format_with_exception(
        self,
        mock_timer: Mock,
    ) -> None:
        """Test the default callback output when the function raises."""

        @stopwatch(timer_func=mock_timer)
        def failing_function() -> None:
            raise ValueError("Test error")

        f = io.StringIO()
        with (
            redirect_stdout(f),
            pytest.raises(ValueError, match="Test error"),
        ):
            failing_function()

        output = f.getvalue()
        assert "'failing_function'" in output
        assert "exited after" in output
        assert "1.000000" in output
        assert "executed" not in output


class TestSynchronousRealTimeMeasurement:
    """Test synchronous timing with the default timer."""

    def test_real_time_measurement(self) -> None:
        """Test decorator with actual time delays."""
        times: list[float] = []

        def capture_callback(elapsed: float) -> None:
            times.append(elapsed)

        @stopwatch(exit_callback=capture_callback)
        def delayed_func() -> str:
            time.sleep(0.1)
            return "done"

        result: str = delayed_func()
        assert result == "done"
        assert len(times) == 1
        assert times[0] > 0.09


class TestAsyncWrappedFunctions:
    """Test async functions and callable objects."""

    def test_async_function_callback_runs_after_awaited_body(self) -> None:
        """Test callback runs after an async function body completes."""
        events: list[str] = []

        def capture_callback(elapsed: float) -> None:
            events.append(f"callback:{elapsed}")

        timer = Mock(side_effect=[0.0, 1.0])

        @stopwatch(timer_func=timer, exit_callback=capture_callback)
        async def sample_func(value: int) -> int:
            events.append("body-start")
            await asyncio.sleep(0)
            events.append("body-end")
            return value * 2

        result = asyncio.run(sample_func(5))

        assert result == 10
        assert events == ["body-start", "body-end", "callback:1.0"]

    def test_async_callable_object_callback_runs_after_awaited_body(
        self,
    ) -> None:
        """Test callback runs after an async callable object completes."""
        events: list[str] = []

        def capture_callback(elapsed: float) -> None:
            events.append(f"callback:{elapsed}")

        class AsyncWork:
            async def __call__(self, value: int) -> int:
                events.append("body-start")
                await asyncio.sleep(0)
                events.append("body-end")
                return value * 2

        timer = Mock(side_effect=[0.0, 1.0])
        decorated = stopwatch(
            AsyncWork(),
            timer_func=timer,
            exit_callback=capture_callback,
        )

        result = asyncio.run(decorated(5))

        assert result == 10
        assert events == ["body-start", "body-end", "callback:1.0"]

    def test_async_function_measures_awaited_execution_time(self) -> None:
        """Test async function timing includes awaited work."""
        times: list[float] = []

        @stopwatch(exit_callback=times.append)
        async def delayed_func() -> str:
            await asyncio.sleep(0.05)
            return "done"

        result = asyncio.run(delayed_func())

        assert result == "done"
        assert len(times) == 1
        assert times[0] > 0.04

    def test_async_function_callback_runs_after_awaited_exception(self) -> None:
        """Test callback runs after an async function body raises."""
        events: list[str] = []

        def capture_callback(elapsed: float) -> None:
            events.append(f"callback:{elapsed}")

        timer = Mock(side_effect=[0.0, 1.0])

        @stopwatch(timer_func=timer, exit_callback=capture_callback)
        async def failing_func() -> None:
            events.append("body-start")
            await asyncio.sleep(0)
            events.append("body-error")
            raise ValueError("async error")

        with pytest.raises(ValueError, match="async error"):
            asyncio.run(failing_func())

        assert events == ["body-start", "body-error", "callback:1.0"]
