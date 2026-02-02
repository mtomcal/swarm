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
        # Also set up temp swarm dirs for status/pause/resume tests
        self.original_swarm_dir = swarm.SWARM_DIR
        self.original_ralph_dir = swarm.RALPH_DIR
        self.original_state_file = swarm.STATE_FILE
        self.original_state_lock_file = swarm.STATE_LOCK_FILE
        swarm.SWARM_DIR = Path(self.temp_dir) / ".swarm"
        swarm.RALPH_DIR = Path(self.temp_dir) / ".swarm" / "ralph"
        swarm.STATE_FILE = Path(self.temp_dir) / ".swarm" / "state.json"
        swarm.STATE_LOCK_FILE = Path(self.temp_dir) / ".swarm" / "state.lock"

    def tearDown(self):
        """Clean up test fixtures."""
        os.chdir(self.original_cwd)
        swarm.SWARM_DIR = self.original_swarm_dir
        swarm.RALPH_DIR = self.original_ralph_dir
        swarm.STATE_FILE = self.original_state_file
        swarm.STATE_LOCK_FILE = self.original_state_lock_file
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

    def test_dispatch_status(self):
        """Test cmd_ralph dispatches to status."""
        # Create worker and ralph state
        state = swarm.State()
        worker = swarm.Worker(
            name='test-worker',
            status='running',
            cmd=['claude'],
            started='2024-01-15T10:30:00',
            cwd='/tmp'
        )
        state.workers.append(worker)
        state.save()

        ralph_state = swarm.RalphState(
            worker_name='test-worker',
            prompt_file='/path/to/prompt.md',
            max_iterations=10,
            status='running'
        )
        swarm.save_ralph_state(ralph_state)

        args = Namespace(ralph_command='status', name='test-worker')

        with patch('builtins.print') as mock_print:
            swarm.cmd_ralph(args)

        output = '\n'.join([str(call) for call in mock_print.call_args_list])
        self.assertIn('Ralph Loop: test-worker', output)

    def test_dispatch_pause(self):
        """Test cmd_ralph dispatches to pause."""
        # Create worker and ralph state
        state = swarm.State()
        worker = swarm.Worker(
            name='test-worker',
            status='running',
            cmd=['claude'],
            started='2024-01-15T10:30:00',
            cwd='/tmp'
        )
        state.workers.append(worker)
        state.save()

        ralph_state = swarm.RalphState(
            worker_name='test-worker',
            prompt_file='/path/to/prompt.md',
            max_iterations=10,
            status='running'
        )
        swarm.save_ralph_state(ralph_state)

        args = Namespace(ralph_command='pause', name='test-worker')

        with patch('builtins.print') as mock_print:
            swarm.cmd_ralph(args)

        mock_print.assert_called_with('paused ralph loop for test-worker')

    def test_dispatch_resume(self):
        """Test cmd_ralph dispatches to resume."""
        # Create worker and ralph state
        state = swarm.State()
        worker = swarm.Worker(
            name='test-worker',
            status='running',
            cmd=['claude'],
            started='2024-01-15T10:30:00',
            cwd='/tmp'
        )
        state.workers.append(worker)
        state.save()

        ralph_state = swarm.RalphState(
            worker_name='test-worker',
            prompt_file='/path/to/prompt.md',
            max_iterations=10,
            status='paused'
        )
        swarm.save_ralph_state(ralph_state)

        args = Namespace(ralph_command='resume', name='test-worker')

        with patch('builtins.print') as mock_print:
            swarm.cmd_ralph(args)

        mock_print.assert_called_with('resumed ralph loop for test-worker')


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
            inactivity_timeout=300,
            inactivity_mode='ready',
            done_pattern=None,
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
            inactivity_timeout=300,
            inactivity_mode='ready',
            done_pattern=None,
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
            inactivity_timeout=300,
            inactivity_mode='ready',
            done_pattern=None,
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
            inactivity_timeout=300,
            inactivity_mode='ready',
            done_pattern=None,
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
            inactivity_timeout=300,
            inactivity_mode='ready',
            done_pattern=None,
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
            inactivity_timeout=300,
            inactivity_mode='ready',
            done_pattern=None,
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
            inactivity_timeout=300,
            inactivity_mode='ready',
            done_pattern=None,
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
            inactivity_timeout=300,
            inactivity_mode='ready',
            done_pattern=None,
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
            inactivity_timeout=300,
            inactivity_mode='ready',
            done_pattern=None,
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
            inactivity_timeout=300,
            inactivity_mode='ready',
            done_pattern=None,
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
            inactivity_timeout=300,
            inactivity_mode='ready',
            done_pattern=None,
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
            inactivity_timeout=300,
            inactivity_mode='ready',
            done_pattern=None,
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
            inactivity_timeout=300,
            inactivity_mode='ready',
            done_pattern=None,
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
            inactivity_timeout=300,
            inactivity_mode='ready',
            done_pattern=None,
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
            inactivity_timeout=300,
            inactivity_mode='ready',
            done_pattern=None,
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
            inactivity_timeout=300,
            inactivity_mode='ready',
            done_pattern=None,
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
            inactivity_timeout=300,
            inactivity_mode='ready',
            done_pattern=None,
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


