"""Decorator for measuring function execution time."""

import functools
import logging
import time
from collections.abc import Callable
from typing import ParamSpec, TypeVar, overload

from .stop_watch import StopWatch

logger = logging.getLogger(__name__)

P = ParamSpec("P")
R = TypeVar("R")


# Overload 1: Decorator without arguments (@stopwatch)
@overload
def stopwatch(
    func: Callable[P, R],
) -> Callable[P, R]: ...


# Overload 2: Decorator with arguments (@stopwatch(...))
@overload
def stopwatch(
    func: None = None,
    *,
    timer_func: Callable[[], float] = time.perf_counter,
    exit_callback: Callable[[StopWatch], None] | None = None,
) -> Callable[[Callable[P, R]], Callable[P, R]]: ...


# Implementation
def stopwatch(
    func: Callable[P, R] | None = None,
    *,
    timer_func: Callable[[], float] = time.perf_counter,
    exit_callback: Callable[[StopWatch], None] | None = None,
) -> Callable[P, R] | Callable[[Callable[P, R]], Callable[P, R]]:
    """Measure the execution time of a function using StopWatch.

    Parameters
    ----------
    func : Callable[P, R] | None, optional
        The function to decorate. If None, returns a decorator function.
    timer_func : Callable[[], float], optional
        Function returning the current time (default: time.perf_counter).
    exit_callback : Callable[[StopWatch], None] | None, optional
        Optional callback invoked with the StopWatch instance when the
        decorated function exits. If None, a default callback is used that
        prints the elapsed time to standard output.

    Returns
    -------
    Callable[P, R] or Callable[[Callable[P, R]], Callable[P, R]]
        The decorated function, or a decorator function when func is None.

    Notes
    -----
    The StopWatch is stopped regardless of whether the decorated function
    returns normally or raises an exception. If an exception occurs it is
    re-raised after the stopwatch has been stopped; exit_callback is still
    invoked.

    Examples
    --------
    >>> @stopwatch
    ... def f(x):
    ...     return x * 2

    """

    def _create_wrapper(f: Callable[P, R]) -> Callable[P, R]:
        """Create the wrapper function for the given function."""

        @functools.wraps(f)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            callback = exit_callback
            if callback is None:

                def _default_callback(sw: StopWatch) -> None:
                    print(  # noqa: T201
                        f"Function {f.__name__!r} executed "
                        f"in {sw.time_elapsed:.6f} seconds",
                    )

                callback = _default_callback

            sw = StopWatch(timer_func=timer_func, exit_callback=callback)
            sw.start()
            try:
                return f(*args, **kwargs)
            except Exception:
                logger.exception(
                    "Exception in stopwatch-decorated function",
                )
                raise
            finally:
                sw.stop()

        return wrapper

    if func is None:
        # Return a decorator function
        return _create_wrapper

    # Apply decorator directly
    return _create_wrapper(func)
