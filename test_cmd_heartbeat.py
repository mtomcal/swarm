"""Unit tests for heartbeat functionality."""

import unittest
import swarm


class TestHeartbeatStateDataclass(unittest.TestCase):
    """Test HeartbeatState dataclass."""

    def test_heartbeat_state_required_fields(self):
        """Test HeartbeatState requires worker_name and interval_seconds."""
        state = swarm.HeartbeatState(
            worker_name='test-worker',
            interval_seconds=3600
        )
        self.assertEqual(state.worker_name, 'test-worker')
        self.assertEqual(state.interval_seconds, 3600)

    def test_heartbeat_state_defaults(self):
        """Test HeartbeatState has correct defaults."""
        state = swarm.HeartbeatState(
            worker_name='test',
            interval_seconds=14400
        )
        self.assertEqual(state.message, "continue")
        self.assertIsNone(state.expire_at)
        self.assertEqual(state.created_at, "")
        self.assertIsNone(state.last_beat_at)
        self.assertEqual(state.beat_count, 0)
        self.assertEqual(state.status, "active")

    def test_heartbeat_state_all_fields(self):
        """Test HeartbeatState with all fields specified."""
        state = swarm.HeartbeatState(
            worker_name='builder',
            interval_seconds=14400,
            message='continue working',
            expire_at='2026-02-05T02:00:00',
            created_at='2026-02-04T02:00:00',
            last_beat_at='2026-02-04T06:00:00',
            beat_count=3,
            status='paused'
        )
        self.assertEqual(state.worker_name, 'builder')
        self.assertEqual(state.interval_seconds, 14400)
        self.assertEqual(state.message, 'continue working')
        self.assertEqual(state.expire_at, '2026-02-05T02:00:00')
        self.assertEqual(state.created_at, '2026-02-04T02:00:00')
        self.assertEqual(state.last_beat_at, '2026-02-04T06:00:00')
        self.assertEqual(state.beat_count, 3)
        self.assertEqual(state.status, 'paused')

    def test_heartbeat_state_to_dict(self):
        """Test HeartbeatState to_dict method."""
        state = swarm.HeartbeatState(
            worker_name='test',
            interval_seconds=3600,
            message='please continue',
            status='active'
        )
        d = state.to_dict()
        self.assertEqual(d['worker_name'], 'test')
        self.assertEqual(d['interval_seconds'], 3600)
        self.assertEqual(d['message'], 'please continue')
        self.assertEqual(d['status'], 'active')
        self.assertIsNone(d['expire_at'])
        self.assertIsNone(d['last_beat_at'])
        self.assertEqual(d['beat_count'], 0)

    def test_heartbeat_state_from_dict_full(self):
        """Test HeartbeatState from_dict with all fields."""
        d = {
            'worker_name': 'builder',
            'interval_seconds': 14400,
            'message': 'continue working',
            'expire_at': '2026-02-05T02:00:00',
            'created_at': '2026-02-04T02:00:00',
            'last_beat_at': '2026-02-04T06:00:00',
            'beat_count': 5,
            'status': 'expired'
        }
        state = swarm.HeartbeatState.from_dict(d)
        self.assertEqual(state.worker_name, 'builder')
        self.assertEqual(state.interval_seconds, 14400)
        self.assertEqual(state.message, 'continue working')
        self.assertEqual(state.expire_at, '2026-02-05T02:00:00')
        self.assertEqual(state.created_at, '2026-02-04T02:00:00')
        self.assertEqual(state.last_beat_at, '2026-02-04T06:00:00')
        self.assertEqual(state.beat_count, 5)
        self.assertEqual(state.status, 'expired')

    def test_heartbeat_state_from_dict_minimal(self):
        """Test HeartbeatState from_dict with only required fields."""
        d = {
            'worker_name': 'test',
            'interval_seconds': 1800
        }
        state = swarm.HeartbeatState.from_dict(d)
        self.assertEqual(state.worker_name, 'test')
        self.assertEqual(state.interval_seconds, 1800)
        self.assertEqual(state.message, 'continue')
        self.assertIsNone(state.expire_at)
        self.assertEqual(state.created_at, '')
        self.assertIsNone(state.last_beat_at)
        self.assertEqual(state.beat_count, 0)
        self.assertEqual(state.status, 'active')

    def test_heartbeat_state_roundtrip(self):
        """Test HeartbeatState survives round-trip through dict."""
        original = swarm.HeartbeatState(
            worker_name='builder',
            interval_seconds=14400,
            message='keep working',
            expire_at='2026-02-05T02:00:00',
            created_at='2026-02-04T02:00:00',
            last_beat_at='2026-02-04T06:00:00',
            beat_count=2,
            status='active'
        )
        d = original.to_dict()
        restored = swarm.HeartbeatState.from_dict(d)
        self.assertEqual(original.worker_name, restored.worker_name)
        self.assertEqual(original.interval_seconds, restored.interval_seconds)
        self.assertEqual(original.message, restored.message)
        self.assertEqual(original.expire_at, restored.expire_at)
        self.assertEqual(original.created_at, restored.created_at)
        self.assertEqual(original.last_beat_at, restored.last_beat_at)
        self.assertEqual(original.beat_count, restored.beat_count)
        self.assertEqual(original.status, restored.status)

    def test_heartbeat_state_status_values(self):
        """Test HeartbeatState accepts all valid status values."""
        for status in ['active', 'paused', 'expired', 'stopped']:
            state = swarm.HeartbeatState(
                worker_name='test',
                interval_seconds=3600,
                status=status
            )
            self.assertEqual(state.status, status)


