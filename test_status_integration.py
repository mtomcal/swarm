#!/usr/bin/env python3
"""Integration test for cmd_status"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path


class TestStatusIntegration(unittest.TestCase):
    """Integration tests for the status command."""

    def setUp(self):
        """Create a temporary directory for SWARM state."""
        self.tmpdir = tempfile.mkdtemp()
        self.env = os.environ.copy()
        self.env['HOME'] = self.tmpdir
        # Create .swarm directory
        swarm_dir = Path(self.tmpdir) / ".swarm"
        swarm_dir.mkdir(parents=True, exist_ok=True)
        (swarm_dir / "logs").mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        """Clean up temp directory."""
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_status_worker_not_found(self):
        """Test status command for non-existent worker."""
        result = subprocess.run(
            ['./swarm.py', 'status', 'nonexistent'],
            capture_output=True,
            text=True,
            env=self.env
        )

        # Should exit with code 2 (not found)
        self.assertEqual(result.returncode, 2, f"Expected exit code 2, got {result.returncode}")
        self.assertIn("worker 'nonexistent' not found", result.stderr)

    def test_status_worker_mock(self):
        """Test status command with a mocked worker (PID doesn't exist)."""
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

        state_file = Path(self.tmpdir) / ".swarm" / "state.json"
        with open(state_file, "w") as f:
            json.dump(state_data, f)

        # Get status
        result = subprocess.run(
            ['./swarm.py', 'status', 'test-worker'],
            capture_output=True,
            text=True,
            env=self.env
        )

        # Should exit with code 1 (stopped, since PID 99999 doesn't exist)
        self.assertEqual(result.returncode, 1, f"Expected exit code 1, got {result.returncode}")
        self.assertIn("test-worker: stopped", result.stdout)
        self.assertIn("pid 99999", result.stdout)
        self.assertIn("uptime 5m", result.stdout)


if __name__ == "__main__":
    unittest.main()
