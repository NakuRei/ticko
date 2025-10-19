"""Thread-safe stopwatch for measuring elapsed time."""

import logging
import threading
import time
from collections.abc import Callable
from types import TracebackType
from typing import Final, final

logger = logging.getLogger(__name__)


class StopWatchError(Exception):
    """Base class for StopWatch exceptions."""


class InvalidStateError(StopWatchError):
    """Raised when an operation is attempted in an invalid state."""


class AlreadyRunningError(StopWatchError):
    """Raised when trying to start an already running stopwatch."""


class NotStartedError(StopWatchError):
    """Raised when stopping or lapping a stopwatch that hasn't been started."""


@final
class StopWatch:
    """Thread-safe stopwatch for measuring elapsed time.

    This class provides methods to start, stop, lap, and reset a stopwatch. It
    is designed to be thread-safe, allowing safe usage in multi-threaded
    environments.

    Parameters
    ----------
    timer_func : Callable[[], float], optional
        Function returning the current time (default: time.perf_counter).
    exit_callback : Callable[[StopWatch], None] | None, optional
        Optional callback invoked with the StopWatch instance when the
        stopwatch is stopped. If None, no callback is invoked.

    Attributes
    ----------
    is_running : bool
        Indicates whether the stopwatch is currently running.
    time_start : float | None
        The start time of the stopwatch, or None if not started.
    time_stop : float | None
        The stop time of the stopwatch, or None if not stopped.
    time_last_lap_start : float | None
        The start time of the last lap, or None if no laps recorded.
    time_elapsed : float
        The total elapsed time since the stopwatch was started.
    time_last_lap : float
        The elapsed time of the last lap.

    Methods
    -------
    start() -> float
        Start the stopwatch.
    lap() -> float
        Record a lap time.
    stop() -> float
        Stop the stopwatch.
    reset() -> None
        Reset the stopwatch to its initial state.

    Examples
    --------
    >>> sw = StopWatch()
    >>> sw.start()
    >>> time.sleep(1)
    >>> sw.lap()
    1.0
    >>> time.sleep(2)
    >>> sw.stop()
    3.0
    >>> sw.time_elapsed
    3.0
    >>> sw.reset()
    >>> sw.time_elapsed
    Traceback (most recent call last):
        ...
    NotStartedError: ...

    """

    def __init__(
        self,
        timer_func: Callable[[], float] = time.perf_counter,
        exit_callback: Callable[["StopWatch"], None] | None = None,
    ) -> None:
        """Initialize the stopwatch.

        Parameters
        ----------
        timer_func : Callable[[], float], optional
            Function returning the current time (default: time.perf_counter).
        exit_callback : Callable[[StopWatch], None] | None, optional
            Optional callback invoked when the stopwatch is stopped.

        """
        self._timer_func: Final = timer_func
        self._exit_callback: Final = exit_callback

        self._time_start: float | None = None
        self._time_last_lap_start: float | None = None
        self._time_stop: float | None = None
        self._is_running: bool = False

        self._lock = threading.Lock()  # For thread safety

    @property
    def is_running(self) -> bool:
        """Check if the stopwatch is currently running."""
        with self._lock:
            return self._is_running

    @property
    def time_start(self) -> float | None:
        """Get the start time of the stopwatch."""
        with self._lock:
            return self._time_start

    @property
    def time_stop(self) -> float | None:
        """Get the stop time of the stopwatch."""
        with self._lock:
            return self._time_stop

    @property
    def time_last_lap_start(self) -> float | None:
        """Get the start time of the last lap."""
        with self._lock:
            return self._time_last_lap_start

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
            # This is unreachable
            msg = (
                "Stopwatch is in an invalid state. "
                "Call reset() to reinitialize."
            )
            raise InvalidStateError(msg)

    @property
    def time_last_lap(self) -> float:
        """Get the elapsed time of the last lap."""
        with self._lock:
            if self._time_last_lap_start is None:
                msg = (
                    "No laps have been recorded. "
                    "Call lap() after starting the stopwatch."
                )
                raise NotStartedError(msg)

            if self._is_running:
                return self._timer_func() - self._time_last_lap_start
            if self._time_stop is not None:
                return self._time_stop - self._time_last_lap_start
            # This is unreachable
            msg = (
                "Stopwatch is in an invalid state. "
                "Call reset() to reinitialize."
            )
            raise InvalidStateError(msg)

    def reset(self) -> None:
        """Reset the stopwatch to its initial state."""
        with self._lock:
            self._time_start = None
            self._time_last_lap_start = None
            self._time_stop = None
            self._is_running = False
            logger.debug("Stopwatch has been reset.")

    def start(self) -> float:
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
            self._is_running = True
            logger.debug("Stopwatch started at %f.", time_current)
            return time_current

    def lap(self) -> float:
        """Record a lap time."""
        with self._lock:
            if not self._is_running:
                msg = (
                    "Stopwatch is not running. "
                    "Call start() first before recording a lap."
                )
                raise NotStartedError(msg)
            if self._time_last_lap_start is None:
                # Invariant check: should not happen if running
                msg = "Last lap start time should not be None if running."
                raise InvalidStateError(msg)

            time_current: Final = self._timer_func()
            lap_duration: Final = time_current - self._time_last_lap_start
            self._time_last_lap_start = time_current
            logger.debug(
                "Lap recorded at %f with duration %f.",
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
                raise NotStartedError(msg)
            if self._time_start is None:
                # Invariant check: should not happen if running
                msg = "Start time should not be None if running."
                raise InvalidStateError(msg)

            time_current: Final = self._timer_func()
            self._time_stop = time_current
            # Directly compute to avoid multiple calls of with self._lock
            time_elapsed: Final = self._time_stop - self._time_start
            self._is_running = False
            logger.debug(
                "Stopwatch stopped at %f with elapsed time %f.",
                time_current,
                time_elapsed,
            )

        # Call exit_callback outside the lock to avoid deadlock
        # if callback tries to access stopwatch properties
        if self._exit_callback is not None:
            try:
                self._exit_callback(self)
            except Exception:
                logger.exception("Exit callback raised an exception")

        return time_elapsed

    def __repr__(self) -> str:
        """Return a string representation for recreating the StopWatch.

        Returns a string showing the constructor parameters, following the
        Python convention that repr() should return a string that could be
        used to recreate the object.
        """
        timer_name = getattr(
            self._timer_func,
            "__name__",
            repr(self._timer_func),
        )
        callback_name = (
            None
            if self._exit_callback is None
            else getattr(
                self._exit_callback,
                "__name__",
                repr(self._exit_callback),
            )
        )
        return (
            f"StopWatch(timer_func={timer_name}, exit_callback={callback_name})"
        )

    def __str__(self) -> str:
        """Return a human-readable string representation.

        Returns a string describing the current state of the stopwatch,
        including whether it's running and the elapsed time if applicable.
        """
        with self._lock:
            if self._time_start is None:
                return "StopWatch(not started)"
            if self._is_running:
                elapsed = self._timer_func() - self._time_start
                return f"StopWatch(running, elapsed={elapsed:.6f}s)"
            if self._time_stop is not None:
                elapsed = self._time_stop - self._time_start
                return f"StopWatch(stopped, elapsed={elapsed:.6f}s)"
            return "StopWatch(invalid state)"  # This is unreachable

    def __enter__(self) -> "StopWatch":
        """Enter the context manager and start the stopwatch."""
        self.start()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Exit the context manager and stop the stopwatch."""
        self.stop()
