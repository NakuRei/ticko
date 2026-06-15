"""Decorator for measuring function execution time."""

import functools
import inspect
import logging
import time
from collections.abc import AsyncGenerator, Awaitable, Callable, Generator
from types import TracebackType
from typing import ParamSpec, TypeVar, cast, overload

from ._stopwatch import Stopwatch

logger = logging.getLogger(__name__)

P = ParamSpec("P")
R = TypeVar("R")
_MISSING = object()


def _stop_during_exception_unwind(sw: Stopwatch) -> None:
    """Stop while the wrapped function's exception is propagating.

    A stop failure of type Exception is logged instead of raised so that
    it never masks the original exception. BaseException (for example
    KeyboardInterrupt) still propagates.
    """
    try:
        sw.stop()
    except Exception:
        logger.exception("Stopwatch stop failed during exception cleanup")


def _validate_send_value_before_start(
    value: object,
    *,
    async_generator: bool,
) -> None:
    """Reject values that native generators reject before first yield."""
    if value is None:
        return
    generator_type = "async generator" if async_generator else "generator"
    message = f"can't send non-None value to a just-started {generator_type}"
    raise TypeError(message)


def _validate_throw_arguments(
    typ: object,
    val: object,
    tb: object,
) -> None:
    """Reject throw arguments before they can affect timing state."""
    if isinstance(typ, BaseException):
        if val is not _MISSING and val is not None:
            message = "instance exception may not have a separate value"
            raise TypeError(message)
    elif not (isinstance(typ, type) and issubclass(typ, BaseException)):
        typ_name = type(typ).__name__
        message = (
            "exceptions must be classes or instances deriving from "
            f"BaseException, not {typ_name}"
        )
        raise TypeError(message)

    if tb is _MISSING or tb is None or isinstance(tb, TracebackType):
        return

    message = "throw() third argument must be a traceback object"
    raise TypeError(message)


class _GeneratorExecutionTimer:
    """Track only the time spent inside a generator body."""

    def __init__(
        self,
        timer_func: Callable[[], float],
        callback: Callable[[float], None],
    ) -> None:
        self._timer_func = timer_func
        self._callback = callback
        self._stopwatch: Stopwatch | None = None
        self._paused_after_yield = False
        self._finalized = False

    @property
    def has_started(self) -> bool:
        """Return whether timing has started at least once."""
        return self._stopwatch is not None

    @property
    def is_finalized(self) -> bool:
        """Return whether no more elapsed time will be reported."""
        return self._finalized

    def start_or_resume_body(self) -> None:
        """Start or resume timing before generator body execution."""
        if self._finalized:
            return
        if self._stopwatch is None:
            stopwatch = Stopwatch(
                timer_func=self._timer_func,
                exit_callback=self._callback,
            )
            stopwatch.start()
            self._stopwatch = stopwatch
            self._paused_after_yield = False
            return
        if self._paused_after_yield:
            self._stopwatch.resume()
            self._paused_after_yield = False

    def pause_after_yield(self) -> None:
        """Pause timing after the generator yields to its consumer."""
        if (
            self._stopwatch is None
            or self._finalized
            or self._paused_after_yield
        ):
            return
        self._stopwatch.pause()
        self._paused_after_yield = True

    def resume_cleanup_body(self) -> None:
        """Resume timing before explicit or GC-triggered generator cleanup."""
        if (
            self._stopwatch is None
            or self._finalized
            or not self._paused_after_yield
        ):
            return
        self._stopwatch.resume()
        self._paused_after_yield = False

    def stop_after_completion(self) -> None:
        """Stop timing after normal completion or explicit close."""
        if self._finalized:
            return
        if self._stopwatch is None:
            self._finalized = True
            return
        stopwatch = self._stopwatch
        self._finalized = True
        self._paused_after_yield = False
        stopwatch.stop()

    def stop_during_exception_unwind(self) -> None:
        """Stop timing while preserving a generator body exception."""
        if self._finalized:
            return
        if self._stopwatch is None:
            self._finalized = True
            return
        stopwatch = self._stopwatch
        self._finalized = True
        self._paused_after_yield = False
        _stop_during_exception_unwind(stopwatch)

    def discard_incomplete_timing(self) -> None:
        """Finalize without reporting a measurement that cannot continue."""
        self._finalized = True
        self._paused_after_yield = False

    def stop_after_cleanup(self) -> None:
        """Stop timing during GC cleanup without raising stop failures."""
        if self._finalized:
            return
        if self._stopwatch is None:
            self._finalized = True
            return
        stopwatch = self._stopwatch
        self._finalized = True
        self._paused_after_yield = False
        try:
            stopwatch.stop()
        except BaseException:
            logger.exception("Stopwatch stop failed during generator cleanup")


