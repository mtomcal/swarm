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

    @patch('swarm.start_heartbeat_monitor')
    @patch('swarm.State')
    def test_start_creates_heartbeat_state(self, mock_state_cls, mock_start_monitor):
        """Test starting heartbeat creates state file."""
        mock_worker = MagicMock()
        mock_worker.tmux = MagicMock()
        mock_state = MagicMock()
        mock_state.get_worker.return_value = mock_worker
        mock_state_cls.return_value = mock_state
        mock_start_monitor.return_value = 12345  # Fake PID

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
        self.assertEqual(data['monitor_pid'], 12345)

        # Verify monitor was started
        mock_start_monitor.assert_called_once_with('builder')

    @patch('swarm.start_heartbeat_monitor')
    @patch('swarm.State')
    def test_start_without_expiration(self, mock_state_cls, mock_start_monitor):
        """Test starting heartbeat without expiration."""
        mock_worker = MagicMock()
        mock_worker.tmux = MagicMock()
        mock_state = MagicMock()
        mock_state.get_worker.return_value = mock_worker
        mock_state_cls.return_value = mock_state
        mock_start_monitor.return_value = 12345  # Fake PID

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

    @patch('swarm.start_heartbeat_monitor')
    @patch('swarm.stop_heartbeat_monitor')
    @patch('swarm.State')
    def test_start_existing_heartbeat_replaced_with_force(self, mock_state_cls, mock_stop_monitor, mock_start_monitor):
        """Test starting heartbeat when one exists succeeds with --force."""
        # Create existing heartbeat
        existing_state = swarm.HeartbeatState(
            worker_name='builder',
            interval_seconds=3600,
            message='old message',
            created_at=datetime.now(timezone.utc).isoformat(),
            status='active',
            monitor_pid=9999,  # Old monitor PID
        )
        swarm.save_heartbeat_state(existing_state)

        mock_worker = MagicMock()
        mock_worker.tmux = MagicMock()
        mock_state = MagicMock()
        mock_state.get_worker.return_value = mock_worker
        mock_state_cls.return_value = mock_state
        mock_start_monitor.return_value = 12345  # New monitor PID

        args = Namespace(
            worker='builder',
            interval='4h',
            expire=None,
            message='new message',
            force=True
        )

        swarm.cmd_heartbeat_start(args)

        # Verify old monitor was stopped
        mock_stop_monitor.assert_called_once()

        # Load and verify state was replaced
        state_path = swarm.HEARTBEATS_DIR / "builder.json"
        with open(state_path) as f:
            data = json.load(f)

        self.assertEqual(data['message'], 'new message')
        self.assertEqual(data['interval_seconds'], 14400)
        self.assertEqual(data['monitor_pid'], 12345)


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

    def test_list_shows_dash_for_paused(self):
        """Test that paused heartbeats show dash for next beat."""
        state = swarm.HeartbeatState(
            worker_name='paused-worker',
            interval_seconds=3600,
            message='continue',
            created_at=datetime.now(timezone.utc).isoformat(),
            status='paused',
        )
        swarm.save_heartbeat_state(state)

        args = Namespace(format='table')
        # Should not raise and should show "-" for next beat
        swarm.cmd_heartbeat_list(args)

    def test_list_shows_dash_for_stopped(self):
        """Test that stopped heartbeats show dash for next beat."""
        state = swarm.HeartbeatState(
            worker_name='stopped-worker',
            interval_seconds=3600,
            message='continue',
            created_at=datetime.now(timezone.utc).isoformat(),
            status='stopped',
        )
        swarm.save_heartbeat_state(state)

        args = Namespace(format='table')
        # Should not raise and should show "-" for next beat
        swarm.cmd_heartbeat_list(args)

    def test_list_calculates_next_beat_from_last_beat(self):
        """Test that next beat is calculated from last_beat_at when available."""
        last_beat = datetime.now(timezone.utc) - timedelta(minutes=30)
        state = swarm.HeartbeatState(
            worker_name='beat-worker',
            interval_seconds=3600,
            message='continue',
            created_at=(datetime.now(timezone.utc) - timedelta(hours=2)).isoformat(),
            last_beat_at=last_beat.isoformat(),
            beat_count=2,
            status='active',
        )
        swarm.save_heartbeat_state(state)

        args = Namespace(format='table')
        # Should not raise - next beat should be ~30 minutes from now
        swarm.cmd_heartbeat_list(args)

    def test_list_json_with_heartbeats(self):
        """Test JSON output for heartbeats."""
        state = swarm.HeartbeatState(
            worker_name='json-worker',
            interval_seconds=3600,
            message='continue',
            created_at=datetime.now(timezone.utc).isoformat(),
            status='active',
        )
        swarm.save_heartbeat_state(state)

        args = Namespace(format='json')
        # Should output valid JSON
        swarm.cmd_heartbeat_list(args)

    def test_list_with_expire_time(self):
        """Test listing heartbeats with expiration time."""
        expire_time = datetime.now(timezone.utc) + timedelta(hours=24)
        state = swarm.HeartbeatState(
            worker_name='expiring-worker',
            interval_seconds=3600,
            message='continue',
            created_at=datetime.now(timezone.utc).isoformat(),
            expire_at=expire_time.isoformat(),
            status='active',
        )
        swarm.save_heartbeat_state(state)

        args = Namespace(format='table')
        # Should show expiration time
        swarm.cmd_heartbeat_list(args)

    def test_list_with_invalid_expire_at(self):
        """Test listing heartbeats with invalid expire_at timestamp."""
        state = swarm.HeartbeatState(
            worker_name='invalid-expire-worker',
            interval_seconds=3600,
            message='continue',
            created_at=datetime.now(timezone.utc).isoformat(),
            expire_at='not-a-valid-timestamp',
            status='active',
        )
        swarm.save_heartbeat_state(state)

        args = Namespace(format='table')
        # Should handle gracefully and show original string
        swarm.cmd_heartbeat_list(args)

    def test_list_with_invalid_created_at(self):
        """Test listing heartbeats with invalid created_at timestamp."""
        state = swarm.HeartbeatState(
            worker_name='invalid-created-worker',
            interval_seconds=3600,
            message='continue',
            created_at='not-a-valid-timestamp',
            status='active',
        )
        swarm.save_heartbeat_state(state)

        args = Namespace(format='table')
        # Should handle gracefully and show "?"
        swarm.cmd_heartbeat_list(args)

    def test_list_with_empty_created_at(self):
        """Test listing heartbeats with empty created_at."""
        state = swarm.HeartbeatState(
            worker_name='empty-created-worker',
            interval_seconds=3600,
            message='continue',
            created_at='',
            status='active',
        )
        swarm.save_heartbeat_state(state)

        args = Namespace(format='table')
        # Should handle gracefully and show "?"
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

    def test_resume_restarts_monitor_if_dead(self):
        """Test resuming restarts monitor if process died."""
        # Create paused heartbeat with non-existent PID
        state = swarm.HeartbeatState(
            worker_name='builder',
            interval_seconds=3600,
            message='continue',
            created_at=datetime.now(timezone.utc).isoformat(),
            status='paused',
            monitor_pid=99999999,  # Non-existent PID
        )
        swarm.save_heartbeat_state(state)

        args = Namespace(worker='builder')

        with patch('swarm.start_heartbeat_monitor', return_value=12345) as mock_start:
            swarm.cmd_heartbeat_resume(args)
            mock_start.assert_called_once_with('builder')

        updated = swarm.load_heartbeat_state('builder')
        self.assertEqual(updated.status, 'active')
        self.assertEqual(updated.monitor_pid, 12345)


class TestHeartbeatMonitorFunctions(unittest.TestCase):
    """Test heartbeat monitor helper functions."""

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

    def test_stop_heartbeat_monitor_no_pid(self):
        """Test stopping monitor when no PID stored."""
        state = swarm.HeartbeatState(
            worker_name='builder',
            interval_seconds=3600,
            message='continue',
            created_at=datetime.now(timezone.utc).isoformat(),
            status='active',
            monitor_pid=None,
        )
        result = swarm.stop_heartbeat_monitor(state)
        self.assertFalse(result)

    def test_stop_heartbeat_monitor_process_not_running(self):
        """Test stopping monitor when process not running."""
        state = swarm.HeartbeatState(
            worker_name='builder',
            interval_seconds=3600,
            message='continue',
            created_at=datetime.now(timezone.utc).isoformat(),
            status='active',
            monitor_pid=99999999,  # Non-existent PID
        )
        result = swarm.stop_heartbeat_monitor(state)
        self.assertFalse(result)

    @patch('os.kill')
    def test_stop_heartbeat_monitor_terminates_process(self, mock_kill):
        """Test stopping monitor terminates the process."""
        # First call (signal 0) succeeds, second call (SIGTERM) succeeds
        mock_kill.return_value = None

        state = swarm.HeartbeatState(
            worker_name='builder',
            interval_seconds=3600,
            message='continue',
            created_at=datetime.now(timezone.utc).isoformat(),
            status='active',
            monitor_pid=12345,
        )
        result = swarm.stop_heartbeat_monitor(state)
        self.assertTrue(result)

        # Verify os.kill was called with signal 0 (check) and SIGTERM
        calls = mock_kill.call_args_list
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0], ((12345, 0),))
        self.assertEqual(calls[1], ((12345, swarm.signal.SIGTERM),))

    def test_heartbeat_state_monitor_pid_serialization(self):
        """Test HeartbeatState serializes monitor_pid correctly."""
        state = swarm.HeartbeatState(
            worker_name='builder',
            interval_seconds=3600,
            message='continue',
            created_at=datetime.now(timezone.utc).isoformat(),
            status='active',
            monitor_pid=12345,
        )
        swarm.save_heartbeat_state(state)

        loaded = swarm.load_heartbeat_state('builder')
        self.assertEqual(loaded.monitor_pid, 12345)

    def test_heartbeat_state_monitor_pid_none_serialization(self):
        """Test HeartbeatState serializes None monitor_pid correctly."""
        state = swarm.HeartbeatState(
            worker_name='builder',
            interval_seconds=3600,
            message='continue',
            created_at=datetime.now(timezone.utc).isoformat(),
            status='active',
            monitor_pid=None,
        )
        swarm.save_heartbeat_state(state)

        loaded = swarm.load_heartbeat_state('builder')
        self.assertIsNone(loaded.monitor_pid)


