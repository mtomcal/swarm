#!/usr/bin/env python3
"""Tests for swarm heartbeat command - TDD tests for heartbeat subcommands."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from argparse import Namespace
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock

import swarm


class TestDurationParsing(unittest.TestCase):
    """Test duration string parsing."""

    def test_parse_seconds(self):
        """Test parsing bare seconds."""
        self.assertEqual(swarm.parse_duration("3600"), 3600)
        self.assertEqual(swarm.parse_duration("60"), 60)
        self.assertEqual(swarm.parse_duration("1"), 1)

    def test_parse_minutes(self):
        """Test parsing minutes."""
        self.assertEqual(swarm.parse_duration("30m"), 1800)
        self.assertEqual(swarm.parse_duration("1m"), 60)
        self.assertEqual(swarm.parse_duration("90m"), 5400)

    def test_parse_hours(self):
        """Test parsing hours."""
        self.assertEqual(swarm.parse_duration("4h"), 14400)
        self.assertEqual(swarm.parse_duration("1h"), 3600)
        self.assertEqual(swarm.parse_duration("24h"), 86400)

    def test_parse_seconds_with_unit(self):
        """Test parsing seconds with 's' suffix."""
        self.assertEqual(swarm.parse_duration("90s"), 90)
        self.assertEqual(swarm.parse_duration("3600s"), 3600)

    def test_parse_combinations(self):
        """Test parsing combined durations."""
        self.assertEqual(swarm.parse_duration("1h30m"), 5400)
        self.assertEqual(swarm.parse_duration("2h30m15s"), 9015)
        self.assertEqual(swarm.parse_duration("1h1m1s"), 3661)

    def test_parse_case_insensitive(self):
        """Test parsing is case insensitive."""
        self.assertEqual(swarm.parse_duration("4H"), 14400)
        self.assertEqual(swarm.parse_duration("30M"), 1800)
        self.assertEqual(swarm.parse_duration("1H30M"), 5400)

    def test_parse_invalid_empty(self):
        """Test empty string raises error."""
        with self.assertRaises(ValueError):
            swarm.parse_duration("")

    def test_parse_invalid_negative(self):
        """Test negative values raise error."""
        with self.assertRaises(ValueError):
            swarm.parse_duration("-1")

    def test_parse_invalid_zero(self):
        """Test zero raises error."""
        with self.assertRaises(ValueError):
            swarm.parse_duration("0")
        with self.assertRaises(ValueError):
            swarm.parse_duration("0h")

    def test_parse_invalid_format(self):
        """Test invalid format raises error."""
        with self.assertRaises(ValueError):
            swarm.parse_duration("abc")
        with self.assertRaises(ValueError):
            swarm.parse_duration("4x")


class TestFormatDuration(unittest.TestCase):
    """Test duration formatting.

    Note: format_duration uses the existing format with spaces
    like "1h 0m" for hours, "1m 0s" for minutes.
    """

    def test_format_seconds(self):
        """Test formatting seconds."""
        self.assertEqual(swarm.format_duration(30), "30s")
        self.assertEqual(swarm.format_duration(59), "59s")

    def test_format_minutes(self):
        """Test formatting minutes."""
        self.assertEqual(swarm.format_duration(60), "1m 0s")
        self.assertEqual(swarm.format_duration(120), "2m 0s")
        self.assertEqual(swarm.format_duration(1800), "30m 0s")

    def test_format_hours(self):
        """Test formatting hours."""
        self.assertEqual(swarm.format_duration(3600), "1h 0m")
        self.assertEqual(swarm.format_duration(7200), "2h 0m")
        self.assertEqual(swarm.format_duration(14400), "4h 0m")

    def test_format_combinations(self):
        """Test formatting combined durations."""
        self.assertEqual(swarm.format_duration(3661), "1h 1m")  # Existing format drops seconds
        self.assertEqual(swarm.format_duration(5400), "1h 30m")
        self.assertEqual(swarm.format_duration(90), "1m 30s")

    def test_format_zero(self):
        """Test formatting zero."""
        self.assertEqual(swarm.format_duration(0), "0s")


class TestHeartbeatSubparser(unittest.TestCase):
    """Test that heartbeat subparser is correctly configured."""

    def test_heartbeat_subparser_exists(self):
        """Test that 'heartbeat' subcommand is recognized."""
        result = subprocess.run(
            [sys.executable, 'swarm.py', 'heartbeat', '--help'],
            capture_output=True,
            text=True
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn('heartbeat', result.stdout.lower())

    def test_heartbeat_start_subcommand_exists(self):
        """Test that 'heartbeat start' subcommand is recognized."""
        result = subprocess.run(
            [sys.executable, 'swarm.py', 'heartbeat', 'start', '--help'],
            capture_output=True,
            text=True
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn('interval', result.stdout.lower())

    def test_heartbeat_stop_subcommand_exists(self):
        """Test that 'heartbeat stop' subcommand is recognized."""
        result = subprocess.run(
            [sys.executable, 'swarm.py', 'heartbeat', 'stop', '--help'],
            capture_output=True,
            text=True
        )
        self.assertEqual(result.returncode, 0)

    def test_heartbeat_list_subcommand_exists(self):
        """Test that 'heartbeat list' subcommand is recognized."""
        result = subprocess.run(
            [sys.executable, 'swarm.py', 'heartbeat', 'list', '--help'],
            capture_output=True,
            text=True
        )
        self.assertEqual(result.returncode, 0)

    def test_heartbeat_status_subcommand_exists(self):
        """Test that 'heartbeat status' subcommand is recognized."""
        result = subprocess.run(
            [sys.executable, 'swarm.py', 'heartbeat', 'status', '--help'],
            capture_output=True,
            text=True
        )
        self.assertEqual(result.returncode, 0)

    def test_heartbeat_pause_subcommand_exists(self):
        """Test that 'heartbeat pause' subcommand is recognized."""
        result = subprocess.run(
            [sys.executable, 'swarm.py', 'heartbeat', 'pause', '--help'],
            capture_output=True,
            text=True
        )
        self.assertEqual(result.returncode, 0)

    def test_heartbeat_resume_subcommand_exists(self):
        """Test that 'heartbeat resume' subcommand is recognized."""
        result = subprocess.run(
            [sys.executable, 'swarm.py', 'heartbeat', 'resume', '--help'],
            capture_output=True,
            text=True
        )
        self.assertEqual(result.returncode, 0)

    def test_heartbeat_requires_subcommand(self):
        """Test that heartbeat without subcommand shows error."""
        result = subprocess.run(
            [sys.executable, 'swarm.py', 'heartbeat'],
            capture_output=True,
            text=True
        )
        self.assertNotEqual(result.returncode, 0)


class TestHeartbeatHelpTextConstants(unittest.TestCase):
    """Test heartbeat CLI help text module-level constants for coverage."""

    def test_heartbeat_help_description_exists(self):
        """Test HEARTBEAT_HELP_DESCRIPTION constant exists and has content."""
        self.assertIn('nudges', swarm.HEARTBEAT_HELP_DESCRIPTION)
        self.assertIn('rate limits', swarm.HEARTBEAT_HELP_DESCRIPTION)

    def test_heartbeat_help_epilog_exists(self):
        """Test HEARTBEAT_HELP_EPILOG constant exists and has content."""
        self.assertIn('Quick Reference', swarm.HEARTBEAT_HELP_EPILOG)
        self.assertIn('Common Patterns', swarm.HEARTBEAT_HELP_EPILOG)

    def test_heartbeat_start_help_description_exists(self):
        """Test HEARTBEAT_START_HELP_DESCRIPTION constant exists."""
        self.assertIn('heartbeat', swarm.HEARTBEAT_START_HELP_DESCRIPTION.lower())

    def test_heartbeat_start_help_epilog_exists(self):
        """Test HEARTBEAT_START_HELP_EPILOG constant has examples."""
        self.assertIn('Examples:', swarm.HEARTBEAT_START_HELP_EPILOG)
        self.assertIn('Duration Format:', swarm.HEARTBEAT_START_HELP_EPILOG)
        self.assertIn('Safety:', swarm.HEARTBEAT_START_HELP_EPILOG)


class TestCmdHeartbeatStart(unittest.TestCase):
    """Test cmd_heartbeat_start function."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.original_swarm_dir = swarm.SWARM_DIR
        self.original_heartbeats_dir = swarm.HEARTBEATS_DIR
        swarm.SWARM_DIR = Path(self.temp_dir) / ".swarm"
        swarm.HEARTBEATS_DIR = swarm.SWARM_DIR / "heartbeats"
        swarm.HEARTBEATS_DIR.mkdir(parents=True, exist_ok=True)
        swarm.HEARTBEAT_LOCK_FILE = swarm.SWARM_DIR / "heartbeat.lock"

    def tearDown(self):
        """Clean up test fixtures."""
        swarm.SWARM_DIR = self.original_swarm_dir
        swarm.HEARTBEATS_DIR = self.original_heartbeats_dir
        swarm.HEARTBEAT_LOCK_FILE = swarm.SWARM_DIR / "heartbeat.lock"
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @patch('swarm.State')
    def test_start_worker_not_found(self, mock_state_cls):
        """Test starting heartbeat for non-existent worker fails."""
        mock_state = MagicMock()
        mock_state.get_worker.return_value = None
        mock_state_cls.return_value = mock_state

        args = Namespace(
            worker='nonexistent',
            interval='4h',
            expire=None,
            message='continue',
            force=False
        )

        with self.assertRaises(SystemExit) as ctx:
            swarm.cmd_heartbeat_start(args)

        self.assertEqual(ctx.exception.code, 1)

    @patch('swarm.State')
    def test_start_non_tmux_worker_fails(self, mock_state_cls):
        """Test starting heartbeat for non-tmux worker fails."""
        mock_worker = MagicMock()
        mock_worker.tmux = None  # Not a tmux worker
        mock_state = MagicMock()
        mock_state.get_worker.return_value = mock_worker
        mock_state_cls.return_value = mock_state

        args = Namespace(
            worker='bg-job',
            interval='4h',
            expire=None,
            message='continue',
            force=False
        )

        with self.assertRaises(SystemExit) as ctx:
            swarm.cmd_heartbeat_start(args)

        self.assertEqual(ctx.exception.code, 1)

    @patch('swarm.State')
    def test_start_invalid_interval_fails(self, mock_state_cls):
        """Test starting heartbeat with invalid interval fails."""
        mock_worker = MagicMock()
        mock_worker.tmux = MagicMock()  # Is a tmux worker
        mock_state = MagicMock()
        mock_state.get_worker.return_value = mock_worker
        mock_state_cls.return_value = mock_state

        args = Namespace(
            worker='builder',
            interval='invalid',
            expire=None,
            message='continue',
            force=False
        )

        with self.assertRaises(SystemExit) as ctx:
            swarm.cmd_heartbeat_start(args)

        self.assertEqual(ctx.exception.code, 1)

    @patch('swarm.State')
    def test_start_creates_heartbeat_state(self, mock_state_cls):
        """Test starting heartbeat creates state file."""
        mock_worker = MagicMock()
        mock_worker.tmux = MagicMock()
        mock_state = MagicMock()
        mock_state.get_worker.return_value = mock_worker
        mock_state_cls.return_value = mock_state

        args = Namespace(
            worker='builder',
            interval='4h',
            expire='24h',
            message='continue',
            force=False
        )

        swarm.cmd_heartbeat_start(args)

        # Check state file was created
        state_path = swarm.HEARTBEATS_DIR / "builder.json"
        self.assertTrue(state_path.exists())

        # Load and verify state
        with open(state_path) as f:
            data = json.load(f)

        self.assertEqual(data['worker_name'], 'builder')
        self.assertEqual(data['interval_seconds'], 14400)  # 4h
        self.assertEqual(data['message'], 'continue')
        self.assertEqual(data['status'], 'active')
        self.assertEqual(data['beat_count'], 0)
        self.assertIsNotNone(data['expire_at'])

    @patch('swarm.State')
    def test_start_without_expiration(self, mock_state_cls):
        """Test starting heartbeat without expiration."""
        mock_worker = MagicMock()
        mock_worker.tmux = MagicMock()
        mock_state = MagicMock()
        mock_state.get_worker.return_value = mock_worker
        mock_state_cls.return_value = mock_state

        args = Namespace(
            worker='builder',
            interval='4h',
            expire=None,
            message='continue',
            force=False
        )

        swarm.cmd_heartbeat_start(args)

        state_path = swarm.HEARTBEATS_DIR / "builder.json"
        with open(state_path) as f:
            data = json.load(f)

        self.assertIsNone(data['expire_at'])

    @patch('swarm.State')
    def test_start_existing_heartbeat_fails_without_force(self, mock_state_cls):
        """Test starting heartbeat when one exists fails without --force."""
        # Create existing heartbeat
        existing_state = swarm.HeartbeatState(
            worker_name='builder',
            interval_seconds=3600,
            message='continue',
            created_at=datetime.now(timezone.utc).isoformat(),
            status='active',
        )
        swarm.save_heartbeat_state(existing_state)

        mock_worker = MagicMock()
        mock_worker.tmux = MagicMock()
        mock_state = MagicMock()
        mock_state.get_worker.return_value = mock_worker
        mock_state_cls.return_value = mock_state

        args = Namespace(
            worker='builder',
            interval='4h',
            expire=None,
            message='continue',
            force=False
        )

        with self.assertRaises(SystemExit) as ctx:
            swarm.cmd_heartbeat_start(args)

        self.assertEqual(ctx.exception.code, 1)

    @patch('swarm.State')
    def test_start_existing_heartbeat_replaced_with_force(self, mock_state_cls):
        """Test starting heartbeat when one exists succeeds with --force."""
        # Create existing heartbeat
        existing_state = swarm.HeartbeatState(
            worker_name='builder',
            interval_seconds=3600,
            message='old message',
            created_at=datetime.now(timezone.utc).isoformat(),
            status='active',
        )
        swarm.save_heartbeat_state(existing_state)

        mock_worker = MagicMock()
        mock_worker.tmux = MagicMock()
        mock_state = MagicMock()
        mock_state.get_worker.return_value = mock_worker
        mock_state_cls.return_value = mock_state

        args = Namespace(
            worker='builder',
            interval='4h',
            expire=None,
            message='new message',
            force=True
        )

        swarm.cmd_heartbeat_start(args)

        # Load and verify state was replaced
        state_path = swarm.HEARTBEATS_DIR / "builder.json"
        with open(state_path) as f:
            data = json.load(f)

        self.assertEqual(data['message'], 'new message')
        self.assertEqual(data['interval_seconds'], 14400)


