#!/usr/bin/env python3
"""Tests for swarm ralph command - TDD tests for ralph subcommands."""

import os
import subprocess
import sys
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch

import swarm


class TestRalphSubparser(unittest.TestCase):
    """Test that ralph subparser is correctly configured."""

    def test_ralph_subparser_exists(self):
        """Test that 'ralph' subcommand is recognized."""
        result = subprocess.run(
            [sys.executable, 'swarm.py', 'ralph', '--help'],
            capture_output=True,
            text=True
        )
        # Should succeed with help output
        self.assertEqual(result.returncode, 0)
        self.assertIn('ralph', result.stdout.lower())

    def test_ralph_init_subcommand_exists(self):
        """Test that 'ralph init' subcommand is recognized."""
        result = subprocess.run(
            [sys.executable, 'swarm.py', 'ralph', 'init', '--help'],
            capture_output=True,
            text=True
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn('prompt', result.stdout.lower())

    def test_ralph_template_subcommand_exists(self):
        """Test that 'ralph template' subcommand is recognized."""
        result = subprocess.run(
            [sys.executable, 'swarm.py', 'ralph', 'template', '--help'],
            capture_output=True,
            text=True
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn('template', result.stdout.lower())

    def test_ralph_init_force_flag(self):
        """Test --force flag is accepted for ralph init."""
        result = subprocess.run(
            [sys.executable, 'swarm.py', 'ralph', 'init', '--force', '--help'],
            capture_output=True,
            text=True
        )
        self.assertEqual(result.returncode, 0)

    def test_ralph_requires_subcommand(self):
        """Test that ralph without subcommand shows error."""
        result = subprocess.run(
            [sys.executable, 'swarm.py', 'ralph'],
            capture_output=True,
            text=True
        )
        # Should fail without subcommand
        self.assertNotEqual(result.returncode, 0)


class TestRalphPromptTemplate(unittest.TestCase):
    """Test RALPH_PROMPT_TEMPLATE constant."""

    def test_template_contains_study_instructions(self):
        """Test template contains study instructions."""
        self.assertIn('study specs/README.md', swarm.RALPH_PROMPT_TEMPLATE)
        self.assertIn('study CLAUDE.md', swarm.RALPH_PROMPT_TEMPLATE)

    def test_template_contains_verification_instruction(self):
        """Test template contains verification instruction."""
        self.assertIn('do not assume anything is implemented', swarm.RALPH_PROMPT_TEMPLATE)
        self.assertIn('verify by reading code', swarm.RALPH_PROMPT_TEMPLATE)

    def test_template_contains_plan_update_instruction(self):
        """Test template contains plan update instruction."""
        self.assertIn('IMPLEMENTATION_PLAN.md', swarm.RALPH_PROMPT_TEMPLATE)

    def test_template_contains_test_instruction(self):
        """Test template contains test instruction."""
        self.assertIn('tests', swarm.RALPH_PROMPT_TEMPLATE.lower())

    def test_template_contains_commit_instruction(self):
        """Test template contains commit instruction."""
        self.assertIn('commit', swarm.RALPH_PROMPT_TEMPLATE)
        self.assertIn('push', swarm.RALPH_PROMPT_TEMPLATE)

    def test_template_is_minimal(self):
        """Test template is minimal (less than 500 chars)."""
        # Template should be intentionally minimal for more context
        self.assertLess(len(swarm.RALPH_PROMPT_TEMPLATE), 500)


class TestCmdRalphInit(unittest.TestCase):
    """Test cmd_ralph_init function."""

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

    def test_creates_prompt_md(self):
        """Test ralph init creates PROMPT.md."""
        args = Namespace(force=False)

        with patch('builtins.print'):
            swarm.cmd_ralph_init(args)

        self.assertTrue(Path('PROMPT.md').exists())

    def test_creates_prompt_md_with_template_content(self):
        """Test ralph init creates PROMPT.md with template content."""
        args = Namespace(force=False)

        with patch('builtins.print'):
            swarm.cmd_ralph_init(args)

        content = Path('PROMPT.md').read_text()
        self.assertIn('study specs/README.md', content)
        self.assertIn('study CLAUDE.md', content)

    def test_prints_success_message(self):
        """Test ralph init prints success message."""
        args = Namespace(force=False)

        with patch('builtins.print') as mock_print:
            swarm.cmd_ralph_init(args)

        mock_print.assert_called_with('created PROMPT.md')

    def test_refuses_to_overwrite_existing(self):
        """Test ralph init refuses to overwrite existing PROMPT.md."""
        Path('PROMPT.md').write_text('existing content')
        args = Namespace(force=False)

        with patch('builtins.print'):
            with self.assertRaises(SystemExit) as ctx:
                swarm.cmd_ralph_init(args)

        self.assertEqual(ctx.exception.code, 1)

    def test_refuses_to_overwrite_error_message(self):
        """Test ralph init prints error when file exists."""
        Path('PROMPT.md').write_text('existing content')
        args = Namespace(force=False)

        with patch('builtins.print') as mock_print:
            with self.assertRaises(SystemExit):
                swarm.cmd_ralph_init(args)

        # Check error was printed to stderr
        error_output = str(mock_print.call_args_list)
        self.assertIn('already exists', error_output)

    def test_force_overwrites_existing(self):
        """Test ralph init --force overwrites existing PROMPT.md."""
        Path('PROMPT.md').write_text('old content')
        args = Namespace(force=True)

        with patch('builtins.print'):
            swarm.cmd_ralph_init(args)

        content = Path('PROMPT.md').read_text()
        self.assertNotIn('old content', content)
        self.assertIn('study specs/README.md', content)

    def test_force_prints_overwritten_message(self):
        """Test ralph init --force prints overwritten message."""
        Path('PROMPT.md').write_text('old content')
        args = Namespace(force=True)

        with patch('builtins.print') as mock_print:
            swarm.cmd_ralph_init(args)

        mock_print.assert_called_with('created PROMPT.md (overwritten)')

    def test_content_ends_with_newline(self):
        """Test PROMPT.md ends with newline."""
        args = Namespace(force=False)

        with patch('builtins.print'):
            swarm.cmd_ralph_init(args)

        content = Path('PROMPT.md').read_text()
        self.assertTrue(content.endswith('\n'))


class TestCmdRalphTemplate(unittest.TestCase):
    """Test cmd_ralph_template function."""

    def test_outputs_template_to_stdout(self):
        """Test ralph template outputs template to stdout."""
        args = Namespace()

        with patch('builtins.print') as mock_print:
            swarm.cmd_ralph_template(args)

        mock_print.assert_called_once()
        output = mock_print.call_args[0][0]
        self.assertIn('study specs/README.md', output)

    def test_outputs_complete_template(self):
        """Test ralph template outputs complete template."""
        args = Namespace()

        with patch('builtins.print') as mock_print:
            swarm.cmd_ralph_template(args)

        output = mock_print.call_args[0][0]
        self.assertEqual(output, swarm.RALPH_PROMPT_TEMPLATE)

    def test_no_files_created(self):
        """Test ralph template doesn't create any files."""
        temp_dir = tempfile.mkdtemp()
        original_cwd = os.getcwd()
        os.chdir(temp_dir)

        try:
            args = Namespace()

            with patch('builtins.print'):
                swarm.cmd_ralph_template(args)

            # Check no files were created
            files = list(Path('.').iterdir())
            self.assertEqual(len(files), 0)
        finally:
            os.chdir(original_cwd)
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)


class TestCmdRalphDispatch(unittest.TestCase):
    """Test cmd_ralph dispatch function."""

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

    def test_dispatch_init(self):
        """Test cmd_ralph dispatches to init."""
        args = Namespace(ralph_command='init', force=False)

        with patch('builtins.print'):
            swarm.cmd_ralph(args)

        self.assertTrue(Path('PROMPT.md').exists())

    def test_dispatch_template(self):
        """Test cmd_ralph dispatches to template."""
        args = Namespace(ralph_command='template')

        with patch('builtins.print') as mock_print:
            swarm.cmd_ralph(args)

        output = mock_print.call_args[0][0]
        self.assertIn('study specs/README.md', output)


class TestRalphIntegration(unittest.TestCase):
    """Integration tests for ralph command via CLI."""

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

    def test_cli_ralph_init(self):
        """Test swarm ralph init via CLI creates PROMPT.md."""
        result = subprocess.run(
            [sys.executable, '-c', f'''
import sys
sys.path.insert(0, "{self.original_cwd}")
import swarm
from argparse import Namespace
args = Namespace(ralph_command='init', force=False)
swarm.cmd_ralph(args)
'''],
            capture_output=True,
            text=True
        )
        self.assertEqual(result.returncode, 0)
        self.assertTrue(Path('PROMPT.md').exists())

    def test_cli_ralph_template(self):
        """Test swarm ralph template via CLI outputs template."""
        result = subprocess.run(
            [sys.executable, '-c', f'''
import sys
sys.path.insert(0, "{self.original_cwd}")
import swarm
from argparse import Namespace
args = Namespace(ralph_command='template')
swarm.cmd_ralph(args)
'''],
            capture_output=True,
            text=True
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn('study specs/README.md', result.stdout)

    def test_cli_ralph_init_refuses_overwrite(self):
        """Test swarm ralph init refuses to overwrite via CLI."""
        Path('PROMPT.md').write_text('existing')

        result = subprocess.run(
            [sys.executable, '-c', f'''
import sys
sys.path.insert(0, "{self.original_cwd}")
import swarm
from argparse import Namespace
args = Namespace(ralph_command='init', force=False)
swarm.cmd_ralph(args)
'''],
            capture_output=True,
            text=True
        )
        self.assertEqual(result.returncode, 1)
        # Original content should be preserved
        self.assertEqual(Path('PROMPT.md').read_text(), 'existing')

    def test_cli_ralph_init_force_overwrites(self):
        """Test swarm ralph init --force overwrites via CLI."""
        Path('PROMPT.md').write_text('old content')

        result = subprocess.run(
            [sys.executable, '-c', f'''
import sys
sys.path.insert(0, "{self.original_cwd}")
import swarm
from argparse import Namespace
args = Namespace(ralph_command='init', force=True)
swarm.cmd_ralph(args)
'''],
            capture_output=True,
            text=True
        )
        self.assertEqual(result.returncode, 0)
        content = Path('PROMPT.md').read_text()
        self.assertIn('study specs/README.md', content)


class TestRalphScenarios(unittest.TestCase):
    """Scenario-based tests from ralph-loop.md spec."""

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

    def test_scenario_initialize_prompt_file(self):
        """Scenario: Initialize prompt file.

        Given: Current directory has no PROMPT.md
        When: swarm ralph init
        Then:
          - PROMPT.md created with template content
          - Output: "created PROMPT.md"
          - Exit code 0
        """
        args = Namespace(ralph_command='init', force=False)

        with patch('builtins.print') as mock_print:
            swarm.cmd_ralph(args)

        # PROMPT.md created with template content
        self.assertTrue(Path('PROMPT.md').exists())
        content = Path('PROMPT.md').read_text()
        self.assertIn('study specs/README.md', content)

        # Output: "created PROMPT.md"
        mock_print.assert_called_with('created PROMPT.md')

    def test_scenario_init_refuses_to_overwrite(self):
        """Scenario: Init refuses to overwrite.

        Given: PROMPT.md already exists
        When: swarm ralph init
        Then:
          - Exit code 1
          - Error: "swarm: error: PROMPT.md already exists (use --force to overwrite)"
        """
        Path('PROMPT.md').write_text('existing content')
        args = Namespace(ralph_command='init', force=False)

        with self.assertRaises(SystemExit) as ctx:
            swarm.cmd_ralph(args)

        self.assertEqual(ctx.exception.code, 1)

    def test_scenario_init_with_force_flag(self):
        """Scenario: Init with force flag.

        Given: PROMPT.md already exists
        When: swarm ralph init --force
        Then:
          - PROMPT.md overwritten with template
          - Output: "created PROMPT.md (overwritten)"
          - Exit code 0
        """
        Path('PROMPT.md').write_text('old content')
        args = Namespace(ralph_command='init', force=True)

        with patch('builtins.print') as mock_print:
            swarm.cmd_ralph(args)

        # PROMPT.md overwritten with template
        content = Path('PROMPT.md').read_text()
        self.assertNotIn('old content', content)
        self.assertIn('study specs/README.md', content)

        # Output: "created PROMPT.md (overwritten)"
        mock_print.assert_called_with('created PROMPT.md (overwritten)')

    def test_scenario_output_template_to_stdout(self):
        """Scenario: Output template to stdout.

        Given: Agent wants to customize template
        When: swarm ralph template
        Then:
          - Template printed to stdout
          - No files created
          - Exit code 0
        """
        args = Namespace(ralph_command='template')

        with patch('builtins.print') as mock_print:
            swarm.cmd_ralph(args)

        # Template printed to stdout
        output = mock_print.call_args[0][0]
        self.assertEqual(output, swarm.RALPH_PROMPT_TEMPLATE)

        # No files created
        files = list(Path('.').iterdir())
        self.assertEqual(len(files), 0)


class TestRalphSpawnArguments(unittest.TestCase):
    """Test ralph spawn arguments are correctly configured."""

    def test_ralph_flag_exists(self):
        """Test that --ralph flag is recognized by spawn."""
        result = subprocess.run(
            [sys.executable, 'swarm.py', 'spawn', '--help'],
            capture_output=True,
            text=True,
            cwd=self.original_cwd if hasattr(self, 'original_cwd') else '.'
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn('--ralph', result.stdout)

    def test_prompt_file_argument_exists(self):
        """Test that --prompt-file argument is recognized by spawn."""
        result = subprocess.run(
            [sys.executable, 'swarm.py', 'spawn', '--help'],
            capture_output=True,
            text=True
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn('--prompt-file', result.stdout)

    def test_max_iterations_argument_exists(self):
        """Test that --max-iterations argument is recognized by spawn."""
        result = subprocess.run(
            [sys.executable, 'swarm.py', 'spawn', '--help'],
            capture_output=True,
            text=True
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn('--max-iterations', result.stdout)


class TestRalphSpawnValidation(unittest.TestCase):
    """Test ralph spawn validation logic."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.original_cwd = os.getcwd()
        os.chdir(self.temp_dir)
        # Create a test prompt file
        Path('test_prompt.md').write_text('test prompt content')

    def tearDown(self):
        """Clean up test fixtures."""
        os.chdir(self.original_cwd)
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_ralph_requires_prompt_file(self):
        """Test --ralph without --prompt-file fails."""
        args = Namespace(
            name='test-worker',
            ralph=True,
            prompt_file=None,
            max_iterations=10,
            tmux=False,
            worktree=False,
            session=None,
            tmux_socket=None,
            branch=None,
            worktree_dir=None,
            tags=[],
            env=[],
            cwd=None,
            ready_wait=False,
            ready_timeout=120,
            cmd=['--', 'echo', 'test']
        )

        with patch('builtins.print') as mock_print:
            with self.assertRaises(SystemExit) as ctx:
                swarm.cmd_spawn(args)

        self.assertEqual(ctx.exception.code, 1)
        # Check error message
        error_calls = [str(call) for call in mock_print.call_args_list]
        self.assertTrue(any('--ralph requires --prompt-file' in call for call in error_calls))

    def test_ralph_requires_max_iterations(self):
        """Test --ralph without --max-iterations fails."""
        args = Namespace(
            name='test-worker',
            ralph=True,
            prompt_file='test_prompt.md',
            max_iterations=None,
            tmux=False,
            worktree=False,
            session=None,
            tmux_socket=None,
            branch=None,
            worktree_dir=None,
            tags=[],
            env=[],
            cwd=None,
            ready_wait=False,
            ready_timeout=120,
            cmd=['--', 'echo', 'test']
        )

        with patch('builtins.print') as mock_print:
            with self.assertRaises(SystemExit) as ctx:
                swarm.cmd_spawn(args)

        self.assertEqual(ctx.exception.code, 1)
        # Check error message
        error_calls = [str(call) for call in mock_print.call_args_list]
        self.assertTrue(any('--ralph requires --max-iterations' in call for call in error_calls))

    def test_ralph_prompt_file_not_found(self):
        """Test --ralph with non-existent prompt file fails."""
        args = Namespace(
            name='test-worker',
            ralph=True,
            prompt_file='nonexistent.md',
            max_iterations=10,
            tmux=False,
            worktree=False,
            session=None,
            tmux_socket=None,
            branch=None,
            worktree_dir=None,
            tags=[],
            env=[],
            cwd=None,
            ready_wait=False,
            ready_timeout=120,
            cmd=['--', 'echo', 'test']
        )

        with patch('builtins.print') as mock_print:
            with self.assertRaises(SystemExit) as ctx:
                swarm.cmd_spawn(args)

        self.assertEqual(ctx.exception.code, 1)
        # Check error message
        error_calls = [str(call) for call in mock_print.call_args_list]
        self.assertTrue(any('prompt file not found' in call for call in error_calls))

    def test_ralph_high_iteration_warning(self):
        """Test --ralph with >50 iterations shows warning."""
        args = Namespace(
            name='test-worker',
            ralph=True,
            prompt_file='test_prompt.md',
            max_iterations=100,
            tmux=False,
            worktree=False,
            session=None,
            tmux_socket=None,
            branch=None,
            worktree_dir=None,
            tags=[],
            env=[],
            cwd=None,
            ready_wait=False,
            ready_timeout=120,
            cmd=['--', 'echo', 'test']
        )

        # Mock State and other functions to prevent actual spawning
        with patch.object(swarm.State, 'get_worker', return_value=None):
            with patch.object(swarm.State, 'add_worker'):
                with patch('swarm.create_tmux_window'):
                    with patch('swarm.get_default_session_name', return_value='swarm-test'):
                        with patch('builtins.print') as mock_print:
                            swarm.cmd_spawn(args)

        # Check warning was printed
        all_calls = [str(call) for call in mock_print.call_args_list]
        self.assertTrue(any('high iteration count' in call for call in all_calls))

    def test_ralph_auto_enables_tmux(self):
        """Test --ralph automatically enables --tmux."""
        args = Namespace(
            name='test-worker',
            ralph=True,
            prompt_file='test_prompt.md',
            max_iterations=10,
            tmux=False,  # Not explicitly set
            worktree=False,
            session=None,
            tmux_socket=None,
            branch=None,
            worktree_dir=None,
            tags=[],
            env=[],
            cwd=None,
            ready_wait=False,
            ready_timeout=120,
            cmd=['--', 'echo', 'test']
        )

        # Mock State and other functions to prevent actual spawning
        with patch.object(swarm.State, 'get_worker', return_value=None):
            with patch.object(swarm.State, 'add_worker'):
                with patch('swarm.create_tmux_window') as mock_create_tmux:
                    with patch('swarm.get_default_session_name', return_value='swarm-test'):
                        with patch('builtins.print'):
                            swarm.cmd_spawn(args)

        # Verify tmux window was created (indicating tmux was enabled)
        mock_create_tmux.assert_called_once()

    def test_ralph_valid_configuration_proceeds(self):
        """Test valid ralph configuration proceeds to spawn."""
        args = Namespace(
            name='test-worker',
            ralph=True,
            prompt_file='test_prompt.md',
            max_iterations=10,
            tmux=False,
            worktree=False,
            session=None,
            tmux_socket=None,
            branch=None,
            worktree_dir=None,
            tags=[],
            env=[],
            cwd=None,
            ready_wait=False,
            ready_timeout=120,
            cmd=['--', 'echo', 'test']
        )

        # Mock State and other functions to prevent actual spawning
        with patch.object(swarm.State, 'get_worker', return_value=None):
            with patch.object(swarm.State, 'add_worker') as mock_add_worker:
                with patch('swarm.create_tmux_window'):
                    with patch('swarm.get_default_session_name', return_value='swarm-test'):
                        with patch('builtins.print') as mock_print:
                            swarm.cmd_spawn(args)

        # Verify worker was added
        mock_add_worker.assert_called_once()
        # Verify success message
        all_calls = [str(call) for call in mock_print.call_args_list]
        self.assertTrue(any('spawned' in call for call in all_calls))

    def test_no_ralph_skips_validation(self):
        """Test spawn without --ralph skips ralph validation."""
        args = Namespace(
            name='test-worker',
            ralph=False,
            prompt_file=None,  # Would fail if ralph validation ran
            max_iterations=None,  # Would fail if ralph validation ran
            tmux=True,
            worktree=False,
            session=None,
            tmux_socket=None,
            branch=None,
            worktree_dir=None,
            tags=[],
            env=[],
            cwd=None,
            ready_wait=False,
            ready_timeout=120,
            cmd=['--', 'echo', 'test']
        )

        # Mock State and other functions to prevent actual spawning
        with patch.object(swarm.State, 'get_worker', return_value=None):
            with patch.object(swarm.State, 'add_worker'):
                with patch('swarm.create_tmux_window'):
                    with patch('swarm.get_default_session_name', return_value='swarm-test'):
                        with patch('builtins.print'):
                            # Should not raise - ralph validation is skipped
                            swarm.cmd_spawn(args)


class TestRalphSpawnScenarios(unittest.TestCase):
    """Scenario-based tests for ralph spawn from ralph-loop.md spec."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.original_cwd = os.getcwd()
        os.chdir(self.temp_dir)
        # Create a test prompt file
        Path('PROMPT.md').write_text('study specs/README.md\n')

    def tearDown(self):
        """Clean up test fixtures."""
        os.chdir(self.original_cwd)
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_scenario_ralph_without_prompt_file_error(self):
        """Scenario: Ralph without prompt-file shows error.

        Given: User specifies --ralph without --prompt-file
        When: swarm spawn --name agent --ralph --max-iterations 10 -- claude
        Then:
          - Exit code 1
          - Error: "swarm: error: --ralph requires --prompt-file"
        """
        args = Namespace(
            name='agent',
            ralph=True,
            prompt_file=None,
            max_iterations=10,
            tmux=False,
            worktree=False,
            session=None,
            tmux_socket=None,
            branch=None,
            worktree_dir=None,
            tags=[],
            env=[],
            cwd=None,
            ready_wait=False,
            ready_timeout=120,
            cmd=['--', 'claude']
        )

        with patch('builtins.print') as mock_print:
            with self.assertRaises(SystemExit) as ctx:
                swarm.cmd_spawn(args)

        self.assertEqual(ctx.exception.code, 1)
        error_calls = [str(call) for call in mock_print.call_args_list]
        self.assertTrue(any('--ralph requires --prompt-file' in call for call in error_calls))

    def test_scenario_ralph_without_max_iterations_error(self):
        """Scenario: Ralph without max-iterations shows error.

        Given: User specifies --ralph without --max-iterations
        When: swarm spawn --name agent --ralph --prompt-file ./PROMPT.md -- claude
        Then:
          - Exit code 1
          - Error: "swarm: error: --ralph requires --max-iterations"
        """
        args = Namespace(
            name='agent',
            ralph=True,
            prompt_file='PROMPT.md',
            max_iterations=None,
            tmux=False,
            worktree=False,
            session=None,
            tmux_socket=None,
            branch=None,
            worktree_dir=None,
            tags=[],
            env=[],
            cwd=None,
            ready_wait=False,
            ready_timeout=120,
            cmd=['--', 'claude']
        )

        with patch('builtins.print') as mock_print:
            with self.assertRaises(SystemExit) as ctx:
                swarm.cmd_spawn(args)

        self.assertEqual(ctx.exception.code, 1)
        error_calls = [str(call) for call in mock_print.call_args_list]
        self.assertTrue(any('--ralph requires --max-iterations' in call for call in error_calls))

    def test_scenario_missing_prompt_file_error(self):
        """Scenario: Missing prompt file shows error.

        Given: --prompt-file ./missing.md specified
        When: swarm spawn --ralph --prompt-file ./missing.md --max-iterations 10 -- claude
        Then:
          - Exit code 1
          - Error: "swarm: error: prompt file not found: ./missing.md"
        """
        args = Namespace(
            name='agent',
            ralph=True,
            prompt_file='./missing.md',
            max_iterations=10,
            tmux=False,
            worktree=False,
            session=None,
            tmux_socket=None,
            branch=None,
            worktree_dir=None,
            tags=[],
            env=[],
            cwd=None,
            ready_wait=False,
            ready_timeout=120,
            cmd=['--', 'claude']
        )

        with patch('builtins.print') as mock_print:
            with self.assertRaises(SystemExit) as ctx:
                swarm.cmd_spawn(args)

        self.assertEqual(ctx.exception.code, 1)
        error_calls = [str(call) for call in mock_print.call_args_list]
        self.assertTrue(any('prompt file not found' in call for call in error_calls))

    def test_scenario_high_iteration_warning(self):
        """Scenario: High iteration warning.

        Given: User spawns with --max-iterations 100
        When: Command executed
        Then:
          - Warning: "swarm: warning: high iteration count (>50) may consume significant resources"
          - Worker still spawns successfully
        """
        args = Namespace(
            name='agent',
            ralph=True,
            prompt_file='PROMPT.md',
            max_iterations=100,
            tmux=False,
            worktree=False,
            session=None,
            tmux_socket=None,
            branch=None,
            worktree_dir=None,
            tags=[],
            env=[],
            cwd=None,
            ready_wait=False,
            ready_timeout=120,
            cmd=['--', 'claude']
        )

        with patch.object(swarm.State, 'get_worker', return_value=None):
            with patch.object(swarm.State, 'add_worker') as mock_add:
                with patch('swarm.create_tmux_window'):
                    with patch('swarm.get_default_session_name', return_value='swarm-test'):
                        with patch('builtins.print') as mock_print:
                            swarm.cmd_spawn(args)

        # Check warning was printed
        all_calls = [str(call) for call in mock_print.call_args_list]
        self.assertTrue(any('high iteration count' in call for call in all_calls))

        # Worker still spawns successfully
        mock_add.assert_called_once()

    def test_scenario_ralph_requires_tmux(self):
        """Scenario: Ralph requires tmux.

        Given: User attempts ralph without explicit tmux
        When: swarm spawn --name agent --ralph --prompt-file ./PROMPT.md --max-iterations 10 -- claude
        Then:
          - --tmux automatically enabled
          - Worker created in tmux mode
        """
        args = Namespace(
            name='agent',
            ralph=True,
            prompt_file='PROMPT.md',
            max_iterations=10,
            tmux=False,  # Not explicitly set
            worktree=False,
            session=None,
            tmux_socket=None,
            branch=None,
            worktree_dir=None,
            tags=[],
            env=[],
            cwd=None,
            ready_wait=False,
            ready_timeout=120,
            cmd=['--', 'claude']
        )

        with patch.object(swarm.State, 'get_worker', return_value=None):
            with patch.object(swarm.State, 'add_worker') as mock_add:
                with patch('swarm.create_tmux_window') as mock_tmux:
                    with patch('swarm.get_default_session_name', return_value='swarm-test'):
                        with patch('builtins.print'):
                            swarm.cmd_spawn(args)

        # Verify tmux window was created
        mock_tmux.assert_called_once()

        # Verify worker was added with tmux info
        call_args = mock_add.call_args[0][0]
        self.assertIsNotNone(call_args.tmux)


class TestRalphSpawnEdgeCases(unittest.TestCase):
    """Edge case tests for ralph spawn."""

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

    def test_prompt_file_absolute_path(self):
        """Test prompt file with absolute path works."""
        # Create prompt file with absolute path
        prompt_path = Path(self.temp_dir) / 'prompt.md'
        prompt_path.write_text('test content')

        args = Namespace(
            name='test-worker',
            ralph=True,
            prompt_file=str(prompt_path),  # Absolute path
            max_iterations=10,
            tmux=False,
            worktree=False,
            session=None,
            tmux_socket=None,
            branch=None,
            worktree_dir=None,
            tags=[],
            env=[],
            cwd=None,
            ready_wait=False,
            ready_timeout=120,
            cmd=['--', 'echo', 'test']
        )

        with patch.object(swarm.State, 'get_worker', return_value=None):
            with patch.object(swarm.State, 'add_worker'):
                with patch('swarm.create_tmux_window'):
                    with patch('swarm.get_default_session_name', return_value='swarm-test'):
                        with patch('builtins.print'):
                            # Should not raise
                            swarm.cmd_spawn(args)

    def test_prompt_file_relative_path(self):
        """Test prompt file with relative path works."""
        # Create prompt file with relative path
        Path('relative_prompt.md').write_text('test content')

        args = Namespace(
            name='test-worker',
            ralph=True,
            prompt_file='relative_prompt.md',  # Relative path
            max_iterations=10,
            tmux=False,
            worktree=False,
            session=None,
            tmux_socket=None,
            branch=None,
            worktree_dir=None,
            tags=[],
            env=[],
            cwd=None,
            ready_wait=False,
            ready_timeout=120,
            cmd=['--', 'echo', 'test']
        )

        with patch.object(swarm.State, 'get_worker', return_value=None):
            with patch.object(swarm.State, 'add_worker'):
                with patch('swarm.create_tmux_window'):
                    with patch('swarm.get_default_session_name', return_value='swarm-test'):
                        with patch('builtins.print'):
                            # Should not raise
                            swarm.cmd_spawn(args)

    def test_empty_prompt_file_allowed(self):
        """Test empty prompt file is allowed."""
        Path('empty.md').write_text('')  # Empty file

        args = Namespace(
            name='test-worker',
            ralph=True,
            prompt_file='empty.md',
            max_iterations=10,
            tmux=False,
            worktree=False,
            session=None,
            tmux_socket=None,
            branch=None,
            worktree_dir=None,
            tags=[],
            env=[],
            cwd=None,
            ready_wait=False,
            ready_timeout=120,
            cmd=['--', 'echo', 'test']
        )

        with patch.object(swarm.State, 'get_worker', return_value=None):
            with patch.object(swarm.State, 'add_worker'):
                with patch('swarm.create_tmux_window'):
                    with patch('swarm.get_default_session_name', return_value='swarm-test'):
                        with patch('builtins.print'):
                            # Should not raise - empty file is allowed
                            swarm.cmd_spawn(args)

    def test_max_iterations_exactly_50_no_warning(self):
        """Test max-iterations of exactly 50 does not trigger warning."""
        Path('prompt.md').write_text('test')

        args = Namespace(
            name='test-worker',
            ralph=True,
            prompt_file='prompt.md',
            max_iterations=50,  # Exactly 50, not > 50
            tmux=False,
            worktree=False,
            session=None,
            tmux_socket=None,
            branch=None,
            worktree_dir=None,
            tags=[],
            env=[],
            cwd=None,
            ready_wait=False,
            ready_timeout=120,
            cmd=['--', 'echo', 'test']
        )

        with patch.object(swarm.State, 'get_worker', return_value=None):
            with patch.object(swarm.State, 'add_worker'):
                with patch('swarm.create_tmux_window'):
                    with patch('swarm.get_default_session_name', return_value='swarm-test'):
                        with patch('builtins.print') as mock_print:
                            swarm.cmd_spawn(args)

        # No warning should be printed
        all_calls = [str(call) for call in mock_print.call_args_list]
        self.assertFalse(any('high iteration count' in call for call in all_calls))

    def test_max_iterations_51_triggers_warning(self):
        """Test max-iterations of 51 triggers warning."""
        Path('prompt.md').write_text('test')

        args = Namespace(
            name='test-worker',
            ralph=True,
            prompt_file='prompt.md',
            max_iterations=51,  # Just above threshold
            tmux=False,
            worktree=False,
            session=None,
            tmux_socket=None,
            branch=None,
            worktree_dir=None,
            tags=[],
            env=[],
            cwd=None,
            ready_wait=False,
            ready_timeout=120,
            cmd=['--', 'echo', 'test']
        )

        with patch.object(swarm.State, 'get_worker', return_value=None):
            with patch.object(swarm.State, 'add_worker'):
                with patch('swarm.create_tmux_window'):
                    with patch('swarm.get_default_session_name', return_value='swarm-test'):
                        with patch('builtins.print') as mock_print:
                            swarm.cmd_spawn(args)

        # Warning should be printed
        all_calls = [str(call) for call in mock_print.call_args_list]
        self.assertTrue(any('high iteration count' in call for call in all_calls))


if __name__ == "__main__":
    unittest.main()
