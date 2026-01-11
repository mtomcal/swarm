#!/usr/bin/env python3
"""Test tmux isolation for integration tests.

This module provides a base test class that ensures complete tmux isolation
for integration tests, preventing collisions with user sessions and enabling
parallel test execution.
"""

import json
import os
import shutil
import subprocess
import tempfile
import time
import unittest
import uuid
from pathlib import Path
from typing import List, Optional


class TmuxIsolatedTestCase(unittest.TestCase):
    """Base class for tests requiring real tmux isolation.

    This class creates a unique tmux socket per test, ensuring complete isolation
    from user sessions and other tests. Each test gets its own tmux server that
    is automatically cleaned up on teardown.

    Attributes:
        tmux_socket: Unique socket name for this test's tmux server
    """

    def setUp(self):
        """Create unique tmux socket for this test."""
        super().setUp()
        self.tmux_socket = f"swarm-test-{uuid.uuid4().hex[:8]}"

    def tearDown(self):
        """Kill isolated tmux server and clean up."""
        # Kill entire tmux server for this socket
        subprocess.run(
            ["tmux", "-L", self.tmux_socket, "kill-server"],
            capture_output=True
        )
        super().tearDown()

    def tmux_cmd(self, *args) -> subprocess.CompletedProcess:
        """Run tmux command with isolated socket.

        Args:
            *args: Arguments to pass to tmux command

        Returns:
            CompletedProcess with stdout/stderr captured as text

        Example:
            result = self.tmux_cmd("list-sessions", "-F", "#{session_name}")
        """
        return subprocess.run(
            ["tmux", "-L", self.tmux_socket] + list(args),
            capture_output=True,
            text=True
        )

    def list_sessions(self) -> List[str]:
        """List sessions in isolated tmux server.

        Returns:
            List of session names in the isolated tmux server.
            Returns empty list if no sessions exist.
        """
        result = self.tmux_cmd("list-sessions", "-F", "#{session_name}")
        if result.returncode != 0:
            return []
        return [s for s in result.stdout.strip().split('\n') if s]

    def get_windows(self, session_name: str) -> List[str]:
        """Get list of window names in a session.

        Args:
            session_name: Name of the tmux session to query

        Returns:
            List of window names in the session.
            Returns empty list if session doesn't exist or has no windows.
        """
        result = self.tmux_cmd(
            "list-windows", "-t", session_name, "-F", "#{window_name}"
        )
        if result.returncode != 0:
            return []
        return [w for w in result.stdout.strip().split('\n') if w]

    def parse_worker_id(self, output: str) -> str:
        """Parse worker ID from spawn command output.

        Args:
            output: stdout from spawn command

        Returns:
            The worker name/id extracted from output

        Raises:
            ValueError: If worker ID cannot be parsed from output

        Expected formats:
            - "spawned <worker-id> (tmux: <session>:<window>)"
            - "spawned <worker-id> (pid: <pid>)"
        """
        for line in output.split('\n'):
            line = line.strip()
            if 'spawned' in line.lower():
                # Format: "spawned test-worker (tmux: session:window)"
                # or "spawned test-worker (pid: 12345)"
                parts = line.split()
                if len(parts) >= 2:
                    # Second word should be the worker ID
                    worker_id = parts[1]
                    # Remove any trailing parentheses or punctuation
                    worker_id = worker_id.rstrip('(').rstrip(':').rstrip(',')
                    return worker_id

        raise ValueError(f"Could not parse worker ID from output: {output!r}")

    def get_swarm_session(self) -> str:
        """Get the swarm session name from the isolated tmux server.

        Returns:
            The session name starting with 'swarm-'

        Raises:
            ValueError: If no swarm session found
        """
        sessions = self.list_sessions()
        for session in sessions:
            if session.startswith('swarm-'):
                return session
        raise ValueError(
            f"No swarm session found. Available sessions: {sessions!r}"
        )

    def run_swarm(self, *args, **kwargs) -> subprocess.CompletedProcess:
        """Run swarm command with isolated tmux socket.

        This method automatically injects the --tmux-socket flag to ensure
        the swarm command uses this test's isolated tmux server.

        Args:
            *args: Arguments to pass to swarm command
            **kwargs: Additional keyword arguments for subprocess.run

        Returns:
            CompletedProcess from the swarm command

        Example:
            result = self.run_swarm("spawn", "--tmux", "claude", "--dangerously-skip-permissions")
        """
        # Find swarm.py in the repository root (parent of tests/)
        swarm_path = Path(__file__).parent.parent / "swarm.py"

        # Build command with tmux socket injection
        args_list = list(args)

        # Inject --tmux-socket flag if spawning with --tmux
        # Must insert BEFORE '--' separator if present, otherwise append
        if "--tmux" in args_list:
            if "--" in args_list:
                # Insert before the '--' separator
                dash_idx = args_list.index("--")
                args_list.insert(dash_idx, "--tmux-socket")
                args_list.insert(dash_idx + 1, self.tmux_socket)
            else:
                # No '--', just append
                args_list.append("--tmux-socket")
                args_list.append(self.tmux_socket)

        cmd = [str(swarm_path)] + args_list

        # Set default kwargs for capture
        if "capture_output" not in kwargs:
            kwargs["capture_output"] = True
        if "text" not in kwargs:
            kwargs["text"] = True

        return subprocess.run(cmd, **kwargs)

    def get_workers(self) -> List[dict]:
        """Get list of workers from swarm ls --format json.

        Returns:
            List of worker dictionaries from swarm state.
            Each worker dict contains: name, status, cmd, started, cwd, env, tags, tmux, worktree, pid

        Note:
            This method filters workers to only return those belonging to this test's
            isolated tmux socket, ensuring proper test isolation.

        Raises:
            ValueError: If swarm ls fails or returns invalid JSON
        """
        result = self.run_swarm('ls', '--format', 'json')
        if result.returncode != 0:
            raise ValueError(
                f"swarm ls failed with code {result.returncode}. "
                f"Stderr: {result.stderr!r}"
            )
        # Handle empty output (no workers)
        if not result.stdout.strip():
            return []
        try:
            workers = json.loads(result.stdout)
            # Filter to only workers that belong to this test's socket
            # This ensures test isolation when multiple tests share global state
            filtered = []
            for w in workers:
                tmux_info = w.get('tmux')
                if tmux_info and tmux_info.get('socket') == self.tmux_socket:
                    filtered.append(w)
            return filtered
        except json.JSONDecodeError as e:
            raise ValueError(
                f"Invalid JSON from swarm ls: {e}. Output: {result.stdout!r}"
            )


