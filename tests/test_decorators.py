"""Tests for the stopwatch decorator."""

import asyncio
import gc
import logging
import sys
import threading
import time
from collections.abc import AsyncGenerator, Awaitable, Callable, Generator
from contextlib import nullcontext
from typing import cast
from unittest.mock import Mock

import pytest
from _timing_output_assertions import assert_elapsed_seconds_displayed

from ticko.decorators import stopwatch


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

    def test_bare_decorator_wraps_function(
        self,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Test @stopwatch decoration."""

        @stopwatch
        def sample_func(x: int) -> int:
            return x + 1

        result = sample_func(10)

        assert result == 11
        output = capsys.readouterr().out
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

    def test_decorator_preserves_exception_when_stop_timer_fails(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Test stop timer failure does not replace function exception."""
        timer = Mock(side_effect=[0.0, RuntimeError("timer failed")])
        callback = Mock()

        @stopwatch(timer_func=timer, exit_callback=callback)
        def failing_func() -> None:
            raise ValueError("body failed")

        with (
            caplog.at_level(logging.ERROR, logger="ticko"),
            pytest.raises(ValueError, match="body failed"),
        ):
            failing_func()

        callback.assert_not_called()
        assert any(
            record.levelno >= logging.ERROR
            and (record.name == "ticko" or record.name.startswith("ticko."))
            and record.exc_info is not None
            and isinstance(record.exc_info[1], RuntimeError)
            and str(record.exc_info[1]) == "timer failed"
            for record in caplog.records
        )

    def test_stop_failure_propagates_when_called_inside_except_block(
        self,
    ) -> None:
        """Test stop failure propagates when the function itself succeeds.

        An exception being handled in the caller must not be mistaken for
        a failure of the decorated function.
        """
        timer = Mock(side_effect=[0.0, RuntimeError("timer failed")])
        callback = Mock()

        @stopwatch(timer_func=timer, exit_callback=callback)
        def succeeding_func() -> str:
            return "ok"

        def _raise_outer_error() -> None:
            raise ValueError("outer error being handled")

        def call_inside_except_block() -> str:
            try:
                _raise_outer_error()
            except ValueError:
                return succeeding_func()
            return ""

        with pytest.raises(RuntimeError, match="timer failed"):
            call_inside_except_block()

        callback.assert_not_called()


class TestDefaultCallbackOutput:
    """Test output written by the default callback."""

    def test_default_callback_format(
        self,
        mock_timer: Mock,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Test the default callback output format."""

        @stopwatch(timer_func=mock_timer)
        def my_function() -> None:
            pass

        my_function()

        output = capsys.readouterr().out
        assert "my_function" in output
        assert_elapsed_seconds_displayed(output, 1.0)

    def test_default_callback_format_with_callable_object(
        self,
        mock_timer: Mock,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Test the default callback output for callable objects."""

        class Work:
            def __call__(self) -> str:
                return "ok"

        decorated = stopwatch(Work(), timer_func=mock_timer)

        result = decorated()

        output = capsys.readouterr().out
        assert result == "ok"
        assert "Work" in output
        assert_elapsed_seconds_displayed(output, 1.0)

    def test_default_callback_format_with_exception(
        self,
        mock_timer: Mock,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Test the default callback output when the function raises."""

        @stopwatch(timer_func=mock_timer)
        def failing_function() -> None:
            raise ValueError("Test error")

        with pytest.raises(ValueError, match="Test error"):
            failing_function()

        output = capsys.readouterr().out
        assert "failing_function" in output
        assert_elapsed_seconds_displayed(output, 1.0)


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

    def test_async_function_preserves_exception_when_stop_timer_fails(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Test async stop timer failure does not replace body exception."""
        timer = Mock(side_effect=[0.0, RuntimeError("timer failed")])
        callback = Mock()

        @stopwatch(timer_func=timer, exit_callback=callback)
        async def failing_func() -> None:
            await asyncio.sleep(0)
            raise ValueError("async body failed")

        with (
            caplog.at_level(logging.ERROR, logger="ticko"),
            pytest.raises(ValueError, match="async body failed"),
        ):
            asyncio.run(failing_func())

        callback.assert_not_called()
        assert any(
            record.levelno >= logging.ERROR
            and (record.name == "ticko" or record.name.startswith("ticko."))
            and record.exc_info is not None
            and isinstance(record.exc_info[1], RuntimeError)
            and str(record.exc_info[1]) == "timer failed"
            for record in caplog.records
        )

    def test_async_stop_failure_propagates_when_called_inside_except_block(
        self,
    ) -> None:
        """Test async stop failure propagates when the body succeeds.

        An exception being handled in the caller must not be mistaken for
        a failure of the awaited function.
        """
        timer = Mock(side_effect=[0.0, RuntimeError("timer failed")])
        callback = Mock()

        @stopwatch(timer_func=timer, exit_callback=callback)
        async def succeeding_func() -> str:
            return "ok"

        def _raise_outer_error() -> None:
            raise ValueError("outer error being handled")

        async def call_inside_except_block() -> str:
            try:
                _raise_outer_error()
            except ValueError:
                return await succeeding_func()
            return ""

        with pytest.raises(RuntimeError, match="timer failed"):
            asyncio.run(call_inside_except_block())

        callback.assert_not_called()


class TestGeneratorWrappedFunctions:
    """Test generator functions."""

    def test_generator_object_creation_does_not_start_timer(self) -> None:
        """Test generator creation is not measured before consumption."""
        callback = Mock()
        timer = Mock(side_effect=[0.0, 1.0])

        @stopwatch(timer_func=timer, exit_callback=callback)
        def sample_generator() -> Generator[str, None, None]:
            yield "value"

        generator = sample_generator()

        assert isinstance(generator, Generator)
        timer.assert_not_called()
        callback.assert_not_called()
        generator.close()

    def test_generator_callback_runs_after_consumption(self) -> None:
        """Test callback runs after a generator is fully consumed."""
        events: list[str] = []

        def capture_callback(elapsed: float) -> None:
            events.append(f"callback:{elapsed}")

        timer = Mock(side_effect=[0.0, 1.0, 10.0, 12.0])

        @stopwatch(timer_func=timer, exit_callback=capture_callback)
        def sample_generator() -> Generator[str, None, None]:
            events.append("body-start")
            yield "first"
            events.append("body-end")

        generator = sample_generator()

        assert next(generator) == "first"
        assert events == ["body-start"]
        assert timer.call_count == 2

        with pytest.raises(StopIteration):
            next(generator)

        assert events == ["body-start", "body-end", "callback:3.0"]

    def test_generator_excludes_time_between_yields(self) -> None:
        """Test consumer time between yielded values is not measured."""
        callback = Mock()
        timer = Mock(side_effect=[0.0, 1.0, 101.0, 103.0, 203.0, 206.0])

        @stopwatch(timer_func=timer, exit_callback=callback)
        def sample_generator() -> Generator[str, None, None]:
            yield "first"
            yield "second"

        generator = sample_generator()

        assert next(generator) == "first"
        assert next(generator) == "second"
        with pytest.raises(StopIteration):
            next(generator)

        callback.assert_called_once_with(6.0)

    def test_generator_callable_object_callback_runs_after_consumption(
        self,
    ) -> None:
        """Test callable object generator consumption is measured."""
        events: list[str] = []

        def capture_callback(elapsed: float) -> None:
            events.append(f"callback:{elapsed}")

        class Work:
            def __call__(self) -> Generator[str, None, None]:
                events.append("body-start")
                yield "first"
                events.append("body-end")

        timer = Mock(side_effect=[0.0, 1.0, 10.0, 12.0])
        decorated = stopwatch(
            Work(),
            timer_func=timer,
            exit_callback=capture_callback,
        )

        generator = decorated()

        timer.assert_not_called()
        assert next(generator) == "first"
        assert events == ["body-start"]

        with pytest.raises(StopIteration):
            next(generator)

        assert events == ["body-start", "body-end", "callback:3.0"]

    def test_generator_close_stops_timing_once(self) -> None:
        """Test closing a partially consumed generator reports elapsed time."""
        events: list[str] = []

        def capture_callback(elapsed: float) -> None:
            events.append(f"callback:{elapsed}")

        timer = Mock(side_effect=[0.0, 1.0, 10.0, 12.0, 99.0])

        @stopwatch(timer_func=timer, exit_callback=capture_callback)
        def sample_generator() -> Generator[str, None, None]:
            try:
                yield "first"
                yield "second"
            finally:
                events.append("body-finally")

        generator = sample_generator()

        assert next(generator) == "first"
        generator.close()
        generator.close()

        assert events == ["body-finally", "callback:3.0"]
        assert timer.call_count == 4

    def test_generator_gc_cleanup_reports_elapsed_time(self) -> None:
        """Test dropping a partially consumed generator reports elapsed time."""
        events: list[str] = []

        def capture_callback(elapsed: float) -> None:
            events.append(f"callback:{elapsed}")

        timer = Mock(side_effect=[0.0, 1.0, 10.0, 12.0, 99.0])

        @stopwatch(timer_func=timer, exit_callback=capture_callback)
        def sample_generator() -> Generator[str, None, None]:
            try:
                yield "first"
                yield "second"
            finally:
                events.append("body-finally")

        generator = sample_generator()

        assert next(generator) == "first"
        del generator
        gc.collect()

        assert events == ["body-finally", "callback:3.0"]
        assert timer.call_count == 4

    def test_generator_gc_cleanup_does_not_report_twice_after_close(
        self,
    ) -> None:
        """Test GC cleanup does not report again after explicit close."""
        events: list[str] = []

        def capture_callback(elapsed: float) -> None:
            events.append(f"callback:{elapsed}")

        timer = Mock(side_effect=[0.0, 1.0, 10.0, 12.0, 99.0])

        @stopwatch(timer_func=timer, exit_callback=capture_callback)
        def sample_generator() -> Generator[str, None, None]:
            try:
                yield "first"
                yield "second"
            finally:
                events.append("body-finally")

        generator = sample_generator()

        assert next(generator) == "first"
        generator.close()
        del generator
        gc.collect()

        assert events == ["body-finally", "callback:3.0"]
        assert timer.call_count == 4

    def test_generator_gc_cleanup_logs_stop_timer_failure(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Test GC cleanup logs stop failures without raising."""
        events: list[str] = []
        timer = Mock(
            side_effect=[0.0, 1.0, 10.0, RuntimeError("timer failed")],
        )
        callback = Mock()

        @stopwatch(timer_func=timer, exit_callback=callback)
        def sample_generator() -> Generator[str, None, None]:
            try:
                yield "first"
                yield "second"
            finally:
                events.append("body-finally")

        with caplog.at_level(logging.ERROR, logger="ticko"):
            generator = sample_generator()
            assert next(generator) == "first"
            del generator
            gc.collect()

        assert events == ["body-finally"]
        callback.assert_not_called()
        assert timer.call_count == 4
        assert any(
            record.levelno >= logging.ERROR
            and (record.name == "ticko" or record.name.startswith("ticko."))
            and record.exc_info is not None
            and isinstance(record.exc_info[1], RuntimeError)
            and str(record.exc_info[1]) == "timer failed"
            for record in caplog.records
        )

    def test_generator_gc_cleanup_runs_finally_when_resume_timer_fails(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Test GC cleanup still closes the generator after resume failure."""
        events: list[str] = []
        timer = Mock(side_effect=[0.0, 1.0, RuntimeError("resume failed")])
        callback = Mock()

        @stopwatch(timer_func=timer, exit_callback=callback)
        def sample_generator() -> Generator[str, None, None]:
            try:
                yield "first"
                yield "second"
            finally:
                events.append("body-finally")

        with caplog.at_level(logging.ERROR, logger="ticko"):
            generator = sample_generator()
            assert next(generator) == "first"
            del generator
            gc.collect()

        assert events == ["body-finally"]
        callback.assert_not_called()
        assert timer.call_count == 3
        assert any(
            record.levelno >= logging.ERROR
            and (record.name == "ticko" or record.name.startswith("ticko."))
            and record.exc_info is not None
            and isinstance(record.exc_info[1], RuntimeError)
            and str(record.exc_info[1]) == "resume failed"
            for record in caplog.records
        )

    def test_generator_gc_cleanup_logs_base_exception_stop_timer_failure(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Test GC cleanup logs BaseException stop failures."""
        events: list[str] = []
        timer = Mock(
            side_effect=[0.0, 1.0, 10.0, KeyboardInterrupt("interrupted")],
        )
        callback = Mock()

        @stopwatch(timer_func=timer, exit_callback=callback)
        def sample_generator() -> Generator[str, None, None]:
            try:
                yield "first"
                yield "second"
            finally:
                events.append("body-finally")

        with caplog.at_level(logging.ERROR, logger="ticko"):
            generator = sample_generator()
            assert next(generator) == "first"
            del generator
            gc.collect()

        assert events == ["body-finally"]
        callback.assert_not_called()
        assert timer.call_count == 4
        assert any(
            record.levelno >= logging.ERROR
            and (record.name == "ticko" or record.name.startswith("ticko."))
            and record.exc_info is not None
            and isinstance(record.exc_info[1], KeyboardInterrupt)
            and str(record.exc_info[1]) == "interrupted"
            for record in caplog.records
        )

    def test_generator_gc_cleanup_logs_inner_close_failure(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Test GC cleanup logs inner generator close failures."""
        events: list[str] = []
        timer = Mock(side_effect=[0.0, 1.0, 10.0, 12.0])
        callback = Mock()

        @stopwatch(timer_func=timer, exit_callback=callback)
        def sample_generator() -> Generator[str, None, None]:
            try:
                yield "first"
            except GeneratorExit:
                events.append("ignored-close")
                yield "bad"

        with caplog.at_level(logging.ERROR, logger="ticko"):
            generator = sample_generator()
            assert next(generator) == "first"
            del generator
            gc.collect()

        assert events == ["ignored-close"]
        callback.assert_called_once_with(3.0)
        assert any(
            record.levelno >= logging.ERROR
            and (record.name == "ticko" or record.name.startswith("ticko."))
            and record.exc_info is not None
            and isinstance(record.exc_info[1], RuntimeError)
            and str(record.exc_info[1]) == "generator ignored GeneratorExit"
            for record in caplog.records
        )

    def test_generator_close_propagates_stop_timer_failure(self) -> None:
        """Test close propagates stop timer failure after body cleanup."""
        events: list[str] = []
        timer = Mock(
            side_effect=[0.0, 1.0, 10.0, RuntimeError("timer failed")],
        )
        callback = Mock()

        @stopwatch(timer_func=timer, exit_callback=callback)
        def sample_generator() -> Generator[str, None, None]:
            try:
                yield "first"
            finally:
                events.append("body-finally")

        generator = sample_generator()

        assert next(generator) == "first"
        with pytest.raises(RuntimeError, match="timer failed"):
            generator.close()

        assert events == ["body-finally"]
        callback.assert_not_called()
        assert timer.call_count == 4

    def test_generator_close_runs_finally_when_resume_timer_fails(
        self,
    ) -> None:
        """Test close still closes the generator after resume failure."""
        events: list[str] = []
        timer = Mock(side_effect=[0.0, 1.0, RuntimeError("resume failed")])
        callback = Mock()

        @stopwatch(timer_func=timer, exit_callback=callback)
        def sample_generator() -> Generator[str, None, None]:
            try:
                yield "first"
            finally:
                events.append("body-finally")

        generator = sample_generator()

        assert next(generator) == "first"
        with pytest.raises(RuntimeError, match="resume failed"):
            generator.close()

        assert events == ["body-finally"]
        callback.assert_not_called()
        assert timer.call_count == 3

    def test_generator_close_ignored_generatorexit_keeps_timing_active(
        self,
    ) -> None:
        """Test ignored GeneratorExit does not finalize generator timing."""
        events: list[str] = []
        timer = Mock(
            side_effect=[0.0, 1.0, 10.0, 12.0, 20.0, 22.0, 30.0, 33.0],
        )
        callback = Mock()

        @stopwatch(timer_func=timer, exit_callback=callback)
        def sample_generator() -> Generator[str, None, None]:
            try:
                events.append("body-start")
                yield "first"
            except GeneratorExit:
                events.append("ignored-close")
                yield "ignored"
            events.append("body-tail")
            yield "tail"

        generator = sample_generator()

        assert next(generator) == "first"
        with pytest.raises(RuntimeError, match="ignored GeneratorExit"):
            generator.close()

        callback.assert_not_called()
        assert next(generator) == "tail"
        with pytest.raises(StopIteration):
            next(generator)

        assert events == ["body-start", "ignored-close", "body-tail"]
        callback.assert_called_once_with(8.0)

    def test_generator_close_does_not_report_after_pause_timer_fails(
        self,
    ) -> None:
        """Test close cleans up without reporting after pause failure."""
        events: list[str] = []
        timer = Mock(
            side_effect=[0.0, RuntimeError("pause failed"), 10.0],
        )
        callback = Mock()

        @stopwatch(timer_func=timer, exit_callback=callback)
        def sample_generator() -> Generator[str, None, None]:
            try:
                yield "first"
            finally:
                events.append("body-finally")

        generator = sample_generator()

        with pytest.raises(RuntimeError, match="pause failed"):
            next(generator)
        generator.close()

        assert events == ["body-finally"]
        callback.assert_not_called()
        assert timer.call_count == 2

    def test_generator_pause_timer_failure_closes_generator(self) -> None:
        """Test pause failure closes instead of leaving unmeasured values."""
        events: list[str] = []
        timer = Mock(
            side_effect=[0.0, RuntimeError("pause failed"), 10.0],
        )
        callback = Mock()

        @stopwatch(timer_func=timer, exit_callback=callback)
        def sample_generator() -> Generator[str, None, None]:
            try:
                yield "first"
                yield "second"
            finally:
                events.append("body-finally")

        generator = sample_generator()

        with pytest.raises(RuntimeError, match="pause failed"):
            next(generator)
        with pytest.raises(StopIteration):
            next(generator)

        assert events == ["body-finally"]
        callback.assert_not_called()
        assert timer.call_count == 2

    def test_generator_reentrant_next_does_not_stop_timing(self) -> None:
        """Test overlapping next rejection does not end generator timing."""
        first_value_started = threading.Event()
        first_value_can_finish = threading.Event()
        thread_results: list[str] = []
        thread_errors: list[BaseException] = []
        timer = Mock(side_effect=[0.0, 1.0, 10.0, 12.0, 20.0, 22.0])
        callback = Mock()

        @stopwatch(timer_func=timer, exit_callback=callback)
        def sample_generator() -> Generator[str, None, None]:
            first_value_started.set()
            first_value_can_finish.wait()
            yield "first"
            yield "second"

        generator = sample_generator()

        def consume_first_value() -> None:
            try:
                thread_results.append(next(generator))
            except BaseException as exc:
                thread_errors.append(exc)

        thread = threading.Thread(target=consume_first_value)
        thread.start()

        try:
            assert first_value_started.wait(timeout=5.0)
            with pytest.raises(ValueError, match="already executing"):
                next(generator)

            callback.assert_not_called()
        finally:
            first_value_can_finish.set()
            thread.join(timeout=5.0)

        assert thread_results == ["first"]
        assert thread_errors == []
        assert next(generator) == "second"
        with pytest.raises(StopIteration):
            next(generator)

        callback.assert_called_once_with(5.0)

    def test_generator_reentrant_close_does_not_stop_timing(self) -> None:
        """Test close while running does not end generator timing."""
        first_value_started = threading.Event()
        first_value_can_finish = threading.Event()
        thread_results: list[str] = []
        thread_errors: list[BaseException] = []
        timer = Mock(side_effect=[0.0, 1.0, 10.0, 12.0, 20.0, 22.0])
        callback = Mock()

        @stopwatch(timer_func=timer, exit_callback=callback)
        def sample_generator() -> Generator[str, None, None]:
            first_value_started.set()
            first_value_can_finish.wait()
            yield "first"
            yield "second"

        generator = sample_generator()

        def consume_first_value() -> None:
            try:
                thread_results.append(next(generator))
            except BaseException as exc:
                thread_errors.append(exc)

        thread = threading.Thread(target=consume_first_value)
        thread.start()

        try:
            assert first_value_started.wait(timeout=5.0)
            with pytest.raises(ValueError, match="already executing"):
                generator.close()

            callback.assert_not_called()
        finally:
            first_value_can_finish.set()
            thread.join(timeout=5.0)

        assert thread_results == ["first"]
        assert thread_errors == []
        assert next(generator) == "second"
        with pytest.raises(StopIteration):
            next(generator)

        callback.assert_called_once_with(5.0)

    def test_generator_callback_runs_after_body_exception(self) -> None:
        """Test generator body exceptions are measured before propagation."""
        events: list[str] = []

        def capture_callback(elapsed: float) -> None:
            events.append(f"callback:{elapsed}")

        timer = Mock(side_effect=[0.0, 1.0, 10.0, 12.0])

        @stopwatch(timer_func=timer, exit_callback=capture_callback)
        def failing_generator() -> Generator[str, None, None]:
            events.append("body-start")
            yield "first"
            events.append("body-error")
            raise ValueError("generator error")

        generator = failing_generator()

        assert next(generator) == "first"
        with pytest.raises(ValueError, match="generator error"):
            next(generator)

        assert events == [
            "body-start",
            "body-error",
            "callback:3.0",
        ]

    def test_generator_preserves_exception_when_stop_timer_fails(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Test stop failure does not replace generator body exception."""
        timer = Mock(
            side_effect=[0.0, 1.0, 10.0, RuntimeError("timer failed")],
        )
        callback = Mock()

        @stopwatch(timer_func=timer, exit_callback=callback)
        def failing_generator() -> Generator[str, None, None]:
            yield "first"
            raise ValueError("generator body failed")

        generator = failing_generator()

        assert next(generator) == "first"
        with (
            caplog.at_level(logging.ERROR, logger="ticko"),
            pytest.raises(ValueError, match="generator body failed"),
        ):
            next(generator)

        callback.assert_not_called()
        assert any(
            record.levelno >= logging.ERROR
            and (record.name == "ticko" or record.name.startswith("ticko."))
            and record.exc_info is not None
            and isinstance(record.exc_info[1], RuntimeError)
            and str(record.exc_info[1]) == "timer failed"
            for record in caplog.records
        )

    def test_generator_send_and_throw_reach_wrapped_generator(self) -> None:
        """Test send and throw preserve the wrapped generator protocol."""
        events: list[str] = []

        def capture_callback(elapsed: float) -> None:
            events.append(f"callback:{elapsed}")

        timer = Mock(side_effect=[0.0, 1.0, 10.0, 12.0, 20.0, 22.0])

        @stopwatch(timer_func=timer, exit_callback=capture_callback)
        def interactive_generator() -> Generator[str, str, str]:
            received = yield "ready"
            events.append(f"sent:{received}")
            try:
                yield f"echo:{received}"
            except KeyError as exc:
                events.append(f"caught:{exc.args[0]}")
                return "done"
            return "unused"

        generator = interactive_generator()

        assert next(generator) == "ready"
        assert generator.send("value") == "echo:value"
        with pytest.raises(StopIteration) as exc_info:
            generator.throw(KeyError("boom"))

        assert exc_info.value.value == "done"
        assert events == ["sent:value", "caught:boom", "callback:5.0"]

    def test_generator_send_before_start_rejects_value_without_timing(
        self,
    ) -> None:
        """Test send before start rejects non-None values before timing."""
        timer = Mock(side_effect=[0.0, 1.0, 10.0, 12.0])
        callback = Mock()

        @stopwatch(timer_func=timer, exit_callback=callback)
        def sample_generator() -> Generator[str, object, None]:
            yield "ready"

        generator = sample_generator()

        with pytest.raises(TypeError, match="non-None"):
            generator.send("value")

        timer.assert_not_called()
        callback.assert_not_called()
        assert next(generator) == "ready"
        generator.close()
        callback.assert_called_once_with(3.0)

    @pytest.mark.parametrize(
        "args",
        [
            (ValueError("x"), ValueError("y")),
            ("bad",),
            (ValueError, None, "bad traceback"),
        ],
    )
    def test_generator_throw_invalid_args_do_not_stop_timing(
        self,
        args: tuple[object, ...],
    ) -> None:
        """Test invalid throw arguments do not end generator timing."""
        timer = Mock(side_effect=[0.0, 1.0, 10.0, 12.0, 20.0, 22.0])
        callback = Mock()

        @stopwatch(timer_func=timer, exit_callback=callback)
        def sample_generator() -> Generator[str, None, None]:
            yield "ready"
            yield "second"

        generator = sample_generator()
        throw = cast("Callable[..., object]", generator.throw)

        assert next(generator) == "ready"
        with pytest.raises(TypeError):
            throw(*args)
        callback.assert_not_called()
        assert next(generator) == "second"
        with pytest.raises(StopIteration):
            next(generator)

        callback.assert_called_once_with(5.0)

    def test_generator_throw_accepts_deprecated_instance_with_none_value(
        self,
    ) -> None:
        """Test throw(instance, None) remains native-compatible."""
        events: list[str] = []

        def capture_callback(elapsed: float) -> None:
            events.append(f"callback:{elapsed}")

        timer = Mock(side_effect=[0.0, 1.0, 10.0, 12.0])

        @stopwatch(timer_func=timer, exit_callback=capture_callback)
        def sample_generator() -> Generator[str, None, None]:
            try:
                yield "ready"
            except ValueError as exc:
                events.append(f"caught:{exc.args[0]}")

        generator = sample_generator()

        assert next(generator) == "ready"
        warning_context = (
            pytest.warns(DeprecationWarning, match="deprecated")
            if sys.version_info >= (3, 12)
            else nullcontext()
        )
        with warning_context, pytest.raises(StopIteration):
            generator.throw(ValueError("x"), None)

        assert events == ["caught:x", "callback:3.0"]


class TestAsyncGeneratorWrappedFunctions:
    """Test async generator functions."""

    def test_async_generator_creation_does_not_start_timer(self) -> None:
        """Test async generator creation is not measured before consumption."""
        callback = Mock()
        timer = Mock(side_effect=[0.0, 1.0])

        @stopwatch(timer_func=timer, exit_callback=callback)
        async def sample_generator() -> AsyncGenerator[str, None]:
            yield "value"

        async def run() -> None:
            generator = sample_generator()
            assert isinstance(generator, AsyncGenerator)
            timer.assert_not_called()
            callback.assert_not_called()
            await generator.aclose()

        asyncio.run(run())

    def test_async_generator_callback_runs_after_consumption(self) -> None:
        """Test callback runs after an async generator is fully consumed."""
        events: list[str] = []

        def capture_callback(elapsed: float) -> None:
            events.append(f"callback:{elapsed}")

        timer = Mock(side_effect=[0.0, 1.0, 10.0, 12.0])

        @stopwatch(timer_func=timer, exit_callback=capture_callback)
        async def sample_generator() -> AsyncGenerator[str, None]:
            events.append("body-start")
            yield "first"
            events.append("body-end")

        async def run() -> list[str]:
            return [value async for value in sample_generator()]

        assert asyncio.run(run()) == ["first"]
        assert events == ["body-start", "body-end", "callback:3.0"]

    def test_async_generator_excludes_time_between_yields(self) -> None:
        """Test consumer time between yielded values is not measured."""
        callback = Mock()
        timer = Mock(side_effect=[0.0, 1.0, 101.0, 103.0, 203.0, 206.0])

        @stopwatch(timer_func=timer, exit_callback=callback)
        async def sample_generator() -> AsyncGenerator[str, None]:
            yield "first"
            yield "second"

        async def run() -> None:
            generator = sample_generator()
            assert await anext(generator) == "first"
            assert await anext(generator) == "second"
            with pytest.raises(StopAsyncIteration):
                await anext(generator)

        asyncio.run(run())

        callback.assert_called_once_with(6.0)

    def test_async_generator_callable_object_callback_runs_after_consumption(
        self,
    ) -> None:
        """Test callable object async generator consumption is measured."""
        events: list[str] = []

        def capture_callback(elapsed: float) -> None:
            events.append(f"callback:{elapsed}")

        class Work:
            async def __call__(self) -> AsyncGenerator[str, None]:
                events.append("body-start")
                yield "first"
                events.append("body-end")

        timer = Mock(side_effect=[0.0, 1.0, 10.0, 12.0])
        decorated = stopwatch(
            Work(),
            timer_func=timer,
            exit_callback=capture_callback,
        )

        async def run() -> list[str]:
            generator = decorated()
            timer.assert_not_called()
            return [value async for value in generator]

        assert asyncio.run(run()) == ["first"]
        assert events == ["body-start", "body-end", "callback:3.0"]

    def test_async_generator_aclose_stops_timing_once(self) -> None:
        """Test aclose reports elapsed time after partial consumption."""
        events: list[str] = []

        def capture_callback(elapsed: float) -> None:
            events.append(f"callback:{elapsed}")

        timer = Mock(side_effect=[0.0, 1.0, 10.0, 12.0, 99.0])

        @stopwatch(timer_func=timer, exit_callback=capture_callback)
        async def sample_generator() -> AsyncGenerator[str, None]:
            try:
                yield "first"
                yield "second"
            finally:
                events.append("body-finally")

        async def run() -> None:
            generator = sample_generator()
            assert await anext(generator) == "first"
            await generator.aclose()
            await generator.aclose()

        asyncio.run(run())

        assert events == ["body-finally", "callback:3.0"]
        assert timer.call_count == 4

    def test_async_generator_aclose_propagates_stop_timer_failure(
        self,
    ) -> None:
        """Test aclose propagates stop timer failure after body cleanup."""
        events: list[str] = []
        timer = Mock(
            side_effect=[0.0, 1.0, 10.0, RuntimeError("timer failed")],
        )
        callback = Mock()

        @stopwatch(timer_func=timer, exit_callback=callback)
        async def sample_generator() -> AsyncGenerator[str, None]:
            try:
                yield "first"
            finally:
                events.append("body-finally")

        async def run() -> None:
            generator = sample_generator()
            assert await anext(generator) == "first"
            with pytest.raises(RuntimeError, match="timer failed"):
                await generator.aclose()

        asyncio.run(run())

        assert events == ["body-finally"]
        callback.assert_not_called()
        assert timer.call_count == 4

    def test_async_generator_aclose_runs_finally_when_resume_timer_fails(
        self,
    ) -> None:
        """Test aclose still closes the generator after resume failure."""
        events: list[str] = []
        timer = Mock(side_effect=[0.0, 1.0, RuntimeError("resume failed")])
        callback = Mock()

        @stopwatch(timer_func=timer, exit_callback=callback)
        async def sample_generator() -> AsyncGenerator[str, None]:
            try:
                yield "first"
            finally:
                events.append("body-finally")

        async def run() -> None:
            generator = sample_generator()
            assert await anext(generator) == "first"
            with pytest.raises(RuntimeError, match="resume failed"):
                await generator.aclose()

        asyncio.run(run())

        assert events == ["body-finally"]
        callback.assert_not_called()
        assert timer.call_count == 3

    def test_async_generator_aclose_ignored_generatorexit_keeps_timing_active(
        self,
    ) -> None:
        """Test ignored GeneratorExit does not finalize async timing."""
        events: list[str] = []
        timer = Mock(
            side_effect=[0.0, 1.0, 10.0, 12.0, 20.0, 22.0, 30.0, 33.0],
        )
        callback = Mock()

        @stopwatch(timer_func=timer, exit_callback=callback)
        async def sample_generator() -> AsyncGenerator[str, None]:
            try:
                events.append("body-start")
                yield "first"
            except GeneratorExit:
                events.append("ignored-close")
                yield "ignored"
            events.append("body-tail")
            yield "tail"

        async def run() -> None:
            generator = sample_generator()
            assert await anext(generator) == "first"
            with pytest.raises(RuntimeError, match="ignored GeneratorExit"):
                await generator.aclose()

            callback.assert_not_called()
            assert await anext(generator) == "tail"
            with pytest.raises(StopAsyncIteration):
                await anext(generator)

        asyncio.run(run())

        assert events == ["body-start", "ignored-close", "body-tail"]
        callback.assert_called_once_with(8.0)

    def test_async_generator_aclose_does_not_report_after_pause_timer_fails(
        self,
    ) -> None:
        """Test aclose cleans up without reporting after pause failure."""
        events: list[str] = []
        timer = Mock(
            side_effect=[0.0, RuntimeError("pause failed"), 10.0],
        )
        callback = Mock()

        @stopwatch(timer_func=timer, exit_callback=callback)
        async def sample_generator() -> AsyncGenerator[str, None]:
            try:
                yield "first"
            finally:
                events.append("body-finally")

        async def run() -> None:
            generator = sample_generator()
            with pytest.raises(RuntimeError, match="pause failed"):
                await anext(generator)
            await generator.aclose()

        asyncio.run(run())

        assert events == ["body-finally"]
        callback.assert_not_called()
        assert timer.call_count == 2

    def test_async_generator_pause_timer_failure_closes_generator(
        self,
    ) -> None:
        """Test pause failure closes instead of leaving unmeasured values."""
        events: list[str] = []
        timer = Mock(
            side_effect=[0.0, RuntimeError("pause failed"), 10.0],
        )
        callback = Mock()

        @stopwatch(timer_func=timer, exit_callback=callback)
        async def sample_generator() -> AsyncGenerator[str, None]:
            try:
                yield "first"
                yield "second"
            finally:
                events.append("body-finally")

        async def run() -> None:
            generator = sample_generator()
            with pytest.raises(RuntimeError, match="pause failed"):
                await anext(generator)
            with pytest.raises(StopAsyncIteration):
                await anext(generator)

        asyncio.run(run())

        assert events == ["body-finally"]
        callback.assert_not_called()
        assert timer.call_count == 2

    def test_async_generator_reentrant_anext_does_not_stop_timing(
        self,
    ) -> None:
        """Test overlapping anext rejection does not end timing."""
        timer = Mock(side_effect=[0.0, 1.0, 10.0, 12.0, 20.0, 22.0])
        callback = Mock()

        async def run() -> None:
            first_value_started = asyncio.Event()
            first_value_can_finish = asyncio.Event()

            @stopwatch(timer_func=timer, exit_callback=callback)
            async def sample_generator() -> AsyncGenerator[str, None]:
                first_value_started.set()
                await first_value_can_finish.wait()
                yield "first"
                yield "second"

            generator = sample_generator()
            first_value_task = asyncio.create_task(anext(generator))

            try:
                await asyncio.wait_for(first_value_started.wait(), timeout=5.0)
                with pytest.raises(RuntimeError, match="already running"):
                    await anext(generator)

                callback.assert_not_called()
            finally:
                first_value_can_finish.set()
            assert await first_value_task == "first"
            assert await anext(generator) == "second"
            with pytest.raises(StopAsyncIteration):
                await anext(generator)

        asyncio.run(run())
        callback.assert_called_once_with(5.0)

    def test_async_generator_reentrant_aclose_does_not_stop_timing(
        self,
    ) -> None:
        """Test aclose while running does not end timing."""
        timer = Mock(side_effect=[0.0, 1.0, 10.0, 12.0, 20.0, 22.0])
        callback = Mock()

        async def run() -> None:
            first_value_started = asyncio.Event()
            first_value_can_finish = asyncio.Event()

            @stopwatch(timer_func=timer, exit_callback=callback)
            async def sample_generator() -> AsyncGenerator[str, None]:
                first_value_started.set()
                await first_value_can_finish.wait()
                yield "first"
                yield "second"

            generator = sample_generator()
            first_value_task = asyncio.create_task(anext(generator))

            try:
                await asyncio.wait_for(first_value_started.wait(), timeout=5.0)
                with pytest.raises(RuntimeError, match="already running"):
                    await generator.aclose()

                callback.assert_not_called()
            finally:
                first_value_can_finish.set()
            assert await first_value_task == "first"
            assert await anext(generator) == "second"
            with pytest.raises(StopAsyncIteration):
                await anext(generator)

        asyncio.run(run())
        callback.assert_called_once_with(5.0)

    def test_async_generator_implicit_shutdown_does_not_report_time(
        self,
    ) -> None:
        """Test implicit async generator shutdown does not report time."""
        events: list[str] = []

        def capture_callback(elapsed: float) -> None:
            events.append(f"callback:{elapsed}")

        timer = Mock(side_effect=[0.0, 1.0])

        @stopwatch(timer_func=timer, exit_callback=capture_callback)
        async def sample_generator() -> AsyncGenerator[str, None]:
            try:
                yield "first"
                yield "second"
            finally:
                events.append("body-finally")

        async def run() -> None:
            generator = sample_generator()
            assert await anext(generator) == "first"

        asyncio.run(run())

        assert events == ["body-finally"]
        assert timer.call_count == 2

    def test_async_generator_callback_runs_after_body_exception(self) -> None:
        """Test async generator body exceptions are measured."""
        events: list[str] = []

        def capture_callback(elapsed: float) -> None:
            events.append(f"callback:{elapsed}")

        timer = Mock(side_effect=[0.0, 1.0, 10.0, 12.0])

        @stopwatch(timer_func=timer, exit_callback=capture_callback)
        async def failing_generator() -> AsyncGenerator[str, None]:
            events.append("body-start")
            yield "first"
            events.append("body-error")
            raise ValueError("async generator error")

        async def run() -> None:
            generator = failing_generator()
            assert await anext(generator) == "first"
            with pytest.raises(ValueError, match="async generator error"):
                await anext(generator)

        asyncio.run(run())

        assert events == [
            "body-start",
            "body-error",
            "callback:3.0",
        ]

    def test_async_generator_preserves_exception_when_stop_timer_fails(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Test stop failure does not replace async generator exception."""
        timer = Mock(
            side_effect=[0.0, 1.0, 10.0, RuntimeError("timer failed")],
        )
        callback = Mock()

        @stopwatch(timer_func=timer, exit_callback=callback)
        async def failing_generator() -> AsyncGenerator[str, None]:
            yield "first"
            raise ValueError("async generator body failed")

        async def run() -> None:
            generator = failing_generator()
            assert await anext(generator) == "first"
            with (
                caplog.at_level(logging.ERROR, logger="ticko"),
                pytest.raises(
                    ValueError,
                    match="async generator body failed",
                ),
            ):
                await anext(generator)

        asyncio.run(run())

        callback.assert_not_called()
        assert any(
            record.levelno >= logging.ERROR
            and (record.name == "ticko" or record.name.startswith("ticko."))
            and record.exc_info is not None
            and isinstance(record.exc_info[1], RuntimeError)
            and str(record.exc_info[1]) == "timer failed"
            for record in caplog.records
        )

    def test_async_generator_asend_and_athrow_reach_wrapped_generator(
        self,
    ) -> None:
        """Test asend and athrow preserve the wrapped generator protocol."""
        events: list[str] = []

        def capture_callback(elapsed: float) -> None:
            events.append(f"callback:{elapsed}")

        timer = Mock(side_effect=[0.0, 1.0, 10.0, 12.0, 20.0, 22.0])

        @stopwatch(timer_func=timer, exit_callback=capture_callback)
        async def interactive_generator() -> AsyncGenerator[str, str]:
            received = yield "ready"
            events.append(f"sent:{received}")
            try:
                yield f"echo:{received}"
            except KeyError as exc:
                events.append(f"caught:{exc.args[0]}")

        async def run() -> None:
            generator = interactive_generator()
            assert await anext(generator) == "ready"
            assert await generator.asend("value") == "echo:value"
            with pytest.raises(StopAsyncIteration):
                await generator.athrow(KeyError("boom"))

        asyncio.run(run())

        assert events == ["sent:value", "caught:boom", "callback:5.0"]

    def test_async_generator_asend_before_start_rejects_value_without_timing(
        self,
    ) -> None:
        """Test asend before start rejects non-None values before timing."""
        timer = Mock(side_effect=[0.0, 1.0, 10.0, 12.0])
        callback = Mock()

        @stopwatch(timer_func=timer, exit_callback=callback)
        async def sample_generator() -> AsyncGenerator[str, object]:
            yield "ready"

        async def run() -> None:
            generator = sample_generator()
            with pytest.raises(TypeError, match="non-None"):
                await generator.asend("value")
            timer.assert_not_called()
            callback.assert_not_called()
            assert await anext(generator) == "ready"
            await generator.aclose()

        asyncio.run(run())
        callback.assert_called_once_with(3.0)

    @pytest.mark.parametrize(
        "args",
        [
            (ValueError("x"), ValueError("y")),
            ("bad",),
            (ValueError, None, "bad traceback"),
        ],
    )
    def test_async_generator_athrow_invalid_args_do_not_stop_timing(
        self,
        args: tuple[object, ...],
    ) -> None:
        """Test invalid athrow arguments do not end generator timing."""
        timer = Mock(side_effect=[0.0, 1.0, 10.0, 12.0, 20.0, 22.0])
        callback = Mock()

        @stopwatch(timer_func=timer, exit_callback=callback)
        async def sample_generator() -> AsyncGenerator[str, None]:
            yield "ready"
            yield "second"

        async def run() -> None:
            generator = sample_generator()
            invalid_athrow = cast(
                "Callable[..., Awaitable[str]]",
                generator.athrow,
            )
            assert await anext(generator) == "ready"
            with pytest.raises(TypeError):
                await invalid_athrow(*args)
            callback.assert_not_called()
            assert await anext(generator) == "second"
            with pytest.raises(StopAsyncIteration):
                await anext(generator)

        asyncio.run(run())
        callback.assert_called_once_with(5.0)

    def test_async_generator_athrow_accepts_deprecated_instance_with_none_value(
        self,
    ) -> None:
        """Test athrow(instance, None) remains native-compatible."""
        events: list[str] = []

        def capture_callback(elapsed: float) -> None:
            events.append(f"callback:{elapsed}")

        timer = Mock(side_effect=[0.0, 1.0, 10.0, 12.0])

        @stopwatch(timer_func=timer, exit_callback=capture_callback)
        async def sample_generator() -> AsyncGenerator[str, None]:
            try:
                yield "ready"
            except ValueError as exc:
                events.append(f"caught:{exc.args[0]}")

        async def run() -> None:
            generator = sample_generator()
            assert await anext(generator) == "ready"
            warning_context = (
                pytest.warns(DeprecationWarning, match="deprecated")
                if sys.version_info >= (3, 12)
                else nullcontext()
            )
            with warning_context, pytest.raises(StopAsyncIteration):
                await generator.athrow(ValueError("x"), None)

        asyncio.run(run())

        assert events == ["caught:x", "callback:3.0"]

    @pytest.mark.parametrize(
        ("method_name", "kwargs"),
        [
            ("asend", {"value": None}),
            ("athrow", {"typ": ValueError}),
        ],
    )
    def test_async_generator_protocol_methods_reject_keyword_args(
        self,
        method_name: str,
        kwargs: dict[str, object],
    ) -> None:
        """Test async generator protocol methods reject keyword arguments."""
        timer = Mock(side_effect=[0.0, 4.0])
        callback = Mock()

        @stopwatch(timer_func=timer, exit_callback=callback)
        async def sample_generator() -> AsyncGenerator[str, None]:
            yield "ready"

        async def run() -> None:
            generator = sample_generator()
            method = cast(
                "Callable[..., Awaitable[str]]",
                getattr(generator, method_name),
            )
            with pytest.raises(TypeError, match="keyword"):
                await method(**kwargs)

        asyncio.run(run())
        timer.assert_not_called()
        callback.assert_not_called()
