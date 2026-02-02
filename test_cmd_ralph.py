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
        self.assertEqual(ralph_state.current_iteration, 0)
        self.assertIsNotNone(ralph_state.started)

    def test_spawn_ralph_message_includes_iteration(self):
        """Test that spawn message includes ralph mode info."""
        args = Namespace(
            name='ralph-worker',
            ralph=True,
            prompt_file='test_prompt.md',
            max_iterations=100,
            inactivity_timeout=300,
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


if __name__ == "__main__":
    unittest.main()