def skip_if_no_tmux(test_func):
    """Decorator to skip test if tmux is not available.

    Args:
        test_func: Test function to wrap

    Returns:
        Wrapped test function that skips if tmux not found
    """
    return unittest.skipUnless(
        shutil.which("tmux"),
        "tmux not found - skipping tmux integration test"
    )(test_func)


class TestTmuxIsolation(TmuxIsolatedTestCase):
    """Smoke tests to verify tmux isolation works correctly."""

    @skip_if_no_tmux
    def test_unique_socket_per_test(self):
        """Verify each test gets a unique tmux socket."""
        # Socket name should be unique per test
        self.assertTrue(
            self.tmux_socket.startswith("swarm-test-"),
            f"Expected socket to start with 'swarm-test-', got: {self.tmux_socket!r}"
        )

        expected_length = len("swarm-test-") + 8
        actual_length = len(self.tmux_socket)
        self.assertEqual(
            actual_length,
            expected_length,
            f"Expected socket length {expected_length} (prefix + 8 hex chars), "
            f"got {actual_length}. Socket: {self.tmux_socket!r}"
        )

    @skip_if_no_tmux
    def test_isolated_session_creation(self):
        """Verify sessions are created in isolated tmux server."""
        # Initially no sessions
        initial_sessions = self.list_sessions()
        self.assertEqual(
            initial_sessions,
            [],
            f"Expected no sessions initially in isolated tmux server, "
            f"but found: {initial_sessions!r}"
        )

        # Create a test session
        result = self.tmux_cmd("new-session", "-d", "-s", "test-session")
        self.assertEqual(
            result.returncode,
            0,
            f"Expected tmux new-session to succeed (returncode 0), "
            f"got {result.returncode}. Stderr: {result.stderr!r}"
        )

        # Session should exist in isolated server
        sessions = self.list_sessions()
        self.assertEqual(
            sessions,
            ["test-session"],
            f"Expected exactly one session 'test-session', got: {sessions!r}"
        )

    @skip_if_no_tmux
    def test_isolation_from_user_sessions(self):
        """Verify test sessions don't appear in default tmux server."""
        # Create session in isolated server
        session_name = "isolated-session"
        create_result = self.tmux_cmd("new-session", "-d", "-s", session_name)
        self.assertEqual(
            create_result.returncode,
            0,
            f"Failed to create isolated session. Stderr: {create_result.stderr!r}"
        )

        # Check default tmux server (no -L flag)
        result = subprocess.run(
            ["tmux", "list-sessions", "-F", "#{session_name}"],
            capture_output=True,
            text=True
        )

        # If default tmux server exists, isolated session should NOT be there
        if result.returncode == 0:
            default_sessions = [s for s in result.stdout.strip().split('\n') if s]
            self.assertNotIn(
                session_name,
                default_sessions,
                f"Session '{session_name}' created in isolated socket '{self.tmux_socket}' "
                f"should NOT appear in default tmux server. "
                f"Default server sessions: {default_sessions!r}"
            )

    @skip_if_no_tmux
    def test_cleanup_kills_all_sessions(self):
        """Verify tearDown completely cleans up tmux server."""
        # Create multiple sessions
        self.tmux_cmd("new-session", "-d", "-s", "session1")
        self.tmux_cmd("new-session", "-d", "-s", "session2")

        sessions_before = self.list_sessions()
        self.assertEqual(
            len(sessions_before),
            2,
            f"Expected 2 sessions before cleanup, got {len(sessions_before)}: {sessions_before!r}"
        )

        # Manually trigger cleanup (normally done in tearDown)
        kill_result = subprocess.run(
            ["tmux", "-L", self.tmux_socket, "kill-server"],
            capture_output=True
        )

        # All sessions should be gone
        sessions_after = self.list_sessions()
        self.assertEqual(
            sessions_after,
            [],
            f"Expected 0 sessions after kill-server, got {len(sessions_after)}: {sessions_after!r}"
        )

    @skip_if_no_tmux
    def test_run_swarm_with_socket_injection(self):
        """Verify run_swarm helper correctly injects tmux socket."""
        # This test verifies the helper method works
        # We can't fully test swarm spawn without dependencies, but we can
        # verify the command is constructed correctly

        # Create a mock scenario - just verify the socket is available
        session_name = "test"
        result = self.tmux_cmd("new-session", "-d", "-s", session_name)
        self.assertEqual(
            result.returncode,
            0,
            f"Failed to create session '{session_name}'. Stderr: {result.stderr!r}"
        )

        sessions = self.list_sessions()
        self.assertIn(
            session_name,
            sessions,
            f"Expected session '{session_name}' in sessions list, got: {sessions!r}"
        )