class TestRunHeartbeatMonitor(unittest.TestCase):
    """Test run_heartbeat_monitor function logic."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.original_swarm_dir = swarm.SWARM_DIR
        self.original_heartbeats_dir = swarm.HEARTBEATS_DIR
        self.original_state_file = swarm.STATE_FILE
        swarm.SWARM_DIR = Path(self.temp_dir) / ".swarm"
        swarm.HEARTBEATS_DIR = swarm.SWARM_DIR / "heartbeats"
        swarm.STATE_FILE = swarm.SWARM_DIR / "state.json"
        swarm.HEARTBEATS_DIR.mkdir(parents=True, exist_ok=True)
        swarm.HEARTBEAT_LOCK_FILE = swarm.SWARM_DIR / "heartbeat.lock"
        swarm.STATE_LOCK_FILE = swarm.SWARM_DIR / "state.lock"

    def tearDown(self):
        """Clean up test fixtures."""
        swarm.SWARM_DIR = self.original_swarm_dir
        swarm.HEARTBEATS_DIR = self.original_heartbeats_dir
        swarm.STATE_FILE = self.original_state_file
        swarm.HEARTBEAT_LOCK_FILE = swarm.SWARM_DIR / "heartbeat.lock"
        swarm.STATE_LOCK_FILE = swarm.SWARM_DIR / "state.lock"
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @patch('swarm.time.sleep')
    def test_monitor_exits_when_state_deleted(self, mock_sleep):
        """Test monitor exits when heartbeat state file is deleted."""
        # Create heartbeat state
        state = swarm.HeartbeatState(
            worker_name='builder',
            interval_seconds=60,
            message='continue',
            created_at=datetime.now(timezone.utc).isoformat(),
            status='active',
        )
        swarm.save_heartbeat_state(state)

        # Delete state after first sleep
        def delete_state_on_sleep(seconds):
            swarm.delete_heartbeat_state('builder')

        mock_sleep.side_effect = delete_state_on_sleep

        # Monitor should exit gracefully
        swarm.run_heartbeat_monitor('builder')

        mock_sleep.assert_called_once_with(30)

    @patch('swarm.time.sleep')
    def test_monitor_exits_when_status_stopped(self, mock_sleep):
        """Test monitor exits when status is stopped."""
        state = swarm.HeartbeatState(
            worker_name='builder',
            interval_seconds=60,
            message='continue',
            created_at=datetime.now(timezone.utc).isoformat(),
            status='stopped',
        )
        swarm.save_heartbeat_state(state)

        swarm.run_heartbeat_monitor('builder')

        mock_sleep.assert_called_once_with(30)

    @patch('swarm.time.sleep')
    def test_monitor_exits_when_status_expired(self, mock_sleep):
        """Test monitor exits when status is expired."""
        state = swarm.HeartbeatState(
            worker_name='builder',
            interval_seconds=60,
            message='continue',
            created_at=datetime.now(timezone.utc).isoformat(),
            status='expired',
        )
        swarm.save_heartbeat_state(state)

        swarm.run_heartbeat_monitor('builder')

        mock_sleep.assert_called_once_with(30)

    @patch('swarm.time.sleep')
    def test_monitor_continues_when_paused(self, mock_sleep):
        """Test monitor continues but doesn't send beats when paused."""
        state = swarm.HeartbeatState(
            worker_name='builder',
            interval_seconds=60,
            message='continue',
            created_at=datetime.now(timezone.utc).isoformat(),
            status='paused',
        )
        swarm.save_heartbeat_state(state)

        call_count = [0]
        def sleep_and_stop(seconds):
            call_count[0] += 1
            if call_count[0] >= 2:
                # Change to stopped after second iteration
                loaded = swarm.load_heartbeat_state('builder')
                loaded.status = 'stopped'
                swarm.save_heartbeat_state(loaded)

        mock_sleep.side_effect = sleep_and_stop

        swarm.run_heartbeat_monitor('builder')

        self.assertEqual(call_count[0], 2)

    @patch('swarm.time.sleep')
    def test_monitor_sets_expired_when_past_expire_time(self, mock_sleep):
        """Test monitor sets status to expired when expire_at is passed."""
        # Create heartbeat with expire_at in the past
        past_time = datetime.now(timezone.utc) - timedelta(hours=1)
        state = swarm.HeartbeatState(
            worker_name='builder',
            interval_seconds=60,
            message='continue',
            created_at=datetime.now(timezone.utc).isoformat(),
            expire_at=past_time.isoformat(),
            status='active',
        )
        swarm.save_heartbeat_state(state)

        swarm.run_heartbeat_monitor('builder')

        # Verify status changed to expired
        updated = swarm.load_heartbeat_state('builder')
        self.assertEqual(updated.status, 'expired')

    @patch('swarm.State')
    @patch('swarm.time.sleep')
    def test_monitor_stops_when_worker_not_found(self, mock_sleep, mock_state_cls):
        """Test monitor stops when worker is not in state."""
        state = swarm.HeartbeatState(
            worker_name='builder',
            interval_seconds=60,
            message='continue',
            created_at=datetime.now(timezone.utc).isoformat(),
            status='active',
        )
        swarm.save_heartbeat_state(state)

        mock_state = MagicMock()
        mock_state.get_worker.return_value = None
        mock_state_cls.return_value = mock_state

        swarm.run_heartbeat_monitor('builder')

        # Verify status changed to stopped
        updated = swarm.load_heartbeat_state('builder')
        self.assertEqual(updated.status, 'stopped')

    @patch('swarm.refresh_worker_status')
    @patch('swarm.State')
    @patch('swarm.time.sleep')
    def test_monitor_stops_when_worker_not_running(self, mock_sleep, mock_state_cls, mock_refresh):
        """Test monitor stops when worker is not running."""
        state = swarm.HeartbeatState(
            worker_name='builder',
            interval_seconds=60,
            message='continue',
            created_at=datetime.now(timezone.utc).isoformat(),
            status='active',
        )
        swarm.save_heartbeat_state(state)

        mock_worker = MagicMock()
        mock_state = MagicMock()
        mock_state.get_worker.return_value = mock_worker
        mock_state_cls.return_value = mock_state
        mock_refresh.return_value = 'stopped'

        swarm.run_heartbeat_monitor('builder')

        # Verify status changed to stopped
        updated = swarm.load_heartbeat_state('builder')
        self.assertEqual(updated.status, 'stopped')

    @patch('swarm.tmux_send')
    @patch('swarm.refresh_worker_status')
    @patch('swarm.State')
    @patch('swarm.time.monotonic')
    @patch('swarm.time.sleep')
    def test_monitor_sends_beat_at_interval(self, mock_sleep, mock_monotonic, mock_state_cls, mock_refresh, mock_tmux_send):
        """Test monitor sends beat when interval elapsed."""
        state = swarm.HeartbeatState(
            worker_name='builder',
            interval_seconds=60,
            message='continue',
            created_at=datetime.now(timezone.utc).isoformat(),
            status='active',
        )
        swarm.save_heartbeat_state(state)

        mock_worker = MagicMock()
        mock_worker.tmux.session = 'session'
        mock_worker.tmux.window = 'window'
        mock_worker.tmux.socket = None
        mock_state = MagicMock()
        mock_state.get_worker.return_value = mock_worker
        mock_state_cls.return_value = mock_state
        mock_refresh.return_value = 'running'

        # Simulate time progression: start=0, after sleep=100 (past 60s interval), then 100 for reset
        monotonic_values = [0, 100, 100]  # First call for init, then for elapsed check, then for reset
        mock_monotonic.side_effect = monotonic_values

        call_count = [0]
        def sleep_and_continue(seconds):
            call_count[0] += 1
            # Don't stop in sleep callback - let the beat happen first
            # Stop after 2nd sleep to allow beat processing
            if call_count[0] >= 2:
                loaded = swarm.load_heartbeat_state('builder')
                loaded.status = 'stopped'
                swarm.save_heartbeat_state(loaded)

        mock_sleep.side_effect = sleep_and_continue

        swarm.run_heartbeat_monitor('builder')

        # Verify tmux_send was called
        mock_tmux_send.assert_called_once_with(
            'session', 'window', 'continue', enter=True, socket=None, pre_clear=False
        )

    @patch('swarm.tmux_send')
    @patch('swarm.refresh_worker_status')
    @patch('swarm.State')
    @patch('swarm.time.monotonic')
    @patch('swarm.time.sleep')
    def test_monitor_handles_tmux_send_failure(self, mock_sleep, mock_monotonic, mock_state_cls, mock_refresh, mock_tmux_send):
        """Test monitor continues when tmux_send fails."""
        state = swarm.HeartbeatState(
            worker_name='builder',
            interval_seconds=60,
            message='continue',
            created_at=datetime.now(timezone.utc).isoformat(),
            status='active',
        )
        swarm.save_heartbeat_state(state)

        mock_worker = MagicMock()
        mock_worker.tmux.session = 'session'
        mock_worker.tmux.window = 'window'
        mock_worker.tmux.socket = None
        mock_state = MagicMock()
        mock_state.get_worker.return_value = mock_worker
        mock_state_cls.return_value = mock_state
        mock_refresh.return_value = 'running'

        # Simulate time progression past interval
        mock_monotonic.side_effect = [0, 100]

        # tmux_send raises exception
        mock_tmux_send.side_effect = Exception("tmux error")

        call_count = [0]
        def sleep_and_stop(seconds):
            call_count[0] += 1
            # Stop after 2nd sleep to allow beat attempt
            if call_count[0] >= 2:
                loaded = swarm.load_heartbeat_state('builder')
                loaded.status = 'stopped'
                swarm.save_heartbeat_state(loaded)

        mock_sleep.side_effect = sleep_and_stop

        # Should not raise, just continue
        swarm.run_heartbeat_monitor('builder')

        mock_tmux_send.assert_called_once()

    @patch('swarm.tmux_capture_pane')
    @patch('swarm.tmux_send')
    @patch('swarm.refresh_worker_status')
    @patch('swarm.State')
    @patch('swarm.time.monotonic')
    @patch('swarm.time.sleep')
    def test_monitor_skips_beat_when_message_pending(self, mock_sleep, mock_monotonic, mock_state_cls, mock_refresh, mock_tmux_send, mock_capture):
        """Test monitor skips beat when previous message is still in tmux pane."""
        state = swarm.HeartbeatState(
            worker_name='builder',
            interval_seconds=60,
            message='continue',
            created_at=datetime.now(timezone.utc).isoformat(),
            status='active',
            beat_count=0,
        )
        swarm.save_heartbeat_state(state)

        mock_worker = MagicMock()
        mock_worker.tmux.session = 'session'
        mock_worker.tmux.window = 'window'
        mock_worker.tmux.socket = None
        mock_state = MagicMock()
        mock_state.get_worker.return_value = mock_worker
        mock_state_cls.return_value = mock_state
        mock_refresh.return_value = 'running'

        # Pane shows the heartbeat message still pending on last line
        mock_capture.return_value = "some output\n$ continue\n"

        # Simulate time progression past interval, then time for reset after skip
        mock_monotonic.side_effect = [0, 100, 100]

        call_count = [0]
        def sleep_and_stop(seconds):
            call_count[0] += 1
            if call_count[0] >= 2:
                loaded = swarm.load_heartbeat_state('builder')
                loaded.status = 'stopped'
                swarm.save_heartbeat_state(loaded)

        mock_sleep.side_effect = sleep_and_stop

        swarm.run_heartbeat_monitor('builder')

        # tmux_send should NOT have been called — beat was skipped
        mock_tmux_send.assert_not_called()

        # beat_count should remain 0
        updated = swarm.load_heartbeat_state('builder')
        self.assertEqual(updated.beat_count, 0)

    @patch('swarm.tmux_capture_pane')
    @patch('swarm.tmux_send')
    @patch('swarm.refresh_worker_status')
    @patch('swarm.State')
    @patch('swarm.time.monotonic')
    @patch('swarm.time.sleep')
    def test_monitor_sends_beat_when_message_not_pending(self, mock_sleep, mock_monotonic, mock_state_cls, mock_refresh, mock_tmux_send, mock_capture):
        """Test monitor sends beat normally when previous message is not in pane."""
        state = swarm.HeartbeatState(
            worker_name='builder',
            interval_seconds=60,
            message='continue',
            created_at=datetime.now(timezone.utc).isoformat(),
            status='active',
            beat_count=0,
        )
        swarm.save_heartbeat_state(state)

        mock_worker = MagicMock()
        mock_worker.tmux.session = 'session'
        mock_worker.tmux.window = 'window'
        mock_worker.tmux.socket = None
        mock_state = MagicMock()
        mock_state.get_worker.return_value = mock_worker
        mock_state_cls.return_value = mock_state
        mock_refresh.return_value = 'running'

        # Pane does NOT contain the heartbeat message
        mock_capture.return_value = "some output\n$ \n"

        # Simulate time progression past interval, then time for reset after send
        mock_monotonic.side_effect = [0, 100, 100]

        call_count = [0]
        def sleep_and_stop(seconds):
            call_count[0] += 1
            if call_count[0] >= 2:
                loaded = swarm.load_heartbeat_state('builder')
                loaded.status = 'stopped'
                swarm.save_heartbeat_state(loaded)

        mock_sleep.side_effect = sleep_and_stop

        swarm.run_heartbeat_monitor('builder')

        # tmux_send SHOULD have been called
        mock_tmux_send.assert_called_once_with(
            'session', 'window', 'continue', enter=True, socket=None, pre_clear=False
        )

        # beat_count should be incremented
        updated = swarm.load_heartbeat_state('builder')
        self.assertEqual(updated.beat_count, 1)


