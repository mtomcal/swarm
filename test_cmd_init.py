#!/usr/bin/env python3
"""Tests for swarm init command - TDD tests for init subparser and cmd_init."""

import os
import subprocess
import sys
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import swarm


class TestInitSubparser(unittest.TestCase):
    """Test that init subparser is correctly configured."""

    def test_init_subparser_exists(self):
        """Test that 'init' subcommand is recognized."""
        # Parse valid init command - should not raise
        with patch('sys.argv', ['swarm', 'init']):
            import argparse
            parser = argparse.ArgumentParser()
            subparsers = parser.add_subparsers(dest='command')

            # This simulates what main() should do - add init subparser
            # We test that swarm.py's main() correctly adds it
            result = subprocess.run(
                [sys.executable, 'swarm.py', 'init', '--help'],
                capture_output=True,
                text=True
            )
            # Should succeed (exit 0) with help output
            self.assertEqual(result.returncode, 0)
            self.assertIn('init', result.stdout.lower())

    def test_init_dry_run_flag(self):
        """Test --dry-run flag is accepted."""
        result = subprocess.run(
            [sys.executable, 'swarm.py', 'init', '--dry-run', '--help'],
            capture_output=True,
            text=True
        )
        # Just checking it parses without error
        self.assertEqual(result.returncode, 0)

    def test_init_file_choices(self):
        """Test --file accepts valid choices."""
        # AGENTS.md should be valid
        result = subprocess.run(
            [sys.executable, 'swarm.py', 'init', '--file', 'AGENTS.md', '--help'],
            capture_output=True,
            text=True
        )
        self.assertEqual(result.returncode, 0)

        # CLAUDE.md should be valid
        result = subprocess.run(
            [sys.executable, 'swarm.py', 'init', '--file', 'CLAUDE.md', '--help'],
            capture_output=True,
            text=True
        )
        self.assertEqual(result.returncode, 0)

    def test_init_file_invalid_choice(self):
        """Test --file rejects invalid choices."""
        result = subprocess.run(
            [sys.executable, 'swarm.py', 'init', '--file', 'INVALID.md'],
            capture_output=True,
            text=True
        )
        # Should fail with invalid choice
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('invalid choice', result.stderr.lower())

    def test_init_force_flag(self):
        """Test --force flag is accepted."""
        result = subprocess.run(
            [sys.executable, 'swarm.py', 'init', '--force', '--help'],
            capture_output=True,
            text=True
        )
        self.assertEqual(result.returncode, 0)


class TestCmdInit(unittest.TestCase):
    """Test cmd_init function."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.original_cwd = os.getcwd()
        os.chdir(self.temp_dir)

    def tearDown(self):
        """Clean up test fixtures."""
        os.chdir(self.original_cwd)
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_cmd_init_dry_run_no_file_created(self):
        """Test --dry-run shows what would be done without creating file."""
        args = Namespace(dry_run=True, file=None, force=False)

        with patch('builtins.print') as mock_print:
            swarm.cmd_init(args)

        # Should NOT create the file
        self.assertFalse(Path('AGENTS.md').exists())
        self.assertFalse(Path('CLAUDE.md').exists())

        # Should print what would be done
        output = ' '.join(str(call) for call in mock_print.call_args_list)
        self.assertIn('AGENTS.md', output)

    def test_cmd_init_creates_agents_md_by_default(self):
        """Test init creates AGENTS.md by default when neither exists."""
        args = Namespace(dry_run=False, file=None, force=False)

        with patch('builtins.print'):
            swarm.cmd_init(args)

        self.assertTrue(Path('AGENTS.md').exists())
        content = Path('AGENTS.md').read_text()
        # Should use SWARM_INSTRUCTIONS constant with marker
        self.assertIn('Process Management (swarm)', content)

    def test_cmd_init_creates_claude_md_when_specified(self):
        """Test init creates CLAUDE.md when --file=CLAUDE.md."""
        args = Namespace(dry_run=False, file='CLAUDE.md', force=False)

        with patch('builtins.print'):
            swarm.cmd_init(args)

        self.assertTrue(Path('CLAUDE.md').exists())
        content = Path('CLAUDE.md').read_text()
        self.assertIn('Process Management (swarm)', content)

    def test_cmd_init_uses_swarm_instructions_content(self):
        """Test init uses SWARM_INSTRUCTIONS constant."""
        args = Namespace(dry_run=False, file=None, force=False)

        with patch('builtins.print'):
            swarm.cmd_init(args)

        content = Path('AGENTS.md').read_text()
        # Should contain key elements from SWARM_INSTRUCTIONS
        self.assertIn('Process Management (swarm)', content)
        self.assertIn('swarm spawn', content)
        self.assertIn('swarm ls', content)
        self.assertIn('swarm kill', content)

    def test_cmd_init_prints_success_message(self):
        """Test init prints success message."""
        args = Namespace(dry_run=False, file=None, force=False)

        with patch('builtins.print') as mock_print:
            swarm.cmd_init(args)

        # Should print success message
        output = ' '.join(str(call) for call in mock_print.call_args_list)
        self.assertTrue(
            'created' in output.lower() or 'initialized' in output.lower() or 'added' in output.lower()
        )


class TestCmdInitIdempotency(unittest.TestCase):
    """Test idempotent behavior with marker detection."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.original_cwd = os.getcwd()
        os.chdir(self.temp_dir)

    def tearDown(self):
        """Clean up test fixtures."""
        os.chdir(self.original_cwd)
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_cmd_init_detects_marker_in_agents_md(self):
        """Test init detects existing marker and reports already exists."""
        # Create file with marker
        Path('AGENTS.md').write_text('# My Project\n\n## Process Management (swarm)\nExisting content')

        args = Namespace(dry_run=False, file=None, force=False)

        with patch('builtins.print') as mock_print:
            swarm.cmd_init(args)

        # Should NOT modify the file
        content = Path('AGENTS.md').read_text()
        self.assertIn('Existing content', content)

        # Should print "already exists" or similar
        output = ' '.join(str(call) for call in mock_print.call_args_list)
        self.assertTrue('already' in output.lower() or 'exists' in output.lower())

    def test_cmd_init_detects_marker_in_claude_md(self):
        """Test init detects existing marker in CLAUDE.md."""
        # Create file with marker
        Path('CLAUDE.md').write_text('# Instructions\n\n## Process Management (swarm)\nOther stuff')

        args = Namespace(dry_run=False, file=None, force=False)

        with patch('builtins.print') as mock_print:
            swarm.cmd_init(args)

        # Should NOT modify the file
        content = Path('CLAUDE.md').read_text()
        self.assertIn('Other stuff', content)

        # Should print that it already exists
        output = ' '.join(str(call) for call in mock_print.call_args_list)
        self.assertTrue('already' in output.lower() or 'exists' in output.lower())

    def test_cmd_init_force_overwrites_marker_section(self):
        """Test --force replaces existing section."""
        # Create file with marker and old content
        Path('AGENTS.md').write_text('# My Project\n\n## Process Management (swarm)\nOld swarm content\n\n## Other Section\nKeep this')

        args = Namespace(dry_run=False, file='AGENTS.md', force=True)

        with patch('builtins.print'):
            swarm.cmd_init(args)

        content = Path('AGENTS.md').read_text()
        # Should have new SWARM_INSTRUCTIONS content
        self.assertIn('swarm spawn', content)
        # Marker should still be present
        self.assertIn('Process Management (swarm)', content)


