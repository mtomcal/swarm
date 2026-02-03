#!/usr/bin/env python3
"""Unit tests for core swarm functions.

Tests the low-level functions that other commands depend on:
- spawn_process: Background process spawning
- process_alive: Process status checking
- tmux_send: Sending text to tmux windows
- tmux_window_exists: Checking tmux window existence
- update_worker_atomic: Atomic state updates
- create_worktree: Git worktree creation
- get_git_root: Git repository root detection
"""

import json
import os
import signal
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import swarm


class TestSpawnProcess(unittest.TestCase):
    """Test the spawn_process function."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.log_prefix = Path(self.temp_dir) / "test-worker"

    def tearDown(self):
        """Clean up test fixtures."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_spawn_process_returns_pid(self):
        """Test spawn_process returns a valid PID."""
        cmd = ["sleep", "0.1"]
        cwd = Path(self.temp_dir)
        env = {}

        pid = swarm.spawn_process(cmd, cwd, env, self.log_prefix)

        self.assertIsInstance(pid, int)
        self.assertGreater(pid, 0)

    def test_spawn_process_creates_log_files(self):
        """Test spawn_process creates stdout and stderr log files."""
        cmd = ["echo", "hello"]
        cwd = Path(self.temp_dir)
        env = {}

        swarm.spawn_process(cmd, cwd, env, self.log_prefix)

        # Wait for process to finish
        import time
        time.sleep(0.2)

        stdout_log = Path(f"{self.log_prefix}.stdout.log")
        stderr_log = Path(f"{self.log_prefix}.stderr.log")

        self.assertTrue(stdout_log.exists(), "stdout log file should be created")
        self.assertTrue(stderr_log.exists(), "stderr log file should be created")

    def test_spawn_process_captures_stdout(self):
        """Test spawn_process captures command output to stdout log."""
        cmd = ["echo", "test output"]
        cwd = Path(self.temp_dir)
        env = {}

        swarm.spawn_process(cmd, cwd, env, self.log_prefix)

        # Wait for process to finish
        import time
        time.sleep(0.2)

        stdout_log = Path(f"{self.log_prefix}.stdout.log")
        content = stdout_log.read_text()
        self.assertIn("test output", content)

    def test_spawn_process_uses_custom_env(self):
        """Test spawn_process passes environment variables to the process."""
        cmd = ["sh", "-c", "echo $TEST_VAR"]
        cwd = Path(self.temp_dir)
        env = {"TEST_VAR": "custom_value"}

        swarm.spawn_process(cmd, cwd, env, self.log_prefix)

        # Wait for process to finish
        import time
        time.sleep(0.2)

        stdout_log = Path(f"{self.log_prefix}.stdout.log")
        content = stdout_log.read_text()
        self.assertIn("custom_value", content)

    def test_spawn_process_uses_cwd(self):
        """Test spawn_process runs command in specified working directory."""
        cmd = ["pwd"]
        cwd = Path(self.temp_dir)
        env = {}

        swarm.spawn_process(cmd, cwd, env, self.log_prefix)

        # Wait for process to finish
        import time
        time.sleep(0.2)

        stdout_log = Path(f"{self.log_prefix}.stdout.log")
        content = stdout_log.read_text().strip()
        self.assertEqual(content, self.temp_dir)

    def test_spawn_process_detaches_from_parent(self):
        """Test spawn_process creates detached process (new session)."""
        cmd = ["sleep", "0.5"]
        cwd = Path(self.temp_dir)
        env = {}

        pid = swarm.spawn_process(cmd, cwd, env, self.log_prefix)

        # Verify the process is running and has a different session
        # os.getsid returns the session ID of the process
        try:
            session_id = os.getsid(pid)
            # The spawned process should be its own session leader
            self.assertEqual(session_id, pid,
                           "Spawned process should be session leader (start_new_session=True)")
        except ProcessLookupError:
            # Process may have already exited, which is OK
            pass


class TestProcessAlive(unittest.TestCase):
    """Test the process_alive function."""

    def test_process_alive_returns_true_for_running_process(self):
        """Test process_alive returns True for a running process."""
        # Start a process that runs briefly
        proc = subprocess.Popen(["sleep", "10"])
        try:
            result = swarm.process_alive(proc.pid)
            self.assertTrue(result, "Should return True for running process")
        finally:
            proc.terminate()
            proc.wait()

    def test_process_alive_returns_false_for_nonexistent_process(self):
        """Test process_alive returns False for a nonexistent PID."""
        # Use a very high PID that shouldn't exist
        # We use a PID that's likely not in use
        result = swarm.process_alive(999999999)
        self.assertFalse(result, "Should return False for nonexistent process")

    def test_process_alive_returns_false_after_process_exits(self):
        """Test process_alive returns False after process terminates."""
        # Start and immediately terminate a process
        proc = subprocess.Popen(["true"])
        proc.wait()

        result = swarm.process_alive(proc.pid)
        self.assertFalse(result, "Should return False for terminated process")

    def test_process_alive_permission_error_returns_true(self):
        """Test process_alive returns True on PermissionError (process exists but can't signal)."""
        with patch('os.kill') as mock_kill:
            mock_kill.side_effect = PermissionError("Operation not permitted")

            result = swarm.process_alive(12345)

            self.assertTrue(result,
                          "Should return True when PermissionError (process exists but can't signal)")
            mock_kill.assert_called_once_with(12345, 0)