def _resolve_exit_callback(
    f: Callable[..., object],
    exit_callback: Callable[[float], None] | None,
) -> Callable[[float], None]:
    """Return the configured callback or the stdout-printing default."""
    if exit_callback is not None:
        return exit_callback

    callable_name = getattr(f, "__name__", None)
    if not isinstance(callable_name, str):
        callable_name = getattr(f, "__qualname__", None)
    if not isinstance(callable_name, str):
        callable_name = type(f).__name__

    def _default_callback(elapsed: float) -> None:
        # Default callback intentionally writes timing output to stdout.
        print(  # noqa: T201
            f"Function {callable_name!r} exited after {elapsed:.6f} seconds",
        )

    return _default_callback


def _wrap_async(
    f: Callable[P, R],
    timer_func: Callable[[], float],
    callback: Callable[[float], None],
) -> Callable[P, R]:
    """Wrap an async callable so each call is timed by a Stopwatch."""
    async_func = cast("Callable[P, Awaitable[object]]", f)

    @functools.wraps(f)
    async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> object:
        sw = Stopwatch(timer_func=timer_func, exit_callback=callback)
        sw.start()
        try:
            result = await async_func(*args, **kwargs)
        except BaseException:
            _stop_during_exception_unwind(sw)
            raise
        else:
            sw.stop()
            return result

    return cast("Callable[P, R]", async_wrapper)


class _TimedAsyncGenerator:
    """Time async generator consumption while preserving its protocol."""

    def __init__(
        self,
        async_generator: AsyncGenerator[object, object],
        timer_func: Callable[[], float],
        callback: Callable[[float], None],
    ) -> None:
        self._async_generator = async_generator
        self._async_generator_closed = False
        self._is_driving = False
        self._execution_timer = _GeneratorExecutionTimer(
            timer_func,
            callback,
        )

    def __aiter__(self) -> "_TimedAsyncGenerator":
        """Return the async iterator."""
        return self

    async def __anext__(self) -> object:
        """Return the next value from the wrapped async generator."""
        return await self._await_with_timing(
            self._async_generator.__anext__,
            "anext",
        )

    async def asend(self, value: object, /) -> object:
        """Send a value into the wrapped async generator."""
        self._reject_if_driving("anext")
        if (
            not self._execution_timer.has_started
            and not self._execution_timer.is_finalized
        ):
            _validate_send_value_before_start(
                value,
                async_generator=True,
            )
        return await self._await_with_timing(
            lambda: self._async_generator.asend(value),
            "anext",
        )

    async def athrow(
        self,
        typ: BaseException | type[BaseException],
        val: object = _MISSING,
        tb: object = _MISSING,
        /,
    ) -> object:
        """Throw an exception into the wrapped async generator."""
        self._reject_if_driving("athrow")
        _validate_throw_arguments(typ, val, tb)
        athrow = cast(
            "Callable[..., Awaitable[object]]",
            self._async_generator.athrow,
        )

        def create_athrow_awaitable() -> Awaitable[object]:
            if val is _MISSING:
                return athrow(typ)
            if tb is _MISSING:
                return athrow(typ, val)
            return athrow(typ, val, tb)

        if (
            not self._execution_timer.has_started
            and not self._execution_timer.is_finalized
        ):
            return await self._athrow_before_start(create_athrow_awaitable)
        return await self._await_with_timing(
            create_athrow_awaitable,
            "athrow",
        )

    async def _athrow_before_start(
        self,
        create_awaitable: Callable[[], Awaitable[object]],
    ) -> object:
        self._is_driving = True
        try:
            return await create_awaitable()
        finally:
            try:
                if self._async_generator_is_closed():
                    self._async_generator_closed = True
                    self._execution_timer.stop_after_completion()
            finally:
                self._is_driving = False

    async def aclose(self) -> None:
        """Close the wrapped async generator."""
        self._reject_if_driving("aclose")
        self._is_driving = True
        try:
            try:
                self._execution_timer.resume_cleanup_body()
            except BaseException:
                self._execution_timer.discard_incomplete_timing()
                try:
                    await self._close_async_generator()
                except BaseException:
                    logger.exception("Async generator cleanup failed")
                raise

            try:
                await self._close_async_generator()
            except BaseException:
                if self._async_generator_is_suspended():
                    self._pause_after_failed_close_yield()
                else:
                    self._execution_timer.stop_during_exception_unwind()
                raise
            else:
                self._execution_timer.stop_after_completion()
        finally:
            self._is_driving = False

    async def _close_async_generator(self) -> None:
        if self._async_generator_closed:
            return
        try:
            await self._async_generator.aclose()
        except BaseException:
            if self._async_generator_is_closed():
                self._async_generator_closed = True
            raise
        else:
            self._async_generator_closed = True

    def _async_generator_is_closed(self) -> bool:
        return getattr(self._async_generator, "ag_frame", None) is None

    def _async_generator_is_suspended(self) -> bool:
        return not self._async_generator_is_closed() and not getattr(
            self._async_generator, "ag_running", False
        )

    def _pause_after_failed_close_yield(self) -> None:
        try:
            self._execution_timer.pause_after_yield()
        except Exception:
            logger.exception(
                "Stopwatch pause failed after async generator close failure",
            )
            self._execution_timer.discard_incomplete_timing()

    async def _await_with_timing(
        self,
        create_awaitable: Callable[[], Awaitable[object]],
        method_name: str,
    ) -> object:
        self._reject_if_driving(method_name)
        self._is_driving = True
        try:
            self._execution_timer.start_or_resume_body()
            try:
                result = await create_awaitable()
            except StopAsyncIteration:
                self._async_generator_closed = True
                self._execution_timer.stop_after_completion()
                raise
            except BaseException:
                self._execution_timer.stop_during_exception_unwind()
                raise
            else:
                try:
                    self._execution_timer.pause_after_yield()
                except BaseException:
                    self._execution_timer.discard_incomplete_timing()
                    try:
                        await self._close_async_generator()
                    except BaseException:
                        logger.exception("Async generator cleanup failed")
                    raise
                return result
        finally:
            self._is_driving = False

    def _reject_if_driving(self, method_name: str) -> None:
        if self._is_driving:
            message = (
                f"{method_name}(): asynchronous generator is already running"
            )
            raise RuntimeError(message)