class TestHeartbeatsDirConstant(unittest.TestCase):
    """Test HEARTBEATS_DIR constant."""

    def test_heartbeats_dir_exists(self):
        """Test HEARTBEATS_DIR constant is defined."""
        self.assertTrue(hasattr(swarm, 'HEARTBEATS_DIR'))

    def test_heartbeats_dir_path(self):
        """Test HEARTBEATS_DIR is under SWARM_DIR."""
        self.assertEqual(
            swarm.HEARTBEATS_DIR,
            swarm.SWARM_DIR / "heartbeats"
        )


import json
import os
import shutil
import tempfile
from pathlib import Path


class TestHeartbeatStatePersistence(unittest.TestCase):
    """Test heartbeat state persistence functions."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.original_cwd = os.getcwd()
        os.chdir(self.temp_dir)
        # Set up temp swarm dirs
        self.original_swarm_dir = swarm.SWARM_DIR
        self.original_heartbeats_dir = swarm.HEARTBEATS_DIR
        self.original_heartbeat_lock_file = swarm.HEARTBEAT_LOCK_FILE
        swarm.SWARM_DIR = Path(self.temp_dir) / ".swarm"
        swarm.HEARTBEATS_DIR = Path(self.temp_dir) / ".swarm" / "heartbeats"
        swarm.HEARTBEAT_LOCK_FILE = Path(self.temp_dir) / ".swarm" / "heartbeat.lock"

    def tearDown(self):
        """Clean up test fixtures."""
        os.chdir(self.original_cwd)
        swarm.SWARM_DIR = self.original_swarm_dir
        swarm.HEARTBEATS_DIR = self.original_heartbeats_dir
        swarm.HEARTBEAT_LOCK_FILE = self.original_heartbeat_lock_file
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_get_heartbeat_state_path(self):
        """Test get_heartbeat_state_path returns correct path."""
        path = swarm.get_heartbeat_state_path('test-worker')
        expected = swarm.HEARTBEATS_DIR / 'test-worker.json'
        self.assertEqual(path, expected)

    def test_get_heartbeat_state_path_different_workers(self):
        """Test get_heartbeat_state_path for different workers."""
        path1 = swarm.get_heartbeat_state_path('worker1')
        path2 = swarm.get_heartbeat_state_path('worker2')
        self.assertNotEqual(path1, path2)
        self.assertTrue(str(path1).endswith('worker1.json'))
        self.assertTrue(str(path2).endswith('worker2.json'))

    def test_save_heartbeat_state_creates_file(self):
        """Test save_heartbeat_state creates state file."""
        state = swarm.HeartbeatState(
            worker_name='test-worker',
            interval_seconds=3600,
            message='continue'
        )
        swarm.save_heartbeat_state(state)

        path = swarm.get_heartbeat_state_path('test-worker')
        self.assertTrue(path.exists())

    def test_save_heartbeat_state_creates_directory(self):
        """Test save_heartbeat_state creates heartbeats directory."""
        self.assertFalse(swarm.HEARTBEATS_DIR.exists())

        state = swarm.HeartbeatState(
            worker_name='test-worker',
            interval_seconds=3600
        )
        swarm.save_heartbeat_state(state)

        self.assertTrue(swarm.HEARTBEATS_DIR.exists())

    def test_save_heartbeat_state_content(self):
        """Test save_heartbeat_state writes correct content."""
        state = swarm.HeartbeatState(
            worker_name='test-worker',
            interval_seconds=14400,
            message='please continue',
            status='active',
            beat_count=5
        )
        swarm.save_heartbeat_state(state)

        path = swarm.get_heartbeat_state_path('test-worker')
        with open(path, 'r') as f:
            data = json.load(f)

        self.assertEqual(data['worker_name'], 'test-worker')
        self.assertEqual(data['interval_seconds'], 14400)
        self.assertEqual(data['message'], 'please continue')
        self.assertEqual(data['status'], 'active')
        self.assertEqual(data['beat_count'], 5)

    def test_load_heartbeat_state_returns_none_for_nonexistent(self):
        """Test load_heartbeat_state returns None for non-existent worker."""
        result = swarm.load_heartbeat_state('nonexistent')
        self.assertIsNone(result)

    def test_load_heartbeat_state_loads_saved_state(self):
        """Test load_heartbeat_state loads previously saved state."""
        state = swarm.HeartbeatState(
            worker_name='test-worker',
            interval_seconds=3600,
            message='continue',
            expire_at='2026-02-05T00:00:00',
            created_at='2026-02-04T00:00:00',
            beat_count=3,
            status='active'
        )
        swarm.save_heartbeat_state(state)

        loaded = swarm.load_heartbeat_state('test-worker')
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.worker_name, 'test-worker')
        self.assertEqual(loaded.interval_seconds, 3600)
        self.assertEqual(loaded.message, 'continue')
        self.assertEqual(loaded.expire_at, '2026-02-05T00:00:00')
        self.assertEqual(loaded.created_at, '2026-02-04T00:00:00')
        self.assertEqual(loaded.beat_count, 3)
        self.assertEqual(loaded.status, 'active')

    def test_save_and_load_roundtrip(self):
        """Test save then load preserves all fields."""
        original = swarm.HeartbeatState(
            worker_name='builder',
            interval_seconds=14400,
            message='keep working',
            expire_at='2026-02-05T02:00:00',
            created_at='2026-02-04T02:00:00',
            last_beat_at='2026-02-04T06:00:00',
            beat_count=2,
            status='paused'
        )
        swarm.save_heartbeat_state(original)

        loaded = swarm.load_heartbeat_state('builder')
        self.assertEqual(original.worker_name, loaded.worker_name)
        self.assertEqual(original.interval_seconds, loaded.interval_seconds)
        self.assertEqual(original.message, loaded.message)
        self.assertEqual(original.expire_at, loaded.expire_at)
        self.assertEqual(original.created_at, loaded.created_at)
        self.assertEqual(original.last_beat_at, loaded.last_beat_at)
        self.assertEqual(original.beat_count, loaded.beat_count)
        self.assertEqual(original.status, loaded.status)

    def test_save_heartbeat_state_overwrites_existing(self):
        """Test save_heartbeat_state overwrites existing state."""
        state1 = swarm.HeartbeatState(
            worker_name='test-worker',
            interval_seconds=3600,
            beat_count=0
        )
        swarm.save_heartbeat_state(state1)

        state2 = swarm.HeartbeatState(
            worker_name='test-worker',
            interval_seconds=7200,
            beat_count=10
        )
        swarm.save_heartbeat_state(state2)

        loaded = swarm.load_heartbeat_state('test-worker')
        self.assertEqual(loaded.interval_seconds, 7200)
        self.assertEqual(loaded.beat_count, 10)

    def test_delete_heartbeat_state_removes_file(self):
        """Test delete_heartbeat_state removes the state file."""
        state = swarm.HeartbeatState(
            worker_name='test-worker',
            interval_seconds=3600
        )
        swarm.save_heartbeat_state(state)

        path = swarm.get_heartbeat_state_path('test-worker')
        self.assertTrue(path.exists())

        result = swarm.delete_heartbeat_state('test-worker')
        self.assertTrue(result)
        self.assertFalse(path.exists())

    def test_delete_heartbeat_state_returns_false_for_nonexistent(self):
        """Test delete_heartbeat_state returns False if file doesn't exist."""
        result = swarm.delete_heartbeat_state('nonexistent')
        self.assertFalse(result)

    def test_delete_heartbeat_state_then_load_returns_none(self):
        """Test load returns None after delete."""
        state = swarm.HeartbeatState(
            worker_name='test-worker',
            interval_seconds=3600
        )
        swarm.save_heartbeat_state(state)
        swarm.delete_heartbeat_state('test-worker')

        loaded = swarm.load_heartbeat_state('test-worker')
        self.assertIsNone(loaded)

    def test_list_heartbeat_states_empty(self):
        """Test list_heartbeat_states returns empty list when no heartbeats."""
        result = swarm.list_heartbeat_states()
        self.assertEqual(result, [])

    def test_list_heartbeat_states_empty_dir_exists(self):
        """Test list_heartbeat_states returns empty list when dir exists but empty."""
        swarm.HEARTBEATS_DIR.mkdir(parents=True)
        result = swarm.list_heartbeat_states()
        self.assertEqual(result, [])

    def test_list_heartbeat_states_single(self):
        """Test list_heartbeat_states returns single heartbeat."""
        state = swarm.HeartbeatState(
            worker_name='test-worker',
            interval_seconds=3600
        )
        swarm.save_heartbeat_state(state)

        result = swarm.list_heartbeat_states()
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].worker_name, 'test-worker')

    def test_list_heartbeat_states_multiple(self):
        """Test list_heartbeat_states returns multiple heartbeats."""
        state1 = swarm.HeartbeatState(worker_name='worker1', interval_seconds=3600)
        state2 = swarm.HeartbeatState(worker_name='worker2', interval_seconds=7200)
        state3 = swarm.HeartbeatState(worker_name='worker3', interval_seconds=1800)

        swarm.save_heartbeat_state(state1)
        swarm.save_heartbeat_state(state2)
        swarm.save_heartbeat_state(state3)

        result = swarm.list_heartbeat_states()
        self.assertEqual(len(result), 3)

    def test_list_heartbeat_states_sorted_by_name(self):
        """Test list_heartbeat_states returns states sorted by worker name."""
        state1 = swarm.HeartbeatState(worker_name='zebra', interval_seconds=3600)
        state2 = swarm.HeartbeatState(worker_name='alpha', interval_seconds=3600)
        state3 = swarm.HeartbeatState(worker_name='middle', interval_seconds=3600)

        swarm.save_heartbeat_state(state1)
        swarm.save_heartbeat_state(state2)
        swarm.save_heartbeat_state(state3)

        result = swarm.list_heartbeat_states()
        names = [s.worker_name for s in result]
        self.assertEqual(names, ['alpha', 'middle', 'zebra'])

    def test_list_heartbeat_states_skips_invalid_files(self):
        """Test list_heartbeat_states skips invalid JSON files."""
        state = swarm.HeartbeatState(worker_name='valid', interval_seconds=3600)
        swarm.save_heartbeat_state(state)

        # Create an invalid JSON file
        swarm.HEARTBEATS_DIR.mkdir(parents=True, exist_ok=True)
        invalid_path = swarm.HEARTBEATS_DIR / 'invalid.json'
        with open(invalid_path, 'w') as f:
            f.write('not valid json')

        result = swarm.list_heartbeat_states()
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].worker_name, 'valid')

    def test_list_heartbeat_states_skips_missing_required_fields(self):
        """Test list_heartbeat_states skips files missing required fields."""
        state = swarm.HeartbeatState(worker_name='valid', interval_seconds=3600)
        swarm.save_heartbeat_state(state)

        # Create a file missing required fields
        swarm.HEARTBEATS_DIR.mkdir(parents=True, exist_ok=True)
        incomplete_path = swarm.HEARTBEATS_DIR / 'incomplete.json'
        with open(incomplete_path, 'w') as f:
            json.dump({'worker_name': 'incomplete'}, f)  # missing interval_seconds

        result = swarm.list_heartbeat_states()
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].worker_name, 'valid')


