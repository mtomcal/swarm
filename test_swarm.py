#!/usr/bin/env python3
"""Tests for swarm.py - focusing on cmd_interrupt and cmd_eof."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest.mock import MagicMock, Mock, call, patch

# Import the module under test
import swarm


class TestCmdInterrupt(unittest.TestCase):
    """Test cmd_interrupt function."""

    def setUp(self):
        """Set up test fixtures."""
        # Create temporary swarm directory
        self.temp_dir = tempfile.mkdtemp()
        self.swarm_dir = Path(self.temp_dir) / ".swarm"
        self.state_file = self.swarm_dir / "state.json"

        # Patch constants
        self.patcher_swarm_dir = patch.object(swarm, 'SWARM_DIR', self.swarm_dir)
        self.patcher_state_file = patch.object(swarm, 'STATE_FILE', self.state_file)
        self.patcher_swarm_dir.start()
        self.patcher_state_file.start()

        # Create swarm directory
        self.swarm_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        """Clean up test fixtures."""
        self.patcher_swarm_dir.stop()
        self.patcher_state_file.stop()
        # Clean up temp directory
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _create_test_state(self, workers):
        """Helper to create a test state file."""
        state_data = {
            "workers": [w.to_dict() for w in workers]
        }
        with open(self.state_file, "w") as f:
            json.dump(state_data, f)

    def test_interrupt_single_worker_success(self):
        """Test interrupting a single running tmux worker."""
        # Create a test worker
        worker = swarm.Worker(
            name="test-worker",
            status="running",
            cmd=["echo", "test"],
            started="2026-01-10T00:00:00",
            cwd="/tmp",
            tmux=swarm.TmuxInfo(session="swarm", window="test-worker")
        )
        self._create_test_state([worker])

        # Mock subprocess.run
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = Mock(returncode=0)

            # Mock refresh_worker_status to return "running"
            with patch.object(swarm, 'refresh_worker_status', return_value="running"):
                # Call cmd_interrupt
                args = Namespace(name="test-worker", all=False)

                with patch('builtins.print') as mock_print:
                    swarm.cmd_interrupt(args)

                # Verify tmux send-keys was called correctly
                mock_run.assert_called_once_with(
                    ["tmux", "send-keys", "-t", "swarm:test-worker", "C-c"],
                    capture_output=True
                )

                # Verify output
                mock_print.assert_called_once_with("interrupted test-worker")

    def test_interrupt_worker_not_found(self):
        """Test interrupt with non-existent worker."""
        self._create_test_state([])

        args = Namespace(name="nonexistent", all=False)

        with patch('sys.stderr'):
            with self.assertRaises(SystemExit) as cm:
                swarm.cmd_interrupt(args)
            self.assertEqual(cm.exception.code, 1)

    def test_interrupt_worker_not_tmux(self):
        """Test interrupt with non-tmux worker."""
        # Create a worker without tmux
        worker = swarm.Worker(
            name="pid-worker",
            status="running",
            cmd=["echo", "test"],
            started="2026-01-10T00:00:00",
            cwd="/tmp",
            pid=12345
        )
        self._create_test_state([worker])

        args = Namespace(name="pid-worker", all=False)

        with patch('sys.stderr'):
            with self.assertRaises(SystemExit) as cm:
                swarm.cmd_interrupt(args)
            self.assertEqual(cm.exception.code, 1)

    def test_interrupt_worker_not_running(self):
        """Test interrupt with stopped worker."""
        worker = swarm.Worker(
            name="stopped-worker",
            status="stopped",
            cmd=["echo", "test"],
            started="2026-01-10T00:00:00",
            cwd="/tmp",
            tmux=swarm.TmuxInfo(session="swarm", window="stopped-worker")
        )
        self._create_test_state([worker])

        # Mock refresh to return "stopped"
        with patch.object(swarm, 'refresh_worker_status', return_value="stopped"):
            args = Namespace(name="stopped-worker", all=False)

            with patch('sys.stderr'):
                with self.assertRaises(SystemExit) as cm:
                    swarm.cmd_interrupt(args)
                self.assertEqual(cm.exception.code, 1)

    def test_interrupt_all_workers(self):
        """Test interrupt with --all flag."""
        # Create multiple workers
        workers = [
            swarm.Worker(
                name="worker-1",
                status="running",
                cmd=["echo", "1"],
                started="2026-01-10T00:00:00",
                cwd="/tmp",
                tmux=swarm.TmuxInfo(session="swarm", window="worker-1")
            ),
            swarm.Worker(
                name="worker-2",
                status="running",
                cmd=["echo", "2"],
                started="2026-01-10T00:00:00",
                cwd="/tmp",
                tmux=swarm.TmuxInfo(session="swarm", window="worker-2")
            ),
            swarm.Worker(
                name="worker-3",
                status="stopped",
                cmd=["echo", "3"],
                started="2026-01-10T00:00:00",
                cwd="/tmp",
                tmux=swarm.TmuxInfo(session="swarm", window="worker-3")
            ),
        ]
        self._create_test_state(workers)

        with patch('subprocess.run') as mock_run:
            mock_run.return_value = Mock(returncode=0)

            # Mock refresh to return running for first two, stopped for third
            def mock_refresh(w):
                return "running" if w.name in ["worker-1", "worker-2"] else "stopped"

            with patch.object(swarm, 'refresh_worker_status', side_effect=mock_refresh):
                args = Namespace(name=None, all=True)

                with patch('builtins.print') as mock_print:
                    swarm.cmd_interrupt(args)

                # Should only interrupt running workers
                self.assertEqual(mock_run.call_count, 2)
                mock_run.assert_any_call(
                    ["tmux", "send-keys", "-t", "swarm:worker-1", "C-c"],
                    capture_output=True
                )
                mock_run.assert_any_call(
                    ["tmux", "send-keys", "-t", "swarm:worker-2", "C-c"],
                    capture_output=True
                )

                # Verify output
                self.assertEqual(mock_print.call_count, 2)


class TestCmdEof(unittest.TestCase):
    """Test cmd_eof function."""

    def setUp(self):
        """Set up test fixtures."""
        # Create temporary swarm directory
        self.temp_dir = tempfile.mkdtemp()
        self.swarm_dir = Path(self.temp_dir) / ".swarm"
        self.state_file = self.swarm_dir / "state.json"

        # Patch constants
        self.patcher_swarm_dir = patch.object(swarm, 'SWARM_DIR', self.swarm_dir)
        self.patcher_state_file = patch.object(swarm, 'STATE_FILE', self.state_file)
        self.patcher_swarm_dir.start()
        self.patcher_state_file.start()

        # Create swarm directory
        self.swarm_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        """Clean up test fixtures."""
        self.patcher_swarm_dir.stop()
        self.patcher_state_file.stop()
        # Clean up temp directory
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _create_test_state(self, workers):
        """Helper to create a test state file."""
        state_data = {
            "workers": [w.to_dict() for w in workers]
        }
        with open(self.state_file, "w") as f:
            json.dump(state_data, f)

    def test_eof_single_worker_success(self):
        """Test sending EOF to a single running tmux worker."""
        worker = swarm.Worker(
            name="test-worker",
            status="running",
            cmd=["echo", "test"],
            started="2026-01-10T00:00:00",
            cwd="/tmp",
            tmux=swarm.TmuxInfo(session="swarm", window="test-worker")
        )
        self._create_test_state([worker])

        with patch('subprocess.run') as mock_run:
            mock_run.return_value = Mock(returncode=0)

            with patch.object(swarm, 'refresh_worker_status', return_value="running"):
                args = Namespace(name="test-worker")

                with patch('builtins.print') as mock_print:
                    swarm.cmd_eof(args)

                # Verify tmux send-keys was called correctly
                mock_run.assert_called_once_with(
                    ["tmux", "send-keys", "-t", "swarm:test-worker", "C-d"],
                    capture_output=True
                )

                # Verify output
                mock_print.assert_called_once_with("sent eof to test-worker")

    def test_eof_worker_not_found(self):
        """Test eof with non-existent worker."""
        self._create_test_state([])

        args = Namespace(name="nonexistent")

        with patch('sys.stderr'):
            with self.assertRaises(SystemExit) as cm:
                swarm.cmd_eof(args)
            self.assertEqual(cm.exception.code, 1)

    def test_eof_worker_not_tmux(self):
        """Test eof with non-tmux worker."""
        worker = swarm.Worker(
            name="pid-worker",
            status="running",
            cmd=["echo", "test"],
            started="2026-01-10T00:00:00",
            cwd="/tmp",
            pid=12345
        )
        self._create_test_state([worker])

        args = Namespace(name="pid-worker")

        with patch('sys.stderr'):
            with self.assertRaises(SystemExit) as cm:
                swarm.cmd_eof(args)
            self.assertEqual(cm.exception.code, 1)

    def test_eof_worker_not_running(self):
        """Test eof with stopped worker."""
        worker = swarm.Worker(
            name="stopped-worker",
            status="stopped",
            cmd=["echo", "test"],
            started="2026-01-10T00:00:00",
            cwd="/tmp",
            tmux=swarm.TmuxInfo(session="swarm", window="stopped-worker")
        )
        self._create_test_state([worker])

        with patch.object(swarm, 'refresh_worker_status', return_value="stopped"):
            args = Namespace(name="stopped-worker")

            with patch('sys.stderr'):
                with self.assertRaises(SystemExit) as cm:
                    swarm.cmd_eof(args)
                self.assertEqual(cm.exception.code, 1)


class TestCmdAttach(unittest.TestCase):
    """Test cmd_attach function."""

    def setUp(self):
        """Set up test fixtures."""
        # Create temporary swarm directory
        self.temp_dir = tempfile.mkdtemp()
        self.swarm_dir = Path(self.temp_dir) / ".swarm"
        self.state_file = self.swarm_dir / "state.json"

        # Patch constants
        self.patcher_swarm_dir = patch.object(swarm, 'SWARM_DIR', self.swarm_dir)
        self.patcher_state_file = patch.object(swarm, 'STATE_FILE', self.state_file)
        self.patcher_swarm_dir.start()
        self.patcher_state_file.start()

        # Create swarm directory
        self.swarm_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        """Clean up test fixtures."""
        self.patcher_swarm_dir.stop()
        self.patcher_state_file.stop()
        # Clean up temp directory
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _create_test_state(self, workers):
        """Helper to create a test state file."""
        state_data = {
            "workers": [w.to_dict() for w in workers]
        }
        with open(self.state_file, "w") as f:
            json.dump(state_data, f)

    def test_attach_worker_not_found(self):
        """Test attach with non-existent worker."""
        self._create_test_state([])

        args = Namespace(name="nonexistent")

        with patch('sys.stderr'):
            with self.assertRaises(SystemExit) as cm:
                swarm.cmd_attach(args)
            self.assertEqual(cm.exception.code, 1)

    def test_attach_worker_not_tmux(self):
        """Test attach with non-tmux worker."""
        worker = swarm.Worker(
            name="pid-worker",
            status="running",
            cmd=["echo", "test"],
            started="2026-01-10T00:00:00",
            cwd="/tmp",
            pid=12345
        )
        self._create_test_state([worker])

        args = Namespace(name="pid-worker")

        with patch('sys.stderr'):
            with self.assertRaises(SystemExit) as cm:
                swarm.cmd_attach(args)
            self.assertEqual(cm.exception.code, 1)

    @patch('os.execvp')
    @patch('subprocess.run')
    def test_attach_success(self, mock_subprocess_run, mock_execvp):
        """Test successful attach to tmux worker."""
        worker = swarm.Worker(
            name="test-worker",
            status="running",
            cmd=["echo", "test"],
            started="2026-01-10T00:00:00",
            cwd="/tmp",
            tmux=swarm.TmuxInfo(session="swarm", window="test-worker")
        )
        self._create_test_state([worker])

        mock_subprocess_run.return_value = Mock(returncode=0)

        args = Namespace(name="test-worker")
        swarm.cmd_attach(args)

        # Verify select-window was called
        mock_subprocess_run.assert_called_once_with(
            ["tmux", "select-window", "-t", "swarm:test-worker"],
            check=True
        )

        # Verify execvp was called to attach to session
        mock_execvp.assert_called_once_with(
            "tmux",
            ["tmux", "attach-session", "-t", "swarm"]
        )


class TestCmdWait(unittest.TestCase):
    """Test cmd_wait function."""

    def setUp(self):
        """Set up test fixtures."""
        # Create temporary swarm directory
        self.temp_dir = tempfile.mkdtemp()
        self.swarm_dir = Path(self.temp_dir) / ".swarm"
        self.state_file = self.swarm_dir / "state.json"

        # Patch constants
        self.patcher_swarm_dir = patch.object(swarm, 'SWARM_DIR', self.swarm_dir)
        self.patcher_state_file = patch.object(swarm, 'STATE_FILE', self.state_file)
        self.patcher_swarm_dir.start()
        self.patcher_state_file.start()

        # Create swarm directory
        self.swarm_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        """Clean up test fixtures."""
        self.patcher_swarm_dir.stop()
        self.patcher_state_file.stop()
        # Clean up temp directory
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _create_test_state(self, workers):
        """Helper to create a test state file."""
        state_data = {
            "workers": [w.to_dict() for w in workers]
        }
        with open(self.state_file, "w") as f:
            json.dump(state_data, f)

    def test_wait_worker_not_found(self):
        """Test wait with non-existent worker."""
        self._create_test_state([])

        args = Namespace(name="nonexistent", all=False, timeout=None)

        with patch('sys.stderr'):
            with self.assertRaises(SystemExit) as cm:
                swarm.cmd_wait(args)
            self.assertEqual(cm.exception.code, 1)

    def test_wait_no_name_and_no_all(self):
        """Test error when neither name nor --all is provided."""
        self._create_test_state([])

        args = Namespace(name=None, all=False, timeout=None)

        with patch('sys.stderr'):
            with self.assertRaises(SystemExit) as cm:
                swarm.cmd_wait(args)
            self.assertEqual(cm.exception.code, 1)

    @patch('swarm.refresh_worker_status')
    def test_wait_single_worker_already_stopped(self, mock_refresh):
        """Test waiting for a worker that's already stopped."""
        worker = swarm.Worker(
            name="test-worker",
            status="stopped",
            cmd=["echo", "test"],
            started="2026-01-10T12:00:00",
            cwd="/tmp"
        )
        self._create_test_state([worker])

        mock_refresh.return_value = "stopped"

        args = Namespace(name="test-worker", all=False, timeout=None)

        with patch('builtins.print') as mock_print:
            with self.assertRaises(SystemExit) as cm:
                swarm.cmd_wait(args)
            self.assertEqual(cm.exception.code, 0)

        # Verify output
        mock_print.assert_called_once_with("test-worker: exited")

    @patch('time.sleep')
    @patch('swarm.refresh_worker_status')
    def test_wait_single_worker_becomes_stopped(self, mock_refresh, mock_sleep):
        """Test waiting for a worker that becomes stopped."""
        worker = swarm.Worker(
            name="test-worker",
            status="running",
            cmd=["sleep", "10"],
            started="2026-01-10T12:00:00",
            cwd="/tmp",
            pid=12345
        )
        self._create_test_state([worker])

        # Mock: running twice, then stopped
        mock_refresh.side_effect = ["running", "running", "stopped"]

        args = Namespace(name="test-worker", all=False, timeout=None)

        with patch('builtins.print') as mock_print:
            with self.assertRaises(SystemExit) as cm:
                swarm.cmd_wait(args)
            self.assertEqual(cm.exception.code, 0)

        # Verify sleep was called twice
        self.assertEqual(mock_sleep.call_count, 2)
        mock_sleep.assert_called_with(1)

        # Verify output
        mock_print.assert_called_once_with("test-worker: exited")

    @patch('time.sleep')
    @patch('swarm.refresh_worker_status')
    def test_wait_all_workers(self, mock_refresh, mock_sleep):
        """Test waiting for all workers with --all flag."""
        workers = [
            swarm.Worker(
                name="worker1",
                status="running",
                cmd=["sleep", "5"],
                started="2026-01-10T12:00:00",
                cwd="/tmp",
                pid=111
            ),
            swarm.Worker(
                name="worker2",
                status="running",
                cmd=["sleep", "5"],
                started="2026-01-10T12:00:00",
                cwd="/tmp",
                pid=222
            ),
            swarm.Worker(
                name="worker3",
                status="stopped",
                cmd=["echo", "done"],
                started="2026-01-10T12:00:00",
                cwd="/tmp"
            ),
        ]
        self._create_test_state(workers)

        # Initial filter calls + poll cycles
        # worker1, worker2, worker3 for initial filter
        # Then poll: worker1 stops, worker2 still running
        # Then poll: worker2 stops
        mock_refresh.side_effect = [
            "running",  # worker1 initial filter
            "running",  # worker2 initial filter
            "stopped",  # worker3 initial filter (excluded)
            "stopped",  # worker1 poll - exits
            "running",  # worker2 poll - still running
            "stopped",  # worker2 poll - exits
        ]

        args = Namespace(name=None, all=True, timeout=None)

        with patch('builtins.print') as mock_print:
            with self.assertRaises(SystemExit) as cm:
                swarm.cmd_wait(args)
            self.assertEqual(cm.exception.code, 0)

        # Verify both workers showed as exited
        print_calls = [str(call) for call in mock_print.call_args_list]
        self.assertTrue(any("worker1: exited" in str(call) for call in print_calls))
        self.assertTrue(any("worker2: exited" in str(call) for call in print_calls))

    @patch('time.time')
    @patch('swarm.refresh_worker_status')
    def test_wait_timeout(self, mock_refresh, mock_time):
        """Test timeout functionality."""
        worker = swarm.Worker(
            name="slow-worker",
            status="running",
            cmd=["sleep", "1000"],
            started="2026-01-10T12:00:00",
            cwd="/tmp",
            pid=12345
        )
        self._create_test_state([worker])

        # Simulate time passing: start at 0, then 3, then 6 (exceeds 5 second timeout)
        mock_time.side_effect = [0, 3, 6]

        # Always return running
        mock_refresh.return_value = "running"

        args = Namespace(name="slow-worker", all=False, timeout=5)

        with patch('builtins.print') as mock_print:
            with patch('time.sleep'):
                with self.assertRaises(SystemExit) as cm:
                    swarm.cmd_wait(args)
                self.assertEqual(cm.exception.code, 1)

        # Verify timeout message
        mock_print.assert_called_once_with("slow-worker: still running (timeout)")

    @patch('swarm.refresh_worker_status')
    def test_wait_all_no_running_workers(self, mock_refresh):
        """Test --all when no workers are running."""
        worker = swarm.Worker(
            name="stopped-worker",
            status="stopped",
            cmd=["echo", "done"],
            started="2026-01-10T12:00:00",
            cwd="/tmp"
        )
        self._create_test_state([worker])

        mock_refresh.return_value = "stopped"

        args = Namespace(name=None, all=True, timeout=None)

        with patch('builtins.print') as mock_print:
            with self.assertRaises(SystemExit) as cm:
                swarm.cmd_wait(args)
            self.assertEqual(cm.exception.code, 0)

        # No output expected (no workers to wait for)
        mock_print.assert_not_called()

    @patch('time.time')
    @patch('time.sleep')
    @patch('swarm.refresh_worker_status')
    def test_wait_multiple_workers_timeout(self, mock_refresh, mock_sleep, mock_time):
        """Test timeout with multiple workers still running."""
        workers = [
            swarm.Worker(
                name="worker1",
                status="running",
                cmd=["sleep", "100"],
                started="2026-01-10T12:00:00",
                cwd="/tmp",
                pid=111
            ),
            swarm.Worker(
                name="worker2",
                status="running",
                cmd=["sleep", "100"],
                started="2026-01-10T12:00:00",
                cwd="/tmp",
                pid=222
            ),
        ]
        self._create_test_state(workers)

        # Time progression: 0, 3, 6 (timeout)
        mock_time.side_effect = [0, 3, 6]

        # All workers stay running
        mock_refresh.return_value = "running"

        args = Namespace(name=None, all=True, timeout=5)

        with patch('builtins.print') as mock_print:
            with self.assertRaises(SystemExit) as cm:
                swarm.cmd_wait(args)
            self.assertEqual(cm.exception.code, 1)

        # Both workers should be listed as timing out
        print_calls = [str(call) for call in mock_print.call_args_list]
        self.assertTrue(any("worker1: still running (timeout)" in str(call) for call in print_calls))
        self.assertTrue(any("worker2: still running (timeout)" in str(call) for call in print_calls))


if __name__ == "__main__":
    unittest.main()
