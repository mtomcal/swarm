#!/usr/bin/env python3
"""Integration test for cmd_status"""

import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

def test_status_worker_not_found():
    """Test status command for non-existent worker."""
    # Set up clean environment
    with tempfile.TemporaryDirectory() as tmpdir:
        env = os.environ.copy()
        env['HOME'] = tmpdir

        # Try to get status of non-existent worker
        result = subprocess.run(
            ['./swarm.py', 'status', 'nonexistent'],
            capture_output=True,
            text=True,
            env=env
        )

        # Should exit with code 2 (not found)
        assert result.returncode == 2, f"Expected exit code 2, got {result.returncode}"
        assert "worker 'nonexistent' not found" in result.stderr, f"Expected error message in stderr: {result.stderr}"
        print("✓ Test passed: worker not found")


def test_status_worker_mock():
    """Test status command with a mocked worker."""
    with tempfile.TemporaryDirectory() as tmpdir:
        env = os.environ.copy()
        env['HOME'] = tmpdir

        # Create state directory
        swarm_dir = Path(tmpdir) / ".swarm"
        swarm_dir.mkdir(parents=True)

        # Create a mock worker in state
        started = (datetime.now() - timedelta(minutes=5)).isoformat()
        state_data = {
            "workers": [
                {
                    "name": "test-worker",
                    "status": "running",
                    "cmd": ["sleep", "100"],
                    "started": started,
                    "cwd": "/tmp",
                    "env": {},
                    "tags": [],
                    "tmux": None,
                    "worktree": None,
                    "pid": 99999  # Non-existent PID
                }
            ]
        }

        state_file = swarm_dir / "state.json"
        with open(state_file, "w") as f:
            json.dump(state_data, f)

        # Get status
        result = subprocess.run(
            ['./swarm.py', 'status', 'test-worker'],
            capture_output=True,
            text=True,
            env=env
        )

        # Should exit with code 1 (stopped, since PID 99999 doesn't exist)
        assert result.returncode == 1, f"Expected exit code 1, got {result.returncode}"
        assert "test-worker: stopped" in result.stdout, f"Expected status in stdout: {result.stdout}"
        assert "pid 99999" in result.stdout, f"Expected PID in output: {result.stdout}"
        assert "uptime 5m" in result.stdout, f"Expected uptime in output: {result.stdout}"
        print("✓ Test passed: worker status with PID")


if __name__ == "__main__":
    print("Running integration tests for cmd_status...")
    try:
        test_status_worker_not_found()
        test_status_worker_mock()
        print("\n✓ All integration tests passed!")
    except AssertionError as e:
        print(f"\n✗ Test failed: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ Test error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
