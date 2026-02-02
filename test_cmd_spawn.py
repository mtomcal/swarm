#!/usr/bin/env python3
"""Unit tests for cmd_spawn function."""

import json
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest.mock import Mock, patch

import swarm


class TestCmdSpawn(unittest.TestCase):
    """Test cmd_spawn function."""

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

    def tearDown(self):
        """Clean up test fixtures."""
        self.patcher_swarm_dir.stop()
        self.patcher_state_file.stop()
        self.patcher_logs_dir.stop()
        # Clean up temp directory
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_spawn_basic_process(self):
        """Test spawning a basic process without tmux."""
        args = Namespace(
            name="test-worker",
            cmd=["--", "echo", "hello"],
            tmux=False,
            worktree=False,
            cwd=None,
            env=[],
            tags=[],
            session="swarm",
            tmux_socket=None,
            ready_wait=False,
            ralph=False,
            prompt_file=None,
            max_iterations=None
        )

        with patch('swarm.spawn_process', return_value=12345) as mock_spawn:
            with patch('builtins.print') as mock_print:
                swarm.cmd_spawn(args)

                # Verify spawn was called correctly
                mock_spawn.assert_called_once()
                call_args = mock_spawn.call_args
                self.assertEqual(call_args[0][0], ["echo", "hello"])  # cmd
                self.assertIsInstance(call_args[0][1], Path)  # cwd
                self.assertEqual(call_args[0][2], {})  # env

                # Verify output
                mock_print.assert_called_once()
                self.assertIn("spawned test-worker", mock_print.call_args[0][0])
                self.assertIn("pid: 12345", mock_print.call_args[0][0])

        # Verify state was saved
        with open(self.state_file) as f:
            state = json.load(f)
            self.assertEqual(len(state["workers"]), 1)
            worker = state["workers"][0]
            self.assertEqual(worker["name"], "test-worker")
            self.assertEqual(worker["cmd"], ["echo", "hello"])
            self.assertEqual(worker["pid"], 12345)
            self.assertIsNone(worker["tmux"])

    def test_spawn_with_tmux(self):
        """Test spawning with tmux."""
        args = Namespace(
            name="tmux-worker",
            cmd=["--", "bash"],
            tmux=True,
            session="swarm",
            tmux_socket=None,
            ready_wait=False,
            worktree=False,
            cwd=None,
            env=[],
            tags=[],
            ralph=False,
            prompt_file=None,
            max_iterations=None
        )

        with patch('swarm.create_tmux_window') as mock_tmux:
            with patch('builtins.print') as mock_print:
                swarm.cmd_spawn(args)

                # Verify tmux window was created
                mock_tmux.assert_called_once()
                call_args = mock_tmux.call_args
                self.assertEqual(call_args[0][0], "swarm")  # session
                self.assertEqual(call_args[0][1], "tmux-worker")  # window
                self.assertEqual(call_args[0][3], ["bash"])  # cmd

                # Verify output
                mock_print.assert_called_once()
                self.assertIn("spawned tmux-worker", mock_print.call_args[0][0])
                self.assertIn("tmux: swarm:tmux-worker", mock_print.call_args[0][0])

        # Verify state
        with open(self.state_file) as f:
            state = json.load(f)
            worker = state["workers"][0]
            self.assertIsNotNone(worker["tmux"])
            self.assertEqual(worker["tmux"]["session"], "swarm")
            self.assertEqual(worker["tmux"]["window"], "tmux-worker")
            self.assertIsNone(worker["pid"])

    def test_spawn_no_command_error(self):
        """Test that missing command produces error."""
        args = Namespace(
            name="test",
            cmd=[],
            tmux=False,
            worktree=False,
            cwd=None,
            env=[],
            tags=[],
            session="swarm",
            tmux_socket=None,
            ready_wait=False,
            ralph=False,
            prompt_file=None,
            max_iterations=None
        )

        with patch('sys.stderr'):
            with self.assertRaises(SystemExit) as cm:
                swarm.cmd_spawn(args)
            self.assertEqual(cm.exception.code, 1)

    def test_spawn_duplicate_name_error(self):
        """Test that duplicate name is rejected."""
        # Create initial worker
        args1 = Namespace(
            name="duplicate",
            cmd=["--", "sleep", "1"],
            tmux=False,
            worktree=False,
            cwd=None,
            env=[],
            tags=[],
            session="swarm",
            tmux_socket=None,
            ready_wait=False,
            ralph=False,
            prompt_file=None,
            max_iterations=None
        )

        with patch('swarm.spawn_process', return_value=111):
            with patch('builtins.print'):
                swarm.cmd_spawn(args1)

        # Try to create duplicate
        args2 = Namespace(
            name="duplicate",
            cmd=["--", "sleep", "2"],
            tmux=False,
            worktree=False,
            cwd=None,
            env=[],
            tags=[],
            session="swarm",
            tmux_socket=None,
            ready_wait=False,
            ralph=False,
            prompt_file=None,
            max_iterations=None
        )

        with patch('sys.stderr'):
            with self.assertRaises(SystemExit) as cm:
                swarm.cmd_spawn(args2)
            self.assertEqual(cm.exception.code, 1)

    def test_spawn_with_env_vars(self):
        """Test environment variable parsing."""
        args = Namespace(
            name="env-test",
            cmd=["--", "printenv"],
            tmux=False,
            worktree=False,
            cwd=None,
            env=["FOO=bar", "BAZ=qux"],
            tags=[],
            session="swarm",
            tmux_socket=None,
            ready_wait=False,
            ralph=False,
            prompt_file=None,
            max_iterations=None
        )

        with patch('swarm.spawn_process', return_value=222) as mock_spawn:
            with patch('builtins.print'):
                swarm.cmd_spawn(args)

                # Verify env was parsed correctly
                call_args = mock_spawn.call_args
                env_dict = call_args[0][2]
                self.assertEqual(env_dict["FOO"], "bar")
                self.assertEqual(env_dict["BAZ"], "qux")

        # Verify state
        with open(self.state_file) as f:
            state = json.load(f)
            worker = state["workers"][0]
            self.assertEqual(worker["env"]["FOO"], "bar")
            self.assertEqual(worker["env"]["BAZ"], "qux")

    def test_spawn_with_tags(self):
        """Test tag assignment."""
        args = Namespace(
            name="tagged",
            cmd=["--", "echo", "test"],
            tmux=False,
            worktree=False,
            cwd=None,
            env=[],
            tags=["important", "test"],
            session="swarm",
            tmux_socket=None,
            ready_wait=False,
            ralph=False,
            prompt_file=None,
            max_iterations=None
        )

        with patch('swarm.spawn_process', return_value=333):
            with patch('builtins.print'):
                swarm.cmd_spawn(args)

        # Verify tags in state
        with open(self.state_file) as f:
            state = json.load(f)
            worker = state["workers"][0]
            self.assertEqual(worker["tags"], ["important", "test"])

    def test_spawn_strips_leading_double_dash(self):
        """Test that leading -- is stripped from command."""
        args = Namespace(
            name="dash-test",
            cmd=["--", "echo", "hello"],
            tmux=False,
            worktree=False,
            cwd=None,
            env=[],
            tags=[],
            session="swarm",
            tmux_socket=None,
            ready_wait=False,
            ralph=False,
            prompt_file=None,
            max_iterations=None
        )

        with patch('swarm.spawn_process', return_value=444) as mock_spawn:
            with patch('builtins.print'):
                swarm.cmd_spawn(args)

                # Verify -- was stripped
                call_args = mock_spawn.call_args
                cmd = call_args[0][0]
                self.assertEqual(cmd, ["echo", "hello"])
                self.assertNotIn("--", cmd)

    def test_spawn_invalid_env_format(self):
        """Test that invalid env format is rejected."""
        args = Namespace(
            name="bad-env",
            cmd=["--", "echo", "test"],
            tmux=False,
            worktree=False,
            cwd=None,
            env=["INVALID"],  # Missing =
            tags=[],
            session="swarm",
            tmux_socket=None,
            ready_wait=False,
            ralph=False,
            prompt_file=None,
            max_iterations=None
        )

        with patch('sys.stderr'):
            with self.assertRaises(SystemExit) as cm:
                swarm.cmd_spawn(args)
            self.assertEqual(cm.exception.code, 1)


if __name__ == "__main__":
    unittest.main()
