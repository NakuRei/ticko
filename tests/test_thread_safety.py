"""Tests for thread safety of StopWatch."""

import threading
import time
from typing import Any

from ticko.stop_watch import AlreadyRunningError, NotStartedError, StopWatch


class TestThreadSafety:
    """Test cases for thread safety."""

    def test_concurrent_property_reads(self) -> None:
        """Test reading properties from multiple threads."""
        sw = StopWatch()
        sw.start()
        results: list[tuple[str, Any]] = []
        errors: list[Exception] = []

        def read_properties() -> None:
            try:
                for _ in range(100):
                    results.append(("is_running", sw.is_running))
                    results.append(("time_start", sw.time_start))
                    results.append(("time_elapsed", sw.time_elapsed))
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=read_properties) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        sw.stop()
        assert len(errors) == 0, f"Unexpected errors: {errors}"

    def test_concurrent_laps(self) -> None:
        """Test recording laps from multiple threads."""
        sw = StopWatch()
        sw.start()
        lap_times: list[float] = []
        errors: list[Exception] = []

        def record_laps() -> None:
            try:
                for _ in range(10):
                    lap_time = sw.lap()
                    lap_times.append(lap_time)
                    time.sleep(0.001)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=record_laps) for _ in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        sw.stop()
        assert len(errors) == 0, f"Unexpected errors: {errors}"
        assert len(lap_times) == 30  # 10 laps * 3 threads
        # All lap times should be non-negative
        for lap_time in lap_times:
            assert lap_time >= 0

    def test_concurrent_start_attempts(self) -> None:
        """Test multiple threads trying to start stopwatch."""
        sw = StopWatch()
        start_count = 0
        error_count = 0
        lock = threading.Lock()

        def try_start() -> None:
            nonlocal start_count, error_count
            try:
                sw.start()
                with lock:
                    start_count += 1
            except AlreadyRunningError:
                with lock:
                    error_count += 1

        threads = [threading.Thread(target=try_start) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Only one thread should successfully start
        assert start_count == 1
        assert error_count == 9
        assert sw.is_running
        sw.stop()

    def test_concurrent_stop_attempts(self) -> None:
        """Test multiple threads trying to stop stopwatch."""
        sw = StopWatch()
        sw.start()
        time.sleep(0.01)  # Let it run for a bit

        stop_count = 0
        error_count = 0
        lock = threading.Lock()

        def try_stop() -> None:
            nonlocal stop_count, error_count
            try:
                sw.stop()
                with lock:
                    stop_count += 1
            except NotStartedError:
                with lock:
                    error_count += 1

        threads = [threading.Thread(target=try_stop) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Only one thread should successfully stop
        assert stop_count == 1
        assert error_count == 9
        assert not sw.is_running

    def test_reset_while_reading(self) -> None:
        """Test resetting while other threads are reading."""
        sw = StopWatch()
        sw.start()
        time.sleep(0.01)

        should_stop = threading.Event()
        errors: list[Exception] = []

        def continuous_read() -> None:
            try:
                while not should_stop.is_set():
                    try:
                        _ = sw.is_running
                        if sw.time_start is not None:
                            _ = sw.time_elapsed
                    except NotStartedError:
                        # Expected after reset
                        pass
                    time.sleep(0.0001)
            except Exception as e:
                errors.append(e)

        def reset_stopwatch() -> None:
            try:
                time.sleep(0.005)
                sw.stop()
                sw.reset()
            except Exception as e:
                errors.append(e)

        reader_threads = [
            threading.Thread(target=continuous_read) for _ in range(3)
        ]
        reset_thread = threading.Thread(target=reset_stopwatch)

        for t in reader_threads:
            t.start()
        reset_thread.start()

        reset_thread.join()
        time.sleep(0.01)
        should_stop.set()

        for t in reader_threads:
            t.join()

        assert len(errors) == 0, f"Unexpected errors: {errors}"

    def test_context_manager_in_threads(self) -> None:
        """Test using stopwatch as context manager in multiple threads."""
        results: list[float] = []
        errors: list[Exception] = []

        def use_context_manager() -> None:
            try:
                sw = StopWatch()
                with sw:
                    time.sleep(0.01)
                    elapsed = sw.time_elapsed
                results.append(elapsed)
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=use_context_manager) for _ in range(5)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f"Unexpected errors: {errors}"
        assert len(results) == 5
        for elapsed in results:
            assert elapsed > 0.009

    def test_callback_thread_safety(self) -> None:
        """Test that exit callbacks are thread-safe."""
        callback_calls: list[float] = []
        lock = threading.Lock()

        def thread_safe_callback(sw: StopWatch) -> None:
            with lock:
                callback_calls.append(sw.time_elapsed)

        def run_stopwatch() -> None:
            sw = StopWatch(exit_callback=thread_safe_callback)
            sw.start()
            time.sleep(0.001)
            sw.stop()

        threads = [threading.Thread(target=run_stopwatch) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(callback_calls) == 10


class TestRaceConditions:
    """Test for potential race conditions."""

    def test_start_stop_race(self) -> None:
        """Test rapid start/stop cycles."""
        sw = StopWatch()
        errors: list[Exception] = []

        for _ in range(100):
            try:
                sw.start()
                sw.stop()
                sw.reset()
            except Exception as e:
                errors.append(e)

        assert len(errors) == 0

    def test_lap_property_consistency(self) -> None:
        """Test that lap times and properties remain consistent."""
        sw = StopWatch()
        sw.start()

        for _ in range(50):
            sw.lap()
            last_lap_property = sw.time_last_lap
            # The property should be very close to 0 right after lap
            assert last_lap_property < 0.01

        sw.stop()
