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
        args = Namespace(dry_run=True, file='AGENTS.md', force=False)

        with patch('builtins.print') as mock_print:
            swarm.cmd_init(args)

        # Should NOT create the file
        self.assertFalse(Path('AGENTS.md').exists())

        # Should print what would be done
        output = ' '.join(str(call) for call in mock_print.call_args_list)
        self.assertIn('AGENTS.md', output)

    def test_cmd_init_creates_agents_md(self):
        """Test init creates AGENTS.md by default."""
        args = Namespace(dry_run=False, file='AGENTS.md', force=False)

        with patch('builtins.print'):
            swarm.cmd_init(args)

        self.assertTrue(Path('AGENTS.md').exists())
        content = Path('AGENTS.md').read_text()
        self.assertIn('swarm', content.lower())

    def test_cmd_init_creates_claude_md(self):
        """Test init creates CLAUDE.md when specified."""
        args = Namespace(dry_run=False, file='CLAUDE.md', force=False)

        with patch('builtins.print'):
            swarm.cmd_init(args)

        self.assertTrue(Path('CLAUDE.md').exists())
        content = Path('CLAUDE.md').read_text()
        self.assertIn('swarm', content.lower())

    def test_cmd_init_refuses_overwrite_without_force(self):
        """Test init refuses to overwrite existing file without --force."""
        # Create existing file
        Path('AGENTS.md').write_text('existing content')

        args = Namespace(dry_run=False, file='AGENTS.md', force=False)

        with patch('sys.stderr'):
            with self.assertRaises(SystemExit) as cm:
                swarm.cmd_init(args)
            self.assertEqual(cm.exception.code, 1)

        # Original content should be preserved
        content = Path('AGENTS.md').read_text()
        self.assertEqual(content, 'existing content')

    def test_cmd_init_overwrites_with_force(self):
        """Test init overwrites existing file with --force."""
        # Create existing file
        Path('AGENTS.md').write_text('existing content')

        args = Namespace(dry_run=False, file='AGENTS.md', force=True)

        with patch('builtins.print'):
            swarm.cmd_init(args)

        # File should be overwritten
        content = Path('AGENTS.md').read_text()
        self.assertNotEqual(content, 'existing content')
        self.assertIn('swarm', content.lower())

    def test_cmd_init_prints_success_message(self):
        """Test init prints success message."""
        args = Namespace(dry_run=False, file='AGENTS.md', force=False)

        with patch('builtins.print') as mock_print:
            swarm.cmd_init(args)

        # Should print success message
        output = ' '.join(str(call) for call in mock_print.call_args_list)
        self.assertTrue(
            'created' in output.lower() or 'initialized' in output.lower()
        )


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
args = Namespace(dry_run=False, file='AGENTS.md', force=False)
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
args = Namespace(dry_run=True, file='AGENTS.md', force=False)
swarm.cmd_init(args)
'''],
            capture_output=True,
            text=True
        )
        self.assertEqual(result.returncode, 0)
        self.assertFalse(Path('AGENTS.md').exists())


if __name__ == "__main__":
    unittest.main()