class TestCmdHeartbeatStop(unittest.TestCase):
    """Test cmd_heartbeat_stop function."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.original_swarm_dir = swarm.SWARM_DIR
        self.original_heartbeats_dir = swarm.HEARTBEATS_DIR
        swarm.SWARM_DIR = Path(self.temp_dir) / ".swarm"
        swarm.HEARTBEATS_DIR = swarm.SWARM_DIR / "heartbeats"
        swarm.HEARTBEATS_DIR.mkdir(parents=True, exist_ok=True)
        swarm.HEARTBEAT_LOCK_FILE = swarm.SWARM_DIR / "heartbeat.lock"

    def tearDown(self):
        """Clean up test fixtures."""
        swarm.SWARM_DIR = self.original_swarm_dir
        swarm.HEARTBEATS_DIR = self.original_heartbeats_dir
        swarm.HEARTBEAT_LOCK_FILE = swarm.SWARM_DIR / "heartbeat.lock"
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_stop_nonexistent_heartbeat(self):
        """Test stopping non-existent heartbeat prints message."""
        args = Namespace(worker='nonexistent')

        # Should not raise, just print message
        swarm.cmd_heartbeat_stop(args)

    def test_stop_updates_status(self):
        """Test stopping heartbeat updates status to stopped."""
        # Create heartbeat
        state = swarm.HeartbeatState(
            worker_name='builder',
            interval_seconds=3600,
            message='continue',
            created_at=datetime.now(timezone.utc).isoformat(),
            status='active',
        )
        swarm.save_heartbeat_state(state)

        args = Namespace(worker='builder')
        swarm.cmd_heartbeat_stop(args)

        # Verify status changed
        updated = swarm.load_heartbeat_state('builder')
        self.assertEqual(updated.status, 'stopped')


class TestCmdHeartbeatList(unittest.TestCase):
    """Test cmd_heartbeat_list function."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.original_swarm_dir = swarm.SWARM_DIR
        self.original_heartbeats_dir = swarm.HEARTBEATS_DIR
        swarm.SWARM_DIR = Path(self.temp_dir) / ".swarm"
        swarm.HEARTBEATS_DIR = swarm.SWARM_DIR / "heartbeats"
        swarm.HEARTBEATS_DIR.mkdir(parents=True, exist_ok=True)
        swarm.HEARTBEAT_LOCK_FILE = swarm.SWARM_DIR / "heartbeat.lock"

    def tearDown(self):
        """Clean up test fixtures."""
        swarm.SWARM_DIR = self.original_swarm_dir
        swarm.HEARTBEATS_DIR = self.original_heartbeats_dir
        swarm.HEARTBEAT_LOCK_FILE = swarm.SWARM_DIR / "heartbeat.lock"
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_list_empty(self):
        """Test listing when no heartbeats exist."""
        args = Namespace(format='table')
        # Should not raise
        swarm.cmd_heartbeat_list(args)

    def test_list_json_empty(self):
        """Test listing JSON when no heartbeats exist."""
        args = Namespace(format='json')
        # Should not raise
        swarm.cmd_heartbeat_list(args)

    def test_list_with_heartbeats(self):
        """Test listing existing heartbeats."""
        # Create heartbeats
        for name in ['worker1', 'worker2']:
            state = swarm.HeartbeatState(
                worker_name=name,
                interval_seconds=3600,
                message='continue',
                created_at=datetime.now(timezone.utc).isoformat(),
                status='active',
            )
            swarm.save_heartbeat_state(state)

        args = Namespace(format='table')
        # Should not raise
        swarm.cmd_heartbeat_list(args)


