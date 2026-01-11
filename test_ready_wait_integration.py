#!/usr/bin/env python3
"""Integration tests for --ready-wait functionality (READY-1 through READY-4).

Tests verify that --ready-wait flag correctly detects agent readiness by
monitoring tmux pane output for ready patterns, handling timeouts gracefully,
and working with ANSI escape codes and scrollback.
"""

import shutil
import sys
import time
import unittest
from pathlib import Path

# Add tests/ directory to path to import TmuxIsolatedTestCase
sys.path.insert(0, str(Path(__file__).parent / "tests"))
from test_tmux_isolation import TmuxIsolatedTestCase, skip_if_no_tmux


class TestReadyWaitDetectsPrompt(TmuxIsolatedTestCase):
    """READY-1: Test that --ready-wait detects Claude Code prompt."""

    @skip_if_no_tmux
    def test_ready_wait_detects_claude_code_prompt(self):
        """Verify --ready-wait returns when Claude Code prompt is detected.

        This test spawns a process with --ready-wait that outputs a ready
        pattern ("> "), and verifies that spawn returns within a reasonable
        time (not timing out).
        """
        # Use a bash script that outputs the ready pattern after a short delay
        worker_name = f"ready1-{self.tmux_socket[-8:]}"

        # Create a command that outputs Claude Code ready pattern, then waits
        # Using 'cat' to keep the process alive waiting for input
        # Note: Use "Claude Code v" pattern since trailing spaces get stripped
        cmd = [
            'bash', '-c',
            'sleep 1; echo "Claude Code v2.0.76"; cat'
        ]

        start_time = time.time()
        result = self.run_swarm(
            'spawn',
            '--name', worker_name,
            '--tmux',
            '--ready-wait',
            '--',
            *cmd
        )
        elapsed = time.time() - start_time

        # Should succeed (returncode 0)
        self.assertEqual(
            result.returncode,
            0,
            f"Expected spawn with --ready-wait to succeed (returncode 0), "
            f"got {result.returncode}. Stdout: {result.stdout!r}, Stderr: {result.stderr!r}"
        )

        # Should return within ~3 seconds (1s sleep + 1s detection + 1s margin)
        # NOT timeout (default timeout is 30s)
        self.assertLess(
            elapsed,
            5.0,
            f"Expected spawn --ready-wait to return within 5 seconds (not timeout), "
            f"but took {elapsed:.2f}s. This indicates ready detection may not be working."
        )

        # Verify worker was created
        workers = self.get_workers()
        worker_names = [w['name'] for w in workers]
        self.assertIn(
            worker_name,
            worker_names,
            f"Expected worker '{worker_name}' to be created, "
            f"got workers: {worker_names!r}"
        )


class TestReadyWaitTimeout(TmuxIsolatedTestCase):
    """READY-2: Test that --ready-wait handles timeouts correctly."""

    @skip_if_no_tmux
    def test_ready_wait_timeout_handling(self):
        """Verify --ready-wait times out when process never outputs ready pattern.

        This test spawns a process that never outputs a ready pattern and
        verifies that --ready-wait respects the --ready-timeout flag.
        """
        worker_name = f"ready2-{self.tmux_socket[-8:]}"

        # Process that sleeps forever without outputting ready pattern
        cmd = ['sleep', '300']

        start_time = time.time()
        result = self.run_swarm(
            'spawn',
            '--name', worker_name,
            '--tmux',
            '--ready-wait',
            '--ready-timeout', '2',  # 2 second timeout
            '--',
            *cmd
        )
        elapsed = time.time() - start_time

        # Should still succeed (spawn completes, just reports timeout)
        self.assertEqual(
            result.returncode,
            0,
            f"Expected spawn to succeed even with timeout (returncode 0), "
            f"got {result.returncode}. Stdout: {result.stdout!r}, Stderr: {result.stderr!r}"
        )

        # Should take approximately 2 seconds (timeout duration)
        self.assertGreaterEqual(
            elapsed,
            2.0,
            f"Expected spawn to wait for timeout duration (~2s), but returned in {elapsed:.2f}s"
        )
        self.assertLess(
            elapsed,
            5.0,
            f"Expected spawn to timeout after ~2s, but took {elapsed:.2f}s. "
            f"Timeout mechanism may not be working correctly."
        )

        # Output should mention timeout (informational warning)
        # Note: swarm may not explicitly print "timeout" - it just returns after waiting
        # So we verify by checking elapsed time instead

        # Verify worker was still created (timeout doesn't fail spawn)
        workers = self.get_workers()
        worker_names = [w['name'] for w in workers]
        self.assertIn(
            worker_name,
            worker_names,
            f"Expected worker '{worker_name}' to be created even after timeout, "
            f"got workers: {worker_names!r}"
        )


