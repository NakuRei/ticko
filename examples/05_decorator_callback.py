"""Using @stopwatch decorator with custom callback."""

import time

from ticko import StopWatch, stopwatch


def custom_callback(sw: StopWatch) -> None:
    """Log execution time.

    Custom callback to log execution time.
    """
    print(f"Function took {sw.time_elapsed:.3f} seconds")


@stopwatch(exit_callback=custom_callback)
def fetch_data() -> str:
    """Simulate fetching data."""
    time.sleep(0.3)
    return "Data retrieved"


result = fetch_data()
print(f"Result: {result}")