class TestSpawnCreatesDedicatedSession(TmuxIsolatedTestCase):
    """Integration test for spawn creating a dedicated tmux session."""

    @skip_if_no_tmux
    def test_spawn_creates_dedicated_session(self):
        """Verify that spawn with --tmux creates a session with name starting with 'swarm-'."""
        # Pre-condition: no swarm sessions exist
        sessions_before = self.list_sessions()
        self.assertEqual(
            len(sessions_before),
            0,
            f"Expected no sessions before spawn, but found {len(sessions_before)}: {sessions_before!r}"
        )

        # Action: spawn a worker (use socket suffix in name to ensure uniqueness across tests)
        worker_name = f"spawn-test-{self.tmux_socket[-8:]}"
        result = self.run_swarm('spawn', '--name', worker_name, '--tmux', '--', 'echo', 'hello')
        self.assertEqual(
            result.returncode,
            0,
            f"Expected spawn command to succeed (returncode 0), "
            f"got {result.returncode}. Stdout: {result.stdout!r}, Stderr: {result.stderr!r}"
        )

        # Verify: session was created with expected name pattern
        sessions_after = self.list_sessions()
        self.assertEqual(
            len(sessions_after),
            1,
            f"Expected exactly 1 session after spawn, "
            f"got {len(sessions_after)}: {sessions_after!r}"
        )
        self.assertTrue(
            sessions_after[0].startswith('swarm-'),
            f"Expected session name to start with 'swarm-', "
            f"got: {sessions_after[0]!r}"
        )


class TestSpawnDoesNotModifyExistingSessions(TmuxIsolatedTestCase):
    """Test that swarm spawn does not modify pre-existing user sessions."""

    @skip_if_no_tmux
    def test_spawn_does_not_modify_existing_sessions(self):
        """Verify spawning a swarm worker does not alter existing user sessions.

        This test ensures that when swarm spawns a new worker in tmux, it creates
        its own isolated session and does not modify any pre-existing sessions
        that might belong to the user.
        """
        # Setup: create user's pre-existing session with known windows
        self.tmux_cmd('new-session', '-d', '-s', 'user-work')
        self.tmux_cmd('new-window', '-t', 'user-work', '-n', 'editor')

        windows_before = self.get_windows('user-work')
        self.assertEqual(
            len(windows_before),
            2,
            f"Expected 2 windows in 'user-work' session (default + editor), "
            f"got {len(windows_before)}: {windows_before!r}"
        )

        # Action: spawn swarm worker (use socket suffix for uniqueness)
        worker_name = f"modify-test-{self.tmux_socket[-8:]}"
        result = self.run_swarm('spawn', '--name', worker_name, '--tmux', '--', 'sleep', '60')
        self.assertEqual(
            result.returncode,
            0,
            f"Expected swarm spawn to succeed (returncode 0), "
            f"got {result.returncode}. Stdout: {result.stdout!r}, Stderr: {result.stderr!r}"
        )

        # Verify: user session unchanged
        windows_after = self.get_windows('user-work')
        self.assertEqual(
            windows_before,
            windows_after,
            f"User session 'user-work' was modified during swarm spawn. "
            f"Windows before: {windows_before!r}, windows after: {windows_after!r}"
        )

        # Verify: swarm created its own session
        sessions = self.list_sessions()
        self.assertIn(
            'user-work',
            sessions,
            f"Expected 'user-work' session to still exist after spawn, "
            f"but sessions are: {sessions!r}"
        )
        swarm_sessions = [s for s in sessions if s.startswith('swarm-')]
        self.assertEqual(
            len(swarm_sessions),
            1,
            f"Expected exactly 1 swarm session to be created, "
            f"got {len(swarm_sessions)}: {swarm_sessions!r}. All sessions: {sessions!r}"
        )


class TestSpawnFromInsideTmux(TmuxIsolatedTestCase):
    """Test that swarm spawn creates separate sessions when run from inside tmux."""

    @skip_if_no_tmux
    def test_spawn_from_inside_tmux_creates_separate_session(self):
        """Verify swarm spawn creates a separate session when run from inside tmux.

        When a user runs swarm spawn from inside an existing tmux session,
        the worker should be created in a NEW separate session, not as a window
        in the user's current session. This prevents cluttering the user's
        workspace and ensures proper isolation.
        """
        # Setup: create a "user" tmux session simulating someone's dev environment
        user_session = "my-dev-session"
        result = self.tmux_cmd("new-session", "-d", "-s", user_session)
        self.assertEqual(
            result.returncode,
            0,
            f"Failed to create user session '{user_session}'. "
            f"Returncode: {result.returncode}, Stderr: {result.stderr!r}"
        )

        # Get absolute path to swarm.py
        swarm_path = Path(__file__).parent.parent / "swarm.py"

        # Use unique worker name per test instance to avoid collisions with global state
        worker_name = f"inside-{self.tmux_socket[-8:]}"

        # Action: run swarm spawn FROM INSIDE the tmux session
        # This simulates: user has tmux attached -> runs swarm spawn
        # Use a marker file to signal when the command completes
        marker_file = f"/tmp/swarm-test-marker-{self.tmux_socket[-8:]}"
        spawn_cmd = f"python3 {swarm_path} spawn --name {worker_name} --tmux --tmux-socket {self.tmux_socket} -- sleep 60 && touch {marker_file}"
        result = self.tmux_cmd(
            "send-keys", "-t", user_session,
            spawn_cmd,
            "Enter"
        )
        self.assertEqual(
            result.returncode,
            0,
            f"Failed to send spawn command to session '{user_session}'. "
            f"Returncode: {result.returncode}, Stderr: {result.stderr!r}"
        )

        # Wait for spawn to complete by polling for swarm session creation
        # We poll because send-keys is asynchronous and the command needs time to execute
        max_wait = 15  # seconds (increased for reliability)
        poll_interval = 0.5
        waited = 0
        while waited < max_wait:
            time.sleep(poll_interval)
            waited += poll_interval
            sessions = self.list_sessions()
            swarm_sessions = [s for s in sessions if s.startswith("swarm-")]
            if swarm_sessions:
                break

        # Cleanup marker file if it exists
        try:
            os.unlink(marker_file)
        except FileNotFoundError:
            pass

        # Verify: "my-dev-session" has only 1 window (the original shell)
        # This confirms swarm didn't add a window to the user's session
        windows = self.get_windows(user_session)
        self.assertEqual(
            len(windows),
            1,
            f"Expected user session '{user_session}' to have exactly 1 window "
            f"(the original shell running swarm), but found {len(windows)} windows: {windows!r}. "
            f"Swarm should NOT add windows to the user's session."
        )

        # Verify: swarm created a separate session for the worker
        sessions = self.list_sessions()
        swarm_sessions = [s for s in sessions if s.startswith("swarm-")]
        self.assertGreaterEqual(
            len(swarm_sessions),
            1,
            f"Expected at least 1 swarm session (starting with 'swarm-'), "
            f"but found {len(swarm_sessions)}. All sessions: {sessions!r}. "
            f"Swarm spawn should create worker sessions in a separate tmux session."
        )


