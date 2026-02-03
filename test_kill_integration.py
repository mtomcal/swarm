#!/usr/bin/env python3
"""Integration test for swarm kill command"""

import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

SWARM_CMD = "./swarm.py"


def run_swarm(*args, env=None, check=True):
    """Run swarm command and return result."""
    cmd = [SWARM_CMD] + list(args)
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    if check and result.returncode != 0:
        raise RuntimeError(
            f"Command failed with code {result.returncode}\n"
            f"stdout: {result.stdout}\n"
            f"stderr: {result.stderr}"
        )
    return result


class TestKillIntegration(unittest.TestCase):
    """Integration tests for the kill command."""

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
        """Clean up any test workers and temp directory."""
        # Try to clean up any workers we created
        try:
            run_swarm("kill", "--all", env=self.env, check=False)
            run_swarm("clean", "--all", env=self.env, check=False)
        except Exception:
            pass

        # Clean up the temp directory
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def get_state(self):
        """Load current swarm state."""
        state_file = Path(self.tmpdir) / ".swarm" / "state.json"
        if state_file.exists():
            with open(state_file) as f:
                return json.load(f)
        return {"workers": []}

    def test_kill_basic_worker(self):
        """Test killing a basic PID worker."""
        # Spawn a simple process
        result = run_swarm(
            "spawn", "--name", "test-kill-basic",
            "--", "sleep", "1000",
            env=self.env
        )
        self.assertEqual(result.returncode, 0, "spawn should succeed")

        # Verify it's running
        state = self.get_state()
        worker = next(
            (w for w in state["workers"] if w["name"] == "test-kill-basic"),
            None
        )
        self.assertIsNotNone(worker, "worker should exist")
        self.assertEqual(worker["status"], "running", "worker should be running")
        pid = worker["pid"]
        self.assertIsNotNone(pid, "worker should have a PID")

        # Kill the worker
        result = run_swarm("kill", "test-kill-basic", env=self.env)
        self.assertEqual(result.returncode, 0, "kill should succeed")
        self.assertIn("killed test-kill-basic", result.stdout, "should print confirmation")

        # Verify it's stopped
        state = self.get_state()
        worker = next(
            (w for w in state["workers"] if w["name"] == "test-kill-basic"),
            None
        )
        self.assertIsNotNone(worker, "worker should still be in state")
        self.assertEqual(worker["status"], "stopped", "worker should be stopped")

        # Verify process is actually dead
        time.sleep(0.5)  # Give it time to die
        try:
            os.kill(pid, 0)
            self.fail("Process should be dead")
        except ProcessLookupError:
            # Process is dead, this is expected
            pass

    def test_kill_nonexistent_worker(self):
        """Test killing a worker that doesn't exist."""
        result = run_swarm(
            "kill", "nonexistent-worker-xyz",
            env=self.env, check=False
        )
        self.assertNotEqual(result.returncode, 0, "should fail for nonexistent worker")
        self.assertIn("not found", result.stderr.lower(), "should indicate worker not found")

    def test_kill_without_name_or_all(self):
        """Test kill without specifying name or --all."""
        result = run_swarm("kill", env=self.env, check=False)
        self.assertNotEqual(result.returncode, 0, "should fail without name or --all")
        self.assertTrue(
            "must specify" in result.stderr.lower() or "required" in result.stderr.lower(),
            f"should indicate name is required, got stderr: {result.stderr}"
        )


if __name__ == "__main__":
    unittest.main()
