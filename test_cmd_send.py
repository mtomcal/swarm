#!/usr/bin/env python3
"""Unit tests for cmd_send function."""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
from io import StringIO

# Import from swarm
import swarm


class TestCmdSend(unittest.TestCase):
    """Test the cmd_send function."""

    def setUp(self):
        """Set up test fixtures."""
        # Create temporary directory for state
        self.temp_dir = tempfile.mkdtemp()
        self.state_file = Path(self.temp_dir) / "state.json"
        self.state_lock_file = Path(self.temp_dir) / "state.lock"
        self.logs_dir = Path(self.temp_dir) / "logs"
        self.logs_dir.mkdir(exist_ok=True)

        # Patch SWARM_DIR, STATE_FILE, and STATE_LOCK_FILE
        self.swarm_dir_patch = patch.object(swarm, 'SWARM_DIR', Path(self.temp_dir))
        self.state_file_patch = patch.object(swarm, 'STATE_FILE', self.state_file)
        self.state_lock_file_patch = patch.object(swarm, 'STATE_LOCK_FILE', self.state_lock_file)
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

    def test_send_to_single_tmux_worker(self):
        """Test sending text to a single tmux worker."""
        # Create a running tmux worker
        worker = swarm.Worker(
            name="w1",
            status="running",
            cmd=["echo", "test"],
            started="2026-01-10T12:00:00",
            cwd="/tmp",
            tmux=swarm.TmuxInfo(session="swarm", window="w1")
        )
        self.create_test_state([worker])

        # Mock args
        args = MagicMock()
        args.name = "w1"
        args.text = "hello world"
        args.no_enter = False
        args.all = False
        args.raw = False

        # Mock tmux_send and refresh_worker_status
        with patch.object(swarm, 'tmux_send') as mock_send, \
             patch.object(swarm, 'refresh_worker_status', return_value="running") as mock_refresh, \
             patch('sys.stdout', new_callable=StringIO) as mock_stdout:

            swarm.cmd_send(args)

            # Verify tmux_send was called correctly
            mock_send.assert_called_once_with("swarm", "w1", "hello world", enter=True, socket=None, pre_clear=True)
            mock_refresh.assert_called_once()

            # Verify output
            self.assertIn("sent to w1", mock_stdout.getvalue())

    def test_send_with_no_enter_flag(self):
        """Test sending text with --no-enter flag."""
        worker = swarm.Worker(
            name="w1",
            status="running",
            cmd=["echo", "test"],
            started="2026-01-10T12:00:00",
            cwd="/tmp",
            tmux=swarm.TmuxInfo(session="swarm", window="w1")
        )
        self.create_test_state([worker])

        args = MagicMock()
        args.name = "w1"
        args.text = "hello world"
        args.no_enter = True
        args.all = False
        args.raw = False

        with patch.object(swarm, 'tmux_send') as mock_send, \
             patch.object(swarm, 'refresh_worker_status', return_value="running"):

            swarm.cmd_send(args)

            # Verify enter=False was passed
            mock_send.assert_called_once_with("swarm", "w1", "hello world", enter=False, socket=None, pre_clear=True)

    def test_send_to_all_tmux_workers(self):
        """Test sending text to all running tmux workers."""
        workers = [
            swarm.Worker(
                name="w1",
                status="running",
                cmd=["echo", "test"],
                started="2026-01-10T12:00:00",
                cwd="/tmp",
                tmux=swarm.TmuxInfo(session="swarm", window="w1")
            ),
            swarm.Worker(
                name="w2",
                status="running",
                cmd=["echo", "test"],
                started="2026-01-10T12:00:00",
                cwd="/tmp",
                tmux=swarm.TmuxInfo(session="swarm", window="w2")
            ),
            swarm.Worker(
                name="w3",
                status="stopped",
                cmd=["echo", "test"],
                started="2026-01-10T12:00:00",
                cwd="/tmp",
                tmux=swarm.TmuxInfo(session="swarm", window="w3")
            ),
            swarm.Worker(
                name="w4",
                status="running",
                cmd=["echo", "test"],
                started="2026-01-10T12:00:00",
                cwd="/tmp",
                pid=12345  # Not a tmux worker
            ),
        ]
        self.create_test_state(workers)

        args = MagicMock()
        args.name = None
        args.text = "hello all"
        args.no_enter = False
        args.all = True
        args.raw = False

        def mock_refresh(worker):
            # Return "stopped" for w3, "running" for others
            if worker.name == "w3":
                return "stopped"
            return "running"

        with patch.object(swarm, 'tmux_send') as mock_send, \
             patch.object(swarm, 'refresh_worker_status', side_effect=mock_refresh) as mock_refresh_fn, \
             patch('sys.stdout', new_callable=StringIO) as mock_stdout:

            swarm.cmd_send(args)

            # Should send to w1 and w2 only (w3 is skipped because stopped, w4 is not tmux)
            self.assertEqual(mock_send.call_count, 2)
            mock_send.assert_any_call("swarm", "w1", "hello all", enter=True, socket=None, pre_clear=True)
            mock_send.assert_any_call("swarm", "w2", "hello all", enter=True, socket=None, pre_clear=True)

            output = mock_stdout.getvalue()
            self.assertIn("sent to w1", output)
            self.assertIn("sent to w2", output)

    def test_send_worker_not_found(self):
        """Test error when worker is not found."""
        self.create_test_state([])

        args = MagicMock()
        args.name = "nonexistent"
        args.text = "hello"
        args.no_enter = False
        args.all = False

        with patch('sys.stderr', new_callable=StringIO) as mock_stderr, \
             self.assertRaises(SystemExit) as cm:
            swarm.cmd_send(args)

        self.assertEqual(cm.exception.code, 1)
        self.assertIn("worker 'nonexistent' not found", mock_stderr.getvalue())

    def test_send_worker_not_tmux(self):
        """Test error when worker is not a tmux worker."""
        worker = swarm.Worker(
            name="w1",
            status="running",
            cmd=["echo", "test"],
            started="2026-01-10T12:00:00",
            cwd="/tmp",
            pid=12345  # Not tmux
        )
        self.create_test_state([worker])

        args = MagicMock()
        args.name = "w1"
        args.text = "hello"
        args.no_enter = False
        args.all = False

        with patch('sys.stderr', new_callable=StringIO) as mock_stderr, \
             self.assertRaises(SystemExit) as cm:
            swarm.cmd_send(args)

        self.assertEqual(cm.exception.code, 1)
        self.assertIn("worker 'w1' is not a tmux worker", mock_stderr.getvalue())

    def test_send_worker_not_running(self):
        """Test error when worker is not running."""
        worker = swarm.Worker(
            name="w1",
            status="running",
            cmd=["echo", "test"],
            started="2026-01-10T12:00:00",
            cwd="/tmp",
            tmux=swarm.TmuxInfo(session="swarm", window="w1")
        )
        self.create_test_state([worker])

        args = MagicMock()
        args.name = "w1"
        args.text = "hello"
        args.no_enter = False
        args.all = False

        # Mock refresh_worker_status to return stopped
        with patch.object(swarm, 'refresh_worker_status', return_value="stopped"), \
             patch('sys.stderr', new_callable=StringIO) as mock_stderr, \
             self.assertRaises(SystemExit) as cm:
            swarm.cmd_send(args)

        self.assertEqual(cm.exception.code, 1)
        self.assertIn("worker 'w1' is not running", mock_stderr.getvalue())


    def test_send_without_name_or_all_flag(self):
        """Test error when neither name nor --all is specified."""
        self.create_test_state([])

        args = MagicMock()
        args.name = None
        args.text = "hello"
        args.no_enter = False
        args.all = False

        with patch('sys.stderr', new_callable=StringIO) as mock_stderr, \
             self.assertRaises(SystemExit) as cm:
            swarm.cmd_send(args)

        self.assertEqual(cm.exception.code, 1)
        self.assertIn("--name required", mock_stderr.getvalue())

    def test_send_with_raw_flag_skips_pre_clear(self):
        """Test --raw flag disables pre-clear sequence."""
        worker = swarm.Worker(
            name="w1",
            status="running",
            cmd=["echo", "test"],
            started="2026-01-10T12:00:00",
            cwd="/tmp",
            tmux=swarm.TmuxInfo(session="swarm", window="w1")
        )
        self.create_test_state([worker])

        args = MagicMock()
        args.name = "w1"
        args.text = "hello world"
        args.no_enter = False
        args.all = False
        args.raw = True

        with patch.object(swarm, 'tmux_send') as mock_send, \
             patch.object(swarm, 'refresh_worker_status', return_value="running"):

            swarm.cmd_send(args)

            # Verify pre_clear=False was passed when --raw is set
            mock_send.assert_called_once_with("swarm", "w1", "hello world", enter=True, socket=None, pre_clear=False)

    def test_send_default_uses_pre_clear(self):
        """Test default send (no --raw) uses pre-clear."""
        worker = swarm.Worker(
            name="w1",
            status="running",
            cmd=["echo", "test"],
            started="2026-01-10T12:00:00",
            cwd="/tmp",
            tmux=swarm.TmuxInfo(session="swarm", window="w1")
        )
        self.create_test_state([worker])

        args = MagicMock()
        args.name = "w1"
        args.text = "hello"
        args.no_enter = False
        args.all = False
        args.raw = False

        with patch.object(swarm, 'tmux_send') as mock_send, \
             patch.object(swarm, 'refresh_worker_status', return_value="running"):

            swarm.cmd_send(args)

            # Verify pre_clear=True was passed when --raw is not set
            mock_send.assert_called_once_with("swarm", "w1", "hello", enter=True, socket=None, pre_clear=True)


if __name__ == '__main__':
    unittest.main()
