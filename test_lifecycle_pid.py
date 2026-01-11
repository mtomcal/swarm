#!/usr/bin/env python3
"""Integration test LIFE-2: Full lifecycle test for non-tmux background process worker."""

import json
import subprocess
import sys
import time
import unittest
from pathlib import Path


SWARM_CMD = "./swarm.py"


def run_swarm(*args, check=False):
    """Run swarm command and return result."""
    cmd = [SWARM_CMD] + list(args)
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        check=False,
    )
    if check and result.returncode != 0:
        print(f"Command failed: {' '.join(cmd)}", file=sys.stderr)
        print(f"stdout: {result.stdout}", file=sys.stderr)
        print(f"stderr: {result.stderr}", file=sys.stderr)
        raise RuntimeError(f"Command failed with code {result.returncode}")
    return result


def parse_worker_id(output: str) -> str:
    """Parse worker ID from spawn command output.

    Expected format: "spawned <worker-id> (pid: <pid>)"
    """
    for line in output.split('\n'):
        line = line.strip()
        if 'spawned' in line.lower():
            # Format: "spawned test-worker (pid: 12345)"
            # Extract the worker name between "spawned" and "(pid:"
            parts = line.split()
            if len(parts) >= 2:
                # Second word should be the worker ID
                worker_id = parts[1]
                # Remove any trailing parentheses or punctuation
                worker_id = worker_id.rstrip('(').rstrip(':').rstrip(',')
                return worker_id

    # If no pattern matched, raise error
    raise ValueError(f"Could not parse worker ID from output: {output}")


def find_worker(json_output: str, worker_id: str) -> dict:
    """Find a worker by ID in JSON output from 'swarm ls --json'.

    Returns worker dict or None if not found.
    """
    try:
        workers = json.loads(json_output)
        for worker in workers:
            if worker.get('name') == worker_id:
                return worker
        return None
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON output: {e}\n{json_output}")


class TestFullLifecyclePid(unittest.TestCase):
    """Test LIFE-2: Full lifecycle for PID-based (non-tmux) worker."""

    def setUp(self):
        """Set up test - ensure clean state."""
        self.test_worker_name = f"test-lifecycle-pid-{int(time.time())}"
        self.cleanup_worker(self.test_worker_name)

    def tearDown(self):
        """Clean up test worker."""
        self.cleanup_worker(self.test_worker_name)

    def cleanup_worker(self, name: str):
        """Clean up a test worker."""
        run_swarm("kill", name, check=False)
        run_swarm("clean", name, "--rm-worktree", check=False)

    def test_full_lifecycle_pid_worker(self):
        """Test full lifecycle of a PID-based worker.

        Tests:
        1. Spawn without --tmux (uses PID tracking)
        2. Verify worker is running with PID
        3. Kill the worker
        4. Verify worker is stopped
        5. Clean the worker
        6. Verify worker is removed from state
        """
        # 1. Spawn (no --tmux, uses PID tracking)
        result = run_swarm('spawn', '--name', self.test_worker_name, '--', 'sleep', '300')
        self.assertEqual(result.returncode, 0,
                        f"spawn should succeed. stderr: {result.stderr}")

        worker_id = parse_worker_id(result.stdout)
        self.assertEqual(worker_id, self.test_worker_name,
                        f"Worker ID should match name. Got: {worker_id}")

        # 2. Status - verify running
        ls = run_swarm('ls', '--format', 'json')
        self.assertEqual(ls.returncode, 0, "ls should succeed")

        worker = find_worker(ls.stdout, worker_id)
        self.assertIsNotNone(worker,
                            f"Worker {worker_id} should exist in state")
        self.assertEqual(worker['status'], 'running',
                        f"Worker should be running, got: {worker['status']}")
        self.assertIsNotNone(worker.get('pid'),
                            "Worker should have a PID")
        self.assertIsNone(worker.get('tmux'),
                         "Worker should NOT have tmux info (this is PID-based)")

        # Store PID for later verification
        pid = worker['pid']
        self.assertGreater(pid, 0, "PID should be positive")

        # 3. Kill
        kill = run_swarm('kill', worker_id)
        self.assertEqual(kill.returncode, 0,
                        f"kill should succeed. stderr: {kill.stderr}")
        self.assertIn('killed', kill.stdout.lower(),
                     "kill output should confirm kill")

        # Verify stopped
        time.sleep(0.5)  # Give it time to update state
        ls2 = run_swarm('ls', '--format', 'json')
        self.assertEqual(ls2.returncode, 0, "ls should succeed")

        worker2 = find_worker(ls2.stdout, worker_id)
        self.assertIsNotNone(worker2,
                            f"Worker {worker_id} should still exist after kill")
        self.assertEqual(worker2['status'], 'stopped',
                        f"Worker should be stopped, got: {worker2['status']}")

        # 4. Clean
        clean = run_swarm('clean', worker_id)
        self.assertEqual(clean.returncode, 0,
                        f"clean should succeed. stderr: {clean.stderr}")
        self.assertIn('cleaned', clean.stdout.lower(),
                     "clean output should confirm cleanup")

        # Verify removed
        ls3 = run_swarm('ls', '--format', 'json')
        self.assertEqual(ls3.returncode, 0, "ls should succeed")

        worker3 = find_worker(ls3.stdout, worker_id)
        self.assertIsNone(worker3,
                         f"Worker {worker_id} should be removed after clean")


def main():
    """Run all integration tests."""
    print("=" * 60)
    print("Running LIFE-2: Full lifecycle PID worker integration tests")
    print("=" * 60)

    # Run with unittest
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromTestCase(TestFullLifecyclePid)
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