class _TimedGenerator:
    """Time generator consumption while preserving its protocol."""

    def __init__(
        self,
        generator: Generator[object, object, object],
        timer_func: Callable[[], float],
        callback: Callable[[float], None],
    ) -> None:
        self._generator = generator
        self._generator_closed = False
        self._is_driving = False
        self._execution_timer = _GeneratorExecutionTimer(
            timer_func,
            callback,
        )

    def __iter__(self) -> "_TimedGenerator":
        """Return the iterator."""
        return self

    def __next__(self) -> object:
        """Return the next value from the wrapped generator."""
        return self._resume_with_timing(self._generator.__next__)

    def __del__(self) -> None:
        """Finalize timing when the wrapper is garbage collected."""
        self._close_for_cleanup()

    def send(self, value: object, /) -> object:
        """Send a value into the wrapped generator."""
        self._reject_if_driving()
        if (
            not self._execution_timer.has_started
            and not self._execution_timer.is_finalized
        ):
            _validate_send_value_before_start(
                value,
                async_generator=False,
            )
        return self._resume_with_timing(
            lambda: self._generator.send(value),
        )

    def throw(
        self,
        typ: BaseException | type[BaseException],
        val: object = _MISSING,
        tb: object = _MISSING,
        /,
    ) -> object:
        """Throw an exception into the wrapped generator."""
        self._reject_if_driving()
        _validate_throw_arguments(typ, val, tb)
        throw = cast("Callable[..., object]", self._generator.throw)

        def throw_into_generator() -> object:
            if val is _MISSING:
                return throw(typ)
            if tb is _MISSING:
                return throw(typ, val)
            return throw(typ, val, tb)

        if (
            not self._execution_timer.has_started
            and not self._execution_timer.is_finalized
        ):
            return self._throw_before_start(throw_into_generator)
        return self._resume_with_timing(throw_into_generator)

    def _throw_before_start(
        self,
        throw_into_generator: Callable[[], object],
    ) -> object:
        self._is_driving = True
        try:
            return throw_into_generator()
        finally:
            try:
                if self._generator_is_closed():
                    self._generator_closed = True
                    self._execution_timer.stop_after_completion()
            finally:
                self._is_driving = False

    def close(self) -> None:
        """Close the wrapped generator."""
        self._reject_if_driving()
        self._is_driving = True
        try:
            try:
                self._execution_timer.resume_cleanup_body()
            except BaseException:
                self._execution_timer.discard_incomplete_timing()
                try:
                    self._close_generator()
                except BaseException:
                    logger.exception("Generator cleanup failed")
                raise

            try:
                self._close_generator()
            except BaseException:
                if self._generator_is_suspended():
                    self._pause_after_failed_close_yield()
                else:
                    self._execution_timer.stop_during_exception_unwind()
                raise
            else:
                self._execution_timer.stop_after_completion()
        finally:
            self._is_driving = False

    def _close_for_cleanup(self) -> None:
        if self._generator_closed:
            return
        if self._is_driving:
            return
        try:
            self._execution_timer.resume_cleanup_body()
        except BaseException:
            logger.exception("Stopwatch resume failed during generator cleanup")
            self._execution_timer.discard_incomplete_timing()
            try:
                self._close_generator()
            except BaseException:
                logger.exception("Generator cleanup failed")
            return

        try:
            self._close_generator()
        except BaseException:
            logger.exception("Generator cleanup failed")
        self._execution_timer.stop_after_cleanup()

    def _close_generator(self) -> None:
        if self._generator_closed:
            return
        try:
            self._generator.close()
        except BaseException:
            if self._generator_is_closed():
                self._generator_closed = True
            raise
        else:
            self._generator_closed = True

    def _generator_is_closed(self) -> bool:
        return inspect.getgeneratorstate(self._generator) == inspect.GEN_CLOSED

    def _generator_is_suspended(self) -> bool:
        return (
            inspect.getgeneratorstate(self._generator) == inspect.GEN_SUSPENDED
        )

    def _pause_after_failed_close_yield(self) -> None:
        try:
            self._execution_timer.pause_after_yield()
        except Exception:
            logger.exception(
                "Stopwatch pause failed after generator close failure",
            )
            self._execution_timer.discard_incomplete_timing()

    def _resume_with_timing(
        self,
        resume: Callable[[], object],
    ) -> object:
        self._reject_if_driving()
        self._is_driving = True
        try:
            self._execution_timer.start_or_resume_body()
            try:
                result = resume()
            except StopIteration:
                self._generator_closed = True
                self._execution_timer.stop_after_completion()
                raise
            except BaseException:
                self._execution_timer.stop_during_exception_unwind()
                raise
            else:
                try:
                    self._execution_timer.pause_after_yield()
                except BaseException:
                    self._execution_timer.discard_incomplete_timing()
                    try:
                        self._close_generator()
                    except BaseException:
                        logger.exception("Generator cleanup failed")
                    raise
                return result
        finally:
            self._is_driving = False

    def _reject_if_driving(self) -> None:
        if self._is_driving:
            message = "generator already executing"
            raise ValueError(message)