class TestTmuxSend(unittest.TestCase):
    """Test the tmux_send function."""

    @patch('subprocess.run')
    @patch('time.sleep')
    def test_tmux_send_with_enter(self, mock_sleep, mock_run):
        """Test tmux_send sends text and Enter key."""
        mock_run.return_value = MagicMock(returncode=0)

        swarm.tmux_send("test-session", "test-window", "hello world", enter=True)

        # Should be called twice: once for text, once for Enter
        self.assertEqual(mock_run.call_count, 2)

        # First call: send text
        first_call = mock_run.call_args_list[0]
        self.assertEqual(first_call[0][0], ["tmux", "send-keys", "-t", "test-session:test-window", "-l", "hello world"])

        # Second call: send Enter
        second_call = mock_run.call_args_list[1]
        self.assertEqual(second_call[0][0], ["tmux", "send-keys", "-t", "test-session:test-window", "Enter"])

    @patch('subprocess.run')
    def test_tmux_send_without_enter(self, mock_run):
        """Test tmux_send sends only text when enter=False."""
        mock_run.return_value = MagicMock(returncode=0)

        swarm.tmux_send("test-session", "test-window", "hello world", enter=False)

        # Should be called once: only for text
        mock_run.assert_called_once()
        call_args = mock_run.call_args[0][0]
        self.assertEqual(call_args, ["tmux", "send-keys", "-t", "test-session:test-window", "-l", "hello world"])

    @patch('subprocess.run')
    @patch('time.sleep')
    def test_tmux_send_with_socket(self, mock_sleep, mock_run):
        """Test tmux_send uses socket parameter."""
        mock_run.return_value = MagicMock(returncode=0)

        swarm.tmux_send("test-session", "test-window", "hello", enter=True, socket="custom-socket")

        # First call should include -L flag
        first_call = mock_run.call_args_list[0]
        self.assertEqual(first_call[0][0],
                        ["tmux", "-L", "custom-socket", "send-keys", "-t", "test-session:test-window", "-l", "hello"])

    @patch('subprocess.run')
    @patch('time.sleep')
    def test_tmux_send_multiline_has_longer_delay(self, mock_sleep, mock_run):
        """Test tmux_send uses longer delay for multiline content."""
        mock_run.return_value = MagicMock(returncode=0)

        # Send multiline content
        swarm.tmux_send("test-session", "test-window", "line1\nline2", enter=True)

        # Check that sleep was called with 0.5 for multiline content
        mock_sleep.assert_called_with(0.5)

    @patch('subprocess.run')
    @patch('time.sleep')
    def test_tmux_send_single_line_has_shorter_delay(self, mock_sleep, mock_run):
        """Test tmux_send uses shorter delay for single line content."""
        mock_run.return_value = MagicMock(returncode=0)

        # Send single line content
        swarm.tmux_send("test-session", "test-window", "single line", enter=True)

        # Check that sleep was called with 0.1 for single line
        mock_sleep.assert_called_with(0.1)


class TestTmuxWindowExists(unittest.TestCase):
    """Test the tmux_window_exists function."""

    @patch('subprocess.run')
    def test_tmux_window_exists_returns_true(self, mock_run):
        """Test tmux_window_exists returns True when window exists."""
        mock_run.return_value = MagicMock(returncode=0)

        result = swarm.tmux_window_exists("test-session", "test-window")

        self.assertTrue(result)
        mock_run.assert_called_once_with(
            ["tmux", "has-session", "-t", "test-session:test-window"],
            capture_output=True,
        )

    @patch('subprocess.run')
    def test_tmux_window_exists_returns_false(self, mock_run):
        """Test tmux_window_exists returns False when window doesn't exist."""
        mock_run.return_value = MagicMock(returncode=1)

        result = swarm.tmux_window_exists("test-session", "test-window")

        self.assertFalse(result)

    @patch('subprocess.run')
    def test_tmux_window_exists_with_socket(self, mock_run):
        """Test tmux_window_exists uses socket parameter."""
        mock_run.return_value = MagicMock(returncode=0)

        result = swarm.tmux_window_exists("test-session", "test-window", socket="custom-socket")

        self.assertTrue(result)
        mock_run.assert_called_once_with(
            ["tmux", "-L", "custom-socket", "has-session", "-t", "test-session:test-window"],
            capture_output=True,
        )