class TestCmdInitFileDiscovery(unittest.TestCase):
    """Test file auto-discovery (AGENTS.md first, then CLAUDE.md)."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.original_cwd = os.getcwd()
        os.chdir(self.temp_dir)

    def tearDown(self):
        """Clean up test fixtures."""
        os.chdir(self.original_cwd)
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_cmd_init_uses_agents_md_when_exists(self):
        """Test init appends to AGENTS.md when it exists (no marker)."""
        # Create existing AGENTS.md without marker
        Path('AGENTS.md').write_text('# My Project\n\nExisting content\n')

        args = Namespace(dry_run=False, file=None, force=False)

        with patch('builtins.print'):
            swarm.cmd_init(args)

        content = Path('AGENTS.md').read_text()
        # Should preserve existing content
        self.assertIn('# My Project', content)
        self.assertIn('Existing content', content)
        # Should append SWARM_INSTRUCTIONS
        self.assertIn('Process Management (swarm)', content)

    def test_cmd_init_uses_claude_md_when_no_agents_md(self):
        """Test init appends to CLAUDE.md when AGENTS.md doesn't exist."""
        # Create only CLAUDE.md without marker
        Path('CLAUDE.md').write_text('# Claude Instructions\n\nBe helpful\n')

        args = Namespace(dry_run=False, file=None, force=False)

        with patch('builtins.print'):
            swarm.cmd_init(args)

        # Should use CLAUDE.md
        content = Path('CLAUDE.md').read_text()
        self.assertIn('# Claude Instructions', content)
        self.assertIn('Be helpful', content)
        self.assertIn('Process Management (swarm)', content)
        # Should NOT create AGENTS.md
        self.assertFalse(Path('AGENTS.md').exists())

    def test_cmd_init_prefers_agents_md_over_claude_md(self):
        """Test init prefers AGENTS.md when both exist."""
        # Create both files without marker
        Path('AGENTS.md').write_text('# Agents\n')
        Path('CLAUDE.md').write_text('# Claude\n')

        args = Namespace(dry_run=False, file=None, force=False)

        with patch('builtins.print'):
            swarm.cmd_init(args)

        # AGENTS.md should be modified
        agents_content = Path('AGENTS.md').read_text()
        self.assertIn('Process Management (swarm)', agents_content)

        # CLAUDE.md should be unchanged
        claude_content = Path('CLAUDE.md').read_text()
        self.assertNotIn('Process Management (swarm)', claude_content)

    def test_cmd_init_creates_agents_md_when_neither_exists(self):
        """Test init creates AGENTS.md when neither file exists."""
        args = Namespace(dry_run=False, file=None, force=False)

        with patch('builtins.print'):
            swarm.cmd_init(args)

        self.assertTrue(Path('AGENTS.md').exists())
        self.assertFalse(Path('CLAUDE.md').exists())

    def test_cmd_init_respects_explicit_file_choice(self):
        """Test --file overrides auto-discovery."""
        # Create AGENTS.md (would normally be preferred)
        Path('AGENTS.md').write_text('# Agents\n')

        args = Namespace(dry_run=False, file='CLAUDE.md', force=False)

        with patch('builtins.print'):
            swarm.cmd_init(args)

        # Should create CLAUDE.md as requested
        self.assertTrue(Path('CLAUDE.md').exists())
        claude_content = Path('CLAUDE.md').read_text()
        self.assertIn('Process Management (swarm)', claude_content)

        # AGENTS.md should be unchanged
        agents_content = Path('AGENTS.md').read_text()
        self.assertNotIn('Process Management (swarm)', agents_content)


