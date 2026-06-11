"""Thread-safe stopwatch for measuring elapsed time."""

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
    """Raised when stop(), lap(), or pause() is called while not running."""


class AlreadyPausedError(StopwatchError):
    """Raised when an operation is blocked because the stopwatch is paused.

    Covers start(), pause(), lap(), and stop() while paused.
    """


class NotPausedError(StopwatchError):
    """Raised when resume() is called while the stopwatch is not paused."""


class NotStartedError(StopwatchError):
    """Raised when accessing time_elapsed before start() has been called."""


class NoLapsRecordedError(StopwatchError):
    """Raised when accessing time_since_last_lap before any lap is recorded."""


@final
class Stopwatch:
    """Thread-safe stopwatch for measuring elapsed time.

    This class provides methods to start, pause, resume, stop, lap, and reset
    a stopwatch. It is designed to be thread-safe, allowing safe usage in
    multi-threaded environments.

    Parameters
    ----------
    name : str | None, optional
        Optional name for identifying this stopwatch in log messages and
        string representations (default: None).
    timer_func : Callable[[], float], optional
        Function returning the current time (default: time.perf_counter). It
        should be fast and side-effect-light. It may be called while the
        stopwatch holds its internal lock, so it must not call methods or
        properties on the same Stopwatch instance.
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
        The raw ``timer_func()`` value marking the effective measurement
        start, or None if not started. After a ``pause()`` / ``resume()`` it
        is shifted forward by the paused duration so that ``time_elapsed``
        excludes paused intervals. Its absolute value depends on the
        ``timer_func`` used (e.g. a Unix timestamp when using ``time.time``,
        an arbitrary epoch when using the default ``time.perf_counter``).
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
    pause() -> None
        Pause the stopwatch, excluding the paused interval from elapsed time.
    resume() -> None
        Resume a paused stopwatch.
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
    >>> sw.time_elapsed  # doctest: +IGNORE_EXCEPTION_DETAIL
    Traceback (most recent call last):
        ...
    NotStartedError: ...

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
            It should be fast and side-effect-light. It may be called while
            the stopwatch holds its internal lock, so it must not call methods
            or properties on the same Stopwatch instance.
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
        self._time_paused: float | None = None
        self._is_running: bool = False
        self._is_paused: bool = False
        self._lap_recorded: bool = False
        self._lap_durations: list[float] = []

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
        """Get the raw timer_func() value marking the effective start.

        Returns None if the stopwatch has not been started. After a
        pause()/resume(), this value is shifted forward by the paused duration
        so that time_elapsed excludes paused intervals. The absolute value
        depends on the timer_func used; compare only against other timestamps
        from the same stopwatch instance.
        """
        with self._lock:
            return self._time_start

    @property
    def time_stop(self) -> float | None:
        """Get the raw timer_func() value recorded at stop().

        Returns None if the stopwatch has not been stopped (including while
        paused, which is not a stopped state). The absolute value depends on the
        timer_func used; compare only against other timestamps from the same
        stopwatch instance.
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
            if self._is_paused and self._time_paused is not None:
                return self._time_paused - self._time_start
            if self._time_stop is not None:
                return self._time_stop - self._time_start
            msg = (  # pragma: no cover
                "Invariant: _time_stop must be set when stopped."
            )
            raise AssertionError(msg)

    @property
    def time_since_last_lap(self) -> float:
        """Get the elapsed time from the last lap marker to now or to stop."""
        with self._lock:
            if not self._lap_recorded or self._time_last_lap_start is None:
                msg = (
                    "lap() has not been called. "
                    "Call lap() after starting the stopwatch."
                )
                raise NoLapsRecordedError(msg)

            if self._is_running:
                return self._timer_func() - self._time_last_lap_start
            if self._is_paused and self._time_paused is not None:
                return self._time_paused - self._time_last_lap_start
            if self._time_stop is not None:
                return self._time_stop - self._time_last_lap_start
            msg = (  # pragma: no cover
                "Invariant: _time_stop must be set when stopped."
            )
            raise AssertionError(msg)

    @property
    def laps(self) -> tuple[float, ...]:
        """Get the recorded lap durations in the order they were recorded."""
        with self._lock:
            return tuple(self._lap_durations)

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
            self._time_paused = None
            self._is_running = False
            self._is_paused = False
            self._lap_recorded = False
            self._lap_durations.clear()
            logger.debug("%s has been reset.", self._log_name)

    def start(self) -> None:
        """Start the stopwatch."""
        with self._lock:
            if self._is_paused:
                msg = (
                    "Stopwatch is paused. "
                    "Call resume() or reset() before starting again."
                )
                raise AlreadyPausedError(msg)
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
            self._time_paused = None
            self._is_paused = False
            self._lap_recorded = False
            self._lap_durations.clear()
            self._is_running = True
            logger.debug("%s started at %f.", self._log_name, time_current)

    def pause(self) -> None:
        """Pause the stopwatch.

        Freezes the elapsed time at the current active measurement so that the
        interval until ``resume()`` is excluded from the reported time. After
        pause, ``is_running`` returns False. ``exit_callback`` is not invoked,
        since pause is not the end of a measurement.

        Raises
        ------
        AlreadyPausedError
            If the stopwatch is already paused.
        NotRunningError
            If the stopwatch is not running (not started or stopped).
        """
        with self._lock:
            if self._is_paused:
                msg = (
                    "Stopwatch is already paused. "
                    "Call resume() before pausing again."
                )
                raise AlreadyPausedError(msg)
            if not self._is_running:
                msg = (
                    "Stopwatch is not running. "
                    "Call start() first before pausing."
                )
                raise NotRunningError(msg)

            time_current: Final = self._timer_func()
            self._time_paused = time_current
            self._is_running = False
            self._is_paused = True
            logger.debug("%s paused at %f.", self._log_name, time_current)

    def resume(self) -> None:
        """Resume a paused stopwatch.

        Restarts measurement from the value frozen at ``pause()``; the paused
        interval is not counted. After resume, ``is_running`` returns True.

        Raises
        ------
        NotPausedError
            If the stopwatch is not currently paused.
        """
        with self._lock:
            if not self._is_paused:
                msg = "Stopwatch is not paused. Call pause() before resuming."
                raise NotPausedError(msg)
            if self._time_paused is None or self._time_start is None:
                msg = (  # pragma: no cover
                    "Invariant: _time_paused and _time_start must be set "
                    "while paused."
                )
                raise AssertionError(msg)

            time_current: Final = self._timer_func()
            pause_duration: Final = time_current - self._time_paused
            self._time_start += pause_duration
            if self._time_last_lap_start is not None:
                self._time_last_lap_start += pause_duration
            self._time_paused = None
            self._is_paused = False
            self._is_running = True
            logger.debug(
                "%s resumed at %f after %f paused.",
                self._log_name,
                time_current,
                pause_duration,
            )

    def lap(self) -> float:
        """Record a lap time."""
        with self._lock:
            if self._is_paused:
                msg = (
                    "Stopwatch is paused. Call resume() before recording a lap."
                )
                raise AlreadyPausedError(msg)
            if not self._is_running:
                msg = (
                    "Stopwatch is not running. "
                    "Call start() first before recording a lap."
                )
                raise NotRunningError(msg)
            if self._time_last_lap_start is None:
                msg = (  # pragma: no cover
                    "Invariant: _time_last_lap_start is None while running."
                )
                raise AssertionError(msg)

            time_current: Final = self._timer_func()
            lap_duration: Final = time_current - self._time_last_lap_start
            self._time_last_lap_start = time_current
            self._lap_recorded = True
            self._lap_durations.append(lap_duration)
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
            if self._is_paused:
                msg = "Stopwatch is paused. Call resume() before stopping."
                raise AlreadyPausedError(msg)
            if not self._is_running:
                msg = (
                    "Stopwatch is not running. "
                    "Call start() first before stopping."
                )
                raise NotRunningError(msg)
            if self._time_start is None:
                msg = (  # pragma: no cover
                    "Invariant: _time_start is None while running."
                )
                raise AssertionError(msg)

            if self._time_last_lap_start is None:
                msg = (  # pragma: no cover
                    "Invariant: _time_last_lap_start is None while running."
                )
                raise AssertionError(msg)

            time_current: Final = self._timer_func()
            self._time_stop = time_current
            # Directly compute to avoid multiple calls of with self._lock
            time_elapsed: Final = self._time_stop - self._time_start
            self._lap_durations.append(
                self._time_stop - self._time_last_lap_start
            )
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

    def _finalize_paused_for_cleanup(self) -> bool:
        """Finalize a paused stopwatch on context-manager cleanup.

        Converts a paused stopwatch to stopped using the pause-excluded
        elapsed time frozen at ``pause()`` and invokes ``exit_callback``.
        Used only by ``__exit__``; direct ``stop()`` on a paused stopwatch
        remains strict and raises ``AlreadyPausedError``.

        Returns
        -------
        bool
            True if the stopwatch was paused and has been finalized; False if
            it was not paused, in which case no state was changed.
        """
        with self._lock:
            if not self._is_paused:
                return False
            if (
                self._time_paused is None
                or self._time_start is None
                or self._time_last_lap_start is None
            ):
                msg = (  # pragma: no cover
                    "Invariant: _time_paused, _time_start and "
                    "_time_last_lap_start must be set while paused."
                )
                raise AssertionError(msg)

            time_elapsed: Final = self._time_paused - self._time_start
            self._lap_durations.append(
                self._time_paused - self._time_last_lap_start
            )
            self._time_stop = self._time_paused
            self._time_paused = None
            self._is_paused = False
            logger.debug(
                "%s finalized from paused with elapsed time %f.",
                self._log_name,
                time_elapsed,
            )

        if self._exit_callback is not None:
            try:
                self._exit_callback(time_elapsed)
            except Exception:
                logger.exception("Exit callback raised an exception")
        return True

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
            if self._is_paused and self._time_paused is not None:
                elapsed = self._time_paused - self._time_start
                return f"Stopwatch({name_part}paused, elapsed={elapsed:.6f}s)"
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
        A paused stopwatch is finalized on exit (stopped with the
        pause-excluded elapsed) and ``exit_callback`` fires.
        If the context exits with an exception, stop failures are logged
        without replacing the original exception.
        """
        # A paused watch only reaches cleanup through `__exit__`, so it is
        # finalized here (self-access), not in the shared cleanup helper
        # below, which decorators also use (their watch is never paused).
        if self._finalize_paused_for_cleanup():
            return
        stop_for_exception_cleanup(self, exc_type, exc_value, traceback)


def stop_for_exception_cleanup(
    stopwatch: Stopwatch,
    exc_type: type[BaseException] | None,
    exc_value: BaseException | None,
    traceback: TracebackType | None,
) -> None:
    """Stop from decorator or context manager cleanup."""
    del exc_value, traceback
    try:
        stopwatch.stop()
    except NotRunningError:
        pass
    except Exception:
        if exc_type is None:
            raise
        logger.exception("Stopwatch stop failed during exception cleanup")
