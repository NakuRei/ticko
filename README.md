# ticko

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
from ticko import StopWatch

# Basic usage
with StopWatch() as sw:
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

process_data()  # Automatically prints execution time
```

## Core Features

### Manual Control

```python
sw = StopWatch()
sw.start()
# ... your code ...
elapsed = sw.stop()
```

### Lap Timing

```python
sw = StopWatch()
sw.start()

# Record multiple laps
lap1 = sw.lap()
lap2 = sw.lap()

sw.stop()
```

### Custom Callbacks

```python
def log_time(sw: StopWatch):
    logger.info(f"Execution took {sw.time_elapsed:.3f}s")

@stopwatch(exit_callback=log_time)
def my_function():
    pass
```

For more examples, see the [`examples/`](examples/) directory.

## API Overview

### `StopWatch`

**Properties:**
- `is_running: bool` - Current state
- `time_elapsed: float` - Total elapsed time
- `time_last_lap: float` - Last lap duration

**Methods:**
- `start()` - Start timing
- `stop()` - Stop and return elapsed time
- `lap()` - Record lap time
- `reset()` - Reset to initial state

### `@stopwatch`

Decorator for automatic function timing with optional custom callbacks.

## Development

```bash
# Install with dev dependencies
uv sync --dev

# Run tests
pytest tests/

# Run tests with coverage report
pytest tests -v --cov=src --cov-report=term-missing --cov-report=xml:cov.xml

# Type checking
mypy .

# Lint checking
ruff check

# Format checking
ruff format --check --diff
```

## License

MIT License - Copyright (c) 2025 NakuRei

## Contributing

Contributions welcome! Feel free to open issues or submit pull requests.