class TestUpdateWorker(unittest.TestCase):
    """Test the update_worker method of State (atomic updates)."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.state_file = Path(self.temp_dir) / "state.json"
        self.logs_dir = Path(self.temp_dir) / "logs"
        self.logs_dir.mkdir(exist_ok=True)

        # Patch SWARM_DIR and STATE_FILE
        self.swarm_dir_patch = patch.object(swarm, 'SWARM_DIR', Path(self.temp_dir))
        self.state_file_patch = patch.object(swarm, 'STATE_FILE', self.state_file)
        self.logs_dir_patch = patch.object(swarm, 'LOGS_DIR', self.logs_dir)

        self.swarm_dir_patch.start()
        self.state_file_patch.start()
        self.logs_dir_patch.start()

    def tearDown(self):
        """Clean up test fixtures."""
        self.swarm_dir_patch.stop()
        self.state_file_patch.stop()
        self.logs_dir_patch.stop()
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _create_state(self, workers):
        """Helper to create a state file with given workers."""
        data = {"workers": [w.to_dict() for w in workers]}
        with open(self.state_file, "w") as f:
            json.dump(data, f)

    def test_update_worker_updates_single_field(self):
        """Test update_worker updates a single field atomically."""
        worker = swarm.Worker(
            name="w1",
            status="running",
            cmd=["echo", "test"],
            started="2026-01-10T12:00:00",
            cwd="/tmp",
        )
        self._create_state([worker])

        state = swarm.State()
        state.update_worker("w1", status="stopped")

        # Reload state and verify
        state2 = swarm.State()
        updated_worker = state2.get_worker("w1")
        self.assertEqual(updated_worker.status, "stopped")

    def test_update_worker_updates_multiple_fields(self):
        """Test update_worker updates multiple fields at once."""
        worker = swarm.Worker(
            name="w1",
            status="running",
            cmd=["echo", "test"],
            started="2026-01-10T12:00:00",
            cwd="/tmp",
            tags=[],
        )
        self._create_state([worker])

        state = swarm.State()
        state.update_worker("w1", status="stopped", tags=["updated"])

        # Reload state and verify
        state2 = swarm.State()
        updated_worker = state2.get_worker("w1")
        self.assertEqual(updated_worker.status, "stopped")
        self.assertEqual(updated_worker.tags, ["updated"])

    def test_update_worker_nonexistent_worker(self):
        """Test update_worker handles nonexistent worker gracefully."""
        self._create_state([])

        state = swarm.State()
        # Should not raise exception for nonexistent worker
        state.update_worker("nonexistent", status="stopped")

        # State should remain empty
        state2 = swarm.State()
        self.assertEqual(len(state2.workers), 0)


class TestGetGitRoot(unittest.TestCase):
    """Test the get_git_root function."""

    @patch('subprocess.run')
    def test_get_git_root_returns_repo_root(self, mock_run):
        """Test get_git_root returns the git repository root."""
        mock_run.return_value = MagicMock(
            stdout="/home/user/project\n",
            returncode=0
        )

        result = swarm.get_git_root()

        self.assertEqual(result, Path("/home/user/project"))
        mock_run.assert_called_once_with(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=True,
        )

    @patch('subprocess.run')
    def test_get_git_root_raises_for_non_repo(self, mock_run):
        """Test get_git_root raises CalledProcessError outside git repo."""
        mock_run.side_effect = subprocess.CalledProcessError(128, "git")

        with self.assertRaises(subprocess.CalledProcessError):
            swarm.get_git_root()


class TestCreateWorktree(unittest.TestCase):
    """Test the create_worktree function."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Clean up test fixtures."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @patch('subprocess.run')
    def test_create_worktree_creates_new_branch(self, mock_run):
        """Test create_worktree creates worktree with new branch."""
        # First call (with -b) fails, second call (without -b) succeeds
        mock_run.side_effect = [
            MagicMock(returncode=1),  # git worktree add -b fails (branch exists)
            MagicMock(returncode=0),  # git worktree add without -b succeeds
        ]

        worktree_path = Path(self.temp_dir) / "worktrees" / "test-worktree"
        swarm.create_worktree(worktree_path, "test-branch")

        # Verify git worktree add was called
        self.assertEqual(mock_run.call_count, 2)
        first_call = mock_run.call_args_list[0]
        self.assertEqual(first_call[0][0], ["git", "worktree", "add", "-b", "test-branch", str(worktree_path)])

    @patch('subprocess.run')
    def test_create_worktree_new_branch_succeeds_first_try(self, mock_run):
        """Test create_worktree succeeds on first try when creating new branch."""
        mock_run.return_value = MagicMock(returncode=0)

        worktree_path = Path(self.temp_dir) / "worktrees" / "test-worktree"
        swarm.create_worktree(worktree_path, "new-branch")

        # Verify only one call was made (first try succeeded)
        mock_run.assert_called_once()
        call_args = mock_run.call_args[0][0]
        self.assertEqual(call_args, ["git", "worktree", "add", "-b", "new-branch", str(worktree_path)])

    @patch('subprocess.run')
    def test_create_worktree_existing_branch(self, mock_run):
        """Test create_worktree uses existing branch if it exists."""
        # First call fails (branch already exists), second call succeeds
        mock_run.side_effect = [
            MagicMock(returncode=1),
            MagicMock(returncode=0),
        ]

        worktree_path = Path(self.temp_dir) / "worktrees" / "test-worktree"
        swarm.create_worktree(worktree_path, "existing-branch")

        # Verify second call used existing branch
        second_call = mock_run.call_args_list[1]
        self.assertEqual(second_call[0][0], ["git", "worktree", "add", str(worktree_path), "existing-branch"])

    def test_create_worktree_creates_parent_directory(self):
        """Test create_worktree creates parent directories as needed."""
        worktree_path = Path(self.temp_dir) / "deeply" / "nested" / "worktree"

        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            swarm.create_worktree(worktree_path, "nested-branch")

        # Verify parent directory was created
        self.assertTrue(worktree_path.parent.exists(), "Parent directories should exist")


