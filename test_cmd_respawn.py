#!/usr/bin/env python3
"""Unit tests for cmd_respawn function."""

import json
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest.mock import Mock, patch, call

import swarm


class TestCmdRespawn(unittest.TestCase):
    """Test cmd_respawn function."""

    def setUp(self):
        """Set up test fixtures."""
        # Create temporary swarm directory
        self.temp_dir = tempfile.mkdtemp()
        self.swarm_dir = Path(self.temp_dir) / ".swarm"
        self.logs_dir = self.swarm_dir / "logs"
        self.state_file = self.swarm_dir / "state.json"

        # Patch constants
        self.patcher_swarm_dir = patch.object(swarm, 'SWARM_DIR', self.swarm_dir)
        self.patcher_state_file = patch.object(swarm, 'STATE_FILE', self.state_file)
        self.patcher_logs_dir = patch.object(swarm, 'LOGS_DIR', self.logs_dir)
        self.patcher_swarm_dir.start()
        self.patcher_state_file.start()
        self.patcher_logs_dir.start()

        # Create directories
        self.swarm_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        """Clean up test fixtures."""
        self.patcher_swarm_dir.stop()
        self.patcher_state_file.stop()
        self.patcher_logs_dir.stop()
        # Clean up temp directory
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _create_worker_state(self, worker_data):
        """Helper to create a worker in state."""
        state_data = {"workers": [worker_data]}
        with open(self.state_file, "w") as f:
            json.dump(state_data, f)

    def test_respawn_worker_not_found(self):
        """Test respawn fails when worker doesn't exist."""
        # Create empty state
        self._create_worker_state({
            "name": "other-worker",
            "status": "stopped",
            "cmd": ["echo"],
            "started": "2024-01-01T00:00:00",
            "cwd": "/tmp",
            "env": {},
            "tags": [],
            "tmux": None,
            "worktree": None,
            "pid": 111
        })

        args = Namespace(name="nonexistent", clean_first=False)

        with patch('sys.stderr'):
            with self.assertRaises(SystemExit) as cm:
                swarm.cmd_respawn(args)
            self.assertEqual(cm.exception.code, 1)

    def test_respawn_basic_process(self):
        """Test respawning a basic non-tmux worker."""
        # Create stopped worker in state
        self._create_worker_state({
            "name": "test-worker",
            "status": "stopped",
            "cmd": ["echo", "hello"],
            "started": "2024-01-01T00:00:00",
            "cwd": "/tmp",
            "env": {"FOO": "bar"},
            "tags": ["test"],
            "tmux": None,
            "worktree": None,
            "pid": 12345
        })

        args = Namespace(name="test-worker", clean_first=False)

        with patch('swarm.refresh_worker_status', return_value="stopped"):
            with patch('swarm.spawn_process', return_value=54321) as mock_spawn:
                with patch('builtins.print') as mock_print:
                    swarm.cmd_respawn(args)

                    # Verify spawn was called with original config
                    mock_spawn.assert_called_once()
                    call_args = mock_spawn.call_args
                    self.assertEqual(call_args[0][0], ["echo", "hello"])  # cmd
                    self.assertEqual(call_args[0][2], {"FOO": "bar"})  # env

                    # Verify output
                    mock_print.assert_called_once()
                    self.assertIn("respawned test-worker", mock_print.call_args[0][0])
                    self.assertIn("pid: 54321", mock_print.call_args[0][0])

        # Verify state was updated with new PID
        with open(self.state_file) as f:
            state = json.load(f)
            self.assertEqual(len(state["workers"]), 1)
            worker = state["workers"][0]
            self.assertEqual(worker["name"], "test-worker")
            self.assertEqual(worker["pid"], 54321)
            self.assertEqual(worker["status"], "running")
            self.assertEqual(worker["tags"], ["test"])
            self.assertEqual(worker["env"], {"FOO": "bar"})

    def test_respawn_tmux_worker(self):
        """Test respawning a tmux worker."""
        # Create stopped tmux worker in state
        self._create_worker_state({
            "name": "tmux-worker",
            "status": "stopped",
            "cmd": ["bash"],
            "started": "2024-01-01T00:00:00",
            "cwd": "/tmp",
            "env": {},
            "tags": [],
            "tmux": {"session": "swarm", "window": "tmux-worker"},
            "worktree": None,
            "pid": None
        })

        args = Namespace(name="tmux-worker", clean_first=False)

        with patch('swarm.refresh_worker_status', return_value="stopped"):
            with patch('swarm.create_tmux_window') as mock_tmux:
                with patch('builtins.print') as mock_print:
                    swarm.cmd_respawn(args)

                    # Verify tmux window was created with original config
                    mock_tmux.assert_called_once()
                    call_args = mock_tmux.call_args
                    self.assertEqual(call_args[0][0], "swarm")  # session
                    self.assertEqual(call_args[0][1], "tmux-worker")  # window
                    self.assertEqual(call_args[0][3], ["bash"])  # cmd

                    # Verify output
                    mock_print.assert_called_once()
                    self.assertIn("respawned tmux-worker", mock_print.call_args[0][0])
                    self.assertIn("tmux: swarm:tmux-worker", mock_print.call_args[0][0])

        # Verify state
        with open(self.state_file) as f:
            state = json.load(f)
            worker = state["workers"][0]
            self.assertIsNotNone(worker["tmux"])
            self.assertEqual(worker["tmux"]["session"], "swarm")
            self.assertEqual(worker["status"], "running")

    def test_respawn_kills_running_worker(self):
        """Test that respawn kills a still-running worker first."""
        # Create running worker in state
        self._create_worker_state({
            "name": "running-worker",
            "status": "running",
            "cmd": ["sleep", "100"],
            "started": "2024-01-01T00:00:00",
            "cwd": "/tmp",
            "env": {},
            "tags": [],
            "tmux": None,
            "worktree": None,
            "pid": 12345
        })

        args = Namespace(name="running-worker", clean_first=False)

        with patch('swarm.refresh_worker_status', return_value="running"):
            with patch('swarm.process_alive', return_value=False):
                with patch('os.kill') as mock_kill:
                    with patch('swarm.spawn_process', return_value=54321):
                        with patch('builtins.print'):
                            swarm.cmd_respawn(args)

                            # Verify SIGTERM was sent at least once
                            self.assertTrue(mock_kill.call_count >= 1)
                            # First call should be to the original pid
                            self.assertEqual(mock_kill.call_args_list[0][0][0], 12345)

    def test_respawn_kills_running_tmux_worker(self):
        """Test that respawn kills a still-running tmux worker first."""
        # Create running tmux worker in state
        self._create_worker_state({
            "name": "running-tmux",
            "status": "running",
            "cmd": ["bash"],
            "started": "2024-01-01T00:00:00",
            "cwd": "/tmp",
            "env": {},
            "tags": [],
            "tmux": {"session": "swarm", "window": "running-tmux"},
            "worktree": None,
            "pid": None
        })

        args = Namespace(name="running-tmux", clean_first=False)

        with patch('swarm.refresh_worker_status', return_value="running"):
            with patch('subprocess.run') as mock_run:
                with patch('swarm.create_tmux_window'):
                    with patch('builtins.print'):
                        swarm.cmd_respawn(args)

                        # Verify tmux kill-window was called
                        kill_calls = [c for c in mock_run.call_args_list
                                     if "kill-window" in c[0][0]]
                        self.assertEqual(len(kill_calls), 1)

    def test_respawn_with_worktree_existing(self):
        """Test respawning a worker with an existing worktree."""
        # Create temp worktree dir
        worktree_path = Path(self.temp_dir) / "worktrees" / "wt-worker"
        worktree_path.mkdir(parents=True, exist_ok=True)

        # Create stopped worker with worktree in state
        self._create_worker_state({
            "name": "wt-worker",
            "status": "stopped",
            "cmd": ["echo"],
            "started": "2024-01-01T00:00:00",
            "cwd": str(worktree_path),
            "env": {},
            "tags": [],
            "tmux": None,
            "worktree": {
                "path": str(worktree_path),
                "branch": "feature-branch",
                "base_repo": "/repo"
            },
            "pid": 111
        })

        args = Namespace(name="wt-worker", clean_first=False)

        with patch('swarm.refresh_worker_status', return_value="stopped"):
            with patch('swarm.spawn_process', return_value=222) as mock_spawn:
                with patch('builtins.print'):
                    swarm.cmd_respawn(args)

                    # Verify spawn used existing worktree path
                    call_args = mock_spawn.call_args
                    self.assertEqual(str(call_args[0][1]), str(worktree_path))

        # Verify worktree info preserved in state
        with open(self.state_file) as f:
            state = json.load(f)
            worker = state["workers"][0]
            self.assertIsNotNone(worker["worktree"])
            self.assertEqual(worker["worktree"]["branch"], "feature-branch")

    def test_respawn_clean_first_removes_worktree(self):
        """Test --clean-first removes existing worktree before respawn."""
        # Create temp worktree dir
        worktree_path = Path(self.temp_dir) / "worktrees" / "clean-worker"
        worktree_path.mkdir(parents=True, exist_ok=True)

        # Create stopped worker with worktree in state
        self._create_worker_state({
            "name": "clean-worker",
            "status": "stopped",
            "cmd": ["echo"],
            "started": "2024-01-01T00:00:00",
            "cwd": str(worktree_path),
            "env": {},
            "tags": [],
            "tmux": None,
            "worktree": {
                "path": str(worktree_path),
                "branch": "cleanup-branch",
                "base_repo": "/repo"
            },
            "pid": 111
        })

        args = Namespace(name="clean-worker", clean_first=True, force_dirty=False)

        with patch('swarm.refresh_worker_status', return_value="stopped"):
            with patch('swarm.remove_worktree', return_value=(True, "")) as mock_remove:
                with patch('swarm.create_worktree') as mock_create:
                    with patch('swarm.spawn_process', return_value=333):
                        with patch('builtins.print'):
                            swarm.cmd_respawn(args)

                            # Verify worktree was removed with force=False
                            mock_remove.assert_called_once()
                            self.assertEqual(str(mock_remove.call_args[0][0]), str(worktree_path))
                            self.assertEqual(mock_remove.call_args[1]['force'], False)

                            # Verify worktree was recreated
                            mock_create.assert_called_once()

    def test_respawn_preserves_all_config(self):
        """Test that respawn preserves all original configuration."""
        # Create worker with full config
        self._create_worker_state({
            "name": "full-config",
            "status": "stopped",
            "cmd": ["python", "-c", "print('hello')"],
            "started": "2024-01-01T00:00:00",
            "cwd": "/custom/path",
            "env": {"VAR1": "val1", "VAR2": "val2"},
            "tags": ["tag1", "tag2", "tag3"],
            "tmux": None,
            "worktree": None,
            "pid": 999
        })

        args = Namespace(name="full-config", clean_first=False)

        with patch('swarm.refresh_worker_status', return_value="stopped"):
            with patch('swarm.spawn_process', return_value=1000) as mock_spawn:
                with patch('builtins.print'):
                    swarm.cmd_respawn(args)

                    # Verify all config was passed
                    call_args = mock_spawn.call_args
                    self.assertEqual(call_args[0][0], ["python", "-c", "print('hello')"])
                    self.assertEqual(call_args[0][2], {"VAR1": "val1", "VAR2": "val2"})

        # Verify state preserved tags and env
        with open(self.state_file) as f:
            state = json.load(f)
            worker = state["workers"][0]
            self.assertEqual(worker["tags"], ["tag1", "tag2", "tag3"])
            self.assertEqual(worker["env"], {"VAR1": "val1", "VAR2": "val2"})
            self.assertEqual(worker["cmd"], ["python", "-c", "print('hello')"])


    def test_respawn_worktree_creation_fails(self):
        """Test respawn handles worktree creation failure."""
        import subprocess
        from io import StringIO

        self._create_worker_state({
            "name": "worktree-fail",
            "status": "stopped",
            "cmd": ["echo", "test"],
            "started": "2024-01-01T00:00:00",
            "cwd": "/tmp/worktree",
            "env": {},
            "tags": [],
            "tmux": None,
            "worktree": {
                "path": str(Path(self.temp_dir) / "nonexistent-worktree"),
                "branch": "test-branch",
                "base_repo": str(self.temp_dir)
            },
            "pid": 123
        })

        args = Namespace(name="worktree-fail", clean_first=False, force_dirty=False)

        with patch('swarm.refresh_worker_status', return_value="stopped"), \
             patch('swarm.create_worktree', side_effect=subprocess.CalledProcessError(1, "git")), \
             patch('sys.stderr', new_callable=StringIO) as mock_stderr, \
             self.assertRaises(SystemExit) as cm:
            swarm.cmd_respawn(args)

        self.assertEqual(cm.exception.code, 1)
        self.assertIn("failed to create worktree", mock_stderr.getvalue())

    def test_respawn_tmux_creation_fails(self):
        """Test respawn handles tmux window creation failure."""
        import subprocess
        from io import StringIO

        self._create_worker_state({
            "name": "tmux-fail",
            "status": "stopped",
            "cmd": ["echo", "test"],
            "started": "2024-01-01T00:00:00",
            "cwd": "/tmp",
            "env": {},
            "tags": [],
            "tmux": {"session": "swarm", "window": "tmux-fail", "socket": None},
            "worktree": None,
            "pid": None
        })

        args = Namespace(name="tmux-fail", clean_first=False, force_dirty=False)

        with patch('swarm.refresh_worker_status', return_value="stopped"), \
             patch('swarm.create_tmux_window', side_effect=subprocess.CalledProcessError(1, "tmux")), \
             patch('sys.stderr', new_callable=StringIO) as mock_stderr, \
             self.assertRaises(SystemExit) as cm:
            swarm.cmd_respawn(args)

        self.assertEqual(cm.exception.code, 1)
        self.assertIn("failed to create tmux window", mock_stderr.getvalue())

    def test_respawn_process_spawn_fails(self):
        """Test respawn handles process spawn failure."""
        from io import StringIO

        self._create_worker_state({
            "name": "spawn-fail",
            "status": "stopped",
            "cmd": ["echo", "test"],
            "started": "2024-01-01T00:00:00",
            "cwd": "/tmp",
            "env": {},
            "tags": [],
            "tmux": None,
            "worktree": None,
            "pid": 123
        })

        args = Namespace(name="spawn-fail", clean_first=False, force_dirty=False)

        with patch('swarm.refresh_worker_status', return_value="stopped"), \
             patch('swarm.spawn_process', side_effect=Exception("Spawn failed")), \
             patch('sys.stderr', new_callable=StringIO) as mock_stderr, \
             self.assertRaises(SystemExit) as cm:
            swarm.cmd_respawn(args)

        self.assertEqual(cm.exception.code, 1)
        self.assertIn("failed to spawn process", mock_stderr.getvalue())

    def test_respawn_clean_first_dirty_worktree_fails(self):
        """Test respawn --clean-first fails with dirty worktree without --force-dirty."""
        from io import StringIO

        worktree_path = Path(self.temp_dir) / "dirty-worktree"
        worktree_path.mkdir(exist_ok=True)

        self._create_worker_state({
            "name": "dirty-worker",
            "status": "stopped",
            "cmd": ["echo", "test"],
            "started": "2024-01-01T00:00:00",
            "cwd": str(worktree_path),
            "env": {},
            "tags": [],
            "tmux": None,
            "worktree": {
                "path": str(worktree_path),
                "branch": "test-branch",
                "base_repo": str(self.temp_dir)
            },
            "pid": 123
        })

        args = Namespace(name="dirty-worker", clean_first=True, force_dirty=False)

        with patch('swarm.refresh_worker_status', return_value="stopped"), \
             patch('swarm.remove_worktree', return_value=(False, "worktree has uncommitted changes")), \
             patch('sys.stderr', new_callable=StringIO) as mock_stderr, \
             self.assertRaises(SystemExit) as cm:
            swarm.cmd_respawn(args)

        self.assertEqual(cm.exception.code, 1)
        output = mock_stderr.getvalue()
        self.assertIn("cannot remove worktree", output)
        self.assertIn("uncommitted changes", output)


if __name__ == "__main__":
    unittest.main()
