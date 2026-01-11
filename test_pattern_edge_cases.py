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

    def _get_matching_pattern(self, text: str) -> str | None:
        """Get the pattern that matched, for debugging.

        Args:
            text: Text to check for ready patterns

        Returns:
            The pattern string that matched, or None
        """
        for line in text.split('\n'):
            for pattern in self.ready_patterns:
                if re.search(pattern, line):
                    return pattern
        return None

    def test_pattern_with_leading_whitespace(self):
        """EDGE-1: Verify ^> pattern doesn't match if there's leading whitespace.

        The ^> pattern should only match prompts at the start of a line.
        Leading whitespace means it's not actually a prompt.
        """
        # Leading spaces should NOT match
        output1 = "  > "
        result1 = self._check_pattern(output1)
        self.assertFalse(
            result1,
            f"Expected '  > ' (2 leading spaces) to NOT match - prompt not at line start. "
            f"Output: {output1!r}, Matched pattern: {self._get_matching_pattern(output1)}"
        )

        output2 = "   > some text"
        result2 = self._check_pattern(output2)
        self.assertFalse(
            result2,
            f"Expected '   > some text' (3 leading spaces) to NOT match. "
            f"Output: {output2!r}, Matched pattern: {self._get_matching_pattern(output2)}"
        )

        output3 = "\t> "
        result3 = self._check_pattern(output3)
        self.assertFalse(
            result3,
            f"Expected '\\t> ' (leading tab) to NOT match. "
            f"Output: {output3!r}, Matched pattern: {self._get_matching_pattern(output3)}"
        )

        # But actual prompt at line start SHOULD match
        output4 = "> "
        result4 = self._check_pattern(output4)
        self.assertTrue(
            result4,
            f"Expected '> ' at line start to match Claude Code prompt pattern. Output: {output4!r}"
        )

        output5 = "> Try something"
        result5 = self._check_pattern(output5)
        self.assertTrue(
            result5,
            f"Expected '> Try something' at line start to match. Output: {output5!r}"
        )

    def test_pattern_with_ansi_before_prompt(self):
        r"""EDGE-2: Verify ANSI codes before prompt are handled correctly.

        Terminal color codes often appear before prompts. The ANSI-aware
        pattern (?:^|\x1b\[[0-9;]*m)> should match these.

        This is marked P1 critical in the research document.
        """
        # ANSI color codes before prompt should match
        output1 = "\x1b[32m> "
        result1 = self._check_pattern(output1)
        self.assertTrue(
            result1,
            f"Expected ANSI green (\\x1b[32m) before '> ' to match. Output: {output1!r}"
        )

        output2 = "\x1b[0m> "
        result2 = self._check_pattern(output2)
        self.assertTrue(
            result2,
            f"Expected ANSI reset (\\x1b[0m) before '> ' to match. Output: {output2!r}"
        )

        output3 = "\x1b[1;34m> "
        result3 = self._check_pattern(output3)
        self.assertTrue(
            result3,
            f"Expected ANSI bold blue (\\x1b[1;34m) before '> ' to match. Output: {output3!r}"
        )

        output4 = "\x1b[0m\x1b[1;34m> "
        result4 = self._check_pattern(output4)
        self.assertTrue(
            result4,
            f"Expected multiple ANSI codes before '> ' to match. Output: {output4!r}"
        )

        # ANSI codes for shell prompt
        output5 = "\x1b[32m$ "
        result5 = self._check_pattern(output5)
        self.assertTrue(
            result5,
            f"Expected ANSI green before '$ ' shell prompt to match. Output: {output5!r}"
        )

        # ANSI codes for Python REPL
        output6 = "\x1b[32m>>> "
        result6 = self._check_pattern(output6)
        self.assertTrue(
            result6,
            f"Expected ANSI green before '>>> ' Python REPL to match. Output: {output6!r}"
        )

        # Plain prompts should still work
        output7 = "> "
        result7 = self._check_pattern(output7)
        self.assertTrue(
            result7,
            f"Expected plain '> ' (no ANSI) to still match. Output: {output7!r}"
        )

        output8 = "$ "
        result8 = self._check_pattern(output8)
        self.assertTrue(
            result8,
            f"Expected plain '$ ' (no ANSI) to still match. Output: {output8!r}"
        )

        output9 = ">>> "
        result9 = self._check_pattern(output9)
        self.assertTrue(
            result9,
            f"Expected plain '>>> ' (no ANSI) to still match. Output: {output9!r}"
        )

    def test_pattern_multiline_output(self):
        """EDGE-3: Verify pattern found on line N of multi-line output is detected.

        The ready pattern might not appear on the first line. We need to
        check all lines in the output.
        """
        # Pattern on first line
        multiline1 = "> \nSome other text\nMore text"
        result1 = self._check_pattern(multiline1)
        self.assertTrue(
            result1,
            f"Expected '> ' on first line of multi-line output to match. Output: {multiline1!r}"
        )

        # Pattern on middle line
        multiline2 = "Loading...\n> Try something\nStatus line"
        result2 = self._check_pattern(multiline2)
        self.assertTrue(
            result2,
            f"Expected '> ' on middle line (line 2) to match. Output: {multiline2!r}"
        )

        # Pattern on last line
        multiline3 = "Banner text\nVersion info\n> "
        result3 = self._check_pattern(multiline3)
        self.assertTrue(
            result3,
            f"Expected '> ' on last line (line 3) to match. Output: {multiline3!r}"
        )

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
        result4 = self._check_pattern(claude_startup)
        matched_pattern = self._get_matching_pattern(claude_startup)
        self.assertTrue(
            result4,
            f"Expected Claude Code startup screen to match (banner, prompt, or bypass text). "
            f"Matched pattern: {matched_pattern}"
        )

    def test_pattern_carriage_return_handling(self):
        """EDGE-4: Verify lines with \\r (carriage return) are handled correctly.

        Terminals use \\r to overwrite lines (e.g., progress indicators).
        Our pattern matching doesn't simulate terminal \\r behavior, but we test
        that patterns can still be found when \\r is present in the output.
        """
        # Simple carriage return - terminal overwrites "Loading..." with "Done!"
        output1 = "Loading...\rDone!\n> "
        result1 = self._check_pattern(output1)
        self.assertTrue(
            result1,
            f"Expected '> ' on line after \\r to match. Output: {output1!r}"
        )

        # Progress bar that gets overwritten, prompt on new line
        output2 = "Progress: 10%\rProgress: 50%\rProgress: 100%\n$ "
        result2 = self._check_pattern(output2)
        self.assertTrue(
            result2,
            f"Expected '$ ' on line after progress bar with \\r to match. Output: {output2!r}"
        )

        # Carriage return in middle of output
        output3 = "Starting...\rReady\n> Try something"
        result3 = self._check_pattern(output3)
        self.assertTrue(
            result3,
            f"Expected '> Try something' after \\r in previous line to match. Output: {output3!r}"
        )

        # Pattern appears after carriage return on same line
        # Note: In actual terminal, \r moves cursor to line start, but our
        # pattern matching just treats \r as a character in the string
        output4 = "Loading\r> "
        result4 = self._check_pattern(output4)
        # This won't match because > is not at line start in the string
        # This is acceptable - in real tmux capture, the line would be rendered
        self.assertFalse(
            result4,
            f"Expected '> ' after \\r on same line to NOT match (\\r not processed as cursor move). "
            f"Output: {output4!r}"
        )

    def test_pattern_unicode_in_output(self):
        """EDGE-5: Verify non-ASCII characters don't break pattern matching.

        Claude Code uses Unicode symbols (⏵⏵) and other non-ASCII characters.
        Pattern matching should handle these gracefully.
        """
        # Unicode triangle symbols from Claude Code
        output1 = "⏵⏵ bypass permissions on"
        result1 = self._check_pattern(output1)
        self.assertTrue(
            result1,
            f"Expected '⏵⏵ bypass permissions on' with Unicode triangles to match. Output: {output1!r}"
        )

        # Unicode with prompt
        output2 = "✓ Ready\n> "
        result2 = self._check_pattern(output2)
        self.assertTrue(
            result2,
            f"Expected '> ' after Unicode checkmark to match. Output: {output2!r}"
        )

        # Emoji in output
        output3 = "🚀 Starting...\n> Try something"
        result3 = self._check_pattern(output3)
        self.assertTrue(
            result3,
            f"Expected '> ' after emoji to match. Output: {output3!r}"
        )

        # Chinese characters
        output4 = "启动中...\n> "
        result4 = self._check_pattern(output4)
        self.assertTrue(
            result4,
            f"Expected '> ' after Chinese characters to match. Output: {output4!r}"
        )

        # Mixed Unicode and ANSI
        output5 = "\x1b[32m⏵⏵ bypass permissions on\x1b[0m"
        result5 = self._check_pattern(output5)
        self.assertTrue(
            result5,
            f"Expected 'bypass permissions on' with Unicode and ANSI to match. Output: {output5!r}"
        )

    def test_pattern_very_long_lines(self):
        """EDGE-6: Verify wrapped lines (exceeding terminal width) are handled.

        Very long lines might be wrapped by the terminal, but our pattern
        matching works on logical lines, so this should still work.
        """
        # Very long line before prompt
        long_line = "x" * 500 + "\n> "
        result1 = self._check_pattern(long_line)
        self.assertTrue(
            result1,
            f"Expected '> ' after 500-char line to match. Line length: {len(long_line)} chars"
        )

        # Prompt at start of very long line
        long_prompt_line = "> " + "x" * 500
        result2 = self._check_pattern(long_prompt_line)
        self.assertTrue(
            result2,
            f"Expected '> ' at start of 500-char line to match. Line length: {len(long_prompt_line)} chars"
        )

        # Very long output with pattern in middle
        long_output = "Start\n" + "x" * 1000 + "\n> Try something\n" + "y" * 1000
        result3 = self._check_pattern(long_output)
        self.assertTrue(
            result3,
            f"Expected '> ' in middle of very long output to match. Total length: {len(long_output)} chars"
        )

    def test_pattern_rapid_output_capture(self):
        """EDGE-7: Verify pattern timing edge case - pattern appears then scrolls.

        This is a unit test, so we can't truly test timing. Instead, we verify
        that if the pattern appears anywhere in the captured output, it's detected.

        The actual timing test would be an integration test with real tmux.
        """
        # Pattern appears early, then lots of output
        rapid1 = "> Ready\n" + "\n".join([f"Line {i}" for i in range(100)])
        result1 = self._check_pattern(rapid1)
        self.assertTrue(
            result1,
            f"Expected '> ' at start of 100-line output to match. Total lines: 101"
        )

        # Pattern appears late
        rapid2 = "\n".join([f"Line {i}" for i in range(100)]) + "\n> "
        result2 = self._check_pattern(rapid2)
        self.assertTrue(
            result2,
            f"Expected '> ' at end of 100-line output to match. Total lines: 101"
        )

        # Pattern appears, then scrolls, but we capture history
        # (In real integration test, this would use tmux capture-pane with -S)
        rapid3 = "\n".join([f"Output {i}" for i in range(50)]) + "\n> \n" + "\n".join([f"More {i}" for i in range(50)])
        result3 = self._check_pattern(rapid3)
        self.assertTrue(
            result3,
            f"Expected '> ' in middle of scrolling output to match. Total lines: 101"
        )

    def test_pattern_bypass_permissions_variants(self):
        """Additional test: Verify bypass permissions text variations.

        The research doc notes that the actual text is "bypass permissions on"
        with spaces, not "bypass.permissions" with a dot.
        """
        # Current actual Claude Code text
        output1 = "⏵⏵ bypass permissions on (shift+tab to cycle)"
        result1 = self._check_pattern(output1)
        self.assertTrue(
            result1,
            f"Expected full Claude Code bypass text to match. Output: {output1!r}"
        )

        # Just the core text
        output2 = "bypass permissions on"
        result2 = self._check_pattern(output2)
        self.assertTrue(
            result2,
            f"Expected bare 'bypass permissions on' to match. Output: {output2!r}"
        )

        # With ANSI codes
        output3 = "\x1b[32mbypass permissions on\x1b[0m"
        result3 = self._check_pattern(output3)
        self.assertTrue(
            result3,
            f"Expected 'bypass permissions on' with ANSI codes to match. Output: {output3!r}"
        )

    def test_pattern_claude_code_banner(self):
        """Additional test: Verify Claude Code banner detection.

        The pattern should match the versioned banner format.
        """
        # Standard banner
        output1 = "Claude Code v2.0.76"
        result1 = self._check_pattern(output1)
        self.assertTrue(
            result1,
            f"Expected 'Claude Code v2.0.76' to match banner pattern. Output: {output1!r}"
        )

        # Different versions
        output2 = "Claude Code v1.0.0"
        result2 = self._check_pattern(output2)
        self.assertTrue(
            result2,
            f"Expected 'Claude Code v1.0.0' to match banner pattern. Output: {output2!r}"
        )

        output3 = "Claude Code v3.14.159"
        result3 = self._check_pattern(output3)
        self.assertTrue(
            result3,
            f"Expected 'Claude Code v3.14.159' to match banner pattern. Output: {output3!r}"
        )

        # With surrounding text
        output4 = " * ▐▛███▜▌ *   Claude Code v2.0.76"
        result4 = self._check_pattern(output4)
        self.assertTrue(
            result4,
            f"Expected banner with ASCII art prefix to match. Output: {output4!r}"
        )

        # Should NOT match non-versioned text
        output5 = "Claude Code"
        result5 = self._check_pattern(output5)
        self.assertFalse(
            result5,
            f"Expected 'Claude Code' without version to NOT match. Output: {output5!r}"
        )

        output6 = "Welcome to Claude Code"
        result6 = self._check_pattern(output6)
        self.assertFalse(
            result6,
            f"Expected 'Welcome to Claude Code' without version to NOT match. Output: {output6!r}"
        )

    def test_pattern_no_false_positives(self):
        """Additional test: Verify patterns don't match incorrectly.

        Mid-line > characters should not match the ^> pattern.
        """
        # Redirect operators should NOT match
        output1 = "echo hello > file.txt"
        result1 = self._check_pattern(output1)
        self.assertFalse(
            result1,
            f"Expected shell redirect '>' mid-line to NOT match prompt pattern. Output: {output1!r}"
        )

        output2 = "cat file1 > file2"
        result2 = self._check_pattern(output2)
        self.assertFalse(
            result2,
            f"Expected file redirect '>' mid-line to NOT match. Output: {output2!r}"
        )

        # Comparison operators should NOT match
        output3 = "if x > 5:"
        result3 = self._check_pattern(output3)
        self.assertFalse(
            result3,
            f"Expected comparison '>' mid-line to NOT match. Output: {output3!r}"
        )

        # Dollar sign mid-line should NOT match
        output4 = "Price: $100"
        result4 = self._check_pattern(output4)
        self.assertFalse(
            result4,
            f"Expected '$' in 'Price: $100' mid-line to NOT match shell prompt. Output: {output4!r}"
        )

        # Python prompt mid-line should NOT match
        output5 = "The prompt >>> is visible"
        result5 = self._check_pattern(output5)
        self.assertFalse(
            result5,
            f"Expected '>>>' mid-line in prose to NOT match Python REPL. Output: {output5!r}"
        )

    def test_pattern_empty_output(self):
        """Additional test: Verify graceful handling of empty output."""
        output1 = ""
        result1 = self._check_pattern(output1)
        self.assertFalse(
            result1,
            f"Expected empty string to NOT match any pattern. Output: {output1!r}"
        )

        output2 = "\n"
        result2 = self._check_pattern(output2)
        self.assertFalse(
            result2,
            f"Expected single newline to NOT match any pattern. Output: {output2!r}"
        )

        output3 = "\n\n\n"
        result3 = self._check_pattern(output3)
        self.assertFalse(
            result3,
            f"Expected multiple newlines to NOT match any pattern. Output: {output3!r}"
        )


if __name__ == "__main__":
    unittest.main()