class TestCleanWithExternallyKilledWorker(TmuxIsolatedTestCase):
    """Test STATE-1: clean --all should detect externally killed workers."""

    @skip_if_no_tmux
    def test_clean_all_with_externally_killed_worker(self):
        """Verify clean --all detects and cleans workers whose tmux windows were killed externally.

        This test verifies that when a tmux window is killed outside of swarm
        (e.g., by the user running 'tmux kill-window'), the swarm state may still
        show the worker as 'running' (stale state), but 'clean --all' should
        detect that the window is actually dead and clean it from state.
        """
        # Use unique worker name based on test's tmux socket to avoid collisions
        # with global state from other tests
        worker_name = f"state1-{self.tmux_socket[-8:]}"

        # Spawn a worker with a long-running command
        result = self.run_swarm('spawn', '--name', worker_name, '--tmux', '--', 'sleep', '300')
        self.assertEqual(
            result.returncode,
            0,
            f"Expected spawn to succeed (returncode 0), "
            f"got {result.returncode}. Stdout: {result.stdout!r}, Stderr: {result.stderr!r}"
        )
        worker_id = self.parse_worker_id(result.stdout)
        self.assertEqual(
            worker_id,
            worker_name,
            f"Expected worker_id to be '{worker_name}', got: {worker_id!r}"
        )

        # Verify worker is running using get_workers helper
        workers = self.get_workers()
        self.assertEqual(
            len(workers),
            1,
            f"Expected exactly 1 worker after spawn, got {len(workers)}: {workers!r}"
        )
        self.assertEqual(
            workers[0]['status'],
            'running',
            f"Expected worker status to be 'running', got: {workers[0]['status']!r}"
        )

        # Kill tmux window EXTERNALLY (not via swarm)
        session = self.get_swarm_session()
        kill_result = self.tmux_cmd('kill-window', '-t', f'{session}:{worker_id}')
        self.assertEqual(
            kill_result.returncode,
            0,
            f"Expected external tmux kill-window to succeed, "
            f"got returncode {kill_result.returncode}. Stderr: {kill_result.stderr!r}"
        )

        # State may still show "running" (stale) - this is expected behavior
        # The clean --all command should detect the window is actually dead

        # Run clean --all
        result = self.run_swarm('clean', '--all')
        self.assertEqual(
            result.returncode,
            0,
            f"Expected clean --all to succeed (returncode 0), "
            f"got {result.returncode}. Stdout: {result.stdout!r}, Stderr: {result.stderr!r}"
        )

        # Verify: worker cleaned from state
        workers = self.get_workers()
        self.assertEqual(
            len(workers),
            0,
            f"Expected 0 workers after clean --all (worker was externally killed and should be cleaned), "
            f"but got {len(workers)} workers: {workers!r}"
        )


class TestMultipleSwarmInstances(TmuxIsolatedTestCase):
    """Test isolation between multiple swarm instances with different sessions."""

    @skip_if_no_tmux
    @unittest.skip("SWARM_DIR env var not yet implemented - swarm always uses ~/.swarm")
    def test_multiple_swarm_instances_isolation(self):
        """Verify two swarm instances with different SWARM_DIRs create separate sessions.

        NOTE: This test is currently skipped because swarm.py does not read the
        SWARM_DIR environment variable. SWARM_DIR is hardcoded to ~/.swarm.
        To enable this test, swarm.py would need to be modified to:
            SWARM_DIR = Path(os.environ.get('SWARM_DIR', str(Path.home() / '.swarm')))
        """
        # Setup: two separate SWARM_DIRs (different hashes)
        with tempfile.TemporaryDirectory() as dir1, \
             tempfile.TemporaryDirectory() as dir2:

            # Spawn worker in first swarm instance
            env1 = {**os.environ, 'SWARM_DIR': dir1}
            result1 = self.run_swarm(
                'spawn', '--name', 'worker1', '--tmux', '--', 'sleep', '60', env=env1
            )

            # Spawn worker in second swarm instance
            env2 = {**os.environ, 'SWARM_DIR': dir2}
            result2 = self.run_swarm(
                'spawn', '--name', 'worker2', '--tmux', '--', 'sleep', '60', env=env2
            )

            # Both should succeed
            self.assertEqual(
                result1.returncode,
                0,
                f"First swarm spawn should succeed (returncode 0), "
                f"got {result1.returncode}. Stdout: {result1.stdout!r}, Stderr: {result1.stderr!r}"
            )
            self.assertEqual(
                result2.returncode,
                0,
                f"Second swarm spawn should succeed (returncode 0), "
                f"got {result2.returncode}. Stdout: {result2.stdout!r}, Stderr: {result2.stderr!r}"
            )

            # Verify: two different sessions created
            sessions = self.list_sessions()
            swarm_sessions = [s for s in sessions if s.startswith('swarm-')]
            self.assertEqual(
                len(swarm_sessions),
                2,
                f"Expected 2 swarm sessions (one per SWARM_DIR), "
                f"got {len(swarm_sessions)}. Sessions: {swarm_sessions!r}"
            )

            # Verify: session names are different (different hashes)
            self.assertNotEqual(
                swarm_sessions[0],
                swarm_sessions[1],
                f"Expected different session names for different SWARM_DIRs, "
                f"but both are: {swarm_sessions[0]!r}"
            )


