"""Using custom timer function with Stopwatch."""

import time

from ticko import Stopwatch

# Use time.time instead of default time.perf_counter
sw = Stopwatch(timer_func=time.time)
sw.start()

time.sleep(0.5)

sw.stop()
print(f"Elapsed time: {sw.time_elapsed:.3f} seconds")
print(f"Start time (Unix timestamp): {sw.time_start}")
print(f"Stop time (Unix timestamp): {sw.time_stop}")
