#!/usr/bin/env python3
"""Unit tests for tmux session cleanup after last worker is killed/cleaned."""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch, call
from argparse import Namespace

# Import the module under test
import swarm


class TestSessionHasOtherWorkers(unittest.TestCase):
    """Test cases for session_has_other_workers helper function."""

    def setUp(self):
        """Set up test fixtures."""
        self.test_dir = tempfile.mkdtemp()
        self.old_swarm_dir = swarm.SWARM_DIR
        self.old_state_file = swarm.STATE_FILE
        self.old_logs_dir = swarm.LOGS_DIR

        swarm.SWARM_DIR = Path(self.test_dir)
        swarm.STATE_FILE = swarm.SWARM_DIR / "state.json"
        swarm.LOGS_DIR = swarm.SWARM_DIR / "logs"
        swarm.LOGS_DIR.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        """Clean up test fixtures."""
        swarm.SWARM_DIR = self.old_swarm_dir
        swarm.STATE_FILE = self.old_state_file
        swarm.LOGS_DIR = self.old_logs_dir

        import shutil
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_no_other_workers_in_session(self):
        """Test when no other workers use the same session."""
        state = swarm.State()
        worker = swarm.Worker(
            name="only-worker",
            status="running",
            cmd=["echo", "hello"],
            started="2024-01-01T00:00:00",
            cwd="/tmp",
            tmux=swarm.TmuxInfo(session="swarm-abc", window="only-worker"),
        )
        state.add_worker(worker)

        result = swarm.session_has_other_workers(state, "swarm-abc", "only-worker")
        self.assertFalse(result)

    def test_other_workers_in_same_session(self):
        """Test when other workers use the same session."""
        state = swarm.State()
        worker1 = swarm.Worker(
            name="worker-1",
            status="running",
            cmd=["echo", "1"],
            started="2024-01-01T00:00:00",
            cwd="/tmp",
            tmux=swarm.TmuxInfo(session="swarm-abc", window="worker-1"),
        )
        worker2 = swarm.Worker(
            name="worker-2",
            status="running",
            cmd=["echo", "2"],
            started="2024-01-01T00:00:00",
            cwd="/tmp",
            tmux=swarm.TmuxInfo(session="swarm-abc", window="worker-2"),
        )
        state.add_worker(worker1)
        state.add_worker(worker2)

        result = swarm.session_has_other_workers(state, "swarm-abc", "worker-1")
        self.assertTrue(result)

    def test_workers_in_different_sessions(self):
        """Test workers in different sessions don't count."""
        state = swarm.State()
        worker1 = swarm.Worker(
            name="worker-1",
            status="running",
            cmd=["echo", "1"],
            started="2024-01-01T00:00:00",
            cwd="/tmp",
            tmux=swarm.TmuxInfo(session="swarm-abc", window="worker-1"),
        )
        worker2 = swarm.Worker(
            name="worker-2",
            status="running",
            cmd=["echo", "2"],
            started="2024-01-01T00:00:00",
            cwd="/tmp",
            tmux=swarm.TmuxInfo(session="swarm-xyz", window="worker-2"),
        )
        state.add_worker(worker1)
        state.add_worker(worker2)

        result = swarm.session_has_other_workers(state, "swarm-abc", "worker-1")
        self.assertFalse(result)

    def test_non_tmux_workers_ignored(self):
        """Test non-tmux workers don't affect session count."""
        state = swarm.State()
        tmux_worker = swarm.Worker(
            name="tmux-worker",
            status="running",
            cmd=["echo", "1"],
            started="2024-01-01T00:00:00",
            cwd="/tmp",
            tmux=swarm.TmuxInfo(session="swarm-abc", window="tmux-worker"),
        )
        non_tmux_worker = swarm.Worker(
            name="non-tmux-worker",
            status="running",
            cmd=["echo", "2"],
            started="2024-01-01T00:00:00",
            cwd="/tmp",
            pid=12345,
        )
        state.add_worker(tmux_worker)
        state.add_worker(non_tmux_worker)

        result = swarm.session_has_other_workers(state, "swarm-abc", "tmux-worker")
        self.assertFalse(result)

    def test_different_socket_same_session_name(self):
        """Test workers with same session name but different sockets are separate."""
        state = swarm.State()
        worker1 = swarm.Worker(
            name="worker-1",
            status="running",
            cmd=["echo", "1"],
            started="2024-01-01T00:00:00",
            cwd="/tmp",
            tmux=swarm.TmuxInfo(session="swarm", window="worker-1", socket="socket1"),
        )
        worker2 = swarm.Worker(
            name="worker-2",
            status="running",
            cmd=["echo", "2"],
            started="2024-01-01T00:00:00",
            cwd="/tmp",
            tmux=swarm.TmuxInfo(session="swarm", window="worker-2", socket="socket2"),
        )
        state.add_worker(worker1)
        state.add_worker(worker2)

        result = swarm.session_has_other_workers(state, "swarm", "worker-1", socket="socket1")
        self.assertFalse(result)

    def test_same_socket_same_session(self):
        """Test workers with same session and socket are counted together."""
        state = swarm.State()
        worker1 = swarm.Worker(
            name="worker-1",
            status="running",
            cmd=["echo", "1"],
            started="2024-01-01T00:00:00",
            cwd="/tmp",
            tmux=swarm.TmuxInfo(session="swarm", window="worker-1", socket="socket1"),
        )
        worker2 = swarm.Worker(
            name="worker-2",
            status="running",
            cmd=["echo", "2"],
            started="2024-01-01T00:00:00",
            cwd="/tmp",
            tmux=swarm.TmuxInfo(session="swarm", window="worker-2", socket="socket1"),
        )
        state.add_worker(worker1)
        state.add_worker(worker2)

        result = swarm.session_has_other_workers(state, "swarm", "worker-1", socket="socket1")
        self.assertTrue(result)