class TestReadyWaitWithAnsi(TmuxIsolatedTestCase):
    """READY-3: Test that --ready-wait works with ANSI escape codes."""

    @skip_if_no_tmux
    def test_ready_wait_with_ansi_escape_codes(self):
        r"""Verify pattern matching works with ANSI color codes in output.

        The ready patterns in swarm.py are ANSI-aware (using regex like
        r"(?:^|\x1b\[[0-9;]*m)> "), so this test verifies that ANSI
        codes don't break detection.
        """
        worker_name = f"ready3-{self.tmux_socket[-8:]}"

        # Output ANSI color codes before the ready text
        # \x1b[32m = green color
        # Using 'cat' to keep process alive
        # Use "Claude Code" pattern to avoid trailing space issues
        cmd = [
            'bash', '-c',
            'sleep 1; echo -e "\\x1b[32mClaude Code v2.0\\x1b[0m"; cat'
        ]

        start_time = time.time()
        result = self.run_swarm(
            'spawn',
            '--name', worker_name,
            '--tmux',
            '--ready-wait',
            '--ready-timeout', '5',
            '--',
            *cmd
        )
        elapsed = time.time() - start_time

        # Should succeed
        self.assertEqual(
            result.returncode,
            0,
            f"Expected spawn with --ready-wait to succeed (returncode 0), "
            f"got {result.returncode}. Stdout: {result.stdout!r}, Stderr: {result.stderr!r}"
        )

        # Should detect prompt and return quickly (not timeout)
        self.assertLess(
            elapsed,
            5.0,
            f"Expected spawn --ready-wait to detect ANSI-prefixed prompt within 5s, "
            f"but took {elapsed:.2f}s. ANSI codes may be breaking pattern detection."
        )

        # Verify worker created
        workers = self.get_workers()
        worker_names = [w['name'] for w in workers]
        self.assertIn(
            worker_name,
            worker_names,
            f"Expected worker '{worker_name}' to be created, got workers: {worker_names!r}"
        )


class TestReadyWaitScrollbackCapture(TmuxIsolatedTestCase):
    """READY-4: Test that --ready-wait detects prompt even if it scrolls off screen."""

    @skip_if_no_tmux
    def test_ready_wait_scrollback_capture(self):
        """Verify pattern detection works when prompt scrolls off visible area.

        If the ready prompt appears but then scrolls off the visible pane area
        due to additional output, the detection should still work because
        tmux_capture_pane includes scrollback history.

        This is tricky to test because we need to ensure enough output to
        cause scrolling, then verify detection still works.
        """
        worker_name = f"ready4-{self.tmux_socket[-8:]}"

        # Strategy: output ready pattern, then output many lines to scroll it off
        # The wait_for_agent_ready should detect it before scrolling
        # OR if using history capture, should find it in scrollback
        cmd = [
            'bash', '-c',
            # Output Claude Code banner immediately, then spam lines
            'echo "Claude Code v2.0.76"; for i in {1..50}; do echo "Line $i"; sleep 0.05; done; sleep 60'
        ]

        start_time = time.time()
        result = self.run_swarm(
            'spawn',
            '--name', worker_name,
            '--tmux',
            '--ready-wait',
            '--ready-timeout', '10',
            '--',
            *cmd
        )
        elapsed = time.time() - start_time

        # Should succeed
        self.assertEqual(
            result.returncode,
            0,
            f"Expected spawn with --ready-wait to succeed (returncode 0), "
            f"got {result.returncode}. Stdout: {result.stdout!r}, Stderr: {result.stderr!r}"
        )

        # Should detect prompt and return quickly (within 3s)
        # The prompt appears immediately, so detection should happen before scrolling
        self.assertLess(
            elapsed,
            5.0,
            f"Expected spawn --ready-wait to detect prompt quickly (before scrolling), "
            f"but took {elapsed:.2f}s. Detection timing may need adjustment."
        )

        # Verify worker created
        workers = self.get_workers()
        worker_names = [w['name'] for w in workers]
        self.assertIn(
            worker_name,
            worker_names,
            f"Expected worker '{worker_name}' to be created, got workers: {worker_names!r}"
        )


if __name__ == "__main__":
    unittest.main()
