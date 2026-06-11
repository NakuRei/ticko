"""Shared pytest fixtures."""

from unittest.mock import Mock

import pytest


@pytest.fixture
def mock_timer() -> Mock:
    """Create a mock timer function."""
    return Mock(side_effect=[0.0, 1.0, 2.0, 3.0, 4.0, 5.0])
