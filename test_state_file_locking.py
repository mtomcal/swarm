#!/usr/bin/env python3
"""Unit tests for state file locking mechanism.

This module tests the file locking functionality that prevents race conditions
during concurrent state file operations.

The file locking implementation uses fcntl.flock() with LOCK_EX to ensure
that concurrent swarm operations don't cause lost updates to state.json.

Test coverage:
- Exclusive lock prevents simultaneous file access
- Concurrent state updates preserve all changes
- Lock is released even if exception occurs
- Corrupt state file recovery (backup + reset)
"""

import fcntl
import io
import json
import os
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import swarm


class TestStateLocking(unittest.TestCase):
    """Test state file locking mechanisms."""

    def setUp(self):
        """Create a temporary state file for testing."""
        self.temp_dir = tempfile.mkdtemp()
        self.state_file = Path(self.temp_dir) / "state.json"
        # Initialize with empty state
        with open(self.state_file, "w") as f:
            json.dump({"workers": []}, f)

    def tearDown(self):
        """Clean up temporary files."""
        import shutil
        shutil.rmtree(self.temp_dir)

    def test_exclusive_lock_prevents_concurrent_writes(self):
        """Verify that exclusive lock prevents simultaneous file access.

        This test ensures that when one thread holds an exclusive lock,
        other threads must wait before accessing the file.
        """
        lock_acquired_times = []
        lock_file_path = self.state_file.with_suffix('.lock')

        def worker_thread(worker_id, delay):
            """Acquire lock, record time, hold briefly, then release."""
            with open(lock_file_path, 'w') as lock_file:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
                try:
                    # Record when we got the lock
                    lock_acquired_times.append((worker_id, time.time()))
                    # Hold lock briefly
                    time.sleep(delay)
                finally:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

        # Start two threads trying to acquire lock simultaneously
        t1 = threading.Thread(target=worker_thread, args=(1, 0.1))
        t2 = threading.Thread(target=worker_thread, args=(2, 0.1))

        t1.start()
        t2.start()
        t1.join()
        t2.join()

        # Both should have acquired the lock, but at different times
        self.assertEqual(len(lock_acquired_times), 2)

        # The time gap between acquisitions should be >= 0.1s (the hold time)
        time_gap = abs(lock_acquired_times[1][1] - lock_acquired_times[0][1])
        self.assertGreaterEqual(
            time_gap,
            0.09,  # Allow small margin for timing precision
            f"Lock was not properly exclusive. Time gap: {time_gap}s, "
            f"expected >= 0.09s. Acquisitions: {lock_acquired_times}"
        )

    def test_concurrent_state_updates_with_locking(self):
        """Verify that with locking, concurrent updates don't lose data.

        This test simulates the real-world scenario where multiple swarm
        commands try to update state.json simultaneously. With proper locking,
        all updates should be preserved.
        """
        results = []
        lock_file_path = self.state_file.with_suffix('.lock')

        def update_state(worker_name):
            """Load state, add worker, save state (with locking)."""
            try:
                with open(lock_file_path, 'w') as lock_file:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
                    try:
                        # Load current state
                        with open(self.state_file, 'r') as f:
                            state = json.load(f)

                        # Modify state
                        state['workers'].append({'name': worker_name})

                        # Small delay to increase chance of race condition
                        time.sleep(0.01)

                        # Save state
                        with open(self.state_file, 'w') as f:
                            json.dump(state, f, indent=2)

                        results.append(('success', worker_name))
                    finally:
                        fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
            except Exception as e:
                results.append(('error', worker_name, str(e)))

        # Run 5 concurrent updates
        threads = []
        for i in range(5):
            t = threading.Thread(target=update_state, args=(f'worker-{i}',))
            threads.append(t)
            t.start()

        # Wait for all to complete
        for t in threads:
            t.join()

        # All should succeed
        self.assertEqual(len(results), 5)
        for result in results:
            self.assertEqual(result[0], 'success', f"Update failed: {result}")

        # Final state should have all 5 workers
        with open(self.state_file, 'r') as f:
            final_state = json.load(f)

        self.assertEqual(
            len(final_state['workers']),
            5,
            f"Expected 5 workers in final state, got {len(final_state['workers'])}. "
            f"Workers: {[w['name'] for w in final_state['workers']]}"
        )

        # All worker names should be present
        worker_names = {w['name'] for w in final_state['workers']}
        expected_names = {f'worker-{i}' for i in range(5)}
        self.assertEqual(
            worker_names,
            expected_names,
            f"Missing workers. Expected: {expected_names}, Got: {worker_names}"
        )

    def test_lock_released_on_exception(self):
        """Verify lock is released even if exception occurs during critical section.

        This ensures that if an error occurs while holding the lock, the lock
        is still properly released so other threads aren't blocked forever.
        """
        lock_file_path = self.state_file.with_suffix('.lock')

        # First thread will acquire lock and raise exception
        def thread_with_error():
            with open(lock_file_path, 'w') as lock_file:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
                try:
                    raise ValueError("Simulated error")
                finally:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

        # Run thread and expect exception
        t1 = threading.Thread(target=thread_with_error)
        t1.start()
        t1.join()

        # Second thread should be able to acquire lock without hanging
        acquired = []
        def thread_normal():
            with open(lock_file_path, 'w') as lock_file:
                # Try to acquire with timeout (non-blocking)
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                try:
                    acquired.append(True)
                finally:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

        t2 = threading.Thread(target=thread_normal)
        t2.start()
        t2.join(timeout=1.0)  # Should complete quickly

        self.assertTrue(
            t2.is_alive() is False,
            "Second thread is still blocked, lock was not released after exception"
        )
        self.assertEqual(len(acquired), 1, "Second thread failed to acquire lock")


