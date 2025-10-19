"""Using @stopwatch decorator for automatic function timing."""

import time

from ticko import stopwatch


@stopwatch
def process_data(n: int) -> int:
    """Simulate data processing."""
    time.sleep(0.5)
    return n * 2


# The decorator automatically prints execution time
result = process_data(10)
print(f"Result: {result}")
