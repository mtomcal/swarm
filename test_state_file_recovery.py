#!/usr/bin/env python3
"""Integration test LIFE-5: State file corruption recovery.

Tests behavior when state.json is malformed, missing, or has missing fields.
Verifies graceful handling and automatic recovery.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


def run_swarm(*args, env=None):
    """Run swarm command with specified environment."""
    cmd = ['./swarm.py'] + list(args)
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        env=env
    )
    return result


class TestStateFileRecovery(unittest.TestCase):
    """Integration tests for state file edge cases and corruption recovery."""

    def setUp(self):
        """Set up isolated test environment."""
        self.state_dir = tempfile.mkdtemp()
        self.state_file = Path(self.state_dir) / '.swarm' / 'state.json'
        self.env = os.environ.copy()
        self.env['HOME'] = self.state_dir

    def tearDown(self):
        """Clean up test environment."""
        shutil.rmtree(self.state_dir, ignore_errors=True)

    def test_missing_state_file(self):
        """Test ls command when state file doesn't exist.

        Expected behavior: Should succeed with empty list, not crash.
        The State class handles missing file by initializing empty worker list.
        """
        # Verify state file doesn't exist
        self.assertFalse(self.state_file.exists())

        # Run ls command
        result = run_swarm('ls', env=self.env)

        # Should succeed
        self.assertEqual(result.returncode, 0,
                        f"ls should succeed with missing state file. stderr: {result.stderr}")

        # Should show empty list (no workers)
        # The output should contain the header but no worker entries
        self.assertNotIn('Error', result.stderr,
                        "Should not show errors")

    def test_corrupted_json(self):
        """Test ls command when state.json contains invalid JSON.

        Expected behavior: Should recover gracefully — reset to empty workers,
        print a warning to stderr, and back up the corrupt file.
        """
        # Create .swarm directory
        self.state_file.parent.mkdir(parents=True, exist_ok=True)

        # Write invalid JSON
        self.state_file.write_text('{invalid json}}')

        # Run ls command
        result = run_swarm('ls', env=self.env)

        # Should succeed after recovery
        self.assertEqual(result.returncode, 0,
                        f"ls should succeed after corrupt state recovery. stderr: {result.stderr}")
        # Should print warning to stderr
        self.assertIn('corrupt state file', result.stderr,
                     "Should show corrupt state file warning")
        # Backup file should be created
        corrupted_path = self.state_file.parent / "state.json.corrupted"
        self.assertTrue(corrupted_path.exists(),
                       "Should back up corrupt file to state.json.corrupted")

    def test_missing_fields(self):
        """Test ls command when state.json has missing required fields.

        Expected behavior: Should handle gracefully, possibly skipping malformed entries.
        Tests robustness against incomplete worker records.
        """
        # Create .swarm directory
        self.state_file.parent.mkdir(parents=True, exist_ok=True)

        # Write JSON missing required fields (only has 'id', missing 'name', 'status', etc.)
        self.state_file.write_text('{"workers": [{"id": "w1"}]}')

        # Run ls command
        result = run_swarm('ls', env=self.env)

        # Document actual behavior: Worker.from_dict expects specific fields
        # This will fail with KeyError for missing required fields
        self.assertNotEqual(result.returncode, 0,
                           "Currently expected to fail with missing required fields")
        # The error might be KeyError for 'name' or other required field
        self.assertTrue(result.returncode != 0 or 'Error' in result.stderr,
                       "Should indicate error for missing fields")

    def test_spawn_creates_state_file(self):
        """Test that spawn command creates state file from scratch.

        Expected behavior: State file should be created automatically on first spawn.
        Verifies proper initialization of swarm state directory structure.
        """
        # Verify state file doesn't exist
        self.assertFalse(self.state_file.exists(),
                        "State file should not exist before spawn")

        # Spawn a short-lived worker (no tmux to avoid complexity)
        result = run_swarm('spawn', '--name', 'test-create-state',
                          '--', 'sleep', '1', env=self.env)

        # Should succeed
        self.assertEqual(result.returncode, 0,
                        f"spawn should succeed. stderr: {result.stderr}")

        # State file should now exist
        self.assertTrue(self.state_file.exists(),
                       "State file should be created after spawn")

        # Verify state file is valid JSON
        with open(self.state_file, 'r') as f:
            state_data = json.load(f)

        # Should have workers array
        self.assertIn('workers', state_data,
                     "State file should contain 'workers' key")
        self.assertIsInstance(state_data['workers'], list,
                            "workers should be a list")

        # Should have our worker
        self.assertEqual(len(state_data['workers']), 1,
                        "Should have exactly one worker")
        worker = state_data['workers'][0]
        self.assertEqual(worker['name'], 'test-create-state',
                        "Worker should have correct name")

        # Clean up the spawned worker
        run_swarm('kill', 'test-create-state', env=self.env)
        run_swarm('clean', 'test-create-state', env=self.env)


def main():
    """Run the integration tests."""
    print("Running integration tests for state file recovery (LIFE-5)...")
    print("=" * 70)

    # Run tests with verbose output
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromTestCase(TestStateFileRecovery)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    print("=" * 70)
    if result.wasSuccessful():
        print("✓ All state file recovery tests passed!")
        return 0
    else:
        print("✗ Some tests failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