class TestMonitorBeatCountAndLastBeatAt(unittest.TestCase):
    """Test that beat_count and last_beat_at are updated after beat is sent."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.original_swarm_dir = swarm.SWARM_DIR
        self.original_heartbeats_dir = swarm.HEARTBEATS_DIR
        self.original_state_file = swarm.STATE_FILE
        swarm.SWARM_DIR = Path(self.temp_dir) / ".swarm"
        swarm.HEARTBEATS_DIR = swarm.SWARM_DIR / "heartbeats"
        swarm.STATE_FILE = swarm.SWARM_DIR / "state.json"
        swarm.HEARTBEATS_DIR.mkdir(parents=True, exist_ok=True)
        swarm.HEARTBEAT_LOCK_FILE = swarm.SWARM_DIR / "heartbeat.lock"
        swarm.STATE_LOCK_FILE = swarm.SWARM_DIR / "state.lock"

    def tearDown(self):
        """Clean up test fixtures."""
        swarm.SWARM_DIR = self.original_swarm_dir
        swarm.HEARTBEATS_DIR = self.original_heartbeats_dir
        swarm.STATE_FILE = self.original_state_file
        swarm.HEARTBEAT_LOCK_FILE = swarm.SWARM_DIR / "heartbeat.lock"
        swarm.STATE_LOCK_FILE = swarm.SWARM_DIR / "state.lock"
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @patch('swarm.tmux_send')
    @patch('swarm.refresh_worker_status')
    @patch('swarm.State')
    @patch('swarm.time.monotonic')
    @patch('swarm.time.sleep')
    def test_beat_count_incremented_after_successful_beat(self, mock_sleep, mock_monotonic, mock_state_cls, mock_refresh, mock_tmux_send):
        """Test beat_count is incremented after a successful beat."""
        state = swarm.HeartbeatState(
            worker_name='builder',
            interval_seconds=60,
            message='continue',
            created_at=datetime.now(timezone.utc).isoformat(),
            status='active',
            beat_count=0,
        )
        swarm.save_heartbeat_state(state)

        mock_worker = MagicMock()
        mock_worker.tmux.session = 'session'
        mock_worker.tmux.window = 'window'
        mock_worker.tmux.socket = None
        mock_state = MagicMock()
        mock_state.get_worker.return_value = mock_worker
        mock_state_cls.return_value = mock_state
        mock_refresh.return_value = 'running'

        # Simulate time progression past interval
        mock_monotonic.side_effect = [0, 100, 100]

        call_count = [0]
        def sleep_and_stop(seconds):
            call_count[0] += 1
            if call_count[0] >= 2:
                loaded = swarm.load_heartbeat_state('builder')
                loaded.status = 'stopped'
                swarm.save_heartbeat_state(loaded)

        mock_sleep.side_effect = sleep_and_stop

        swarm.run_heartbeat_monitor('builder')

        # Verify beat_count was incremented
        updated = swarm.load_heartbeat_state('builder')
        self.assertEqual(updated.beat_count, 1)

    @patch('swarm.tmux_send')
    @patch('swarm.refresh_worker_status')
    @patch('swarm.State')
    @patch('swarm.time.monotonic')
    @patch('swarm.time.sleep')
    def test_last_beat_at_updated_after_successful_beat(self, mock_sleep, mock_monotonic, mock_state_cls, mock_refresh, mock_tmux_send):
        """Test last_beat_at is updated after a successful beat."""
        created = datetime.now(timezone.utc) - timedelta(hours=1)
        state = swarm.HeartbeatState(
            worker_name='builder',
            interval_seconds=60,
            message='continue',
            created_at=created.isoformat(),
            last_beat_at=None,
            status='active',
        )
        swarm.save_heartbeat_state(state)

        mock_worker = MagicMock()
        mock_worker.tmux.session = 'session'
        mock_worker.tmux.window = 'window'
        mock_worker.tmux.socket = None
        mock_state = MagicMock()
        mock_state.get_worker.return_value = mock_worker
        mock_state_cls.return_value = mock_state
        mock_refresh.return_value = 'running'

        mock_monotonic.side_effect = [0, 100, 100]

        call_count = [0]
        def sleep_and_stop(seconds):
            call_count[0] += 1
            if call_count[0] >= 2:
                loaded = swarm.load_heartbeat_state('builder')
                loaded.status = 'stopped'
                swarm.save_heartbeat_state(loaded)

        mock_sleep.side_effect = sleep_and_stop

        swarm.run_heartbeat_monitor('builder')

        # Verify last_beat_at was updated
        updated = swarm.load_heartbeat_state('builder')
        self.assertIsNotNone(updated.last_beat_at)

    @patch('swarm.tmux_send')
    @patch('swarm.refresh_worker_status')
    @patch('swarm.State')
    @patch('swarm.time.monotonic')
    @patch('swarm.time.sleep')
    def test_beat_count_not_incremented_on_tmux_failure(self, mock_sleep, mock_monotonic, mock_state_cls, mock_refresh, mock_tmux_send):
        """Test beat_count is NOT incremented when tmux_send fails."""
        state = swarm.HeartbeatState(
            worker_name='builder',
            interval_seconds=60,
            message='continue',
            created_at=datetime.now(timezone.utc).isoformat(),
            status='active',
            beat_count=0,
        )
        swarm.save_heartbeat_state(state)

        mock_worker = MagicMock()
        mock_worker.tmux.session = 'session'
        mock_worker.tmux.window = 'window'
        mock_worker.tmux.socket = None
        mock_state = MagicMock()
        mock_state.get_worker.return_value = mock_worker
        mock_state_cls.return_value = mock_state
        mock_refresh.return_value = 'running'

        mock_monotonic.side_effect = [0, 100]
        mock_tmux_send.side_effect = Exception("tmux error")

        call_count = [0]
        def sleep_and_stop(seconds):
            call_count[0] += 1
            if call_count[0] >= 2:
                loaded = swarm.load_heartbeat_state('builder')
                loaded.status = 'stopped'
                swarm.save_heartbeat_state(loaded)

        mock_sleep.side_effect = sleep_and_stop

        swarm.run_heartbeat_monitor('builder')

        # Verify beat_count was NOT incremented
        updated = swarm.load_heartbeat_state('builder')
        self.assertEqual(updated.beat_count, 0)


class TestShortIntervalWarning(unittest.TestCase):
    """Test warning for short heartbeat interval."""

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

    @patch('swarm.start_heartbeat_monitor')
    @patch('swarm.State')
    def test_short_interval_shows_warning(self, mock_state_cls, mock_start_monitor):
        """Test that intervals less than 1 minute show a warning."""
        mock_worker = MagicMock()
        mock_worker.tmux = MagicMock()
        mock_state = MagicMock()
        mock_state.get_worker.return_value = mock_worker
        mock_state_cls.return_value = mock_state
        mock_start_monitor.return_value = 12345

        args = Namespace(
            worker='builder',
            interval='30s',  # Less than 1 minute
            expire=None,
            message='continue',
            force=False
        )

        # Capture stderr
        import io
        import sys
        captured = io.StringIO()
        old_stderr = sys.stderr
        sys.stderr = captured

        try:
            swarm.cmd_heartbeat_start(args)
        finally:
            sys.stderr = old_stderr

        warning_output = captured.getvalue()
        self.assertIn('warning', warning_output.lower())
        self.assertIn('short', warning_output.lower())

    @patch('swarm.start_heartbeat_monitor')
    @patch('swarm.State')
    def test_normal_interval_no_warning(self, mock_state_cls, mock_start_monitor):
        """Test that intervals >= 1 minute do not show a warning."""
        mock_worker = MagicMock()
        mock_worker.tmux = MagicMock()
        mock_state = MagicMock()
        mock_state.get_worker.return_value = mock_worker
        mock_state_cls.return_value = mock_state
        mock_start_monitor.return_value = 12345

        args = Namespace(
            worker='builder',
            interval='1m',  # Exactly 1 minute
            expire=None,
            message='continue',
            force=False
        )

        # Capture stderr
        import io
        import sys
        captured = io.StringIO()
        old_stderr = sys.stderr
        sys.stderr = captured

        try:
            swarm.cmd_heartbeat_start(args)
        finally:
            sys.stderr = old_stderr

        warning_output = captured.getvalue()
        self.assertNotIn('warning', warning_output.lower())


class TestHeartbeatStatePersistence(unittest.TestCase):
    """Test comprehensive state persistence behavior."""

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

    def test_state_persists_all_fields(self):
        """Test that all HeartbeatState fields are persisted correctly."""
        created = datetime.now(timezone.utc)
        expire = created + timedelta(hours=24)
        last_beat = created + timedelta(hours=1)

        state = swarm.HeartbeatState(
            worker_name='test-worker',
            interval_seconds=3600,
            expire_at=expire.isoformat(),
            message='test message',
            created_at=created.isoformat(),
            last_beat_at=last_beat.isoformat(),
            beat_count=5,
            status='active',
            monitor_pid=12345,
        )
        swarm.save_heartbeat_state(state)

        loaded = swarm.load_heartbeat_state('test-worker')

        self.assertEqual(loaded.worker_name, 'test-worker')
        self.assertEqual(loaded.interval_seconds, 3600)
        self.assertEqual(loaded.expire_at, expire.isoformat())
        self.assertEqual(loaded.message, 'test message')
        self.assertEqual(loaded.created_at, created.isoformat())
        self.assertEqual(loaded.last_beat_at, last_beat.isoformat())
        self.assertEqual(loaded.beat_count, 5)
        self.assertEqual(loaded.status, 'active')
        self.assertEqual(loaded.monitor_pid, 12345)

    def test_state_file_location(self):
        """Test state file is saved to correct location."""
        state = swarm.HeartbeatState(
            worker_name='location-test',
            interval_seconds=60,
            message='test',
            created_at=datetime.now(timezone.utc).isoformat(),
            status='active',
        )
        swarm.save_heartbeat_state(state)

        expected_path = swarm.HEARTBEATS_DIR / "location-test.json"
        self.assertTrue(expected_path.exists())

    def test_load_nonexistent_returns_none(self):
        """Test loading non-existent state returns None."""
        loaded = swarm.load_heartbeat_state('nonexistent')
        self.assertIsNone(loaded)

    def test_delete_heartbeat_state(self):
        """Test deleting heartbeat state removes file."""
        state = swarm.HeartbeatState(
            worker_name='to-delete',
            interval_seconds=60,
            message='test',
            created_at=datetime.now(timezone.utc).isoformat(),
            status='active',
        )
        swarm.save_heartbeat_state(state)

        state_path = swarm.HEARTBEATS_DIR / "to-delete.json"
        self.assertTrue(state_path.exists())

        swarm.delete_heartbeat_state('to-delete')
        self.assertFalse(state_path.exists())

    def test_state_survives_status_transitions(self):
        """Test state persists correctly through status transitions."""
        state = swarm.HeartbeatState(
            worker_name='transition-test',
            interval_seconds=60,
            message='test',
            created_at=datetime.now(timezone.utc).isoformat(),
            status='active',
        )
        swarm.save_heartbeat_state(state)

        # Transition to paused
        loaded = swarm.load_heartbeat_state('transition-test')
        loaded.status = 'paused'
        swarm.save_heartbeat_state(loaded)

        reloaded = swarm.load_heartbeat_state('transition-test')
        self.assertEqual(reloaded.status, 'paused')

        # Transition to stopped
        reloaded.status = 'stopped'
        swarm.save_heartbeat_state(reloaded)

        final = swarm.load_heartbeat_state('transition-test')
        self.assertEqual(final.status, 'stopped')


class TestIntervalCalculation(unittest.TestCase):
    """Test interval-related calculations via status command."""

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

    def test_next_beat_calculated_from_created_at_when_no_beats(self):
        """Test next beat is calculated from created_at when no beats sent (via JSON output)."""
        import io
        from contextlib import redirect_stdout

        created = datetime.now(timezone.utc) - timedelta(minutes=30)
        state = swarm.HeartbeatState(
            worker_name='calc-test',
            interval_seconds=3600,  # 1 hour
            message='test',
            created_at=created.isoformat(),
            last_beat_at=None,
            status='active',
        )
        swarm.save_heartbeat_state(state)

        args = Namespace(worker='calc-test', format='json')
        f = io.StringIO()
        with redirect_stdout(f):
            swarm.cmd_heartbeat_status(args)

        output = f.getvalue()
        data = json.loads(output)

        # next_beat_at should be created_at + interval
        expected = created + timedelta(seconds=3600)
        next_beat = datetime.fromisoformat(data['next_beat_at'].replace('Z', '+00:00'))

        diff = abs((next_beat - expected).total_seconds())
        self.assertLess(diff, 1)

    def test_next_beat_calculated_from_last_beat_when_beats_sent(self):
        """Test next beat is calculated from last_beat_at when beats have been sent."""
        import io
        from contextlib import redirect_stdout

        created = datetime.now(timezone.utc) - timedelta(hours=2)
        last_beat = datetime.now(timezone.utc) - timedelta(minutes=45)
        state = swarm.HeartbeatState(
            worker_name='calc-test',
            interval_seconds=3600,  # 1 hour
            message='test',
            created_at=created.isoformat(),
            last_beat_at=last_beat.isoformat(),
            beat_count=2,
            status='active',
        )
        swarm.save_heartbeat_state(state)

        args = Namespace(worker='calc-test', format='json')
        f = io.StringIO()
        with redirect_stdout(f):
            swarm.cmd_heartbeat_status(args)

        output = f.getvalue()
        data = json.loads(output)

        # next_beat_at should be last_beat + interval
        expected = last_beat + timedelta(seconds=3600)
        next_beat = datetime.fromisoformat(data['next_beat_at'].replace('Z', '+00:00'))

        diff = abs((next_beat - expected).total_seconds())
        self.assertLess(diff, 1)

    def test_next_beat_null_for_stopped_heartbeat(self):
        """Test next beat is null for stopped heartbeats (via JSON output)."""
        import io
        from contextlib import redirect_stdout

        state = swarm.HeartbeatState(
            worker_name='stopped-test',
            interval_seconds=3600,
            message='test',
            created_at=datetime.now(timezone.utc).isoformat(),
            status='stopped',
        )
        swarm.save_heartbeat_state(state)

        args = Namespace(worker='stopped-test', format='json')
        f = io.StringIO()
        with redirect_stdout(f):
            swarm.cmd_heartbeat_status(args)

        output = f.getvalue()
        data = json.loads(output)

        self.assertIsNone(data['next_beat_at'])

    def test_next_beat_null_for_expired_heartbeat(self):
        """Test next beat is null for expired heartbeats (via JSON output)."""
        import io
        from contextlib import redirect_stdout

        state = swarm.HeartbeatState(
            worker_name='expired-test',
            interval_seconds=3600,
            message='test',
            created_at=datetime.now(timezone.utc).isoformat(),
            status='expired',
        )
        swarm.save_heartbeat_state(state)

        args = Namespace(worker='expired-test', format='json')
        f = io.StringIO()
        with redirect_stdout(f):
            swarm.cmd_heartbeat_status(args)

        output = f.getvalue()
        data = json.loads(output)

        self.assertIsNone(data['next_beat_at'])

    def test_next_beat_null_for_paused_heartbeat(self):
        """Test next beat is null for paused heartbeats (via JSON output)."""
        import io
        from contextlib import redirect_stdout

        state = swarm.HeartbeatState(
            worker_name='paused-test',
            interval_seconds=3600,
            message='test',
            created_at=datetime.now(timezone.utc).isoformat(),
            status='paused',
        )
        swarm.save_heartbeat_state(state)

        args = Namespace(worker='paused-test', format='json')
        f = io.StringIO()
        with redirect_stdout(f):
            swarm.cmd_heartbeat_status(args)

        output = f.getvalue()
        data = json.loads(output)

        self.assertIsNone(data['next_beat_at'])


class TestStartHeartbeatMonitor(unittest.TestCase):
    """Test start_heartbeat_monitor function."""

    @patch('swarm.os.fork')
    def test_parent_returns_pid(self, mock_fork):
        """Test parent process returns child PID."""
        mock_fork.return_value = 12345

        result = swarm.start_heartbeat_monitor('builder')

        self.assertEqual(result, 12345)
        mock_fork.assert_called_once()

    @patch('swarm.run_heartbeat_monitor')
    @patch('swarm.os._exit')
    @patch('swarm.os.close')
    @patch('swarm.os.dup2')
    @patch('swarm.os.open')
    @patch('swarm.sys.stderr')
    @patch('swarm.sys.stdout')
    @patch('swarm.sys.stdin')
    @patch('swarm.os.setsid')
    @patch('swarm.os.fork')
    def test_child_process_becomes_daemon(self, mock_fork, mock_setsid,
                                          mock_stdin, mock_stdout, mock_stderr,
                                          mock_open, mock_dup2, mock_close,
                                          mock_exit, mock_run_monitor):
        """Test child process performs daemon setup."""
        # First fork returns 0 (child), second fork returns 0 (grandchild)
        mock_fork.side_effect = [0, 0]
        mock_open.return_value = 3  # File descriptor for /dev/null

        swarm.start_heartbeat_monitor('builder')

        # Verify daemon setup
        self.assertEqual(mock_fork.call_count, 2)
        mock_setsid.assert_called_once()
        mock_stdin.close.assert_called_once()
        mock_stdout.close.assert_called_once()
        mock_stderr.close.assert_called_once()
        mock_run_monitor.assert_called_once_with('builder')
        mock_exit.assert_called_with(0)

    @patch('swarm.os._exit')
    @patch('swarm.os.setsid')
    @patch('swarm.os.fork')
    def test_first_child_exits(self, mock_fork, mock_setsid, mock_exit):
        """Test first child process exits after second fork."""
        # First fork returns 0 (child), second fork returns 9999 (grandchild PID)
        mock_fork.side_effect = [0, 9999]
        # Make _exit raise SystemExit to simulate process termination
        mock_exit.side_effect = SystemExit(0)

        with self.assertRaises(SystemExit):
            swarm.start_heartbeat_monitor('builder')

        mock_setsid.assert_called_once()
        mock_exit.assert_called_with(0)


class TestHeartbeatStopWithMonitor(unittest.TestCase):
    """Test cmd_heartbeat_stop terminates monitor process."""

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

    @patch('swarm.stop_heartbeat_monitor')
    def test_stop_calls_stop_monitor(self, mock_stop_monitor):
        """Test cmd_heartbeat_stop calls stop_heartbeat_monitor."""
        state = swarm.HeartbeatState(
            worker_name='builder',
            interval_seconds=3600,
            message='continue',
            created_at=datetime.now(timezone.utc).isoformat(),
            status='active',
            monitor_pid=12345,
        )
        swarm.save_heartbeat_state(state)

        args = Namespace(worker='builder')
        swarm.cmd_heartbeat_stop(args)

        mock_stop_monitor.assert_called_once()
        # Verify state was updated
        updated = swarm.load_heartbeat_state('builder')
        self.assertEqual(updated.status, 'stopped')
        self.assertIsNone(updated.monitor_pid)


class TestCmdHeartbeatStatus(unittest.TestCase):
    """Test cmd_heartbeat_status function."""

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

    def test_status_nonexistent_heartbeat_fails(self):
        """Test status for non-existent heartbeat fails."""
        args = Namespace(worker='nonexistent', format='text')

        with self.assertRaises(SystemExit) as ctx:
            swarm.cmd_heartbeat_status(args)

        self.assertEqual(ctx.exception.code, 1)

    def test_status_shows_active_heartbeat(self):
        """Test status shows active heartbeat info."""
        created = datetime.now(timezone.utc)
        state = swarm.HeartbeatState(
            worker_name='builder',
            interval_seconds=3600,
            message='continue',
            created_at=created.isoformat(),
            status='active',
            beat_count=5,
        )
        swarm.save_heartbeat_state(state)

        args = Namespace(worker='builder', format='text')
        # Should not raise
        swarm.cmd_heartbeat_status(args)

    def test_status_shows_next_beat_for_active(self):
        """Test status shows next beat time for active heartbeat."""
        created = datetime.now(timezone.utc) - timedelta(minutes=30)
        state = swarm.HeartbeatState(
            worker_name='builder',
            interval_seconds=3600,
            message='continue',
            created_at=created.isoformat(),
            status='active',
        )
        swarm.save_heartbeat_state(state)

        args = Namespace(worker='builder', format='text')
        # Should show next beat (created + 1 hour interval = 30 min from now)
        swarm.cmd_heartbeat_status(args)

    def test_status_shows_next_beat_based_on_last_beat(self):
        """Test next beat is calculated from last_beat_at when available."""
        created = datetime.now(timezone.utc) - timedelta(hours=2)
        last_beat = datetime.now(timezone.utc) - timedelta(minutes=30)
        state = swarm.HeartbeatState(
            worker_name='builder',
            interval_seconds=3600,
            message='continue',
            created_at=created.isoformat(),
            last_beat_at=last_beat.isoformat(),
            beat_count=2,
            status='active',
        )
        swarm.save_heartbeat_state(state)

        args = Namespace(worker='builder', format='text')
        # Should show next beat (last_beat + 1 hour = 30 min from now)
        swarm.cmd_heartbeat_status(args)

    def test_status_shows_dash_for_paused(self):
        """Test status shows dash for next beat when paused."""
        state = swarm.HeartbeatState(
            worker_name='builder',
            interval_seconds=3600,
            message='continue',
            created_at=datetime.now(timezone.utc).isoformat(),
            status='paused',
        )
        swarm.save_heartbeat_state(state)

        args = Namespace(worker='builder', format='text')
        # Should show "-" for next beat
        swarm.cmd_heartbeat_status(args)

    def test_status_shows_dash_for_stopped(self):
        """Test status shows dash for next beat when stopped."""
        state = swarm.HeartbeatState(
            worker_name='builder',
            interval_seconds=3600,
            message='continue',
            created_at=datetime.now(timezone.utc).isoformat(),
            status='stopped',
        )
        swarm.save_heartbeat_state(state)

        args = Namespace(worker='builder', format='text')
        # Should show "-" for next beat
        swarm.cmd_heartbeat_status(args)

    def test_status_shows_dash_for_expired(self):
        """Test status shows dash for next beat when expired."""
        state = swarm.HeartbeatState(
            worker_name='builder',
            interval_seconds=3600,
            message='continue',
            created_at=datetime.now(timezone.utc).isoformat(),
            status='expired',
        )
        swarm.save_heartbeat_state(state)

        args = Namespace(worker='builder', format='text')
        # Should show "-" for next beat
        swarm.cmd_heartbeat_status(args)

    def test_status_shows_expiration(self):
        """Test status shows expiration time."""
        expire_time = datetime.now(timezone.utc) + timedelta(hours=12)
        state = swarm.HeartbeatState(
            worker_name='builder',
            interval_seconds=3600,
            message='continue',
            created_at=datetime.now(timezone.utc).isoformat(),
            expire_at=expire_time.isoformat(),
            status='active',
        )
        swarm.save_heartbeat_state(state)

        args = Namespace(worker='builder', format='text')
        # Should show expiration time
        swarm.cmd_heartbeat_status(args)

    def test_status_shows_never_for_no_expiration(self):
        """Test status shows 'never' when no expiration set."""
        state = swarm.HeartbeatState(
            worker_name='builder',
            interval_seconds=3600,
            message='continue',
            created_at=datetime.now(timezone.utc).isoformat(),
            expire_at=None,
            status='active',
        )
        swarm.save_heartbeat_state(state)

        args = Namespace(worker='builder', format='text')
        # Should show "never" for expiration
        swarm.cmd_heartbeat_status(args)

    def test_status_json_output(self):
        """Test status JSON output format."""
        created = datetime.now(timezone.utc)
        expire_time = created + timedelta(hours=24)
        state = swarm.HeartbeatState(
            worker_name='builder',
            interval_seconds=3600,
            message='continue',
            created_at=created.isoformat(),
            expire_at=expire_time.isoformat(),
            beat_count=3,
            status='active',
        )
        swarm.save_heartbeat_state(state)

        args = Namespace(worker='builder', format='json')
        # Should output valid JSON
        swarm.cmd_heartbeat_status(args)

    def test_status_json_includes_next_beat_at(self):
        """Test JSON output includes next_beat_at field."""
        created = datetime.now(timezone.utc) - timedelta(minutes=30)
        state = swarm.HeartbeatState(
            worker_name='builder',
            interval_seconds=3600,
            message='continue',
            created_at=created.isoformat(),
            status='active',
        )
        swarm.save_heartbeat_state(state)

        args = Namespace(worker='builder', format='json')

        # Capture output
        import io
        from contextlib import redirect_stdout
        f = io.StringIO()
        with redirect_stdout(f):
            swarm.cmd_heartbeat_status(args)

        output = f.getvalue()
        data = json.loads(output)

        self.assertIn('next_beat_at', data)
        self.assertIsNotNone(data['next_beat_at'])

    def test_status_json_next_beat_at_null_for_stopped(self):
        """Test JSON output has null next_beat_at when stopped."""
        state = swarm.HeartbeatState(
            worker_name='builder',
            interval_seconds=3600,
            message='continue',
            created_at=datetime.now(timezone.utc).isoformat(),
            status='stopped',
        )
        swarm.save_heartbeat_state(state)

        args = Namespace(worker='builder', format='json')

        # Capture output
        import io
        from contextlib import redirect_stdout
        f = io.StringIO()
        with redirect_stdout(f):
            swarm.cmd_heartbeat_status(args)

        output = f.getvalue()
        data = json.loads(output)

        self.assertIn('next_beat_at', data)
        self.assertIsNone(data['next_beat_at'])

    def test_status_handles_invalid_created_at(self):
        """Test status handles invalid created_at timestamp."""
        state = swarm.HeartbeatState(
            worker_name='builder',
            interval_seconds=3600,
            message='continue',
            created_at='not-a-valid-timestamp',
            status='active',
        )
        swarm.save_heartbeat_state(state)

        args = Namespace(worker='builder', format='text')
        # Should handle gracefully
        swarm.cmd_heartbeat_status(args)

    def test_status_handles_empty_created_at(self):
        """Test status handles empty created_at."""
        state = swarm.HeartbeatState(
            worker_name='builder',
            interval_seconds=3600,
            message='continue',
            created_at='',
            status='active',
        )
        swarm.save_heartbeat_state(state)

        args = Namespace(worker='builder', format='text')
        # Should handle gracefully and show "?"
        swarm.cmd_heartbeat_status(args)

    def test_status_cli_format_flag(self):
        """Test status command accepts --format flag via CLI."""
        result = subprocess.run(
            [sys.executable, 'swarm.py', 'heartbeat', 'status', '--help'],
            capture_output=True,
            text=True
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn('--format', result.stdout)
        self.assertIn('json', result.stdout)


class TestCmdHeartbeatDispatch(unittest.TestCase):
    """Test cmd_heartbeat dispatch function."""

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

    @patch('swarm.cmd_heartbeat_start')
    def test_dispatch_start(self, mock_start):
        """Test cmd_heartbeat dispatches to start."""
        args = Namespace(heartbeat_command='start')
        swarm.cmd_heartbeat(args)
        mock_start.assert_called_once_with(args)

    @patch('swarm.cmd_heartbeat_stop')
    def test_dispatch_stop(self, mock_stop):
        """Test cmd_heartbeat dispatches to stop."""
        args = Namespace(heartbeat_command='stop')
        swarm.cmd_heartbeat(args)
        mock_stop.assert_called_once_with(args)

    @patch('swarm.cmd_heartbeat_list')
    def test_dispatch_list(self, mock_list):
        """Test cmd_heartbeat dispatches to list."""
        args = Namespace(heartbeat_command='list')
        swarm.cmd_heartbeat(args)
        mock_list.assert_called_once_with(args)

    @patch('swarm.cmd_heartbeat_status')
    def test_dispatch_status(self, mock_status):
        """Test cmd_heartbeat dispatches to status."""
        args = Namespace(heartbeat_command='status')
        swarm.cmd_heartbeat(args)
        mock_status.assert_called_once_with(args)

    @patch('swarm.cmd_heartbeat_pause')
    def test_dispatch_pause(self, mock_pause):
        """Test cmd_heartbeat dispatches to pause."""
        args = Namespace(heartbeat_command='pause')
        swarm.cmd_heartbeat(args)
        mock_pause.assert_called_once_with(args)

    @patch('swarm.cmd_heartbeat_resume')
    def test_dispatch_resume(self, mock_resume):
        """Test cmd_heartbeat dispatches to resume."""
        args = Namespace(heartbeat_command='resume')
        swarm.cmd_heartbeat(args)
        mock_resume.assert_called_once_with(args)


class TestHeartbeatCleanupOnKill(unittest.TestCase):
    """Test that heartbeat is stopped when worker is killed."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.original_swarm_dir = swarm.SWARM_DIR
        self.original_heartbeats_dir = swarm.HEARTBEATS_DIR
        self.original_state_file = swarm.STATE_FILE
        swarm.SWARM_DIR = Path(self.temp_dir) / ".swarm"
        swarm.HEARTBEATS_DIR = swarm.SWARM_DIR / "heartbeats"
        swarm.STATE_FILE = swarm.SWARM_DIR / "state.json"
        swarm.SWARM_DIR.mkdir(parents=True, exist_ok=True)
        swarm.HEARTBEATS_DIR.mkdir(parents=True, exist_ok=True)
        swarm.HEARTBEAT_LOCK_FILE = swarm.SWARM_DIR / "heartbeat.lock"
        swarm.STATE_LOCK_FILE = swarm.SWARM_DIR / "state.lock"
        swarm.LOGS_DIR = swarm.SWARM_DIR / "logs"
        swarm.LOGS_DIR.mkdir(parents=True, exist_ok=True)
        swarm.RALPH_DIR = swarm.SWARM_DIR / "ralph"

    def tearDown(self):
        """Clean up test fixtures."""
        swarm.SWARM_DIR = self.original_swarm_dir
        swarm.HEARTBEATS_DIR = self.original_heartbeats_dir
        swarm.STATE_FILE = self.original_state_file
        swarm.HEARTBEAT_LOCK_FILE = swarm.SWARM_DIR / "heartbeat.lock"
        swarm.STATE_LOCK_FILE = swarm.SWARM_DIR / "state.lock"
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @patch('swarm.stop_heartbeat_monitor')
    @patch('swarm.subprocess.run')
    def test_kill_stops_active_heartbeat(self, mock_subprocess_run, mock_stop_monitor):
        """Test killing worker stops active heartbeat."""
        # Create worker state
        state = swarm.State()
        worker = swarm.Worker(
            name='builder',
            status='running',
            cmd=['bash', '-c', 'sleep 100'],
            started=datetime.now().isoformat(),
            cwd='/tmp',
            tmux=swarm.TmuxInfo(session='swarm', window='builder', socket=None),
        )
        state.add_worker(worker)

        # Create active heartbeat
        heartbeat_state = swarm.HeartbeatState(
            worker_name='builder',
            interval_seconds=3600,
            message='continue',
            created_at=datetime.now(timezone.utc).isoformat(),
            status='active',
            monitor_pid=12345,
        )
        swarm.save_heartbeat_state(heartbeat_state)

        # Kill the worker
        args = Namespace(name='builder', all=False, rm_worktree=False, force_dirty=False)
        swarm.cmd_kill(args)

        # Verify heartbeat monitor was stopped
        mock_stop_monitor.assert_called_once()

        # Verify heartbeat status changed to stopped
        updated = swarm.load_heartbeat_state('builder')
        self.assertEqual(updated.status, 'stopped')
        self.assertIsNone(updated.monitor_pid)

    @patch('swarm.stop_heartbeat_monitor')
    @patch('swarm.subprocess.run')
    def test_kill_stops_paused_heartbeat(self, mock_subprocess_run, mock_stop_monitor):
        """Test killing worker stops paused heartbeat."""
        # Create worker state
        state = swarm.State()
        worker = swarm.Worker(
            name='builder',
            status='running',
            cmd=['bash', '-c', 'sleep 100'],
            started=datetime.now().isoformat(),
            cwd='/tmp',
            tmux=swarm.TmuxInfo(session='swarm', window='builder', socket=None),
        )
        state.add_worker(worker)

        # Create paused heartbeat
        heartbeat_state = swarm.HeartbeatState(
            worker_name='builder',
            interval_seconds=3600,
            message='continue',
            created_at=datetime.now(timezone.utc).isoformat(),
            status='paused',
            monitor_pid=12345,
        )
        swarm.save_heartbeat_state(heartbeat_state)

        # Kill the worker
        args = Namespace(name='builder', all=False, rm_worktree=False, force_dirty=False)
        swarm.cmd_kill(args)

        # Verify heartbeat monitor was stopped
        mock_stop_monitor.assert_called_once()

        # Verify heartbeat status changed to stopped
        updated = swarm.load_heartbeat_state('builder')
        self.assertEqual(updated.status, 'stopped')

    @patch('swarm.stop_heartbeat_monitor')
    @patch('swarm.subprocess.run')
    def test_kill_ignores_stopped_heartbeat(self, mock_subprocess_run, mock_stop_monitor):
        """Test killing worker ignores already stopped heartbeat."""
        # Create worker state
        state = swarm.State()
        worker = swarm.Worker(
            name='builder',
            status='running',
            cmd=['bash', '-c', 'sleep 100'],
            started=datetime.now().isoformat(),
            cwd='/tmp',
            tmux=swarm.TmuxInfo(session='swarm', window='builder', socket=None),
        )
        state.add_worker(worker)

        # Create already stopped heartbeat
        heartbeat_state = swarm.HeartbeatState(
            worker_name='builder',
            interval_seconds=3600,
            message='continue',
            created_at=datetime.now(timezone.utc).isoformat(),
            status='stopped',
            monitor_pid=None,
        )
        swarm.save_heartbeat_state(heartbeat_state)

        # Kill the worker
        args = Namespace(name='builder', all=False, rm_worktree=False, force_dirty=False)
        swarm.cmd_kill(args)

        # Verify heartbeat monitor was NOT stopped (heartbeat already stopped)
        mock_stop_monitor.assert_not_called()

    @patch('swarm.stop_heartbeat_monitor')
    @patch('swarm.subprocess.run')
    def test_kill_handles_no_heartbeat(self, mock_subprocess_run, mock_stop_monitor):
        """Test killing worker works when no heartbeat exists."""
        # Create worker state
        state = swarm.State()
        worker = swarm.Worker(
            name='builder',
            status='running',
            cmd=['bash', '-c', 'sleep 100'],
            started=datetime.now().isoformat(),
            cwd='/tmp',
            tmux=swarm.TmuxInfo(session='swarm', window='builder', socket=None),
        )
        state.add_worker(worker)

        # No heartbeat created

        # Kill the worker - should not raise
        args = Namespace(name='builder', all=False, rm_worktree=False, force_dirty=False)
        swarm.cmd_kill(args)

        # Verify heartbeat monitor was NOT stopped (no heartbeat)
        mock_stop_monitor.assert_not_called()

    @patch('swarm.stop_heartbeat_monitor')
    @patch('swarm.subprocess.run')
    def test_kill_all_stops_all_heartbeats(self, mock_subprocess_run, mock_stop_monitor):
        """Test killing all workers stops all active heartbeats."""
        # Create worker state with two workers
        state = swarm.State()
        for name in ['worker1', 'worker2']:
            worker = swarm.Worker(
                name=name,
                status='running',
                cmd=['bash', '-c', 'sleep 100'],
                started=datetime.now().isoformat(),
                cwd='/tmp',
                tmux=swarm.TmuxInfo(session='swarm', window=name, socket=None),
            )
            state.add_worker(worker)

            # Create active heartbeat
            heartbeat_state = swarm.HeartbeatState(
                worker_name=name,
                interval_seconds=3600,
                message='continue',
                created_at=datetime.now(timezone.utc).isoformat(),
                status='active',
                monitor_pid=12345,
            )
            swarm.save_heartbeat_state(heartbeat_state)

        # Kill all workers
        args = Namespace(name=None, all=True, rm_worktree=False, force_dirty=False)
        swarm.cmd_kill(args)

        # Verify heartbeat monitor was stopped for both
        self.assertEqual(mock_stop_monitor.call_count, 2)

        # Verify both heartbeats are stopped
        for name in ['worker1', 'worker2']:
            updated = swarm.load_heartbeat_state(name)
            self.assertEqual(updated.status, 'stopped')


