"""Ticko: A simple and flexible stopwatch library for Python.

This package provides utilities for measuring execution time in Python programs.
It includes a thread-safe Stopwatch class for manual timing control and a
decorator for automatically measuring function execution times.

Classes
-------
Stopwatch
    Thread-safe stopwatch for measuring elapsed time with start, stop, lap,
    and reset functionality.
StopwatchError
    Base class for all Stopwatch exceptions.
AlreadyRunningError
    Raised when trying to start an already running stopwatch.
NotRunningError
    Raised when stop() or lap() is called while the stopwatch is not running.
NotStartedError
    Raised when accessing time_elapsed before start() has ever been called.
NoLapsRecordedError
    Raised when accessing time_since_last_lap before any lap has been recorded.

Functions
---------
stopwatch
    Decorator that measures and reports the execution time of a function.

Examples
--------
Using the decorator:

>>> timer_values = iter([0.0, 0.25])
>>> @stopwatch(timer_func=timer_values.__next__)
... def compute(n):
...     return sum(range(n))
>>> compute(1000)
Function 'compute' exited after 0.250000 seconds
499500

Using the Stopwatch class directly:

>>> timer_values = iter([0.0, 1.0, 3.0])
>>> sw = Stopwatch(timer_func=timer_values.__next__)
>>> sw.start()
>>> sw.lap()
1.0
>>> sw.stop()
3.0

Using Stopwatch as a context manager:

>>> timer_values = iter([0.0, 1.234])
>>> with Stopwatch(timer_func=timer_values.__next__) as sw:
...     pass
>>> sw.time_elapsed
1.234

"""

from ._stopwatch import (
    AlreadyRunningError,
    NoLapsRecordedError,
    NotRunningError,
    NotStartedError,
    Stopwatch,
    StopwatchError,
)
from .decorators import stopwatch

__all__ = [
    "AlreadyRunningError",
    "NoLapsRecordedError",
    "NotRunningError",
    "NotStartedError",
    "Stopwatch",
    "StopwatchError",
    "stopwatch",
]
