"""Thread-safe stopwatch for measuring elapsed time."""

import enum
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
    """Raised when stop(), lap(), or pause() is used with no open session.

    Covers a stopwatch that has not started, has stopped, or was reset.
    """


class PausedStateError(StopwatchError):
    """Raised when an operation is blocked because the stopwatch is paused.

    Covers start(), pause(), and lap() while paused.
    """


class NotPausedError(StopwatchError):
    """Raised when resume() is called while the stopwatch is not paused."""


class NotStartedError(StopwatchError):
    """Raised when reading time_elapsed while no measurement exists.

    Covers a stopwatch that has never been started and one that has been
    cleared by reset().
    """


class NoLapsRecordedError(StopwatchError):
    """Raised when accessing time_since_last_lap before any lap is recorded."""


class _State(enum.Enum):
    """Lifecycle state of a Stopwatch."""

    IDLE = enum.auto()
    RUNNING = enum.auto()
    PAUSED = enum.auto()
    STOPPED = enum.auto()


@final
class Stopwatch:
    """Thread-safe stopwatch for measuring elapsed time.

    This class provides methods to start, restart, pause, resume, stop, lap,
    and reset a stopwatch. It is designed to be thread-safe, allowing safe
    usage in multi-threaded environments.

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
    is_paused : bool
        Indicates whether the stopwatch is currently paused.
    time_elapsed : float
        The total elapsed time since the stopwatch was started.
    time_since_last_lap : float
        Elapsed time from the last ``lap()`` marker to now (if running), to
        the instant frozen at ``pause()`` (if paused), or to the stop time
        (if stopped).
    laps : tuple[float, ...]
        The recorded lap durations in recording order, including the final
        segment appended at stop.

    Methods
    -------
    start() -> None
        Start the stopwatch.
    restart() -> None
        Begin a fresh measurement from any state, discarding any
        in-progress measurement.
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
        self._state: _State = _State.IDLE
        self._lap_recorded: bool = False
        self._lap_durations: list[float] = []

        self._lock = threading.Lock()

    @property
    def name(self) -> str | None:
        """Get the name of the stopwatch."""
        return self._name

    @property
    def is_running(self) -> bool:
        """Check if the stopwatch is currently running."""
        with self._lock:
            return self._state is _State.RUNNING

    @property
    def is_paused(self) -> bool:
        """Check if the stopwatch is currently paused."""
        with self._lock:
            return self._state is _State.PAUSED

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

            return self._reference_time_locked() - self._time_start

    @property
    def time_since_last_lap(self) -> float:
        """Get the elapsed time from the last lap() marker.

        Measured to now (if running), to the instant frozen at pause()
        (if paused), or to the stop time (if stopped).
        """
        with self._lock:
            if not self._lap_recorded or self._time_last_lap_start is None:
                msg = (
                    "lap() has not been called. "
                    "Call lap() after starting the stopwatch."
                )
                raise NoLapsRecordedError(msg)

            return self._reference_time_locked() - self._time_last_lap_start

    @property
    def laps(self) -> tuple[float, ...]:
        """Get the recorded lap durations in the order they were recorded.

        Stopping (including context-manager exit) appends the final
        segment from the last lap marker, or from start when no lap was
        recorded, so the durations sum to ``time_elapsed``.
        """
        with self._lock:
            return tuple(self._lap_durations)

    def _reference_time_locked(self) -> float:
        """Return the instant that closes the current measurement window.

        The caller must hold the lock and must have ruled out the
        never-started state.
        """
        if self._state is _State.RUNNING:
            return self._timer_func()
        if self._state is _State.PAUSED:
            if self._time_paused is None:
                msg = (  # pragma: no cover
                    "Invariant: _time_paused must be set while paused."
                )
                raise AssertionError(msg)
            return self._time_paused
        if self._time_stop is None:
            msg = (  # pragma: no cover
                "Invariant: _time_stop must be set when stopped."
            )
            raise AssertionError(msg)
        return self._time_stop

    def reset(self) -> None:
        """Reset the stopwatch to its initial state.

        Clears all timing state regardless of whether the stopwatch is
        currently running. If called while running, the in-progress
        measurement is discarded without invoking ``exit_callback`` and the
        stopwatch returns to its never-started state. To stop and trigger
        the callback before resetting, call ``stop()`` first.
        """
        with self._lock:
            self._time_start = None
            self._time_last_lap_start = None
            self._time_stop = None
            self._time_paused = None
            self._state = _State.IDLE
            self._lap_recorded = False
            self._lap_durations.clear()
            logger.debug("%s has been reset.", self._log_name)

    def start(self) -> None:
        """Start the stopwatch."""
        with self._lock:
            if self._state is _State.PAUSED:
                msg = (
                    "Stopwatch is paused. "
                    "Call resume() or reset() before starting again."
                )
                raise PausedStateError(msg)
            if self._state is _State.RUNNING:
                msg = (
                    "Stopwatch is already running. "
                    "Stop or reset it before starting again."
                )
                raise AlreadyRunningError(msg)
            self._begin_measurement_locked()

    def restart(self) -> None:
        """Restart the stopwatch, beginning a fresh measurement.

        Works from any state and never raises a state error. The implied
        reset and start happen in one atomic step, so concurrent threads
        cannot interleave a competing ``start()`` in between. Any
        in-progress measurement is discarded without invoking
        ``exit_callback``, like ``reset()``.
        """
        with self._lock:
            self._begin_measurement_locked()

    def _begin_measurement_locked(self) -> None:
        """Begin a fresh measurement. The caller must hold the lock."""
        time_current: Final = self._timer_func()
        self._time_start = time_current
        self._time_last_lap_start = time_current
        self._time_stop = None
        self._time_paused = None
        self._lap_recorded = False
        self._lap_durations.clear()
        self._state = _State.RUNNING
        logger.debug("%s started at %f.", self._log_name, time_current)

    def pause(self) -> None:
        """Pause the stopwatch.

        Freezes the elapsed time at the current active measurement so that the
        interval until ``resume()`` is excluded from the reported time. After
        pause, ``is_running`` returns False. ``exit_callback`` is not invoked,
        since pause is not the end of a measurement.

        Raises
        ------
        PausedStateError
            If the stopwatch is already paused.
        NotRunningError
            If the stopwatch is not running (not started or stopped).
        """
        with self._lock:
            if self._state is _State.PAUSED:
                msg = (
                    "Stopwatch is already paused. "
                    "Call resume() before pausing again."
                )
                raise PausedStateError(msg)
            if self._state is not _State.RUNNING:
                msg = (
                    "Stopwatch is not running. "
                    "Call start() first before pausing."
                )
                raise NotRunningError(msg)

            time_current: Final = self._timer_func()
            self._time_paused = time_current
            self._state = _State.PAUSED
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
            if self._state is not _State.PAUSED:
                msg = "Stopwatch is not paused. Call pause() before resuming."
                raise NotPausedError(msg)
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

            time_current: Final = self._timer_func()
            pause_duration: Final = time_current - self._time_paused
            self._time_start += pause_duration
            self._time_last_lap_start += pause_duration
            self._time_paused = None
            self._state = _State.RUNNING
            logger.debug(
                "%s resumed at %f after %f paused.",
                self._log_name,
                time_current,
                pause_duration,
            )

    def lap(self) -> float:
        """Record a lap time."""
        with self._lock:
            if self._state is _State.PAUSED:
                msg = (
                    "Stopwatch is paused. Call resume() before recording a lap."
                )
                raise PausedStateError(msg)
            if self._state is not _State.RUNNING:
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
            if self._state is _State.PAUSED:
                time_elapsed = self._finalize_paused_locked()
            elif self._state is _State.RUNNING:
                time_elapsed = self._stop_running_locked()
            else:
                msg = (
                    "Stopwatch is not running. "
                    "Call start() first before stopping."
                )
                raise NotRunningError(msg)

        self._invoke_exit_callback(time_elapsed)
        return time_elapsed

    def _stop_running_locked(self) -> float:
        """Finalize a running measurement. The caller must hold the lock."""
        if self._time_start is None or self._time_last_lap_start is None:
            msg = (  # pragma: no cover
                "Invariant: _time_start and _time_last_lap_start must be "
                "set while running."
            )
            raise AssertionError(msg)

        time_current: Final = self._timer_func()
        self._time_stop = time_current
        time_elapsed: Final = time_current - self._time_start
        self._lap_durations.append(time_current - self._time_last_lap_start)
        self._state = _State.STOPPED
        logger.debug(
            "%s stopped at %f with elapsed time %f.",
            self._log_name,
            time_current,
            time_elapsed,
        )
        return time_elapsed

    def _finalize_paused_locked(self) -> float:
        """Finalize a paused measurement. The caller must hold the lock.

        The pause-excluded elapsed time frozen at ``pause()`` becomes the
        final measurement; no timer read is needed.
        """
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
        self._state = _State.STOPPED
        logger.debug(
            "%s finalized from paused with elapsed time %f.",
            self._log_name,
            time_elapsed,
        )
        return time_elapsed

    def _invoke_exit_callback(self, time_elapsed: float) -> None:
        """Report the elapsed time to ``exit_callback``, logging failures.

        Must be called without holding the lock so a slow or reentrant
        callback cannot block other threads.
        """
        if self._exit_callback is None:
            return
        try:
            self._exit_callback(time_elapsed)
        except Exception:
            logger.exception("Exit callback raised an exception")

    def _stop_for_cleanup(self) -> float | None:
        """Stop for context-manager cleanup, tolerating any state.

        A paused stopwatch is finalized with the pause-excluded elapsed
        time; a running one is stopped normally. Returns None without
        changing state when there is nothing to stop (never started or
        already stopped), so ``__exit__`` does not raise where ``stop()``
        would. The single lock acquisition makes the state check and the
        stop atomic against concurrent transitions.
        """
        with self._lock:
            if self._state is _State.PAUSED:
                time_elapsed = self._finalize_paused_locked()
            elif self._state is _State.RUNNING:
                time_elapsed = self._stop_running_locked()
            else:
                return None

        self._invoke_exit_callback(time_elapsed)
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
        state_labels: Final = {
            _State.RUNNING: "running",
            _State.PAUSED: "paused",
            _State.STOPPED: "stopped",
        }
        with self._lock:
            name_part = f"{self._name!r}, " if self._name is not None else ""
            if self._time_start is None:
                return f"Stopwatch({name_part}not started)"
            elapsed = self._reference_time_locked() - self._time_start
            state_label = state_labels[self._state]
            return (
                f"Stopwatch({name_part}{state_label}, elapsed={elapsed:.6f}s)"
            )

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
        If the context exits with an exception, Exception-typed stop
        failures are logged without replacing the original exception.
        """
        del exc_value, traceback
        try:
            self._stop_for_cleanup()
        except Exception:
            if exc_type is None:
                raise
            logger.exception("Stopwatch stop failed during exception cleanup")
