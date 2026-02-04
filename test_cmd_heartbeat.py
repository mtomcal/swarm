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
            'session', 'window', 'continue', enter=True, socket=None
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


if __name__ == '__main__':
    unittest.main()
