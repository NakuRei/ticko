"""Custom logger configuration for ticko.

ticko internally uses Python's standard logging module.
The logger name is 'ticko._stopwatch', and all internal
messages are emitted at DEBUG level.

By default nothing is printed because the root logger level
is WARNING. Configure the 'ticko' logger to see the messages.
"""

import logging
import time
from pathlib import Path

from ticko import Stopwatch

# --- Example 1: Enable debug output to the console ---

handler = logging.StreamHandler()
handler.setFormatter(
    logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
)

ticko_logger = logging.getLogger("ticko")
ticko_logger.setLevel(logging.DEBUG)
ticko_logger.addHandler(handler)

print("=== Example 1: Console logging ===")
sw = Stopwatch(name="task-A")
sw.start()
time.sleep(0.1)
sw.lap()
time.sleep(0.1)
sw.stop()
sw.reset()

# --- Example 2: Redirect ticko logs to a file ---

print("\n=== Example 2: File logging ===")
file_handler = logging.FileHandler("stopwatch.log", mode="w")
file_handler.setFormatter(
    logging.Formatter("%(asctime)s %(levelname)s %(message)s")
)

file_logger = logging.getLogger("ticko._stopwatch")
file_logger.addHandler(file_handler)

sw2 = Stopwatch(name="task-B")
sw2.start()
time.sleep(0.05)
sw2.stop()

print("Logs written to stopwatch.log")
print(Path("stopwatch.log").read_text(), end="")

# Cleanup
Path("stopwatch.log").unlink()
