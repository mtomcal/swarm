#!/usr/bin/env python3
"""Unit tests for cmd_clean function."""

import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch, call

# Import the module under test
import swarm


class TestCmdClean(unittest.TestCase):
    """Test cases for cmd_clean function."""

    def setUp(self):
        """Set up test fixtures."""
        # Create a temporary directory for test state
        self.test_dir = tempfile.mkdtemp()
        self.old_swarm_dir = swarm.SWARM_DIR
        self.old_state_file = swarm.STATE_FILE
        self.old_logs_dir = swarm.LOGS_DIR

        # Override constants to use test directory
        swarm.SWARM_DIR = Path(self.test_dir)
        swarm.STATE_FILE = swarm.SWARM_DIR / "state.json"
        swarm.LOGS_DIR = swarm.SWARM_DIR / "logs"
        swarm.LOGS_DIR.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        """Clean up test fixtures."""
        # Restore original constants
        swarm.SWARM_DIR = self.old_swarm_dir
        swarm.STATE_FILE = self.old_state_file
        swarm.LOGS_DIR = self.old_logs_dir

        # Remove test directory
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_clean_single_stopped_worker_without_worktree(self):
        """Test cleaning a single stopped worker without worktree."""
        # Create a stopped worker in state
        state = swarm.State()
        worker = swarm.Worker(
            name="test-worker",
            status="stopped",
            cmd=["echo", "hello"],
            started="2024-01-01T00:00:00",
            cwd="/tmp",
        )
        state.add_worker(worker)

        # Create log files
        stdout_log = swarm.LOGS_DIR / "test-worker.stdout.log"
        stderr_log = swarm.LOGS_DIR / "test-worker.stderr.log"
        stdout_log.write_text("stdout content")
        stderr_log.write_text("stderr content")

        # Mock args
        args = Mock()
        args.name = "test-worker"
        args.all = False
        args.rm_worktree = True

        # Mock refresh_worker_status to return stopped
        with patch('swarm.refresh_worker_status', return_value="stopped"):
            # Capture stdout
            with patch('builtins.print') as mock_print:
                swarm.cmd_clean(args)

        # Verify worker removed from state
        state = swarm.State()
        self.assertIsNone(state.get_worker("test-worker"))

        # Verify log files removed
        self.assertFalse(stdout_log.exists())
        self.assertFalse(stderr_log.exists())

        # Verify output
        mock_print.assert_called_once_with("cleaned test-worker")

    def test_clean_single_stopped_worker_with_worktree(self):
        """Test cleaning a stopped worker with worktree."""
        # Create a stopped worker with worktree
        state = swarm.State()
        worktree_path = Path(self.test_dir) / "worktree"
        worktree_path.mkdir()

        worker = swarm.Worker(
            name="test-worker",
            status="stopped",
            cmd=["echo", "hello"],
            started="2024-01-01T00:00:00",
            cwd="/tmp",
            worktree=swarm.WorktreeInfo(
                path=str(worktree_path),
                branch="test-branch",
                base_repo="/repo"
            )
        )
        state.add_worker(worker)

        # Mock args
        args = Mock()
        args.name = "test-worker"
        args.all = False
        args.rm_worktree = True
        args.force_dirty = False

        # Mock functions
        with patch('swarm.refresh_worker_status', return_value="stopped"), \
             patch('swarm.remove_worktree', return_value=(True, "")) as mock_remove_worktree, \
             patch('builtins.print'):
            swarm.cmd_clean(args)

        # Verify remove_worktree was called with force=False
        mock_remove_worktree.assert_called_once_with(worktree_path, force=False)

        # Verify worker removed from state
        state = swarm.State()
        self.assertIsNone(state.get_worker("test-worker"))

    def test_clean_worker_not_found(self):
        """Test cleaning a worker that doesn't exist."""
        state = swarm.State()

        args = Mock()
        args.name = "nonexistent"
        args.all = False

        # Should print error and exit with code 1
        with patch('builtins.print') as mock_print:
            with self.assertRaises(SystemExit) as cm:
                swarm.cmd_clean(args)

        self.assertEqual(cm.exception.code, 1)
        mock_print.assert_called_once()
        self.assertIn("not found", mock_print.call_args[0][0])

    def test_clean_running_worker_error(self):
        """Test that cleaning a running worker produces an error."""
        # Create a running worker
        state = swarm.State()
        worker = swarm.Worker(
            name="running-worker",
            status="running",
            cmd=["echo", "hello"],
            started="2024-01-01T00:00:00",
            cwd="/tmp",
            pid=12345
        )
        state.add_worker(worker)

        args = Mock()
        args.name = "running-worker"
        args.all = False

        # Mock refresh to return running
        with patch('swarm.refresh_worker_status', return_value="running"), \
             patch('builtins.print') as mock_print:
            with self.assertRaises(SystemExit) as cm:
                swarm.cmd_clean(args)

        # Verify error message and exit
        self.assertEqual(cm.exception.code, 1)
        mock_print.assert_called_once()
        self.assertIn("cannot clean running worker", mock_print.call_args[0][0])
        self.assertIn("running-worker", mock_print.call_args[0][0])

    def test_clean_all_stopped_workers(self):
        """Test cleaning all stopped workers."""
        state = swarm.State()

        # Create multiple workers: some stopped, some running
        stopped1 = swarm.Worker(
            name="stopped-1",
            status="stopped",
            cmd=["echo", "1"],
            started="2024-01-01T00:00:00",
            cwd="/tmp",
        )
        stopped2 = swarm.Worker(
            name="stopped-2",
            status="stopped",
            cmd=["echo", "2"],
            started="2024-01-01T00:00:00",
            cwd="/tmp",
        )
        running1 = swarm.Worker(
            name="running-1",
            status="running",
            cmd=["echo", "3"],
            started="2024-01-01T00:00:00",
            cwd="/tmp",
            pid=12345
        )

        state.add_worker(stopped1)
        state.add_worker(stopped2)
        state.add_worker(running1)

        # Create log files for stopped workers
        for name in ["stopped-1", "stopped-2"]:
            (swarm.LOGS_DIR / f"{name}.stdout.log").write_text("content")
            (swarm.LOGS_DIR / f"{name}.stderr.log").write_text("content")

        args = Mock()
        args.name = None
        args.all = True
        args.rm_worktree = True

        # Mock refresh to return correct status for each worker
        def refresh_side_effect(worker):
            if worker.name in ["stopped-1", "stopped-2"]:
                return "stopped"
            else:
                return "running"

        with patch('swarm.refresh_worker_status', side_effect=refresh_side_effect), \
             patch('builtins.print') as mock_print:
            swarm.cmd_clean(args)

        # Verify only stopped workers removed
        state = swarm.State()
        self.assertIsNone(state.get_worker("stopped-1"))
        self.assertIsNone(state.get_worker("stopped-2"))
        self.assertIsNotNone(state.get_worker("running-1"))

        # Verify print was called for each cleaned worker
        self.assertEqual(mock_print.call_count, 2)

    def test_clean_worker_becomes_running_during_refresh(self):
        """Test skipping worker that becomes running during refresh."""
        state = swarm.State()
        worker = swarm.Worker(
            name="test-worker",
            status="stopped",
            cmd=["echo", "hello"],
            started="2024-01-01T00:00:00",
            cwd="/tmp",
        )
        state.add_worker(worker)

        args = Mock()
        args.name = "test-worker"
        args.all = False

        # Mock refresh to return running (status changed)
        with patch('swarm.refresh_worker_status', return_value="running"), \
             patch('builtins.print') as mock_print:
            with self.assertRaises(SystemExit) as cm:
                swarm.cmd_clean(args)

        # Should error out for single worker case
        self.assertEqual(cm.exception.code, 1)
        mock_print.assert_called_once()
        self.assertIn("cannot clean running worker", mock_print.call_args[0][0])

    def test_clean_without_rm_worktree_flag(self):
        """Test that worktree is not removed when rm_worktree is False."""
        state = swarm.State()
        worktree_path = Path(self.test_dir) / "worktree"
        worktree_path.mkdir()

        worker = swarm.Worker(
            name="test-worker",
            status="stopped",
            cmd=["echo", "hello"],
            started="2024-01-01T00:00:00",
            cwd="/tmp",
            worktree=swarm.WorktreeInfo(
                path=str(worktree_path),
                branch="test-branch",
                base_repo="/repo"
            )
        )
        state.add_worker(worker)

        args = Mock()
        args.name = "test-worker"
        args.all = False
        args.rm_worktree = False
        args.force_dirty = False

        with patch('swarm.refresh_worker_status', return_value="stopped"), \
             patch('swarm.remove_worktree', return_value=(True, "")) as mock_remove_worktree, \
             patch('builtins.print'):
            swarm.cmd_clean(args)

        # Verify remove_worktree was NOT called
        mock_remove_worktree.assert_not_called()

        # Worker should still be removed from state
        state = swarm.State()
        self.assertIsNone(state.get_worker("test-worker"))

    def test_clean_missing_log_files(self):
        """Test cleaning worker when log files don't exist."""
        state = swarm.State()
        worker = swarm.Worker(
            name="test-worker",
            status="stopped",
            cmd=["echo", "hello"],
            started="2024-01-01T00:00:00",
            cwd="/tmp",
        )
        state.add_worker(worker)

        # Don't create log files

        args = Mock()
        args.name = "test-worker"
        args.all = False
        args.rm_worktree = True

        with patch('swarm.refresh_worker_status', return_value="stopped"), \
             patch('builtins.print'):
            # Should not raise an error
            swarm.cmd_clean(args)

        # Verify worker removed
        state = swarm.State()
        self.assertIsNone(state.get_worker("test-worker"))

    def test_clean_all_with_worker_becoming_running(self):
        """Test --all skips workers that become running during refresh."""
        state = swarm.State()

        # Create workers that will appear stopped initially
        worker1 = swarm.Worker(
            name="worker-1",
            status="stopped",
            cmd=["echo", "1"],
            started="2024-01-01T00:00:00",
            cwd="/tmp",
        )
        worker2 = swarm.Worker(
            name="worker-2",
            status="stopped",
            cmd=["echo", "2"],
            started="2024-01-01T00:00:00",
            cwd="/tmp",
        )

        state.add_worker(worker1)
        state.add_worker(worker2)

        args = Mock()
        args.name = None
        args.all = True
        args.rm_worktree = True

        # Mock refresh: worker-1 stays stopped, worker-2 becomes running
        def refresh_side_effect(worker):
            if worker.name == "worker-1":
                return "stopped"
            else:
                return "running"

        with patch('swarm.refresh_worker_status', side_effect=refresh_side_effect), \
             patch('builtins.print') as mock_print:
            swarm.cmd_clean(args)

        # Verify only worker-1 removed
        state = swarm.State()
        self.assertIsNone(state.get_worker("worker-1"))
        self.assertIsNotNone(state.get_worker("worker-2"))

        # Verify output: one cleaned
        # Note: With the fix, worker-2 is filtered out during the initial refresh,
        # so there's no "skipping" warning - it never makes it to workers_to_clean
        calls = [str(call) for call in mock_print.call_args_list]
        self.assertTrue(any("cleaned worker-1" in str(c) for c in calls))
        # worker-2 should NOT appear in output at all (filtered before cleanup)

    def test_clean_all_refreshes_status_before_filtering(self):
        """Test that clean --all refreshes status before filtering stopped workers.

        This test verifies the fix for the state/reality mismatch bug where
        clean --all was using cached status from state.json instead of
        refreshing actual worker status before filtering.
        """
        state = swarm.State()

        # Create a worker with stale "running" status in state
        # but actually stopped (e.g., tmux window was killed externally)
        worker_stale_running = swarm.Worker(
            name="stale-running",
            status="running",  # Cached as running in state.json
            cmd=["echo", "test"],
            started="2024-01-01T00:00:00",
            cwd="/tmp",
        )

        # Create a worker with stale "stopped" status in state
        # but actually running (e.g., process was restarted)
        worker_stale_stopped = swarm.Worker(
            name="stale-stopped",
            status="stopped",  # Cached as stopped in state.json
            cmd=["echo", "test2"],
            started="2024-01-01T00:00:00",
            cwd="/tmp",
        )

        state.add_worker(worker_stale_running)
        state.add_worker(worker_stale_stopped)

        args = Mock()
        args.name = None
        args.all = True
        args.rm_worktree = True

        # Mock refresh to return actual status (opposite of cached)
        def refresh_side_effect(worker):
            if worker.name == "stale-running":
                # Actually stopped (despite cached "running")
                return "stopped"
            elif worker.name == "stale-stopped":
                # Actually running (despite cached "stopped")
                return "running"
            return "stopped"

        with patch('swarm.refresh_worker_status', side_effect=refresh_side_effect) as mock_refresh, \
             patch('builtins.print') as mock_print:
            swarm.cmd_clean(args)

        # Critical assertion: refresh_worker_status should be called for ALL workers
        # during the filtering phase (2 workers) plus once more for the cleaned worker
        # in the cleanup loop (1 worker) = 3 total calls
        self.assertGreaterEqual(mock_refresh.call_count, 2,
                        "refresh_worker_status should be called at least for all workers during filtering")

        # Verify refresh was called during filtering phase (not just cleanup phase)
        # by checking that both workers were passed to refresh
        refresh_call_names = {call[0][0].name for call in mock_refresh.call_args_list}
        self.assertIn("stale-running", refresh_call_names)
        self.assertIn("stale-stopped", refresh_call_names)

        # Verify correct worker was cleaned:
        # "stale-running" should be cleaned (actually stopped)
        # "stale-stopped" should NOT be cleaned (actually running)
        state = swarm.State()
        self.assertIsNone(state.get_worker("stale-running"),
                         "Worker with stale 'running' status but actually stopped should be cleaned")
        self.assertIsNotNone(state.get_worker("stale-stopped"),
                           "Worker with stale 'stopped' status but actually running should NOT be cleaned")

        # Verify the actually-running worker's status was updated in state
        updated_worker = state.get_worker("stale-stopped")
        self.assertEqual(updated_worker.status, "running",
                        "Worker status should be updated to actual 'running' in state after refresh")


if __name__ == "__main__":
    unittest.main()
