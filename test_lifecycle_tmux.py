#!/usr/bin/env python3
"""Integration test LIFE-1: Full lifecycle test for tmux worker.

This test covers the complete workflow for a tmux-based worker:
spawn -> status -> send -> logs -> kill -> clean
"""

import json
import sys
import time
import unittest
from pathlib import Path

# Import the isolated test base class
sys.path.insert(0, str(Path(__file__).parent / "tests"))
from test_tmux_isolation import TmuxIsolatedTestCase, skip_if_no_tmux


def find_worker(workers_list: list, worker_id: str) -> dict:
    """Find a worker by ID in a list of worker dictionaries.

    Args:
        workers_list: List of worker dicts from get_workers()
        worker_id: Worker name/ID to search for

    Returns:
        Worker dict or None if not found
    """
    for worker in workers_list:
        if worker.get('name') == worker_id:
            return worker
    return None


class TestFullLifecycleTmux(TmuxIsolatedTestCase):
    """Test LIFE-1: Full lifecycle for tmux worker."""

    @skip_if_no_tmux
    def test_full_lifecycle_tmux_worker(self):
        """Test full lifecycle of a tmux worker.

        This test covers the complete workflow:
        1. Spawn - create a worker with --tmux
        2. Status - verify the worker is running via ls
        3. Send - send a command to the worker
        4. Logs - verify the command output appears in logs
        5. Kill - stop the worker
        6. Clean - remove the worker from state

        Acceptance Criteria:
        - Tests spawn command
        - Tests ls/status command
        - Tests send command
        - Tests logs command
        - Tests kill command
        - Tests clean command
        - Full happy path works end-to-end
        """
        # Use unique worker name based on test socket to avoid collisions
        worker_name = f"lifecycle-tmux-{self.tmux_socket[-8:]}"

        # 1. Spawn
        result = self.run_swarm('spawn', '--name', worker_name, '--tmux', '--', 'bash')
        self.assertEqual(
            result.returncode,
            0,
            f"spawn should succeed (returncode 0), got {result.returncode}. "
            f"Stdout: {result.stdout!r}, Stderr: {result.stderr!r}"
        )
        worker_id = self.parse_worker_id(result.stdout)
        self.assertEqual(
            worker_id,
            worker_name,
            f"Worker ID should match name '{worker_name}', got: {worker_id!r}"
        )

        # 2. Status - verify running
        workers = self.get_workers()
        self.assertEqual(
            len(workers),
            1,
            f"Expected exactly 1 worker after spawn, got {len(workers)}: "
            f"{[w['name'] for w in workers]!r}"
        )

        worker = find_worker(workers, worker_id)
        self.assertIsNotNone(
            worker,
            f"Worker '{worker_id}' should exist in state. Available workers: "
            f"{[w['name'] for w in workers]!r}"
        )
        self.assertEqual(
            worker['status'],
            'running',
            f"Worker should be running, got: {worker['status']!r}"
        )

        # Verify tmux info is present
        self.assertIsNotNone(
            worker.get('tmux'),
            "Worker should have tmux info (this is a tmux-based worker)"
        )
        tmux_info = worker['tmux']
        self.assertIsNotNone(
            tmux_info.get('session'),
            "Worker tmux info should have session name"
        )
        self.assertIsNotNone(
            tmux_info.get('window'),
            "Worker tmux info should have window name"
        )
        self.assertEqual(
            tmux_info.get('socket'),
            self.tmux_socket,
            f"Worker should use our isolated socket '{self.tmux_socket}', "
            f"got: {tmux_info.get('socket')!r}"
        )

        # 3. Send - send a command
        send_result = self.run_swarm('send', worker_id, 'echo LIFECYCLE_TEST')
        self.assertEqual(
            send_result.returncode,
            0,
            f"send should succeed (returncode 0), got {send_result.returncode}. "
            f"Stdout: {send_result.stdout!r}, Stderr: {send_result.stderr!r}"
        )

        # Allow time for command to execute
        time.sleep(0.5)

        # 4. Logs - verify command output
        logs_result = self.run_swarm('logs', worker_id)
        self.assertEqual(
            logs_result.returncode,
            0,
            f"logs should succeed (returncode 0), got {logs_result.returncode}. "
            f"Stdout: {logs_result.stdout!r}, Stderr: {logs_result.stderr!r}"
        )
        self.assertIn(
            'LIFECYCLE_TEST',
            logs_result.stdout,
            f"Command output 'LIFECYCLE_TEST' should appear in logs. "
            f"Logs output: {logs_result.stdout!r}"
        )

        # 5. Kill
        kill_result = self.run_swarm('kill', worker_id)
        self.assertEqual(
            kill_result.returncode,
            0,
            f"kill should succeed (returncode 0), got {kill_result.returncode}. "
            f"Stdout: {kill_result.stdout!r}, Stderr: {kill_result.stderr!r}"
        )
        self.assertIn(
            'killed',
            kill_result.stdout.lower(),
            f"kill output should confirm kill. Output: {kill_result.stdout!r}"
        )

        # Verify stopped
        time.sleep(0.5)  # Give it time to update state
        workers_after_kill = self.get_workers()
        self.assertEqual(
            len(workers_after_kill),
            1,
            f"Worker should still exist in state after kill (just stopped), "
            f"got {len(workers_after_kill)} workers"
        )

        worker_after_kill = find_worker(workers_after_kill, worker_id)
        self.assertIsNotNone(
            worker_after_kill,
            f"Worker '{worker_id}' should still exist after kill"
        )
        self.assertEqual(
            worker_after_kill['status'],
            'stopped',
            f"Worker should be stopped after kill, got: {worker_after_kill['status']!r}"
        )

        # 6. Clean
        clean_result = self.run_swarm('clean', worker_id)
        self.assertEqual(
            clean_result.returncode,
            0,
            f"clean should succeed (returncode 0), got {clean_result.returncode}. "
            f"Stdout: {clean_result.stdout!r}, Stderr: {clean_result.stderr!r}"
        )
        self.assertIn(
            'cleaned',
            clean_result.stdout.lower(),
            f"clean output should confirm cleanup. Output: {clean_result.stdout!r}"
        )

        # Verify removed
        workers_final = self.get_workers()
        self.assertEqual(
            len(workers_final),
            0,
            f"Expected 0 workers after clean (worker should be removed), "
            f"got {len(workers_final)}: {[w['name'] for w in workers_final]!r}"
        )

        worker_final = find_worker(workers_final, worker_id)
        self.assertIsNone(
            worker_final,
            f"Worker '{worker_id}' should be removed from state after clean"
        )


def main():
    """Run all integration tests."""
    print("=" * 60)
    print("Running LIFE-1: Full lifecycle tmux worker integration tests")
    print("=" * 60)

    # Run with unittest
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromTestCase(TestFullLifecycleTmux)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    print("=" * 60)
    if result.wasSuccessful():
        print("All integration tests passed!")
        print("=" * 60)
        return 0
    else:
        print("Some tests failed!")
        print("=" * 60)
        return 1


if __name__ == "__main__":
    sys.exit(main())