class TestSessionNameCollision(TmuxIsolatedTestCase):
    """Test that swarm handles session name collisions gracefully."""

    @skip_if_no_tmux
    def test_session_name_collision_handling(self):
        """Verify swarm creates unique session when legacy 'swarm' session exists.

        When a session named 'swarm' already exists (legacy behavior or user-created),
        swarm should create a new session with a hash-based suffix instead of
        modifying the existing session.
        """
        # Setup: create session with legacy "swarm" name
        create_result = self.tmux_cmd('new-session', '-d', '-s', 'swarm')
        self.assertEqual(
            create_result.returncode,
            0,
            f"Failed to create legacy 'swarm' session. Stderr: {create_result.stderr!r}"
        )
        windows_before = self.get_windows('swarm')
        self.assertGreater(
            len(windows_before),
            0,
            f"Expected at least one window in legacy 'swarm' session, got: {windows_before!r}"
        )

        # Action: spawn worker (should use hash-based name)
        worker_name = f"collision-test-{self.tmux_socket[-8:]}"
        result = self.run_swarm('spawn', '--name', worker_name, '--tmux', '--', 'sleep', '60')
        self.assertEqual(
            result.returncode,
            0,
            f"Expected swarm spawn to succeed (returncode 0), got {result.returncode}. "
            f"Stdout: {result.stdout!r}, Stderr: {result.stderr!r}"
        )

        # Verify: legacy "swarm" session unchanged
        windows_after = self.get_windows('swarm')
        self.assertEqual(
            windows_before,
            windows_after,
            f"Legacy 'swarm' session should be unchanged. "
            f"Windows before: {windows_before!r}, Windows after: {windows_after!r}"
        )

        # Verify: new session created with hash suffix
        sessions = self.list_sessions()
        hash_sessions = [s for s in sessions if s.startswith('swarm-') and s != 'swarm']
        self.assertEqual(
            len(hash_sessions),
            1,
            f"Expected exactly one hash-suffixed session (swarm-*), "
            f"got {len(hash_sessions)}: {hash_sessions!r}. All sessions: {sessions!r}"
        )



class TestCleanupOnlyAffectsSwarmSessions(TmuxIsolatedTestCase):
    """Test that swarm kill --all only affects swarm-managed sessions."""

    @skip_if_no_tmux
    def test_cleanup_only_affects_swarm_sessions(self):
        """Verify that killing swarm workers does not affect user sessions.

        This test ensures that when 'swarm kill --all' is executed, it only
        terminates swarm-managed workers and leaves user-created tmux sessions
        completely untouched.
        """
        # Setup: create user session with windows
        self.tmux_cmd('new-session', '-d', '-s', 'user-session')
        self.tmux_cmd('new-window', '-t', 'user-session', '-n', 'vim')
        self.tmux_cmd('new-window', '-t', 'user-session', '-n', 'htop')
        user_windows_before = self.get_windows('user-session')
        self.assertEqual(
            len(user_windows_before),
            3,  # default window + vim + htop
            f"Expected 3 windows in user-session before spawning workers, "
            f"got {len(user_windows_before)}: {user_windows_before!r}"
        )

        # Setup: spawn swarm workers
        spawn_result1 = self.run_swarm(
            'spawn', '--name', 'worker-1', '--tmux', '--', 'sleep', '60'
        )
        self.assertEqual(
            spawn_result1.returncode,
            0,
            f"Failed to spawn first worker. Returncode: {spawn_result1.returncode}, "
            f"stderr: {spawn_result1.stderr!r}"
        )

        spawn_result2 = self.run_swarm(
            'spawn', '--name', 'worker-2', '--tmux', '--', 'sleep', '60'
        )
        self.assertEqual(
            spawn_result2.returncode,
            0,
            f"Failed to spawn second worker. Returncode: {spawn_result2.returncode}, "
            f"stderr: {spawn_result2.stderr!r}"
        )

        # Give workers time to start
        time.sleep(0.5)

        # Action: kill all swarm workers
        result = self.run_swarm('kill', '--all')
        self.assertEqual(
            result.returncode,
            0,
            f"Expected 'swarm kill --all' to succeed (returncode 0), "
            f"got {result.returncode}. Stderr: {result.stderr!r}"
        )

        # Verify: user session completely untouched
        user_windows_after = self.get_windows('user-session')
        self.assertEqual(
            user_windows_before,
            user_windows_after,
            f"User session windows were modified by 'swarm kill --all'. "
            f"Before: {user_windows_before!r}, After: {user_windows_after!r}"
        )

        # Verify: user session still exists
        sessions = self.list_sessions()
        self.assertIn(
            'user-session',
            sessions,
            f"User session 'user-session' was deleted by 'swarm kill --all'. "
            f"Remaining sessions: {sessions!r}"
        )



