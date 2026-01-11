#!/usr/bin/env python3
"""Integration test LIFE-3: Respawn preserves config (command, env, tags, cwd)."""

import json
import sys
import time
import unittest
from pathlib import Path

# Import the base test class
sys.path.insert(0, str(Path(__file__).parent / "tests"))
from test_tmux_isolation import TmuxIsolatedTestCase, skip_if_no_tmux


class TestRespawnPreservesConfig(TmuxIsolatedTestCase):
    """Integration test LIFE-3: Respawn maintains original command, env, tags, and cwd."""

    @skip_if_no_tmux
    def test_respawn_preserves_config(self):
        """Verify respawn preserves all original configuration.

        This test ensures that when a worker is killed and respawned,
        all of its original configuration is preserved, including:
        - Command (with arguments)
        - Environment variables
        - Tags
        - Current working directory
        """
        # Spawn with specific config
        worker_name = f"respawn-test-{self.tmux_socket[-8:]}"
        result = self.run_swarm(
            'spawn',
            '--name', worker_name,
            '--tmux',
            '--tag', 'role:worker',
            '--tag', 'env:test',
            '--env', 'MY_VAR=hello',
            '--env', 'OTHER_VAR=world',
            '--cwd', '/tmp',
            '--',
            'bash', '-c', 'echo $MY_VAR && pwd && sleep 300'
        )
        self.assertEqual(
            result.returncode,
            0,
            f"spawn should succeed. stdout: {result.stdout!r}, stderr: {result.stderr!r}"
        )

        worker_id = self.parse_worker_id(result.stdout)
        self.assertEqual(
            worker_id,
            worker_name,
            f"Expected worker_id to be '{worker_name}', got: {worker_id!r}"
        )

        # Get original config using the helper method
        workers1 = self.get_workers()
        self.assertEqual(
            len(workers1),
            1,
            f"Expected exactly 1 worker after spawn, got {len(workers1)}"
        )
        original = workers1[0]

        # Store original config values for comparison
        original_cmd = original['cmd']
        original_tags = sorted(original['tags'])
        original_env = original['env']
        original_cwd = original['cwd']

        # Verify original config is what we set
        self.assertEqual(
            original_cmd,
            ['bash', '-c', 'echo $MY_VAR && pwd && sleep 300'],
            f"Original command should match what we spawned"
        )
        self.assertEqual(
            original_tags,
            ['env:test', 'role:worker'],
            f"Original tags should match what we set"
        )
        self.assertEqual(
            original_env,
            {'MY_VAR': 'hello', 'OTHER_VAR': 'world'},
            f"Original env should match what we set"
        )
        self.assertEqual(
            original_cwd,
            '/tmp',
            f"Original cwd should match what we set"
        )

        # Kill worker
        kill = self.run_swarm('kill', worker_id)
        self.assertEqual(
            kill.returncode,
            0,
            f"kill should succeed. stdout: {kill.stdout!r}, stderr: {kill.stderr!r}"
        )

        # Wait for kill to complete
        time.sleep(0.5)

        # Verify worker still exists in state (but stopped)
        workers_after_kill = self.get_workers()
        self.assertEqual(
            len(workers_after_kill),
            1,
            f"Worker should still exist after kill (status=stopped), "
            f"got {len(workers_after_kill)} workers"
        )
        self.assertEqual(
            workers_after_kill[0]['status'],
            'stopped',
            f"Worker should be stopped after kill, got: {workers_after_kill[0]['status']!r}"
        )

        # Respawn
        respawn = self.run_swarm('respawn', worker_id)
        self.assertEqual(
            respawn.returncode,
            0,
            f"respawn should succeed. stdout: {respawn.stdout!r}, stderr: {respawn.stderr!r}"
        )

        # Wait for respawn to complete
        time.sleep(0.5)

        # Get new config using the helper method
        # First check all workers to debug
        ls_all = self.run_swarm('ls', '--format', 'json')
        if ls_all.returncode == 0 and ls_all.stdout.strip():
            all_workers = json.loads(ls_all.stdout)
            matching = [w for w in all_workers if w.get('name') == worker_id]
            if matching:
                # Worker exists, check if socket matches
                worker_socket = matching[0].get('tmux', {}).get('socket') if matching[0].get('tmux') else None
                self.assertEqual(
                    worker_socket,
                    self.tmux_socket,
                    f"Worker '{worker_id}' socket should be '{self.tmux_socket}', got: {worker_socket!r}. "
                    f"This indicates respawn did not preserve the tmux socket."
                )

        workers2 = self.get_workers()
        self.assertEqual(
            len(workers2),
            1,
            f"Expected exactly 1 worker after respawn, got {len(workers2)}. "
            f"Socket filter: {self.tmux_socket!r}"
        )
        respawned = workers2[0]

        # Verify preserved - command
        self.assertEqual(
            respawned['cmd'],
            original_cmd,
            f"Command should be preserved after respawn. "
            f"Original: {original_cmd!r}, Respawned: {respawned['cmd']!r}"
        )

        # Verify preserved - tags
        self.assertEqual(
            sorted(respawned['tags']),
            original_tags,
            f"Tags should be preserved after respawn. "
            f"Original: {original_tags!r}, Respawned: {sorted(respawned['tags'])!r}"
        )

        # Verify preserved - env
        self.assertEqual(
            respawned['env'],
            original_env,
            f"Environment variables should be preserved after respawn. "
            f"Original: {original_env!r}, Respawned: {respawned['env']!r}"
        )

        # Verify preserved - cwd
        self.assertEqual(
            respawned['cwd'],
            original_cwd,
            f"Current working directory should be preserved after respawn. "
            f"Original: {original_cwd!r}, Respawned: {respawned['cwd']!r}"
        )

        # Verify worker is running after respawn
        self.assertEqual(
            respawned['status'],
            'running',
            f"Worker should be running after respawn, got: {respawned['status']!r}"
        )


def main():
    """Run the test."""
    print("=" * 60)
    print("Running LIFE-3: Respawn preserves config integration test")
    print("=" * 60)

    loader = unittest.TestLoader()
    suite = loader.loadTestsFromTestCase(TestRespawnPreservesConfig)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    print("=" * 60)
    if result.wasSuccessful():
        print("All tests passed!")
        print("=" * 60)
        return 0
    else:
        print("Some tests failed!")
        print("=" * 60)
        return 1


if __name__ == "__main__":
    sys.exit(main())
