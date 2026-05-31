"""Assertions for human-readable timing output."""

import re
from typing import Final

import pytest

_SECONDS_VALUE_PATTERN: Final = re.compile(
    r"(?<![\w.])(?P<value>\d+(?:\.\d+)?)\s*"
    r"(?P<unit>seconds?|secs?|s)\b",
)


def assert_elapsed_seconds_displayed(output: str, expected: float) -> None:
    """Assert that output shows the expected elapsed value in seconds."""
    for match in _SECONDS_VALUE_PATTERN.finditer(output):
        if float(match.group("value")) == pytest.approx(expected):
            return

    pytest.fail(
        f"Expected elapsed seconds value near {expected!r} in {output!r}",
    )
