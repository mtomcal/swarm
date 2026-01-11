#!/usr/bin/env python3
"""Test cmd_kill function"""

import json
import os
import signal
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch, Mock
from argparse import Namespace

# Import swarm module
sys.path.insert(0, str(Path(__file__).parent))
import swarm


def test_kill_single_tmux_worker():
    """Test killing a single tmux worker."""
    print("Test: kill single tmux worker...")

    # Create temporary state directory
    with tempfile.TemporaryDirectory() as tmpdir:
        state_file = Path(tmpdir) / "state.json"

        # Patch the global constants
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
                mock_run.assert_called_once_with(
                    ["tmux", "kill-window", "-t", "swarm:test-worker"],
                    capture_output=True
                )

                # Verify worker status was updated
                state = swarm.State()
                updated_worker = state.get_worker("test-worker")
                assert updated_worker.status == "stopped", f"Expected 'stopped', got '{updated_worker.status}'"

    print("  PASS")


def test_kill_worker_not_found():
    """Test killing a worker that doesn't exist."""
    print("Test: kill worker not found...")

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
            try:
                swarm.cmd_kill(args)
                assert False, "Should have exited with error"
            except SystemExit as e:
                assert e.code == 1, f"Expected exit code 1, got {e.code}"

    print("  PASS")


def test_kill_all_workers():
    """Test killing all workers with --all flag."""
    print("Test: kill all workers...")

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
                assert any(
                    call_args[0][0] == ["tmux", "kill-window", "-t", "swarm:worker1"]
                    for call_args in mock_run.call_args_list
                ), "Expected tmux kill-window call for worker1"

                # Verify SIGTERM was sent for worker2
                mock_kill.assert_called_with(99999, signal.SIGTERM)

                # Verify both workers are stopped
                state = swarm.State()
                assert state.get_worker("worker1").status == "stopped"
                assert state.get_worker("worker2").status == "stopped"

    print("  PASS")


def test_kill_with_rm_worktree():
    """Test killing a worker and removing its worktree."""
    print("Test: kill with --rm-worktree...")

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
                mock_run.assert_called_once_with(
                    ["tmux", "kill-window", "-t", "swarm:test-worker"],
                    capture_output=True
                )

                # Verify remove_worktree was called with force=False
                mock_remove_worktree.assert_called_once_with(Path("/tmp/worktrees/test-worker"), force=False)

    print("  PASS")


def main():
    """Run all tests."""
    print("=" * 60)
    print("Testing cmd_kill implementation")
    print("=" * 60)

    tests = [
        test_kill_single_tmux_worker,
        test_kill_worker_not_found,
        test_kill_all_workers,
        test_kill_with_rm_worktree,
    ]

    for test in tests:
        try:
            test()
        except AssertionError as e:
            print(f"  FAIL: {e}")
            sys.exit(1)
        except Exception as e:
            print(f"  ERROR: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)

    print("=" * 60)
    print("All tests passed!")
    print("=" * 60)


if __name__ == "__main__":
    main()
