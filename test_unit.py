#!/usr/bin/env python3
"""Unit tests for swarm.py"""

import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

# Import the module under test
import swarm


class TestRelativeTime(unittest.TestCase):
    """Test the relative_time helper function."""

    def test_seconds(self):
        """Test formatting for seconds."""
        now = datetime.now()
        past = now - timedelta(seconds=30)
        result = swarm.relative_time(past.isoformat())
        self.assertEqual(result, "30s")

    def test_minutes(self):
        """Test formatting for minutes."""
        now = datetime.now()
        past = now - timedelta(minutes=5, seconds=30)
        result = swarm.relative_time(past.isoformat())
        self.assertEqual(result, "5m")

    def test_hours(self):
        """Test formatting for hours."""
        now = datetime.now()
        past = now - timedelta(hours=2, minutes=30)
        result = swarm.relative_time(past.isoformat())
        self.assertEqual(result, "2h")

    def test_days(self):
        """Test formatting for days."""
        now = datetime.now()
        past = now - timedelta(days=3, hours=12)
        result = swarm.relative_time(past.isoformat())
        self.assertEqual(result, "3d")

    def test_zero_seconds(self):
        """Test formatting for zero elapsed time."""
        now = datetime.now()
        result = swarm.relative_time(now.isoformat())
        self.assertEqual(result, "0s")


