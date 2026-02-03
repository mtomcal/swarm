#!/usr/bin/env python3
"""Test cmd_kill function"""

import json
import os
import signal
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch, Mock
from argparse import Namespace

# Import swarm module
sys.path.insert(0, str(Path(__file__).parent))
import swarm


class TestCmdKill(unittest.TestCase):
    """Tests for the cmd_kill function."""

    def test_kill_single_tmux_worker(self):
        """Test killing a single tmux worker."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = Path(tmpdir) / "state.json"

            with patch.object(swarm, 'SWARM_DIR', Path(tmpdir)), \
                 patch.object(swarm, 'STATE_FILE', state_file), \
                 patch.object(swarm, 'LOGS_DIR', Path(tmpdir) / "logs"):

                # Create state with a tmux worker
                state = swarm.State()
                worker = swarm.Worker(
                    name="test-worker",
                    status="running",
                    cmd=["bash"],
                    started="2026-01-10T12:00:00Z",
                    cwd="/tmp",
                    tmux=swarm.TmuxInfo(session="swarm", window="test-worker"),
                )
                state.add_worker(worker)

                # Mock subprocess.run
                with patch('subprocess.run') as mock_run:
                    mock_run.return_value = Mock(returncode=0)

                    # Create args using Namespace
                    args = Namespace(name="test-worker", all=False, rm_worktree=False)

                    # Call cmd_kill
                    swarm.cmd_kill(args)

                    # Verify tmux kill-window was called
                    kill_window_call = [
                        call for call in mock_run.call_args_list
                        if "kill-window" in call[0][0]
                    ]
                    self.assertEqual(len(kill_window_call), 1)
                    self.assertEqual(
                        kill_window_call[0][0][0],
                        ["tmux", "kill-window", "-t", "swarm:test-worker"]
                    )

                    # Verify worker status was updated
                    state = swarm.State()
                    updated_worker = state.get_worker("test-worker")
                    self.assertEqual(updated_worker.status, "stopped")

    def test_kill_worker_not_found(self):
        """Test killing a worker that doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = Path(tmpdir) / "state.json"

            with patch.object(swarm, 'SWARM_DIR', Path(tmpdir)), \
                 patch.object(swarm, 'STATE_FILE', state_file), \
                 patch.object(swarm, 'LOGS_DIR', Path(tmpdir) / "logs"):

                # Create empty state
                state = swarm.State()

                # Create args using Namespace
                args = Namespace(name="nonexistent", all=False, rm_worktree=False)

                # Should exit with error
                with self.assertRaises(SystemExit) as cm:
                    swarm.cmd_kill(args)
                self.assertEqual(cm.exception.code, 1)

    def test_kill_all_workers(self):
        """Test killing all workers with --all flag."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = Path(tmpdir) / "state.json"

            with patch.object(swarm, 'SWARM_DIR', Path(tmpdir)), \
                 patch.object(swarm, 'STATE_FILE', state_file), \
                 patch.object(swarm, 'LOGS_DIR', Path(tmpdir) / "logs"):

                # Create state with multiple workers
                state = swarm.State()

                # Add tmux worker
                worker1 = swarm.Worker(
                    name="worker1",
                    status="running",
                    cmd=["bash"],
                    started="2026-01-10T12:00:00Z",
                    cwd="/tmp",
                    tmux=swarm.TmuxInfo(session="swarm", window="worker1"),
                )
                state.add_worker(worker1)

                # Add non-tmux worker
                worker2 = swarm.Worker(
                    name="worker2",
                    status="running",
                    cmd=["sleep", "1000"],
                    started="2026-01-10T12:00:00Z",
                    cwd="/tmp",
                    pid=99999,  # Use a fake PID
                )
                state.add_worker(worker2)

                # Mock subprocess.run, os.kill, and process_alive
                with patch('subprocess.run') as mock_run, \
                     patch('os.kill') as mock_kill, \
                     patch.object(swarm, 'process_alive') as mock_alive:

                    mock_run.return_value = Mock(returncode=0)
                    mock_alive.return_value = False

                    # Create args using Namespace
                    args = Namespace(name=None, all=True, rm_worktree=False)

                    # Call cmd_kill
                    swarm.cmd_kill(args)

                    # Verify tmux kill-window was called for worker1
                    call_found = any(
                        call_args[0][0] == ["tmux", "kill-window", "-t", "swarm:worker1"]
                        for call_args in mock_run.call_args_list
                    )
                    self.assertTrue(call_found, "Expected tmux kill-window call for worker1")

                    # Verify SIGTERM was sent for worker2
                    mock_kill.assert_called_with(99999, signal.SIGTERM)

                    # Verify both workers are stopped
                    state = swarm.State()
                    self.assertEqual(state.get_worker("worker1").status, "stopped")
                    self.assertEqual(state.get_worker("worker2").status, "stopped")

    def test_kill_with_rm_worktree(self):
        """Test killing a worker and removing its worktree."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = Path(tmpdir) / "state.json"

            with patch.object(swarm, 'SWARM_DIR', Path(tmpdir)), \
                 patch.object(swarm, 'STATE_FILE', state_file), \
                 patch.object(swarm, 'LOGS_DIR', Path(tmpdir) / "logs"):

                # Create state with a worker that has a worktree
                state = swarm.State()
                worker = swarm.Worker(
                    name="test-worker",
                    status="running",
                    cmd=["bash"],
                    started="2026-01-10T12:00:00Z",
                    cwd="/tmp",
                    tmux=swarm.TmuxInfo(session="swarm", window="test-worker"),
                    worktree=swarm.WorktreeInfo(
                        path="/tmp/worktrees/test-worker",
                        branch="test-branch",
                        base_repo="/tmp/repo",
                    ),
                )
                state.add_worker(worker)

                # Mock subprocess.run and remove_worktree
                with patch('subprocess.run') as mock_run, \
                     patch.object(swarm, 'remove_worktree', return_value=(True, "")) as mock_remove_worktree:

                    mock_run.return_value = Mock(returncode=0)

                    # Create args using Namespace
                    args = Namespace(name="test-worker", all=False, rm_worktree=True, force_dirty=False)

                    # Call cmd_kill
                    swarm.cmd_kill(args)

                    # Verify tmux kill-window was called
                    kill_window_call = [
                        call for call in mock_run.call_args_list
                        if "kill-window" in call[0][0]
                    ]
                    self.assertEqual(len(kill_window_call), 1)
                    self.assertEqual(
                        kill_window_call[0][0][0],
                        ["tmux", "kill-window", "-t", "swarm:test-worker"]
                    )

                    # Verify remove_worktree was called with force=False
                    mock_remove_worktree.assert_called_once_with(Path("/tmp/worktrees/test-worker"), force=False)

    def test_kill_without_name_or_all(self):
        """Test that kill without name or --all produces error."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = Path(tmpdir) / "state.json"

            with patch.object(swarm, 'SWARM_DIR', Path(tmpdir)), \
                 patch.object(swarm, 'STATE_FILE', state_file), \
                 patch.object(swarm, 'LOGS_DIR', Path(tmpdir) / "logs"):

                # Create args without name or all
                args = Namespace(name=None, all=False, rm_worktree=False)

                # Should exit with error code 1
                with self.assertRaises(SystemExit) as cm:
                    swarm.cmd_kill(args)
                self.assertEqual(cm.exception.code, 1)

    def test_kill_pid_worker_with_sigkill_fallback(self):
        """Test killing a PID worker that requires SIGKILL after SIGTERM timeout."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = Path(tmpdir) / "state.json"

            with patch.object(swarm, 'SWARM_DIR', Path(tmpdir)), \
                 patch.object(swarm, 'STATE_FILE', state_file), \
                 patch.object(swarm, 'LOGS_DIR', Path(tmpdir) / "logs"):

                # Create state with a PID worker
                state = swarm.State()
                worker = swarm.Worker(
                    name="stubborn-worker",
                    status="running",
                    cmd=["sleep", "1000"],
                    started="2026-01-10T12:00:00Z",
                    cwd="/tmp",
                    pid=12345,
                )
                state.add_worker(worker)

                # Mock os.kill and process_alive
                # process_alive returns True (still alive after SIGTERM)
                with patch('os.kill') as mock_kill, \
                     patch.object(swarm, 'process_alive', return_value=True), \
                     patch('time.sleep'):

                    args = Namespace(name="stubborn-worker", all=False, rm_worktree=False)
                    swarm.cmd_kill(args)

                    # Verify SIGTERM was sent first
                    sigterm_call = unittest.mock.call(12345, signal.SIGTERM)
                    self.assertIn(sigterm_call, mock_kill.call_args_list)

                    # Verify SIGKILL was sent after (process still alive)
                    sigkill_call = unittest.mock.call(12345, signal.SIGKILL)
                    self.assertIn(sigkill_call, mock_kill.call_args_list)

    def test_kill_pid_worker_process_already_dead(self):
        """Test killing a PID worker where process is already dead."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = Path(tmpdir) / "state.json"

            with patch.object(swarm, 'SWARM_DIR', Path(tmpdir)), \
                 patch.object(swarm, 'STATE_FILE', state_file), \
                 patch.object(swarm, 'LOGS_DIR', Path(tmpdir) / "logs"):

                # Create state with a PID worker
                state = swarm.State()
                worker = swarm.Worker(
                    name="dead-worker",
                    status="running",
                    cmd=["sleep", "1000"],
                    started="2026-01-10T12:00:00Z",
                    cwd="/tmp",
                    pid=12345,
                )
                state.add_worker(worker)

                # Mock os.kill to raise ProcessLookupError (process doesn't exist)
                with patch('os.kill', side_effect=ProcessLookupError):
                    args = Namespace(name="dead-worker", all=False, rm_worktree=False)

                    # Should not raise, handles ProcessLookupError gracefully
                    swarm.cmd_kill(args)

                    # Verify worker status was updated
                    state = swarm.State()
                    updated_worker = state.get_worker("dead-worker")
                    self.assertEqual(updated_worker.status, "stopped")

    def test_kill_with_rm_worktree_failure(self):
        """Test killing a worker when worktree removal fails."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = Path(tmpdir) / "state.json"

            with patch.object(swarm, 'SWARM_DIR', Path(tmpdir)), \
                 patch.object(swarm, 'STATE_FILE', state_file), \
                 patch.object(swarm, 'LOGS_DIR', Path(tmpdir) / "logs"):

                # Create state with a worker that has a worktree
                state = swarm.State()
                worker = swarm.Worker(
                    name="test-worker",
                    status="running",
                    cmd=["bash"],
                    started="2026-01-10T12:00:00Z",
                    cwd="/tmp",
                    tmux=swarm.TmuxInfo(session="swarm", window="test-worker"),
                    worktree=swarm.WorktreeInfo(
                        path="/tmp/worktrees/test-worker",
                        branch="test-branch",
                        base_repo="/tmp/repo",
                    ),
                )
                state.add_worker(worker)

                # Mock subprocess.run and remove_worktree (failure case)
                with patch('subprocess.run') as mock_run, \
                     patch.object(swarm, 'remove_worktree', return_value=(False, "worktree has uncommitted changes")):

                    mock_run.return_value = Mock(returncode=0)

                    args = Namespace(name="test-worker", all=False, rm_worktree=True, force_dirty=False)

                    # Should complete without raising (just prints warning to stderr)
                    swarm.cmd_kill(args)

                    # Verify worker status was still updated
                    state = swarm.State()
                    updated_worker = state.get_worker("test-worker")
                    self.assertEqual(updated_worker.status, "stopped")


