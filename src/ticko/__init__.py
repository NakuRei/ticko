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
    Raised when accessing time_last_lap before any lap has been recorded.
InvalidStateError
    Raised when an operation is attempted in an invalid state.

Functions
---------
stopwatch
    Decorator that measures and reports the execution time of a function.

Examples
--------
Using the decorator:

>>> @stopwatch
... def compute(n):
...     return sum(range(n))
>>> compute(1000)
Function 'compute' executed in 0.000123 seconds
499500

Using the Stopwatch class directly:

>>> sw = Stopwatch()
>>> sw.start()
>>> # ... do some work ...
>>> sw.lap()
1.234
>>> # ... do more work ...
>>> sw.stop()
2.567

Using Stopwatch as a context manager:

>>> with Stopwatch() as sw:
...     # ... do some work ...
...     pass
>>> sw.time_elapsed
1.234

"""

from .decorators import stopwatch
from .stopwatch import (
    AlreadyRunningError,
    InvalidStateError,
    NoLapsRecordedError,
    NotRunningError,
    NotStartedError,
    Stopwatch,
    StopwatchError,
)

__all__ = [
    "AlreadyRunningError",
    "InvalidStateError",
    "NoLapsRecordedError",
    "NotRunningError",
    "NotStartedError",
    "Stopwatch",
    "StopwatchError",
    "stopwatch",
]
