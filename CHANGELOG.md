# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [2.0.0] - 2026-06-11

### Added

- `Stopwatch.pause()` and `Stopwatch.resume()` to suspend and continue timing without losing elapsed time
- `name` keyword argument to `Stopwatch` and a read-only `name` property; the name appears in log messages and string representations to identify a stopwatch
- `Stopwatch.laps` property returning the full history of recorded lap durations as an immutable tuple in recording order; `stop()` now appends the final segment so the durations sum to `time_elapsed`
- Dedicated exception classes `NotRunningError`, `AlreadyPausedError`, `NotPausedError`, and `NoLapsRecordedError`, splitting lifecycle, paused-state, and missing-lap failures into specific `StopwatchError` subclasses

### Changed

- Renamed `StopWatch` to `Stopwatch` and `StopWatchError` to `StopwatchError` to reflect that "stopwatch" is a single English word
- Renamed the `time_last_lap` property to `time_since_last_lap`
- `exit_callback` now receives the elapsed time as a `float` instead of the stopwatch instance; its type changed from `Callable[[Stopwatch], None]` to `Callable[[float], None]`, affecting both `Stopwatch` and the `@stopwatch` decorator
- `Stopwatch.start()` now returns `None` instead of the start time
- The default `@stopwatch` message changed from `Function '<name>' executed in <n> seconds` to `Function '<name>' exited after <n> seconds`

### Removed

- The old `ticko.stop_watch` module; `ticko._stopwatch` is a private implementation module. Import `Stopwatch` from the `ticko` package root instead
- `InvalidStateError`; use the specific `StopwatchError` subclasses instead
- The `time_last_lap_start` property

### Fixed

- `@stopwatch` now measures the full execution time of async functions, awaiting the coroutine instead of timing only its creation
- `@stopwatch` now measures async callable objects through their awaited body
- The default `@stopwatch` output now handles callable objects without a `__name__` attribute
- The package no longer emits log records by default; a `NullHandler` is attached so logging stays silent unless the application configures it
- When `stop()` fails while a decorated function is unwinding from an exception, the original exception is preserved and re-raised instead of being masked by the stop failure
- `Stopwatch.__exit__()` no longer raises `NotRunningError` if the stopwatch was already stopped inside the context, and it finalizes a paused stopwatch with pause-excluded elapsed time

## [1.0.0] - 2025-10-19

### Added

- Initial release of ticko
- `StopWatch` class for thread-safe stopwatch functionality
  - Start, stop, lap, and reset operations
  - Lap timing support
  - Elapsed time measurement
- `@stopwatch` decorator for easy function timing
- Thread-safe implementation using locks
- Type hints support with `py.typed`
- Comprehensive test suite with pytest
- CI/CD pipeline with GitHub Actions
- Code coverage reporting with Codecov

[unreleased]: https://github.com/NakuRei/ticko/compare/v2.0.0...HEAD
[2.0.0]: https://github.com/NakuRei/ticko/compare/v1.0.0...v2.0.0
[1.0.0]: https://github.com/NakuRei/ticko/releases/tag/v1.0.0
