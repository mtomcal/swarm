#!/usr/bin/env python3
"""Tests for worktree protection against uncommitted changes.

Issue: Prevent accidental deletion of worktrees with uncommitted changes.
"""

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import swarm


class TestWorktreeIsDirty(unittest.TestCase):
    """Test cases for worktree_is_dirty function."""

    def test_dirty_with_unstaged_changes(self):
        """Test detection of unstaged changes."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Initialize a git repo
            subprocess.run(["git", "init"], cwd=tmpdir, capture_output=True, timeout=30)
            subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=tmpdir, capture_output=True, timeout=30)
            subprocess.run(["git", "config", "user.name", "Test"], cwd=tmpdir, capture_output=True, timeout=30)

            # Create and commit a file
            test_file = Path(tmpdir) / "test.txt"
            test_file.write_text("initial content")
            subprocess.run(["git", "add", "test.txt"], cwd=tmpdir, capture_output=True, timeout=30)
            subprocess.run(["git", "commit", "-m", "initial"], cwd=tmpdir, capture_output=True, timeout=30)

            # Modify the file (unstaged change)
            test_file.write_text("modified content")

            # Should detect as dirty
            self.assertTrue(swarm.worktree_is_dirty(Path(tmpdir)))

    def test_dirty_with_staged_changes(self):
        """Test detection of staged changes."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Initialize a git repo
            subprocess.run(["git", "init"], cwd=tmpdir, capture_output=True, timeout=30)
            subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=tmpdir, capture_output=True, timeout=30)
            subprocess.run(["git", "config", "user.name", "Test"], cwd=tmpdir, capture_output=True, timeout=30)

            # Create and commit a file
            test_file = Path(tmpdir) / "test.txt"
            test_file.write_text("initial content")
            subprocess.run(["git", "add", "test.txt"], cwd=tmpdir, capture_output=True, timeout=30)
            subprocess.run(["git", "commit", "-m", "initial"], cwd=tmpdir, capture_output=True, timeout=30)

            # Stage a new file
            new_file = Path(tmpdir) / "new.txt"
            new_file.write_text("new content")
            subprocess.run(["git", "add", "new.txt"], cwd=tmpdir, capture_output=True, timeout=30)

            # Should detect as dirty
            self.assertTrue(swarm.worktree_is_dirty(Path(tmpdir)))

    def test_dirty_with_untracked_files(self):
        """Test detection of untracked files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Initialize a git repo
            subprocess.run(["git", "init"], cwd=tmpdir, capture_output=True, timeout=30)
            subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=tmpdir, capture_output=True, timeout=30)
            subprocess.run(["git", "config", "user.name", "Test"], cwd=tmpdir, capture_output=True, timeout=30)

            # Create and commit a file
            test_file = Path(tmpdir) / "test.txt"
            test_file.write_text("initial content")
            subprocess.run(["git", "add", "test.txt"], cwd=tmpdir, capture_output=True, timeout=30)
            subprocess.run(["git", "commit", "-m", "initial"], cwd=tmpdir, capture_output=True, timeout=30)

            # Create untracked file
            untracked = Path(tmpdir) / "untracked.txt"
            untracked.write_text("untracked content")

            # Should detect as dirty
            self.assertTrue(swarm.worktree_is_dirty(Path(tmpdir)))

    def test_clean_worktree(self):
        """Test clean worktree is detected as not dirty."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Initialize a git repo
            subprocess.run(["git", "init"], cwd=tmpdir, capture_output=True, timeout=30)
            subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=tmpdir, capture_output=True, timeout=30)
            subprocess.run(["git", "config", "user.name", "Test"], cwd=tmpdir, capture_output=True, timeout=30)

            # Create and commit a file
            test_file = Path(tmpdir) / "test.txt"
            test_file.write_text("initial content")
            subprocess.run(["git", "add", "test.txt"], cwd=tmpdir, capture_output=True, timeout=30)
            subprocess.run(["git", "commit", "-m", "initial"], cwd=tmpdir, capture_output=True, timeout=30)

            # Should NOT detect as dirty
            self.assertFalse(swarm.worktree_is_dirty(Path(tmpdir)))

    def test_nonexistent_path_not_dirty(self):
        """Test nonexistent path returns False."""
        self.assertFalse(swarm.worktree_is_dirty(Path("/nonexistent/path")))


