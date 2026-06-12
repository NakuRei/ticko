"""Decorator for measuring function execution time."""

import functools
import inspect
import logging
import time
from collections.abc import Awaitable, Callable
from typing import ParamSpec, TypeVar, cast, overload

from ._stopwatch import Stopwatch

logger = logging.getLogger(__name__)

P = ParamSpec("P")
R = TypeVar("R")


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
    Generator and async generator consumption time is not measured.

    Examples
    --------
    >>> @stopwatch
    ... def f(x):
    ...     return x * 2

    """

    def _create_wrapper(f: Callable[P, R]) -> Callable[P, R]:
        callback = _resolve_exit_callback(f, exit_callback)
        if inspect.iscoroutinefunction(f) or inspect.iscoroutinefunction(
            type(f).__call__,
        ):
            return _wrap_async(f, timer_func, callback)
        return _wrap_sync(f, timer_func, callback)

    if func is None:
        return _create_wrapper
    return _create_wrapper(func)