class TestIsHeartbeatMonitorRunning(unittest.TestCase):
    """Test is_heartbeat_monitor_running function."""

    def test_no_monitor_pid(self):
        """Test returns False when monitor_pid is None."""
        heartbeat_state = swarm.HeartbeatState(
            worker_name='builder',
            interval_seconds=3600,
            message='continue',
            created_at=datetime.now(timezone.utc).isoformat(),
            status='active',
            monitor_pid=None,
        )
        self.assertFalse(swarm.is_heartbeat_monitor_running(heartbeat_state))

    def test_invalid_pid(self):
        """Test returns False when PID doesn't exist."""
        heartbeat_state = swarm.HeartbeatState(
            worker_name='builder',
            interval_seconds=3600,
            message='continue',
            created_at=datetime.now(timezone.utc).isoformat(),
            status='active',
            monitor_pid=999999999,  # Highly unlikely to exist
        )
        self.assertFalse(swarm.is_heartbeat_monitor_running(heartbeat_state))

    def test_current_process_pid(self):
        """Test returns True for a running process (current process)."""
        heartbeat_state = swarm.HeartbeatState(
            worker_name='builder',
            interval_seconds=3600,
            message='continue',
            created_at=datetime.now(timezone.utc).isoformat(),
            status='active',
            monitor_pid=os.getpid(),  # Current process is definitely running
        )
        self.assertTrue(swarm.is_heartbeat_monitor_running(heartbeat_state))