class TestRemoveWorktreeProtection(unittest.TestCase):
    """Test cases for remove_worktree protection."""

    def test_refuses_dirty_worktree_without_force(self):
        """Test that dirty worktree is not removed without force."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Initialize a git repo
            subprocess.run(["git", "init"], cwd=tmpdir, capture_output=True, timeout=30)
            subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=tmpdir, capture_output=True, timeout=30)
            subprocess.run(["git", "config", "user.name", "Test"], cwd=tmpdir, capture_output=True, timeout=30)

            # Create and commit a file
            test_file = Path(tmpdir) / "test.txt"
            test_file.write_text("initial content")
            subprocess.run(["git", "add", "test.txt"], cwd=tmpdir, capture_output=True, timeout=30)
            subprocess.run(["git", "commit", "-m", "initial"], cwd=tmpdir, capture_output=True, timeout=30)

            # Make it dirty
            test_file.write_text("modified content")

            # Attempt to remove without force
            success, msg = swarm.remove_worktree(Path(tmpdir), force=False)

            # Should fail
            self.assertFalse(success)
            self.assertIn("uncommitted change", msg)

            # Directory should still exist
            self.assertTrue(Path(tmpdir).exists())

    def test_removes_dirty_worktree_with_force_mocked(self):
        """Test that dirty worktree is removed with force (mocked git remove)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Initialize a git repo
            subprocess.run(["git", "init"], cwd=tmpdir, capture_output=True, timeout=30)
            subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=tmpdir, capture_output=True, timeout=30)
            subprocess.run(["git", "config", "user.name", "Test"], cwd=tmpdir, capture_output=True, timeout=30)

            # Create and commit a file
            test_file = Path(tmpdir) / "test.txt"
            test_file.write_text("initial content")
            subprocess.run(["git", "add", "test.txt"], cwd=tmpdir, capture_output=True, timeout=30)
            subprocess.run(["git", "commit", "-m", "initial"], cwd=tmpdir, capture_output=True, timeout=30)

            # Make it dirty
            test_file.write_text("modified content")

            # Mock the git worktree remove command since we can't do a real worktree in temp dir
            with patch('subprocess.run') as mock_run:
                mock_run.return_value = Mock(returncode=0)

                # Attempt to remove with force
                success, msg = swarm.remove_worktree(Path(tmpdir), force=True)

                # Should succeed
                self.assertTrue(success)
                self.assertEqual(msg, "")

                # Verify git worktree remove --force was called
                mock_run.assert_called_once()
                call_args = mock_run.call_args[0][0]
                self.assertIn("worktree", call_args)
                self.assertIn("remove", call_args)
                self.assertIn("--force", call_args)

    def test_removes_clean_worktree_without_force_mocked(self):
        """Test that clean worktree is removed without force (mocked git remove)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Initialize a git repo
            subprocess.run(["git", "init"], cwd=tmpdir, capture_output=True, timeout=30)
            subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=tmpdir, capture_output=True, timeout=30)
            subprocess.run(["git", "config", "user.name", "Test"], cwd=tmpdir, capture_output=True, timeout=30)

            # Create and commit a file
            test_file = Path(tmpdir) / "test.txt"
            test_file.write_text("initial content")
            subprocess.run(["git", "add", "test.txt"], cwd=tmpdir, capture_output=True, timeout=30)
            subprocess.run(["git", "commit", "-m", "initial"], cwd=tmpdir, capture_output=True, timeout=30)

            # Mock only the final git worktree remove call (not the status check)
            original_run = subprocess.run

            def mock_run_selective(cmd, *args, **kwargs):
                # Let git status through, mock git worktree remove
                if "worktree" in cmd and "remove" in cmd:
                    return Mock(returncode=0)
                return original_run(cmd, *args, **kwargs)

            with patch('subprocess.run', side_effect=mock_run_selective):
                # Attempt to remove without force (should succeed since clean)
                success, msg = swarm.remove_worktree(Path(tmpdir), force=False)

                # Should succeed
                self.assertTrue(success)
                self.assertEqual(msg, "")

    def test_nonexistent_path_succeeds(self):
        """Test that removing nonexistent path succeeds."""
        success, msg = swarm.remove_worktree(Path("/nonexistent/path"), force=False)
        self.assertTrue(success)
        self.assertEqual(msg, "")


class TestCleanCommandProtection(unittest.TestCase):
    """Test cases for clean command worktree protection."""

    def setUp(self):
        """Set up test fixtures."""
        self.original_swarm_dir = swarm.SWARM_DIR
        self.original_state_file = swarm.STATE_FILE
        self.original_logs_dir = swarm.LOGS_DIR

        # Create temp directory for state
        self.temp_dir = tempfile.mkdtemp()
        swarm.SWARM_DIR = Path(self.temp_dir)
        swarm.STATE_FILE = swarm.SWARM_DIR / "state.json"
        swarm.LOGS_DIR = swarm.SWARM_DIR / "logs"
        swarm.ensure_dirs()

    def tearDown(self):
        """Restore original paths."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
        swarm.SWARM_DIR = self.original_swarm_dir
        swarm.STATE_FILE = self.original_state_file
        swarm.LOGS_DIR = self.original_logs_dir

    def test_clean_preserves_dirty_worktree(self):
        """Test that clean preserves worktree with uncommitted changes."""
        # Create worker with worktree
        state = swarm.State()
        worktree_path = Path(self.temp_dir) / "test-worktree"
        worktree_path.mkdir()  # Create the directory so it exists

        worker = swarm.Worker(
            name="test-worker",
            status="stopped",
            cmd=["echo", "test"],
            started="2024-01-01T00:00:00",
            cwd=str(worktree_path),
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

        # Mock remove_worktree to return failure (dirty)
        with patch('swarm.refresh_worker_status', return_value="stopped"), \
             patch('swarm.remove_worktree', return_value=(False, "worktree has 2 uncommitted change(s)")) as mock_remove, \
             patch('builtins.print') as mock_print:
            swarm.cmd_clean(args)

        # Verify remove_worktree was called
        mock_remove.assert_called_once()

        # Verify warning was printed (to stderr)
        all_print_calls = str(mock_print.call_args_list)
        self.assertIn("preserving", all_print_calls.lower(), f"Expected warning about preserved worktree, got: {all_print_calls}")

    def test_clean_force_dirty_removes_worktree(self):
        """Test that clean --force-dirty removes dirty worktree."""
        state = swarm.State()
        worktree_path = Path(self.temp_dir) / "test-worktree"
        worktree_path.mkdir()  # Create the directory so it exists

        worker = swarm.Worker(
            name="test-worker",
            status="stopped",
            cmd=["echo", "test"],
            started="2024-01-01T00:00:00",
            cwd=str(worktree_path),
            worktree=swarm.WorktreeInfo(
                path=str(worktree_path),
                branch="test-branch",
                base_repo="/repo"
            )
        )
        state.add_worker(worker)

        # Mock args with force_dirty=True
        args = Mock()
        args.name = "test-worker"
        args.all = False
        args.rm_worktree = True
        args.force_dirty = True

        with patch('swarm.refresh_worker_status', return_value="stopped"), \
             patch('swarm.remove_worktree', return_value=(True, "")) as mock_remove, \
             patch('builtins.print'):
            swarm.cmd_clean(args)

        # Verify remove_worktree was called with force=True
        mock_remove.assert_called_once()
        self.assertEqual(mock_remove.call_args[1]['force'], True)


if __name__ == '__main__':
    unittest.main()
