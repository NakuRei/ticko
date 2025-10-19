"""Using custom timer function with StopWatch."""

import time

from ticko import StopWatch

# Use time.time instead of default time.perf_counter
sw = StopWatch(timer_func=time.time)
sw.start()

time.sleep(0.5)

sw.stop()
print(f"Elapsed time: {sw.time_elapsed:.3f} seconds")
print(f"Start time (Unix timestamp): {sw.time_start}")
print(f"Stop time (Unix timestamp): {sw.time_stop}")
