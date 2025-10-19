# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.0.0] - 2025-10-19

### Added

- Initial release of ticko
- `StopWatch` class for thread-safe stopwatch functionality
  - Start, stop, pause, and resume operations
  - Lap timing support
  - Elapsed time measurement
- `@stopwatch` decorator for easy function timing
- Thread-safe implementation using locks
- Type hints support with `py.typed`
- Comprehensive test suite with pytest
- CI/CD pipeline with GitHub Actions
- Code coverage reporting with Codecov

[unreleased]: https://github.com/NakuRei/ticko/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/NakuRei/ticko/releases/tag/v1.0.0