class TestHeartbeatFileLock(unittest.TestCase):
    """Test heartbeat_file_lock context manager."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.original_swarm_dir = swarm.SWARM_DIR
        self.original_heartbeat_lock_file = swarm.HEARTBEAT_LOCK_FILE
        swarm.SWARM_DIR = Path(self.temp_dir) / ".swarm"
        swarm.HEARTBEAT_LOCK_FILE = Path(self.temp_dir) / ".swarm" / "heartbeat.lock"

    def tearDown(self):
        """Clean up test fixtures."""
        swarm.SWARM_DIR = self.original_swarm_dir
        swarm.HEARTBEAT_LOCK_FILE = self.original_heartbeat_lock_file
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_heartbeat_file_lock_creates_lock_file(self):
        """Test heartbeat_file_lock creates lock file."""
        with swarm.heartbeat_file_lock():
            self.assertTrue(swarm.HEARTBEAT_LOCK_FILE.exists())

    def test_heartbeat_file_lock_context_manager(self):
        """Test heartbeat_file_lock works as context manager."""
        with swarm.heartbeat_file_lock() as lock_file:
            self.assertIsNotNone(lock_file)

    def test_heartbeat_file_lock_yields_file(self):
        """Test heartbeat_file_lock yields a file object."""
        with swarm.heartbeat_file_lock() as lock_file:
            # Should be a file-like object
            self.assertTrue(hasattr(lock_file, 'fileno'))

    def test_heartbeat_file_lock_function_exists(self):
        """Test heartbeat_file_lock function exists."""
        self.assertTrue(hasattr(swarm, 'heartbeat_file_lock'))

    def test_heartbeat_lock_file_constant_exists(self):
        """Test HEARTBEAT_LOCK_FILE constant exists."""
        self.assertTrue(hasattr(swarm, 'HEARTBEAT_LOCK_FILE'))


if __name__ == '__main__':
    unittest.main()