def _wrap_async_generator(
    f: Callable[P, R],
    timer_func: Callable[[], float],
    callback: Callable[[float], None],
) -> Callable[P, R]:
    """Wrap an async generator so consumption is timed by a Stopwatch."""
    async_generator_func = cast(
        "Callable[P, AsyncGenerator[object, object]]",
        f,
    )

    @functools.wraps(f)
    def async_generator_wrapper(
        *args: P.args,
        **kwargs: P.kwargs,
    ) -> _TimedAsyncGenerator:
        return _TimedAsyncGenerator(
            async_generator_func(*args, **kwargs),
            timer_func,
            callback,
        )

    return cast("Callable[P, R]", async_generator_wrapper)


def _wrap_generator(
    f: Callable[P, R],
    timer_func: Callable[[], float],
    callback: Callable[[float], None],
) -> Callable[P, R]:
    """Wrap a generator so consumption is timed by a Stopwatch."""
    generator_func = cast("Callable[P, Generator[object, object, object]]", f)

    @functools.wraps(f)
    def generator_wrapper(
        *args: P.args,
        **kwargs: P.kwargs,
    ) -> _TimedGenerator:
        return _TimedGenerator(
            generator_func(*args, **kwargs),
            timer_func,
            callback,
        )

    return cast("Callable[P, R]", generator_wrapper)