class TestKillTmuxSession(unittest.TestCase):
    """Test cases for kill_tmux_session helper function."""

    def test_kill_session_no_socket(self):
        """Test killing a session without socket."""
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = Mock(returncode=0)
            swarm.kill_tmux_session("swarm-abc")
            mock_run.assert_called_once_with(
                ["tmux", "kill-session", "-t", "swarm-abc"],
                capture_output=True
            )

    def test_kill_session_with_socket(self):
        """Test killing a session with socket."""
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = Mock(returncode=0)
            swarm.kill_tmux_session("swarm-abc", socket="test-socket")
            mock_run.assert_called_once_with(
                ["tmux", "-L", "test-socket", "kill-session", "-t", "swarm-abc"],
                capture_output=True
            )


class TestCmdKillSessionCleanup(unittest.TestCase):
    """Test cmd_kill cleans up empty sessions."""

    def setUp(self):
        """Set up test fixtures."""
        self.test_dir = tempfile.mkdtemp()
        self.old_swarm_dir = swarm.SWARM_DIR
        self.old_state_file = swarm.STATE_FILE
        self.old_logs_dir = swarm.LOGS_DIR

        swarm.SWARM_DIR = Path(self.test_dir)
        swarm.STATE_FILE = swarm.SWARM_DIR / "state.json"
        swarm.LOGS_DIR = swarm.SWARM_DIR / "logs"
        swarm.LOGS_DIR.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        """Clean up test fixtures."""
        swarm.SWARM_DIR = self.old_swarm_dir
        swarm.STATE_FILE = self.old_state_file
        swarm.LOGS_DIR = self.old_logs_dir

        import shutil
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_kill_last_worker_cleans_session(self):
        """Test killing the last worker in a session cleans up the session."""
        state = swarm.State()
        worker = swarm.Worker(
            name="only-worker",
            status="running",
            cmd=["echo", "hello"],
            started="2024-01-01T00:00:00",
            cwd="/tmp",
            tmux=swarm.TmuxInfo(session="swarm-abc", window="only-worker"),
        )
        state.add_worker(worker)

        args = Namespace(name="only-worker", all=False, rm_worktree=False)

        with patch('subprocess.run') as mock_run, \
             patch('swarm.kill_tmux_session') as mock_kill_session:
            mock_run.return_value = Mock(returncode=0)

            swarm.cmd_kill(args)

            # Verify kill-window was called
            mock_run.assert_called_once_with(
                ["tmux", "kill-window", "-t", "swarm-abc:only-worker"],
                capture_output=True
            )
            # Verify session cleanup was called
            mock_kill_session.assert_called_once_with("swarm-abc", socket=None)

    def test_kill_non_last_worker_keeps_session(self):
        """Test killing a worker when others remain doesn't clean session."""
        state = swarm.State()
        worker1 = swarm.Worker(
            name="worker-1",
            status="running",
            cmd=["echo", "1"],
            started="2024-01-01T00:00:00",
            cwd="/tmp",
            tmux=swarm.TmuxInfo(session="swarm-abc", window="worker-1"),
        )
        worker2 = swarm.Worker(
            name="worker-2",
            status="running",
            cmd=["echo", "2"],
            started="2024-01-01T00:00:00",
            cwd="/tmp",
            tmux=swarm.TmuxInfo(session="swarm-abc", window="worker-2"),
        )
        state.add_worker(worker1)
        state.add_worker(worker2)

        args = Namespace(name="worker-1", all=False, rm_worktree=False)

        with patch('subprocess.run') as mock_run, \
             patch('swarm.kill_tmux_session') as mock_kill_session:
            mock_run.return_value = Mock(returncode=0)

            swarm.cmd_kill(args)

            # Verify kill-window was called
            mock_run.assert_called_once()
            # Verify session cleanup was NOT called
            mock_kill_session.assert_not_called()

    def test_kill_non_tmux_worker_no_session_cleanup(self):
        """Test killing non-tmux worker doesn't trigger session cleanup."""
        state = swarm.State()
        worker = swarm.Worker(
            name="pid-worker",
            status="running",
            cmd=["sleep", "1000"],
            started="2024-01-01T00:00:00",
            cwd="/tmp",
            pid=12345,
        )
        state.add_worker(worker)

        args = Namespace(name="pid-worker", all=False, rm_worktree=False)

        with patch('os.kill') as mock_kill, \
             patch('swarm.process_alive', return_value=False), \
             patch('swarm.kill_tmux_session') as mock_kill_session:

            swarm.cmd_kill(args)

            # Verify SIGTERM was sent
            mock_kill.assert_called_with(12345, 15)  # SIGTERM = 15
            # Verify session cleanup was NOT called
            mock_kill_session.assert_not_called()

    def test_kill_all_workers_cleans_sessions(self):
        """Test killing all workers cleans up sessions with no remaining workers."""
        state = swarm.State()
        # Two workers in same session
        worker1 = swarm.Worker(
            name="worker-1",
            status="running",
            cmd=["echo", "1"],
            started="2024-01-01T00:00:00",
            cwd="/tmp",
            tmux=swarm.TmuxInfo(session="swarm-abc", window="worker-1"),
        )
        worker2 = swarm.Worker(
            name="worker-2",
            status="running",
            cmd=["echo", "2"],
            started="2024-01-01T00:00:00",
            cwd="/tmp",
            tmux=swarm.TmuxInfo(session="swarm-abc", window="worker-2"),
        )
        # One worker in different session
        worker3 = swarm.Worker(
            name="worker-3",
            status="running",
            cmd=["echo", "3"],
            started="2024-01-01T00:00:00",
            cwd="/tmp",
            tmux=swarm.TmuxInfo(session="swarm-xyz", window="worker-3"),
        )
        state.add_worker(worker1)
        state.add_worker(worker2)
        state.add_worker(worker3)

        args = Namespace(name=None, all=True, rm_worktree=False)

        with patch('subprocess.run') as mock_run, \
             patch('swarm.kill_tmux_session') as mock_kill_session:
            mock_run.return_value = Mock(returncode=0)

            swarm.cmd_kill(args)

            # Verify kill-window was called for all workers
            self.assertEqual(mock_run.call_count, 3)
            # Verify both sessions were cleaned up
            self.assertEqual(mock_kill_session.call_count, 2)
            # Check sessions cleaned
            kill_session_calls = [c[0][0] for c in mock_kill_session.call_args_list]
            self.assertIn("swarm-abc", kill_session_calls)
            self.assertIn("swarm-xyz", kill_session_calls)

    def test_kill_with_socket_cleans_session(self):
        """Test killing worker with socket cleans session with same socket."""
        state = swarm.State()
        worker = swarm.Worker(
            name="socket-worker",
            status="running",
            cmd=["echo", "hello"],
            started="2024-01-01T00:00:00",
            cwd="/tmp",
            tmux=swarm.TmuxInfo(session="swarm-abc", window="socket-worker", socket="test-sock"),
        )
        state.add_worker(worker)

        args = Namespace(name="socket-worker", all=False, rm_worktree=False)

        with patch('subprocess.run') as mock_run, \
             patch('swarm.kill_tmux_session') as mock_kill_session:
            mock_run.return_value = Mock(returncode=0)

            swarm.cmd_kill(args)

            # Verify session cleanup was called with socket
            mock_kill_session.assert_called_once_with("swarm-abc", socket="test-sock")