class TestCmdStatus(unittest.TestCase):
    """Test the cmd_status command."""

    def setUp(self):
        """Set up test fixtures."""
        # Create a temporary directory for test state
        self.test_dir = tempfile.mkdtemp()
        self.state_file = Path(self.test_dir) / "state.json"

        # Patch the STATE_FILE and SWARM_DIR constants
        self.patcher_state = patch.object(swarm, 'STATE_FILE', self.state_file)
        self.patcher_dir = patch.object(swarm, 'SWARM_DIR', Path(self.test_dir))
        self.patcher_state.start()
        self.patcher_dir.start()

    def tearDown(self):
        """Clean up test fixtures."""
        self.patcher_state.stop()
        self.patcher_dir.stop()
        # Clean up temporary directory
        import shutil
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def _create_state(self, workers):
        """Helper to create a state file with given workers."""
        Path(self.test_dir).mkdir(parents=True, exist_ok=True)
        data = {"workers": [w.to_dict() for w in workers]}
        with open(self.state_file, "w") as f:
            json.dump(data, f)

    @patch('swarm.refresh_worker_status')
    @patch('sys.stdout')
    def test_status_tmux_worker_running(self, mock_stdout, mock_refresh):
        """Test status for a running tmux worker with worktree."""
        # Create a mock worker
        started = (datetime.now() - timedelta(minutes=5)).isoformat()
        worker = swarm.Worker(
            name="w1",
            status="running",
            cmd=["claude"],
            started=started,
            cwd="/home/user/code/myrepo",
            tmux=swarm.TmuxInfo(session="swarm", window="w1"),
            worktree=swarm.WorktreeInfo(
                path="/home/user/code/swarm-worktrees/w1",
                branch="work/task-1",
                base_repo="/home/user/code/myrepo"
            )
        )
        self._create_state([worker])

        # Mock refresh to return running
        mock_refresh.return_value = "running"

        # Create args
        args = MagicMock()
        args.name = "w1"

        # Call cmd_status and expect exit code 0
        with self.assertRaises(SystemExit) as cm:
            swarm.cmd_status(args)
        self.assertEqual(cm.exception.code, 0)

        # Verify output format
        mock_stdout.write.assert_called()
        output = ''.join(call[0][0] for call in mock_stdout.write.call_args_list)
        self.assertIn("w1: running", output)
        self.assertIn("tmux window swarm:w1", output)
        self.assertIn("worktree /home/user/code/swarm-worktrees/w1", output)
        self.assertIn("uptime 5m", output)

    @patch('swarm.refresh_worker_status')
    @patch('sys.stdout')
    def test_status_pid_worker_running(self, mock_stdout, mock_refresh):
        """Test status for a running non-tmux worker with PID."""
        # Create a mock worker
        started = (datetime.now() - timedelta(hours=2)).isoformat()
        worker = swarm.Worker(
            name="w2",
            status="running",
            cmd=["python", "agent.py"],
            started=started,
            cwd="/home/user/code/myrepo",
            pid=12345
        )
        self._create_state([worker])

        # Mock refresh to return running
        mock_refresh.return_value = "running"

        # Create args
        args = MagicMock()
        args.name = "w2"

        # Call cmd_status and expect exit code 0
        with self.assertRaises(SystemExit) as cm:
            swarm.cmd_status(args)
        self.assertEqual(cm.exception.code, 0)

        # Verify output format
        mock_stdout.write.assert_called()
        output = ''.join(call[0][0] for call in mock_stdout.write.call_args_list)
        self.assertIn("w2: running", output)
        self.assertIn("pid 12345", output)
        self.assertIn("uptime 2h", output)

    @patch('swarm.refresh_worker_status')
    @patch('sys.stdout')
    def test_status_worker_stopped(self, mock_stdout, mock_refresh):
        """Test status for a stopped worker."""
        # Create a mock worker
        started = (datetime.now() - timedelta(days=1)).isoformat()
        worker = swarm.Worker(
            name="w3",
            status="running",  # Initially running
            cmd=["bash"],
            started=started,
            cwd="/home/user/code/myrepo",
            tmux=swarm.TmuxInfo(session="swarm", window="w3")
        )
        self._create_state([worker])

        # Mock refresh to return stopped
        mock_refresh.return_value = "stopped"

        # Create args
        args = MagicMock()
        args.name = "w3"

        # Call cmd_status and expect exit code 1
        with self.assertRaises(SystemExit) as cm:
            swarm.cmd_status(args)
        self.assertEqual(cm.exception.code, 1)

        # Verify output format
        mock_stdout.write.assert_called()
        output = ''.join(call[0][0] for call in mock_stdout.write.call_args_list)
        self.assertIn("w3: stopped", output)
        self.assertIn("uptime 1d", output)

    @patch('sys.stderr')
    def test_status_worker_not_found(self, mock_stderr):
        """Test status for a non-existent worker."""
        # Create empty state
        self._create_state([])

        # Create args
        args = MagicMock()
        args.name = "nonexistent"

        # Call cmd_status and expect exit code 2
        with self.assertRaises(SystemExit) as cm:
            swarm.cmd_status(args)
        self.assertEqual(cm.exception.code, 2)

        # Verify error message
        mock_stderr.write.assert_called()
        output = ''.join(call[0][0] for call in mock_stderr.write.call_args_list)
        self.assertIn("swarm: error: worker 'nonexistent' not found", output)

    @patch('swarm.refresh_worker_status')
    @patch('sys.stdout')
    def test_status_tmux_worker_no_worktree(self, mock_stdout, mock_refresh):
        """Test status for a tmux worker without worktree."""
        # Create a mock worker
        started = (datetime.now() - timedelta(seconds=45)).isoformat()
        worker = swarm.Worker(
            name="w4",
            status="running",
            cmd=["bash"],
            started=started,
            cwd="/home/user/code/myrepo",
            tmux=swarm.TmuxInfo(session="swarm", window="w4")
        )
        self._create_state([worker])

        # Mock refresh to return running
        mock_refresh.return_value = "running"

        # Create args
        args = MagicMock()
        args.name = "w4"

        # Call cmd_status and expect exit code 0
        with self.assertRaises(SystemExit) as cm:
            swarm.cmd_status(args)
        self.assertEqual(cm.exception.code, 0)

        # Verify output format
        mock_stdout.write.assert_called()
        output = ''.join(call[0][0] for call in mock_stdout.write.call_args_list)
        self.assertIn("w4: running", output)
        self.assertIn("tmux window swarm:w4", output)
        self.assertNotIn("worktree", output)
        self.assertIn("uptime 45s", output)


if __name__ == "__main__":
    unittest.main()