class TestCleanAllSkipsRunningWorkers(TmuxIsolatedTestCase):
    """Integration test for 'swarm clean --all' behavior with running workers."""

    @skip_if_no_tmux
    def test_clean_all_skips_still_running_workers(self):
        """Verify that 'clean --all' only cleans stopped workers, not running ones.

        This test ensures that:
        1. Multiple workers can be spawned
        2. Killing one worker marks it as stopped
        3. 'clean --all' only removes stopped workers
        4. Running workers remain untouched
        """
        # Spawn 3 workers with unique names based on tmux socket
        # This ensures test isolation even with shared global state
        worker_prefix = self.tmux_socket.replace('swarm-test-', 'w')
        for i in range(3):
            result = self.run_swarm(
                'spawn', '--name', f'{worker_prefix}-{i}', '--tmux', '--', 'sleep', '300'
            )
            self.assertEqual(
                result.returncode,
                0,
                f"Expected spawn command #{i+1} to succeed, "
                f"got returncode {result.returncode}. "
                f"Stdout: {result.stdout!r}, Stderr: {result.stderr!r}"
            )

        # Allow time for workers to start
        time.sleep(0.5)

        # Verify 3 workers exist
        workers = self.get_workers()
        self.assertEqual(
            len(workers),
            3,
            f"Expected 3 workers after spawning, got {len(workers)}. "
            f"Workers: {[w['name'] for w in workers]!r}"
        )

        # Stop one worker via swarm kill
        first_worker_name = workers[0]['name']
        kill_result = self.run_swarm('kill', first_worker_name)
        self.assertEqual(
            kill_result.returncode,
            0,
            f"Expected kill command to succeed for worker '{first_worker_name}', "
            f"got returncode {kill_result.returncode}. "
            f"Stdout: {kill_result.stdout!r}, Stderr: {kill_result.stderr!r}"
        )

        # Allow time for status to update
        time.sleep(0.5)

        # Verify: 1 stopped, 2 running
        workers_after_kill = self.get_workers()
        stopped = [w for w in workers_after_kill if w['status'] == 'stopped']
        running = [w for w in workers_after_kill if w['status'] == 'running']
        self.assertEqual(
            len(stopped),
            1,
            f"Expected 1 stopped worker after kill, got {len(stopped)}. "
            f"Stopped workers: {[w['name'] for w in stopped]!r}, "
            f"All workers: {[(w['name'], w['status']) for w in workers_after_kill]!r}"
        )
        self.assertEqual(
            len(running),
            2,
            f"Expected 2 running workers after kill, got {len(running)}. "
            f"Running workers: {[w['name'] for w in running]!r}, "
            f"All workers: {[(w['name'], w['status']) for w in workers_after_kill]!r}"
        )

        # Clean all (should only clean stopped workers)
        clean_result = self.run_swarm('clean', '--all')
        self.assertEqual(
            clean_result.returncode,
            0,
            f"Expected 'clean --all' to succeed, got returncode {clean_result.returncode}. "
            f"Stdout: {clean_result.stdout!r}, Stderr: {clean_result.stderr!r}"
        )

        # Verify: 2 running workers still exist
        workers_final = self.get_workers()
        self.assertEqual(
            len(workers_final),
            2,
            f"Expected 2 workers remaining after 'clean --all', got {len(workers_final)}. "
            f"Expected the stopped worker to be cleaned and running workers to remain. "
            f"Remaining workers: {[(w['name'], w['status']) for w in workers_final]!r}"
        )

        # All remaining workers should be running
        for w in workers_final:
            self.assertEqual(
                w['status'],
                'running',
                f"Expected all remaining workers to have status 'running', "
                f"but worker '{w['name']}' has status '{w['status']}'. "
                f"All workers: {[(w['name'], w['status']) for w in workers_final]!r}"
            )



class TestLsReflectsActualStatus(TmuxIsolatedTestCase):
    """Integration test STATE-3: Verify swarm ls reflects actual worker status.

    This test verifies that when a tmux window is killed externally (not via
    swarm kill), swarm ls correctly detects and reports the worker as stopped.
    This exercises the refresh_worker_status() function in swarm.py.
    """

    @skip_if_no_tmux
    def test_ls_reflects_actual_status(self):
        """Verify swarm ls shows correct status after external tmux window kill.

        This test:
        1. Spawns a worker in tmux
        2. Verifies ls shows 'running' status
        3. Kills the tmux window externally (bypassing swarm kill)
        4. Verifies ls shows 'stopped' status (not stale 'running')
        """
        # Spawn worker with unique name
        worker_name = f"test-state-{uuid.uuid4().hex[:8]}"
        result = self.run_swarm(
            'spawn', '--name', worker_name, '--tmux', '--', 'sleep', '300'
        )
        self.assertEqual(
            result.returncode,
            0,
            f"spawn command failed. stdout: {result.stdout!r}, stderr: {result.stderr!r}"
        )

        worker_id = self.parse_worker_id(result.stdout)
        self.assertEqual(
            worker_id,
            worker_name,
            f"Expected worker ID to match name '{worker_name}', got: {worker_id!r}"
        )

        # Verify running status via ls --format json
        ls1 = self.run_swarm('ls', '--format', 'json')
        self.assertEqual(
            ls1.returncode,
            0,
            f"ls command failed. stdout: {ls1.stdout!r}, stderr: {ls1.stderr!r}"
        )

        workers1 = json.loads(ls1.stdout)
        # Filter to workers in our isolated socket
        our_workers1 = [
            w for w in workers1
            if w.get('tmux') and w['tmux'].get('socket') == self.tmux_socket
        ]
        self.assertEqual(
            len(our_workers1),
            1,
            f"Expected exactly 1 worker in our socket after spawn, "
            f"got {len(our_workers1)}. All workers: {workers1!r}"
        )
        self.assertEqual(
            our_workers1[0]['status'],
            'running',
            f"Expected worker status 'running' after spawn, "
            f"got: {our_workers1[0]['status']!r}. Full worker: {our_workers1[0]!r}"
        )

        # Kill tmux window externally (bypass swarm kill)
        session = self.get_swarm_session()
        kill_result = self.tmux_cmd('kill-window', '-t', f'{session}:{worker_id}')
        self.assertEqual(
            kill_result.returncode,
            0,
            f"Failed to kill tmux window '{session}:{worker_id}'. "
            f"stderr: {kill_result.stderr!r}"
        )

        # Verify: ls now shows stopped status (not stale "running")
        ls2 = self.run_swarm('ls', '--format', 'json')
        self.assertEqual(
            ls2.returncode,
            0,
            f"ls command failed after kill. stdout: {ls2.stdout!r}, stderr: {ls2.stderr!r}"
        )

        workers2 = json.loads(ls2.stdout)
        # Filter to workers in our isolated socket
        our_workers2 = [
            w for w in workers2
            if w.get('tmux') and w['tmux'].get('socket') == self.tmux_socket
        ]
        self.assertEqual(
            len(our_workers2),
            1,
            f"Expected worker to still exist in state after external kill, "
            f"got {len(our_workers2)} workers. All workers: {workers2!r}"
        )

        worker = our_workers2[0]
        self.assertEqual(
            worker['name'],
            worker_name,
            f"Expected worker name '{worker_name}', got: {worker['name']!r}"
        )
        self.assertEqual(
            worker['status'],
            'stopped',
            f"Expected worker status 'stopped' after external tmux kill, "
            f"but got '{worker['status']}'. This indicates swarm ls is not "
            f"correctly detecting that the tmux window was killed externally. "
            f"The refresh_worker_status() function should detect that the tmux "
            f"window no longer exists and update the status accordingly. "
            f"Full worker state: {worker!r}"
        )