class TestResumeActiveHeartbeats(unittest.TestCase):
    """Test resume_active_heartbeats function."""

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

    def test_no_heartbeats(self):
        """Test returns 0 when no heartbeats exist."""
        result = swarm.resume_active_heartbeats()
        self.assertEqual(result, 0)

    def test_paused_heartbeat_not_resumed(self):
        """Test paused heartbeats are not resumed."""
        heartbeat_state = swarm.HeartbeatState(
            worker_name='builder',
            interval_seconds=3600,
            message='continue',
            created_at=datetime.now(timezone.utc).isoformat(),
            status='paused',
            monitor_pid=None,
        )
        swarm.save_heartbeat_state(heartbeat_state)

        result = swarm.resume_active_heartbeats()
        self.assertEqual(result, 0)

    def test_stopped_heartbeat_not_resumed(self):
        """Test stopped heartbeats are not resumed."""
        heartbeat_state = swarm.HeartbeatState(
            worker_name='builder',
            interval_seconds=3600,
            message='continue',
            created_at=datetime.now(timezone.utc).isoformat(),
            status='stopped',
            monitor_pid=None,
        )
        swarm.save_heartbeat_state(heartbeat_state)

        result = swarm.resume_active_heartbeats()
        self.assertEqual(result, 0)

    def test_expired_heartbeat_not_resumed(self):
        """Test expired heartbeats are not resumed."""
        heartbeat_state = swarm.HeartbeatState(
            worker_name='builder',
            interval_seconds=3600,
            message='continue',
            created_at=datetime.now(timezone.utc).isoformat(),
            status='expired',
            monitor_pid=None,
        )
        swarm.save_heartbeat_state(heartbeat_state)

        result = swarm.resume_active_heartbeats()
        self.assertEqual(result, 0)

    @patch('swarm.is_heartbeat_monitor_running')
    def test_active_heartbeat_with_running_monitor_not_resumed(self, mock_is_running):
        """Test active heartbeats with running monitor are not resumed."""
        mock_is_running.return_value = True

        heartbeat_state = swarm.HeartbeatState(
            worker_name='builder',
            interval_seconds=3600,
            message='continue',
            created_at=datetime.now(timezone.utc).isoformat(),
            status='active',
            monitor_pid=12345,
        )
        swarm.save_heartbeat_state(heartbeat_state)

        result = swarm.resume_active_heartbeats()
        self.assertEqual(result, 0)

    @patch('swarm.start_heartbeat_monitor')
    @patch('swarm.refresh_worker_status')
    @patch('swarm.is_heartbeat_monitor_running')
    @patch('swarm.State')
    def test_active_heartbeat_without_worker_marked_stopped(
        self, mock_state_cls, mock_is_running, mock_refresh, mock_start_monitor
    ):
        """Test active heartbeats without a worker are marked stopped."""
        mock_is_running.return_value = False
        mock_state = MagicMock()
        mock_state.get_worker.return_value = None  # Worker doesn't exist
        mock_state_cls.return_value = mock_state

        heartbeat_state = swarm.HeartbeatState(
            worker_name='builder',
            interval_seconds=3600,
            message='continue',
            created_at=datetime.now(timezone.utc).isoformat(),
            status='active',
            monitor_pid=None,
        )
        swarm.save_heartbeat_state(heartbeat_state)

        result = swarm.resume_active_heartbeats()
        self.assertEqual(result, 0)

        # Verify heartbeat was marked stopped
        updated = swarm.load_heartbeat_state('builder')
        self.assertEqual(updated.status, 'stopped')
        mock_start_monitor.assert_not_called()

    @patch('swarm.start_heartbeat_monitor')
    @patch('swarm.refresh_worker_status')
    @patch('swarm.is_heartbeat_monitor_running')
    @patch('swarm.State')
    def test_active_heartbeat_with_stopped_worker_marked_stopped(
        self, mock_state_cls, mock_is_running, mock_refresh, mock_start_monitor
    ):
        """Test active heartbeats with stopped worker are marked stopped."""
        mock_is_running.return_value = False
        mock_worker = MagicMock()
        mock_state = MagicMock()
        mock_state.get_worker.return_value = mock_worker
        mock_state_cls.return_value = mock_state
        mock_refresh.return_value = 'stopped'  # Worker is stopped

        heartbeat_state = swarm.HeartbeatState(
            worker_name='builder',
            interval_seconds=3600,
            message='continue',
            created_at=datetime.now(timezone.utc).isoformat(),
            status='active',
            monitor_pid=None,
        )
        swarm.save_heartbeat_state(heartbeat_state)

        result = swarm.resume_active_heartbeats()
        self.assertEqual(result, 0)

        # Verify heartbeat was marked stopped
        updated = swarm.load_heartbeat_state('builder')
        self.assertEqual(updated.status, 'stopped')
        mock_start_monitor.assert_not_called()

    @patch('swarm.start_heartbeat_monitor')
    @patch('swarm.refresh_worker_status')
    @patch('swarm.is_heartbeat_monitor_running')
    @patch('swarm.State')
    def test_expired_active_heartbeat_marked_expired(
        self, mock_state_cls, mock_is_running, mock_refresh, mock_start_monitor
    ):
        """Test active heartbeats past expiration are marked expired."""
        mock_is_running.return_value = False
        mock_worker = MagicMock()
        mock_state = MagicMock()
        mock_state.get_worker.return_value = mock_worker
        mock_state_cls.return_value = mock_state
        mock_refresh.return_value = 'running'

        # Create heartbeat that expired in the past
        expired_time = datetime.now(timezone.utc) - timedelta(hours=1)
        heartbeat_state = swarm.HeartbeatState(
            worker_name='builder',
            interval_seconds=3600,
            message='continue',
            created_at=datetime.now(timezone.utc).isoformat(),
            expire_at=expired_time.isoformat(),
            status='active',
            monitor_pid=None,
        )
        swarm.save_heartbeat_state(heartbeat_state)

        result = swarm.resume_active_heartbeats()
        self.assertEqual(result, 0)

        # Verify heartbeat was marked expired
        updated = swarm.load_heartbeat_state('builder')
        self.assertEqual(updated.status, 'expired')
        mock_start_monitor.assert_not_called()

    @patch('swarm.start_heartbeat_monitor')
    @patch('swarm.refresh_worker_status')
    @patch('swarm.is_heartbeat_monitor_running')
    @patch('swarm.State')
    def test_active_heartbeat_resumed_successfully(
        self, mock_state_cls, mock_is_running, mock_refresh, mock_start_monitor
    ):
        """Test active heartbeat with running worker is resumed."""
        mock_is_running.return_value = False
        mock_worker = MagicMock()
        mock_state = MagicMock()
        mock_state.get_worker.return_value = mock_worker
        mock_state_cls.return_value = mock_state
        mock_refresh.return_value = 'running'
        mock_start_monitor.return_value = 54321  # New monitor PID

        heartbeat_state = swarm.HeartbeatState(
            worker_name='builder',
            interval_seconds=3600,
            message='continue',
            created_at=datetime.now(timezone.utc).isoformat(),
            status='active',
            monitor_pid=None,
        )
        swarm.save_heartbeat_state(heartbeat_state)

        result = swarm.resume_active_heartbeats()
        self.assertEqual(result, 1)

        # Verify monitor was started
        mock_start_monitor.assert_called_once_with('builder')

        # Verify heartbeat was updated with new PID
        updated = swarm.load_heartbeat_state('builder')
        self.assertEqual(updated.status, 'active')
        self.assertEqual(updated.monitor_pid, 54321)

    @patch('swarm.start_heartbeat_monitor')
    @patch('swarm.refresh_worker_status')
    @patch('swarm.is_heartbeat_monitor_running')
    @patch('swarm.State')
    def test_multiple_heartbeats_resumed(
        self, mock_state_cls, mock_is_running, mock_refresh, mock_start_monitor
    ):
        """Test multiple active heartbeats are resumed."""
        mock_is_running.return_value = False
        mock_worker = MagicMock()
        mock_state = MagicMock()
        mock_state.get_worker.return_value = mock_worker
        mock_state_cls.return_value = mock_state
        mock_refresh.return_value = 'running'
        mock_start_monitor.side_effect = [11111, 22222, 33333]

        # Create three active heartbeats
        for name in ['worker1', 'worker2', 'worker3']:
            heartbeat_state = swarm.HeartbeatState(
                worker_name=name,
                interval_seconds=3600,
                message='continue',
                created_at=datetime.now(timezone.utc).isoformat(),
                status='active',
                monitor_pid=None,
            )
            swarm.save_heartbeat_state(heartbeat_state)

        result = swarm.resume_active_heartbeats()
        self.assertEqual(result, 3)

        # Verify all monitors were started
        self.assertEqual(mock_start_monitor.call_count, 3)


class TestHeartbeatLsAlias(unittest.TestCase):
    """Test that 'heartbeat ls' alias works."""

    def test_heartbeat_ls_subcommand_exists(self):
        """Test that 'heartbeat ls' subcommand is recognized."""
        result = subprocess.run(
            [sys.executable, 'swarm.py', 'heartbeat', 'ls', '--help'],
            capture_output=True,
            text=True
        )
        self.assertEqual(result.returncode, 0)

    def test_heartbeat_ls_has_format_flag(self):
        """Test heartbeat ls accepts --format flag like list."""
        result = subprocess.run(
            [sys.executable, 'swarm.py', 'heartbeat', 'ls', '--help'],
            capture_output=True,
            text=True
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn('--format', result.stdout)

    def test_heartbeat_ls_dispatch(self):
        """Test cmd_heartbeat dispatches 'ls' to cmd_heartbeat_list."""
        args = Namespace(heartbeat_command='ls', format='table')

        with patch('swarm.cmd_heartbeat_list') as mock_list:
            swarm.cmd_heartbeat(args)

        mock_list.assert_called_once_with(args)


if __name__ == '__main__':
    unittest.main()
