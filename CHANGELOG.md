# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [2.0.0] - 2026-06-13

### Added

- `Stopwatch.pause()` and `Stopwatch.resume()` to suspend and continue timing without losing elapsed time
- `Stopwatch.is_paused` property to distinguish a paused stopwatch from a stopped one
- `Stopwatch.restart()` to discard any in-progress measurement and start a new one in a single atomic step, so concurrent threads cannot interleave between the implied reset and start
- `name` keyword argument to `Stopwatch` and a read-only `name` property; the name appears in log messages and string representations to identify a stopwatch
- `Stopwatch.laps` property returning the full history of recorded lap durations as an immutable tuple in recording order; `stop()` now appends the final segment so the durations sum to `time_elapsed`
- Dedicated exception classes `NotRunningError`, `PausedStateError`, `NotPausedError`, and `NoLapsRecordedError`, splitting lifecycle, paused-state, and missing-lap failures into specific `StopwatchError` subclasses
- `@stopwatch` now measures generator and async generator body execution during consumption, excluding time spent between yielded values
- Official support for Python 3.14

### Changed

- Renamed `StopWatch` to `Stopwatch` and `StopWatchError` to `StopwatchError` to reflect that "stopwatch" is a single English word
- Renamed the `time_last_lap` property to `time_since_last_lap`
- `exit_callback` now receives the elapsed time as a `float` instead of the stopwatch instance; its type changed from `Callable[[Stopwatch], None]` to `Callable[[float], None]`, affecting both `Stopwatch` and the `@stopwatch` decorator
- `Stopwatch.start()` now returns `None` instead of the start time
- `Stopwatch` constructor arguments are now keyword-only; pass `timer_func` and `exit_callback` by name
- `stop()` and `lap()` before start, after stop, or after reset now raise `NotRunningError` instead of `NotStartedError`, and `time_since_last_lap` before any lap raises `NoLapsRecordedError` instead of `NotStartedError`
- `Stopwatch.stop()` now finalizes a paused stopwatch using the elapsed time frozen at `pause()`, matching context-manager exit behavior
- The default `@stopwatch` message changed from `Function '<name>' executed in <n> seconds` to `Function '<name>' exited after <n> seconds`

### Removed

- The old `ticko.stop_watch` module; `ticko._stopwatch` is a private implementation module. Import `Stopwatch` from the `ticko` package root instead
- `InvalidStateError`; use the specific `StopwatchError` subclasses instead
- The `time_last_lap_start` property
- The `time_start` and `time_stop` properties; after a `pause()`/`resume()` the internally shifted start time is no longer the real start instant, so the raw timestamps were misleading. Use `time_elapsed`, or record your own timestamps if you need absolute times

### Fixed

- `@stopwatch` now measures the full execution time of async functions, awaiting the coroutine instead of timing only its creation
- `@stopwatch` now measures async callable objects through their awaited body
- The default `@stopwatch` output now handles callable objects without a `__name__` attribute
- The package no longer emits log records by default; a `NullHandler` is attached so logging stays silent unless the application configures it
- When `stop()` fails while a decorated function is unwinding from an exception, the original exception is preserved and re-raised instead of being masked by the stop failure
- When a decorated function is called inside an `except` block of its caller and returns normally, a `stop()` failure now propagates instead of being mistaken for exception cleanup and silently logged
- `Stopwatch.__exit__()` no longer raises `NotRunningError` if the stopwatch was already stopped inside the context, and it finalizes a paused stopwatch with pause-excluded elapsed time
- `Stopwatch.__exit__()` now checks the state and stops in one atomic step, so a `pause()` racing with the context exit can no longer make `__exit__()` raise `PausedStateError`

## [1.0.0] - 2025-10-19

### Added

- Initial release of ticko
- `StopWatch` class for thread-safe stopwatch functionality
  - Start, stop, lap, and reset operations
  - Lap timing support
  - Elapsed time measurement
- `@stopwatch` decorator for easy function timing
- Thread-safe implementation
- Type hints support with `py.typed`

[unreleased]: https://github.com/NakuRei/ticko/compare/v2.0.0...HEAD
[2.0.0]: https://github.com/NakuRei/ticko/compare/v1.0.0...v2.0.0
[1.0.0]: https://github.com/NakuRei/ticko/releases/tag/v1.0.0
