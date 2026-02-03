#!/usr/bin/env python3
"""Tests for cmd_logs function."""

import io
import sys
import tempfile
import unittest
from argparse import Namespace
from datetime import datetime
from pathlib import Path
from unittest.mock import patch, Mock

# Import swarm module
sys.path.insert(0, str(Path(__file__).parent))
import swarm


class TestCmdLogsWorkerNotFound(unittest.TestCase):
    """Tests for cmd_logs when worker is not found."""

    def test_logs_worker_not_found(self):
        """Test logs command when worker does not exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = Path(tmpdir) / "state.json"

            with patch.object(swarm, 'SWARM_DIR', Path(tmpdir)), \
                 patch.object(swarm, 'STATE_FILE', state_file), \
                 patch.object(swarm, 'LOGS_DIR', Path(tmpdir) / "logs"):

                # Create empty state
                state = swarm.State()

                args = Namespace(name="nonexistent", history=False, lines=1000, follow=False)

                with self.assertRaises(SystemExit) as cm:
                    swarm.cmd_logs(args)
                self.assertEqual(cm.exception.code, 1)


class TestCmdLogsTmuxWorker(unittest.TestCase):
    """Tests for cmd_logs with tmux workers."""

    def setUp(self):
        """Set up common test fixtures."""
        self.tmpdir = tempfile.mkdtemp()
        self.state_file = Path(self.tmpdir) / "state.json"
        self.logs_dir = Path(self.tmpdir) / "logs"
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.patches = [
            patch.object(swarm, 'SWARM_DIR', Path(self.tmpdir)),
            patch.object(swarm, 'STATE_FILE', self.state_file),
            patch.object(swarm, 'LOGS_DIR', self.logs_dir),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        """Clean up patches."""
        for p in self.patches:
            p.stop()
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _create_tmux_worker(self, name, socket=None):
        """Helper to create a tmux worker in state."""
        state = swarm.State()
        tmux_info = swarm.TmuxInfo(session="swarm-test", window=name, socket=socket)
        worker = swarm.Worker(
            name=name,
            status="running",
            cmd=["bash"],
            started=datetime.now().isoformat(),
            cwd="/tmp",
            tmux=tmux_info,
        )
        state.add_worker(worker)
        return worker

    def test_logs_tmux_worker_default_mode(self):
        """Test logs for tmux worker in default mode (no history)."""
        self._create_tmux_worker("worker-1")

        args = Namespace(name="worker-1", history=False, lines=1000, follow=False)

        with patch.object(swarm, 'tmux_capture_pane', return_value="line1\nline2\nline3") as mock_capture:
            captured_output = io.StringIO()
            with patch('sys.stdout', captured_output):
                swarm.cmd_logs(args)

            # Verify tmux_capture_pane was called with history=0 (no history)
            mock_capture.assert_called_once_with("swarm-test", "worker-1", history_lines=0, socket=None)

            output = captured_output.getvalue()
            self.assertEqual(output, "line1\nline2\nline3")

    def test_logs_tmux_worker_with_history(self):
        """Test logs for tmux worker with history enabled."""
        self._create_tmux_worker("worker-1")

        args = Namespace(name="worker-1", history=True, lines=500, follow=False)

        with patch.object(swarm, 'tmux_capture_pane', return_value="history output") as mock_capture:
            captured_output = io.StringIO()
            with patch('sys.stdout', captured_output):
                swarm.cmd_logs(args)

            # Verify history_lines was set to args.lines
            mock_capture.assert_called_once_with("swarm-test", "worker-1", history_lines=500, socket=None)

    def test_logs_tmux_worker_with_socket(self):
        """Test logs for tmux worker with custom socket."""
        self._create_tmux_worker("worker-1", socket="test-socket")

        args = Namespace(name="worker-1", history=False, lines=1000, follow=False)

        with patch.object(swarm, 'tmux_capture_pane', return_value="output") as mock_capture:
            captured_output = io.StringIO()
            with patch('sys.stdout', captured_output):
                swarm.cmd_logs(args)

            # Verify socket was passed correctly
            mock_capture.assert_called_once_with("swarm-test", "worker-1", history_lines=0, socket="test-socket")

    def test_logs_tmux_worker_follow_mode_keyboard_interrupt(self):
        """Test logs follow mode handles KeyboardInterrupt gracefully."""
        self._create_tmux_worker("worker-1")

        args = Namespace(name="worker-1", history=False, lines=1000, follow=True)

        # Mock tmux_capture_pane to raise KeyboardInterrupt after first call
        call_count = [0]
        def mock_capture(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] > 1:
                raise KeyboardInterrupt()
            return "line1\nline2"

        with patch.object(swarm, 'tmux_capture_pane', side_effect=mock_capture), \
             patch('time.sleep'):
            captured_output = io.StringIO()
            with patch('sys.stdout', captured_output):
                # Should not raise, handles KeyboardInterrupt
                swarm.cmd_logs(args)


class TestCmdLogsPidWorker(unittest.TestCase):
    """Tests for cmd_logs with PID (non-tmux) workers."""

    def setUp(self):
        """Set up common test fixtures."""
        self.tmpdir = tempfile.mkdtemp()
        self.state_file = Path(self.tmpdir) / "state.json"
        self.logs_dir = Path(self.tmpdir) / "logs"
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.patches = [
            patch.object(swarm, 'SWARM_DIR', Path(self.tmpdir)),
            patch.object(swarm, 'STATE_FILE', self.state_file),
            patch.object(swarm, 'LOGS_DIR', self.logs_dir),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        """Clean up patches."""
        for p in self.patches:
            p.stop()
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _create_pid_worker(self, name, pid=12345):
        """Helper to create a PID worker in state."""
        state = swarm.State()
        worker = swarm.Worker(
            name=name,
            status="running",
            cmd=["sleep", "1000"],
            started=datetime.now().isoformat(),
            cwd="/tmp",
            pid=pid,
        )
        state.add_worker(worker)
        return worker

    def test_logs_pid_worker_reads_log_file(self):
        """Test logs for PID worker reads from stdout log file."""
        self._create_pid_worker("worker-1")

        # Create log file
        log_file = self.logs_dir / "worker-1.stdout.log"
        log_file.write_text("log output line 1\nlog output line 2\n")

        args = Namespace(name="worker-1", history=False, lines=1000, follow=False)

        captured_output = io.StringIO()
        with patch('sys.stdout', captured_output):
            swarm.cmd_logs(args)

        output = captured_output.getvalue()
        self.assertEqual(output, "log output line 1\nlog output line 2\n")

    def test_logs_pid_worker_no_log_file(self):
        """Test logs for PID worker when log file does not exist."""
        self._create_pid_worker("worker-1")

        # Don't create log file

        args = Namespace(name="worker-1", history=False, lines=1000, follow=False)

        with self.assertRaises(SystemExit) as cm:
            swarm.cmd_logs(args)
        self.assertEqual(cm.exception.code, 1)

    def test_logs_pid_worker_follow_mode_uses_tail(self):
        """Test logs follow mode for PID worker uses tail -f."""
        self._create_pid_worker("worker-1")

        args = Namespace(name="worker-1", history=False, lines=1000, follow=True)

        with patch('os.execvp') as mock_execvp:
            swarm.cmd_logs(args)

            # Verify tail -f was called
            mock_execvp.assert_called_once()
            call_args = mock_execvp.call_args
            self.assertEqual(call_args[0][0], "tail")
            self.assertEqual(call_args[0][1][0], "tail")
            self.assertEqual(call_args[0][1][1], "-f")
            self.assertIn("worker-1.stdout.log", call_args[0][1][2])


if __name__ == "__main__":
    unittest.main()
