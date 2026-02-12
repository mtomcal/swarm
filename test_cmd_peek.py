#!/usr/bin/env python3
"""Unit tests for cmd_peek function."""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch, call
from io import StringIO

# Import from swarm
import swarm


class TestCmdPeek(unittest.TestCase):
    """Test the cmd_peek function."""

    def setUp(self):
        """Set up test fixtures."""
        # Create temporary directory for state
        self.temp_dir = tempfile.mkdtemp()
        self.state_file = Path(self.temp_dir) / "state.json"
        self.logs_dir = Path(self.temp_dir) / "logs"
        self.logs_dir.mkdir(exist_ok=True)

        # Patch SWARM_DIR, STATE_FILE, and STATE_LOCK_FILE
        self.swarm_dir_patch = patch.object(swarm, 'SWARM_DIR', Path(self.temp_dir))
        self.state_file_patch = patch.object(swarm, 'STATE_FILE', self.state_file)
        self.state_lock_file_patch = patch.object(swarm, 'STATE_LOCK_FILE', Path(self.temp_dir) / "state.lock")
        self.logs_dir_patch = patch.object(swarm, 'LOGS_DIR', self.logs_dir)

        self.swarm_dir_patch.start()
        self.state_file_patch.start()
        self.state_lock_file_patch.start()
        self.logs_dir_patch.start()

    def tearDown(self):
        """Clean up test fixtures."""
        self.swarm_dir_patch.stop()
        self.state_file_patch.stop()
        self.state_lock_file_patch.stop()
        self.logs_dir_patch.stop()

    def create_test_state(self, workers):
        """Helper to create test state file."""
        state_data = {"workers": [w.to_dict() for w in workers]}
        with open(self.state_file, 'w') as f:
            json.dump(state_data, f)

    def test_basic_peek_returns_captured_content(self):
        """Test basic peek returns captured content."""
        worker = swarm.Worker(
            name="dev",
            status="running",
            cmd=["claude"],
            started="2026-01-10T12:00:00",
            cwd="/tmp",
            tmux=swarm.TmuxInfo(session="swarm", window="dev")
        )
        self.create_test_state([worker])

        args = MagicMock()
        args.name = "dev"
        args.lines = 30
        args.all = False

        with patch.object(swarm, 'tmux_window_exists', return_value=True), \
             patch.object(swarm, 'tmux_capture_pane', return_value="hello world\n") as mock_capture, \
             patch('sys.stdout', new_callable=StringIO) as mock_stdout:

            with self.assertRaises(SystemExit) as cm:
                swarm.cmd_peek(args)
            self.assertEqual(cm.exception.code, 0)

            mock_capture.assert_called_once_with("swarm", "dev", history_lines=30, socket=None)
            self.assertEqual(mock_stdout.getvalue(), "hello world\n")

    def test_all_shows_headers_for_multiple_workers(self):
        """Test --all shows headers for multiple workers."""
        workers = [
            swarm.Worker(
                name="w1",
                status="running",
                cmd=["claude"],
                started="2026-01-10T12:00:00",
                cwd="/tmp",
                tmux=swarm.TmuxInfo(session="swarm", window="w1")
            ),
            swarm.Worker(
                name="w2",
                status="running",
                cmd=["claude"],
                started="2026-01-10T12:00:00",
                cwd="/tmp",
                tmux=swarm.TmuxInfo(session="swarm", window="w2")
            ),
        ]
        self.create_test_state(workers)

        args = MagicMock()
        args.name = None
        args.lines = 30
        args.all = True

        def capture_side_effect(session, window, history_lines=0, socket=None):
            return f"output from {window}\n"

        with patch.object(swarm, 'tmux_window_exists', return_value=True), \
             patch.object(swarm, 'tmux_capture_pane', side_effect=capture_side_effect), \
             patch('sys.stdout', new_callable=StringIO) as mock_stdout:

            with self.assertRaises(SystemExit) as cm:
                swarm.cmd_peek(args)
            self.assertEqual(cm.exception.code, 0)

            output = mock_stdout.getvalue()
            self.assertIn("=== w1 ===", output)
            self.assertIn("=== w2 ===", output)
            self.assertIn("output from w1", output)
            self.assertIn("output from w2", output)

    def test_all_with_n_applies_per_worker(self):
        """Test --all with -n applies the line count per worker."""
        worker = swarm.Worker(
            name="w1",
            status="running",
            cmd=["claude"],
            started="2026-01-10T12:00:00",
            cwd="/tmp",
            tmux=swarm.TmuxInfo(session="swarm", window="w1")
        )
        self.create_test_state([worker])

        args = MagicMock()
        args.name = None
        args.lines = 100
        args.all = True

        with patch.object(swarm, 'tmux_window_exists', return_value=True), \
             patch.object(swarm, 'tmux_capture_pane', return_value="content\n") as mock_capture, \
             patch('sys.stdout', new_callable=StringIO):

            with self.assertRaises(SystemExit) as cm:
                swarm.cmd_peek(args)
            self.assertEqual(cm.exception.code, 0)

            mock_capture.assert_called_once_with("swarm", "w1", history_lines=100, socket=None)

    def test_nonexistent_worker_exits_2(self):
        """Test non-existent worker → exit 2."""
        self.create_test_state([])

        args = MagicMock()
        args.name = "ghost"
        args.lines = 30
        args.all = False

        with patch('sys.stderr', new_callable=StringIO) as mock_stderr:
            with self.assertRaises(SystemExit) as cm:
                swarm.cmd_peek(args)
            self.assertEqual(cm.exception.code, 2)
            self.assertIn("worker 'ghost' not found", mock_stderr.getvalue())

    def test_non_tmux_worker_exits_1(self):
        """Test non-tmux worker → exit 1."""
        worker = swarm.Worker(
            name="bg-job",
            status="running",
            cmd=["python", "script.py"],
            started="2026-01-10T12:00:00",
            cwd="/tmp",
            pid=12345
        )
        self.create_test_state([worker])

        args = MagicMock()
        args.name = "bg-job"
        args.lines = 30
        args.all = False

        with patch('sys.stderr', new_callable=StringIO) as mock_stderr:
            with self.assertRaises(SystemExit) as cm:
                swarm.cmd_peek(args)
            self.assertEqual(cm.exception.code, 1)
            self.assertIn("is not a tmux worker", mock_stderr.getvalue())

    def test_stopped_tmux_worker_exits_1(self):
        """Test stopped tmux worker → exit 1."""
        worker = swarm.Worker(
            name="old",
            status="stopped",
            cmd=["claude"],
            started="2026-01-10T12:00:00",
            cwd="/tmp",
            tmux=swarm.TmuxInfo(session="swarm", window="old")
        )
        self.create_test_state([worker])

        args = MagicMock()
        args.name = "old"
        args.lines = 30
        args.all = False

        with patch.object(swarm, 'tmux_window_exists', return_value=False), \
             patch('sys.stderr', new_callable=StringIO) as mock_stderr:

            with self.assertRaises(SystemExit) as cm:
                swarm.cmd_peek(args)
            self.assertEqual(cm.exception.code, 1)
            self.assertIn("is not running", mock_stderr.getvalue())

    def test_capture_failure_exits_1(self):
        """Test capture failure → exit 1."""
        worker = swarm.Worker(
            name="dev",
            status="running",
            cmd=["claude"],
            started="2026-01-10T12:00:00",
            cwd="/tmp",
            tmux=swarm.TmuxInfo(session="swarm", window="dev")
        )
        self.create_test_state([worker])

        args = MagicMock()
        args.name = "dev"
        args.lines = 30
        args.all = False

        with patch.object(swarm, 'tmux_window_exists', return_value=True), \
             patch.object(swarm, 'tmux_capture_pane', side_effect=Exception("tmux error")), \
             patch('sys.stderr', new_callable=StringIO) as mock_stderr:

            with self.assertRaises(SystemExit) as cm:
                swarm.cmd_peek(args)
            self.assertEqual(cm.exception.code, 1)
            self.assertIn("failed to capture pane", mock_stderr.getvalue())
            self.assertIn("tmux error", mock_stderr.getvalue())

    def test_empty_pane_exits_0(self):
        """Test empty pane → exit 0, empty output."""
        worker = swarm.Worker(
            name="dev",
            status="running",
            cmd=["claude"],
            started="2026-01-10T12:00:00",
            cwd="/tmp",
            tmux=swarm.TmuxInfo(session="swarm", window="dev")
        )
        self.create_test_state([worker])

        args = MagicMock()
        args.name = "dev"
        args.lines = 30
        args.all = False

        with patch.object(swarm, 'tmux_window_exists', return_value=True), \
             patch.object(swarm, 'tmux_capture_pane', return_value=""), \
             patch('sys.stdout', new_callable=StringIO) as mock_stdout:

            with self.assertRaises(SystemExit) as cm:
                swarm.cmd_peek(args)
            self.assertEqual(cm.exception.code, 0)
            self.assertEqual(mock_stdout.getvalue(), "")

    def test_all_with_no_running_workers_exits_0(self):
        """Test --all with no running workers → exit 0."""
        # Worker with no tmux
        worker = swarm.Worker(
            name="bg-job",
            status="running",
            cmd=["python", "script.py"],
            started="2026-01-10T12:00:00",
            cwd="/tmp",
            pid=12345
        )
        self.create_test_state([worker])

        args = MagicMock()
        args.name = None
        args.lines = 30
        args.all = True

        with patch('sys.stdout', new_callable=StringIO) as mock_stdout:
            with self.assertRaises(SystemExit) as cm:
                swarm.cmd_peek(args)
            self.assertEqual(cm.exception.code, 0)
            self.assertEqual(mock_stdout.getvalue(), "")

    def test_all_skips_dead_tmux_windows(self):
        """Test --all skips workers whose tmux window no longer exists."""
        workers = [
            swarm.Worker(
                name="alive",
                status="running",
                cmd=["claude"],
                started="2026-01-10T12:00:00",
                cwd="/tmp",
                tmux=swarm.TmuxInfo(session="swarm", window="alive")
            ),
            swarm.Worker(
                name="dead",
                status="running",
                cmd=["claude"],
                started="2026-01-10T12:00:00",
                cwd="/tmp",
                tmux=swarm.TmuxInfo(session="swarm", window="dead")
            ),
        ]
        self.create_test_state(workers)

        args = MagicMock()
        args.name = None
        args.lines = 30
        args.all = True

        def exists_side_effect(session, window, socket=None):
            return window == "alive"

        with patch.object(swarm, 'tmux_window_exists', side_effect=exists_side_effect), \
             patch.object(swarm, 'tmux_capture_pane', return_value="content\n"), \
             patch('sys.stdout', new_callable=StringIO) as mock_stdout:

            with self.assertRaises(SystemExit) as cm:
                swarm.cmd_peek(args)
            self.assertEqual(cm.exception.code, 0)

            output = mock_stdout.getvalue()
            self.assertIn("=== alive ===", output)
            self.assertNotIn("=== dead ===", output)

    def test_peek_with_socket(self):
        """Test peek uses correct socket when worker has one."""
        worker = swarm.Worker(
            name="dev",
            status="running",
            cmd=["claude"],
            started="2026-01-10T12:00:00",
            cwd="/tmp",
            tmux=swarm.TmuxInfo(session="swarm", window="dev", socket="my-socket")
        )
        self.create_test_state([worker])

        args = MagicMock()
        args.name = "dev"
        args.lines = 30
        args.all = False

        with patch.object(swarm, 'tmux_window_exists', return_value=True) as mock_exists, \
             patch.object(swarm, 'tmux_capture_pane', return_value="content\n") as mock_capture, \
             patch('sys.stdout', new_callable=StringIO):

            with self.assertRaises(SystemExit) as cm:
                swarm.cmd_peek(args)
            self.assertEqual(cm.exception.code, 0)

            mock_exists.assert_called_once_with("swarm", "dev", socket="my-socket")
            mock_capture.assert_called_once_with("swarm", "dev", history_lines=30, socket="my-socket")


if __name__ == '__main__':
    unittest.main()