def _wrap_sync(
    f: Callable[P, R],
    timer_func: Callable[[], float],
    callback: Callable[[float], None],
) -> Callable[P, R]:
    """Wrap a sync callable so each call is timed by a Stopwatch."""

    @functools.wraps(f)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        sw = Stopwatch(timer_func=timer_func, exit_callback=callback)
        sw.start()
        try:
            result = f(*args, **kwargs)
        except BaseException:
            _stop_during_exception_unwind(sw)
            raise
        else:
            sw.stop()
            return result

    return wrapper


# Overload 1: Decorator without arguments (@stopwatch)
@overload
def stopwatch(
    func: Callable[P, R],
) -> Callable[P, R]: ...


# Overload 2: Direct decoration with arguments (stopwatch(func, ...))
@overload
def stopwatch(
    func: Callable[P, R],
    *,
    timer_func: Callable[[], float] = time.perf_counter,
    exit_callback: Callable[[float], None] | None = None,
) -> Callable[P, R]: ...


# Overload 3: Decorator with arguments (@stopwatch(...))
@overload
def stopwatch(
    func: None = None,
    *,
    timer_func: Callable[[], float] = time.perf_counter,
    exit_callback: Callable[[float], None] | None = None,
) -> Callable[[Callable[P, R]], Callable[P, R]]: ...


# Implementation
def stopwatch(
    func: Callable[P, R] | None = None,
    *,
    timer_func: Callable[[], float] = time.perf_counter,
    exit_callback: Callable[[float], None] | None = None,
) -> Callable[P, R] | Callable[[Callable[P, R]], Callable[P, R]]:
    """Measure the execution time of a function using Stopwatch.

    Parameters
    ----------
    func : Callable[P, R] | None, optional
        The function to decorate. If None, returns a decorator function.
    timer_func : Callable[[], float], optional
        Function returning the current time (default: time.perf_counter). It
        should be fast and side-effect-light. It may be called while the
        stopwatch holds its internal lock, so it must not call methods or
        properties on the same Stopwatch instance.
    exit_callback : Callable[[float], None] | None, optional
        Optional callback invoked with the elapsed time when the
        decorated function exits. If None, a default callback is used that
        prints the elapsed time to standard output.

    Returns
    -------
    Callable[P, R] or Callable[[Callable[P, R]], Callable[P, R]]
        The decorated function, or a decorator function when func is None.

    Notes
    -----
    The Stopwatch is stopped when the decorated function exits normally. It
    is also stopped when the decorated function raises, and the original
    exception is re-raised after successful cleanup. If stopping fails with
    an Exception while preserving that exception, the stop failure is
    logged, the original exception is re-raised, and exit_callback is not
    invoked.

    When applied to an async function, timing includes the awaited function
    body until it returns or raises. When applied to a synchronous function
    that returns an awaitable object, timing ends when that object is returned.
    Generator and async generator timing starts on first consumption, not
    object creation, and stops when consumption completes, raises through the
    wrapper, or is explicitly closed with close() or aclose(). Time spent
    between yielded values is excluded; generator timing is the sum of time
    spent executing the generator body. For partially consumed async
    generators, event-loop or garbage-collection cleanup can close the
    underlying generator without reporting elapsed time; fully consume the
    generator or call aclose() when the elapsed time must be reported.

    Decorated generator and async generator callables return
    protocol-compatible wrapper objects that satisfy
    collections.abc.Generator or collections.abc.AsyncGenerator checks, but
    concrete-type introspection such as inspect.isgenerator() or
    inspect.isasyncgen() may not identify them as native generator objects.
    The decorated callable itself is also a regular wrapper function, so
    inspect.isgeneratorfunction() and inspect.isasyncgenfunction() may not
    identify it as a generator function.

    Examples
    --------
    >>> @stopwatch
    ... def f(x):
    ...     return x * 2

    """

    def _create_wrapper(f: Callable[P, R]) -> Callable[P, R]:
        callback = _resolve_exit_callback(f, exit_callback)
        if inspect.isasyncgenfunction(f) or inspect.isasyncgenfunction(
            type(f).__call__,
        ):
            return _wrap_async_generator(
                f,
                timer_func,
                callback,
            )
        if inspect.isgeneratorfunction(f) or inspect.isgeneratorfunction(
            type(f).__call__,
        ):
            return _wrap_generator(
                f,
                timer_func,
                callback,
            )
        if inspect.iscoroutinefunction(f) or inspect.iscoroutinefunction(
            type(f).__call__,
        ):
            return _wrap_async(f, timer_func, callback)
        return _wrap_sync(f, timer_func, callback)

    if func is None:
        return _create_wrapper
    return _create_wrapper(func)
