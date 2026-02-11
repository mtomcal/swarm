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
        result = self._wait_for_ready_with_output(output)
        self.assertTrue(
            result,
            f"Expected Claude Code prompt '> ' to be detected as ready. Output: {output!r}"
        )

    def test_pattern_claude_code_prompt_with_text(self):
        """PATTERN-2: '> some text' is detected."""
        output = "> some text here"
        result = self._wait_for_ready_with_output(output)
        self.assertTrue(
            result,
            f"Expected Claude Code prompt with text '> some text' to be detected. Output: {output!r}"
        )

    def test_pattern_bypass_permissions(self):
        """PATTERN-3: 'bypass permissions' text detected."""
        output = "bypass permissions on"
        result = self._wait_for_ready_with_output(output)
        self.assertTrue(
            result,
            f"Expected 'bypass permissions on' to be detected as ready. Output: {output!r}"
        )

    def test_pattern_bypass_permissions_variants(self):
        """PATTERN-4: Test 'bypass permissions' with different whitespace."""
        # Test with single space separator
        output1 = "bypass permissions on"
        result1 = self._wait_for_ready_with_output(output1)
        self.assertTrue(
            result1,
            f"Expected 'bypass permissions on' (single space) to match. Output: {output1!r}"
        )

        # Test with multiple spaces
        output2 = "bypass   permissions   on"
        result2 = self._wait_for_ready_with_output(output2)
        self.assertTrue(
            result2,
            f"Expected 'bypass   permissions   on' (multiple spaces) to match. Output: {output2!r}"
        )

        # Test with tab separator
        output3 = "bypass\tpermissions\ton"
        result3 = self._wait_for_ready_with_output(output3)
        self.assertTrue(
            result3,
            f"Expected 'bypass\\tpermissions\\ton' (tabs) to match. Output: {output3!r}"
        )

        # Test with mixed whitespace
        output4 = "bypass \t permissions  \t on"
        result4 = self._wait_for_ready_with_output(output4)
        self.assertTrue(
            result4,
            f"Expected mixed whitespace variant to match. Output: {output4!r}"
        )

        # Test that dot separator does NOT match (not whitespace)
        output5 = "bypass.permissions on"
        result5 = self._wait_for_ready_with_output(output5, timeout=1)
        self.assertFalse(
            result5,
            f"Expected 'bypass.permissions on' (dot separator) to NOT match - dot is not whitespace. Output: {output5!r}"
        )

    def test_pattern_claude_code_banner(self):
        """PATTERN-5: 'Claude Code' banner detected."""
        output = "Claude Code v2.0.76"
        result = self._wait_for_ready_with_output(output)
        self.assertTrue(
            result,
            f"Expected 'Claude Code v2.0.76' banner to be detected. Output: {output!r}"
        )

    def test_pattern_shell_prompt(self):
        """PATTERN-6: '$ ' at line start detected."""
        output = "$ "
        result = self._wait_for_ready_with_output(output)
        self.assertTrue(
            result,
            f"Expected shell prompt '$ ' to be detected as ready. Output: {output!r}"
        )

    def test_pattern_python_repl(self):
        """PATTERN-7: '>>> ' at line start detected."""
        output = ">>> "
        result = self._wait_for_ready_with_output(output)
        self.assertTrue(
            result,
            f"Expected Python REPL prompt '>>> ' to be detected as ready. Output: {output!r}"
        )

    def test_pattern_no_false_positives(self):
        """PATTERN-8: 'echo > file' should NOT match '^> '."""
        # Mid-line > should not match
        output1 = "echo > file.txt"
        result1 = self._wait_for_ready_with_output(output1, timeout=1)
        self.assertFalse(
            result1,
            f"Expected mid-line '>' in redirect to NOT match prompt pattern. Output: {output1!r}"
        )

        # Redirect operators should not match
        output2 = "cat file.txt >> output.log"
        result2 = self._wait_for_ready_with_output(output2, timeout=1)
        self.assertFalse(
            result2,
            f"Expected '>>' redirect operator to NOT match prompt pattern. Output: {output2!r}"
        )

        # Dollar sign in middle of line should not match
        output3 = "price is $100"
        result3 = self._wait_for_ready_with_output(output3, timeout=1)
        self.assertFalse(
            result3,
            f"Expected mid-line '$' in 'price is $100' to NOT match shell prompt. Output: {output3!r}"
        )

    def test_pattern_multiple_patterns_first_wins(self):
        """PATTERN-9: Multiple patterns, first match returns True."""
        # Output contains both shell prompt and python REPL pattern
        output = """$ echo test
>>> print('hello')
> """
        result = self._wait_for_ready_with_output(output)
        self.assertTrue(
            result,
            f"Expected at least one pattern to match in multi-pattern output. Output: {output!r}"
        )

    def test_pattern_empty_output(self):
        """PATTERN-10: Empty string handled gracefully."""
        output = ""
        result = self._wait_for_ready_with_output(output, timeout=1)
        self.assertFalse(
            result,
            f"Expected empty output to NOT match any pattern (should timeout). Output: {output!r}"
        )

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
        result = self._wait_for_ready_with_output(output)
        self.assertTrue(
            result,
            f"Expected actual Claude Code v2.0.76 startup screen to be detected. "
            f"Should match banner, prompt '> ', or 'bypass permissions on'. Output length: {len(output)} chars"
        )

    def test_pattern_bypass_with_unicode_prefix(self):
        """PATTERN-12: '⏵⏵ bypass permissions on' detected."""
        output = "⏵⏵ bypass permissions on (shift+tab to cycle)"
        result = self._wait_for_ready_with_output(output)
        self.assertTrue(
            result,
            f"Expected '⏵⏵ bypass permissions on' with Unicode prefix to be detected. Output: {output!r}"
        )

    def test_pattern_prompt_with_hint_text(self):
        """PATTERN-13: '> Try "refactor..."' format detected."""
        output = '> Try "refactor <filepath>"'
        result = self._wait_for_ready_with_output(output)
        self.assertTrue(
            result,
            f"Expected prompt with hint text '> Try \"refactor...\"' to be detected. Output: {output!r}"
        )

    def test_pattern_with_ansi_before_prompt(self):
        """Additional test: ANSI codes before prompt detected."""
        # ANSI color codes before >
        output1 = "\x1b[32m> \x1b[0m"
        result1 = self._wait_for_ready_with_output(output1)
        self.assertTrue(
            result1,
            f"Expected ANSI green color code before '> ' to be detected. Output: {output1!r}"
        )

        # ANSI codes before $
        output2 = "\x1b[1;34m$ \x1b[0m"
        result2 = self._wait_for_ready_with_output(output2)
        self.assertTrue(
            result2,
            f"Expected ANSI bold blue before '$ ' to be detected. Output: {output2!r}"
        )

        # ANSI codes before >>>
        output3 = "\x1b[0m>>> "
        result3 = self._wait_for_ready_with_output(output3)
        self.assertTrue(
            result3,
            f"Expected ANSI reset before '>>> ' to be detected. Output: {output3!r}"
        )

    def test_pattern_multiline_output(self):
        """Additional test: Pattern found on line N of multi-line output."""
        output = """Starting agent...
Loading configuration...
Initializing...
> Ready for input
"""
        result = self._wait_for_ready_with_output(output)
        self.assertTrue(
            result,
            f"Expected '> ' on line 4 of multi-line output to be detected. Output: {output!r}"
        )

    def test_pattern_with_leading_whitespace(self):
        """Additional test: '> ' with leading whitespace should NOT match '^> '."""
        # Leading spaces before > should not match
        output1 = "   > prompt"
        result1 = self._wait_for_ready_with_output(output1, timeout=1)
        self.assertFalse(
            result1,
            f"Expected '> ' with leading spaces to NOT match (not at line start). Output: {output1!r}"
        )

        # Tab before > should not match
        output2 = "\t> prompt"
        result2 = self._wait_for_ready_with_output(output2, timeout=1)
        self.assertFalse(
            result2,
            f"Expected '> ' with leading tab to NOT match (not at line start). Output: {output2!r}"
        )


    # =========================================================================
    # OpenCode Ready Pattern Tests
    # =========================================================================

    def test_pattern_opencode_version_banner(self):
        """OPENCODE-1: OpenCode version banner detected."""
        output = "opencode v1.0.115"
        result = self._wait_for_ready_with_output(output)
        self.assertTrue(
            result,
            f"Expected 'opencode v1.0.115' banner to be detected. Output: {output!r}"
        )

    def test_pattern_opencode_version_banner_variants(self):
        """OPENCODE-2: OpenCode version banner with different versions detected."""
        # Single digit version
        output1 = "opencode v1"
        result1 = self._wait_for_ready_with_output(output1)
        self.assertTrue(
            result1,
            f"Expected 'opencode v1' (single digit) to be detected. Output: {output1!r}"
        )

        # Multi-digit version
        output2 = "opencode v2.5.123"
        result2 = self._wait_for_ready_with_output(output2)
        self.assertTrue(
            result2,
            f"Expected 'opencode v2.5.123' to be detected. Output: {output2!r}"
        )

    def test_pattern_opencode_tab_switch_agent(self):
        """OPENCODE-3: OpenCode 'tab switch agent' UI hint detected."""
        output = "tab switch agent"
        result = self._wait_for_ready_with_output(output)
        self.assertTrue(
            result,
            f"Expected 'tab switch agent' UI hint to be detected. Output: {output!r}"
        )

    def test_pattern_opencode_ctrl_p_commands(self):
        """OPENCODE-4: OpenCode 'ctrl+p commands' UI hint detected."""
        output = "ctrl+p commands"
        result = self._wait_for_ready_with_output(output)
        self.assertTrue(
            result,
            f"Expected 'ctrl+p commands' UI hint to be detected. Output: {output!r}"
        )

    def test_pattern_opencode_actual_startup_screen(self):
        """OPENCODE-5: Actual OpenCode startup screen detected."""
        # Based on the issue screenshot description
        output = """
 ████████████████████████████████
        opencode
 ████████████████████████████████

Build Google Gemini Flash Latest
tab switch agent                ctrl+p commands
opencode v1.0.115
"""
        result = self._wait_for_ready_with_output(output)
        self.assertTrue(
            result,
            f"Expected actual OpenCode startup screen to be detected. "
            f"Should match version banner or UI hints. Output length: {len(output)} chars"
        )



    def test_pattern_opencode_no_false_positives(self):
        """OPENCODE-6: OpenCode patterns should not match unrelated text."""
        # 'tab' alone should not match
        output1 = "press tab to continue"
        result1 = self._wait_for_ready_with_output(output1, timeout=1)
        self.assertFalse(
            result1,
            f"Expected 'press tab to continue' to NOT match opencode patterns. Output: {output1!r}"
        )

        # 'opencode' without version should not match
        output2 = "opencode is running"
        result2 = self._wait_for_ready_with_output(output2, timeout=1)
        self.assertFalse(
            result2,
            f"Expected 'opencode is running' without version to NOT match. Output: {output2!r}"
        )

        # Version strings in installation/error messages should NOT match (false positives)
        # These were problematic with the broad r"v\d+\.\d+\.\d+" pattern
        output3 = "Installing package v2.3.4..."
        result3 = self._wait_for_ready_with_output(output3, timeout=1)
        self.assertFalse(
            result3,
            f"Expected 'Installing package v2.3.4...' to NOT match (version in install message). Output: {output3!r}"
        )

        output4 = "Downloading node v18.0.0"
        result4 = self._wait_for_ready_with_output(output4, timeout=1)
        self.assertFalse(
            result4,
            f"Expected 'Downloading node v18.0.0' to NOT match (version in download message). Output: {output4!r}"
        )

        output5 = "Python v3.11.0 is required"
        result5 = self._wait_for_ready_with_output(output5, timeout=1)
        self.assertFalse(
            result5,
            f"Expected 'Python v3.11.0 is required' to NOT match (version in requirement message). Output: {output5!r}"
        )

        output6 = "Error in v1.2.3: something failed"
        result6 = self._wait_for_ready_with_output(output6, timeout=1)
        self.assertFalse(
            result6,
            f"Expected 'Error in v1.2.3: something failed' to NOT match (version in error message). Output: {output6!r}"
        )


    # =========================================================================
    # Theme Picker Not-Ready Pattern Tests
    # =========================================================================

    def test_theme_picker_choose_text_style_not_ready(self):
        """THEME-1: 'Choose the text style' does NOT trigger ready detection."""
        output = "Choose the text style that looks best with your terminal"
        result = self._wait_for_ready_with_output(output, timeout=1)
        self.assertFalse(
            result,
            f"Expected theme picker 'Choose the text style' to NOT be detected as ready. Output: {output!r}"
        )

    def test_theme_picker_looks_best_not_ready(self):
        """THEME-2: 'looks best with your terminal' does NOT trigger ready detection."""
        output = "looks best with your terminal"
        result = self._wait_for_ready_with_output(output, timeout=1)
        self.assertFalse(
            result,
            f"Expected theme picker 'looks best with your terminal' to NOT be detected as ready. Output: {output!r}"
        )

    def test_theme_picker_full_screen_not_ready(self):
        """THEME-3: Full theme picker screen does NOT trigger ready detection."""
        output = """
Choose the text style that looks best with your terminal

  ○ Light
  ● Dark
  ○ Light High Contrast
  ○ Dark High Contrast
"""
        result = self._wait_for_ready_with_output(output, timeout=1)
        self.assertFalse(
            result,
            f"Expected full theme picker screen to NOT be detected as ready. Output length: {len(output)} chars"
        )

    def test_theme_picker_with_prompt_pattern_not_ready(self):
        """THEME-4: Theme picker with '> ' in output still NOT ready (not-ready takes priority)."""
        # This tests that not-ready patterns are checked before ready patterns.
        # The '>' might appear in the theme picker UI but should not trigger ready.
        output = """Choose the text style that looks best with your terminal
> Dark
  Light"""
        result = self._wait_for_ready_with_output(output, timeout=1)
        self.assertFalse(
            result,
            f"Expected theme picker with '> ' marker to NOT be detected as ready "
            f"(not-ready patterns take priority). Output: {output!r}"
        )

    def test_theme_picker_sends_enter_to_dismiss(self):
        """THEME-5: Theme picker detection sends Enter to dismiss via tmux."""
        with patch('swarm.tmux_capture_pane', return_value="Choose the text style that looks best"), \
             patch('swarm.subprocess.run') as mock_run, \
             patch('swarm.tmux_cmd_prefix', return_value=["tmux"]):
            mock_run.return_value = MagicMock(returncode=0)
            # Will timeout, but we want to verify Enter was sent
            swarm.wait_for_agent_ready(
                session="test-session",
                window="test-window",
                timeout=1,
                socket=None
            )
            # Verify send-keys Enter was called at least once
            enter_calls = [
                call for call in mock_run.call_args_list
                if call[0] and "send-keys" in call[0][0] and "Enter" in call[0][0]
            ]
            self.assertGreater(
                len(enter_calls), 0,
                "Expected tmux send-keys Enter to be called to dismiss theme picker"
            )

    def test_theme_picker_then_ready_pattern_succeeds(self):
        """THEME-6: Theme picker followed by real ready pattern eventually returns True."""
        # First call returns theme picker, second call returns ready pattern
        call_count = [0]
        def mock_capture(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] <= 2:
                return "Choose the text style that looks best with your terminal"
            return "bypass permissions on"

        with patch('swarm.tmux_capture_pane', side_effect=mock_capture), \
             patch('swarm.subprocess.run') as mock_run, \
             patch('swarm.tmux_cmd_prefix', return_value=["tmux"]):
            mock_run.return_value = MagicMock(returncode=0)
            result = swarm.wait_for_agent_ready(
                session="test-session",
                window="test-window",
                timeout=10,
                socket=None
            )
            self.assertTrue(
                result,
                "Expected ready detection to succeed after theme picker is dismissed "
                "and real ready pattern appears"
            )


if __name__ == "__main__":
    unittest.main()
