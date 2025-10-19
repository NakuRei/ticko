"""Thread-safe lap timing with multiple threads.

This demonstrates that multiple threads can safely call lap() on a shared
StopWatch instance.
"""

import time
from concurrent.futures import ThreadPoolExecutor

from ticko import StopWatch


def worker(task_id: int, sw: StopWatch) -> tuple[int, float]:
    """Simulate work and record a lap time.

    Args:
        task_id: Task identifier
        sw: Shared StopWatch instance

    Returns:
        Tuple of (task_id, lap_time)

    """
    # Simulate work with varying duration per task
    time.sleep(0.05 * task_id)

    # Thread-safe: Multiple threads can safely call lap()
    lap_time = sw.lap()

    print(f"Task {task_id} completed - Lap time: {lap_time:.3f}s")
    return task_id, lap_time


def main() -> None:
    """Run multiple threads sharing a single StopWatch."""
    sw = StopWatch()
    sw.start()

    # Run 5 tasks concurrently
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(worker, i, sw) for i in range(1, 6)]

        # Wait for all tasks to complete
        results = [future.result() for future in futures]

    total_elapsed = sw.stop()

    print(f"\nAll tasks completed in {total_elapsed:.3f}s")
    print(f"Recorded {len(results)} lap times safely")


if __name__ == "__main__":
    main()