class TestCmdHeartbeatPauseResume(unittest.TestCase):
    """Test cmd_heartbeat_pause and cmd_heartbeat_resume functions."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.original_swarm_dir = swarm.SWARM_DIR
        self.original_heartbeats_dir = swarm.HEARTBEATS_DIR
        swarm.SWARM_DIR = Path(self.temp_dir) / ".swarm"
        swarm.HEARTBEATS_DIR = swarm.SWARM_DIR / "heartbeats"
        swarm.HEARTBEATS_DIR.mkdir(parents=True, exist_ok=True)
        swarm.HEARTBEAT_LOCK_FILE = swarm.SWARM_DIR / "heartbeat.lock"

    def tearDown(self):
        """Clean up test fixtures."""
        swarm.SWARM_DIR = self.original_swarm_dir
        swarm.HEARTBEATS_DIR = self.original_heartbeats_dir
        swarm.HEARTBEAT_LOCK_FILE = swarm.SWARM_DIR / "heartbeat.lock"
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_pause_active_heartbeat(self):
        """Test pausing an active heartbeat."""
        state = swarm.HeartbeatState(
            worker_name='builder',
            interval_seconds=3600,
            message='continue',
            created_at=datetime.now(timezone.utc).isoformat(),
            status='active',
        )
        swarm.save_heartbeat_state(state)

        args = Namespace(worker='builder')
        swarm.cmd_heartbeat_pause(args)

        updated = swarm.load_heartbeat_state('builder')
        self.assertEqual(updated.status, 'paused')

    def test_pause_nonexistent_heartbeat_fails(self):
        """Test pausing non-existent heartbeat fails."""
        args = Namespace(worker='nonexistent')

        with self.assertRaises(SystemExit) as ctx:
            swarm.cmd_heartbeat_pause(args)

        self.assertEqual(ctx.exception.code, 1)

    def test_pause_non_active_heartbeat_fails(self):
        """Test pausing non-active heartbeat fails."""
        state = swarm.HeartbeatState(
            worker_name='builder',
            interval_seconds=3600,
            message='continue',
            created_at=datetime.now(timezone.utc).isoformat(),
            status='stopped',
        )
        swarm.save_heartbeat_state(state)

        args = Namespace(worker='builder')

        with self.assertRaises(SystemExit) as ctx:
            swarm.cmd_heartbeat_pause(args)

        self.assertEqual(ctx.exception.code, 1)

    def test_resume_paused_heartbeat(self):
        """Test resuming a paused heartbeat."""
        state = swarm.HeartbeatState(
            worker_name='builder',
            interval_seconds=3600,
            message='continue',
            created_at=datetime.now(timezone.utc).isoformat(),
            status='paused',
        )
        swarm.save_heartbeat_state(state)

        args = Namespace(worker='builder')
        swarm.cmd_heartbeat_resume(args)

        updated = swarm.load_heartbeat_state('builder')
        self.assertEqual(updated.status, 'active')

    def test_resume_nonexistent_heartbeat_fails(self):
        """Test resuming non-existent heartbeat fails."""
        args = Namespace(worker='nonexistent')

        with self.assertRaises(SystemExit) as ctx:
            swarm.cmd_heartbeat_resume(args)

        self.assertEqual(ctx.exception.code, 1)

    def test_resume_non_paused_heartbeat_fails(self):
        """Test resuming non-paused heartbeat fails."""
        state = swarm.HeartbeatState(
            worker_name='builder',
            interval_seconds=3600,
            message='continue',
            created_at=datetime.now(timezone.utc).isoformat(),
            status='active',
        )
        swarm.save_heartbeat_state(state)

        args = Namespace(worker='builder')

        with self.assertRaises(SystemExit) as ctx:
            swarm.cmd_heartbeat_resume(args)

        self.assertEqual(ctx.exception.code, 1)


if __name__ == '__main__':
    unittest.main()
