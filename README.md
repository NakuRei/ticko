# ticko

[![CI](https://github.com/NakuRei/ticko/actions/workflows/ci.yml/badge.svg)](https://github.com/NakuRei/ticko/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/NakuRei/ticko/branch/main/graph/badge.svg)](https://codecov.io/gh/NakuRei/ticko)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A modern, thread-safe stopwatch library for Python.

## Why ticko?

- **Thread-safe by design** - Use confidently in concurrent applications
- **Type-safe** - Full type hints for excellent IDE support
- **Zero dependencies** - Pure Python, no external requirements
- **Flexible API** - Context managers, decorators, or manual control
- **Production-ready** - Comprehensive test coverage

## Installation

```bash
pip install ticko
```

## Quick Start

```python
from ticko import Stopwatch

# Basic usage
with Stopwatch() as sw:
    # Your code here
    pass

print(f"Elapsed: {sw.time_elapsed:.2f}s")
```

```python
from ticko import stopwatch

# Decorator for function timing
@stopwatch
def process_data():
    # Your code here
    pass

process_data()  # Prints execution time to stdout by default
```

## Core Features

### Context Managers

```python
with Stopwatch() as sw:
    # ... your code ...
    pass

print(f"Elapsed: {sw.time_elapsed:.3f}s")
```

The context manager starts timing on entry and stops on exit. If the block
raises an exception, the original exception is preserved.

### Manual Control

```python
sw = Stopwatch()
sw.start()
# ... your code ...
elapsed = sw.stop()
```

### Pause and Resume

```python
sw = Stopwatch()
sw.start()

# ... active work ...
sw.pause()
# ... waiting or setup that should not count ...
sw.resume()
# ... more active work ...

elapsed = sw.stop()
```

Paused intervals are excluded from `time_elapsed`. Use `is_paused` to check
for the paused state. Calling `stop()` directly while paused raises
`PausedStateError`; call `resume()` before `stop()`, or use a context manager
to finalize a paused stopwatch when the context exits.

### Lap Timing

```python
sw = Stopwatch()
sw.start()

# Record multiple laps
lap1 = sw.lap()
lap2 = sw.lap()

elapsed = sw.stop()
```

The full history of recorded lap durations is available through the `laps`
property, which returns an immutable tuple in recording order. Each `lap()`
appends the duration since the previous lap (or since `start()` for the first
one), and `stop()` appends the final segment from the last lap (or from
`start()` if none) to the stop time. The durations therefore sum to
`time_elapsed`. The tuple is empty until the first `lap()` or `stop()` records a
duration, so a `start()` -> `stop()` with no `lap()` in between yields a single
duration equal to `time_elapsed`. `start()` and `reset()` clear the history.

```python
sw = Stopwatch()
sw.start()
sw.lap()
sw.lap()
sw.stop()

print(sw.laps)  # Recorded lap durations, including the final stop segment
```

### Decorator Timing

```python
@stopwatch
def load_data() -> list[str]:
    return ["alpha", "beta", "gamma"]


load_data()
```

The decorator prints elapsed time to stdout by default. Pass `exit_callback` to
send elapsed seconds to logging, metrics, stderr, or another destination.

### Custom Callbacks

`Stopwatch` and `@stopwatch` accept an `exit_callback` with the signature
`Callable[[float], None]`. The callback receives elapsed seconds when timing
finishes.

`@stopwatch` prints a human-readable timing message to stdout by default. This
is useful for scripts, examples, and interactive use where immediate feedback is
the goal. If stdout is used for structured data or piped output, pass
`exit_callback` to route timing information elsewhere.

```python
import sys


def report_time(elapsed: float) -> None:
    print(f"Execution took {elapsed:.3f}s", file=sys.stderr)


sw = Stopwatch(exit_callback=report_time)
sw.start()
# ... your code ...
sw.stop()
```

The same callback form works with the decorator:

```python
@stopwatch(exit_callback=report_time)
def my_function():
    pass
```

Or route timing to the logging system:

```python
import logging


logger = logging.getLogger(__name__)


def log_time(elapsed: float) -> None:
    logger.info("Execution took %.3fs", elapsed)


@stopwatch(exit_callback=log_time)
def my_function():
    pass
```

### Thread Safety

```python
from concurrent.futures import ThreadPoolExecutor

sw = Stopwatch()
sw.start()

# Multiple threads can safely share one Stopwatch
with ThreadPoolExecutor(max_workers=5) as executor:
    futures = [executor.submit(sw.lap) for _ in range(10)]

elapsed = sw.stop()
```

For more examples, see the [`examples/`](examples/) directory.

## API Overview

### `Stopwatch`

**Constructor:**
- `Stopwatch(*, name=None, timer_func=time.perf_counter, exit_callback=None)` - Create a stopwatch with optional naming, custom timing, and stop callback

When passing a custom `timer_func`, keep it fast and side-effect-light. The
stopwatch may call it while holding its internal lock, so the timer function
must not call methods or properties on the same `Stopwatch` instance.

**Properties:**
- `name: str | None` - Optional stopwatch name
- `is_running: bool` - Whether the stopwatch is currently running
- `is_paused: bool` - Whether the stopwatch is currently paused
- `time_elapsed: float` - Total elapsed time
- `time_since_last_lap: float` - Elapsed time since the last lap marker
- `laps: tuple[float, ...]` - Recorded lap durations in recording order (empty until the first `lap()` or `stop()`)

**Methods:**
- `start()` - Start timing and return `None`
- `restart()` - Discard any in-progress measurement and start a new one in a single atomic step
- `pause()` - Pause timing and exclude the paused interval from elapsed time
- `resume()` - Resume a paused stopwatch
- `stop()` - Stop, call `exit_callback` when configured, and return elapsed time
- `lap()` - Record and return lap duration
- `reset()` - Reset to initial state without calling `exit_callback`

**Exceptions:**
- `StopwatchError` - Base class for stopwatch exceptions
- `AlreadyRunningError` - Raised when starting an already running stopwatch
- `NotRunningError` - Raised when stopping, lapping, or pausing a stopwatch that is not running
- `PausedStateError` - Raised when an operation is blocked because the stopwatch is paused
- `NotPausedError` - Raised when resuming a stopwatch that is not paused
- `NotStartedError` - Raised when reading elapsed time before the first start or after a reset
- `NoLapsRecordedError` - Raised when reading lap elapsed time before any lap

### `@stopwatch`

Decorator for quick, visible function timing.

By default, the decorator prints a human-readable timing message to stdout every
time the decorated function exits. The output includes the callable name and
elapsed seconds. Use `exit_callback` when timing information should go to
stderr, logging, metrics, or another destination.

Works on regular functions, callable objects, `async def` functions, and
callable objects whose `__call__` is async. For async callables, timing covers
the awaited body until it returns or raises.

When a synchronous function returns an awaitable object, timing ends when that
object is returned. Awaiting or consuming that object is not measured.

## Migrating from 1.x

- Rename `StopWatch` to `Stopwatch`
- Rename `StopWatchError` to `StopwatchError`
- Import from `ticko`; `ticko.stop_watch` is no longer supported
- Update `exit_callback` functions to accept elapsed seconds as `float`, not a stopwatch instance
- Do not rely on `start()` returning the start time; it now returns `None`
- Rename `time_last_lap` to `time_since_last_lap`
- Remove uses of `time_last_lap_start` and `InvalidStateError`
- Pass `timer_func` and `exit_callback` to `Stopwatch` as keyword arguments; positional arguments are no longer accepted
- Update `except NotStartedError` handlers: `stop()` and `lap()` on a non-running stopwatch now raise `NotRunningError`, and `time_since_last_lap` before any lap raises `NoLapsRecordedError`
- Remove uses of the `time_start` and `time_stop` properties; use `time_elapsed` for measurements, or record your own timestamps next to `start()`/`stop()` if you need absolute times

## Development

```bash
# Install with dev dependencies
uv sync --dev

# Install pre-commit hooks
uv run pre-commit install

# Run tests
uv run pytest tests/

# Run tests with coverage report
uv run pytest tests -v --cov=src --cov-report=term-missing --cov-report=xml:cov.xml

# Type checking
uv run mypy .

# Lint checking
uv run ruff check

# Format checking
uv run ruff format --check --diff
```

## License

MIT License - Copyright (c) 2025 NakuRei

## Contributing

Contributions welcome! Feel free to open issues or submit pull requests.
