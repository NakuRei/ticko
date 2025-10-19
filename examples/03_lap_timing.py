"""Recording lap times with StopWatch."""

import time

from ticko import StopWatch

sw = StopWatch()
sw.start()

# Record multiple laps
time.sleep(0.5)
lap1 = sw.lap()
print(f"Lap 1: {lap1:.3f} seconds")

time.sleep(0.3)
lap2 = sw.lap()
print(f"Lap 2: {lap2:.3f} seconds")

time.sleep(0.2)
lap3 = sw.lap()
print(f"Lap 3: {lap3:.3f} seconds")

total = sw.stop()
print(f"\nTotal time: {total:.3f} seconds")
