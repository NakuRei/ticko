"""Ticko: A simple and flexible stopwatch library for Python.

This package provides utilities for measuring execution time in Python programs.
It includes a thread-safe StopWatch class for manual timing control and a
decorator for automatically measuring function execution times.

Classes
-------
StopWatch
    Thread-safe stopwatch for measuring elapsed time with start, stop, lap,
    and reset functionality.

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

Using the StopWatch class directly:

>>> sw = StopWatch()
>>> sw.start()
>>> # ... do some work ...
>>> sw.lap()
1.234
>>> # ... do more work ...
>>> sw.stop()
2.567

Using StopWatch as a context manager:

>>> with StopWatch() as sw:
...     # ... do some work ...
...     pass
>>> sw.time_elapsed
1.234

"""

from .decorators import stopwatch
from .stop_watch import StopWatch

__all__ = [
    "StopWatch",
    "stopwatch",
]
