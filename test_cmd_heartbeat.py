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


if __name__ == '__main__':
    unittest.main()