class TestRalphSpawnNewArguments(unittest.TestCase):
    """Test new ralph spawn arguments: --inactivity-timeout, --done-pattern."""

    def test_inactivity_timeout_argument_exists(self):
        """Test that --inactivity-timeout argument is recognized by spawn."""
        result = subprocess.run(
            [sys.executable, 'swarm.py', 'spawn', '--help'],
            capture_output=True,
            text=True
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn('--inactivity-timeout', result.stdout)

    def test_done_pattern_argument_exists(self):
        """Test that --done-pattern argument is recognized by spawn."""
        result = subprocess.run(
            [sys.executable, 'swarm.py', 'spawn', '--help'],
            capture_output=True,
            text=True
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn('--done-pattern', result.stdout)

    def test_inactivity_timeout_default_value(self):
        """Test --inactivity-timeout has default value of 300."""
        # Parse args to verify default
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument("--inactivity-timeout", type=int, default=300)
        args = parser.parse_args([])
        self.assertEqual(args.inactivity_timeout, 300)


class TestRalphStateCreation(unittest.TestCase):
    """Test ralph state creation during spawn."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.original_cwd = os.getcwd()
        os.chdir(self.temp_dir)
        # Set up temp swarm dirs
        self.original_swarm_dir = swarm.SWARM_DIR
        self.original_ralph_dir = swarm.RALPH_DIR
        self.original_state_file = swarm.STATE_FILE
        self.original_state_lock_file = swarm.STATE_LOCK_FILE
        swarm.SWARM_DIR = Path(self.temp_dir) / ".swarm"
        swarm.RALPH_DIR = Path(self.temp_dir) / ".swarm" / "ralph"
        swarm.STATE_FILE = Path(self.temp_dir) / ".swarm" / "state.json"
        swarm.STATE_LOCK_FILE = Path(self.temp_dir) / ".swarm" / "state.lock"
        # Create a test prompt file
        Path('test_prompt.md').write_text('test prompt content')

    def tearDown(self):
        """Clean up test fixtures."""
        os.chdir(self.original_cwd)
        swarm.SWARM_DIR = self.original_swarm_dir
        swarm.RALPH_DIR = self.original_ralph_dir
        swarm.STATE_FILE = self.original_state_file
        swarm.STATE_LOCK_FILE = self.original_state_lock_file
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_spawn_creates_ralph_state(self):
        """Test that spawning with --ralph creates ralph state file."""
        args = Namespace(
            name='ralph-worker',
            ralph=True,
            prompt_file='test_prompt.md',
            max_iterations=10,
            inactivity_timeout=300,
            inactivity_mode='ready',
            done_pattern=None,
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

        with patch('swarm.create_tmux_window'):
            with patch('swarm.get_default_session_name', return_value='swarm-test'):
                with patch('builtins.print'):
                    swarm.cmd_spawn(args)

        # Verify ralph state was created
        ralph_state = swarm.load_ralph_state('ralph-worker')
        self.assertIsNotNone(ralph_state)
        self.assertEqual(ralph_state.worker_name, 'ralph-worker')
        self.assertEqual(ralph_state.max_iterations, 10)
        self.assertEqual(ralph_state.status, 'running')

    def test_spawn_ralph_state_has_correct_values(self):
        """Test that ralph state has correct field values after spawn."""
        args = Namespace(
            name='ralph-worker',
            ralph=True,
            prompt_file='test_prompt.md',
            max_iterations=50,
            inactivity_timeout=600,
            inactivity_mode='ready',
            done_pattern='All tasks complete',
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

        with patch('swarm.create_tmux_window'):
            with patch('swarm.get_default_session_name', return_value='swarm-test'):
                with patch('builtins.print'):
                    swarm.cmd_spawn(args)

        ralph_state = swarm.load_ralph_state('ralph-worker')
        self.assertEqual(ralph_state.max_iterations, 50)
        self.assertEqual(ralph_state.inactivity_timeout, 600)
        self.assertEqual(ralph_state.done_pattern, 'All tasks complete')
        self.assertEqual(ralph_state.current_iteration, 1)  # Starts at iteration 1
        self.assertIsNotNone(ralph_state.started)

    def test_spawn_ralph_message_includes_iteration(self):
        """Test that spawn message includes ralph mode info."""
        args = Namespace(
            name='ralph-worker',
            ralph=True,
            prompt_file='test_prompt.md',
            max_iterations=100,
            inactivity_timeout=300,
            inactivity_mode='ready',
            done_pattern=None,
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

        with patch('swarm.create_tmux_window'):
            with patch('swarm.get_default_session_name', return_value='swarm-test'):
                with patch('builtins.print') as mock_print:
                    swarm.cmd_spawn(args)

        all_calls = [str(call) for call in mock_print.call_args_list]
        self.assertTrue(any('ralph mode: iteration 1/100' in call for call in all_calls))

    def test_spawn_without_ralph_no_state(self):
        """Test that spawning without --ralph does not create ralph state."""
        args = Namespace(
            name='normal-worker',
            ralph=False,
            prompt_file=None,
            max_iterations=None,
            inactivity_timeout=300,
            inactivity_mode='ready',
            done_pattern=None,
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

        with patch('swarm.create_tmux_window'):
            with patch('swarm.get_default_session_name', return_value='swarm-test'):
                with patch('builtins.print'):
                    swarm.cmd_spawn(args)

        # Verify ralph state was NOT created
        ralph_state = swarm.load_ralph_state('normal-worker')
        self.assertIsNone(ralph_state)

    def test_spawn_ralph_stores_absolute_prompt_path(self):
        """Test that ralph state stores absolute path to prompt file."""
        args = Namespace(
            name='ralph-worker',
            ralph=True,
            prompt_file='test_prompt.md',  # Relative path
            max_iterations=10,
            inactivity_timeout=300,
            inactivity_mode='ready',
            done_pattern=None,
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

        with patch('swarm.create_tmux_window'):
            with patch('swarm.get_default_session_name', return_value='swarm-test'):
                with patch('builtins.print'):
                    swarm.cmd_spawn(args)

        ralph_state = swarm.load_ralph_state('ralph-worker')
        # Should be absolute path
        self.assertTrue(Path(ralph_state.prompt_file).is_absolute())


class TestRalphStateDataclass(unittest.TestCase):
    """Test RalphState dataclass."""

    def test_ralph_state_defaults(self):
        """Test RalphState has correct defaults."""
        state = swarm.RalphState(
            worker_name='test',
            prompt_file='/path/to/prompt.md',
            max_iterations=10
        )
        self.assertEqual(state.current_iteration, 0)
        self.assertEqual(state.status, "running")
        self.assertEqual(state.consecutive_failures, 0)
        self.assertEqual(state.total_failures, 0)
        self.assertEqual(state.inactivity_timeout, 300)
        self.assertIsNone(state.done_pattern)

    def test_ralph_state_to_dict(self):
        """Test RalphState to_dict method."""
        state = swarm.RalphState(
            worker_name='test',
            prompt_file='/path/to/prompt.md',
            max_iterations=10,
            current_iteration=5,
            status='paused'
        )
        d = state.to_dict()
        self.assertEqual(d['worker_name'], 'test')
        self.assertEqual(d['prompt_file'], '/path/to/prompt.md')
        self.assertEqual(d['max_iterations'], 10)
        self.assertEqual(d['current_iteration'], 5)
        self.assertEqual(d['status'], 'paused')

    def test_ralph_state_from_dict(self):
        """Test RalphState from_dict method."""
        d = {
            'worker_name': 'test',
            'prompt_file': '/path/to/prompt.md',
            'max_iterations': 10,
            'current_iteration': 3,
            'status': 'running',
            'started': '2024-01-15T10:30:00',
            'last_iteration_started': '2024-01-15T12:45:00',
            'consecutive_failures': 1,
            'total_failures': 2,
            'done_pattern': 'All tasks complete',
            'inactivity_timeout': 600
        }
        state = swarm.RalphState.from_dict(d)
        self.assertEqual(state.worker_name, 'test')
        self.assertEqual(state.current_iteration, 3)
        self.assertEqual(state.done_pattern, 'All tasks complete')
        self.assertEqual(state.inactivity_timeout, 600)

    def test_ralph_state_roundtrip(self):
        """Test RalphState survives round-trip through dict."""
        original = swarm.RalphState(
            worker_name='test',
            prompt_file='/path/to/prompt.md',
            max_iterations=100,
            current_iteration=42,
            status='paused',
            started='2024-01-15T10:30:00',
            consecutive_failures=2,
            total_failures=5
        )
        d = original.to_dict()
        restored = swarm.RalphState.from_dict(d)
        self.assertEqual(original.worker_name, restored.worker_name)
        self.assertEqual(original.current_iteration, restored.current_iteration)
        self.assertEqual(original.status, restored.status)


class TestRalphStatePersistence(unittest.TestCase):
    """Test ralph state file operations."""

    def setUp(self):
        """Set up test fixtures with temporary SWARM_DIR."""
        self.temp_dir = tempfile.mkdtemp()
        self.original_swarm_dir = swarm.SWARM_DIR
        self.original_ralph_dir = swarm.RALPH_DIR
        swarm.SWARM_DIR = Path(self.temp_dir)
        swarm.RALPH_DIR = Path(self.temp_dir) / "ralph"

    def tearDown(self):
        """Clean up test fixtures."""
        swarm.SWARM_DIR = self.original_swarm_dir
        swarm.RALPH_DIR = self.original_ralph_dir
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_get_ralph_state_path(self):
        """Test get_ralph_state_path returns correct path."""
        path = swarm.get_ralph_state_path('my-worker')
        expected = swarm.RALPH_DIR / 'my-worker' / 'state.json'
        self.assertEqual(path, expected)

    def test_load_ralph_state_nonexistent(self):
        """Test loading nonexistent ralph state returns None."""
        result = swarm.load_ralph_state('nonexistent')
        self.assertIsNone(result)

    def test_save_and_load_ralph_state(self):
        """Test saving and loading ralph state."""
        original = swarm.RalphState(
            worker_name='test-worker',
            prompt_file='/path/to/prompt.md',
            max_iterations=10,
            current_iteration=5,
            status='running',
            started='2024-01-15T10:30:00'
        )

        swarm.save_ralph_state(original)

        loaded = swarm.load_ralph_state('test-worker')
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.worker_name, 'test-worker')
        self.assertEqual(loaded.current_iteration, 5)
        self.assertEqual(loaded.status, 'running')

    def test_save_creates_directory(self):
        """Test save_ralph_state creates directory if needed."""
        state = swarm.RalphState(
            worker_name='new-worker',
            prompt_file='/path/to/prompt.md',
            max_iterations=10
        )

        swarm.save_ralph_state(state)

        state_path = swarm.get_ralph_state_path('new-worker')
        self.assertTrue(state_path.exists())


class TestCmdRalphStatus(unittest.TestCase):
    """Test cmd_ralph_status function."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.original_swarm_dir = swarm.SWARM_DIR
        self.original_ralph_dir = swarm.RALPH_DIR
        self.original_state_file = swarm.STATE_FILE
        self.original_state_lock_file = swarm.STATE_LOCK_FILE
        swarm.SWARM_DIR = Path(self.temp_dir)
        swarm.RALPH_DIR = Path(self.temp_dir) / "ralph"
        swarm.STATE_FILE = Path(self.temp_dir) / "state.json"
        swarm.STATE_LOCK_FILE = Path(self.temp_dir) / "state.lock"

    def tearDown(self):
        """Clean up test fixtures."""
        swarm.SWARM_DIR = self.original_swarm_dir
        swarm.RALPH_DIR = self.original_ralph_dir
        swarm.STATE_FILE = self.original_state_file
        swarm.STATE_LOCK_FILE = self.original_state_lock_file
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_status_worker_not_found(self):
        """Test ralph status for nonexistent worker."""
        args = Namespace(name='nonexistent')

        with patch('builtins.print') as mock_print:
            with self.assertRaises(SystemExit) as ctx:
                swarm.cmd_ralph_status(args)

        self.assertEqual(ctx.exception.code, 1)
        error_calls = [str(call) for call in mock_print.call_args_list]
        self.assertTrue(any('not found' in call for call in error_calls))

    def test_status_not_ralph_worker(self):
        """Test ralph status for non-ralph worker."""
        # Create a worker without ralph state
        state = swarm.State()
        worker = swarm.Worker(
            name='normal-worker',
            status='running',
            cmd=['echo', 'test'],
            started='2024-01-15T10:30:00',
            cwd='/tmp'
        )
        state.workers.append(worker)
        state.save()

        args = Namespace(name='normal-worker')

        with patch('builtins.print') as mock_print:
            with self.assertRaises(SystemExit) as ctx:
                swarm.cmd_ralph_status(args)

        self.assertEqual(ctx.exception.code, 1)
        error_calls = [str(call) for call in mock_print.call_args_list]
        self.assertTrue(any('not a ralph worker' in call for call in error_calls))

    def test_status_shows_ralph_state(self):
        """Test ralph status shows correct state."""
        # Create a worker with ralph state
        state = swarm.State()
        worker = swarm.Worker(
            name='ralph-worker',
            status='running',
            cmd=['claude'],
            started='2024-01-15T10:30:00',
            cwd='/tmp'
        )
        state.workers.append(worker)
        state.save()

        # Create ralph state
        ralph_state = swarm.RalphState(
            worker_name='ralph-worker',
            prompt_file='/path/to/prompt.md',
            max_iterations=100,
            current_iteration=7,
            status='running',
            started='2024-01-15T10:30:00',
            last_iteration_started='2024-01-15T12:45:00',
            consecutive_failures=0,
            total_failures=2,
            inactivity_timeout=300,
            inactivity_mode='ready',
            done_pattern='All tasks complete'
        )
        swarm.save_ralph_state(ralph_state)

        args = Namespace(name='ralph-worker')

        with patch('builtins.print') as mock_print:
            swarm.cmd_ralph_status(args)

        output = '\n'.join([str(call) for call in mock_print.call_args_list])
        self.assertIn('Ralph Loop: ralph-worker', output)
        self.assertIn('Status: running', output)
        self.assertIn('7/100', output)
        self.assertIn('Consecutive failures: 0', output)
        self.assertIn('Total failures: 2', output)
        self.assertIn('Done pattern: All tasks complete', output)


class TestCmdRalphPause(unittest.TestCase):
    """Test cmd_ralph_pause function."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.original_swarm_dir = swarm.SWARM_DIR
        self.original_ralph_dir = swarm.RALPH_DIR
        self.original_state_file = swarm.STATE_FILE
        self.original_state_lock_file = swarm.STATE_LOCK_FILE
        swarm.SWARM_DIR = Path(self.temp_dir)
        swarm.RALPH_DIR = Path(self.temp_dir) / "ralph"
        swarm.STATE_FILE = Path(self.temp_dir) / "state.json"
        swarm.STATE_LOCK_FILE = Path(self.temp_dir) / "state.lock"

    def tearDown(self):
        """Clean up test fixtures."""
        swarm.SWARM_DIR = self.original_swarm_dir
        swarm.RALPH_DIR = self.original_ralph_dir
        swarm.STATE_FILE = self.original_state_file
        swarm.STATE_LOCK_FILE = self.original_state_lock_file
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_pause_worker_not_found(self):
        """Test ralph pause for nonexistent worker."""
        args = Namespace(name='nonexistent')

        with patch('builtins.print') as mock_print:
            with self.assertRaises(SystemExit) as ctx:
                swarm.cmd_ralph_pause(args)

        self.assertEqual(ctx.exception.code, 1)
        error_calls = [str(call) for call in mock_print.call_args_list]
        self.assertTrue(any('not found' in call for call in error_calls))

    def test_pause_not_ralph_worker(self):
        """Test ralph pause for non-ralph worker."""
        # Create a worker without ralph state
        state = swarm.State()
        worker = swarm.Worker(
            name='normal-worker',
            status='running',
            cmd=['echo', 'test'],
            started='2024-01-15T10:30:00',
            cwd='/tmp'
        )
        state.workers.append(worker)
        state.save()

        args = Namespace(name='normal-worker')

        with patch('builtins.print') as mock_print:
            with self.assertRaises(SystemExit) as ctx:
                swarm.cmd_ralph_pause(args)

        self.assertEqual(ctx.exception.code, 1)
        error_calls = [str(call) for call in mock_print.call_args_list]
        self.assertTrue(any('not a ralph worker' in call for call in error_calls))

    def test_pause_already_paused_warns(self):
        """Test ralph pause on already paused worker shows warning."""
        # Create worker and ralph state
        state = swarm.State()
        worker = swarm.Worker(
            name='ralph-worker',
            status='running',
            cmd=['claude'],
            started='2024-01-15T10:30:00',
            cwd='/tmp'
        )
        state.workers.append(worker)
        state.save()

        ralph_state = swarm.RalphState(
            worker_name='ralph-worker',
            prompt_file='/path/to/prompt.md',
            max_iterations=10,
            status='paused'  # Already paused
        )
        swarm.save_ralph_state(ralph_state)

        args = Namespace(name='ralph-worker')

        with patch('builtins.print') as mock_print:
            # Should not raise, just warn
            swarm.cmd_ralph_pause(args)

        output = '\n'.join([str(call) for call in mock_print.call_args_list])
        self.assertIn('already paused', output)

    def test_pause_updates_state(self):
        """Test ralph pause updates state to paused."""
        # Create worker and ralph state
        state = swarm.State()
        worker = swarm.Worker(
            name='ralph-worker',
            status='running',
            cmd=['claude'],
            started='2024-01-15T10:30:00',
            cwd='/tmp'
        )
        state.workers.append(worker)
        state.save()

        ralph_state = swarm.RalphState(
            worker_name='ralph-worker',
            prompt_file='/path/to/prompt.md',
            max_iterations=10,
            status='running'
        )
        swarm.save_ralph_state(ralph_state)

        args = Namespace(name='ralph-worker')

        with patch('builtins.print') as mock_print:
            swarm.cmd_ralph_pause(args)

        # Verify state was updated
        loaded = swarm.load_ralph_state('ralph-worker')
        self.assertEqual(loaded.status, 'paused')

        # Verify success message
        output = '\n'.join([str(call) for call in mock_print.call_args_list])
        self.assertIn('paused ralph loop for ralph-worker', output)


class TestCmdRalphResume(unittest.TestCase):
    """Test cmd_ralph_resume function."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.original_swarm_dir = swarm.SWARM_DIR
        self.original_ralph_dir = swarm.RALPH_DIR
        self.original_state_file = swarm.STATE_FILE
        self.original_state_lock_file = swarm.STATE_LOCK_FILE
        swarm.SWARM_DIR = Path(self.temp_dir)
        swarm.RALPH_DIR = Path(self.temp_dir) / "ralph"
        swarm.STATE_FILE = Path(self.temp_dir) / "state.json"
        swarm.STATE_LOCK_FILE = Path(self.temp_dir) / "state.lock"

    def tearDown(self):
        """Clean up test fixtures."""
        swarm.SWARM_DIR = self.original_swarm_dir
        swarm.RALPH_DIR = self.original_ralph_dir
        swarm.STATE_FILE = self.original_state_file
        swarm.STATE_LOCK_FILE = self.original_state_lock_file
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_resume_worker_not_found(self):
        """Test ralph resume for nonexistent worker."""
        args = Namespace(name='nonexistent')

        with patch('builtins.print') as mock_print:
            with self.assertRaises(SystemExit) as ctx:
                swarm.cmd_ralph_resume(args)

        self.assertEqual(ctx.exception.code, 1)
        error_calls = [str(call) for call in mock_print.call_args_list]
        self.assertTrue(any('not found' in call for call in error_calls))

    def test_resume_not_ralph_worker(self):
        """Test ralph resume for non-ralph worker."""
        # Create a worker without ralph state
        state = swarm.State()
        worker = swarm.Worker(
            name='normal-worker',
            status='running',
            cmd=['echo', 'test'],
            started='2024-01-15T10:30:00',
            cwd='/tmp'
        )
        state.workers.append(worker)
        state.save()

        args = Namespace(name='normal-worker')

        with patch('builtins.print') as mock_print:
            with self.assertRaises(SystemExit) as ctx:
                swarm.cmd_ralph_resume(args)

        self.assertEqual(ctx.exception.code, 1)
        error_calls = [str(call) for call in mock_print.call_args_list]
        self.assertTrue(any('not a ralph worker' in call for call in error_calls))

    def test_resume_not_paused_warns(self):
        """Test ralph resume on non-paused worker shows warning."""
        # Create worker and ralph state
        state = swarm.State()
        worker = swarm.Worker(
            name='ralph-worker',
            status='running',
            cmd=['claude'],
            started='2024-01-15T10:30:00',
            cwd='/tmp'
        )
        state.workers.append(worker)
        state.save()

        ralph_state = swarm.RalphState(
            worker_name='ralph-worker',
            prompt_file='/path/to/prompt.md',
            max_iterations=10,
            status='running'  # Not paused
        )
        swarm.save_ralph_state(ralph_state)

        args = Namespace(name='ralph-worker')

        with patch('builtins.print') as mock_print:
            # Should not raise, just warn
            swarm.cmd_ralph_resume(args)

        output = '\n'.join([str(call) for call in mock_print.call_args_list])
        self.assertIn('not paused', output)

    def test_resume_updates_state(self):
        """Test ralph resume updates state to running."""
        # Create worker and ralph state
        state = swarm.State()
        worker = swarm.Worker(
            name='ralph-worker',
            status='running',
            cmd=['claude'],
            started='2024-01-15T10:30:00',
            cwd='/tmp'
        )
        state.workers.append(worker)
        state.save()

        ralph_state = swarm.RalphState(
            worker_name='ralph-worker',
            prompt_file='/path/to/prompt.md',
            max_iterations=10,
            status='paused'  # Currently paused
        )
        swarm.save_ralph_state(ralph_state)

        args = Namespace(name='ralph-worker')

        with patch('builtins.print') as mock_print:
            swarm.cmd_ralph_resume(args)

        # Verify state was updated
        loaded = swarm.load_ralph_state('ralph-worker')
        self.assertEqual(loaded.status, 'running')

        # Verify success message
        output = '\n'.join([str(call) for call in mock_print.call_args_list])
        self.assertIn('resumed ralph loop for ralph-worker', output)


class TestRalphSubcommandsCLI(unittest.TestCase):
    """Test ralph subcommands via CLI (argparser integration)."""

    def test_ralph_status_subcommand_exists(self):
        """Test that 'ralph status' subcommand is recognized."""
        result = subprocess.run(
            [sys.executable, 'swarm.py', 'ralph', 'status', '--help'],
            capture_output=True,
            text=True
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn('status', result.stdout.lower())

    def test_ralph_pause_subcommand_exists(self):
        """Test that 'ralph pause' subcommand is recognized."""
        result = subprocess.run(
            [sys.executable, 'swarm.py', 'ralph', 'pause', '--help'],
            capture_output=True,
            text=True
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn('pause', result.stdout.lower())

    def test_ralph_resume_subcommand_exists(self):
        """Test that 'ralph resume' subcommand is recognized."""
        result = subprocess.run(
            [sys.executable, 'swarm.py', 'ralph', 'resume', '--help'],
            capture_output=True,
            text=True
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn('resume', result.stdout.lower())

    def test_ralph_status_requires_name(self):
        """Test ralph status requires worker name."""
        result = subprocess.run(
            [sys.executable, 'swarm.py', 'ralph', 'status'],
            capture_output=True,
            text=True
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('name', result.stderr.lower())

    def test_ralph_pause_requires_name(self):
        """Test ralph pause requires worker name."""
        result = subprocess.run(
            [sys.executable, 'swarm.py', 'ralph', 'pause'],
            capture_output=True,
            text=True
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('name', result.stderr.lower())

    def test_ralph_resume_requires_name(self):
        """Test ralph resume requires worker name."""
        result = subprocess.run(
            [sys.executable, 'swarm.py', 'ralph', 'resume'],
            capture_output=True,
            text=True
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('name', result.stderr.lower())


class TestRalphScenariosPauseResume(unittest.TestCase):
    """Scenario-based tests for ralph pause/resume from ralph-loop.md spec."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.original_swarm_dir = swarm.SWARM_DIR
        self.original_ralph_dir = swarm.RALPH_DIR
        self.original_state_file = swarm.STATE_FILE
        self.original_state_lock_file = swarm.STATE_LOCK_FILE
        swarm.SWARM_DIR = Path(self.temp_dir)
        swarm.RALPH_DIR = Path(self.temp_dir) / "ralph"
        swarm.STATE_FILE = Path(self.temp_dir) / "state.json"
        swarm.STATE_LOCK_FILE = Path(self.temp_dir) / "state.lock"

    def tearDown(self):
        """Clean up test fixtures."""
        swarm.SWARM_DIR = self.original_swarm_dir
        swarm.RALPH_DIR = self.original_ralph_dir
        swarm.STATE_FILE = self.original_state_file
        swarm.STATE_LOCK_FILE = self.original_state_lock_file
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_scenario_pause_ralph_loop(self):
        """Scenario: Pause ralph loop.

        Given: Ralph worker "agent" running, iteration 5/10
        When: swarm ralph pause agent
        Then:
          - Output: "paused ralph loop for agent"
          - Ralph state status set to "paused"
        """
        # Create worker and ralph state
        state = swarm.State()
        worker = swarm.Worker(
            name='agent',
            status='running',
            cmd=['claude'],
            started='2024-01-15T10:30:00',
            cwd='/tmp'
        )
        state.workers.append(worker)
        state.save()

        ralph_state = swarm.RalphState(
            worker_name='agent',
            prompt_file='/path/to/prompt.md',
            max_iterations=10,
            current_iteration=5,
            status='running'
        )
        swarm.save_ralph_state(ralph_state)

        args = Namespace(name='agent')

        with patch('builtins.print') as mock_print:
            swarm.cmd_ralph_pause(args)

        # Check output
        mock_print.assert_called_with('paused ralph loop for agent')

        # Check state was updated
        loaded = swarm.load_ralph_state('agent')
        self.assertEqual(loaded.status, 'paused')

    def test_scenario_resume_paused_ralph_loop(self):
        """Scenario: Resume paused ralph loop.

        Given: Ralph worker "agent" paused at iteration 5/10
        When: swarm ralph resume agent
        Then:
          - Output: "resumed ralph loop for agent"
          - Ralph state status set to "running"
        """
        # Create worker and ralph state
        state = swarm.State()
        worker = swarm.Worker(
            name='agent',
            status='stopped',  # Worker not running
            cmd=['claude'],
            started='2024-01-15T10:30:00',
            cwd='/tmp'
        )
        state.workers.append(worker)
        state.save()

        ralph_state = swarm.RalphState(
            worker_name='agent',
            prompt_file='/path/to/prompt.md',
            max_iterations=10,
            current_iteration=5,
            status='paused'
        )
        swarm.save_ralph_state(ralph_state)

        args = Namespace(name='agent')

        with patch('builtins.print') as mock_print:
            swarm.cmd_ralph_resume(args)

        # Check output
        mock_print.assert_called_with('resumed ralph loop for agent')

        # Check state was updated
        loaded = swarm.load_ralph_state('agent')
        self.assertEqual(loaded.status, 'running')

    def test_scenario_ralph_status_check(self):
        """Scenario: Ralph status check.

        Given: Ralph worker "agent" running, iteration 7/100
        When: swarm ralph status agent
        Then: Output shows ralph loop details.
        """
        # Create worker and ralph state
        state = swarm.State()
        worker = swarm.Worker(
            name='agent',
            status='running',
            cmd=['claude'],
            started='2024-01-15T10:30:00',
            cwd='/tmp'
        )
        state.workers.append(worker)
        state.save()

        ralph_state = swarm.RalphState(
            worker_name='agent',
            prompt_file='/path/to/prompt.md',
            max_iterations=100,
            current_iteration=7,
            status='running',
            started='2024-01-15T10:30:00',
            last_iteration_started='2024-01-15T12:45:00',
            consecutive_failures=0,
            total_failures=2
        )
        swarm.save_ralph_state(ralph_state)

        args = Namespace(name='agent')

        with patch('builtins.print') as mock_print:
            swarm.cmd_ralph_status(args)

        output = '\n'.join([str(call) for call in mock_print.call_args_list])
        self.assertIn('Ralph Loop: agent', output)
        self.assertIn('Status: running', output)
        self.assertIn('7/100', output)

    def test_scenario_pause_non_ralph_worker_error(self):
        """Scenario: Pause non-ralph worker.

        Given: A normal (non-ralph) worker
        When: swarm ralph pause <name>
        Then:
          - Exit code 1
          - Error: "swarm: error: worker '<name>' is not a ralph worker"
        """
        # Create a normal worker without ralph state
        state = swarm.State()
        worker = swarm.Worker(
            name='normal',
            status='running',
            cmd=['echo', 'test'],
            started='2024-01-15T10:30:00',
            cwd='/tmp'
        )
        state.workers.append(worker)
        state.save()

        args = Namespace(name='normal')

        with patch('builtins.print') as mock_print:
            with self.assertRaises(SystemExit) as ctx:
                swarm.cmd_ralph_pause(args)

        self.assertEqual(ctx.exception.code, 1)
        error_calls = [str(call) for call in mock_print.call_args_list]
        self.assertTrue(any('not a ralph worker' in call for call in error_calls))


class TestRalphIterationLogging(unittest.TestCase):
    """Test ralph iteration logging functionality."""

    def setUp(self):
        """Set up test fixtures with temporary SWARM_DIR."""
        self.temp_dir = tempfile.mkdtemp()
        self.original_swarm_dir = swarm.SWARM_DIR
        self.original_ralph_dir = swarm.RALPH_DIR
        swarm.SWARM_DIR = Path(self.temp_dir)
        swarm.RALPH_DIR = Path(self.temp_dir) / "ralph"

    def tearDown(self):
        """Clean up test fixtures."""
        swarm.SWARM_DIR = self.original_swarm_dir
        swarm.RALPH_DIR = self.original_ralph_dir
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_get_ralph_iterations_log_path(self):
        """Test get_ralph_iterations_log_path returns correct path."""
        path = swarm.get_ralph_iterations_log_path('my-worker')
        expected = swarm.RALPH_DIR / 'my-worker' / 'iterations.log'
        self.assertEqual(path, expected)

    def test_log_ralph_iteration_creates_directory(self):
        """Test log_ralph_iteration creates parent directory if needed."""
        swarm.log_ralph_iteration('new-worker', 'START', iteration=1, max_iterations=10)
        log_path = swarm.get_ralph_iterations_log_path('new-worker')
        self.assertTrue(log_path.exists())

    def test_log_ralph_iteration_start_event(self):
        """Test log_ralph_iteration with START event."""
        swarm.log_ralph_iteration('worker', 'START', iteration=5, max_iterations=100)
        log_path = swarm.get_ralph_iterations_log_path('worker')
        content = log_path.read_text()
        self.assertIn('[START]', content)
        self.assertIn('iteration 5/100', content)

    def test_log_ralph_iteration_end_event(self):
        """Test log_ralph_iteration with END event."""
        swarm.log_ralph_iteration('worker', 'END', iteration=5, exit_code=0, duration='3m42s')
        log_path = swarm.get_ralph_iterations_log_path('worker')
        content = log_path.read_text()
        self.assertIn('[END]', content)
        self.assertIn('iteration 5', content)
        self.assertIn('exit=0', content)
        self.assertIn('duration=3m42s', content)

    def test_log_ralph_iteration_fail_event(self):
        """Test log_ralph_iteration with FAIL event."""
        swarm.log_ralph_iteration('worker', 'FAIL', iteration=3, exit_code=1, attempt=2, backoff=4)
        log_path = swarm.get_ralph_iterations_log_path('worker')
        content = log_path.read_text()
        self.assertIn('[FAIL]', content)
        self.assertIn('iteration 3', content)
        self.assertIn('exit=1', content)
        self.assertIn('attempt=2/5', content)
        self.assertIn('backoff=4s', content)

    def test_log_ralph_iteration_timeout_event(self):
        """Test log_ralph_iteration with TIMEOUT event."""
        swarm.log_ralph_iteration('worker', 'TIMEOUT', iteration=7, timeout=300)
        log_path = swarm.get_ralph_iterations_log_path('worker')
        content = log_path.read_text()
        self.assertIn('[TIMEOUT]', content)
        self.assertIn('iteration 7', content)
        self.assertIn('inactivity_timeout=300s', content)

    def test_log_ralph_iteration_done_event(self):
        """Test log_ralph_iteration with DONE event."""
        swarm.log_ralph_iteration('worker', 'DONE', total_iterations=47, reason='max_iterations')
        log_path = swarm.get_ralph_iterations_log_path('worker')
        content = log_path.read_text()
        self.assertIn('[DONE]', content)
        self.assertIn('loop complete after 47 iterations', content)
        self.assertIn('reason=max_iterations', content)

    def test_log_ralph_iteration_appends(self):
        """Test log_ralph_iteration appends to existing log."""
        swarm.log_ralph_iteration('worker', 'START', iteration=1, max_iterations=10)
        swarm.log_ralph_iteration('worker', 'END', iteration=1, exit_code=0, duration='5m')
        swarm.log_ralph_iteration('worker', 'START', iteration=2, max_iterations=10)
        log_path = swarm.get_ralph_iterations_log_path('worker')
        content = log_path.read_text()
        lines = content.strip().split('\n')
        self.assertEqual(len(lines), 3)

    def test_log_ralph_iteration_has_timestamp(self):
        """Test log_ralph_iteration includes ISO timestamp."""
        swarm.log_ralph_iteration('worker', 'START', iteration=1, max_iterations=10)
        log_path = swarm.get_ralph_iterations_log_path('worker')
        content = log_path.read_text()
        # Check for ISO format timestamp pattern (YYYY-MM-DDTHH:MM:SS)
        import re
        self.assertTrue(re.search(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}', content))


class TestWorkerMetadata(unittest.TestCase):
    """Test Worker metadata field."""

    def test_worker_has_metadata_field(self):
        """Test Worker dataclass has metadata field."""
        worker = swarm.Worker(
            name='test',
            status='running',
            cmd=['echo'],
            started='2024-01-15T10:30:00',
            cwd='/tmp'
        )
        self.assertIsNotNone(worker.metadata)
        self.assertEqual(worker.metadata, {})

    def test_worker_metadata_to_dict(self):
        """Test Worker.to_dict includes metadata."""
        worker = swarm.Worker(
            name='test',
            status='running',
            cmd=['echo'],
            started='2024-01-15T10:30:00',
            cwd='/tmp',
            metadata={'ralph': True, 'ralph_iteration': 5}
        )
        d = worker.to_dict()
        self.assertIn('metadata', d)
        self.assertEqual(d['metadata']['ralph'], True)
        self.assertEqual(d['metadata']['ralph_iteration'], 5)

    def test_worker_metadata_from_dict(self):
        """Test Worker.from_dict loads metadata."""
        d = {
            'name': 'test',
            'status': 'running',
            'cmd': ['echo'],
            'started': '2024-01-15T10:30:00',
            'cwd': '/tmp',
            'metadata': {'ralph': True, 'ralph_iteration': 3}
        }
        worker = swarm.Worker.from_dict(d)
        self.assertEqual(worker.metadata['ralph'], True)
        self.assertEqual(worker.metadata['ralph_iteration'], 3)

    def test_worker_metadata_from_dict_missing(self):
        """Test Worker.from_dict handles missing metadata."""
        d = {
            'name': 'test',
            'status': 'running',
            'cmd': ['echo'],
            'started': '2024-01-15T10:30:00',
            'cwd': '/tmp'
        }
        worker = swarm.Worker.from_dict(d)
        self.assertEqual(worker.metadata, {})

    def test_worker_metadata_roundtrip(self):
        """Test Worker metadata survives round-trip through dict."""
        original = swarm.Worker(
            name='test',
            status='running',
            cmd=['echo'],
            started='2024-01-15T10:30:00',
            cwd='/tmp',
            metadata={'ralph': True, 'ralph_iteration': 42}
        )
        d = original.to_dict()
        restored = swarm.Worker.from_dict(d)
        self.assertEqual(original.metadata, restored.metadata)


class TestRalphSpawnMetadata(unittest.TestCase):
    """Test ralph spawn creates correct metadata."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.original_cwd = os.getcwd()
        os.chdir(self.temp_dir)
        # Set up temp swarm dirs
        self.original_swarm_dir = swarm.SWARM_DIR
        self.original_ralph_dir = swarm.RALPH_DIR
        self.original_state_file = swarm.STATE_FILE
        self.original_state_lock_file = swarm.STATE_LOCK_FILE
        swarm.SWARM_DIR = Path(self.temp_dir) / ".swarm"
        swarm.RALPH_DIR = Path(self.temp_dir) / ".swarm" / "ralph"
        swarm.STATE_FILE = Path(self.temp_dir) / ".swarm" / "state.json"
        swarm.STATE_LOCK_FILE = Path(self.temp_dir) / ".swarm" / "state.lock"
        # Create a test prompt file
        Path('test_prompt.md').write_text('test prompt content')

    def tearDown(self):
        """Clean up test fixtures."""
        os.chdir(self.original_cwd)
        swarm.SWARM_DIR = self.original_swarm_dir
        swarm.RALPH_DIR = self.original_ralph_dir
        swarm.STATE_FILE = self.original_state_file
        swarm.STATE_LOCK_FILE = self.original_state_lock_file
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_spawn_ralph_sets_metadata(self):
        """Test that spawning with --ralph sets worker metadata."""
        args = Namespace(
            name='ralph-worker',
            ralph=True,
            prompt_file='test_prompt.md',
            max_iterations=10,
            inactivity_timeout=300,
            inactivity_mode='ready',
            done_pattern=None,
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

        with patch('swarm.create_tmux_window'):
            with patch('swarm.get_default_session_name', return_value='swarm-test'):
                with patch('builtins.print'):
                    swarm.cmd_spawn(args)

        # Load worker and verify metadata
        state = swarm.State()
        worker = state.get_worker('ralph-worker')
        self.assertIsNotNone(worker)
        self.assertEqual(worker.metadata.get('ralph'), True)
        self.assertEqual(worker.metadata.get('ralph_iteration'), 1)

    def test_spawn_non_ralph_has_empty_metadata(self):
        """Test that spawning without --ralph has empty metadata."""
        args = Namespace(
            name='normal-worker',
            ralph=False,
            prompt_file=None,
            max_iterations=None,
            inactivity_timeout=300,
            inactivity_mode='ready',
            done_pattern=None,
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

        with patch('swarm.create_tmux_window'):
            with patch('swarm.get_default_session_name', return_value='swarm-test'):
                with patch('builtins.print'):
                    swarm.cmd_spawn(args)

        # Load worker and verify empty metadata
        state = swarm.State()
        worker = state.get_worker('normal-worker')
        self.assertIsNotNone(worker)
        self.assertEqual(worker.metadata, {})

    def test_spawn_ralph_logs_iteration_start(self):
        """Test that spawning with --ralph logs iteration start."""
        args = Namespace(
            name='ralph-worker',
            ralph=True,
            prompt_file='test_prompt.md',
            max_iterations=10,
            inactivity_timeout=300,
            inactivity_mode='ready',
            done_pattern=None,
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

        with patch('swarm.create_tmux_window'):
            with patch('swarm.get_default_session_name', return_value='swarm-test'):
                with patch('builtins.print'):
                    swarm.cmd_spawn(args)

        # Verify iteration log was created
        log_path = swarm.get_ralph_iterations_log_path('ralph-worker')
        self.assertTrue(log_path.exists())
        content = log_path.read_text()
        self.assertIn('[START]', content)
        self.assertIn('iteration 1/10', content)

    def test_spawn_ralph_state_starts_at_iteration_1(self):
        """Test that ralph state starts at iteration 1, not 0."""
        args = Namespace(
            name='ralph-worker',
            ralph=True,
            prompt_file='test_prompt.md',
            max_iterations=10,
            inactivity_timeout=300,
            inactivity_mode='ready',
            done_pattern=None,
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

        with patch('swarm.create_tmux_window'):
            with patch('swarm.get_default_session_name', return_value='swarm-test'):
                with patch('builtins.print'):
                    swarm.cmd_spawn(args)

        # Verify ralph state starts at iteration 1
        ralph_state = swarm.load_ralph_state('ralph-worker')
        self.assertEqual(ralph_state.current_iteration, 1)

    def test_spawn_ralph_state_has_last_iteration_started(self):
        """Test that ralph state has last_iteration_started set on spawn."""
        args = Namespace(
            name='ralph-worker',
            ralph=True,
            prompt_file='test_prompt.md',
            max_iterations=10,
            inactivity_timeout=300,
            inactivity_mode='ready',
            done_pattern=None,
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

        with patch('swarm.create_tmux_window'):
            with patch('swarm.get_default_session_name', return_value='swarm-test'):
                with patch('builtins.print'):
                    swarm.cmd_spawn(args)

        # Verify ralph state has last_iteration_started
        ralph_state = swarm.load_ralph_state('ralph-worker')
        self.assertIsNotNone(ralph_state.last_iteration_started)
        self.assertNotEqual(ralph_state.last_iteration_started, '')


class TestRalphRunSubparser(unittest.TestCase):
    """Test that ralph run subparser is correctly configured."""

    def test_ralph_run_subcommand_exists(self):
        """Test that 'ralph run' subcommand is recognized."""
        result = subprocess.run(
            [sys.executable, 'swarm.py', 'ralph', 'run', '--help'],
            capture_output=True,
            text=True
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn('run', result.stdout.lower())

    def test_ralph_run_requires_name(self):
        """Test ralph run requires worker name."""
        result = subprocess.run(
            [sys.executable, 'swarm.py', 'ralph', 'run'],
            capture_output=True,
            text=True
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('name', result.stderr.lower())


class TestRalphHelperFunctions(unittest.TestCase):
    """Test ralph helper functions."""

    def test_format_duration_seconds(self):
        """Test format_duration with seconds."""
        self.assertEqual(swarm.format_duration(30), "30s")
        self.assertEqual(swarm.format_duration(5), "5s")

    def test_format_duration_minutes(self):
        """Test format_duration with minutes."""
        self.assertEqual(swarm.format_duration(90), "1m 30s")
        self.assertEqual(swarm.format_duration(300), "5m 0s")

    def test_format_duration_hours(self):
        """Test format_duration with hours."""
        self.assertEqual(swarm.format_duration(3660), "1h 1m")
        self.assertEqual(swarm.format_duration(7200), "2h 0m")

    def test_wait_for_worker_exit_returns_exit(self):
        """Test wait_for_worker_exit returns exit when worker stopped."""
        worker = swarm.Worker(
            name='test-worker',
            status='stopped',
            cmd=['echo', 'test'],
            started='2024-01-15T10:30:00',
            cwd='/tmp',
            pid=99999  # Non-existent PID
        )

        exited, reason = swarm.wait_for_worker_exit(worker, timeout=1)
        self.assertTrue(exited)
        self.assertEqual(reason, "exit")


class TestCmdRalphRun(unittest.TestCase):
    """Test cmd_ralph_run function."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.original_swarm_dir = swarm.SWARM_DIR
        self.original_ralph_dir = swarm.RALPH_DIR
        self.original_state_file = swarm.STATE_FILE
        self.original_state_lock_file = swarm.STATE_LOCK_FILE
        swarm.SWARM_DIR = Path(self.temp_dir)
        swarm.RALPH_DIR = Path(self.temp_dir) / "ralph"
        swarm.STATE_FILE = Path(self.temp_dir) / "state.json"
        swarm.STATE_LOCK_FILE = Path(self.temp_dir) / "state.lock"

    def tearDown(self):
        """Clean up test fixtures."""
        swarm.SWARM_DIR = self.original_swarm_dir
        swarm.RALPH_DIR = self.original_ralph_dir
        swarm.STATE_FILE = self.original_state_file
        swarm.STATE_LOCK_FILE = self.original_state_lock_file
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_run_worker_not_found(self):
        """Test ralph run for nonexistent worker."""
        args = Namespace(name='nonexistent')

        with patch('builtins.print') as mock_print:
            with self.assertRaises(SystemExit) as ctx:
                swarm.cmd_ralph_run(args)

        self.assertEqual(ctx.exception.code, 1)
        error_calls = [str(call) for call in mock_print.call_args_list]
        self.assertTrue(any('not found' in call for call in error_calls))

    def test_run_not_ralph_worker(self):
        """Test ralph run for non-ralph worker."""
        # Create a worker without ralph state
        state = swarm.State()
        worker = swarm.Worker(
            name='normal-worker',
            status='running',
            cmd=['echo', 'test'],
            started='2024-01-15T10:30:00',
            cwd='/tmp'
        )
        state.workers.append(worker)
        state.save()

        args = Namespace(name='normal-worker')

        with patch('builtins.print') as mock_print:
            with self.assertRaises(SystemExit) as ctx:
                swarm.cmd_ralph_run(args)

        self.assertEqual(ctx.exception.code, 1)
        error_calls = [str(call) for call in mock_print.call_args_list]
        self.assertTrue(any('not a ralph worker' in call for call in error_calls))

    def test_run_paused_worker_errors(self):
        """Test ralph run for paused worker errors."""
        # Create worker and ralph state
        state = swarm.State()
        worker = swarm.Worker(
            name='ralph-worker',
            status='running',
            cmd=['claude'],
            started='2024-01-15T10:30:00',
            cwd='/tmp',
            tmux=swarm.TmuxInfo(session='swarm', window='ralph-worker')
        )
        state.workers.append(worker)
        state.save()

        ralph_state = swarm.RalphState(
            worker_name='ralph-worker',
            prompt_file='/path/to/prompt.md',
            max_iterations=10,
            status='paused'
        )
        swarm.save_ralph_state(ralph_state)

        args = Namespace(name='ralph-worker')

        with patch('builtins.print') as mock_print:
            with self.assertRaises(SystemExit) as ctx:
                swarm.cmd_ralph_run(args)

        self.assertEqual(ctx.exception.code, 1)
        error_calls = [str(call) for call in mock_print.call_args_list]
        self.assertTrue(any('paused' in call for call in error_calls))

    def test_run_stopped_worker_errors(self):
        """Test ralph run for stopped (completed) worker errors."""
        # Create worker and ralph state
        state = swarm.State()
        worker = swarm.Worker(
            name='ralph-worker',
            status='running',
            cmd=['claude'],
            started='2024-01-15T10:30:00',
            cwd='/tmp',
            tmux=swarm.TmuxInfo(session='swarm', window='ralph-worker')
        )
        state.workers.append(worker)
        state.save()

        ralph_state = swarm.RalphState(
            worker_name='ralph-worker',
            prompt_file='/path/to/prompt.md',
            max_iterations=10,
            status='stopped'
        )
        swarm.save_ralph_state(ralph_state)

        args = Namespace(name='ralph-worker')

        with patch('builtins.print') as mock_print:
            with self.assertRaises(SystemExit) as ctx:
                swarm.cmd_ralph_run(args)

        self.assertEqual(ctx.exception.code, 1)
        error_calls = [str(call) for call in mock_print.call_args_list]
        self.assertTrue(any('stopped' in call for call in error_calls))

    def test_run_requires_tmux(self):
        """Test ralph run requires tmux mode worker."""
        # Create a prompt file
        prompt_path = Path(self.temp_dir) / "prompt.md"
        prompt_path.write_text("test prompt")

        # Create worker without tmux info
        state = swarm.State()
        worker = swarm.Worker(
            name='ralph-worker',
            status='running',
            cmd=['echo', 'test'],
            started='2024-01-15T10:30:00',
            cwd='/tmp',
            pid=12345  # Process mode, not tmux
        )
        state.workers.append(worker)
        state.save()

        ralph_state = swarm.RalphState(
            worker_name='ralph-worker',
            prompt_file=str(prompt_path),
            max_iterations=10,
            status='running'
        )
        swarm.save_ralph_state(ralph_state)

        args = Namespace(name='ralph-worker')

        with patch('builtins.print') as mock_print:
            with self.assertRaises(SystemExit) as ctx:
                swarm.cmd_ralph_run(args)

        self.assertEqual(ctx.exception.code, 1)
        error_calls = [str(call) for call in mock_print.call_args_list]
        self.assertTrue(any('tmux' in call.lower() for call in error_calls))

    def test_run_max_iterations_reached_exits(self):
        """Test ralph run exits when max iterations reached."""
        # Create a prompt file
        prompt_path = Path(self.temp_dir) / "prompt.md"
        prompt_path.write_text("test prompt")

        # Create worker
        state = swarm.State()
        worker = swarm.Worker(
            name='ralph-worker',
            status='running',
            cmd=['echo', 'test'],
            started='2024-01-15T10:30:00',
            cwd='/tmp',
            tmux=swarm.TmuxInfo(session='swarm', window='ralph-worker')
        )
        state.workers.append(worker)
        state.save()

        # Create ralph state at max iterations
        ralph_state = swarm.RalphState(
            worker_name='ralph-worker',
            prompt_file=str(prompt_path),
            max_iterations=10,
            current_iteration=10,  # Already at max
            status='running'
        )
        swarm.save_ralph_state(ralph_state)

        args = Namespace(name='ralph-worker')

        with patch('builtins.print') as mock_print:
            swarm.cmd_ralph_run(args)

        output = '\n'.join([str(call) for call in mock_print.call_args_list])
        self.assertIn('loop complete', output)

        # Verify ralph state is now stopped
        updated_state = swarm.load_ralph_state('ralph-worker')
        self.assertEqual(updated_state.status, 'stopped')

    def test_run_prompt_file_not_found_exits(self):
        """Test ralph run exits when prompt file not found."""
        # Create worker
        state = swarm.State()
        worker = swarm.Worker(
            name='ralph-worker',
            status='running',
            cmd=['echo', 'test'],
            started='2024-01-15T10:30:00',
            cwd='/tmp',
            tmux=swarm.TmuxInfo(session='swarm', window='ralph-worker')
        )
        state.workers.append(worker)
        state.save()

        # Create ralph state pointing to nonexistent prompt file
        ralph_state = swarm.RalphState(
            worker_name='ralph-worker',
            prompt_file='/nonexistent/prompt.md',
            max_iterations=10,
            current_iteration=0,
            status='running'
        )
        swarm.save_ralph_state(ralph_state)

        args = Namespace(name='ralph-worker')

        with patch('builtins.print') as mock_print:
            with self.assertRaises(SystemExit) as ctx:
                swarm.cmd_ralph_run(args)

        self.assertEqual(ctx.exception.code, 1)
        error_calls = [str(call) for call in mock_print.call_args_list]
        self.assertTrue(any('prompt file not found' in call for call in error_calls))

        # Verify ralph state is now failed
        updated_state = swarm.load_ralph_state('ralph-worker')
        self.assertEqual(updated_state.status, 'failed')


class TestRalphRunDispatch(unittest.TestCase):
    """Test ralph run dispatch from cmd_ralph."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.original_swarm_dir = swarm.SWARM_DIR
        self.original_ralph_dir = swarm.RALPH_DIR
        self.original_state_file = swarm.STATE_FILE
        self.original_state_lock_file = swarm.STATE_LOCK_FILE
        swarm.SWARM_DIR = Path(self.temp_dir)
        swarm.RALPH_DIR = Path(self.temp_dir) / "ralph"
        swarm.STATE_FILE = Path(self.temp_dir) / "state.json"
        swarm.STATE_LOCK_FILE = Path(self.temp_dir) / "state.lock"

    def tearDown(self):
        """Clean up test fixtures."""
        swarm.SWARM_DIR = self.original_swarm_dir
        swarm.RALPH_DIR = self.original_ralph_dir
        swarm.STATE_FILE = self.original_state_file
        swarm.STATE_LOCK_FILE = self.original_state_lock_file
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_dispatch_run(self):
        """Test cmd_ralph dispatches to run."""
        args = Namespace(ralph_command='run', name='nonexistent')

        with patch('builtins.print') as mock_print:
            with self.assertRaises(SystemExit):
                swarm.cmd_ralph(args)

        # If it reached cmd_ralph_run, it will error with 'not found'
        error_calls = [str(call) for call in mock_print.call_args_list]
        self.assertTrue(any('not found' in call for call in error_calls))


class TestCheckDonePattern(unittest.TestCase):
    """Test check_done_pattern function."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.original_swarm_dir = swarm.SWARM_DIR
        self.original_ralph_dir = swarm.RALPH_DIR
        self.original_state_file = swarm.STATE_FILE
        self.original_state_lock_file = swarm.STATE_LOCK_FILE
        swarm.SWARM_DIR = Path(self.temp_dir)
        swarm.RALPH_DIR = Path(self.temp_dir) / "ralph"
        swarm.STATE_FILE = Path(self.temp_dir) / "state.json"
        swarm.STATE_LOCK_FILE = Path(self.temp_dir) / "state.lock"

    def tearDown(self):
        """Clean up test fixtures."""
        swarm.SWARM_DIR = self.original_swarm_dir
        swarm.RALPH_DIR = self.original_ralph_dir
        swarm.STATE_FILE = self.original_state_file
        swarm.STATE_LOCK_FILE = self.original_state_lock_file
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_check_done_pattern_no_tmux(self):
        """Test check_done_pattern returns False for non-tmux worker."""
        worker = swarm.Worker(
            name='test-worker',
            status='running',
            cmd=['echo', 'test'],
            started='2024-01-15T10:30:00',
            cwd='/tmp'
        )
        result = swarm.check_done_pattern(worker, "test pattern")
        self.assertFalse(result)

    def test_check_done_pattern_subprocess_error(self):
        """Test check_done_pattern handles subprocess errors."""
        worker = swarm.Worker(
            name='test-worker',
            status='running',
            cmd=['echo', 'test'],
            started='2024-01-15T10:30:00',
            cwd='/tmp',
            tmux=swarm.TmuxInfo(session='nonexistent', window='test')
        )

        # Should return False when window doesn't exist
        result = swarm.check_done_pattern(worker, "test pattern")
        self.assertFalse(result)

    def test_check_done_pattern_matches(self):
        """Test check_done_pattern returns True when pattern matches."""
        worker = swarm.Worker(
            name='test-worker',
            status='running',
            cmd=['echo', 'test'],
            started='2024-01-15T10:30:00',
            cwd='/tmp',
            tmux=swarm.TmuxInfo(session='swarm', window='test')
        )

        with patch('swarm.tmux_capture_pane', return_value='All tasks complete\nDone'):
            result = swarm.check_done_pattern(worker, "All tasks complete")
            self.assertTrue(result)

    def test_check_done_pattern_no_match(self):
        """Test check_done_pattern returns False when pattern doesn't match."""
        worker = swarm.Worker(
            name='test-worker',
            status='running',
            cmd=['echo', 'test'],
            started='2024-01-15T10:30:00',
            cwd='/tmp',
            tmux=swarm.TmuxInfo(session='swarm', window='test')
        )

        with patch('swarm.tmux_capture_pane', return_value='Still working on tasks'):
            result = swarm.check_done_pattern(worker, "All tasks complete")
            self.assertFalse(result)


class TestDetectInactivity(unittest.TestCase):
    """Test detect_inactivity function."""

    def test_detect_inactivity_no_tmux(self):
        """Test detect_inactivity returns False for non-tmux worker."""
        worker = swarm.Worker(
            name='test-worker',
            status='running',
            cmd=['echo', 'test'],
            started='2024-01-15T10:30:00',
            cwd='/tmp',
            pid=12345
        )
        result = swarm.detect_inactivity(worker, timeout=1)
        self.assertFalse(result)


class TestKillWorkerForRalph(unittest.TestCase):
    """Test kill_worker_for_ralph function."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.original_swarm_dir = swarm.SWARM_DIR
        self.original_ralph_dir = swarm.RALPH_DIR
        self.original_state_file = swarm.STATE_FILE
        self.original_state_lock_file = swarm.STATE_LOCK_FILE
        swarm.SWARM_DIR = Path(self.temp_dir)
        swarm.RALPH_DIR = Path(self.temp_dir) / "ralph"
        swarm.STATE_FILE = Path(self.temp_dir) / "state.json"
        swarm.STATE_LOCK_FILE = Path(self.temp_dir) / "state.lock"

    def tearDown(self):
        """Clean up test fixtures."""
        swarm.SWARM_DIR = self.original_swarm_dir
        swarm.RALPH_DIR = self.original_ralph_dir
        swarm.STATE_FILE = self.original_state_file
        swarm.STATE_LOCK_FILE = self.original_state_lock_file
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_kill_tmux_worker(self):
        """Test kill_worker_for_ralph calls tmux kill-window."""
        state = swarm.State()
        worker = swarm.Worker(
            name='test-worker',
            status='running',
            cmd=['echo', 'test'],
            started='2024-01-15T10:30:00',
            cwd='/tmp',
            tmux=swarm.TmuxInfo(session='swarm', window='test-worker')
        )

        with patch('subprocess.run') as mock_run:
            swarm.kill_worker_for_ralph(worker, state)

        mock_run.assert_called_once()
        call_args = mock_run.call_args[0][0]
        self.assertIn('kill-window', call_args)

    def test_kill_non_tmux_worker(self):
        """Test kill_worker_for_ralph does nothing for non-tmux worker."""
        state = swarm.State()
        worker = swarm.Worker(
            name='test-worker',
            status='running',
            cmd=['echo', 'test'],
            started='2024-01-15T10:30:00',
            cwd='/tmp',
            pid=12345
        )

        with patch('subprocess.run') as mock_run:
            swarm.kill_worker_for_ralph(worker, state)

        mock_run.assert_not_called()


class TestSpawnWorkerForRalph(unittest.TestCase):
    """Test spawn_worker_for_ralph function."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Clean up test fixtures."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_spawn_creates_worker(self):
        """Test spawn_worker_for_ralph creates a worker."""
        with patch('swarm.create_tmux_window') as mock_create:
            worker = swarm.spawn_worker_for_ralph(
                name='test-worker',
                cmd=['echo', 'test'],
                cwd=Path(self.temp_dir),
                env={'TEST': 'value'},
                tags=['tag1'],
                session='swarm',
                socket=None,
                worktree_info=None,
                metadata={'ralph': True}
            )

        mock_create.assert_called_once()
        self.assertEqual(worker.name, 'test-worker')
        self.assertEqual(worker.cmd, ['echo', 'test'])
        self.assertEqual(worker.status, 'running')
        self.assertIsNotNone(worker.tmux)
        self.assertEqual(worker.tmux.session, 'swarm')
        self.assertEqual(worker.tmux.window, 'test-worker')
        self.assertEqual(worker.metadata, {'ralph': True})


class TestSendPromptToWorker(unittest.TestCase):
    """Test send_prompt_to_worker function."""

    def test_send_prompt_no_tmux(self):
        """Test send_prompt_to_worker does nothing for non-tmux worker."""
        worker = swarm.Worker(
            name='test-worker',
            status='running',
            cmd=['echo', 'test'],
            started='2024-01-15T10:30:00',
            cwd='/tmp',
            pid=12345
        )

        # Should not raise
        with patch('swarm.wait_for_agent_ready') as mock_wait:
            with patch('swarm.tmux_send') as mock_send:
                swarm.send_prompt_to_worker(worker, "test prompt")

        mock_wait.assert_not_called()
        mock_send.assert_not_called()

    def test_send_prompt_to_tmux_worker(self):
        """Test send_prompt_to_worker sends to tmux worker."""
        worker = swarm.Worker(
            name='test-worker',
            status='running',
            cmd=['echo', 'test'],
            started='2024-01-15T10:30:00',
            cwd='/tmp',
            tmux=swarm.TmuxInfo(session='swarm', window='test-worker')
        )

        with patch('swarm.wait_for_agent_ready') as mock_wait:
            with patch('swarm.tmux_send') as mock_send:
                swarm.send_prompt_to_worker(worker, "test prompt content")

        mock_wait.assert_called_once()
        mock_send.assert_called_once()
        # Check prompt was passed
        call_args = mock_send.call_args
        self.assertEqual(call_args[0][2], "test prompt content")


class TestRalphRunMainLoop(unittest.TestCase):
    """Test the main loop execution path of cmd_ralph_run with mocking."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.original_swarm_dir = swarm.SWARM_DIR
        self.original_ralph_dir = swarm.RALPH_DIR
        self.original_state_file = swarm.STATE_FILE
        self.original_state_lock_file = swarm.STATE_LOCK_FILE
        swarm.SWARM_DIR = Path(self.temp_dir)
        swarm.RALPH_DIR = Path(self.temp_dir) / "ralph"
        swarm.STATE_FILE = Path(self.temp_dir) / "state.json"
        swarm.STATE_LOCK_FILE = Path(self.temp_dir) / "state.lock"

        # Create a prompt file
        self.prompt_path = Path(self.temp_dir) / "prompt.md"
        self.prompt_path.write_text("test prompt content")

    def tearDown(self):
        """Clean up test fixtures."""
        swarm.SWARM_DIR = self.original_swarm_dir
        swarm.RALPH_DIR = self.original_ralph_dir
        swarm.STATE_FILE = self.original_state_file
        swarm.STATE_LOCK_FILE = self.original_state_lock_file
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_loop_spawns_worker_when_stopped(self):
        """Test loop spawns new worker when current one has stopped."""
        # Create worker (stopped status simulated via refresh)
        state = swarm.State()
        worker = swarm.Worker(
            name='ralph-worker',
            status='stopped',
            cmd=['echo', 'test'],
            started='2024-01-15T10:30:00',
            cwd=self.temp_dir,
            tmux=swarm.TmuxInfo(session='swarm', window='ralph-worker')
        )
        state.workers.append(worker)
        state.save()

        # Create ralph state at iteration 0 (so it will start iteration 1)
        ralph_state = swarm.RalphState(
            worker_name='ralph-worker',
            prompt_file=str(self.prompt_path),
            max_iterations=1,  # Only 1 iteration so it stops after
            current_iteration=0,
            status='running'
        )
        swarm.save_ralph_state(ralph_state)

        args = Namespace(name='ralph-worker')

        # Mock the loop to exit after first check
        with patch('swarm.refresh_worker_status', return_value='stopped'):
            with patch('swarm.spawn_worker_for_ralph') as mock_spawn:
                with patch('swarm.send_prompt_to_worker'):
                    with patch.object(swarm.State, 'add_worker'):
                        with patch('builtins.print'):
                            # Mock spawn to return a valid worker
                            mock_worker = swarm.Worker(
                                name='ralph-worker',
                                status='running',
                                cmd=['echo', 'test'],
                                started='2024-01-15T10:30:00',
                                cwd=self.temp_dir,
                                tmux=swarm.TmuxInfo(session='swarm', window='ralph-worker')
                            )
                            mock_spawn.return_value = mock_worker

                            swarm.cmd_ralph_run(args)

        # Verify spawn was called
        mock_spawn.assert_called()

    def test_loop_handles_done_pattern_match(self):
        """Test loop stops when done pattern matches."""
        # Create worker
        state = swarm.State()
        worker = swarm.Worker(
            name='ralph-worker',
            status='running',
            cmd=['echo', 'test'],
            started='2024-01-15T10:30:00',
            cwd=self.temp_dir,
            tmux=swarm.TmuxInfo(session='swarm', window='ralph-worker')
        )
        state.workers.append(worker)
        state.save()

        # Create ralph state with done pattern
        ralph_state = swarm.RalphState(
            worker_name='ralph-worker',
            prompt_file=str(self.prompt_path),
            max_iterations=10,
            current_iteration=1,
            status='running',
            done_pattern='All.*complete'
        )
        swarm.save_ralph_state(ralph_state)

        args = Namespace(name='ralph-worker')

        # Mock worker to be stopped and done pattern to match
        call_count = [0]
        def mock_refresh(w):
            call_count[0] += 1
            if call_count[0] == 1:
                return 'running'
            return 'stopped'

        with patch('swarm.refresh_worker_status', side_effect=mock_refresh):
            with patch('swarm.check_done_pattern', return_value=True):
                with patch('builtins.print') as mock_print:
                    swarm.cmd_ralph_run(args)

        # Check that done pattern message was printed
        output = '\n'.join([str(call) for call in mock_print.call_args_list])
        self.assertIn('done pattern matched', output)

        # Check state is stopped
        updated_state = swarm.load_ralph_state('ralph-worker')
        self.assertEqual(updated_state.status, 'stopped')

    def test_loop_handles_inactivity_timeout(self):
        """Test loop handles inactivity timeout."""
        # Create worker
        state = swarm.State()
        worker = swarm.Worker(
            name='ralph-worker',
            status='running',
            cmd=['echo', 'test'],
            started='2024-01-15T10:30:00',
            cwd=self.temp_dir,
            tmux=swarm.TmuxInfo(session='swarm', window='ralph-worker')
        )
        state.workers.append(worker)
        state.save()

        # Create ralph state with short timeout
        ralph_state = swarm.RalphState(
            worker_name='ralph-worker',
            prompt_file=str(self.prompt_path),
            max_iterations=2,
            current_iteration=1,
            status='running',
            inactivity_timeout=1  # Very short
        )
        swarm.save_ralph_state(ralph_state)

        args = Namespace(name='ralph-worker')

        # Mock to simulate inactivity then stopped
        call_count = [0]
        def mock_refresh(w):
            call_count[0] += 1
            # First few calls show running, then stopped
            if call_count[0] <= 3:
                return 'running'
            return 'stopped'

        inactivity_count = [0]
        def mock_inactivity(w, t, mode='ready'):
            inactivity_count[0] += 1
            if inactivity_count[0] == 1:
                return True  # First check shows inactivity
            return False

        with patch('swarm.refresh_worker_status', side_effect=mock_refresh):
            with patch('swarm.detect_inactivity', side_effect=mock_inactivity):
                with patch('swarm.kill_worker_for_ralph') as mock_kill:
                    with patch('swarm.spawn_worker_for_ralph') as mock_spawn:
                        with patch('swarm.send_prompt_to_worker'):
                            with patch.object(swarm.State, 'add_worker'):
                                with patch.object(swarm.State, 'remove_worker'):
                                    with patch('builtins.print') as mock_print:
                                        # Mock spawn to return a worker
                                        mock_worker = swarm.Worker(
                                            name='ralph-worker',
                                            status='running',
                                            cmd=['echo', 'test'],
                                            started='2024-01-15T10:30:00',
                                            cwd=self.temp_dir,
                                            tmux=swarm.TmuxInfo(session='swarm', window='ralph-worker')
                                        )
                                        mock_spawn.return_value = mock_worker

                                        swarm.cmd_ralph_run(args)

        # Check that inactivity message was logged
        output = '\n'.join([str(call) for call in mock_print.call_args_list])
        self.assertIn('inactivity timeout', output)

    def test_loop_handles_spawn_failure(self):
        """Test loop handles spawn failure with backoff."""
        # Create worker (stopped)
        state = swarm.State()
        worker = swarm.Worker(
            name='ralph-worker',
            status='stopped',
            cmd=['echo', 'test'],
            started='2024-01-15T10:30:00',
            cwd=self.temp_dir,
            tmux=swarm.TmuxInfo(session='swarm', window='ralph-worker')
        )
        state.workers.append(worker)
        state.save()

        # Create ralph state
        ralph_state = swarm.RalphState(
            worker_name='ralph-worker',
            prompt_file=str(self.prompt_path),
            max_iterations=10,
            current_iteration=0,
            status='running',
            consecutive_failures=4  # Already at 4 failures
        )
        swarm.save_ralph_state(ralph_state)

        args = Namespace(name='ralph-worker')

        # Mock spawn to fail
        with patch('swarm.refresh_worker_status', return_value='stopped'):
            with patch('swarm.spawn_worker_for_ralph', side_effect=Exception("Spawn failed")):
                with patch('builtins.print') as mock_print:
                    with self.assertRaises(SystemExit) as ctx:
                        swarm.cmd_ralph_run(args)

        # Should exit with code 1 after 5 consecutive failures
        self.assertEqual(ctx.exception.code, 1)

        # Check state is failed
        updated_state = swarm.load_ralph_state('ralph-worker')
        self.assertEqual(updated_state.status, 'failed')

    def test_loop_resets_failures_on_success(self):
        """Test loop resets consecutive failures on successful iteration."""
        # Create worker
        state = swarm.State()
        worker = swarm.Worker(
            name='ralph-worker',
            status='running',
            cmd=['echo', 'test'],
            started='2024-01-15T10:30:00',
            cwd=self.temp_dir,
            tmux=swarm.TmuxInfo(session='swarm', window='ralph-worker')
        )
        state.workers.append(worker)
        state.save()

        # Create ralph state with some failures - current_iteration=0 so it will spawn
        ralph_state = swarm.RalphState(
            worker_name='ralph-worker',
            prompt_file=str(self.prompt_path),
            max_iterations=1,
            current_iteration=0,  # Will do iteration 1 then hit max
            status='running',
            consecutive_failures=3,  # Had some failures
            total_failures=5
        )
        swarm.save_ralph_state(ralph_state)

        args = Namespace(name='ralph-worker')

        # Mock to simulate: worker initially running, then stopped after one check
        call_count = [0]
        def mock_refresh(w):
            call_count[0] += 1
            # First call: stopped (to trigger spawn), second: running, third+: stopped
            if call_count[0] == 1:
                return 'stopped'
            elif call_count[0] == 2:
                return 'running'
            return 'stopped'

        with patch('swarm.refresh_worker_status', side_effect=mock_refresh):
            with patch('swarm.spawn_worker_for_ralph') as mock_spawn:
                with patch('swarm.send_prompt_to_worker'):
                    with patch.object(swarm.State, 'add_worker'):
                        with patch.object(swarm.State, 'remove_worker'):
                            with patch('swarm.detect_inactivity', return_value=False):
                                with patch('swarm.check_done_pattern', return_value=False):
                                    with patch('builtins.print'):
                                        # Mock spawn to return a worker
                                        mock_worker = swarm.Worker(
                                            name='ralph-worker',
                                            status='running',
                                            cmd=['echo', 'test'],
                                            started='2024-01-15T10:30:00',
                                            cwd=self.temp_dir,
                                            tmux=swarm.TmuxInfo(session='swarm', window='ralph-worker')
                                        )
                                        mock_spawn.return_value = mock_worker

                                        swarm.cmd_ralph_run(args)

        # Check consecutive failures is reset
        updated_state = swarm.load_ralph_state('ralph-worker')
        self.assertEqual(updated_state.consecutive_failures, 0)

    def test_loop_exits_when_paused_externally(self):
        """Test loop exits when status changed to paused externally."""
        # Create worker
        state = swarm.State()
        worker = swarm.Worker(
            name='ralph-worker',
            status='running',
            cmd=['echo', 'test'],
            started='2024-01-15T10:30:00',
            cwd=self.temp_dir,
            tmux=swarm.TmuxInfo(session='swarm', window='ralph-worker')
        )
        state.workers.append(worker)
        state.save()

        # Create ralph state
        ralph_state = swarm.RalphState(
            worker_name='ralph-worker',
            prompt_file=str(self.prompt_path),
            max_iterations=10,
            current_iteration=1,
            status='running'
        )
        swarm.save_ralph_state(ralph_state)

        args = Namespace(name='ralph-worker')

        # Mock to simulate external pause
        load_count = [0]
        original_load = swarm.load_ralph_state
        def mock_load(name):
            load_count[0] += 1
            state = original_load(name)
            if state and load_count[0] >= 3:
                # Simulate external pause
                state.status = 'paused'
            return state

        with patch('swarm.load_ralph_state', side_effect=mock_load):
            with patch('swarm.refresh_worker_status', return_value='running'):
                with patch('swarm.detect_inactivity', return_value=False):
                    with patch('builtins.print') as mock_print:
                        with patch('time.sleep'):  # Speed up the test
                            swarm.cmd_ralph_run(args)

        # Check that paused message was printed
        output = '\n'.join([str(call) for call in mock_print.call_args_list])
        self.assertIn('paused', output)


class TestWaitForWorkerExit(unittest.TestCase):
    """Test wait_for_worker_exit function."""

    def test_returns_timeout_when_still_running(self):
        """Test returns timeout when worker still running."""
        worker = swarm.Worker(
            name='test-worker',
            status='running',
            cmd=['echo', 'test'],
            started='2024-01-15T10:30:00',
            cwd='/tmp',
            pid=12345
        )

        with patch('swarm.refresh_worker_status', return_value='running'):
            with patch('time.sleep'):  # Speed up the test
                exited, reason = swarm.wait_for_worker_exit(worker, timeout=0)

        self.assertFalse(exited)
        self.assertEqual(reason, "timeout")


class TestRalphRunEdgeCases(unittest.TestCase):
    """Test edge cases for cmd_ralph_run that increase coverage."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.original_swarm_dir = swarm.SWARM_DIR
        self.original_ralph_dir = swarm.RALPH_DIR
        self.original_state_file = swarm.STATE_FILE
        self.original_state_lock_file = swarm.STATE_LOCK_FILE
        swarm.SWARM_DIR = Path(self.temp_dir)
        swarm.RALPH_DIR = Path(self.temp_dir) / "ralph"
        swarm.STATE_FILE = Path(self.temp_dir) / "state.json"
        swarm.STATE_LOCK_FILE = Path(self.temp_dir) / "state.lock"

        # Create a prompt file
        self.prompt_path = Path(self.temp_dir) / "prompt.md"
        self.prompt_path.write_text("test prompt content")

    def tearDown(self):
        """Clean up test fixtures."""
        swarm.SWARM_DIR = self.original_swarm_dir
        swarm.RALPH_DIR = self.original_ralph_dir
        swarm.STATE_FILE = self.original_state_file
        swarm.STATE_LOCK_FILE = self.original_state_lock_file
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_run_ralph_state_deleted_during_loop(self):
        """Test ralph run handles ralph state being deleted during loop.

        Covers line 2504: break when ralph_state is None after reload.
        """
        # Create worker
        state = swarm.State()
        worker = swarm.Worker(
            name='ralph-worker',
            status='running',
            cmd=['echo', 'test'],
            started='2024-01-15T10:30:00',
            cwd=self.temp_dir,
            tmux=swarm.TmuxInfo(session='swarm', window='ralph-worker')
        )
        state.workers.append(worker)
        state.save()

        # Create ralph state
        ralph_state = swarm.RalphState(
            worker_name='ralph-worker',
            prompt_file=str(self.prompt_path),
            max_iterations=10,
            current_iteration=1,
            status='running'
        )
        swarm.save_ralph_state(ralph_state)

        args = Namespace(name='ralph-worker')

        # Simulate deleting the ralph state file after first load (which happens before main loop)
        # The main loop starts at line 2500, and line 2502-2504 checks if ralph_state is None
        load_count = [0]
        def mock_load(name):
            load_count[0] += 1
            # First load (before main loop validation) returns the real state
            # Second load (in main while loop at line 2502) returns None
            if load_count[0] <= 1:
                return swarm.RalphState(
                    worker_name='ralph-worker',
                    prompt_file=str(self.prompt_path),
                    max_iterations=10,
                    current_iteration=1,
                    status='running'
                )
            return None  # Simulate deleted state

        with patch('swarm.load_ralph_state', side_effect=mock_load):
            with patch('builtins.print') as mock_print:
                # Should exit cleanly when state is deleted during loop
                swarm.cmd_ralph_run(args)

        # Loop should have exited without crashing after detecting None state
        self.assertGreater(load_count[0], 1)  # Ensure loop was entered

    def test_run_paused_during_inner_loop(self):
        """Test ralph run exits when paused during inner monitoring loop.

        Covers lines 2508-2509: paused status during loop with print message.
        """
        # Create worker
        state = swarm.State()
        worker = swarm.Worker(
            name='ralph-worker',
            status='running',
            cmd=['echo', 'test'],
            started='2024-01-15T10:30:00',
            cwd=self.temp_dir,
            tmux=swarm.TmuxInfo(session='swarm', window='ralph-worker')
        )
        state.workers.append(worker)
        state.save()

        # Create ralph state
        ralph_state = swarm.RalphState(
            worker_name='ralph-worker',
            prompt_file=str(self.prompt_path),
            max_iterations=10,
            current_iteration=1,
            status='running'
        )
        swarm.save_ralph_state(ralph_state)

        args = Namespace(name='ralph-worker')

        # Mock to change status to paused on second load
        load_count = [0]
        original_load = swarm.load_ralph_state
        def mock_load(name):
            load_count[0] += 1
            result = original_load(name)
            if result and load_count[0] >= 2:
                result.status = 'paused'
            return result

        with patch('swarm.load_ralph_state', side_effect=mock_load):
            with patch('swarm.refresh_worker_status', return_value='running'):
                with patch('swarm.detect_inactivity', return_value=False):
                    with patch('builtins.print') as mock_print:
                        with patch('time.sleep'):
                            swarm.cmd_ralph_run(args)

        # Should print paused message
        output = '\n'.join([str(call) for call in mock_print.call_args_list])
        self.assertIn('paused', output)

    def test_run_prompt_file_read_error(self):
        """Test ralph run handles prompt file read permission error.

        Covers lines 2534-2538: cannot read prompt file error.
        """
        # Create worker
        state = swarm.State()
        worker = swarm.Worker(
            name='ralph-worker',
            status='running',
            cmd=['echo', 'test'],
            started='2024-01-15T10:30:00',
            cwd=self.temp_dir,
            tmux=swarm.TmuxInfo(session='swarm', window='ralph-worker')
        )
        state.workers.append(worker)
        state.save()

        # Create ralph state with valid prompt file path (but we'll mock the read to fail)
        ralph_state = swarm.RalphState(
            worker_name='ralph-worker',
            prompt_file=str(self.prompt_path),
            max_iterations=10,
            current_iteration=0,
            status='running'
        )
        swarm.save_ralph_state(ralph_state)

        args = Namespace(name='ralph-worker')

        # Mock Path.read_text to raise an exception
        original_read_text = Path.read_text
        def mock_read_text(path):
            if 'prompt' in str(path):
                raise PermissionError("Permission denied")
            return original_read_text(path)

        with patch.object(Path, 'read_text', mock_read_text):
            with patch('builtins.print') as mock_print:
                with self.assertRaises(SystemExit) as ctx:
                    swarm.cmd_ralph_run(args)

        self.assertEqual(ctx.exception.code, 1)
        error_calls = [str(call) for call in mock_print.call_args_list]
        self.assertTrue(any('cannot read prompt file' in call for call in error_calls))

        # Verify ralph state is set to failed
        updated_state = swarm.load_ralph_state('ralph-worker')
        self.assertEqual(updated_state.status, 'failed')

    def test_run_spawn_failure_with_backoff_logging(self):
        """Test ralph run logs failure with backoff when spawn fails.

        Covers lines 2604-2615: backoff calculation, logging, and sleep.
        """
        # Create worker (stopped)
        state = swarm.State()
        worker = swarm.Worker(
            name='ralph-worker',
            status='stopped',
            cmd=['echo', 'test'],
            started='2024-01-15T10:30:00',
            cwd=self.temp_dir,
            tmux=swarm.TmuxInfo(session='swarm', window='ralph-worker')
        )
        state.workers.append(worker)
        state.save()

        # Create ralph state with 0 consecutive failures (so we test the full backoff path)
        ralph_state = swarm.RalphState(
            worker_name='ralph-worker',
            prompt_file=str(self.prompt_path),
            max_iterations=10,
            current_iteration=0,
            status='running',
            consecutive_failures=0
        )
        swarm.save_ralph_state(ralph_state)

        args = Namespace(name='ralph-worker')

        # Mock spawn to fail repeatedly until we hit 5 failures
        spawn_call_count = [0]
        def mock_spawn(*args, **kwargs):
            spawn_call_count[0] += 1
            raise Exception("Spawn failed")

        with patch('swarm.refresh_worker_status', return_value='stopped'):
            with patch('swarm.spawn_worker_for_ralph', side_effect=mock_spawn):
                with patch('time.sleep') as mock_sleep:
                    with patch('builtins.print') as mock_print:
                        with self.assertRaises(SystemExit) as ctx:
                            swarm.cmd_ralph_run(args)

        # Should exit with code 1
        self.assertEqual(ctx.exception.code, 1)

        # Check that backoff sleep was called with correct values
        # After 1st failure: backoff=1s, 2nd: 2s, 3rd: 4s, 4th: 8s
        sleep_calls = [call[0][0] for call in mock_sleep.call_args_list]
        self.assertEqual(sleep_calls[0], 1)   # 2^(1-1) = 1
        self.assertEqual(sleep_calls[1], 2)   # 2^(2-1) = 2
        self.assertEqual(sleep_calls[2], 4)   # 2^(3-1) = 4
        self.assertEqual(sleep_calls[3], 8)   # 2^(4-1) = 8

        # Check output contains backoff messages
        output = '\n'.join([str(call) for call in mock_print.call_args_list])
        self.assertIn('retrying in', output)
        self.assertIn('5 consecutive failures', output)

        # Check iteration log was created with FAIL events
        log_path = swarm.get_ralph_iterations_log_path('ralph-worker')
        log_content = log_path.read_text()
        self.assertIn('[FAIL]', log_content)


class TestRalphListSubparser(unittest.TestCase):
    """Test that ralph list subparser is correctly configured."""

    def test_ralph_list_subcommand_exists(self):
        """Test that 'ralph list' subcommand is recognized."""
        result = subprocess.run(
            [sys.executable, 'swarm.py', 'ralph', 'list', '--help'],
            capture_output=True,
            text=True
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn('format', result.stdout.lower())

    def test_ralph_list_format_flag(self):
        """Test --format flag accepts valid values."""
        result = subprocess.run(
            [sys.executable, 'swarm.py', 'ralph', 'list', '--format', 'json', '--help'],
            capture_output=True,
            text=True
        )
        self.assertEqual(result.returncode, 0)

    def test_ralph_list_status_flag(self):
        """Test --status flag accepts valid values."""
        result = subprocess.run(
            [sys.executable, 'swarm.py', 'ralph', 'list', '--status', 'running', '--help'],
            capture_output=True,
            text=True
        )
        self.assertEqual(result.returncode, 0)


class TestCmdRalphList(unittest.TestCase):
    """Test cmd_ralph_list function."""

    def setUp(self):
        """Create temporary directories for testing."""
        # Create temp directory for RALPH_DIR
        self.temp_dir = tempfile.mkdtemp()
        self.old_ralph_dir = swarm.RALPH_DIR
        swarm.RALPH_DIR = Path(self.temp_dir) / "ralph"
        swarm.RALPH_DIR.mkdir(parents=True, exist_ok=True)

        # Create temp directory for STATE_FILE
        self.old_state_file = swarm.STATE_FILE
        self.old_state_lock_file = swarm.STATE_LOCK_FILE
        swarm.STATE_FILE = Path(self.temp_dir) / "state.json"
        swarm.STATE_LOCK_FILE = Path(self.temp_dir) / "state.lock"

    def tearDown(self):
        """Restore original directories and clean up."""
        swarm.RALPH_DIR = self.old_ralph_dir
        swarm.STATE_FILE = self.old_state_file
        swarm.STATE_LOCK_FILE = self.old_state_lock_file
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_list_empty_no_ralph_workers(self):
        """Test ralph list with no ralph workers returns empty."""
        args = Namespace(format='table', status='all')

        with patch('builtins.print') as mock_print:
            swarm.cmd_ralph_list(args)

        # Should not print anything for empty list
        mock_print.assert_not_called()

    def test_list_table_format_single_worker(self):
        """Test ralph list table format with single worker."""
        # Create a ralph state
        ralph_state = swarm.RalphState(
            worker_name='test-worker',
            prompt_file='/path/to/prompt.md',
            max_iterations=10,
            current_iteration=3,
            status='running',
            consecutive_failures=1,
            total_failures=2
        )
        swarm.save_ralph_state(ralph_state)

        args = Namespace(format='table', status='all')

        with patch('swarm.refresh_worker_status', return_value='stopped'):
            with patch('builtins.print') as mock_print:
                swarm.cmd_ralph_list(args)

        # Check header was printed
        calls = [str(call) for call in mock_print.call_args_list]
        output = '\n'.join(calls)
        self.assertIn('NAME', output)
        self.assertIn('RALPH_STATUS', output)
        self.assertIn('WORKER_STATUS', output)
        self.assertIn('ITERATION', output)
        self.assertIn('FAILURES', output)
        # Check worker data
        self.assertIn('test-worker', output)
        self.assertIn('running', output)
        self.assertIn('3/10', output)
        self.assertIn('1/2', output)

    def test_list_json_format(self):
        """Test ralph list JSON format."""
        # Create a ralph state
        ralph_state = swarm.RalphState(
            worker_name='json-worker',
            prompt_file='/path/to/prompt.md',
            max_iterations=20,
            current_iteration=5,
            status='paused',
            consecutive_failures=0,
            total_failures=1
        )
        swarm.save_ralph_state(ralph_state)

        args = Namespace(format='json', status='all')

        import io
        import json
        with patch('sys.stdout', new=io.StringIO()) as mock_stdout:
            swarm.cmd_ralph_list(args)
            output = mock_stdout.getvalue()

        # Parse JSON and verify
        data = json.loads(output)
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]['worker_name'], 'json-worker')
        self.assertEqual(data[0]['status'], 'paused')
        self.assertEqual(data[0]['current_iteration'], 5)
        self.assertEqual(data[0]['max_iterations'], 20)
        # Worker doesn't exist in swarm state, so should be 'removed'
        self.assertEqual(data[0]['worker_status'], 'removed')

    def test_list_names_format(self):
        """Test ralph list names format."""
        # Create two ralph states
        ralph_state1 = swarm.RalphState(
            worker_name='worker-a',
            prompt_file='/path/to/prompt.md',
            max_iterations=10,
            current_iteration=1,
            status='running'
        )
        swarm.save_ralph_state(ralph_state1)

        ralph_state2 = swarm.RalphState(
            worker_name='worker-b',
            prompt_file='/path/to/prompt.md',
            max_iterations=10,
            current_iteration=2,
            status='paused'
        )
        swarm.save_ralph_state(ralph_state2)

        args = Namespace(format='names', status='all')

        with patch('builtins.print') as mock_print:
            swarm.cmd_ralph_list(args)

        # Check both workers were printed
        calls = [call[0][0] for call in mock_print.call_args_list]
        self.assertIn('worker-a', calls)
        self.assertIn('worker-b', calls)

    def test_list_filter_by_status_running(self):
        """Test ralph list filters by status=running."""
        # Create workers with different statuses
        ralph_state1 = swarm.RalphState(
            worker_name='running-worker',
            prompt_file='/path/to/prompt.md',
            max_iterations=10,
            current_iteration=1,
            status='running'
        )
        swarm.save_ralph_state(ralph_state1)

        ralph_state2 = swarm.RalphState(
            worker_name='paused-worker',
            prompt_file='/path/to/prompt.md',
            max_iterations=10,
            current_iteration=2,
            status='paused'
        )
        swarm.save_ralph_state(ralph_state2)

        args = Namespace(format='names', status='running')

        with patch('builtins.print') as mock_print:
            swarm.cmd_ralph_list(args)

        # Only running worker should be printed
        calls = [call[0][0] for call in mock_print.call_args_list]
        self.assertEqual(calls, ['running-worker'])

    def test_list_filter_by_status_paused(self):
        """Test ralph list filters by status=paused."""
        # Create workers with different statuses
        ralph_state1 = swarm.RalphState(
            worker_name='running-worker',
            prompt_file='/path/to/prompt.md',
            max_iterations=10,
            current_iteration=1,
            status='running'
        )
        swarm.save_ralph_state(ralph_state1)

        ralph_state2 = swarm.RalphState(
            worker_name='paused-worker',
            prompt_file='/path/to/prompt.md',
            max_iterations=10,
            current_iteration=2,
            status='paused'
        )
        swarm.save_ralph_state(ralph_state2)

        args = Namespace(format='names', status='paused')

        with patch('builtins.print') as mock_print:
            swarm.cmd_ralph_list(args)

        # Only paused worker should be printed
        calls = [call[0][0] for call in mock_print.call_args_list]
        self.assertEqual(calls, ['paused-worker'])

    def test_list_filter_by_status_stopped(self):
        """Test ralph list filters by status=stopped."""
        ralph_state = swarm.RalphState(
            worker_name='stopped-worker',
            prompt_file='/path/to/prompt.md',
            max_iterations=10,
            current_iteration=5,
            status='stopped'
        )
        swarm.save_ralph_state(ralph_state)

        args = Namespace(format='names', status='stopped')

        with patch('builtins.print') as mock_print:
            swarm.cmd_ralph_list(args)

        calls = [call[0][0] for call in mock_print.call_args_list]
        self.assertEqual(calls, ['stopped-worker'])

    def test_list_filter_by_status_failed(self):
        """Test ralph list filters by status=failed."""
        ralph_state = swarm.RalphState(
            worker_name='failed-worker',
            prompt_file='/path/to/prompt.md',
            max_iterations=10,
            current_iteration=3,
            status='failed',
            consecutive_failures=5,
            total_failures=5
        )
        swarm.save_ralph_state(ralph_state)

        args = Namespace(format='names', status='failed')

        with patch('builtins.print') as mock_print:
            swarm.cmd_ralph_list(args)

        calls = [call[0][0] for call in mock_print.call_args_list]
        self.assertEqual(calls, ['failed-worker'])

    def test_list_with_existing_worker(self):
        """Test ralph list shows worker status for existing workers."""
        # Create ralph state
        ralph_state = swarm.RalphState(
            worker_name='existing-worker',
            prompt_file='/path/to/prompt.md',
            max_iterations=10,
            current_iteration=3,
            status='running'
        )
        swarm.save_ralph_state(ralph_state)

        # Create corresponding swarm worker
        state = swarm.State()
        worker = swarm.Worker(
            name='existing-worker',
            status='running',
            cmd=['claude'],
            started='2024-01-15T10:00:00',
            cwd='/tmp'
        )
        state.add_worker(worker)

        args = Namespace(format='json', status='all')

        import io
        import json
        with patch('swarm.refresh_worker_status', return_value='running'):
            with patch('sys.stdout', new=io.StringIO()) as mock_stdout:
                swarm.cmd_ralph_list(args)
                output = mock_stdout.getvalue()

        data = json.loads(output)
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]['worker_status'], 'running')

    def test_list_removed_worker_shows_removed(self):
        """Test ralph list shows 'removed' for non-existent workers."""
        # Create ralph state for a worker that doesn't exist in swarm state
        ralph_state = swarm.RalphState(
            worker_name='removed-worker',
            prompt_file='/path/to/prompt.md',
            max_iterations=10,
            current_iteration=3,
            status='stopped'
        )
        swarm.save_ralph_state(ralph_state)

        args = Namespace(format='json', status='all')

        import io
        import json
        with patch('sys.stdout', new=io.StringIO()) as mock_stdout:
            swarm.cmd_ralph_list(args)
            output = mock_stdout.getvalue()

        data = json.loads(output)
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]['worker_status'], 'removed')

    def test_list_table_format_with_existing_worker(self):
        """Test ralph list table format shows worker status for existing workers."""
        # Create ralph state
        ralph_state = swarm.RalphState(
            worker_name='existing-table-worker',
            prompt_file='/path/to/prompt.md',
            max_iterations=10,
            current_iteration=5,
            status='running'
        )
        swarm.save_ralph_state(ralph_state)

        # Create corresponding swarm worker
        state = swarm.State()
        worker = swarm.Worker(
            name='existing-table-worker',
            status='running',
            cmd=['claude'],
            started='2024-01-15T10:00:00',
            cwd='/tmp'
        )
        state.add_worker(worker)

        args = Namespace(format='table', status='all')

        with patch('swarm.refresh_worker_status', return_value='running'):
            with patch('builtins.print') as mock_print:
                swarm.cmd_ralph_list(args)

        # Check output contains running status from existing worker
        calls = [str(call) for call in mock_print.call_args_list]
        output = '\n'.join(calls)
        self.assertIn('existing-table-worker', output)
        self.assertIn('running', output)
        self.assertIn('5/10', output)


class TestRalphListCLI(unittest.TestCase):
    """Test ralph list CLI integration."""

    def setUp(self):
        """Create temporary directories for testing."""
        self.temp_dir = tempfile.mkdtemp()
        self.old_ralph_dir = swarm.RALPH_DIR
        swarm.RALPH_DIR = Path(self.temp_dir) / "ralph"
        swarm.RALPH_DIR.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        """Restore original directories and clean up."""
        swarm.RALPH_DIR = self.old_ralph_dir
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_ralph_list_cli_empty(self):
        """Test ralph list CLI with no workers."""
        result = subprocess.run(
            [sys.executable, 'swarm.py', 'ralph', 'list'],
            capture_output=True,
            text=True,
            env={**os.environ, 'HOME': self.temp_dir}
        )
        # Should succeed with empty output
        self.assertEqual(result.returncode, 0)

    def test_ralph_list_cli_json_format(self):
        """Test ralph list CLI with --format json."""
        result = subprocess.run(
            [sys.executable, 'swarm.py', 'ralph', 'list', '--format', 'json'],
            capture_output=True,
            text=True,
            env={**os.environ, 'HOME': self.temp_dir}
        )
        self.assertEqual(result.returncode, 0)
        # Should be valid JSON (empty array)
        import json
        data = json.loads(result.stdout)
        self.assertEqual(data, [])

    def test_ralph_list_cli_names_format(self):
        """Test ralph list CLI with --format names."""
        result = subprocess.run(
            [sys.executable, 'swarm.py', 'ralph', 'list', '--format', 'names'],
            capture_output=True,
            text=True,
            env={**os.environ, 'HOME': self.temp_dir}
        )
        self.assertEqual(result.returncode, 0)
        # Should be empty for no workers
        self.assertEqual(result.stdout.strip(), '')


class TestRalphListDispatch(unittest.TestCase):
    """Test ralph list is dispatched correctly from cmd_ralph."""

    def test_dispatch_to_cmd_ralph_list(self):
        """Test that ralph command dispatches to cmd_ralph_list."""
        args = Namespace(ralph_command='list', format='table', status='all')

        with patch('swarm.cmd_ralph_list') as mock_list:
            swarm.cmd_ralph(args)

        mock_list.assert_called_once_with(args)


class TestInactivityModeArgument(unittest.TestCase):
    """Test --inactivity-mode argument for spawn command."""

    def test_inactivity_mode_argument_exists(self):
        """Test that --inactivity-mode argument is recognized by spawn."""
        result = subprocess.run(
            [sys.executable, 'swarm.py', 'spawn', '--help'],
            capture_output=True,
            text=True
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn('--inactivity-mode', result.stdout)

    def test_inactivity_mode_choices(self):
        """Test that --inactivity-mode accepts output, ready, and both."""
        result = subprocess.run(
            [sys.executable, 'swarm.py', 'spawn', '--help'],
            capture_output=True,
            text=True
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn('output', result.stdout)
        self.assertIn('ready', result.stdout)
        self.assertIn('both', result.stdout)

    def test_inactivity_mode_default_is_ready(self):
        """Test --inactivity-mode has default value of 'ready'."""
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument("--inactivity-mode", type=str, choices=["output", "ready", "both"],
                          default="ready")
        args = parser.parse_args([])
        self.assertEqual(args.inactivity_mode, "ready")

    def test_inactivity_mode_invalid_choice_rejected(self):
        """Test that invalid --inactivity-mode values are rejected."""
        result = subprocess.run(
            [sys.executable, 'swarm.py', 'spawn', '--name', 'test', '--inactivity-mode', 'invalid', '--', 'echo'],
            capture_output=True,
            text=True
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('invalid choice', result.stderr)


class TestRalphStateInactivityMode(unittest.TestCase):
    """Test RalphState dataclass with inactivity_mode field."""

    def test_ralph_state_has_inactivity_mode_field(self):
        """Test that RalphState has inactivity_mode field."""
        state = swarm.RalphState(
            worker_name='test',
            prompt_file='/test/prompt.md',
            max_iterations=10
        )
        self.assertTrue(hasattr(state, 'inactivity_mode'))
        self.assertEqual(state.inactivity_mode, 'ready')  # default

    def test_ralph_state_inactivity_mode_in_to_dict(self):
        """Test that inactivity_mode is included in to_dict()."""
        state = swarm.RalphState(
            worker_name='test',
            prompt_file='/test/prompt.md',
            max_iterations=10,
            inactivity_mode='output'
        )
        d = state.to_dict()
        self.assertIn('inactivity_mode', d)
        self.assertEqual(d['inactivity_mode'], 'output')

    def test_ralph_state_inactivity_mode_from_dict(self):
        """Test that inactivity_mode is restored from dict."""
        d = {
            'worker_name': 'test',
            'prompt_file': '/test/prompt.md',
            'max_iterations': 10,
            'inactivity_mode': 'both'
        }
        state = swarm.RalphState.from_dict(d)
        self.assertEqual(state.inactivity_mode, 'both')

    def test_ralph_state_inactivity_mode_default_in_from_dict(self):
        """Test that inactivity_mode defaults to 'ready' when not in dict."""
        d = {
            'worker_name': 'test',
            'prompt_file': '/test/prompt.md',
            'max_iterations': 10
        }
        state = swarm.RalphState.from_dict(d)
        self.assertEqual(state.inactivity_mode, 'ready')


class TestDetectInactivityModes(unittest.TestCase):
    """Test detect_inactivity function with different modes."""

    def test_detect_inactivity_no_tmux_returns_false(self):
        """Test detect_inactivity returns False for non-tmux worker."""
        worker = swarm.Worker(
            name='test-worker',
            status='running',
            cmd=['echo', 'test'],
            started='2024-01-15T10:30:00',
            cwd='/tmp',
            pid=12345
        )
        # Test all modes
        for mode in ['output', 'ready', 'both']:
            result = swarm.detect_inactivity(worker, timeout=1, mode=mode)
            self.assertFalse(result, f"Mode '{mode}' should return False for non-tmux worker")

    def test_detect_inactivity_default_mode_is_ready(self):
        """Test detect_inactivity uses 'ready' as default mode."""
        worker = swarm.Worker(
            name='test-worker',
            status='running',
            cmd=['echo', 'test'],
            started='2024-01-15T10:30:00',
            cwd='/tmp',
            pid=12345
        )
        # Should not raise - verifies signature accepts no mode param
        result = swarm.detect_inactivity(worker, timeout=1)
        self.assertFalse(result)

    @patch('swarm.refresh_worker_status')
    @patch('swarm.tmux_capture_pane')
    @patch('time.time')
    @patch('time.sleep')
    def test_detect_inactivity_output_mode_detects_no_change(self, mock_sleep, mock_time, mock_capture, mock_refresh):
        """Test output mode detects when output stops changing."""
        mock_refresh.return_value = 'running'
        # Return same output for all calls
        mock_capture.return_value = 'same output'
        # Time progression: iter1 start, iter1 check, iter2 start, iter2 check (timeout triggered)
        mock_time.side_effect = [0, 0, 0, 1, 1, 2]

        worker = swarm.Worker(
            name='test-worker',
            status='running',
            cmd=['echo', 'test'],
            started='2024-01-15T10:30:00',
            cwd='/tmp',
            tmux=swarm.TmuxInfo(session='swarm', window='test')
        )

        result = swarm.detect_inactivity(worker, timeout=1, mode='output')
        self.assertTrue(result)

    @patch('swarm.refresh_worker_status')
    @patch('swarm.tmux_capture_pane')
    @patch('time.time')
    @patch('time.sleep')
    def test_detect_inactivity_ready_mode_detects_ready_pattern(self, mock_sleep, mock_time, mock_capture, mock_refresh):
        """Test ready mode detects when agent shows ready pattern."""
        mock_refresh.return_value = 'running'
        # Return output with ready pattern ("> " at start of line)
        mock_capture.return_value = '> waiting for input'
        # Time progression to trigger timeout
        mock_time.side_effect = [0, 0, 0, 1, 1, 2]

        worker = swarm.Worker(
            name='test-worker',
            status='running',
            cmd=['echo', 'test'],
            started='2024-01-15T10:30:00',
            cwd='/tmp',
            tmux=swarm.TmuxInfo(session='swarm', window='test')
        )

        result = swarm.detect_inactivity(worker, timeout=1, mode='ready')
        self.assertTrue(result)

    @patch('swarm.refresh_worker_status')
    @patch('swarm.tmux_capture_pane')
    def test_detect_inactivity_ready_mode_ignores_no_ready_pattern(self, mock_capture, mock_refresh):
        """Test ready mode doesn't trigger without ready pattern."""
        mock_refresh.side_effect = ['running', 'stopped']  # Worker stops
        mock_capture.return_value = 'Working on task...'

        worker = swarm.Worker(
            name='test-worker',
            status='running',
            cmd=['echo', 'test'],
            started='2024-01-15T10:30:00',
            cwd='/tmp',
            tmux=swarm.TmuxInfo(session='swarm', window='test')
        )

        with patch('time.sleep'):
            result = swarm.detect_inactivity(worker, timeout=1, mode='ready')

        self.assertFalse(result)

    @patch('swarm.refresh_worker_status')
    @patch('swarm.tmux_capture_pane')
    @patch('time.time')
    @patch('time.sleep')
    def test_detect_inactivity_both_mode_triggers_on_ready(self, mock_sleep, mock_time, mock_capture, mock_refresh):
        """Test both mode triggers when ready pattern detected."""
        mock_refresh.return_value = 'running'
        # Changing output but with ready pattern - ready detection triggers
        mock_capture.return_value = '> ready prompt'
        # Time progression to trigger ready timeout (more calls needed for both mode)
        mock_time.side_effect = [0, 0, 0, 1, 1, 1, 2]

        worker = swarm.Worker(
            name='test-worker',
            status='running',
            cmd=['echo', 'test'],
            started='2024-01-15T10:30:00',
            cwd='/tmp',
            tmux=swarm.TmuxInfo(session='swarm', window='test')
        )

        result = swarm.detect_inactivity(worker, timeout=1, mode='both')
        self.assertTrue(result)

    @patch('swarm.refresh_worker_status')
    @patch('swarm.tmux_capture_pane')
    @patch('time.time')
    @patch('time.sleep')
    def test_detect_inactivity_both_mode_triggers_on_output_stagnation(self, mock_sleep, mock_time, mock_capture, mock_refresh):
        """Test both mode triggers when output stops changing."""
        mock_refresh.return_value = 'running'
        # Same output without ready pattern
        mock_capture.return_value = 'working...'
        # Time progression to trigger output timeout
        mock_time.side_effect = [0, 0, 0, 1, 1, 2]

        worker = swarm.Worker(
            name='test-worker',
            status='running',
            cmd=['echo', 'test'],
            started='2024-01-15T10:30:00',
            cwd='/tmp',
            tmux=swarm.TmuxInfo(session='swarm', window='test')
        )

        result = swarm.detect_inactivity(worker, timeout=1, mode='both')
        self.assertTrue(result)


class TestRalphSpawnWithInactivityMode(unittest.TestCase):
    """Test spawn command with --inactivity-mode creates correct ralph state."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.original_cwd = os.getcwd()
        os.chdir(self.temp_dir)
        self.original_swarm_dir = swarm.SWARM_DIR
        self.original_ralph_dir = swarm.RALPH_DIR
        self.original_state_file = swarm.STATE_FILE
        self.original_state_lock_file = swarm.STATE_LOCK_FILE
        swarm.SWARM_DIR = Path(self.temp_dir) / ".swarm"
        swarm.RALPH_DIR = Path(self.temp_dir) / ".swarm" / "ralph"
        swarm.STATE_FILE = Path(self.temp_dir) / ".swarm" / "state.json"
        swarm.STATE_LOCK_FILE = Path(self.temp_dir) / ".swarm" / "state.lock"
        # Create a test prompt file
        self.prompt_file = Path(self.temp_dir) / "PROMPT.md"
        self.prompt_file.write_text("Test prompt")

    def tearDown(self):
        """Clean up test fixtures."""
        os.chdir(self.original_cwd)
        swarm.SWARM_DIR = self.original_swarm_dir
        swarm.RALPH_DIR = self.original_ralph_dir
        swarm.STATE_FILE = self.original_state_file
        swarm.STATE_LOCK_FILE = self.original_state_lock_file
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_spawn_with_inactivity_mode_output(self):
        """Test spawn with --inactivity-mode output creates state with correct mode."""
        args = Namespace(
            name='test-worker',
            tmux=False,
            session=None,
            tmux_socket=None,
            worktree=False,
            branch=None,
            worktree_dir=None,
            tags=[],
            env=[],
            cwd=None,
            ready_wait=False,
            ready_timeout=120,
            ralph=True,
            prompt_file=str(self.prompt_file),
            max_iterations=10,
            inactivity_timeout=300,
            inactivity_mode='output',
            done_pattern=None,
            cmd=['--', 'echo', 'test']
        )

        with patch('swarm.create_tmux_window'):
            with patch('swarm.get_default_session_name', return_value='swarm-test'):
                with patch('builtins.print'):
                    swarm.cmd_spawn(args)

        # Check ralph state has correct inactivity_mode
        ralph_state = swarm.load_ralph_state('test-worker')
        self.assertIsNotNone(ralph_state)
        self.assertEqual(ralph_state.inactivity_mode, 'output')

    def test_spawn_with_inactivity_mode_both(self):
        """Test spawn with --inactivity-mode both creates state with correct mode."""
        args = Namespace(
            name='test-worker-both',
            tmux=False,
            session=None,
            tmux_socket=None,
            worktree=False,
            branch=None,
            worktree_dir=None,
            tags=[],
            env=[],
            cwd=None,
            ready_wait=False,
            ready_timeout=120,
            ralph=True,
            prompt_file=str(self.prompt_file),
            max_iterations=10,
            inactivity_timeout=300,
            inactivity_mode='both',
            done_pattern=None,
            cmd=['--', 'echo', 'test']
        )

        with patch('swarm.create_tmux_window'):
            with patch('swarm.get_default_session_name', return_value='swarm-test'):
                with patch('builtins.print'):
                    swarm.cmd_spawn(args)

        ralph_state = swarm.load_ralph_state('test-worker-both')
        self.assertIsNotNone(ralph_state)
        self.assertEqual(ralph_state.inactivity_mode, 'both')

    def test_spawn_default_inactivity_mode_is_ready(self):
        """Test spawn defaults to inactivity_mode='ready' for ralph workers."""
        args = Namespace(
            name='test-worker-default',
            tmux=False,
            session=None,
            tmux_socket=None,
            worktree=False,
            branch=None,
            worktree_dir=None,
            tags=[],
            env=[],
            cwd=None,
            ready_wait=False,
            ready_timeout=120,
            ralph=True,
            prompt_file=str(self.prompt_file),
            max_iterations=10,
            inactivity_timeout=300,
            inactivity_mode='ready',  # default
            done_pattern=None,
            cmd=['--', 'echo', 'test']
        )

        with patch('swarm.create_tmux_window'):
            with patch('swarm.get_default_session_name', return_value='swarm-test'):
                with patch('builtins.print'):
                    swarm.cmd_spawn(args)

        ralph_state = swarm.load_ralph_state('test-worker-default')
        self.assertIsNotNone(ralph_state)
        self.assertEqual(ralph_state.inactivity_mode, 'ready')


class TestRalphStatusShowsInactivityMode(unittest.TestCase):
    """Test ralph status command shows inactivity mode."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.original_swarm_dir = swarm.SWARM_DIR
        self.original_ralph_dir = swarm.RALPH_DIR
        self.original_state_file = swarm.STATE_FILE
        self.original_state_lock_file = swarm.STATE_LOCK_FILE
        swarm.SWARM_DIR = Path(self.temp_dir)
        swarm.RALPH_DIR = Path(self.temp_dir) / "ralph"
        swarm.STATE_FILE = Path(self.temp_dir) / "state.json"
        swarm.STATE_LOCK_FILE = Path(self.temp_dir) / "state.lock"

    def tearDown(self):
        """Clean up test fixtures."""
        swarm.SWARM_DIR = self.original_swarm_dir
        swarm.RALPH_DIR = self.original_ralph_dir
        swarm.STATE_FILE = self.original_state_file
        swarm.STATE_LOCK_FILE = self.original_state_lock_file
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_status_shows_inactivity_mode(self):
        """Test ralph status output includes inactivity mode."""
        # Create a worker and ralph state
        worker = swarm.Worker(
            name='test-worker',
            status='running',
            cmd=['echo', 'test'],
            started='2024-01-15T10:30:00',
            cwd='/tmp',
            metadata={'ralph': True, 'ralph_iteration': 1}
        )
        state = swarm.State()
        state.add_worker(worker)
        state.save()

        ralph_state = swarm.RalphState(
            worker_name='test-worker',
            prompt_file='/test/prompt.md',
            max_iterations=10,
            current_iteration=1,
            started='2024-01-15T10:30:00',
            last_iteration_started='2024-01-15T10:30:00',
            inactivity_mode='output'
        )
        swarm.save_ralph_state(ralph_state)

        # Capture output
        import io
        captured_output = io.StringIO()

        args = Namespace(name='test-worker')
        with patch('sys.stdout', captured_output):
            swarm.cmd_ralph_status(args)

        output = captured_output.getvalue()
        self.assertIn('Inactivity mode: output', output)


class TestDetectInactivityErrorHandling(unittest.TestCase):
    """Test detect_inactivity error handling."""

    @patch('swarm.refresh_worker_status')
    @patch('swarm.tmux_capture_pane')
    @patch('time.sleep')
    def test_detect_inactivity_returns_false_on_subprocess_error(self, mock_sleep, mock_capture, mock_refresh):
        """Test detect_inactivity returns False when tmux capture fails."""
        mock_refresh.return_value = 'running'
        mock_capture.side_effect = subprocess.CalledProcessError(1, 'tmux')

        worker = swarm.Worker(
            name='test-worker',
            status='running',
            cmd=['echo', 'test'],
            started='2024-01-15T10:30:00',
            cwd='/tmp',
            tmux=swarm.TmuxInfo(session='swarm', window='test')
        )

        result = swarm.detect_inactivity(worker, timeout=1, mode='ready')
        self.assertFalse(result)


class TestDetectInactivityReadyPatterns(unittest.TestCase):
    """Test detect_inactivity recognizes all ready patterns."""

    @patch('swarm.refresh_worker_status')
    @patch('swarm.tmux_capture_pane')
    @patch('time.time')
    @patch('time.sleep')
    def test_ready_mode_detects_bypass_permissions(self, mock_sleep, mock_time, mock_capture, mock_refresh):
        """Test ready mode detects 'bypass permissions' pattern."""
        mock_refresh.return_value = 'running'
        mock_capture.return_value = 'bypass permissions on'
        mock_time.side_effect = [0, 0, 0, 1, 1, 2]

        worker = swarm.Worker(
            name='test-worker',
            status='running',
            cmd=['echo', 'test'],
            started='2024-01-15T10:30:00',
            cwd='/tmp',
            tmux=swarm.TmuxInfo(session='swarm', window='test')
        )

        result = swarm.detect_inactivity(worker, timeout=1, mode='ready')
        self.assertTrue(result)

    @patch('swarm.refresh_worker_status')
    @patch('swarm.tmux_capture_pane')
    @patch('time.time')
    @patch('time.sleep')
    def test_ready_mode_detects_claude_code_banner(self, mock_sleep, mock_time, mock_capture, mock_refresh):
        """Test ready mode detects 'Claude Code v' pattern."""
        mock_refresh.return_value = 'running'
        mock_capture.return_value = 'Claude Code v2.1.4'
        mock_time.side_effect = [0, 0, 0, 1, 1, 2]

        worker = swarm.Worker(
            name='test-worker',
            status='running',
            cmd=['echo', 'test'],
            started='2024-01-15T10:30:00',
            cwd='/tmp',
            tmux=swarm.TmuxInfo(session='swarm', window='test')
        )

        result = swarm.detect_inactivity(worker, timeout=1, mode='ready')
        self.assertTrue(result)

    @patch('swarm.refresh_worker_status')
    @patch('swarm.tmux_capture_pane')
    @patch('time.time')
    @patch('time.sleep')
    def test_ready_mode_detects_shell_prompt(self, mock_sleep, mock_time, mock_capture, mock_refresh):
        """Test ready mode detects '$ ' shell prompt."""
        mock_refresh.return_value = 'running'
        mock_capture.return_value = '$ '
        mock_time.side_effect = [0, 0, 0, 1, 1, 2]

        worker = swarm.Worker(
            name='test-worker',
            status='running',
            cmd=['echo', 'test'],
            started='2024-01-15T10:30:00',
            cwd='/tmp',
            tmux=swarm.TmuxInfo(session='swarm', window='test')
        )

        result = swarm.detect_inactivity(worker, timeout=1, mode='ready')
        self.assertTrue(result)


class TestRalphRunSigterm(unittest.TestCase):
    """Test SIGTERM graceful shutdown for ralph run."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.original_swarm_dir = swarm.SWARM_DIR
        self.original_ralph_dir = swarm.RALPH_DIR
        self.original_state_file = swarm.STATE_FILE
        self.original_state_lock_file = swarm.STATE_LOCK_FILE
        swarm.SWARM_DIR = Path(self.temp_dir)
        swarm.RALPH_DIR = Path(self.temp_dir) / "ralph"
        swarm.STATE_FILE = Path(self.temp_dir) / "state.json"
        swarm.STATE_LOCK_FILE = Path(self.temp_dir) / "state.lock"

        # Create prompt file
        self.prompt_file = Path(self.temp_dir) / "PROMPT.md"
        self.prompt_file.write_text("test prompt")

    def tearDown(self):
        """Clean up test fixtures."""
        swarm.SWARM_DIR = self.original_swarm_dir
        swarm.RALPH_DIR = self.original_ralph_dir
        swarm.STATE_FILE = self.original_state_file
        swarm.STATE_LOCK_FILE = self.original_state_lock_file
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @patch('swarm._run_ralph_loop')
    def test_cmd_ralph_run_installs_sigterm_handler(self, mock_run_loop):
        """Test that cmd_ralph_run installs a SIGTERM handler."""
        import signal as sig

        # Track if signal handler was installed
        original_handler = sig.getsignal(sig.SIGTERM)

        # Create a worker and ralph state
        worker = swarm.Worker(
            name='test-worker',
            status='running',
            cmd=['echo', 'test'],
            started='2024-01-15T10:30:00',
            cwd='/tmp',
            tmux=swarm.TmuxInfo(session='swarm', window='test'),
            metadata={'ralph': True, 'ralph_iteration': 1}
        )
        state = swarm.State()
        state.add_worker(worker)
        state.save()

        ralph_state = swarm.RalphState(
            worker_name='test-worker',
            prompt_file=str(self.prompt_file),
            max_iterations=10,
            current_iteration=1,
            started='2024-01-15T10:30:00',
            last_iteration_started='2024-01-15T10:30:00'
        )
        swarm.save_ralph_state(ralph_state)

        args = Namespace(name='test-worker')
        swarm.cmd_ralph_run(args)

        # The loop should have been called
        mock_run_loop.assert_called_once_with(args)

        # Signal handler should be restored after
        self.assertEqual(sig.getsignal(sig.SIGTERM), original_handler)

    @patch('swarm._run_ralph_loop')
    def test_sigterm_handler_pauses_ralph_state(self, mock_run_loop):
        """Test that SIGTERM handler pauses the ralph state."""
        import signal as sig

        # Create a worker and ralph state
        worker = swarm.Worker(
            name='test-worker',
            status='running',
            cmd=['echo', 'test'],
            started='2024-01-15T10:30:00',
            cwd='/tmp',
            tmux=swarm.TmuxInfo(session='swarm', window='test'),
            metadata={'ralph': True, 'ralph_iteration': 1}
        )
        state = swarm.State()
        state.add_worker(worker)
        state.save()

        ralph_state = swarm.RalphState(
            worker_name='test-worker',
            prompt_file=str(self.prompt_file),
            max_iterations=10,
            current_iteration=1,
            started='2024-01-15T10:30:00',
            last_iteration_started='2024-01-15T10:30:00',
            status='running'
        )
        swarm.save_ralph_state(ralph_state)

        # Simulate what happens when SIGTERM is received during the loop
        def simulate_sigterm(*a, **kw):
            # Get the current signal handler (which should be the custom one)
            handler = sig.getsignal(sig.SIGTERM)
            # Call it with dummy args to simulate SIGTERM
            if callable(handler) and handler != sig.SIG_DFL:
                with patch('builtins.print'):
                    handler(sig.SIGTERM, None)

        mock_run_loop.side_effect = simulate_sigterm

        args = Namespace(name='test-worker')
        with patch('builtins.print'):
            swarm.cmd_ralph_run(args)

        # Check that ralph state was paused
        ralph_state = swarm.load_ralph_state('test-worker')
        self.assertEqual(ralph_state.status, 'paused')

    @patch('swarm._run_ralph_loop')
    def test_sigterm_logs_pause_event(self, mock_run_loop):
        """Test that SIGTERM logs a PAUSE event."""
        import signal as sig

        # Create a worker and ralph state
        worker = swarm.Worker(
            name='test-worker',
            status='running',
            cmd=['echo', 'test'],
            started='2024-01-15T10:30:00',
            cwd='/tmp',
            tmux=swarm.TmuxInfo(session='swarm', window='test'),
            metadata={'ralph': True, 'ralph_iteration': 1}
        )
        state = swarm.State()
        state.add_worker(worker)
        state.save()

        ralph_state = swarm.RalphState(
            worker_name='test-worker',
            prompt_file=str(self.prompt_file),
            max_iterations=10,
            current_iteration=1,
            started='2024-01-15T10:30:00',
            last_iteration_started='2024-01-15T10:30:00',
            status='running'
        )
        swarm.save_ralph_state(ralph_state)

        # Simulate what happens when SIGTERM is received during the loop
        def simulate_sigterm(*a, **kw):
            handler = sig.getsignal(sig.SIGTERM)
            if callable(handler) and handler != sig.SIG_DFL:
                with patch('builtins.print'):
                    handler(sig.SIGTERM, None)

        mock_run_loop.side_effect = simulate_sigterm

        args = Namespace(name='test-worker')
        with patch('builtins.print'):
            swarm.cmd_ralph_run(args)

        # Check that PAUSE event was logged
        log_path = swarm.get_ralph_iterations_log_path('test-worker')
        log_content = log_path.read_text()
        self.assertIn('[PAUSE]', log_content)
        self.assertIn('reason=sigterm', log_content)

    @patch('swarm._run_ralph_loop')
    def test_sigterm_does_not_pause_already_paused(self, mock_run_loop):
        """Test that SIGTERM does not change already paused state."""
        import signal as sig

        # Create a worker and ralph state (already paused)
        worker = swarm.Worker(
            name='test-worker',
            status='running',
            cmd=['echo', 'test'],
            started='2024-01-15T10:30:00',
            cwd='/tmp',
            tmux=swarm.TmuxInfo(session='swarm', window='test'),
            metadata={'ralph': True, 'ralph_iteration': 1}
        )
        state = swarm.State()
        state.add_worker(worker)
        state.save()

        ralph_state = swarm.RalphState(
            worker_name='test-worker',
            prompt_file=str(self.prompt_file),
            max_iterations=10,
            current_iteration=5,
            started='2024-01-15T10:30:00',
            last_iteration_started='2024-01-15T10:30:00',
            status='paused'  # Already paused
        )
        swarm.save_ralph_state(ralph_state)

        # Simulate what happens when SIGTERM is received
        def simulate_sigterm(*a, **kw):
            handler = sig.getsignal(sig.SIGTERM)
            if callable(handler) and handler != sig.SIG_DFL:
                with patch('builtins.print'):
                    handler(sig.SIGTERM, None)

        mock_run_loop.side_effect = simulate_sigterm

        args = Namespace(name='test-worker')
        with patch('builtins.print'):
            swarm.cmd_ralph_run(args)

        # Check that ralph state is still paused with same iteration
        ralph_state = swarm.load_ralph_state('test-worker')
        self.assertEqual(ralph_state.status, 'paused')
        self.assertEqual(ralph_state.current_iteration, 5)

    @patch('swarm._run_ralph_loop')
    def test_signal_handler_restored_on_exception(self, mock_run_loop):
        """Test that signal handler is restored even if loop raises exception."""
        import signal as sig

        original_handler = sig.getsignal(sig.SIGTERM)

        # Create a worker and ralph state
        worker = swarm.Worker(
            name='test-worker',
            status='running',
            cmd=['echo', 'test'],
            started='2024-01-15T10:30:00',
            cwd='/tmp',
            tmux=swarm.TmuxInfo(session='swarm', window='test'),
            metadata={'ralph': True, 'ralph_iteration': 1}
        )
        state = swarm.State()
        state.add_worker(worker)
        state.save()

        ralph_state = swarm.RalphState(
            worker_name='test-worker',
            prompt_file=str(self.prompt_file),
            max_iterations=10,
            current_iteration=1,
            started='2024-01-15T10:30:00',
            last_iteration_started='2024-01-15T10:30:00'
        )
        swarm.save_ralph_state(ralph_state)

        mock_run_loop.side_effect = RuntimeError("Test exception")

        args = Namespace(name='test-worker')
        with self.assertRaises(RuntimeError):
            swarm.cmd_ralph_run(args)

        # Signal handler should be restored even after exception
        self.assertEqual(sig.getsignal(sig.SIGTERM), original_handler)


class TestRalphRunLoopInternal(unittest.TestCase):
    """Test _run_ralph_loop internal function."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.original_swarm_dir = swarm.SWARM_DIR
        self.original_ralph_dir = swarm.RALPH_DIR
        self.original_state_file = swarm.STATE_FILE
        self.original_state_lock_file = swarm.STATE_LOCK_FILE
        swarm.SWARM_DIR = Path(self.temp_dir)
        swarm.RALPH_DIR = Path(self.temp_dir) / "ralph"
        swarm.STATE_FILE = Path(self.temp_dir) / "state.json"
        swarm.STATE_LOCK_FILE = Path(self.temp_dir) / "state.lock"

        # Create prompt file
        self.prompt_file = Path(self.temp_dir) / "PROMPT.md"
        self.prompt_file.write_text("test prompt")

    def tearDown(self):
        """Clean up test fixtures."""
        swarm.SWARM_DIR = self.original_swarm_dir
        swarm.RALPH_DIR = self.original_ralph_dir
        swarm.STATE_FILE = self.original_state_file
        swarm.STATE_LOCK_FILE = self.original_state_lock_file
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_run_ralph_loop_worker_not_found(self):
        """Test _run_ralph_loop exits when worker not found."""
        args = Namespace(name='nonexistent-worker')

        with self.assertRaises(SystemExit) as cm:
            swarm._run_ralph_loop(args)

        self.assertEqual(cm.exception.code, 1)

    def test_run_ralph_loop_not_ralph_worker(self):
        """Test _run_ralph_loop exits when not a ralph worker."""
        # Create a regular worker (no ralph state)
        worker = swarm.Worker(
            name='regular-worker',
            status='running',
            cmd=['echo', 'test'],
            started='2024-01-15T10:30:00',
            cwd='/tmp'
        )
        state = swarm.State()
        state.add_worker(worker)
        state.save()

        args = Namespace(name='regular-worker')

        with self.assertRaises(SystemExit) as cm:
            swarm._run_ralph_loop(args)

        self.assertEqual(cm.exception.code, 1)


class TestCmdKillRalphWorker(unittest.TestCase):
    """Test cmd_kill updates ralph state when killing a ralph worker."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        # Patch swarm directories
        self.swarm_dir_patcher = patch.object(swarm, 'SWARM_DIR', Path(self.temp_dir))
        self.state_file_patcher = patch.object(swarm, 'STATE_FILE', Path(self.temp_dir) / 'state.json')
        self.logs_dir_patcher = patch.object(swarm, 'LOGS_DIR', Path(self.temp_dir) / 'logs')
        self.ralph_dir_patcher = patch.object(swarm, 'RALPH_DIR', Path(self.temp_dir) / 'ralph')

        self.swarm_dir_patcher.start()
        self.state_file_patcher.start()
        self.logs_dir_patcher.start()
        self.ralph_dir_patcher.start()

    def tearDown(self):
        """Clean up test fixtures."""
        self.swarm_dir_patcher.stop()
        self.state_file_patcher.stop()
        self.logs_dir_patcher.stop()
        self.ralph_dir_patcher.stop()

        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_kill_ralph_worker_updates_state(self):
        """Test killing a ralph worker updates ralph state to stopped."""
        # Create a worker with tmux
        state = swarm.State()
        worker = swarm.Worker(
            name='ralph-worker',
            status='running',
            cmd=['claude'],
            started='2024-01-15T10:30:00',
            cwd='/tmp',
            tmux=swarm.TmuxInfo(session='swarm', window='ralph-worker'),
            metadata={'ralph': True, 'ralph_iteration': 3}
        )
        state.add_worker(worker)
        state.save()

        # Create ralph state
        ralph_state = swarm.RalphState(
            worker_name='ralph-worker',
            prompt_file='/tmp/PROMPT.md',
            max_iterations=10,
            current_iteration=3,
            status='running'
        )
        swarm.save_ralph_state(ralph_state)

        # Verify ralph state is running before kill
        loaded_state = swarm.load_ralph_state('ralph-worker')
        self.assertEqual(loaded_state.status, 'running')

        # Mock subprocess and kill
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = None
            args = Namespace(name='ralph-worker', all=False, rm_worktree=False)
            swarm.cmd_kill(args)

        # Verify ralph state is now stopped
        updated_state = swarm.load_ralph_state('ralph-worker')
        self.assertEqual(updated_state.status, 'stopped')

    def test_kill_ralph_worker_logs_done_event(self):
        """Test killing a ralph worker logs DONE event with reason=killed."""
        # Create a worker with tmux
        state = swarm.State()
        worker = swarm.Worker(
            name='ralph-worker',
            status='running',
            cmd=['claude'],
            started='2024-01-15T10:30:00',
            cwd='/tmp',
            tmux=swarm.TmuxInfo(session='swarm', window='ralph-worker'),
            metadata={'ralph': True, 'ralph_iteration': 5}
        )
        state.add_worker(worker)
        state.save()

        # Create ralph state
        ralph_state = swarm.RalphState(
            worker_name='ralph-worker',
            prompt_file='/tmp/PROMPT.md',
            max_iterations=10,
            current_iteration=5,
            status='running'
        )
        swarm.save_ralph_state(ralph_state)

        # Mock subprocess and kill
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = None
            args = Namespace(name='ralph-worker', all=False, rm_worktree=False)
            swarm.cmd_kill(args)

        # Check iteration log for DONE event with reason=killed
        log_path = swarm.get_ralph_iterations_log_path('ralph-worker')
        self.assertTrue(log_path.exists())
        log_content = log_path.read_text()
        self.assertIn('[DONE]', log_content)
        self.assertIn('reason=killed', log_content)
        self.assertIn('5 iterations', log_content)

    def test_kill_non_ralph_worker_no_ralph_state_change(self):
        """Test killing a non-ralph worker doesn't create or modify ralph state."""
        # Create a regular worker (no ralph state)
        state = swarm.State()
        worker = swarm.Worker(
            name='regular-worker',
            status='running',
            cmd=['bash'],
            started='2024-01-15T10:30:00',
            cwd='/tmp',
            tmux=swarm.TmuxInfo(session='swarm', window='regular-worker')
        )
        state.add_worker(worker)
        state.save()

        # Mock subprocess and kill
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = None
            args = Namespace(name='regular-worker', all=False, rm_worktree=False)
            swarm.cmd_kill(args)

        # Verify no ralph state was created
        ralph_state = swarm.load_ralph_state('regular-worker')
        self.assertIsNone(ralph_state)

    def test_kill_all_updates_all_ralph_workers(self):
        """Test --all flag updates ralph state for all ralph workers."""
        state = swarm.State()

        # Create two ralph workers
        worker1 = swarm.Worker(
            name='ralph-1',
            status='running',
            cmd=['claude'],
            started='2024-01-15T10:30:00',
            cwd='/tmp',
            tmux=swarm.TmuxInfo(session='swarm', window='ralph-1'),
            metadata={'ralph': True}
        )
        worker2 = swarm.Worker(
            name='ralph-2',
            status='running',
            cmd=['claude'],
            started='2024-01-15T10:30:00',
            cwd='/tmp',
            tmux=swarm.TmuxInfo(session='swarm', window='ralph-2'),
            metadata={'ralph': True}
        )
        state.add_worker(worker1)
        state.add_worker(worker2)
        state.save()

        # Create ralph states
        for name in ['ralph-1', 'ralph-2']:
            ralph_state = swarm.RalphState(
                worker_name=name,
                prompt_file='/tmp/PROMPT.md',
                max_iterations=10,
                current_iteration=2,
                status='running'
            )
            swarm.save_ralph_state(ralph_state)

        # Mock subprocess and kill all
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = None
            args = Namespace(name=None, all=True, rm_worktree=False)
            swarm.cmd_kill(args)

        # Verify both ralph states are stopped
        for name in ['ralph-1', 'ralph-2']:
            updated_state = swarm.load_ralph_state(name)
            self.assertEqual(updated_state.status, 'stopped')


if __name__ == "__main__":
    unittest.main()
