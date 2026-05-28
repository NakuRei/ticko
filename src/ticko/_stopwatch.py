"""Thread-safe stopwatch for measuring elapsed time."""

import contextlib
import logging
import threading
import time
from collections.abc import Callable
from types import TracebackType
from typing import Final, final

logger = logging.getLogger(__name__)


class StopwatchError(Exception):
    """Base class for Stopwatch exceptions."""


class AlreadyRunningError(StopwatchError):
    """Raised when trying to start an already running stopwatch."""


class NotRunningError(StopwatchError):
    """Raised when stop() or lap() is called while not running."""


class NotStartedError(StopwatchError):
    """Raised when accessing time_elapsed before start() has been called."""


class NoLapsRecordedError(StopwatchError):
    """Raised when accessing time_since_last_lap before any lap is recorded."""


@final
class Stopwatch:
    """Thread-safe stopwatch for measuring elapsed time.

    This class provides methods to start, stop, lap, and reset a stopwatch. It
    is designed to be thread-safe, allowing safe usage in multi-threaded
    environments.

    Parameters
    ----------
    name : str | None, optional
        Optional name for identifying this stopwatch in log messages and
        string representations (default: None).
    timer_func : Callable[[], float], optional
        Function returning the current time (default: time.perf_counter).
    exit_callback : Callable[[float], None] | None, optional
        Optional callback invoked with the elapsed time when the
        stopwatch is stopped. If None, no callback is invoked.

    Attributes
    ----------
    name : str | None
        The name of the stopwatch, or None if not named.
    is_running : bool
        Indicates whether the stopwatch is currently running.
    time_start : float | None
        The raw ``timer_func()`` value recorded at ``start()``, or None if not
        started. Its absolute value depends on the ``timer_func`` used (e.g.
        a Unix timestamp when using ``time.time``, an arbitrary epoch when
        using the default ``time.perf_counter``).
    time_stop : float | None
        The raw ``timer_func()`` value recorded at ``stop()``, or None if not
        stopped. Same caveat as ``time_start`` regarding absolute value.
    time_elapsed : float
        The total elapsed time since the stopwatch was started.
    time_since_last_lap : float
        Elapsed time from the last ``lap()`` marker to now (if running) or to
        the stop time (if stopped).

    Methods
    -------
    start() -> None
        Start the stopwatch.
    lap() -> float
        Record a lap time.
    stop() -> float
        Stop the stopwatch.
    reset() -> None
        Reset the stopwatch to its initial state.

    Examples
    --------
    >>> timer_values = iter([0.0, 1.0, 3.0])
    >>> sw = Stopwatch(timer_func=timer_values.__next__)
    >>> sw.start()
    >>> sw.lap()
    1.0
    >>> sw.stop()
    3.0
    >>> sw.time_elapsed
    3.0
    >>> sw.reset()
    >>> sw.time_elapsed  # doctest: +ELLIPSIS
    Traceback (most recent call last):
        ...
    ticko._stopwatch.NotStartedError: ...

    """

    def __init__(
        self,
        *,
        name: str | None = None,
        timer_func: Callable[[], float] = time.perf_counter,
        exit_callback: Callable[[float], None] | None = None,
    ) -> None:
        """Initialize the stopwatch.

        Parameters
        ----------
        name : str | None, optional
            Optional name for identifying this stopwatch in log messages and
            string representations (default: None).
        timer_func : Callable[[], float], optional
            Function returning the current time (default: time.perf_counter).
        exit_callback : Callable[[float], None] | None, optional
            Optional callback invoked with the elapsed time when the stopwatch
            is stopped.

        """
        self._name: Final = name
        self._timer_func: Final = timer_func
        self._exit_callback: Final = exit_callback
        self._log_name: Final = (
            f"Stopwatch[{name!r}]" if name is not None else "Stopwatch"
        )

        self._time_start: float | None = None
        self._time_last_lap_start: float | None = None
        self._time_stop: float | None = None
        self._is_running: bool = False
        self._lap_recorded: bool = False

        self._lock = threading.Lock()  # For thread safety

    @property
    def name(self) -> str | None:
        """Get the name of the stopwatch."""
        return self._name

    @property
    def is_running(self) -> bool:
        """Check if the stopwatch is currently running."""
        with self._lock:
            return self._is_running

    @property
    def time_start(self) -> float | None:
        """Get the raw timer_func() value recorded at start().

        Returns None if the stopwatch has not been started. The absolute value
        depends on the timer_func used; compare only against other timestamps
        from the same stopwatch instance.
        """
        with self._lock:
            return self._time_start

    @property
    def time_stop(self) -> float | None:
        """Get the raw timer_func() value recorded at stop().

        Returns None if the stopwatch has not been stopped. The absolute value
        depends on the timer_func used; compare only against other timestamps
        from the same stopwatch instance.
        """
        with self._lock:
            return self._time_stop

    @property
    def time_elapsed(self) -> float:
        """Get the total elapsed time."""
        with self._lock:
            if self._time_start is None:
                msg = (
                    "Stopwatch has not been started. "
                    "Call start() before getting elapsed time."
                )
                raise NotStartedError(msg)

            if self._is_running:
                return self._timer_func() - self._time_start
            if self._time_stop is not None:
                return self._time_stop - self._time_start
            msg = "Invariant: _time_stop must be set when stopped."
            raise AssertionError(msg)

    @property
    def time_since_last_lap(self) -> float:
        """Get the elapsed time from the last lap marker to now or to stop."""
        with self._lock:
            if not self._lap_recorded or self._time_last_lap_start is None:
                msg = (
                    "No laps have been recorded. "
                    "Call lap() after starting the stopwatch."
                )
                raise NoLapsRecordedError(msg)

            if self._is_running:
                return self._timer_func() - self._time_last_lap_start
            if self._time_stop is not None:
                return self._time_stop - self._time_last_lap_start
            msg = "Invariant: _time_stop must be set when stopped."
            raise AssertionError(msg)

    def reset(self) -> None:
        """Reset the stopwatch to its initial state.

        Clears all timing state regardless of whether the stopwatch is
        currently running. If called while running, the stopwatch is stopped
        without invoking ``exit_callback``; the in-progress measurement is
        discarded. To stop and trigger the callback before resetting, call
        ``stop()`` first.
        """
        with self._lock:
            self._time_start = None
            self._time_last_lap_start = None
            self._time_stop = None
            self._is_running = False
            self._lap_recorded = False
            logger.debug("%s has been reset.", self._log_name)

    def start(self) -> None:
        """Start the stopwatch."""
        with self._lock:
            if self._is_running:
                msg = (
                    "Stopwatch is already running. "
                    "Stop or reset it before starting again."
                )
                raise AlreadyRunningError(msg)
            time_current: Final = self._timer_func()
            self._time_start = time_current
            self._time_last_lap_start = time_current
            self._time_stop = None
            self._lap_recorded = False
            self._is_running = True
            logger.debug("%s started at %f.", self._log_name, time_current)

    def lap(self) -> float:
        """Record a lap time."""
        with self._lock:
            if not self._is_running:
                msg = (
                    "Stopwatch is not running. "
                    "Call start() first before recording a lap."
                )
                raise NotRunningError(msg)
            if self._time_last_lap_start is None:
                msg = "Invariant: _time_last_lap_start is None while running."
                raise AssertionError(msg)

            time_current: Final = self._timer_func()
            lap_duration: Final = time_current - self._time_last_lap_start
            self._time_last_lap_start = time_current
            self._lap_recorded = True
            logger.debug(
                "%s lap recorded at %f with duration %f.",
                self._log_name,
                time_current,
                lap_duration,
            )
            return lap_duration

    def stop(self) -> float:
        """Stop the stopwatch."""
        with self._lock:
            if not self._is_running:
                msg = (
                    "Stopwatch is not running. "
                    "Call start() first before stopping."
                )
                raise NotRunningError(msg)
            if self._time_start is None:
                msg = "Invariant: _time_start is None while running."
                raise AssertionError(msg)

            time_current: Final = self._timer_func()
            self._time_stop = time_current
            # Directly compute to avoid multiple calls of with self._lock
            time_elapsed: Final = self._time_stop - self._time_start
            self._is_running = False
            logger.debug(
                "%s stopped at %f with elapsed time %f.",
                self._log_name,
                time_current,
                time_elapsed,
            )

        # Call exit_callback outside the lock to avoid holding the lock
        # during potentially slow callback execution
        if self._exit_callback is not None:
            try:
                self._exit_callback(time_elapsed)
            except Exception:
                logger.exception("Exit callback raised an exception")

        return time_elapsed

    def __repr__(self) -> str:
        """Return a string representation for recreating the Stopwatch.

        Returns
        -------
        str
            A string showing the constructor parameters, following the
            Python convention that repr() should return a string that
            could be used to recreate the object, given an appropriate
            environment where the referenced callables are imported.
        """

        def _callable_name(func: Callable[..., object]) -> str:
            module = getattr(func, "__module__", None)
            qualname = getattr(func, "__qualname__", None)
            name = (
                qualname
                if isinstance(qualname, str)
                else getattr(func, "__name__", None)
            )
            if not isinstance(name, str):
                return repr(func)
            if isinstance(module, str):
                return f"{module}.{name}"
            return name

        timer_name = _callable_name(self._timer_func)
        callback_name = (
            None
            if self._exit_callback is None
            else _callable_name(self._exit_callback)
        )
        name_part = f"name={self._name!r}, " if self._name is not None else ""
        body = (
            f"{name_part}timer_func={timer_name}, exit_callback={callback_name}"
        )
        return f"Stopwatch({body})"

    def __str__(self) -> str:
        """Return a human-readable string representation.

        Returns
        -------
        str
            A string describing the current state of the stopwatch,
            including whether it's running and the elapsed time if
            applicable.
        """
        with self._lock:
            name_part = f"{self._name!r}, " if self._name is not None else ""
            if self._time_start is None:
                return f"Stopwatch({name_part}not started)"
            if self._is_running:
                elapsed = self._timer_func() - self._time_start
                return f"Stopwatch({name_part}running, elapsed={elapsed:.6f}s)"
            if self._time_stop is not None:
                elapsed = self._time_stop - self._time_start
                return f"Stopwatch({name_part}stopped, elapsed={elapsed:.6f}s)"
            msg = "Invariant: _time_stop must be set when stopped."
            raise AssertionError(msg)

    def __enter__(self) -> "Stopwatch":
        """Enter the context manager and start the stopwatch."""
        self.start()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Exit the context manager and stop the stopwatch.

        If the stopwatch was already stopped before the context exits,
        this method does nothing to avoid raising NotRunningError.
        """
        with contextlib.suppress(NotRunningError):
            self.stop()