class TestCmdCleanSessionCleanup(unittest.TestCase):
    """Test cmd_clean cleans up empty sessions."""

    def setUp(self):
        """Set up test fixtures."""
        self.test_dir = tempfile.mkdtemp()
        self.old_swarm_dir = swarm.SWARM_DIR
        self.old_state_file = swarm.STATE_FILE
        self.old_logs_dir = swarm.LOGS_DIR

        swarm.SWARM_DIR = Path(self.test_dir)
        swarm.STATE_FILE = swarm.SWARM_DIR / "state.json"
        swarm.LOGS_DIR = swarm.SWARM_DIR / "logs"
        swarm.LOGS_DIR.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        """Clean up test fixtures."""
        swarm.SWARM_DIR = self.old_swarm_dir
        swarm.STATE_FILE = self.old_state_file
        swarm.LOGS_DIR = self.old_logs_dir

        import shutil
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_clean_last_tmux_worker_cleans_session(self):
        """Test cleaning the last tmux worker in a session cleans up the session."""
        state = swarm.State()
        worker = swarm.Worker(
            name="only-worker",
            status="stopped",
            cmd=["echo", "hello"],
            started="2024-01-01T00:00:00",
            cwd="/tmp",
            tmux=swarm.TmuxInfo(session="swarm-abc", window="only-worker"),
        )
        state.add_worker(worker)

        args = Mock()
        args.name = "only-worker"
        args.all = False
        args.rm_worktree = False

        with patch('swarm.refresh_worker_status', return_value="stopped"), \
             patch('swarm.kill_tmux_session') as mock_kill_session, \
             patch('builtins.print'):

            swarm.cmd_clean(args)

            # Verify session cleanup was called
            mock_kill_session.assert_called_once_with("swarm-abc", socket=None)

    def test_clean_non_last_tmux_worker_keeps_session(self):
        """Test cleaning a worker when others remain doesn't clean session."""
        state = swarm.State()
        worker1 = swarm.Worker(
            name="worker-1",
            status="stopped",
            cmd=["echo", "1"],
            started="2024-01-01T00:00:00",
            cwd="/tmp",
            tmux=swarm.TmuxInfo(session="swarm-abc", window="worker-1"),
        )
        worker2 = swarm.Worker(
            name="worker-2",
            status="running",
            cmd=["echo", "2"],
            started="2024-01-01T00:00:00",
            cwd="/tmp",
            tmux=swarm.TmuxInfo(session="swarm-abc", window="worker-2"),
        )
        state.add_worker(worker1)
        state.add_worker(worker2)

        args = Mock()
        args.name = "worker-1"
        args.all = False
        args.rm_worktree = False

        with patch('swarm.refresh_worker_status', return_value="stopped"), \
             patch('swarm.kill_tmux_session') as mock_kill_session, \
             patch('builtins.print'):

            swarm.cmd_clean(args)

            # Verify session cleanup was NOT called
            mock_kill_session.assert_not_called()

    def test_clean_non_tmux_worker_no_session_cleanup(self):
        """Test cleaning non-tmux worker doesn't trigger session cleanup."""
        state = swarm.State()
        worker = swarm.Worker(
            name="pid-worker",
            status="stopped",
            cmd=["sleep", "1000"],
            started="2024-01-01T00:00:00",
            cwd="/tmp",
            pid=12345,
        )
        state.add_worker(worker)

        args = Mock()
        args.name = "pid-worker"
        args.all = False
        args.rm_worktree = False

        with patch('swarm.refresh_worker_status', return_value="stopped"), \
             patch('swarm.kill_tmux_session') as mock_kill_session, \
             patch('builtins.print'):

            swarm.cmd_clean(args)

            # Verify session cleanup was NOT called
            mock_kill_session.assert_not_called()

    def test_clean_all_cleans_orphaned_sessions(self):
        """Test clean --all cleans up sessions with no remaining workers."""
        state = swarm.State()
        # Two stopped workers in same session
        worker1 = swarm.Worker(
            name="worker-1",
            status="stopped",
            cmd=["echo", "1"],
            started="2024-01-01T00:00:00",
            cwd="/tmp",
            tmux=swarm.TmuxInfo(session="swarm-abc", window="worker-1"),
        )
        worker2 = swarm.Worker(
            name="worker-2",
            status="stopped",
            cmd=["echo", "2"],
            started="2024-01-01T00:00:00",
            cwd="/tmp",
            tmux=swarm.TmuxInfo(session="swarm-abc", window="worker-2"),
        )
        state.add_worker(worker1)
        state.add_worker(worker2)

        args = Mock()
        args.name = None
        args.all = True
        args.rm_worktree = False

        with patch('swarm.refresh_worker_status', return_value="stopped"), \
             patch('swarm.kill_tmux_session') as mock_kill_session, \
             patch('builtins.print'):

            swarm.cmd_clean(args)

            # Verify session cleanup was called once (for swarm-abc)
            mock_kill_session.assert_called_once_with("swarm-abc", socket=None)

    def test_clean_with_socket_cleans_session(self):
        """Test cleaning worker with socket cleans session with same socket."""
        state = swarm.State()
        worker = swarm.Worker(
            name="socket-worker",
            status="stopped",
            cmd=["echo", "hello"],
            started="2024-01-01T00:00:00",
            cwd="/tmp",
            tmux=swarm.TmuxInfo(session="swarm-abc", window="socket-worker", socket="test-sock"),
        )
        state.add_worker(worker)

        args = Mock()
        args.name = "socket-worker"
        args.all = False
        args.rm_worktree = False

        with patch('swarm.refresh_worker_status', return_value="stopped"), \
             patch('swarm.kill_tmux_session') as mock_kill_session, \
             patch('builtins.print'):

            swarm.cmd_clean(args)

            # Verify session cleanup was called with socket
            mock_kill_session.assert_called_once_with("swarm-abc", socket="test-sock")


if __name__ == "__main__":
    unittest.main()
