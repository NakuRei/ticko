"""Using exit callback with StopWatch."""

import time

from ticko import StopWatch


def on_stop(sw: StopWatch) -> None:
    """Print stopwatch elapsed time.

    Called automatically when stopwatch stops.
    """
    print("Stopwatch stopped!")
    print(f"Total elapsed time: {sw.time_elapsed:.3f} seconds")


# Create stopwatch with exit callback
sw = StopWatch(exit_callback=on_stop)
sw.start()

time.sleep(0.8)

# Callback is automatically invoked when stop() is called
sw.stop()
