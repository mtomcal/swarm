#!/usr/bin/env python3
"""Unit tests for pattern edge cases in ready detection.

These tests verify that the ready pattern matching in wait_for_agent_ready()
correctly handles edge cases including:
- Whitespace handling
- ANSI escape codes
- Multiline output
- Carriage returns
- Unicode characters
- Long lines
- Rapid output timing

Test IDs correspond to EDGE-1 through EDGE-7 in research/2026-01-11-integration-test-topics.md
"""

import re
import unittest


class TestPatternEdgeCases(unittest.TestCase):
    """Test pattern edge cases for ready detection.

    These tests verify the regex patterns used in wait_for_agent_ready()
    handle various terminal quirks and edge cases correctly.
    """

    def setUp(self):
        """Set up test fixtures."""
        # Patterns from swarm.py:334-340
        self.ready_patterns = [
            r"(?:^|\x1b\[[0-9;]*m)> ",       # Claude Code prompt (ANSI-aware)
            r"bypass\s+permissions\s+on",    # Explicit text
            r"Claude Code v\d+\.\d+",        # Versioned banner (more specific)
            r"(?:^|\x1b\[[0-9;]*m)\$ ",      # Shell prompt (ANSI-aware)
            r"(?:^|\x1b\[[0-9;]*m)>>> ",     # Python REPL (ANSI-aware)
        ]

    def _check_pattern(self, text: str) -> bool:
        """Check if any ready pattern matches in the text.

        This mimics the logic in wait_for_agent_ready() at swarm.py:346-350.

        Args:
            text: Text to check for ready patterns

        Returns:
            True if any pattern matches, False otherwise
        """
        for line in text.split('\n'):
            for pattern in self.ready_patterns:
                if re.search(pattern, line):
                    return True
        return False

    def test_pattern_with_leading_whitespace(self):
        """EDGE-1: Verify ^> pattern doesn't match if there's leading whitespace.

        The ^> pattern should only match prompts at the start of a line.
        Leading whitespace means it's not actually a prompt.
        """
        # Leading spaces should NOT match
        self.assertFalse(self._check_pattern("  > "))
        self.assertFalse(self._check_pattern("   > some text"))
        self.assertFalse(self._check_pattern("\t> "))

        # But actual prompt at line start SHOULD match
        self.assertTrue(self._check_pattern("> "))
        self.assertTrue(self._check_pattern("> Try something"))

    def test_pattern_with_ansi_before_prompt(self):
        r"""EDGE-2: Verify ANSI codes before prompt are handled correctly.

        Terminal color codes often appear before prompts. The ANSI-aware
        pattern (?:^|\x1b\[[0-9;]*m)> should match these.

        This is marked P1 critical in the research document.
        """
        # ANSI color codes before prompt should match
        self.assertTrue(self._check_pattern("\x1b[32m> "))  # Green
        self.assertTrue(self._check_pattern("\x1b[0m> "))   # Reset
        self.assertTrue(self._check_pattern("\x1b[1;34m> "))  # Bold blue
        self.assertTrue(self._check_pattern("\x1b[0m\x1b[1;34m> "))  # Multiple codes

        # ANSI codes for shell prompt
        self.assertTrue(self._check_pattern("\x1b[32m$ "))

        # ANSI codes for Python REPL
        self.assertTrue(self._check_pattern("\x1b[32m>>> "))

        # Plain prompts should still work
        self.assertTrue(self._check_pattern("> "))
        self.assertTrue(self._check_pattern("$ "))
        self.assertTrue(self._check_pattern(">>> "))

    def test_pattern_multiline_output(self):
        """EDGE-3: Verify pattern found on line N of multi-line output is detected.

        The ready pattern might not appear on the first line. We need to
        check all lines in the output.
        """
        # Pattern on first line
        multiline1 = "> \nSome other text\nMore text"
        self.assertTrue(self._check_pattern(multiline1))

        # Pattern on middle line
        multiline2 = "Loading...\n> Try something\nStatus line"
        self.assertTrue(self._check_pattern(multiline2))

        # Pattern on last line
        multiline3 = "Banner text\nVersion info\n> "
        self.assertTrue(self._check_pattern(multiline3))

        # Actual Claude Code startup sequence
        claude_startup = """
 * ▐▛███▜▌ *   Claude Code v2.0.76
* ▝▜█████▛▘ *  Opus 4.5 · Claude Max
 *  ▘▘ ▝▝  *   ~/code/swarm

──────────────────────────────────────────────────────────────
> Try "refactor <filepath>"
──────────────────────────────────────────────────────────────
  [Opus 4.5] v2.0.76 ⎇ main ● ⏱ 1s
  ⏵⏵ bypass permissions on (shift+tab to cycle)
"""
        self.assertTrue(self._check_pattern(claude_startup))

    def test_pattern_carriage_return_handling(self):
        """EDGE-4: Verify lines with \r (carriage return) are handled correctly.

        Terminals use \r to overwrite lines (e.g., progress indicators).
        Our pattern matching doesn't simulate terminal \r behavior, but we test
        that patterns can still be found when \r is present in the output.
        """
        # Simple carriage return - terminal overwrites "Loading..." with "Done!"
        output1 = "Loading...\rDone!\n> "
        self.assertTrue(self._check_pattern(output1))

        # Progress bar that gets overwritten, prompt on new line
        output2 = "Progress: 10%\rProgress: 50%\rProgress: 100%\n$ "
        self.assertTrue(self._check_pattern(output2))

        # Carriage return in middle of output
        output3 = "Starting...\rReady\n> Try something"
        self.assertTrue(self._check_pattern(output3))

        # Pattern appears after carriage return on same line
        # Note: In actual terminal, \r moves cursor to line start, but our
        # pattern matching just treats \r as a character in the string
        output4 = "Loading\r> "
        # This won't match because > is not at line start in the string
        # This is acceptable - in real tmux capture, the line would be rendered
        self.assertFalse(self._check_pattern(output4))

    def test_pattern_unicode_in_output(self):
        """EDGE-5: Verify non-ASCII characters don't break pattern matching.

        Claude Code uses Unicode symbols (⏵⏵) and other non-ASCII characters.
        Pattern matching should handle these gracefully.
        """
        # Unicode triangle symbols from Claude Code
        self.assertTrue(self._check_pattern("⏵⏵ bypass permissions on"))

        # Unicode with prompt
        self.assertTrue(self._check_pattern("✓ Ready\n> "))

        # Emoji in output
        self.assertTrue(self._check_pattern("🚀 Starting...\n> Try something"))

        # Chinese characters
        self.assertTrue(self._check_pattern("启动中...\n> "))

        # Mixed Unicode and ANSI
        self.assertTrue(self._check_pattern("\x1b[32m⏵⏵ bypass permissions on\x1b[0m"))

    def test_pattern_very_long_lines(self):
        """EDGE-6: Verify wrapped lines (exceeding terminal width) are handled.

        Very long lines might be wrapped by the terminal, but our pattern
        matching works on logical lines, so this should still work.
        """
        # Very long line before prompt
        long_line = "x" * 500 + "\n> "
        self.assertTrue(self._check_pattern(long_line))

        # Prompt at start of very long line
        long_prompt_line = "> " + "x" * 500
        self.assertTrue(self._check_pattern(long_prompt_line))

        # Very long output with pattern in middle
        long_output = "Start\n" + "x" * 1000 + "\n> Try something\n" + "y" * 1000
        self.assertTrue(self._check_pattern(long_output))

    def test_pattern_rapid_output_capture(self):
        """EDGE-7: Verify pattern timing edge case - pattern appears then scrolls.

        This is a unit test, so we can't truly test timing. Instead, we verify
        that if the pattern appears anywhere in the captured output, it's detected.

        The actual timing test would be an integration test with real tmux.
        """
        # Pattern appears early, then lots of output
        rapid1 = "> Ready\n" + "\n".join([f"Line {i}" for i in range(100)])
        self.assertTrue(self._check_pattern(rapid1))

        # Pattern appears late
        rapid2 = "\n".join([f"Line {i}" for i in range(100)]) + "\n> "
        self.assertTrue(self._check_pattern(rapid2))

        # Pattern appears, then scrolls, but we capture history
        # (In real integration test, this would use tmux capture-pane with -S)
        rapid3 = "\n".join([f"Output {i}" for i in range(50)]) + "\n> \n" + "\n".join([f"More {i}" for i in range(50)])
        self.assertTrue(self._check_pattern(rapid3))

    def test_pattern_bypass_permissions_variants(self):
        """Additional test: Verify bypass permissions text variations.

        The research doc notes that the actual text is "bypass permissions on"
        with spaces, not "bypass.permissions" with a dot.
        """
        # Current actual Claude Code text
        self.assertTrue(self._check_pattern("⏵⏵ bypass permissions on (shift+tab to cycle)"))

        # Just the core text
        self.assertTrue(self._check_pattern("bypass permissions on"))

        # With ANSI codes
        self.assertTrue(self._check_pattern("\x1b[32mbypass permissions on\x1b[0m"))

    def test_pattern_claude_code_banner(self):
        """Additional test: Verify Claude Code banner detection.

        The pattern should match the versioned banner format.
        """
        # Standard banner
        self.assertTrue(self._check_pattern("Claude Code v2.0.76"))

        # Different versions
        self.assertTrue(self._check_pattern("Claude Code v1.0.0"))
        self.assertTrue(self._check_pattern("Claude Code v3.14.159"))

        # With surrounding text
        self.assertTrue(self._check_pattern(" * ▐▛███▜▌ *   Claude Code v2.0.76"))

        # Should NOT match non-versioned text
        self.assertFalse(self._check_pattern("Claude Code"))
        self.assertFalse(self._check_pattern("Welcome to Claude Code"))

    def test_pattern_no_false_positives(self):
        """Additional test: Verify patterns don't match incorrectly.

        Mid-line > characters should not match the ^> pattern.
        """
        # Redirect operators should NOT match
        self.assertFalse(self._check_pattern("echo hello > file.txt"))
        self.assertFalse(self._check_pattern("cat file1 > file2"))

        # Comparison operators should NOT match
        self.assertFalse(self._check_pattern("if x > 5:"))

        # Dollar sign mid-line should NOT match
        self.assertFalse(self._check_pattern("Price: $100"))

        # Python prompt mid-line should NOT match
        self.assertFalse(self._check_pattern("The prompt >>> is visible"))

    def test_pattern_empty_output(self):
        """Additional test: Verify graceful handling of empty output."""
        self.assertFalse(self._check_pattern(""))
        self.assertFalse(self._check_pattern("\n"))
        self.assertFalse(self._check_pattern("\n\n\n"))


if __name__ == "__main__":
    unittest.main()
