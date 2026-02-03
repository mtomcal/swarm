#!/usr/bin/env python3
"""Tests for cmd_ls function."""

import io
import json
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


class TestCmdLsBasic(unittest.TestCase):
    """Basic tests for cmd_ls function."""

    def test_ls_empty_state(self):
        """Test ls with no workers returns nothing for table format."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = Path(tmpdir) / "state.json"

            with patch.object(swarm, 'SWARM_DIR', Path(tmpdir)), \
                 patch.object(swarm, 'STATE_FILE', state_file), \
                 patch.object(swarm, 'LOGS_DIR', Path(tmpdir) / "logs"):

                # Create empty state
                state = swarm.State()

                args = Namespace(format="table", status="all", tag=None)

                # Capture stdout
                captured_output = io.StringIO()
                with patch('sys.stdout', captured_output):
                    swarm.cmd_ls(args)

                output = captured_output.getvalue()
                # Empty state should produce no output
                self.assertEqual(output, "")

    def test_ls_json_format_empty(self):
        """Test ls with JSON format on empty state returns empty array."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = Path(tmpdir) / "state.json"

            with patch.object(swarm, 'SWARM_DIR', Path(tmpdir)), \
                 patch.object(swarm, 'STATE_FILE', state_file), \
                 patch.object(swarm, 'LOGS_DIR', Path(tmpdir) / "logs"):

                state = swarm.State()
                args = Namespace(format="json", status="all", tag=None)

                captured_output = io.StringIO()
                with patch('sys.stdout', captured_output):
                    swarm.cmd_ls(args)

                output = captured_output.getvalue()
                self.assertEqual(json.loads(output), [])

    def test_ls_names_format_empty(self):
        """Test ls with names format on empty state returns nothing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = Path(tmpdir) / "state.json"

            with patch.object(swarm, 'SWARM_DIR', Path(tmpdir)), \
                 patch.object(swarm, 'STATE_FILE', state_file), \
                 patch.object(swarm, 'LOGS_DIR', Path(tmpdir) / "logs"):

                state = swarm.State()
                args = Namespace(format="names", status="all", tag=None)

                captured_output = io.StringIO()
                with patch('sys.stdout', captured_output):
                    swarm.cmd_ls(args)

                output = captured_output.getvalue()
                self.assertEqual(output, "")


class TestCmdLsWithWorkers(unittest.TestCase):
    """Tests for cmd_ls with workers in state."""

    def setUp(self):
        """Set up common test fixtures."""
        self.tmpdir = tempfile.mkdtemp()
        self.state_file = Path(self.tmpdir) / "state.json"
        self.patches = [
            patch.object(swarm, 'SWARM_DIR', Path(self.tmpdir)),
            patch.object(swarm, 'STATE_FILE', self.state_file),
            patch.object(swarm, 'LOGS_DIR', Path(self.tmpdir) / "logs"),
            # Mock refresh_worker_status to return current status
            patch.object(swarm, 'refresh_worker_status', side_effect=lambda w: w.status),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        """Clean up patches."""
        for p in self.patches:
            p.stop()
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _create_worker(self, name, status="running", pid=None, tmux=None, worktree=None, tags=None):
        """Helper to create a worker in state."""
        state = swarm.State()
        worker = swarm.Worker(
            name=name,
            status=status,
            cmd=["sleep", "1000"],
            started=datetime.now().isoformat(),  # Use naive datetime
            cwd="/tmp",
            pid=pid,
            tmux=tmux,
            worktree=worktree,
            tags=tags or [],
        )
        state.add_worker(worker)
        return worker

    def test_ls_table_format_single_pid_worker(self):
        """Test ls table format with a single PID worker."""
        self._create_worker("worker-1", pid=12345)

        args = Namespace(format="table", status="all", tag=None)

        captured_output = io.StringIO()
        with patch('sys.stdout', captured_output):
            swarm.cmd_ls(args)

        output = captured_output.getvalue()
        lines = output.strip().split('\n')

        # Check header
        self.assertIn("NAME", lines[0])
        self.assertIn("STATUS", lines[0])
        self.assertIn("PID/WINDOW", lines[0])

        # Check data row
        self.assertIn("worker-1", lines[1])
        self.assertIn("running", lines[1])
        self.assertIn("12345", lines[1])

    def test_ls_table_format_single_tmux_worker(self):
        """Test ls table format with a single tmux worker."""
        tmux_info = swarm.TmuxInfo(session="swarm-test", window="worker-1")
        self._create_worker("worker-1", tmux=tmux_info)

        args = Namespace(format="table", status="all", tag=None)

        captured_output = io.StringIO()
        with patch('sys.stdout', captured_output):
            swarm.cmd_ls(args)

        output = captured_output.getvalue()
        lines = output.strip().split('\n')

        # Check data row shows session:window
        self.assertIn("swarm-test:worker-1", lines[1])

    def test_ls_table_format_worker_with_worktree(self):
        """Test ls table format shows worktree path."""
        worktree_info = swarm.WorktreeInfo(
            path="/tmp/project-worktrees/worker-1",
            branch="worker-1",
            base_repo="/tmp/project"
        )
        self._create_worker("worker-1", pid=12345, worktree=worktree_info)

        args = Namespace(format="table", status="all", tag=None)

        captured_output = io.StringIO()
        with patch('sys.stdout', captured_output):
            swarm.cmd_ls(args)

        output = captured_output.getvalue()
        self.assertIn("/tmp/project-worktrees/worker-1", output)

    def test_ls_table_format_worker_with_tags(self):
        """Test ls table format shows tags."""
        self._create_worker("worker-1", pid=12345, tags=["team-a", "feature"])

        args = Namespace(format="table", status="all", tag=None)

        captured_output = io.StringIO()
        with patch('sys.stdout', captured_output):
            swarm.cmd_ls(args)

        output = captured_output.getvalue()
        self.assertIn("team-a,feature", output)

    def test_ls_table_format_worker_no_pid_or_tmux(self):
        """Test ls table format shows '-' when worker has no PID or tmux."""
        self._create_worker("worker-1")  # No pid or tmux

        args = Namespace(format="table", status="all", tag=None)

        captured_output = io.StringIO()
        with patch('sys.stdout', captured_output):
            swarm.cmd_ls(args)

        output = captured_output.getvalue()
        lines = output.strip().split('\n')
        # PID/WINDOW column should show "-"
        # The "-" should appear in the data row
        self.assertIn("-", lines[1])

    def test_ls_json_format_with_worker(self):
        """Test ls JSON format outputs valid JSON."""
        self._create_worker("worker-1", pid=12345, tags=["test"])

        args = Namespace(format="json", status="all", tag=None)

        captured_output = io.StringIO()
        with patch('sys.stdout', captured_output):
            swarm.cmd_ls(args)

        output = captured_output.getvalue()
        workers = json.loads(output)

        self.assertEqual(len(workers), 1)
        self.assertEqual(workers[0]["name"], "worker-1")
        self.assertEqual(workers[0]["status"], "running")
        self.assertEqual(workers[0]["pid"], 12345)
        self.assertEqual(workers[0]["tags"], ["test"])

    def test_ls_names_format_with_workers(self):
        """Test ls names format outputs one name per line."""
        self._create_worker("alpha", pid=1)
        self._create_worker("beta", pid=2)
        self._create_worker("gamma", pid=3)

        args = Namespace(format="names", status="all", tag=None)

        captured_output = io.StringIO()
        with patch('sys.stdout', captured_output):
            swarm.cmd_ls(args)

        output = captured_output.getvalue()
        names = [line for line in output.strip().split('\n') if line]

        self.assertEqual(len(names), 3)
        self.assertIn("alpha", names)
        self.assertIn("beta", names)
        self.assertIn("gamma", names)


class TestCmdLsFiltering(unittest.TestCase):
    """Tests for cmd_ls filtering functionality."""

    def setUp(self):
        """Set up common test fixtures."""
        self.tmpdir = tempfile.mkdtemp()
        self.state_file = Path(self.tmpdir) / "state.json"
        self.patches = [
            patch.object(swarm, 'SWARM_DIR', Path(self.tmpdir)),
            patch.object(swarm, 'STATE_FILE', self.state_file),
            patch.object(swarm, 'LOGS_DIR', Path(self.tmpdir) / "logs"),
            # Mock refresh_worker_status to return current status
            patch.object(swarm, 'refresh_worker_status', side_effect=lambda w: w.status),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        """Clean up patches."""
        for p in self.patches:
            p.stop()
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _create_worker(self, name, status="running", pid=None, tags=None):
        """Helper to create a worker in state."""
        state = swarm.State()
        worker = swarm.Worker(
            name=name,
            status=status,
            cmd=["sleep", "1000"],
            started=datetime.now().isoformat(),
            cwd="/tmp",
            pid=pid,
            tags=tags or [],
        )
        state.add_worker(worker)
        return worker

    def test_ls_filter_by_status_running(self):
        """Test ls filters by status=running."""
        self._create_worker("running-1", status="running", pid=1)
        self._create_worker("stopped-1", status="stopped", pid=2)
        self._create_worker("running-2", status="running", pid=3)

        args = Namespace(format="names", status="running", tag=None)

        captured_output = io.StringIO()
        with patch('sys.stdout', captured_output):
            swarm.cmd_ls(args)

        output = captured_output.getvalue()
        names = [line for line in output.strip().split('\n') if line]

        self.assertEqual(len(names), 2)
        self.assertIn("running-1", names)
        self.assertIn("running-2", names)
        self.assertNotIn("stopped-1", names)

    def test_ls_filter_by_status_stopped(self):
        """Test ls filters by status=stopped."""
        self._create_worker("running-1", status="running", pid=1)
        self._create_worker("stopped-1", status="stopped", pid=2)
        self._create_worker("stopped-2", status="stopped", pid=3)

        args = Namespace(format="names", status="stopped", tag=None)

        captured_output = io.StringIO()
        with patch('sys.stdout', captured_output):
            swarm.cmd_ls(args)

        output = captured_output.getvalue()
        names = [line for line in output.strip().split('\n') if line]

        self.assertEqual(len(names), 2)
        self.assertIn("stopped-1", names)
        self.assertIn("stopped-2", names)
        self.assertNotIn("running-1", names)

    def test_ls_filter_by_tag(self):
        """Test ls filters by tag."""
        self._create_worker("worker-a", pid=1, tags=["team-a"])
        self._create_worker("worker-b", pid=2, tags=["team-b"])
        self._create_worker("worker-ab", pid=3, tags=["team-a", "team-b"])

        args = Namespace(format="names", status="all", tag="team-a")

        captured_output = io.StringIO()
        with patch('sys.stdout', captured_output):
            swarm.cmd_ls(args)

        output = captured_output.getvalue()
        names = [line for line in output.strip().split('\n') if line]

        self.assertEqual(len(names), 2)
        self.assertIn("worker-a", names)
        self.assertIn("worker-ab", names)
        self.assertNotIn("worker-b", names)

    def test_ls_filter_by_tag_no_match(self):
        """Test ls with tag filter that matches nothing."""
        self._create_worker("worker-1", pid=1, tags=["team-a"])
        self._create_worker("worker-2", pid=2, tags=["team-b"])

        args = Namespace(format="names", status="all", tag="team-c")

        captured_output = io.StringIO()
        with patch('sys.stdout', captured_output):
            swarm.cmd_ls(args)

        output = captured_output.getvalue()
        self.assertEqual(output, "")

    def test_ls_filter_by_status_and_tag(self):
        """Test ls filters by both status and tag."""
        self._create_worker("running-a", status="running", pid=1, tags=["team-a"])
        self._create_worker("stopped-a", status="stopped", pid=2, tags=["team-a"])
        self._create_worker("running-b", status="running", pid=3, tags=["team-b"])

        args = Namespace(format="names", status="running", tag="team-a")

        captured_output = io.StringIO()
        with patch('sys.stdout', captured_output):
            swarm.cmd_ls(args)

        output = captured_output.getvalue()
        names = [line for line in output.strip().split('\n') if line]

        self.assertEqual(len(names), 1)
        self.assertIn("running-a", names)


class TestCmdLsTableFormatting(unittest.TestCase):
    """Tests for cmd_ls table formatting edge cases."""

    def setUp(self):
        """Set up common test fixtures."""
        self.tmpdir = tempfile.mkdtemp()
        self.state_file = Path(self.tmpdir) / "state.json"
        self.patches = [
            patch.object(swarm, 'SWARM_DIR', Path(self.tmpdir)),
            patch.object(swarm, 'STATE_FILE', self.state_file),
            patch.object(swarm, 'LOGS_DIR', Path(self.tmpdir) / "logs"),
            patch.object(swarm, 'refresh_worker_status', side_effect=lambda w: w.status),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        """Clean up patches."""
        for p in self.patches:
            p.stop()
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_ls_table_column_alignment(self):
        """Test that table columns are properly aligned."""
        state = swarm.State()

        # Create workers with different name lengths
        for name, pid in [("a", 1), ("very-long-worker-name", 2), ("med", 3)]:
            worker = swarm.Worker(
                name=name,
                status="running",
                cmd=["sleep"],
                started=datetime.now().isoformat(),
                cwd="/tmp",
                pid=pid,
            )
            state.add_worker(worker)

        args = Namespace(format="table", status="all", tag=None)

        captured_output = io.StringIO()
        with patch('sys.stdout', captured_output):
            swarm.cmd_ls(args)

        output = captured_output.getvalue()
        lines = output.strip().split('\n')

        # All lines should have the same column positions (proper alignment)
        # Check that STATUS column starts at the same position in all lines
        status_positions = [line.find("running") for line in lines[1:] if "running" in line]
        self.assertTrue(len(set(status_positions)) == 1, "STATUS column should be aligned")


if __name__ == "__main__":
    unittest.main()
