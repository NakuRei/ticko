"""Basic stopwatch usage example."""

import time

from ticko import Stopwatch

# Create and start a stopwatch
sw = Stopwatch()
sw.start()

# Simulate some work
time.sleep(1)

# Stop and get elapsed time
elapsed = sw.stop()
print(f"Elapsed time: {elapsed:.3f} seconds")