class TestCmdKillSessionCleanup(unittest.TestCase):
    """Tests for session cleanup in cmd_kill."""

    def test_kill_cleans_up_session_when_last_worker(self):
        """Test that session is cleaned up when killing the last worker in it."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = Path(tmpdir) / "state.json"

            with patch.object(swarm, 'SWARM_DIR', Path(tmpdir)), \
                 patch.object(swarm, 'STATE_FILE', state_file), \
                 patch.object(swarm, 'LOGS_DIR', Path(tmpdir) / "logs"):

                # Create state with a single tmux worker
                state = swarm.State()
                worker = swarm.Worker(
                    name="only-worker",
                    status="running",
                    cmd=["bash"],
                    started="2026-01-10T12:00:00Z",
                    cwd="/tmp",
                    tmux=swarm.TmuxInfo(session="swarm-abc123", window="only-worker"),
                )
                state.add_worker(worker)

                # Mock subprocess.run
                with patch('subprocess.run') as mock_run:
                    mock_run.return_value = Mock(returncode=0)

                    args = Namespace(name="only-worker", all=False, rm_worktree=False)
                    swarm.cmd_kill(args)

                    # Check that kill-session was called
                    kill_session_call = [
                        call for call in mock_run.call_args_list
                        if "kill-session" in call[0][0]
                    ]
                    self.assertEqual(len(kill_session_call), 1)
                    self.assertIn("-t", kill_session_call[0][0][0])

    def test_kill_preserves_session_when_other_workers_exist(self):
        """Test that session is preserved when other workers still use it."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = Path(tmpdir) / "state.json"

            with patch.object(swarm, 'SWARM_DIR', Path(tmpdir)), \
                 patch.object(swarm, 'STATE_FILE', state_file), \
                 patch.object(swarm, 'LOGS_DIR', Path(tmpdir) / "logs"):

                # Create state with two workers in the same session
                state = swarm.State()
                worker1 = swarm.Worker(
                    name="worker-1",
                    status="running",
                    cmd=["bash"],
                    started="2026-01-10T12:00:00Z",
                    cwd="/tmp",
                    tmux=swarm.TmuxInfo(session="swarm-shared", window="worker-1"),
                )
                worker2 = swarm.Worker(
                    name="worker-2",
                    status="running",
                    cmd=["bash"],
                    started="2026-01-10T12:00:00Z",
                    cwd="/tmp",
                    tmux=swarm.TmuxInfo(session="swarm-shared", window="worker-2"),
                )
                state.add_worker(worker1)
                state.add_worker(worker2)

                # Mock subprocess.run
                with patch('subprocess.run') as mock_run:
                    mock_run.return_value = Mock(returncode=0)

                    # Kill only worker-1
                    args = Namespace(name="worker-1", all=False, rm_worktree=False)
                    swarm.cmd_kill(args)

                    # Check that kill-session was NOT called (worker-2 still exists)
                    kill_session_calls = [
                        call for call in mock_run.call_args_list
                        if "kill-session" in call[0][0]
                    ]
                    self.assertEqual(len(kill_session_calls), 0)


if __name__ == "__main__":
    unittest.main()