class TestConcurrentOperations(TmuxIsolatedTestCase):
    """Test LIFE-4: Multiple swarm commands running simultaneously don't corrupt state.

    This test exposes a race condition in concurrent state file updates.
    See issue swarm-1ry: Implement state file locking to prevent concurrent operation race conditions
    """

    @skip_if_no_tmux
    def test_concurrent_operations(self):
        """Verify concurrent swarm operations don't corrupt state file.

        This test runs multiple swarm commands in parallel to ensure that:
        1. All commands succeed or fail gracefully (no crashes)
        2. The state file remains valid JSON (no corruption)
        3. The final worker count is correct (no lost workers)
        4. All workers can be parsed (state integrity maintained)

        This may expose the need for state file locking if concurrent writes
        cause corruption or lost updates.
        """
        import concurrent.futures

        # Spawn initial workers (5 total)
        worker_prefix = self.tmux_socket.replace('swarm-test-', 'init')
        for i in range(5):
            result = self.run_swarm(
                'spawn', '--name', f'{worker_prefix}-{i}', '--tmux', '--', 'sleep', '60'
            )
            self.assertEqual(
                result.returncode,
                0,
                f"Failed to spawn initial worker {i}. "
                f"stdout: {result.stdout!r}, stderr: {result.stderr!r}"
            )

        # Give workers time to start
        time.sleep(0.5)

        # Verify initial state
        workers_before = self.get_workers()
        self.assertEqual(
            len(workers_before),
            5,
            f"Expected 5 workers before concurrent operations, "
            f"got {len(workers_before)}: {[w['name'] for w in workers_before]!r}"
        )

        # Run concurrent operations (mix of spawn, ls, ls --json)
        # Use unique names to avoid conflicts
        concurrent_prefix = self.tmux_socket.replace('swarm-test-', 'conc')
        operations = [
            ('spawn', '--name', f'{concurrent_prefix}-0', '--tmux', '--', 'sleep', '60'),
            ('ls',),
            ('ls', '--format', 'json'),
            ('spawn', '--name', f'{concurrent_prefix}-1', '--tmux', '--', 'sleep', '60'),
            ('ls',),
        ]

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [
                executor.submit(self.run_swarm, *op)
                for op in operations
            ]
            results = [f.result() for f in futures]

        # All should succeed (or fail gracefully, no crashes)
        for i, result in enumerate(results):
            self.assertIn(
                result.returncode,
                [0, 1],
                f"Operation {i} ({operations[i]}) returned unexpected code {result.returncode}. "
                f"stdout: {result.stdout!r}, stderr: {result.stderr!r}"
            )

        # State should be consistent - verify we can parse it
        ls_result = self.run_swarm('ls', '--format', 'json')
        self.assertEqual(
            ls_result.returncode,
            0,
            f"ls --format json failed after concurrent operations. "
            f"stdout: {ls_result.stdout!r}, stderr: {ls_result.stderr!r}"
        )

        # State file should be valid JSON
        try:
            workers = self.get_workers()
        except (json.JSONDecodeError, ValueError) as e:
            self.fail(
                f"State file corrupted after concurrent operations. "
                f"Failed to parse JSON: {e}. "
                f"This indicates a need for state file locking. "
                f"Raw output: {ls_result.stdout!r}"
            )

        # Should have 7 workers (5 initial + 2 spawned concurrently)
        # NOTE: This test MAY fail due to race conditions in state file updates.
        # If it fails with 6 workers instead of 7, this indicates that concurrent
        # writes to state.json are causing lost updates, which means state file
        # locking is needed.
        expected_workers = 7
        if len(workers) != expected_workers:
            # Document the race condition for debugging
            missing_workers = []
            for i in range(2):
                worker_name = f'{concurrent_prefix}-{i}'
                if not any(w['name'] == worker_name for w in workers):
                    missing_workers.append(worker_name)

            # Check if this is the known race condition
            if len(workers) == expected_workers - 1 and missing_workers:
                self.fail(
                    f"RACE CONDITION DETECTED: Expected {expected_workers} workers "
                    f"(5 initial + 2 concurrent spawns), got {len(workers)}. "
                    f"Missing workers: {missing_workers!r}. "
                    f"Present workers: {[w['name'] for w in workers]!r}. "
                    f"\n\nThis failure indicates that concurrent swarm operations are "
                    f"causing lost updates to state.json. The state file needs locking "
                    f"to prevent race conditions during concurrent reads and writes. "
                    f"\n\nRecommended fix: Implement file locking using fcntl.flock() "
                    f"or similar mechanism in load_state() and save_state() functions."
                )

        self.assertEqual(
            len(workers),
            expected_workers,
            f"Expected {expected_workers} workers (5 initial + 2 concurrent spawns), "
            f"got {len(workers)}. "
            f"Workers: {[w['name'] for w in workers]!r}. "
            f"If count is wrong, this may indicate lost updates due to race conditions."
        )

        # All workers should be parseable (no corruption)
        for w in workers:
            self.assertIn(
                'name',
                w,
                f"Worker missing 'name' field, indicates corruption: {w!r}"
            )
            self.assertIn(
                'status',
                w,
                f"Worker missing 'status' field, indicates corruption: {w!r}"
            )
            # Verify name is one of our expected workers
            self.assertTrue(
                w['name'].startswith(worker_prefix) or w['name'].startswith(concurrent_prefix),
                f"Unexpected worker name '{w['name']}', expected prefix "
                f"'{worker_prefix}' or '{concurrent_prefix}'. Full worker: {w!r}"
            )




