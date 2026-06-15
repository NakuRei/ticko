"""Using a custom timer function to measure CPU time."""

import time

from ticko import Stopwatch

# time.process_time counts CPU time, so sleeping contributes ~0
sw = Stopwatch(timer_func=time.process_time)
sw.start()

time.sleep(0.5)  # Waiting: barely any CPU time
total = sum(i * i for i in range(10**6))  # Actual CPU work

cpu_seconds = sw.stop()
print(f"CPU time consumed: {cpu_seconds:.3f} seconds")