class TestCmdInitAppendBehavior(unittest.TestCase):
    """Test append behavior for existing files."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.original_cwd = os.getcwd()
        os.chdir(self.temp_dir)

    def tearDown(self):
        """Clean up test fixtures."""
        os.chdir(self.original_cwd)
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_cmd_init_appends_with_proper_newlines(self):
        """Test init appends with proper trailing newline handling."""
        # File without trailing newline
        Path('AGENTS.md').write_text('# Project\nContent without trailing newline')

        args = Namespace(dry_run=False, file=None, force=False)

        with patch('builtins.print'):
            swarm.cmd_init(args)

        content = Path('AGENTS.md').read_text()
        # Should have blank line between existing and new content
        self.assertIn('Content without trailing newline\n\n', content)
        self.assertIn('Process Management (swarm)', content)

    def test_cmd_init_appends_with_existing_trailing_newline(self):
        """Test init handles file with existing trailing newline."""
        # File with trailing newline
        Path('AGENTS.md').write_text('# Project\nContent with trailing newline\n')

        args = Namespace(dry_run=False, file=None, force=False)

        with patch('builtins.print'):
            swarm.cmd_init(args)

        content = Path('AGENTS.md').read_text()
        # Should add blank line before new content
        self.assertIn('Content with trailing newline\n\n', content)
        self.assertIn('Process Management (swarm)', content)

    def test_cmd_init_appends_with_multiple_trailing_newlines(self):
        """Test init handles file with multiple trailing newlines."""
        # File with multiple trailing newlines
        Path('AGENTS.md').write_text('# Project\nContent\n\n\n')

        args = Namespace(dry_run=False, file=None, force=False)

        with patch('builtins.print'):
            swarm.cmd_init(args)

        content = Path('AGENTS.md').read_text()
        # Should normalize to single blank line separator
        self.assertNotIn('\n\n\n\n', content)
        self.assertIn('Process Management (swarm)', content)


class TestCmdInitExitCodes(unittest.TestCase):
    """Test correct exit codes for various scenarios."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.original_cwd = os.getcwd()
        os.chdir(self.temp_dir)

    def tearDown(self):
        """Clean up test fixtures."""
        os.chdir(self.original_cwd)
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_cmd_init_exit_0_on_success(self):
        """Test exit code 0 on successful creation."""
        args = Namespace(dry_run=False, file=None, force=False)

        with patch('builtins.print'):
            # Should not raise SystemExit
            swarm.cmd_init(args)

    def test_cmd_init_exit_0_when_already_exists(self):
        """Test exit code 0 when marker already exists (idempotent)."""
        Path('AGENTS.md').write_text('## Process Management (swarm)\nExisting')

        args = Namespace(dry_run=False, file=None, force=False)

        with patch('builtins.print'):
            # Should not raise SystemExit - idempotent success
            swarm.cmd_init(args)


class TestInitIntegration(unittest.TestCase):
    """Integration tests for init command via CLI."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.original_cwd = os.getcwd()
        os.chdir(self.temp_dir)

    def tearDown(self):
        """Clean up test fixtures."""
        os.chdir(self.original_cwd)
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_cli_init_default(self):
        """Test swarm init via CLI creates AGENTS.md."""
        result = subprocess.run(
            [sys.executable, '-c', f'''
import sys
sys.path.insert(0, "{self.original_cwd}")
import swarm
from argparse import Namespace
args = Namespace(dry_run=False, file=None, force=False)
swarm.cmd_init(args)
'''],
            capture_output=True,
            text=True
        )
        self.assertEqual(result.returncode, 0)
        self.assertTrue(Path('AGENTS.md').exists())

    def test_cli_init_dry_run(self):
        """Test swarm init --dry-run via CLI."""
        result = subprocess.run(
            [sys.executable, '-c', f'''
import sys
sys.path.insert(0, "{self.original_cwd}")
import swarm
from argparse import Namespace
args = Namespace(dry_run=True, file=None, force=False)
swarm.cmd_init(args)
'''],
            capture_output=True,
            text=True
        )
        self.assertEqual(result.returncode, 0)
        self.assertFalse(Path('AGENTS.md').exists())


if __name__ == "__main__":
    unittest.main()