class TestRefreshWorkerStatus(unittest.TestCase):
    """Test the refresh_worker_status function."""

    @patch('swarm.tmux_window_exists')
    def test_refresh_tmux_worker_running(self, mock_exists):
        """Test refresh_worker_status returns running for active tmux window."""
        mock_exists.return_value = True

        worker = swarm.Worker(
            name="w1",
            status="running",
            cmd=["echo", "test"],
            started="2026-01-10T12:00:00",
            cwd="/tmp",
            tmux=swarm.TmuxInfo(session="swarm", window="w1"),
        )

        result = swarm.refresh_worker_status(worker)

        self.assertEqual(result, "running")
        mock_exists.assert_called_once_with("swarm", "w1", None)

    @patch('swarm.tmux_window_exists')
    def test_refresh_tmux_worker_stopped(self, mock_exists):
        """Test refresh_worker_status returns stopped for missing tmux window."""
        mock_exists.return_value = False

        worker = swarm.Worker(
            name="w1",
            status="running",
            cmd=["echo", "test"],
            started="2026-01-10T12:00:00",
            cwd="/tmp",
            tmux=swarm.TmuxInfo(session="swarm", window="w1"),
        )

        result = swarm.refresh_worker_status(worker)

        self.assertEqual(result, "stopped")

    @patch('swarm.process_alive')
    def test_refresh_pid_worker_running(self, mock_alive):
        """Test refresh_worker_status returns running for alive PID."""
        mock_alive.return_value = True

        worker = swarm.Worker(
            name="w1",
            status="running",
            cmd=["echo", "test"],
            started="2026-01-10T12:00:00",
            cwd="/tmp",
            pid=12345,
        )

        result = swarm.refresh_worker_status(worker)

        self.assertEqual(result, "running")
        mock_alive.assert_called_once_with(12345)

    @patch('swarm.process_alive')
    def test_refresh_pid_worker_stopped(self, mock_alive):
        """Test refresh_worker_status returns stopped for dead PID."""
        mock_alive.return_value = False

        worker = swarm.Worker(
            name="w1",
            status="running",
            cmd=["echo", "test"],
            started="2026-01-10T12:00:00",
            cwd="/tmp",
            pid=12345,
        )

        result = swarm.refresh_worker_status(worker)

        self.assertEqual(result, "stopped")

    def test_refresh_worker_no_tmux_no_pid(self):
        """Test refresh_worker_status returns stopped for worker with no tmux or pid."""
        worker = swarm.Worker(
            name="w1",
            status="running",
            cmd=["echo", "test"],
            started="2026-01-10T12:00:00",
            cwd="/tmp",
        )

        result = swarm.refresh_worker_status(worker)

        self.assertEqual(result, "stopped")

    @patch('swarm.tmux_window_exists')
    def test_refresh_tmux_worker_with_socket(self, mock_exists):
        """Test refresh_worker_status passes socket to tmux_window_exists."""
        mock_exists.return_value = True

        worker = swarm.Worker(
            name="w1",
            status="running",
            cmd=["echo", "test"],
            started="2026-01-10T12:00:00",
            cwd="/tmp",
            tmux=swarm.TmuxInfo(session="swarm", window="w1", socket="custom-socket"),
        )

        result = swarm.refresh_worker_status(worker)

        self.assertEqual(result, "running")
        mock_exists.assert_called_once_with("swarm", "w1", "custom-socket")


if __name__ == "__main__":
    unittest.main()