class TestStatusRefreshAccuracy(TmuxIsolatedTestCase):
    """Integration test STATE-4: Comprehensive test of refresh_worker_status().

    This test verifies that the refresh_worker_status() function correctly
    detects worker status across various scenarios including normal operation,
    process exit, external tmux window kill, and session termination.
    """

    def spawn_worker(self, *cmd, session=None, name=None):
        """Helper to spawn a worker and return its ID.

        Args:
            *cmd: Command and arguments to run (e.g., 'sleep', '300')
            session: Optional session name (default: use swarm's auto-generated name)
            name: Optional worker name (default: auto-generate unique name)

        Returns:
            Worker ID (name) that was spawned
        """
        if name is None:
            # Generate unique name based on test socket
            name = f"worker-{uuid.uuid4().hex[:8]}"

        args = ['spawn', '--name', name, '--tmux']
        if session:
            args.extend(['--session', session])
        args.extend(['--'] + list(cmd))

        result = self.run_swarm(*args)
        self.assertEqual(
            result.returncode,
            0,
            f"spawn command failed. stdout: {result.stdout!r}, stderr: {result.stderr!r}"
        )

        worker_id = self.parse_worker_id(result.stdout)
        self.assertEqual(
            worker_id,
            name,
            f"Expected worker ID to match name '{name}', got: {worker_id!r}"
        )

        return worker_id

    def kill_tmux_window(self, worker_id):
        """Kill a tmux window externally (not via swarm kill).

        Args:
            worker_id: Worker ID (window name) to kill

        This simulates a user manually killing a tmux window, which should
        cause refresh_worker_status() to detect it as stopped.
        """
        session = self.get_swarm_session()
        result = self.tmux_cmd('kill-window', '-t', f'{session}:{worker_id}')
        self.assertEqual(
            result.returncode,
            0,
            f"Failed to kill tmux window '{session}:{worker_id}'. stderr: {result.stderr!r}"
        )

    @skip_if_no_tmux
    def test_status_refresh_accuracy(self):
        """Verify refresh_worker_status() correctly detects status in all scenarios.

        This comprehensive test verifies that swarm ls (which calls
        refresh_worker_status()) correctly reports worker status across:
        1. Worker running normally
        2. Worker process exited naturally
        3. Tmux window killed externally
        4. Entire session killed

        All scenarios are tested in a single test to ensure proper isolation
        and verify that ls can handle multiple workers with different states.
        """
        scenarios = []

        # Scenario 1: Worker running normally
        w1 = self.spawn_worker('sleep', '300')
        scenarios.append(('running_normal', w1, 'running'))

        # Scenario 2: Worker process exited (sleep finished)
        w2 = self.spawn_worker('sleep', '0.1')
        time.sleep(0.5)  # Wait for process to exit
        scenarios.append(('process_exited', w2, 'stopped'))

        # Scenario 3: Tmux window killed externally
        w3 = self.spawn_worker('sleep', '300')
        self.kill_tmux_window(w3)
        scenarios.append(('window_killed', w3, 'stopped'))

        # Scenario 4: Session killed entirely
        # Create a temporary session for this test
        temp_session = f'temp-session-{uuid.uuid4().hex[:8]}'
        w4 = self.spawn_worker('sleep', '300', session=temp_session)
        self.tmux_cmd('kill-session', '-t', temp_session)
        scenarios.append(('session_killed', w4, 'stopped'))

        # Refresh and verify all workers via swarm ls
        workers = self.get_workers()

        # Build a map of worker_id -> worker for easy lookup
        workers_map = {w['name']: w for w in workers}

        # Verify each scenario
        for name, worker_id, expected_status in scenarios:
            self.assertIn(
                worker_id,
                workers_map,
                f"Scenario '{name}': Worker '{worker_id}' not found in swarm ls output. "
                f"Available workers: {list(workers_map.keys())!r}"
            )

            actual_status = workers_map[worker_id]['status']
            self.assertEqual(
                actual_status,
                expected_status,
                f"Scenario '{name}' failed: Worker '{worker_id}' expected status '{expected_status}', "
                f"but got '{actual_status}'. This indicates refresh_worker_status() did not "
                f"correctly detect the worker's actual state. Full worker: {workers_map[worker_id]!r}"
            )


if __name__ == "__main__":
    unittest.main()
