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

### Manual Control

```python
sw = Stopwatch()
sw.start()
# ... your code ...
elapsed = sw.stop()
```

### Lap Timing

```python
sw = Stopwatch()
sw.start()

# Record multiple laps
lap1 = sw.lap()
lap2 = sw.lap()

elapsed = sw.stop()
```

### Custom Callbacks

`@stopwatch` prints a human-readable timing message to stdout by default. This
is useful for scripts, examples, and interactive use where immediate feedback is
the goal. If stdout is used for structured data or piped output, pass
`exit_callback` to route timing information elsewhere.

```python
import sys


def report_time(elapsed: float) -> None:
    print(f"Execution took {elapsed:.3f}s", file=sys.stderr)


@stopwatch(exit_callback=report_time)
def my_function():
    pass
```

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
- `is_running: bool` - Current state
- `time_start: float | None` - Raw timer value recorded at start
- `time_stop: float | None` - Raw timer value recorded at stop
- `time_elapsed: float` - Total elapsed time
- `time_since_last_lap: float` - Elapsed time since the last lap marker

**Methods:**
- `start()` - Start timing
- `stop()` - Stop and return elapsed time
- `lap()` - Record lap time
- `reset()` - Reset to initial state

### `@stopwatch`

Decorator for quick, visible function timing.

By default, the decorator prints a human-readable timing message to stdout every
time the decorated function exits. Use `exit_callback` when timing information
should go to stderr, logging, metrics, or another destination.

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