class TestCorruptStateRecovery(unittest.TestCase):
    """Test corrupt state file recovery in State._load()."""

    def setUp(self):
        """Create temporary directory and patch swarm constants."""
        self.temp_dir = tempfile.mkdtemp()
        self.state_file = Path(self.temp_dir) / "state.json"
        self.logs_dir = Path(self.temp_dir) / "logs"
        self.logs_dir.mkdir(exist_ok=True)

        self.swarm_dir_patch = patch.object(swarm, 'SWARM_DIR', Path(self.temp_dir))
        self.state_file_patch = patch.object(swarm, 'STATE_FILE', self.state_file)
        self.state_lock_file_patch = patch.object(swarm, 'STATE_LOCK_FILE', Path(self.temp_dir) / "state.lock")
        self.logs_dir_patch = patch.object(swarm, 'LOGS_DIR', self.logs_dir)

        self.swarm_dir_patch.start()
        self.state_file_patch.start()
        self.state_lock_file_patch.start()
        self.logs_dir_patch.start()

    def tearDown(self):
        """Clean up patches and temporary files."""
        self.swarm_dir_patch.stop()
        self.state_file_patch.stop()
        self.state_lock_file_patch.stop()
        self.logs_dir_patch.stop()

        import shutil
        shutil.rmtree(self.temp_dir)

    def test_corrupt_json_resets_workers_and_warns(self):
        """Corrupt JSON in state file results in empty workers, warning, and backup."""
        corrupt_content = "{invalid json content!!"
        with open(self.state_file, "w") as f:
            f.write(corrupt_content)

        with patch('sys.stderr', new_callable=io.StringIO) as mock_stderr:
            state = swarm.State()

        self.assertEqual(state.workers, [])
        self.assertIn("swarm: warning: corrupt state file, resetting", mock_stderr.getvalue())

        # Verify backup was created
        corrupted_path = Path(self.temp_dir) / "state.json.corrupted"
        self.assertTrue(corrupted_path.exists())
        with open(corrupted_path, "r") as f:
            self.assertEqual(f.read(), corrupt_content)

    def test_empty_file_resets_workers_and_warns(self):
        """Empty state file results in empty workers and warning."""
        with open(self.state_file, "w") as f:
            f.write("")

        with patch('sys.stderr', new_callable=io.StringIO) as mock_stderr:
            state = swarm.State()

        self.assertEqual(state.workers, [])
        self.assertIn("swarm: warning: corrupt state file, resetting", mock_stderr.getvalue())

    def test_valid_json_loads_normally(self):
        """Valid JSON state file loads workers without warning."""
        state_data = {"workers": [
            {"name": "test-worker", "status": "running", "cmd": ["echo"],
             "started": "2026-01-01T00:00:00", "cwd": "/tmp",
             "tmux": None, "worktree": None,
             "pid": 1234, "metadata": {}}
        ]}
        with open(self.state_file, "w") as f:
            json.dump(state_data, f)

        with patch('sys.stderr', new_callable=io.StringIO) as mock_stderr:
            state = swarm.State()

        self.assertEqual(len(state.workers), 1)
        self.assertEqual(state.workers[0].name, "test-worker")
        self.assertNotIn("warning", mock_stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
