#!/usr/bin/env python3
"""Unit tests for ready pattern detection in swarm.py.

Tests all 13 pattern detection scenarios from research/2026-01-11-integration-test-topics.md
These are pure unit tests that mock tmux_capture_pane to verify pattern matching.
"""

import unittest
from unittest.mock import patch, MagicMock

import swarm


class TestReadyPatterns(unittest.TestCase):
    """Test ready pattern detection covering PATTERN-1 through PATTERN-13."""

    def _wait_for_ready_with_output(self, output: str, timeout: int = 30) -> bool:
        """Helper to test wait_for_agent_ready with mocked output.

        Args:
            output: The output string to return from tmux_capture_pane
            timeout: Timeout value for wait_for_agent_ready

        Returns:
            True if pattern detected, False otherwise
        """
        with patch('swarm.tmux_capture_pane', return_value=output):
            result = swarm.wait_for_agent_ready(
                session="test-session",
                window="test-window",
                timeout=timeout,
                socket=None
            )
            return result

    def test_pattern_claude_code_prompt_basic(self):
        """PATTERN-1: Output '> ' at line start detected."""
        output = "> "
        self.assertTrue(self._wait_for_ready_with_output(output))

    def test_pattern_claude_code_prompt_with_text(self):
        """PATTERN-2: '> some text' is detected."""
        output = "> some text here"
        self.assertTrue(self._wait_for_ready_with_output(output))

    def test_pattern_bypass_permissions(self):
        """PATTERN-3: 'bypass permissions' text detected."""
        output = "bypass permissions on"
        self.assertTrue(self._wait_for_ready_with_output(output))

    def test_pattern_bypass_permissions_variants(self):
        """PATTERN-4: Test 'bypass permissions' with different whitespace."""
        # Test with single space separator
        output1 = "bypass permissions on"
        self.assertTrue(self._wait_for_ready_with_output(output1))

        # Test with multiple spaces
        output2 = "bypass   permissions   on"
        self.assertTrue(self._wait_for_ready_with_output(output2))

        # Test with tab separator
        output3 = "bypass\tpermissions\ton"
        self.assertTrue(self._wait_for_ready_with_output(output3))

        # Test with mixed whitespace
        output4 = "bypass \t permissions  \t on"
        self.assertTrue(self._wait_for_ready_with_output(output4))

        # Test that dot separator does NOT match (not whitespace)
        output5 = "bypass.permissions on"
        self.assertFalse(self._wait_for_ready_with_output(output5, timeout=1))

    def test_pattern_claude_code_banner(self):
        """PATTERN-5: 'Claude Code' banner detected."""
        output = "Claude Code v2.0.76"
        self.assertTrue(self._wait_for_ready_with_output(output))

    def test_pattern_shell_prompt(self):
        """PATTERN-6: '$ ' at line start detected."""
        output = "$ "
        self.assertTrue(self._wait_for_ready_with_output(output))

    def test_pattern_python_repl(self):
        """PATTERN-7: '>>> ' at line start detected."""
        output = ">>> "
        self.assertTrue(self._wait_for_ready_with_output(output))

    def test_pattern_no_false_positives(self):
        """PATTERN-8: 'echo > file' should NOT match '^> '."""
        # Mid-line > should not match
        output = "echo > file.txt"
        self.assertFalse(self._wait_for_ready_with_output(output, timeout=1))

        # Redirect operators should not match
        output2 = "cat file.txt >> output.log"
        self.assertFalse(self._wait_for_ready_with_output(output2, timeout=1))

        # Dollar sign in middle of line should not match
        output3 = "price is $100"
        self.assertFalse(self._wait_for_ready_with_output(output3, timeout=1))

    def test_pattern_multiple_patterns_first_wins(self):
        """PATTERN-9: Multiple patterns, first match returns True."""
        # Output contains both shell prompt and python REPL pattern
        output = """$ echo test
>>> print('hello')
> """
        self.assertTrue(self._wait_for_ready_with_output(output))

    def test_pattern_empty_output(self):
        """PATTERN-10: Empty string handled gracefully."""
        output = ""
        # Should return False after timeout
        self.assertFalse(self._wait_for_ready_with_output(output, timeout=1))

    def test_pattern_claude_code_actual_startup(self):
        """PATTERN-11: Actual Claude Code v2.0.76 startup screen detected."""
        # Real startup output from research doc
        output = """
 * ▐▛███▜▌ *   Claude Code v2.0.76
* ▝▜█████▛▘ *  Opus 4.5 · Claude Max
 *  ▘▘ ▝▝  *   ~/code/swarm

──────────────────────────────────────────────────────────────
> Try "refactor <filepath>"
──────────────────────────────────────────────────────────────
  [Opus 4.5] v2.0.76 ⎇ main ● ⏱ 1s
  ⏵⏵ bypass permissions on (shift+tab to cycle)
"""
        self.assertTrue(self._wait_for_ready_with_output(output))

    def test_pattern_bypass_with_unicode_prefix(self):
        """PATTERN-12: '⏵⏵ bypass permissions on' detected."""
        output = "⏵⏵ bypass permissions on (shift+tab to cycle)"
        self.assertTrue(self._wait_for_ready_with_output(output))

    def test_pattern_prompt_with_hint_text(self):
        """PATTERN-13: '> Try "refactor..."' format detected."""
        output = '> Try "refactor <filepath>"'
        self.assertTrue(self._wait_for_ready_with_output(output))

    def test_pattern_with_ansi_before_prompt(self):
        """Additional test: ANSI codes before prompt detected."""
        # ANSI color codes before >
        output = "\x1b[32m> \x1b[0m"
        self.assertTrue(self._wait_for_ready_with_output(output))

        # ANSI codes before $
        output2 = "\x1b[1;34m$ \x1b[0m"
        self.assertTrue(self._wait_for_ready_with_output(output2))

        # ANSI codes before >>>
        output3 = "\x1b[0m>>> "
        self.assertTrue(self._wait_for_ready_with_output(output3))

    def test_pattern_multiline_output(self):
        """Additional test: Pattern found on line N of multi-line output."""
        output = """Starting agent...
Loading configuration...
Initializing...
> Ready for input
"""
        self.assertTrue(self._wait_for_ready_with_output(output))

    def test_pattern_with_leading_whitespace(self):
        """Additional test: '> ' with leading whitespace should NOT match '^> '."""
        # Leading spaces before > should not match
        output = "   > prompt"
        self.assertFalse(self._wait_for_ready_with_output(output, timeout=1))

        # Tab before > should not match
        output2 = "\t> prompt"
        self.assertFalse(self._wait_for_ready_with_output(output2, timeout=1))


if __name__ == "__main__":
    unittest.main()
