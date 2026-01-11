#!/usr/bin/env python3
"""Tests for SWARM_INSTRUCTIONS constant template.

Tests that the SWARM_INSTRUCTIONS constant:
- Contains the marker string 'Process Management (swarm)' for idempotent detection
- Is under 50 lines (per AGENTS.md best practices)
- Documents essential commands (spawn, ls, status, send, logs, kill, attach)
- Includes worktree isolation example
- Has power user tips (--ready-wait, --tag, --env)
"""

import unittest

from swarm import SWARM_INSTRUCTIONS


class TestSwarmInstructionsContent(unittest.TestCase):
    """Tests for SWARM_INSTRUCTIONS content requirements."""

    def test_marker_string_present(self):
        """SWARM_INSTRUCTIONS contains marker string for idempotent detection."""
        self.assertIn("Process Management (swarm)", SWARM_INSTRUCTIONS)

    def test_line_count_under_50(self):
        """SWARM_INSTRUCTIONS is under 50 lines (per AGENTS.md best practices)."""
        line_count = len(SWARM_INSTRUCTIONS.split('\n'))
        self.assertLess(line_count, 50,
                       f"SWARM_INSTRUCTIONS has {line_count} lines, expected < 50")

    def test_essential_commands_documented(self):
        """All essential swarm commands are documented."""
        essential_commands = [
            "swarm spawn",
            "swarm ls",
            "swarm status",
            "swarm send",
            "swarm logs",
            "swarm kill",
            "swarm attach",
        ]
        for cmd in essential_commands:
            with self.subTest(command=cmd):
                self.assertIn(cmd, SWARM_INSTRUCTIONS,
                             f"Essential command '{cmd}' not documented")

    def test_worktree_isolation_example(self):
        """SWARM_INSTRUCTIONS includes worktree isolation example."""
        # Check for --worktree flag and worktree concept
        self.assertIn("--worktree", SWARM_INSTRUCTIONS)
        # Check for worktree path pattern explanation
        self.assertIn("worktree", SWARM_INSTRUCTIONS.lower())
        # Check for branch creation mention
        self.assertIn("branch", SWARM_INSTRUCTIONS.lower())

    def test_power_user_tips_present(self):
        """Power user tips are documented (--ready-wait, --tag, --env)."""
        power_flags = [
            "--ready-wait",
            "--tag",
            "--env",
        ]
        for flag in power_flags:
            with self.subTest(flag=flag):
                self.assertIn(flag, SWARM_INSTRUCTIONS,
                             f"Power user flag '{flag}' not documented")

    def test_tmux_flag_documented(self):
        """The --tmux flag is documented for interactive mode."""
        self.assertIn("--tmux", SWARM_INSTRUCTIONS)

    def test_state_location_documented(self):
        """State file location is documented."""
        self.assertIn("~/.swarm", SWARM_INSTRUCTIONS)

    def test_rm_worktree_flag_documented(self):
        """The --rm-worktree cleanup flag is documented."""
        self.assertIn("--rm-worktree", SWARM_INSTRUCTIONS)

    def test_send_all_documented(self):
        """The send --all broadcast feature is documented."""
        self.assertIn("--all", SWARM_INSTRUCTIONS)

    def test_wait_all_documented(self):
        """The wait --all feature is documented."""
        self.assertIn("swarm wait", SWARM_INSTRUCTIONS)


class TestSwarmInstructionsFormat(unittest.TestCase):
    """Tests for SWARM_INSTRUCTIONS formatting requirements."""

    def test_is_non_empty_string(self):
        """SWARM_INSTRUCTIONS is a non-empty string."""
        self.assertIsInstance(SWARM_INSTRUCTIONS, str)
        self.assertTrue(len(SWARM_INSTRUCTIONS) > 0)

    def test_no_leading_trailing_whitespace(self):
        """SWARM_INSTRUCTIONS has no leading/trailing whitespace."""
        self.assertEqual(SWARM_INSTRUCTIONS, SWARM_INSTRUCTIONS.strip())

    def test_starts_with_header(self):
        """SWARM_INSTRUCTIONS starts with markdown header."""
        self.assertTrue(SWARM_INSTRUCTIONS.startswith("##"))

    def test_contains_code_blocks(self):
        """SWARM_INSTRUCTIONS contains code blocks for examples."""
        self.assertIn("```bash", SWARM_INSTRUCTIONS)
        self.assertIn("```", SWARM_INSTRUCTIONS)

    def test_readable_by_ai_and_humans(self):
        """SWARM_INSTRUCTIONS is readable (has descriptive text, not just commands)."""
        # Should have some prose explanation, not just code
        # Check for at least a few description words
        self.assertIn("manages", SWARM_INSTRUCTIONS.lower())
        self.assertIn("workers", SWARM_INSTRUCTIONS.lower())


class TestSwarmInstructionsIdempotency(unittest.TestCase):
    """Tests for idempotent detection via marker string."""

    def test_marker_at_section_header(self):
        """Marker appears in section header for easy detection."""
        # The marker should be findable at the start of a section
        lines = SWARM_INSTRUCTIONS.split('\n')
        marker_in_header = any(
            "Process Management (swarm)" in line and line.startswith("#")
            for line in lines
        )
        self.assertTrue(marker_in_header,
                       "Marker 'Process Management (swarm)' should be in a header line")

    def test_unique_marker_string(self):
        """Marker string is unique enough to avoid false positives."""
        # The full marker should only appear once
        count = SWARM_INSTRUCTIONS.count("Process Management (swarm)")
        self.assertEqual(count, 1,
                        f"Marker should appear exactly once, found {count} times")


if __name__ == '__main__':
    unittest.main()
