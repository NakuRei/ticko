"""Using StopWatch as a context manager."""

import time

from ticko import StopWatch

# Use as context manager (automatically starts and stops)
with StopWatch() as sw:
    time.sleep(1)
    print(f"Still running: {sw.time_elapsed:.3f} seconds")

# Automatically stopped when exiting the context
print(f"Final elapsed time: {sw.time_elapsed:.3f} seconds")
