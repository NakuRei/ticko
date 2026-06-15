"""Using exit callback with Stopwatch."""

import time

from ticko import Stopwatch


def on_stop(elapsed: float) -> None:
    """Print stopwatch elapsed time.

    Called automatically when stopwatch stops.
    """
    print("Stopwatch stopped!")
    print(f"Total elapsed time: {elapsed:.3f} seconds")


# Create stopwatch with exit callback
sw = Stopwatch(exit_callback=on_stop)
sw.start()

time.sleep(0.8)

# Callback is automatically invoked when stop() is called
sw.stop()
