"""Decorator for measuring function execution time."""

import functools
import inspect
import time
from collections.abc import Awaitable, Callable
from typing import ParamSpec, TypeVar, cast, overload

from ._stopwatch import Stopwatch

P = ParamSpec("P")
R = TypeVar("R")


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
        Function returning the current time (default: time.perf_counter).
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
    The Stopwatch is stopped regardless of whether the decorated function
    returns normally or raises an exception. If an exception occurs it is
    re-raised after the stopwatch has been stopped; exit_callback is still
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
        """Create the wrapper function for the given function."""
        if exit_callback is None:

            def _default_callback(elapsed: float) -> None:
                print(  # noqa: T201
                    f"Function {f.__name__!r} exited "
                    f"after {elapsed:.6f} seconds",
                )

            callback: Callable[[float], None] = _default_callback
        else:
            callback = exit_callback

        if inspect.iscoroutinefunction(f):
            async_func = cast("Callable[P, Awaitable[object]]", f)

            @functools.wraps(f)
            async def async_wrapper(
                *args: P.args,
                **kwargs: P.kwargs,
            ) -> object:
                sw = Stopwatch(timer_func=timer_func, exit_callback=callback)
                sw.start()
                try:
                    return await async_func(*args, **kwargs)
                finally:
                    sw.stop()

            return cast("Callable[P, R]", async_wrapper)

        @functools.wraps(f)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            sw = Stopwatch(timer_func=timer_func, exit_callback=callback)
            sw.start()
            try:
                return f(*args, **kwargs)
            finally:
                sw.stop()

        return wrapper

    if func is None:
        # Return a decorator function
        return _create_wrapper

    # Apply decorator directly
    return _create_wrapper(func)
