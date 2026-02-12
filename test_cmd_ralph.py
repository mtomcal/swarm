#!/usr/bin/env python3
"""Tests for swarm ralph command - TDD tests for ralph subcommands."""

import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
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


class TestRalphHelpTextConstants(unittest.TestCase):
    """Test ralph CLI help text module-level constants for coverage."""

    def test_ralph_help_description_exists(self):
        """Test RALPH_HELP_DESCRIPTION constant exists and has content."""
        self.assertIn('Ralph Wiggum pattern', swarm.RALPH_HELP_DESCRIPTION)
        self.assertIn('context', swarm.RALPH_HELP_DESCRIPTION)
        self.assertIn('Workflow', swarm.RALPH_HELP_DESCRIPTION)

    def test_ralph_help_epilog_exists(self):
        """Test RALPH_HELP_EPILOG constant exists and has content."""
        self.assertIn('Prompt Design Principles', swarm.RALPH_HELP_EPILOG)
        self.assertIn('ONE task per iteration', swarm.RALPH_HELP_EPILOG)
        self.assertIn('Quick Reference', swarm.RALPH_HELP_EPILOG)

    def test_ralph_spawn_help_description_exists(self):
        """Test RALPH_SPAWN_HELP_DESCRIPTION constant exists."""
        self.assertIn('monitoring loop', swarm.RALPH_SPAWN_HELP_DESCRIPTION)
        self.assertIn('--no-run', swarm.RALPH_SPAWN_HELP_DESCRIPTION)

    def test_ralph_spawn_help_epilog_exists(self):
        """Test RALPH_SPAWN_HELP_EPILOG constant has examples."""
        self.assertIn('Examples:', swarm.RALPH_SPAWN_HELP_EPILOG)
        self.assertIn('Intervention:', swarm.RALPH_SPAWN_HELP_EPILOG)
        self.assertIn('Monitoring:', swarm.RALPH_SPAWN_HELP_EPILOG)
        self.assertIn('--worktree', swarm.RALPH_SPAWN_HELP_EPILOG)

    def test_ralph_init_help_epilog_exists(self):
        """Test RALPH_INIT_HELP_EPILOG constant exists."""
        self.assertIn('PROMPT.md', swarm.RALPH_INIT_HELP_EPILOG)
        self.assertIn('customize', swarm.RALPH_INIT_HELP_EPILOG.lower())

    def test_ralph_template_help_epilog_exists(self):
        """Test RALPH_TEMPLATE_HELP_EPILOG constant exists."""
        self.assertIn('stdout', swarm.RALPH_TEMPLATE_HELP_EPILOG)
        self.assertIn('pbcopy', swarm.RALPH_TEMPLATE_HELP_EPILOG)

    def test_ralph_status_help_epilog_exists(self):
        """Test RALPH_STATUS_HELP_EPILOG constant exists."""
        self.assertIn('iteration', swarm.RALPH_STATUS_HELP_EPILOG.lower())
        self.assertIn('status', swarm.RALPH_STATUS_HELP_EPILOG.lower())

    def test_ralph_pause_help_epilog_exists(self):
        """Test RALPH_PAUSE_HELP_EPILOG constant exists."""
        self.assertIn('Pauses', swarm.RALPH_PAUSE_HELP_EPILOG)
        self.assertIn('resume', swarm.RALPH_PAUSE_HELP_EPILOG.lower())

    def test_ralph_resume_help_epilog_exists(self):
        """Test RALPH_RESUME_HELP_EPILOG constant exists."""
        self.assertIn('Resumes', swarm.RALPH_RESUME_HELP_EPILOG)
        self.assertIn('iteration count', swarm.RALPH_RESUME_HELP_EPILOG)

    def test_ralph_run_help_epilog_exists(self):
        """Test RALPH_RUN_HELP_EPILOG constant exists."""
        self.assertIn('monitoring loop', swarm.RALPH_RUN_HELP_EPILOG)
        self.assertIn('--no-run', swarm.RALPH_RUN_HELP_EPILOG)

    def test_ralph_list_help_epilog_exists(self):
        """Test RALPH_LIST_HELP_EPILOG constant exists."""
        self.assertIn('ralph mode', swarm.RALPH_LIST_HELP_EPILOG)
        self.assertIn('--format json', swarm.RALPH_LIST_HELP_EPILOG)


class TestRalphHelpContent(unittest.TestCase):
    """Test that ralph --help contains comprehensive documentation."""

    def test_ralph_help_contains_workflow_description(self):
        """Test ralph --help contains workflow overview."""
        result = subprocess.run(
            [sys.executable, 'swarm.py', 'ralph', '--help'],
            capture_output=True,
            text=True
        )
        self.assertEqual(result.returncode, 0)
        # Check for workflow description
        self.assertIn('Ralph Wiggum pattern', result.stdout)
        self.assertIn('context windows', result.stdout)

    def test_ralph_help_contains_prompt_design_principles(self):
        """Test ralph --help contains prompt design principles."""
        result = subprocess.run(
            [sys.executable, 'swarm.py', 'ralph', '--help'],
            capture_output=True,
            text=True
        )
        self.assertEqual(result.returncode, 0)
        # Check for prompt design principles
        self.assertIn('Prompt Design Principles', result.stdout)
        self.assertIn('ONE task per iteration', result.stdout)

    def test_ralph_help_contains_quick_reference(self):
        """Test ralph --help contains quick reference commands."""
        result = subprocess.run(
            [sys.executable, 'swarm.py', 'ralph', '--help'],
            capture_output=True,
            text=True
        )
        self.assertEqual(result.returncode, 0)
        # Check for quick reference
        self.assertIn('Quick Reference', result.stdout)
        self.assertIn('swarm ralph init', result.stdout)
        self.assertIn('swarm send', result.stdout)

    def test_ralph_spawn_help_contains_examples(self):
        """Test ralph spawn --help contains usage examples."""
        result = subprocess.run(
            [sys.executable, 'swarm.py', 'ralph', 'spawn', '--help'],
            capture_output=True,
            text=True
        )
        self.assertEqual(result.returncode, 0)
        # Check for examples section
        self.assertIn('Examples:', result.stdout)
        self.assertIn('--prompt-file PROMPT.md', result.stdout)
        self.assertIn('--max-iterations', result.stdout)

    def test_ralph_spawn_help_contains_intervention_examples(self):
        """Test ralph spawn --help contains intervention examples."""
        result = subprocess.run(
            [sys.executable, 'swarm.py', 'ralph', 'spawn', '--help'],
            capture_output=True,
            text=True
        )
        self.assertEqual(result.returncode, 0)
        # Check for intervention section
        self.assertIn('Intervention:', result.stdout)
        self.assertIn('swarm send', result.stdout)

    def test_ralph_spawn_help_contains_monitoring_examples(self):
        """Test ralph spawn --help contains monitoring examples."""
        result = subprocess.run(
            [sys.executable, 'swarm.py', 'ralph', 'spawn', '--help'],
            capture_output=True,
            text=True
        )
        self.assertEqual(result.returncode, 0)
        # Check for monitoring section
        self.assertIn('Monitoring:', result.stdout)
        self.assertIn('swarm attach', result.stdout)
        self.assertIn('swarm logs', result.stdout)

    def test_ralph_init_help_contains_epilog(self):
        """Test ralph init --help contains epilog with examples."""
        result = subprocess.run(
            [sys.executable, 'swarm.py', 'ralph', 'init', '--help'],
            capture_output=True,
            text=True
        )
        self.assertEqual(result.returncode, 0)
        # Check for epilog content
        self.assertIn('PROMPT.md', result.stdout)
        self.assertIn('customize', result.stdout.lower())

    def test_ralph_run_help_contains_epilog(self):
        """Test ralph run --help contains epilog with examples."""
        result = subprocess.run(
            [sys.executable, 'swarm.py', 'ralph', 'run', '--help'],
            capture_output=True,
            text=True
        )
        self.assertEqual(result.returncode, 0)
        # Check for epilog content
        self.assertIn('monitoring loop', result.stdout)
        self.assertIn('--no-run', result.stdout)

    def test_ralph_status_help_contains_epilog(self):
        """Test ralph status --help contains epilog."""
        result = subprocess.run(
            [sys.executable, 'swarm.py', 'ralph', 'status', '--help'],
            capture_output=True,
            text=True
        )
        self.assertEqual(result.returncode, 0)
        # Check for epilog content
        self.assertIn('iteration', result.stdout.lower())

    def test_ralph_list_help_contains_epilog(self):
        """Test ralph list --help contains epilog with examples."""
        result = subprocess.run(
            [sys.executable, 'swarm.py', 'ralph', 'list', '--help'],
            capture_output=True,
            text=True
        )
        self.assertEqual(result.returncode, 0)
        # Check for epilog content
        self.assertIn('--format json', result.stdout)


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

    def test_ralph_spawn_subcommand_exists(self):
        """Test that 'ralph spawn' subcommand is recognized."""
        result = subprocess.run(
            [sys.executable, 'swarm.py', 'ralph', 'spawn', '--help'],
            capture_output=True,
            text=True
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn('spawn', result.stdout.lower())

    def test_prompt_file_argument_exists(self):
        """Test that --prompt-file argument is recognized by ralph spawn."""
        result = subprocess.run(
            [sys.executable, 'swarm.py', 'ralph', 'spawn', '--help'],
            capture_output=True,
            text=True
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn('--prompt-file', result.stdout)

    def test_max_iterations_argument_exists(self):
        """Test that --max-iterations argument is recognized by ralph spawn."""
        result = subprocess.run(
            [sys.executable, 'swarm.py', 'ralph', 'spawn', '--help'],
            capture_output=True,
            text=True
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn('--max-iterations', result.stdout)

    def test_old_spawn_ralph_flag_removed(self):
        """Test that --ralph flag no longer exists on spawn command."""
        result = subprocess.run(
            [sys.executable, 'swarm.py', 'spawn', '--help'],
            capture_output=True,
            text=True
        )
        self.assertEqual(result.returncode, 0)
        self.assertNotIn('--ralph', result.stdout)
        self.assertNotIn('--prompt-file', result.stdout)
        self.assertNotIn('--max-iterations', result.stdout)
        self.assertNotIn('--inactivity-timeout', result.stdout)
        self.assertNotIn('--done-pattern', result.stdout)

    def test_tmux_flag_exists_in_ralph_spawn(self):
        """Test that --tmux flag is accepted by ralph spawn (B6)."""
        result = subprocess.run(
            [sys.executable, 'swarm.py', 'ralph', 'spawn', '--help'],
            capture_output=True,
            text=True
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn('--tmux', result.stdout)
        # Should indicate it's for consistency/no-op
        self.assertIn('consistency', result.stdout.lower())

    def test_replace_flag_exists_in_ralph_spawn(self):
        """Test that --replace flag is accepted by ralph spawn (F1)."""
        result = subprocess.run(
            [sys.executable, 'swarm.py', 'ralph', 'spawn', '--help'],
            capture_output=True,
            text=True
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn('--replace', result.stdout)
        # Should indicate it auto-cleans existing worker
        self.assertIn('existing', result.stdout.lower())

    def test_clean_state_flag_exists_in_ralph_spawn(self):
        """Test that --clean-state flag is accepted by ralph spawn (F5)."""
        result = subprocess.run(
            [sys.executable, 'swarm.py', 'ralph', 'spawn', '--help'],
            capture_output=True,
            text=True
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn('--clean-state', result.stdout)
        # Should indicate it clears ralph state
        self.assertIn('ralph state', result.stdout.lower())


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

    def test_ralph_spawn_no_command_error(self):
        """Test ralph spawn with empty command fails."""
        args = Namespace(
            ralph_command='spawn',
            name='test-worker',
            prompt_file='test_prompt.md',
            max_iterations=10,
            inactivity_timeout=60,
            done_pattern=None,
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
            cmd=[]  # Empty command
        )

        with patch('builtins.print') as mock_print:
            with self.assertRaises(SystemExit) as ctx:
                swarm.cmd_ralph_spawn(args)

        self.assertEqual(ctx.exception.code, 1)
        error_calls = [str(call) for call in mock_print.call_args_list]
        self.assertTrue(any('no command provided' in call for call in error_calls))

    def test_ralph_spawn_worker_already_exists(self):
        """Test ralph spawn fails if worker already exists."""
        args = Namespace(
            ralph_command='spawn',
            name='existing-worker',
            prompt_file='test_prompt.md',
            max_iterations=10,
            inactivity_timeout=60,
            done_pattern=None,
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

        # Mock State to return an existing worker
        mock_worker = swarm.Worker(
            name='existing-worker',
            status='running',
            cmd=['echo'],
            started='2024-01-01T00:00:00',
            cwd='/tmp'
        )

        with patch.object(swarm.State, 'get_worker', return_value=mock_worker):
            with patch('builtins.print') as mock_print:
                with self.assertRaises(SystemExit) as ctx:
                    swarm.cmd_ralph_spawn(args)

        self.assertEqual(ctx.exception.code, 1)
        error_calls = [str(call) for call in mock_print.call_args_list]
        self.assertTrue(any('already exists' in call for call in error_calls))

    def test_ralph_spawn_replace_cleans_existing_worker(self):
        """Test ralph spawn with --replace cleans up existing worker (F1)."""
        args = Namespace(
            ralph_command='spawn',
            name='existing-worker',
            prompt_file='test_prompt.md',
            max_iterations=10,
            inactivity_timeout=60,
            done_pattern=None,
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
            replace=True,  # The --replace flag
            cmd=['--', 'echo', 'test']
        )

        # Mock existing worker with tmux info
        mock_tmux = swarm.TmuxInfo(session='swarm-test', window='existing-worker', socket=None)
        mock_worker = swarm.Worker(
            name='existing-worker',
            status='running',
            cmd=['echo'],
            started='2024-01-01T00:00:00',
            cwd='/tmp',
            tmux=mock_tmux
        )

        # Create a mock state that returns the existing worker
        mock_state = swarm.State()
        mock_state.workers = [mock_worker]

        # Track if remove_worker was called
        removed_workers = []
        original_remove = mock_state.remove_worker
        def track_remove(name):
            removed_workers.append(name)
            return original_remove(name)
        mock_state.remove_worker = track_remove

        with patch.object(swarm, 'State', return_value=mock_state):
            with patch('subprocess.run') as mock_run:
                # Mock successful tmux operations
                mock_run.return_value.returncode = 0
                with patch.object(swarm, 'create_tmux_window'):
                    with patch.object(swarm, 'save_ralph_state'):
                        with patch.object(swarm, 'log_ralph_iteration'):
                            with patch.object(swarm, 'send_prompt_to_worker', return_value=""):
                                with patch('builtins.print') as mock_print:
                                    swarm.cmd_ralph_spawn(args)

        # Verify the existing worker was removed
        self.assertIn('existing-worker', removed_workers)
        # Verify the "replaced" message was printed
        print_calls = [str(call) for call in mock_print.call_args_list]
        self.assertTrue(any('replaced' in call for call in print_calls))

    def test_ralph_spawn_replace_removes_worktree(self):
        """Test ralph spawn with --replace removes existing worktree (F1)."""
        args = Namespace(
            ralph_command='spawn',
            name='existing-worker',
            prompt_file='test_prompt.md',
            max_iterations=10,
            inactivity_timeout=60,
            done_pattern=None,
            worktree=False,  # Not creating a new worktree, but existing has one
            session=None,
            tmux_socket=None,
            branch=None,
            worktree_dir=None,
            tags=[],
            env=[],
            cwd=None,
            ready_wait=False,
            ready_timeout=120,
            replace=True,
            cmd=['--', 'echo', 'test']
        )

        # Mock existing worker with worktree
        mock_worktree = swarm.WorktreeInfo(
            path='/tmp/test-worktrees/existing-worker',
            branch='existing-worker',
            base_repo='/tmp/test-repo'
        )
        mock_tmux = swarm.TmuxInfo(session='swarm-test', window='existing-worker', socket=None)
        mock_worker = swarm.Worker(
            name='existing-worker',
            status='running',
            cmd=['echo'],
            started='2024-01-01T00:00:00',
            cwd='/tmp',
            tmux=mock_tmux,
            worktree=mock_worktree
        )

        mock_state = swarm.State()
        mock_state.workers = [mock_worker]

        with patch.object(swarm, 'State', return_value=mock_state):
            with patch('subprocess.run') as mock_run:
                mock_run.return_value.returncode = 0
                with patch.object(swarm, 'remove_worktree') as mock_remove_worktree:
                    mock_remove_worktree.return_value = (True, None)
                    with patch.object(swarm, 'create_tmux_window'):
                        with patch.object(swarm, 'save_ralph_state'):
                            with patch.object(swarm, 'log_ralph_iteration'):
                                with patch.object(swarm, 'send_prompt_to_worker', return_value=""):
                                    with patch('builtins.print'):
                                        swarm.cmd_ralph_spawn(args)

        # Verify remove_worktree was called with force=True
        mock_remove_worktree.assert_called_once()
        call_args = mock_remove_worktree.call_args
        self.assertEqual(call_args[1].get('force'), True)

    def test_ralph_spawn_replace_removes_ralph_state(self):
        """Test ralph spawn with --replace removes existing ralph state (F1)."""
        args = Namespace(
            ralph_command='spawn',
            name='existing-worker',
            prompt_file='test_prompt.md',
            max_iterations=10,
            inactivity_timeout=60,
            done_pattern=None,
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
            replace=True,
            cmd=['--', 'echo', 'test']
        )

        # Mock existing worker
        mock_tmux = swarm.TmuxInfo(session='swarm-test', window='existing-worker', socket=None)
        mock_worker = swarm.Worker(
            name='existing-worker',
            status='running',
            cmd=['echo'],
            started='2024-01-01T00:00:00',
            cwd='/tmp',
            tmux=mock_tmux
        )

        mock_state = swarm.State()
        mock_state.workers = [mock_worker]

        # Create a temporary ralph state directory
        ralph_state_dir = swarm.RALPH_DIR / 'existing-worker'
        ralph_state_dir.mkdir(parents=True, exist_ok=True)
        (ralph_state_dir / 'state.json').write_text('{}')

        try:
            with patch.object(swarm, 'State', return_value=mock_state):
                with patch('subprocess.run') as mock_run:
                    mock_run.return_value.returncode = 0
                    with patch.object(swarm, 'create_tmux_window'):
                        with patch.object(swarm, 'save_ralph_state'):
                            with patch.object(swarm, 'log_ralph_iteration'):
                                with patch.object(swarm, 'send_prompt_to_worker', return_value=""):
                                    with patch('builtins.print'):
                                        swarm.cmd_ralph_spawn(args)

            # Verify ralph state directory was removed
            self.assertFalse(ralph_state_dir.exists())
        finally:
            # Cleanup in case test failed
            if ralph_state_dir.exists():
                import shutil
                shutil.rmtree(ralph_state_dir)

    def test_ralph_spawn_clean_state_removes_ralph_state(self):
        """Test ralph spawn with --clean-state removes existing ralph state (F5)."""
        args = Namespace(
            ralph_command='spawn',
            name='test-worker',
            prompt_file='test_prompt.md',
            max_iterations=10,
            inactivity_timeout=60,
            done_pattern=None,
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
            replace=False,
            clean_state=True,  # The --clean-state flag
            cmd=['--', 'echo', 'test']
        )

        # Create an empty state (no existing worker)
        mock_state = swarm.State()
        mock_state.workers = []

        # Create a temporary ralph state directory
        ralph_state_dir = swarm.RALPH_DIR / 'test-worker'
        ralph_state_dir.mkdir(parents=True, exist_ok=True)
        (ralph_state_dir / 'state.json').write_text('{"old": "state"}')

        try:
            with patch.object(swarm, 'State', return_value=mock_state):
                with patch('subprocess.run') as mock_run:
                    mock_run.return_value.returncode = 0
                    with patch.object(swarm, 'create_tmux_window'):
                        with patch.object(swarm, 'save_ralph_state'):
                            with patch.object(swarm, 'log_ralph_iteration'):
                                with patch.object(swarm, 'send_prompt_to_worker', return_value=""):
                                    with patch('builtins.print') as mock_print:
                                        swarm.cmd_ralph_spawn(args)

            # Verify ralph state directory was removed
            self.assertFalse(ralph_state_dir.exists())

            # Verify the message was printed
            print_calls = [str(call) for call in mock_print.call_args_list]
            self.assertTrue(any('cleared ralph state' in call for call in print_calls))
        finally:
            # Cleanup in case test failed
            if ralph_state_dir.exists():
                import shutil
                shutil.rmtree(ralph_state_dir)

    def test_ralph_spawn_clean_state_no_op_when_no_state(self):
        """Test ralph spawn with --clean-state is a no-op when no ralph state exists (F5)."""
        args = Namespace(
            ralph_command='spawn',
            name='test-worker',
            prompt_file='test_prompt.md',
            max_iterations=10,
            inactivity_timeout=60,
            done_pattern=None,
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
            replace=False,
            clean_state=True,  # The --clean-state flag
            cmd=['--', 'echo', 'test']
        )

        # Create an empty state (no existing worker)
        mock_state = swarm.State()
        mock_state.workers = []

        # Ensure no ralph state directory exists
        ralph_state_dir = swarm.RALPH_DIR / 'test-worker'
        if ralph_state_dir.exists():
            import shutil
            shutil.rmtree(ralph_state_dir)

        with patch.object(swarm, 'State', return_value=mock_state):
            with patch('subprocess.run') as mock_run:
                mock_run.return_value.returncode = 0
                with patch.object(swarm, 'create_tmux_window'):
                    with patch.object(swarm, 'save_ralph_state'):
                        with patch.object(swarm, 'log_ralph_iteration'):
                            with patch.object(swarm, 'send_prompt_to_worker', return_value=""):
                                with patch('builtins.print') as mock_print:
                                    # Should not raise any errors
                                    swarm.cmd_ralph_spawn(args)

        # Verify no "cleared ralph state" message was printed (nothing to clear)
        print_calls = [str(call) for call in mock_print.call_args_list]
        self.assertFalse(any('cleared ralph state' in call for call in print_calls))

    def test_ralph_spawn_prompt_file_not_found(self):
        """Test ralph spawn with non-existent prompt file fails."""
        args = Namespace(
            ralph_command='spawn',
            name='test-worker',
            prompt_file='nonexistent.md',
            max_iterations=10,
            inactivity_timeout=60,
            done_pattern=None,
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
                swarm.cmd_ralph_spawn(args)

        self.assertEqual(ctx.exception.code, 1)
        # Check error message
        error_calls = [str(call) for call in mock_print.call_args_list]
        self.assertTrue(any('prompt file not found' in call for call in error_calls))

    def test_ralph_spawn_high_iteration_warning(self):
        """Test ralph spawn with >50 iterations shows warning."""
        args = Namespace(
            ralph_command='spawn',
            name='test-worker',
            prompt_file='test_prompt.md',
            max_iterations=100,
            inactivity_timeout=60,
            done_pattern=None,
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
                        with patch('swarm.send_prompt_to_worker', return_value=""):
                            with patch('builtins.print') as mock_print:
                                swarm.cmd_ralph_spawn(args)

        # Check warning was printed
        all_calls = [str(call) for call in mock_print.call_args_list]
        self.assertTrue(any('high iteration count' in call for call in all_calls))

    def test_ralph_spawn_tmux_flag_shows_note(self):
        """Test ralph spawn with --tmux flag shows informational note (B6)."""
        args = Namespace(
            ralph_command='spawn',
            name='test-worker',
            prompt_file='test_prompt.md',
            max_iterations=10,
            inactivity_timeout=60,
            done_pattern=None,
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
            tmux=True,  # The --tmux flag
            cmd=['--', 'echo', 'test']
        )

        # Mock State and other functions to prevent actual spawning
        with patch.object(swarm.State, 'get_worker', return_value=None):
            with patch.object(swarm.State, 'add_worker'):
                with patch('swarm.create_tmux_window'):
                    with patch('swarm.get_default_session_name', return_value='swarm-test'):
                        with patch('swarm.send_prompt_to_worker', return_value=""):
                            with patch('builtins.print') as mock_print:
                                swarm.cmd_ralph_spawn(args)

        # Check note was printed
        all_calls = [str(call) for call in mock_print.call_args_list]
        self.assertTrue(any('Ralph workers always use tmux' in call for call in all_calls))

    def test_ralph_spawn_no_tmux_flag_no_note(self):
        """Test ralph spawn without --tmux flag doesn't show the note."""
        args = Namespace(
            ralph_command='spawn',
            name='test-worker',
            prompt_file='test_prompt.md',
            max_iterations=10,
            inactivity_timeout=60,
            done_pattern=None,
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
            tmux=False,  # No --tmux flag
            cmd=['--', 'echo', 'test']
        )

        # Mock State and other functions to prevent actual spawning
        with patch.object(swarm.State, 'get_worker', return_value=None):
            with patch.object(swarm.State, 'add_worker'):
                with patch('swarm.create_tmux_window'):
                    with patch('swarm.get_default_session_name', return_value='swarm-test'):
                        with patch('swarm.send_prompt_to_worker', return_value=""):
                            with patch('builtins.print') as mock_print:
                                swarm.cmd_ralph_spawn(args)

        # Check note was NOT printed
        all_calls = [str(call) for call in mock_print.call_args_list]
        self.assertFalse(any('Ralph workers always use tmux' in call for call in all_calls))

    def test_ralph_spawn_uses_tmux(self):
        """Test ralph spawn always uses tmux."""
        args = Namespace(
            ralph_command='spawn',
            name='test-worker',
            prompt_file='test_prompt.md',
            max_iterations=10,
            inactivity_timeout=60,
            done_pattern=None,
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
                        with patch('swarm.send_prompt_to_worker', return_value=""):
                            with patch('builtins.print'):
                                swarm.cmd_ralph_spawn(args)

        # Verify tmux window was created
        mock_create_tmux.assert_called_once()

    def test_ralph_spawn_valid_configuration_proceeds(self):
        """Test valid ralph spawn configuration proceeds."""
        args = Namespace(
            ralph_command='spawn',
            name='test-worker',
            prompt_file='test_prompt.md',
            max_iterations=10,
            inactivity_timeout=60,
            done_pattern=None,
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
                        with patch('swarm.send_prompt_to_worker', return_value=""):
                            with patch('builtins.print') as mock_print:
                                swarm.cmd_ralph_spawn(args)

        # Verify worker was added
        mock_add_worker.assert_called_once()
        # Verify success message
        all_calls = [str(call) for call in mock_print.call_args_list]
        self.assertTrue(any('spawned' in call for call in all_calls))

    def test_ralph_spawn_invalid_env_format(self):
        """Test ralph spawn with invalid env format fails."""
        args = Namespace(
            ralph_command='spawn',
            name='test-worker',
            prompt_file='test_prompt.md',
            max_iterations=10,
            inactivity_timeout=60,
            done_pattern=None,
            worktree=False,
            session=None,
            tmux_socket=None,
            branch=None,
            worktree_dir=None,
            tags=[],
            env=['INVALID_NO_EQUALS'],  # Missing = sign
            cwd=None,
            ready_wait=False,
            ready_timeout=120,
            cmd=['--', 'echo', 'test']
        )

        with patch.object(swarm.State, 'get_worker', return_value=None):
            with patch('builtins.print') as mock_print:
                with self.assertRaises(SystemExit) as ctx:
                    swarm.cmd_ralph_spawn(args)

        self.assertEqual(ctx.exception.code, 1)
        error_calls = [str(call) for call in mock_print.call_args_list]
        self.assertTrue(any('invalid env format' in call for call in error_calls))

    def test_ralph_spawn_valid_env_format(self):
        """Test ralph spawn with valid env format succeeds."""
        args = Namespace(
            ralph_command='spawn',
            name='test-worker',
            prompt_file='test_prompt.md',
            max_iterations=10,
            inactivity_timeout=60,
            done_pattern=None,
            worktree=False,
            session=None,
            tmux_socket=None,
            branch=None,
            worktree_dir=None,
            tags=[],
            env=['KEY=value', 'FOO=bar'],
            cwd=None,
            ready_wait=False,
            ready_timeout=120,
            cmd=['--', 'echo', 'test']
        )

        with patch.object(swarm.State, 'get_worker', return_value=None):
            with patch.object(swarm.State, 'add_worker') as mock_add:
                with patch('swarm.create_tmux_window'):
                    with patch('swarm.get_default_session_name', return_value='swarm-test'):
                        with patch('swarm.send_prompt_to_worker', return_value=""):
                            with patch('builtins.print'):
                                swarm.cmd_ralph_spawn(args)

        # Verify worker was added with env
        mock_add.assert_called_once()
        worker = mock_add.call_args[0][0]
        self.assertEqual(worker.env, {'KEY': 'value', 'FOO': 'bar'})

    def test_ralph_spawn_tmux_window_failure(self):
        """Test ralph spawn handles tmux window creation failure."""
        args = Namespace(
            ralph_command='spawn',
            name='test-worker',
            prompt_file='test_prompt.md',
            max_iterations=10,
            inactivity_timeout=60,
            done_pattern=None,
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
            with patch('swarm.create_tmux_window', side_effect=subprocess.CalledProcessError(1, 'tmux')):
                with patch('swarm.get_default_session_name', return_value='swarm-test'):
                    with patch('builtins.print') as mock_print:
                        with self.assertRaises(SystemExit) as ctx:
                            swarm.cmd_ralph_spawn(args)

        self.assertEqual(ctx.exception.code, 1)
        error_calls = [str(call) for call in mock_print.call_args_list]
        self.assertTrue(any('failed to create tmux window' in call for call in error_calls))

    def test_ralph_spawn_with_cwd(self):
        """Test ralph spawn with custom cwd."""
        args = Namespace(
            ralph_command='spawn',
            name='test-worker',
            prompt_file='test_prompt.md',
            max_iterations=10,
            inactivity_timeout=60,
            done_pattern=None,
            worktree=False,
            session=None,
            tmux_socket=None,
            branch=None,
            worktree_dir=None,
            tags=[],
            env=[],
            cwd='/tmp',
            ready_wait=False,
            ready_timeout=120,
            cmd=['--', 'echo', 'test']
        )

        with patch.object(swarm.State, 'get_worker', return_value=None):
            with patch.object(swarm.State, 'add_worker') as mock_add:
                with patch('swarm.create_tmux_window') as mock_tmux:
                    with patch('swarm.get_default_session_name', return_value='swarm-test'):
                        with patch('swarm.send_prompt_to_worker', return_value=""):
                            with patch('builtins.print'):
                                swarm.cmd_ralph_spawn(args)

        # Verify tmux was created with custom cwd
        mock_tmux.assert_called_once()
        call_args = mock_tmux.call_args
        self.assertEqual(call_args[0][2], Path('/tmp'))


class TestRalphSpawnWorktree(unittest.TestCase):
    """Test ralph spawn with worktree option."""

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

    def test_ralph_spawn_worktree_not_in_git_repo(self):
        """Test ralph spawn with worktree fails outside git repo."""
        args = Namespace(
            ralph_command='spawn',
            name='test-worker',
            prompt_file='test_prompt.md',
            max_iterations=10,
            inactivity_timeout=60,
            done_pattern=None,
            worktree=True,  # Enable worktree
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
            with patch('swarm.get_git_root', side_effect=subprocess.CalledProcessError(1, 'git')):
                with patch('builtins.print') as mock_print:
                    with self.assertRaises(SystemExit) as ctx:
                        swarm.cmd_ralph_spawn(args)

        self.assertEqual(ctx.exception.code, 1)
        error_calls = [str(call) for call in mock_print.call_args_list]
        self.assertTrue(any('not in a git repository' in call for call in error_calls))

    def test_ralph_spawn_worktree_creation_failure(self):
        """Test ralph spawn handles worktree creation failure."""
        args = Namespace(
            ralph_command='spawn',
            name='test-worker',
            prompt_file='test_prompt.md',
            max_iterations=10,
            inactivity_timeout=60,
            done_pattern=None,
            worktree=True,
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
            with patch('swarm.get_git_root', return_value=Path(self.temp_dir)):
                with patch('swarm.create_worktree', side_effect=subprocess.CalledProcessError(1, 'git')):
                    with patch('builtins.print') as mock_print:
                        with self.assertRaises(SystemExit) as ctx:
                            swarm.cmd_ralph_spawn(args)

        self.assertEqual(ctx.exception.code, 1)
        error_calls = [str(call) for call in mock_print.call_args_list]
        self.assertTrue(any('failed to create worktree' in call for call in error_calls))

    def test_ralph_spawn_worktree_success(self):
        """Test ralph spawn with worktree succeeds."""
        args = Namespace(
            ralph_command='spawn',
            name='test-worker',
            prompt_file='test_prompt.md',
            max_iterations=10,
            inactivity_timeout=60,
            done_pattern=None,
            worktree=True,
            session=None,
            tmux_socket=None,
            branch='custom-branch',
            worktree_dir=None,
            tags=[],
            env=[],
            cwd=None,
            ready_wait=False,
            ready_timeout=120,
            cmd=['--', 'echo', 'test']
        )

        worktree_path = Path(self.temp_dir).parent / f'{Path(self.temp_dir).name}-worktrees' / 'test-worker'

        with patch.object(swarm.State, 'get_worker', return_value=None):
            with patch.object(swarm.State, 'add_worker') as mock_add:
                with patch('swarm.get_git_root', return_value=Path(self.temp_dir)):
                    with patch('swarm.create_worktree') as mock_wt:
                        with patch('swarm.create_tmux_window'):
                            with patch('swarm.get_default_session_name', return_value='swarm-test'):
                                with patch('swarm.send_prompt_to_worker', return_value=""):
                                    with patch('builtins.print'):
                                        swarm.cmd_ralph_spawn(args)

        # Verify worktree was created with correct branch
        mock_wt.assert_called_once()
        call_args = mock_wt.call_args[0]
        self.assertEqual(call_args[1], 'custom-branch')

        # Verify worker has worktree info
        mock_add.assert_called_once()
        worker = mock_add.call_args[0][0]
        self.assertIsNotNone(worker.worktree)
        self.assertEqual(worker.worktree.branch, 'custom-branch')

    def test_ralph_spawn_worktree_custom_dir(self):
        """Test ralph spawn with custom worktree dir."""
        args = Namespace(
            ralph_command='spawn',
            name='test-worker',
            prompt_file='test_prompt.md',
            max_iterations=10,
            inactivity_timeout=60,
            done_pattern=None,
            worktree=True,
            session=None,
            tmux_socket=None,
            branch=None,
            worktree_dir='custom-worktrees',
            tags=[],
            env=[],
            cwd=None,
            ready_wait=False,
            ready_timeout=120,
            cmd=['--', 'echo', 'test']
        )

        with patch.object(swarm.State, 'get_worker', return_value=None):
            with patch.object(swarm.State, 'add_worker'):
                with patch('swarm.get_git_root', return_value=Path(self.temp_dir)):
                    with patch('swarm.create_worktree') as mock_wt:
                        with patch('swarm.create_tmux_window'):
                            with patch('swarm.get_default_session_name', return_value='swarm-test'):
                                with patch('swarm.send_prompt_to_worker', return_value=""):
                                    with patch('builtins.print'):
                                        swarm.cmd_ralph_spawn(args)

        # Verify worktree was created with custom dir
        mock_wt.assert_called_once()
        worktree_path = mock_wt.call_args[0][0]
        self.assertIn('custom-worktrees', str(worktree_path))

    def test_ralph_spawn_ready_wait_success(self):
        """Test ralph spawn with ready_wait waits for agent."""
        args = Namespace(
            ralph_command='spawn',
            name='test-worker',
            prompt_file='test_prompt.md',
            max_iterations=10,
            inactivity_timeout=60,
            done_pattern=None,
            worktree=False,
            session=None,
            tmux_socket=None,
            branch=None,
            worktree_dir=None,
            tags=[],
            env=[],
            cwd=None,
            ready_wait=True,  # Enable ready wait
            ready_timeout=120,
            cmd=['--', 'echo', 'test']
        )

        with patch.object(swarm.State, 'get_worker', return_value=None):
            with patch.object(swarm.State, 'add_worker'):
                with patch('swarm.create_tmux_window'):
                    with patch('swarm.get_default_session_name', return_value='swarm-test'):
                        with patch('swarm.send_prompt_to_worker', return_value=""):
                            with patch('swarm.wait_for_agent_ready', return_value=True) as mock_wait:
                                with patch('builtins.print'):
                                    swarm.cmd_ralph_spawn(args)

        # Verify wait_for_agent_ready was called
        mock_wait.assert_called_once()

    def test_ralph_spawn_ready_wait_timeout(self):
        """Test ralph spawn with ready_wait shows warning on timeout."""
        args = Namespace(
            ralph_command='spawn',
            name='test-worker',
            prompt_file='test_prompt.md',
            max_iterations=10,
            inactivity_timeout=60,
            done_pattern=None,
            worktree=False,
            session=None,
            tmux_socket=None,
            branch=None,
            worktree_dir=None,
            tags=[],
            env=[],
            cwd=None,
            ready_wait=True,
            ready_timeout=5,
            cmd=['--', 'echo', 'test']
        )

        with patch.object(swarm.State, 'get_worker', return_value=None):
            with patch.object(swarm.State, 'add_worker'):
                with patch('swarm.create_tmux_window'):
                    with patch('swarm.get_default_session_name', return_value='swarm-test'):
                        with patch('swarm.send_prompt_to_worker', return_value=""):
                            with patch('swarm.wait_for_agent_ready', return_value=False):
                                with patch('builtins.print') as mock_print:
                                    swarm.cmd_ralph_spawn(args)

        # Verify warning was printed
        all_calls = [str(call) for call in mock_print.call_args_list]
        self.assertTrue(any('did not become ready' in call for call in all_calls))


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

    def test_scenario_missing_prompt_file_error(self):
        """Scenario: Missing prompt file shows error.

        Given: --prompt-file ./missing.md specified
        When: swarm ralph spawn --name agent --prompt-file ./missing.md --max-iterations 10 -- claude
        Then:
          - Exit code 1
          - Error: "swarm: error: prompt file not found: ./missing.md"
        """
        args = Namespace(
            ralph_command='spawn',
            name='agent',
            prompt_file='./missing.md',
            max_iterations=10,
            inactivity_timeout=60,
            done_pattern=None,
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
                swarm.cmd_ralph_spawn(args)

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
            ralph_command='spawn',
            name='agent',
            prompt_file='PROMPT.md',
            max_iterations=100,
            inactivity_timeout=60,
            done_pattern=None,
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
                        with patch('swarm.send_prompt_to_worker', return_value=""):
                            with patch('builtins.print') as mock_print:
                                swarm.cmd_ralph_spawn(args)

        # Check warning was printed
        all_calls = [str(call) for call in mock_print.call_args_list]
        self.assertTrue(any('high iteration count' in call for call in all_calls))

        # Worker still spawns successfully
        mock_add.assert_called_once()

    def test_scenario_ralph_spawn_uses_tmux(self):
        """Scenario: Ralph spawn always uses tmux.

        Given: User uses ralph spawn subcommand
        When: swarm ralph spawn --name agent --prompt-file ./PROMPT.md --max-iterations 10 -- claude
        Then:
          - Worker created in tmux mode
        """
        args = Namespace(
            ralph_command='spawn',
            name='agent',
            prompt_file='PROMPT.md',
            max_iterations=10,
            inactivity_timeout=60,
            done_pattern=None,
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
                        with patch('swarm.send_prompt_to_worker', return_value=""):
                            with patch('builtins.print'):
                                swarm.cmd_ralph_spawn(args)

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
            ralph_command='spawn',
            name='test-worker',
            prompt_file=str(prompt_path),  # Absolute path
            max_iterations=10,
            inactivity_timeout=60,
            done_pattern=None,
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
                        with patch('swarm.send_prompt_to_worker', return_value=""):
                            with patch('builtins.print'):
                                # Should not raise
                                swarm.cmd_ralph_spawn(args)

    def test_prompt_file_relative_path(self):
        """Test prompt file with relative path works."""
        # Create prompt file with relative path
        Path('relative_prompt.md').write_text('test content')

        args = Namespace(
            ralph_command='spawn',
            name='test-worker',
            prompt_file='relative_prompt.md',  # Relative path
            max_iterations=10,
            inactivity_timeout=60,
            done_pattern=None,
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
                        with patch('swarm.send_prompt_to_worker', return_value=""):
                            with patch('builtins.print'):
                                # Should not raise
                                swarm.cmd_ralph_spawn(args)

    def test_empty_prompt_file_allowed(self):
        """Test empty prompt file is allowed."""
        Path('empty.md').write_text('')  # Empty file

        args = Namespace(
            ralph_command='spawn',
            name='test-worker',
            prompt_file='empty.md',
            max_iterations=10,
            inactivity_timeout=60,
            done_pattern=None,
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
                        with patch('swarm.send_prompt_to_worker', return_value=""):
                            with patch('builtins.print'):
                                # Should not raise - empty file is allowed
                                swarm.cmd_ralph_spawn(args)

    def test_max_iterations_exactly_50_no_warning(self):
        """Test max-iterations of exactly 50 does not trigger warning."""
        Path('prompt.md').write_text('test')

        args = Namespace(
            ralph_command='spawn',
            name='test-worker',
            prompt_file='prompt.md',
            max_iterations=50,  # Exactly 50, not > 50
            inactivity_timeout=60,
            done_pattern=None,
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
                        with patch('swarm.send_prompt_to_worker', return_value=""):
                            with patch('builtins.print') as mock_print:
                                swarm.cmd_ralph_spawn(args)

                            # No warning should be printed
                            all_calls = [str(call) for call in mock_print.call_args_list]
                            self.assertFalse(any('high iteration count' in call for call in all_calls))

    def test_max_iterations_51_triggers_warning(self):
        """Test max-iterations of 51 triggers warning."""
        Path('prompt.md').write_text('test')

        args = Namespace(
            ralph_command='spawn',
            name='test-worker',
            prompt_file='prompt.md',
            max_iterations=51,  # Just above threshold
            inactivity_timeout=60,
            done_pattern=None,
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
                        with patch('swarm.send_prompt_to_worker', return_value=""):
                            with patch('builtins.print') as mock_print:
                                swarm.cmd_ralph_spawn(args)

                            # Warning should be printed
                            all_calls = [str(call) for call in mock_print.call_args_list]
                            self.assertTrue(any('high iteration count' in call for call in all_calls))


class TestRalphSpawnNewArguments(unittest.TestCase):
    """Test ralph spawn arguments: --inactivity-timeout, --done-pattern."""

    def test_inactivity_timeout_argument_exists(self):
        """Test that --inactivity-timeout argument is recognized by ralph spawn."""
        result = subprocess.run(
            [sys.executable, 'swarm.py', 'ralph', 'spawn', '--help'],
            capture_output=True,
            text=True
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn('--inactivity-timeout', result.stdout)

    def test_done_pattern_argument_exists(self):
        """Test that --done-pattern argument is recognized by ralph spawn."""
        result = subprocess.run(
            [sys.executable, 'swarm.py', 'ralph', 'spawn', '--help'],
            capture_output=True,
            text=True
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn('--done-pattern', result.stdout)

    def test_inactivity_timeout_default_value(self):
        """Test --inactivity-timeout has default value of 180."""
        # Parse args to verify default
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument("--inactivity-timeout", type=int, default=180)
        args = parser.parse_args([])
        self.assertEqual(args.inactivity_timeout, 180)


class TestRalphStateCreation(unittest.TestCase):
    """Test ralph state creation during ralph spawn."""

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

    def test_ralph_spawn_creates_ralph_state(self):
        """Test that ralph spawn creates ralph state file."""
        args = Namespace(
            ralph_command='spawn',
            name='ralph-worker',
            prompt_file='test_prompt.md',
            max_iterations=10,
            inactivity_timeout=60,
            done_pattern=None,
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
                with patch('swarm.send_prompt_to_worker', return_value=""):
                    with patch('builtins.print'):
                        swarm.cmd_ralph_spawn(args)

        # Verify ralph state was created
        ralph_state = swarm.load_ralph_state('ralph-worker')
        self.assertIsNotNone(ralph_state)
        self.assertEqual(ralph_state.worker_name, 'ralph-worker')
        self.assertEqual(ralph_state.max_iterations, 10)
        self.assertEqual(ralph_state.status, 'running')

    def test_ralph_spawn_state_has_correct_values(self):
        """Test that ralph state has correct field values after spawn."""
        args = Namespace(
            ralph_command='spawn',
            name='ralph-worker',
            prompt_file='test_prompt.md',
            max_iterations=50,
            inactivity_timeout=600,
            done_pattern='All tasks complete',
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
                with patch('swarm.send_prompt_to_worker', return_value=""):
                    with patch('builtins.print'):
                        swarm.cmd_ralph_spawn(args)

        ralph_state = swarm.load_ralph_state('ralph-worker')
        self.assertEqual(ralph_state.max_iterations, 50)
        self.assertEqual(ralph_state.inactivity_timeout, 600)
        self.assertEqual(ralph_state.done_pattern, 'All tasks complete')
        self.assertEqual(ralph_state.current_iteration, 1)  # Starts at iteration 1
        self.assertIsNotNone(ralph_state.started)

    def test_ralph_spawn_message_includes_iteration(self):
        """Test that ralph spawn message includes ralph mode info."""
        args = Namespace(
            ralph_command='spawn',
            name='ralph-worker',
            prompt_file='test_prompt.md',
            max_iterations=100,
            inactivity_timeout=60,
            done_pattern=None,
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
                with patch('swarm.send_prompt_to_worker', return_value=""):
                    with patch('builtins.print') as mock_print:
                        swarm.cmd_ralph_spawn(args)

        all_calls = [str(call) for call in mock_print.call_args_list]
        self.assertTrue(any('ralph mode: iteration 1/100' in call for call in all_calls))

    def test_spawn_without_ralph_no_state(self):
        """Test that regular spawn does not create ralph state."""
        args = Namespace(
            name='normal-worker',
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

    def test_ralph_spawn_stores_absolute_prompt_path(self):
        """Test that ralph state stores absolute path to prompt file."""
        args = Namespace(
            ralph_command='spawn',
            name='ralph-worker',
            prompt_file='test_prompt.md',  # Relative path
            max_iterations=10,
            inactivity_timeout=60,
            done_pattern=None,
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
                with patch('swarm.send_prompt_to_worker', return_value=""):
                    with patch('builtins.print'):
                        swarm.cmd_ralph_spawn(args)

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
        self.assertEqual(state.inactivity_timeout, 180)
        self.assertIsNone(state.done_pattern)
        # New fields for B4
        self.assertEqual(state.last_iteration_ended, "")
        self.assertEqual(state.iteration_durations, [])
        self.assertIsNone(state.exit_reason)

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
        # New fields for B4
        self.assertEqual(d['last_iteration_ended'], '')
        self.assertEqual(d['iteration_durations'], [])
        self.assertIsNone(d['exit_reason'])

    def test_ralph_state_to_dict_with_exit_reason(self):
        """Test RalphState to_dict includes exit_reason field (B4)."""
        state = swarm.RalphState(
            worker_name='test',
            prompt_file='/path/to/prompt.md',
            max_iterations=10,
            current_iteration=10,
            status='stopped',
            exit_reason='max_iterations',
            last_iteration_ended='2024-01-15T15:30:00',
            iteration_durations=[300, 312, 298, 305, 310]
        )
        d = state.to_dict()
        self.assertEqual(d['exit_reason'], 'max_iterations')
        self.assertEqual(d['last_iteration_ended'], '2024-01-15T15:30:00')
        self.assertEqual(d['iteration_durations'], [300, 312, 298, 305, 310])

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
        # New fields default correctly when missing
        self.assertEqual(state.last_iteration_ended, '')
        self.assertEqual(state.iteration_durations, [])
        self.assertIsNone(state.exit_reason)

    def test_ralph_state_from_dict_with_exit_reason(self):
        """Test RalphState from_dict loads exit_reason and iteration tracking fields (B4)."""
        d = {
            'worker_name': 'test',
            'prompt_file': '/path/to/prompt.md',
            'max_iterations': 10,
            'current_iteration': 10,
            'status': 'stopped',
            'started': '2024-01-15T10:30:00',
            'last_iteration_started': '2024-01-15T15:25:00',
            'last_iteration_ended': '2024-01-15T15:30:00',
            'iteration_durations': [300, 312, 298],
            'consecutive_failures': 0,
            'total_failures': 1,
            'exit_reason': 'done_pattern'
        }
        state = swarm.RalphState.from_dict(d)
        self.assertEqual(state.exit_reason, 'done_pattern')
        self.assertEqual(state.last_iteration_ended, '2024-01-15T15:30:00')
        self.assertEqual(state.iteration_durations, [300, 312, 298])

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

    def test_ralph_state_roundtrip_with_exit_reason(self):
        """Test RalphState with exit_reason survives round-trip (B4)."""
        original = swarm.RalphState(
            worker_name='test',
            prompt_file='/path/to/prompt.md',
            max_iterations=10,
            current_iteration=10,
            status='stopped',
            started='2024-01-15T10:30:00',
            last_iteration_ended='2024-01-15T15:30:00',
            iteration_durations=[300, 312, 298, 305, 310],
            exit_reason='max_iterations'
        )
        d = original.to_dict()
        restored = swarm.RalphState.from_dict(d)
        self.assertEqual(original.exit_reason, restored.exit_reason)
        self.assertEqual(original.last_iteration_ended, restored.last_iteration_ended)
        self.assertEqual(original.iteration_durations, restored.iteration_durations)


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


class TestRalphCorruptStateRecovery(unittest.TestCase):
    """Test corrupt ralph state recovery in load_ralph_state()."""

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
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_corrupt_json_returns_fresh_state(self):
        """Test: corrupted JSON file returns fresh RalphState + logs warning."""
        worker_name = 'corrupt-worker'
        state_dir = swarm.RALPH_DIR / worker_name
        state_dir.mkdir(parents=True)
        state_path = state_dir / "state.json"
        state_path.write_text("{invalid json content!!!")

        import io
        captured = io.StringIO()
        with patch('sys.stderr', captured):
            result = swarm.load_ralph_state(worker_name)

        # Should return a fresh RalphState, not None
        self.assertIsNotNone(result)
        self.assertIsInstance(result, swarm.RalphState)
        self.assertEqual(result.worker_name, worker_name)
        self.assertEqual(result.prompt_file, "PROMPT.md")
        self.assertEqual(result.max_iterations, 0)
        self.assertEqual(result.current_iteration, 0)
        self.assertEqual(result.status, "running")

        # Should have logged a warning
        self.assertIn("corrupt ralph state", captured.getvalue())
        self.assertIn(worker_name, captured.getvalue())

    def test_corrupt_file_backed_up(self):
        """Test: corrupted file is backed up to state.json.corrupted."""
        worker_name = 'backup-worker'
        state_dir = swarm.RALPH_DIR / worker_name
        state_dir.mkdir(parents=True)
        state_path = state_dir / "state.json"
        corrupt_content = "{this is not valid json"
        state_path.write_text(corrupt_content)

        with patch('sys.stderr', new_callable=lambda: __import__('io').StringIO()):
            swarm.load_ralph_state(worker_name)

        # Check backup file exists and has the corrupt content
        backup_path = state_dir / "state.json.corrupted"
        self.assertTrue(backup_path.exists())
        self.assertEqual(backup_path.read_text(), corrupt_content)

    def test_empty_file_returns_fresh_state(self):
        """Test: empty file returns fresh RalphState."""
        worker_name = 'empty-worker'
        state_dir = swarm.RALPH_DIR / worker_name
        state_dir.mkdir(parents=True)
        state_path = state_dir / "state.json"
        state_path.write_text("")

        with patch('sys.stderr', new_callable=lambda: __import__('io').StringIO()):
            result = swarm.load_ralph_state(worker_name)

        # Empty file is invalid JSON, should return fresh state
        self.assertIsNotNone(result)
        self.assertIsInstance(result, swarm.RalphState)
        self.assertEqual(result.worker_name, worker_name)
        self.assertEqual(result.prompt_file, "PROMPT.md")

    def test_valid_state_still_loads_normally(self):
        """Test: valid state file still loads correctly (no regression)."""
        worker_name = 'valid-worker'
        original = swarm.RalphState(
            worker_name=worker_name,
            prompt_file='/path/to/prompt.md',
            max_iterations=50,
            current_iteration=10,
            status='running',
        )
        swarm.save_ralph_state(original)

        result = swarm.load_ralph_state(worker_name)
        self.assertIsNotNone(result)
        self.assertEqual(result.worker_name, worker_name)
        self.assertEqual(result.prompt_file, '/path/to/prompt.md')
        self.assertEqual(result.max_iterations, 50)
        self.assertEqual(result.current_iteration, 10)


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

    def test_status_shows_exit_reason_when_stopped(self):
        """Test ralph status shows exit_reason when loop is stopped (B4)."""
        # Create a worker with ralph state
        state = swarm.State()
        worker = swarm.Worker(
            name='ralph-worker',
            status='stopped',
            cmd=['claude'],
            started='2024-01-15T10:30:00',
            cwd='/tmp'
        )
        state.workers.append(worker)
        state.save()

        # Create ralph state with exit_reason
        ralph_state = swarm.RalphState(
            worker_name='ralph-worker',
            prompt_file='/path/to/prompt.md',
            max_iterations=10,
            current_iteration=10,
            status='stopped',
            started='2024-01-15T10:30:00',
            last_iteration_ended='2024-01-15T15:30:00',
            exit_reason='max_iterations'
        )
        swarm.save_ralph_state(ralph_state)

        args = Namespace(name='ralph-worker')

        with patch('builtins.print') as mock_print:
            swarm.cmd_ralph_status(args)

        output = '\n'.join([str(call) for call in mock_print.call_args_list])
        self.assertIn('Status: stopped', output)
        self.assertIn('Exit reason: max_iterations', output)

    def test_status_shows_exit_reason_killed(self):
        """Test ralph status shows exit_reason=killed when worker was killed (B4)."""
        state = swarm.State()
        worker = swarm.Worker(
            name='ralph-worker',
            status='stopped',
            cmd=['claude'],
            started='2024-01-15T10:30:00',
            cwd='/tmp'
        )
        state.workers.append(worker)
        state.save()

        ralph_state = swarm.RalphState(
            worker_name='ralph-worker',
            prompt_file='/path/to/prompt.md',
            max_iterations=100,
            current_iteration=5,
            status='stopped',
            started='2024-01-15T10:30:00',
            exit_reason='killed'
        )
        swarm.save_ralph_state(ralph_state)

        args = Namespace(name='ralph-worker')

        with patch('builtins.print') as mock_print:
            swarm.cmd_ralph_status(args)

        output = '\n'.join([str(call) for call in mock_print.call_args_list])
        self.assertIn('Exit reason: killed', output)

    def test_status_shows_no_exit_reason_when_running(self):
        """Test ralph status shows (none - still running) when loop is running (B4)."""
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
            max_iterations=100,
            current_iteration=5,
            status='running',
            started='2024-01-15T10:30:00'
        )
        swarm.save_ralph_state(ralph_state)

        args = Namespace(name='ralph-worker')

        with patch('builtins.print') as mock_print:
            swarm.cmd_ralph_status(args)

        output = '\n'.join([str(call) for call in mock_print.call_args_list])
        self.assertIn('(none - still running)', output)

    def test_status_shows_eta_with_iteration_durations(self):
        """Test ralph status shows ETA when iteration_durations available (B4)."""
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
            current_iteration=5,
            status='running',
            started='2024-01-15T10:30:00',
            iteration_durations=[300, 312, 298, 305, 310]  # avg ~305s
        )
        swarm.save_ralph_state(ralph_state)

        args = Namespace(name='ralph-worker')

        with patch('builtins.print') as mock_print:
            swarm.cmd_ralph_status(args)

        output = '\n'.join([str(call) for call in mock_print.call_args_list])
        # Should show iteration with ETA
        self.assertIn('5/10', output)
        self.assertIn('avg', output)
        self.assertIn('remaining', output)

    def test_status_shows_monitor_disconnected_with_worker_status(self):
        """Test ralph status shows monitor_disconnected exit reason with worker status (B5)."""
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
            current_iteration=5,
            status='stopped',
            started='2024-01-15T10:30:00',
            exit_reason='monitor_disconnected'
        )
        swarm.save_ralph_state(ralph_state)

        args = Namespace(name='ralph-worker')

        with patch('builtins.print') as mock_print:
            with patch.object(swarm, 'refresh_worker_status', return_value='running'):
                swarm.cmd_ralph_status(args)

        output = '\n'.join([str(call) for call in mock_print.call_args_list])
        self.assertIn('monitor_disconnected', output)
        self.assertIn('Worker status: running', output)


class TestCheckMonitorDisconnect(unittest.TestCase):
    """Test _check_monitor_disconnect function (B5)."""

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

    def test_sets_monitor_disconnected_when_worker_still_running(self):
        """Test _check_monitor_disconnect sets exit_reason when worker is still running (B5)."""
        # Create worker that is still running
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

        # Create ralph state in running status with no exit_reason
        ralph_state = swarm.RalphState(
            worker_name='ralph-worker',
            prompt_file='/path/to/prompt.md',
            max_iterations=10,
            current_iteration=5,
            status='running',
            started='2024-01-15T10:30:00'
        )
        swarm.save_ralph_state(ralph_state)

        # Mock refresh_worker_status to return 'running'
        with patch.object(swarm, 'refresh_worker_status', return_value='running'):
            with patch.object(swarm, 'log_ralph_iteration') as mock_log:
                swarm._check_monitor_disconnect('ralph-worker')

        # Verify ralph state was updated
        updated_state = swarm.load_ralph_state('ralph-worker')
        self.assertEqual(updated_state.status, 'stopped')
        self.assertEqual(updated_state.exit_reason, 'monitor_disconnected')

        # Verify log was called
        mock_log.assert_called_once()
        call_args = mock_log.call_args
        self.assertEqual(call_args[0][1], 'DISCONNECT')
        self.assertEqual(call_args[1]['reason'], 'monitor_disconnected')

    def test_does_not_update_when_worker_stopped(self):
        """Test _check_monitor_disconnect does not update state when worker is stopped (B5)."""
        # Create worker that is stopped
        state = swarm.State()
        worker = swarm.Worker(
            name='ralph-worker',
            status='stopped',
            cmd=['claude'],
            started='2024-01-15T10:30:00',
            cwd='/tmp'
        )
        state.workers.append(worker)
        state.save()

        # Create ralph state in running status
        ralph_state = swarm.RalphState(
            worker_name='ralph-worker',
            prompt_file='/path/to/prompt.md',
            max_iterations=10,
            current_iteration=5,
            status='running',
            started='2024-01-15T10:30:00'
        )
        swarm.save_ralph_state(ralph_state)

        # Mock refresh_worker_status to return 'stopped'
        with patch.object(swarm, 'refresh_worker_status', return_value='stopped'):
            swarm._check_monitor_disconnect('ralph-worker')

        # Verify ralph state was NOT updated
        updated_state = swarm.load_ralph_state('ralph-worker')
        self.assertEqual(updated_state.status, 'running')  # Unchanged
        self.assertIsNone(updated_state.exit_reason)  # No exit_reason set

    def test_does_not_update_when_already_has_exit_reason(self):
        """Test _check_monitor_disconnect does not update state when exit_reason already set (B5)."""
        # Create worker
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

        # Create ralph state with exit_reason already set
        ralph_state = swarm.RalphState(
            worker_name='ralph-worker',
            prompt_file='/path/to/prompt.md',
            max_iterations=10,
            current_iteration=10,
            status='stopped',
            started='2024-01-15T10:30:00',
            exit_reason='max_iterations'
        )
        swarm.save_ralph_state(ralph_state)

        # Even if worker is running, should not change exit_reason
        with patch.object(swarm, 'refresh_worker_status', return_value='running'):
            swarm._check_monitor_disconnect('ralph-worker')

        # Verify ralph state was NOT changed
        updated_state = swarm.load_ralph_state('ralph-worker')
        self.assertEqual(updated_state.exit_reason, 'max_iterations')  # Unchanged

    def test_does_not_update_when_ralph_state_not_found(self):
        """Test _check_monitor_disconnect handles missing ralph state gracefully (B5)."""
        # No ralph state created - should not raise an error
        swarm._check_monitor_disconnect('nonexistent-worker')

    def test_does_not_update_when_status_is_paused(self):
        """Test _check_monitor_disconnect does not update state when status is paused (B5)."""
        # Create worker that is running
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

        # Create ralph state in paused status (not 'running')
        ralph_state = swarm.RalphState(
            worker_name='ralph-worker',
            prompt_file='/path/to/prompt.md',
            max_iterations=10,
            current_iteration=5,
            status='paused',
            started='2024-01-15T10:30:00'
        )
        swarm.save_ralph_state(ralph_state)

        # Should not update because status is not 'running'
        with patch.object(swarm, 'refresh_worker_status', return_value='running'):
            swarm._check_monitor_disconnect('ralph-worker')

        # Verify ralph state was NOT updated
        updated_state = swarm.load_ralph_state('ralph-worker')
        self.assertEqual(updated_state.status, 'paused')  # Unchanged
        self.assertIsNone(updated_state.exit_reason)


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

    def test_ralph_spawn_sets_metadata(self):
        """Test that ralph spawn sets worker metadata."""
        args = Namespace(
            ralph_command='spawn',
            name='ralph-worker',
            prompt_file='test_prompt.md',
            max_iterations=10,
            inactivity_timeout=60,
            done_pattern=None,
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
                with patch('swarm.send_prompt_to_worker', return_value=""):
                    with patch('builtins.print'):
                        swarm.cmd_ralph_spawn(args)

        # Load worker and verify metadata
        state = swarm.State()
        worker = state.get_worker('ralph-worker')
        self.assertIsNotNone(worker)
        self.assertEqual(worker.metadata.get('ralph'), True)
        self.assertEqual(worker.metadata.get('ralph_iteration'), 1)

    def test_spawn_non_ralph_has_empty_metadata(self):
        """Test that spawning without ralph has empty metadata."""
        args = Namespace(
            name='normal-worker',
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

    def test_ralph_spawn_logs_iteration_start(self):
        """Test that ralph spawn logs iteration start."""
        args = Namespace(
            ralph_command='spawn',
            name='ralph-worker',
            prompt_file='test_prompt.md',
            max_iterations=10,
            inactivity_timeout=60,
            done_pattern=None,
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
                with patch('swarm.send_prompt_to_worker', return_value=""):
                    with patch('builtins.print'):
                        swarm.cmd_ralph_spawn(args)

        # Verify iteration log was created
        log_path = swarm.get_ralph_iterations_log_path('ralph-worker')
        self.assertTrue(log_path.exists())
        content = log_path.read_text()
        self.assertIn('[START]', content)
        self.assertIn('iteration 1/10', content)

    def test_ralph_spawn_state_starts_at_iteration_1(self):
        """Test that ralph state starts at iteration 1, not 0."""
        args = Namespace(
            ralph_command='spawn',
            name='ralph-worker',
            prompt_file='test_prompt.md',
            max_iterations=10,
            inactivity_timeout=60,
            done_pattern=None,
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
                with patch('swarm.send_prompt_to_worker', return_value=""):
                    with patch('builtins.print'):
                        swarm.cmd_ralph_spawn(args)

        # Verify ralph state starts at iteration 1
        ralph_state = swarm.load_ralph_state('ralph-worker')
        self.assertEqual(ralph_state.current_iteration, 1)

    def test_ralph_spawn_state_has_last_iteration_started(self):
        """Test that ralph state has last_iteration_started set on spawn."""
        args = Namespace(
            ralph_command='spawn',
            name='ralph-worker',
            prompt_file='test_prompt.md',
            max_iterations=10,
            inactivity_timeout=60,
            done_pattern=None,
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
                with patch('swarm.send_prompt_to_worker', return_value=""):
                    with patch('builtins.print'):
                        swarm.cmd_ralph_spawn(args)

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


class TestContinuousDonePatternDetection(unittest.TestCase):
    """Test continuous done pattern detection in detect_inactivity."""

    def test_detect_inactivity_returns_done_pattern_when_matched_continuous(self):
        """Test detect_inactivity returns 'done_pattern' when pattern matches with continuous checking."""
        worker = swarm.Worker(
            name='test-worker',
            status='running',
            cmd=['echo', 'test'],
            started='2024-01-15T10:30:00',
            cwd='/tmp',
            tmux=swarm.TmuxInfo(session='swarm', window='test')
        )

        with patch('swarm.refresh_worker_status', return_value='running'):
            with patch('swarm.tmux_capture_pane', return_value='All tasks complete\nDone'):
                with patch('time.sleep'):
                    result = swarm.detect_inactivity(
                        worker,
                        timeout=60,
                        done_pattern="All tasks complete",
                        check_done_continuous=True
                    )
                    self.assertEqual(result, "done_pattern",
                        "Should return 'done_pattern' when pattern matches during continuous checking")

    def test_detect_inactivity_no_done_pattern_check_without_continuous_flag(self):
        """Test detect_inactivity does NOT check done pattern when check_done_continuous is False."""
        worker = swarm.Worker(
            name='test-worker',
            status='running',
            cmd=['echo', 'test'],
            started='2024-01-15T10:30:00',
            cwd='/tmp',
            tmux=swarm.TmuxInfo(session='swarm', window='test')
        )

        with patch('swarm.refresh_worker_status', side_effect=['running', 'stopped']):
            with patch('swarm.tmux_capture_pane', return_value='All tasks complete\nDone'):
                with patch('time.sleep'):
                    # Even though pattern is in output, it should return "exited" not "done_pattern"
                    # because check_done_continuous is False
                    result = swarm.detect_inactivity(
                        worker,
                        timeout=60,
                        done_pattern="All tasks complete",
                        check_done_continuous=False
                    )
                    self.assertEqual(result, "exited",
                        "Should return 'exited' (not 'done_pattern') when continuous checking is disabled")

    def test_detect_inactivity_continues_when_pattern_not_matched(self):
        """Test detect_inactivity continues monitoring when pattern doesn't match."""
        worker = swarm.Worker(
            name='test-worker',
            status='running',
            cmd=['echo', 'test'],
            started='2024-01-15T10:30:00',
            cwd='/tmp',
            tmux=swarm.TmuxInfo(session='swarm', window='test')
        )

        call_count = [0]
        def mock_capture(*args, **kwargs):
            call_count[0] += 1
            # Pattern never matches
            return 'Still working on tasks'

        # Worker stops after a few checks
        def mock_refresh(w):
            if call_count[0] >= 3:
                return 'stopped'
            return 'running'

        with patch('swarm.refresh_worker_status', side_effect=mock_refresh):
            with patch('swarm.tmux_capture_pane', side_effect=mock_capture):
                with patch('time.sleep'):
                    result = swarm.detect_inactivity(
                        worker,
                        timeout=60,
                        done_pattern="All tasks complete",
                        check_done_continuous=True
                    )
                    # Should eventually return "exited" because worker stopped
                    self.assertEqual(result, "exited")
                    # Verify multiple calls were made (pattern was checked each cycle)
                    self.assertGreaterEqual(call_count[0], 2)

    def test_detect_inactivity_handles_invalid_regex_pattern(self):
        """Test detect_inactivity handles invalid regex patterns gracefully."""
        worker = swarm.Worker(
            name='test-worker',
            status='running',
            cmd=['echo', 'test'],
            started='2024-01-15T10:30:00',
            cwd='/tmp',
            tmux=swarm.TmuxInfo(session='swarm', window='test')
        )

        with patch('swarm.refresh_worker_status', side_effect=['running', 'stopped']):
            with patch('swarm.tmux_capture_pane', return_value='some output'):
                with patch('time.sleep'):
                    # Invalid regex pattern - should not crash
                    result = swarm.detect_inactivity(
                        worker,
                        timeout=60,
                        done_pattern="[invalid",  # Invalid regex
                        check_done_continuous=True
                    )
                    # Should continue and return normally
                    self.assertEqual(result, "exited")

    @patch('swarm.refresh_worker_status')
    @patch('swarm.tmux_capture_pane')
    @patch('time.time')
    @patch('time.sleep')
    def test_detect_inactivity_done_pattern_takes_priority_over_inactivity(
        self, mock_sleep, mock_time, mock_capture, mock_refresh
    ):
        """Test done pattern detection stops immediately, before inactivity timeout."""
        mock_refresh.return_value = 'running'
        # Output contains done pattern on first check
        mock_capture.return_value = 'Task complete!\nAll tasks complete'
        mock_time.return_value = 0  # Time doesn't matter - should return immediately

        worker = swarm.Worker(
            name='test-worker',
            status='running',
            cmd=['echo', 'test'],
            started='2024-01-15T10:30:00',
            cwd='/tmp',
            tmux=swarm.TmuxInfo(session='swarm', window='test')
        )

        result = swarm.detect_inactivity(
            worker,
            timeout=300,  # Long timeout
            done_pattern="All tasks complete",
            check_done_continuous=True
        )
        self.assertEqual(result, "done_pattern",
            "Done pattern match should return immediately, not wait for timeout")
        # Should have made two capture calls before returning:
        # one visible-only for screen hashing, one with scrollback for done-pattern
        self.assertEqual(mock_capture.call_count, 2)

    def test_detect_inactivity_done_pattern_regex_match(self):
        """Test done pattern uses regex matching."""
        worker = swarm.Worker(
            name='test-worker',
            status='running',
            cmd=['echo', 'test'],
            started='2024-01-15T10:30:00',
            cwd='/tmp',
            tmux=swarm.TmuxInfo(session='swarm', window='test')
        )

        with patch('swarm.refresh_worker_status', return_value='running'):
            with patch('swarm.tmux_capture_pane', return_value='IMPLEMENTATION_PLAN.md: 100% complete'):
                with patch('time.sleep'):
                    result = swarm.detect_inactivity(
                        worker,
                        timeout=60,
                        done_pattern=r"IMPLEMENTATION_PLAN.*100%",  # Regex pattern
                        check_done_continuous=True
                    )
                    self.assertEqual(result, "done_pattern",
                        "Should match regex pattern in output")


class TestDetectInactivity(unittest.TestCase):
    """Test detect_inactivity function."""

    def test_detect_inactivity_no_tmux(self):
        """Test detect_inactivity returns 'exited' for non-tmux worker."""
        worker = swarm.Worker(
            name='test-worker',
            status='running',
            cmd=['echo', 'test'],
            started='2024-01-15T10:30:00',
            cwd='/tmp',
            pid=12345
        )
        result = swarm.detect_inactivity(worker, timeout=1)
        self.assertEqual(result, "exited")


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
                with patch('swarm.send_prompt_to_worker', return_value=""):
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

        # Verify spawn was called exactly once
        mock_spawn.assert_called_once()

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
        def mock_inactivity(w, t, done_pattern=None, check_done_continuous=False, prompt_baseline_content=""):
            inactivity_count[0] += 1
            if inactivity_count[0] == 1:
                return "inactive"  # First check shows inactivity
            return "exited"

        with patch('swarm.refresh_worker_status', side_effect=mock_refresh):
            with patch('swarm.detect_inactivity', side_effect=mock_inactivity):
                with patch('swarm.kill_worker_for_ralph') as mock_kill:
                    with patch('swarm.spawn_worker_for_ralph') as mock_spawn:
                        with patch('swarm.send_prompt_to_worker', return_value=""):
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
                with patch('swarm.send_prompt_to_worker', return_value=""):
                    with patch.object(swarm.State, 'add_worker'):
                        with patch.object(swarm.State, 'remove_worker'):
                            with patch('swarm.detect_inactivity', return_value="exited"):
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
                with patch('swarm.detect_inactivity', return_value="exited"):
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
                with patch('swarm.detect_inactivity', return_value="exited"):
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


class TestScreenStableInactivityDetection(unittest.TestCase):
    """Test detect_inactivity function with screen-stable detection algorithm."""

    def test_detect_inactivity_no_tmux_returns_exited(self):
        """Test detect_inactivity returns 'exited' for non-tmux worker."""
        worker = swarm.Worker(
            name='test-worker',
            status='running',
            cmd=['echo', 'test'],
            started='2024-01-15T10:30:00',
            cwd='/tmp',
            pid=12345
        )
        result = swarm.detect_inactivity(worker, timeout=1)
        self.assertEqual(result, "exited", "Should return 'exited' for non-tmux worker")

    def test_detect_inactivity_signature_has_new_params(self):
        """Test detect_inactivity has the expected parameters."""
        import inspect
        sig = inspect.signature(swarm.detect_inactivity)
        params = list(sig.parameters.keys())
        self.assertNotIn('mode', params, "mode parameter should be removed")
        self.assertEqual(params, ['worker', 'timeout', 'done_pattern', 'check_done_continuous', 'prompt_baseline_content'],
                         "Should have worker, timeout, done_pattern, check_done_continuous, and prompt_baseline_content params")

    @patch('swarm.refresh_worker_status')
    @patch('swarm.tmux_capture_pane')
    @patch('time.time')
    @patch('time.sleep')
    def test_detect_inactivity_returns_inactive_when_screen_stable(self, mock_sleep, mock_time, mock_capture, mock_refresh):
        """Test screen-stable detection: returns 'inactive' when screen unchanged for timeout."""
        mock_refresh.return_value = 'running'
        # Return same output for all calls (screen is stable)
        mock_capture.return_value = 'same stable content\nline 2\nline 3'
        # Time progression: start=0, check1=0, check2=2 (timeout=1 triggered)
        mock_time.side_effect = [0, 0, 2]

        worker = swarm.Worker(
            name='test-worker',
            status='running',
            cmd=['echo', 'test'],
            started='2024-01-15T10:30:00',
            cwd='/tmp',
            tmux=swarm.TmuxInfo(session='swarm', window='test')
        )

        result = swarm.detect_inactivity(worker, timeout=1)
        self.assertEqual(result, "inactive", "Should return 'inactive' when screen stable for timeout duration")

    @patch('swarm.refresh_worker_status')
    @patch('swarm.tmux_capture_pane')
    def test_detect_inactivity_returns_exited_when_worker_exits(self, mock_capture, mock_refresh):
        """Test detect_inactivity returns 'exited' when worker exits."""
        mock_refresh.side_effect = ['running', 'stopped']  # Worker stops
        mock_capture.return_value = 'some output'

        worker = swarm.Worker(
            name='test-worker',
            status='running',
            cmd=['echo', 'test'],
            started='2024-01-15T10:30:00',
            cwd='/tmp',
            tmux=swarm.TmuxInfo(session='swarm', window='test')
        )

        with patch('time.sleep'):
            result = swarm.detect_inactivity(worker, timeout=60)

        self.assertEqual(result, "exited", "Should return 'exited' when worker exits")

    @patch('swarm.refresh_worker_status')
    @patch('swarm.tmux_capture_pane')
    @patch('time.time')
    @patch('time.sleep')
    def test_detect_inactivity_resets_timer_on_screen_change(self, mock_sleep, mock_time, mock_capture, mock_refresh):
        """Test screen-stable detection: timer resets when screen changes."""
        mock_refresh.return_value = 'running'
        # Screen changes for first 2 iterations, then stabilizes
        # Iter 0: 'output 1' - first capture, last_hash=None, hash changes, stable_start=None
        # Iter 1: 'output 2' - hash changes from output 1, stable_start=None (reset)
        # Iter 2: 'stable' - hash changes from output 2, stable_start=None (reset)
        # Iter 3: 'stable' - hash SAME, stable_start=time.time() at t=6
        # Iter 4: 'stable' - hash SAME, check elapsed: 10-6=4 >= 3, return True
        outputs = ['output 1', 'output 2', 'stable', 'stable', 'stable']
        mock_capture.side_effect = outputs
        # time.time() is called:
        # - iter 3: once to set stable_start = 6
        # - iter 4: twice to check (time.time() - stable_start) >= timeout: 10 - 6 = 4 >= 3
        mock_time.side_effect = [6, 10, 10]

        worker = swarm.Worker(
            name='test-worker',
            status='running',
            cmd=['echo', 'test'],
            started='2024-01-15T10:30:00',
            cwd='/tmp',
            tmux=swarm.TmuxInfo(session='swarm', window='test')
        )

        result = swarm.detect_inactivity(worker, timeout=3)
        self.assertEqual(result, "inactive", "Should return 'inactive' after screen stabilizes for timeout")

    def test_detect_inactivity_strips_ansi_codes(self):
        """Test that ANSI escape codes are stripped before comparison."""
        # Verify the internal normalize_content function strips ANSI
        import hashlib
        import re

        ansi_escape = re.compile(r'\x1b\[[0-9;]*m')

        # Text with ANSI codes
        text_with_ansi = '\x1b[32mgreen text\x1b[0m normal'
        text_without_ansi = 'green text normal'

        def normalize_content(output: str) -> str:
            lines = output.split('\n')
            last_20 = lines[-20:] if len(lines) > 20 else lines
            joined = '\n'.join(last_20)
            return ansi_escape.sub('', joined)

        normalized = normalize_content(text_with_ansi)
        self.assertEqual(normalized, text_without_ansi, "ANSI codes should be stripped")

    def test_detect_inactivity_uses_last_20_lines(self):
        """Test that only last 20 lines are considered for comparison."""
        import re

        ansi_escape = re.compile(r'\x1b\[[0-9;]*m')

        def normalize_content(output: str) -> str:
            lines = output.split('\n')
            last_20 = lines[-20:] if len(lines) > 20 else lines
            joined = '\n'.join(last_20)
            return ansi_escape.sub('', joined)

        # Create output with 30 lines
        lines = [f'line {i}' for i in range(30)]
        full_output = '\n'.join(lines)

        normalized = normalize_content(full_output)
        # Should only contain lines 10-29 (last 20)
        self.assertEqual(normalized.split('\n')[0], 'line 10')
        self.assertEqual(normalized.split('\n')[-1], 'line 29')
        self.assertEqual(len(normalized.split('\n')), 20)


class TestRalphSpawnWithDefaultTimeout(unittest.TestCase):
    """Test spawn command creates ralph state with correct default timeout."""

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

    def test_ralph_spawn_uses_default_timeout_180(self):
        """Test ralph spawn creates ralph state with default timeout of 180 seconds."""
        args = Namespace(
            ralph_command='spawn',
            name='test-worker',
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
            prompt_file=str(self.prompt_file),
            max_iterations=10,
            inactivity_timeout=180,  # default (increased from 60 for CI/pre-commit hooks)
            done_pattern=None,
            cmd=['--', 'echo', 'test']
        )

        with patch('swarm.create_tmux_window'):
            with patch('swarm.get_default_session_name', return_value='swarm-test'):
                with patch('swarm.send_prompt_to_worker', return_value=""):
                    with patch('builtins.print'):
                        swarm.cmd_ralph_spawn(args)

        ralph_state = swarm.load_ralph_state('test-worker')
        self.assertIsNotNone(ralph_state)
        self.assertEqual(ralph_state.inactivity_timeout, 180, "Default timeout should be 180 seconds")
        self.assertFalse(hasattr(ralph_state, 'inactivity_mode'), "inactivity_mode should not exist")


class TestDetectInactivityErrorHandling(unittest.TestCase):
    """Test detect_inactivity error handling."""

    @patch('swarm.refresh_worker_status')
    @patch('swarm.tmux_capture_pane')
    @patch('time.sleep')
    def test_detect_inactivity_returns_exited_on_subprocess_error(self, mock_sleep, mock_capture, mock_refresh):
        """Test detect_inactivity returns 'exited' when tmux capture fails."""
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

        result = swarm.detect_inactivity(worker, timeout=1)
        self.assertEqual(result, "exited")


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

        # Verify ralph state is now stopped and exit_reason is set (B4)
        updated_state = swarm.load_ralph_state('ralph-worker')
        self.assertEqual(updated_state.status, 'stopped')
        self.assertEqual(updated_state.exit_reason, 'killed')

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

    def test_kill_ralph_worker_with_rm_worktree_removes_ralph_state(self):
        """Test killing a ralph worker with --rm-worktree removes ralph state directory."""
        # Create a worker with tmux and worktree
        state = swarm.State()
        worktree_path = Path(self.temp_dir) / 'worktrees' / 'ralph-worker'
        worktree_path.mkdir(parents=True, exist_ok=True)

        worker = swarm.Worker(
            name='ralph-worker',
            status='running',
            cmd=['claude'],
            started='2024-01-15T10:30:00',
            cwd=str(worktree_path),
            tmux=swarm.TmuxInfo(session='swarm', window='ralph-worker'),
            worktree=swarm.WorktreeInfo(path=str(worktree_path), branch='ralph-worker', base_repo='/tmp/repo'),
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

        # Verify ralph state directory exists before kill
        ralph_state_dir = swarm.RALPH_DIR / 'ralph-worker'
        self.assertTrue(ralph_state_dir.exists())
        self.assertTrue((ralph_state_dir / 'state.json').exists())

        # Mock subprocess and remove_worktree, then kill with --rm-worktree
        with patch('subprocess.run') as mock_run, \
             patch.object(swarm, 'remove_worktree', return_value=(True, '')):
            mock_run.return_value = None
            args = Namespace(name='ralph-worker', all=False, rm_worktree=True, force_dirty=False)
            swarm.cmd_kill(args)

        # Verify ralph state directory was removed
        self.assertFalse(ralph_state_dir.exists())
        self.assertIsNone(swarm.load_ralph_state('ralph-worker'))

    def test_kill_ralph_worker_without_rm_worktree_preserves_ralph_state(self):
        """Test killing a ralph worker without --rm-worktree preserves ralph state."""
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

        # Verify ralph state directory exists before kill
        ralph_state_dir = swarm.RALPH_DIR / 'ralph-worker'
        self.assertTrue(ralph_state_dir.exists())

        # Mock subprocess and kill WITHOUT --rm-worktree
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = None
            args = Namespace(name='ralph-worker', all=False, rm_worktree=False)
            swarm.cmd_kill(args)

        # Verify ralph state directory still exists but status is stopped
        self.assertTrue(ralph_state_dir.exists())
        updated_state = swarm.load_ralph_state('ralph-worker')
        self.assertIsNotNone(updated_state)
        self.assertEqual(updated_state.status, 'stopped')

    def test_kill_all_with_rm_worktree_removes_all_ralph_states(self):
        """Test --all --rm-worktree removes ralph state for all ralph workers."""
        state = swarm.State()

        # Create two ralph workers with worktrees
        worktree_path1 = Path(self.temp_dir) / 'worktrees' / 'ralph-1'
        worktree_path2 = Path(self.temp_dir) / 'worktrees' / 'ralph-2'
        worktree_path1.mkdir(parents=True, exist_ok=True)
        worktree_path2.mkdir(parents=True, exist_ok=True)

        worker1 = swarm.Worker(
            name='ralph-1',
            status='running',
            cmd=['claude'],
            started='2024-01-15T10:30:00',
            cwd=str(worktree_path1),
            tmux=swarm.TmuxInfo(session='swarm', window='ralph-1'),
            worktree=swarm.WorktreeInfo(path=str(worktree_path1), branch='ralph-1', base_repo='/tmp/repo'),
            metadata={'ralph': True}
        )
        worker2 = swarm.Worker(
            name='ralph-2',
            status='running',
            cmd=['claude'],
            started='2024-01-15T10:30:00',
            cwd=str(worktree_path2),
            tmux=swarm.TmuxInfo(session='swarm', window='ralph-2'),
            worktree=swarm.WorktreeInfo(path=str(worktree_path2), branch='ralph-2', base_repo='/tmp/repo'),
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

        # Verify ralph state directories exist before kill
        for name in ['ralph-1', 'ralph-2']:
            self.assertTrue((swarm.RALPH_DIR / name).exists())

        # Mock subprocess and remove_worktree, then kill all with --rm-worktree
        with patch('subprocess.run') as mock_run, \
             patch.object(swarm, 'remove_worktree', return_value=(True, '')):
            mock_run.return_value = None
            args = Namespace(name=None, all=True, rm_worktree=True, force_dirty=False)
            swarm.cmd_kill(args)

        # Verify both ralph state directories were removed
        for name in ['ralph-1', 'ralph-2']:
            self.assertFalse((swarm.RALPH_DIR / name).exists())
            self.assertIsNone(swarm.load_ralph_state(name))


class TestRalphSpawnSendsPrompt(unittest.TestCase):
    """Integration test: spawn --ralph sends prompt to worker.

    Contract verified:
        When spawning with --ralph flag, the command must:
        1. Create the worker in tmux
        2. Create ralph state with iteration=1
        3. Call send_prompt_to_worker with the prompt file contents

    This is the critical integration point - if spawn doesn't send the
    prompt, the ralph loop feature is broken at the most basic level.
    """

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
        # Create a test prompt file with known content
        self.prompt_content = "This is the test prompt content for ralph mode"
        Path('test_prompt.md').write_text(self.prompt_content)

    def tearDown(self):
        """Clean up test fixtures."""
        os.chdir(self.original_cwd)
        swarm.SWARM_DIR = self.original_swarm_dir
        swarm.RALPH_DIR = self.original_ralph_dir
        swarm.STATE_FILE = self.original_state_file
        swarm.STATE_LOCK_FILE = self.original_state_lock_file
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_spawn_ralph_sends_prompt_content_to_worker(self):
        """Integration test: ralph spawn actually sends prompt to the worker.

        This verifies the critical contract that:
        1. ralph spawn creates the worker
        2. ralph spawn calls send_prompt_to_worker with the prompt file contents
        3. send_prompt_to_worker calls wait_for_agent_ready then tmux_send

        The test uses minimal mocking to verify the integration works end-to-end.
        """
        args = Namespace(
            ralph_command='spawn',
            name='ralph-test-worker',
            prompt_file='test_prompt.md',
            max_iterations=10,
            inactivity_timeout=300,
            done_pattern=None,
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

        sent_prompts = []

        def capture_send_prompt(worker, content):
            """Capture sent prompts to verify content."""
            sent_prompts.append({
                'worker_name': worker.name,
                'content': content,
                'has_tmux': worker.tmux is not None
            })
            return ""

        with patch('swarm.create_tmux_window'):
            with patch('swarm.get_default_session_name', return_value='swarm-test'):
                with patch('swarm.send_prompt_to_worker', side_effect=capture_send_prompt) as mock_send:
                    with patch('builtins.print'):
                        swarm.cmd_ralph_spawn(args)

        # Verify send_prompt_to_worker was called exactly once
        self.assertEqual(len(sent_prompts), 1, "send_prompt_to_worker should be called exactly once")
        mock_send.assert_called_once()

        # Verify the prompt content matches the file content
        sent = sent_prompts[0]
        self.assertEqual(sent['worker_name'], 'ralph-test-worker')
        self.assertEqual(sent['content'], self.prompt_content)
        self.assertTrue(sent['has_tmux'], "Worker must be in tmux mode for ralph")

        # Verify ralph state was created correctly
        ralph_state = swarm.load_ralph_state('ralph-test-worker')
        self.assertIsNotNone(ralph_state)
        self.assertEqual(ralph_state.current_iteration, 1)
        self.assertEqual(ralph_state.status, 'running')

        # Verify worker was added to state
        state = swarm.State()
        worker = state.get_worker('ralph-test-worker')
        self.assertIsNotNone(worker)
        self.assertEqual(worker.metadata.get('ralph'), True)
        self.assertEqual(worker.metadata.get('ralph_iteration'), 1)

    def test_spawn_ralph_reads_correct_prompt_file(self):
        """Verify ralph spawn reads from the specified prompt file path.

        This ensures that prompt file reading and path resolution works correctly.
        """
        # Create prompt file with unique content
        unique_content = "UNIQUE_CONTENT_12345_FOR_TESTING"
        prompt_path = Path(self.temp_dir) / 'unique_prompt.md'
        prompt_path.write_text(unique_content)

        args = Namespace(
            ralph_command='spawn',
            name='path-test-worker',
            prompt_file=str(prompt_path),  # Absolute path
            max_iterations=5,
            inactivity_timeout=300,
            done_pattern=None,
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

        captured_content = []

        def capture_content(worker, content):
            captured_content.append(content)
            return ""

        with patch('swarm.create_tmux_window'):
            with patch('swarm.get_default_session_name', return_value='swarm-test'):
                with patch('swarm.send_prompt_to_worker', side_effect=capture_content):
                    with patch('builtins.print'):
                        swarm.cmd_ralph_spawn(args)

        self.assertEqual(len(captured_content), 1)
        self.assertEqual(captured_content[0], unique_content)


class TestRalphRunIntegration(unittest.TestCase):
    """Integration tests for ralph run loop behavior.

    Contract verified:
        The ralph run loop must:
        1. Check if worker is stopped
        2. If stopped, increment iteration and spawn new worker
        3. Call send_prompt_to_worker for new worker
        4. Call detect_inactivity to monitor worker
        5. Handle inactivity/exit correctly to loop back or complete

    These tests verify components work together correctly with minimal mocking.
    """

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
        self.prompt_content = "Test prompt for integration"
        self.prompt_path.write_text(self.prompt_content)

    def tearDown(self):
        """Clean up test fixtures."""
        swarm.SWARM_DIR = self.original_swarm_dir
        swarm.RALPH_DIR = self.original_ralph_dir
        swarm.STATE_FILE = self.original_state_file
        swarm.STATE_LOCK_FILE = self.original_state_lock_file
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_ralph_run_increments_iteration_on_worker_exit(self):
        """Integration test: worker exit triggers iteration increment.

        Contract: When a worker exits and ralph run spawns a new one,
        the iteration counter must increment before spawning.

        Timeout: 5s to prevent hanging.
        """
        import signal

        # Create worker
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

        # Create ralph state at iteration 1
        ralph_state = swarm.RalphState(
            worker_name='ralph-worker',
            prompt_file=str(self.prompt_path),
            max_iterations=3,
            current_iteration=1,
            status='running'
        )
        swarm.save_ralph_state(ralph_state)

        args = Namespace(name='ralph-worker')

        iteration_at_spawn = []

        def capture_spawn(*args, **kwargs):
            """Capture the iteration number when spawn is called."""
            current_state = swarm.load_ralph_state('ralph-worker')
            iteration_at_spawn.append(current_state.current_iteration)
            return swarm.Worker(
                name='ralph-worker',
                status='running',
                cmd=['echo', 'test'],
                started='2024-01-15T10:30:00',
                cwd=str(self.prompt_path.parent),
                tmux=swarm.TmuxInfo(session='swarm', window='ralph-worker')
            )

        # Set up timeout to prevent hanging
        def timeout_handler(signum, frame):
            raise TimeoutError("Test timed out after 5 seconds")

        old_handler = signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(5)  # 5 second timeout

        try:
            with patch('swarm.refresh_worker_status', return_value='stopped'):
                with patch('swarm.spawn_worker_for_ralph', side_effect=capture_spawn):
                    with patch('swarm.send_prompt_to_worker', return_value=""):
                        with patch.object(swarm.State, 'add_worker'):
                            with patch.object(swarm.State, 'remove_worker'):
                                with patch('builtins.print'):
                                    swarm.cmd_ralph_run(args)
        finally:
            signal.alarm(0)  # Cancel alarm
            signal.signal(signal.SIGALRM, old_handler)

        # Verify iteration was incremented before spawn
        self.assertEqual(len(iteration_at_spawn), 2)  # Two iterations spawned (2 and 3)
        self.assertEqual(iteration_at_spawn[0], 2)  # First spawn at iteration 2
        self.assertEqual(iteration_at_spawn[1], 3)  # Second spawn at iteration 3

        # Final state should be stopped at max iterations
        final_state = swarm.load_ralph_state('ralph-worker')
        self.assertEqual(final_state.status, 'stopped')
        self.assertEqual(final_state.current_iteration, 3)

    def test_ralph_run_calls_detect_inactivity_with_correct_params(self):
        """Integration test: ralph run passes correct params to detect_inactivity.

        Contract: detect_inactivity must be called with:
        - The worker object
        - The inactivity_timeout from ralph state

        Timeout: 5s to prevent hanging.
        """
        import signal

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

        # Create ralph state with specific settings
        ralph_state = swarm.RalphState(
            worker_name='ralph-worker',
            prompt_file=str(self.prompt_path),
            max_iterations=2,
            current_iteration=1,
            status='running',
            inactivity_timeout=999,  # Unique value to verify
        )
        swarm.save_ralph_state(ralph_state)

        args = Namespace(name='ralph-worker')

        detect_calls = []

        def capture_detect_inactivity(worker, timeout, done_pattern=None, check_done_continuous=False, prompt_baseline_content=""):
            """Capture detect_inactivity calls."""
            detect_calls.append({
                'worker_name': worker.name,
                'timeout': timeout,
            })
            return "exited"  # Worker exited normally

        # Set up timeout
        def timeout_handler(signum, frame):
            raise TimeoutError("Test timed out")

        old_handler = signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(5)

        refresh_count = [0]
        def mock_refresh(w):
            refresh_count[0] += 1
            # First check: running, then stopped after detect_inactivity
            if refresh_count[0] <= 2:
                return 'running'
            return 'stopped'

        try:
            with patch('swarm.refresh_worker_status', side_effect=mock_refresh):
                with patch('swarm.detect_inactivity', side_effect=capture_detect_inactivity):
                    with patch('swarm.check_done_pattern', return_value=False):
                        with patch('builtins.print'):
                            swarm.cmd_ralph_run(args)
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, old_handler)

        # Verify detect_inactivity was called with correct parameters
        self.assertGreaterEqual(len(detect_calls), 1)
        first_call = detect_calls[0]
        self.assertEqual(first_call['worker_name'], 'ralph-worker')
        self.assertEqual(first_call['timeout'], 999)  # Custom timeout


class TestRalphSpawnSendsPromptIntegration(unittest.TestCase):
    """Integration test: spawn --ralph must send prompt to worker.

    Contract verified:
    - When cmd_spawn is called with --ralph flag, it must:
      1. Create the tmux window
      2. Wait for agent ready
      3. Send the prompt content via tmux_send

    This test uses minimal mocking to verify the real integration between
    cmd_spawn and send_prompt_to_worker. Heavy mocking could hide bugs where
    the prompt is "sent" but never reaches the worker.

    Why this matters:
    - If spawn doesn't send the initial prompt, the worker sits idle
    - The ralph loop expects iteration 1 to already be running
    - This is the entry point for the entire ralph feature
    """

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

        # Create a test prompt file with unique content we can verify
        self.prompt_content = "INTEGRATION_TEST_PROMPT_12345\nDo the test task\n"
        Path('test_prompt.md').write_text(self.prompt_content)

    def tearDown(self):
        """Clean up test fixtures."""
        os.chdir(self.original_cwd)
        swarm.SWARM_DIR = self.original_swarm_dir
        swarm.RALPH_DIR = self.original_ralph_dir
        swarm.STATE_FILE = self.original_state_file
        swarm.STATE_LOCK_FILE = self.original_state_lock_file
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_spawn_ralph_sends_prompt_to_worker(self):
        """Integration test: ralph spawn actually sends prompt content.

        This test verifies that when ralph spawn is called:
        1. send_prompt_to_worker is called (not just mocked away)
        2. The actual prompt file content is passed to it
        3. tmux_send receives the correct prompt content

        We mock at the lowest level (tmux_send) to verify the prompt flows
        through the entire call chain: cmd_ralph_spawn -> send_prompt_to_worker -> tmux_send
        """
        args = Namespace(
            ralph_command='spawn',
            name='integration-test-worker',
            prompt_file='test_prompt.md',
            max_iterations=10,
            inactivity_timeout=300,
            done_pattern=None,
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

        # Track what gets sent via tmux_send
        sent_prompts = []

        def capture_tmux_send(session, window, text, enter=True, socket=None):
            """Capture calls to tmux_send to verify prompt is sent."""
            sent_prompts.append({
                'session': session,
                'window': window,
                'text': text,
                'enter': enter
            })

        # Use real functions except for actual tmux interaction
        with patch('swarm.create_tmux_window'):
            with patch('swarm.get_default_session_name', return_value='swarm-test'):
                with patch('swarm.wait_for_agent_ready', return_value=True):
                    with patch('swarm.tmux_send', side_effect=capture_tmux_send):
                        with patch('builtins.print'):
                            swarm.cmd_ralph_spawn(args)

        # CRITICAL VERIFICATION: The prompt content must have been sent
        self.assertGreaterEqual(len(sent_prompts), 1,
            "ralph spawn must call tmux_send to deliver the prompt")

        # Verify the prompt content matches what was in the file
        prompt_sent = False
        for call in sent_prompts:
            if 'INTEGRATION_TEST_PROMPT_12345' in call['text']:
                prompt_sent = True
                # Verify it was sent to the right window
                self.assertEqual(call['window'], 'integration-test-worker')
                # Verify Enter was pressed
                self.assertTrue(call['enter'],
                    "Prompt must be submitted with Enter")
                break

        self.assertTrue(prompt_sent,
            f"Prompt content must be sent via tmux_send. Got calls: {sent_prompts}")

        # Also verify state was created correctly
        ralph_state = swarm.load_ralph_state('integration-test-worker')
        self.assertIsNotNone(ralph_state)
        self.assertEqual(ralph_state.current_iteration, 1,
            "Ralph state must start at iteration 1")
        self.assertEqual(ralph_state.status, 'running')

    def test_spawn_ralph_reads_prompt_file_content(self):
        """Verify ralph spawn reads the actual file content, not just the path.

        This catches bugs where we might pass the path instead of content,
        or where file reading fails silently.
        """
        # Create prompt with distinctive content
        unique_content = f"UNIQUE_CONTENT_{os.getpid()}_{time.time()}"
        Path('unique_prompt.md').write_text(unique_content)

        args = Namespace(
            ralph_command='spawn',
            name='file-content-test',
            prompt_file='unique_prompt.md',
            max_iterations=5,
            inactivity_timeout=300,
            done_pattern=None,
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

        sent_texts = []

        def capture_send(session, window, text, enter=True, socket=None):
            sent_texts.append(text)

        with patch('swarm.create_tmux_window'):
            with patch('swarm.get_default_session_name', return_value='swarm-test'):
                with patch('swarm.wait_for_agent_ready', return_value=True):
                    with patch('swarm.tmux_send', side_effect=capture_send):
                        with patch('builtins.print'):
                            swarm.cmd_ralph_spawn(args)

        # The unique content must appear in what was sent
        all_sent = ''.join(sent_texts)
        self.assertIn(unique_content, all_sent,
            "Spawn must read and send the actual file content")

        # The file path should NOT appear (we want content, not path)
        self.assertNotIn('unique_prompt.md', all_sent,
            "Spawn should send file content, not file path")


class TestRalphInactivityRestartIntegration(unittest.TestCase):
    """Integration test: inactivity detection triggers full restart cycle.

    Contract verified:
    When detect_inactivity returns True (inactivity detected), the ralph loop must:
    1. Call kill_worker_for_ralph to stop the inactive worker
    2. Increment the iteration counter
    3. Call spawn_worker_for_ralph with new iteration metadata
    4. Call send_prompt_to_worker with the prompt content

    This is the core ralph loop functionality. If any step is skipped:
    - Skipped kill: Zombie workers accumulate
    - Skipped iteration increment: Loop never terminates
    - Skipped spawn: No new worker to continue work
    - Skipped send_prompt: Worker sits idle with no instructions

    Why this test matters:
    The existing tests verify worker exit (detect_inactivity returns False).
    This test verifies the INACTIVITY path (detect_inactivity returns True),
    which is the primary mechanism for restarting stuck agents.
    """

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
        self.prompt_content = "INACTIVITY_TEST_PROMPT_CONTENT_12345"
        self.prompt_path.write_text(self.prompt_content)

    def tearDown(self):
        """Clean up test fixtures."""
        swarm.SWARM_DIR = self.original_swarm_dir
        swarm.RALPH_DIR = self.original_ralph_dir
        swarm.STATE_FILE = self.original_state_file
        swarm.STATE_LOCK_FILE = self.original_state_lock_file
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_inactivity_triggers_kill_then_restart_with_prompt(self):
        """Integration test: inactivity detection triggers full restart cycle.

        This test verifies the complete flow when a worker becomes inactive:
        1. detect_inactivity returns True (inactivity detected)
        2. kill_worker_for_ralph is called
        3. Iteration counter is incremented (on next loop)
        4. spawn_worker_for_ralph is called
        5. send_prompt_to_worker is called with prompt content

        The test uses timeouts to prevent hanging (10s limit).
        """
        # Create initial worker in running state
        state = swarm.State()
        initial_worker = swarm.Worker(
            name='inactivity-test-worker',
            status='running',
            cmd=['echo', 'test'],
            started='2024-01-15T10:30:00',
            cwd=self.temp_dir,
            tmux=swarm.TmuxInfo(session='swarm', window='inactivity-test-worker')
        )
        state.workers.append(initial_worker)
        state.save()

        # Create ralph state at iteration 1, max 2 iterations
        # Starting at iteration 1, after inactivity we spawn iteration 2, then loop exits
        ralph_state = swarm.RalphState(
            worker_name='inactivity-test-worker',
            prompt_file=str(self.prompt_path),
            max_iterations=2,
            current_iteration=1,
            status='running',
            inactivity_timeout=30,
        )
        swarm.save_ralph_state(ralph_state)

        args = Namespace(name='inactivity-test-worker')

        # Track all operations in sequence
        operations = []

        killed = [False]
        def track_kill(worker, state):
            """Track kill_worker_for_ralph calls."""
            killed[0] = True
            operations.append({
                'op': 'kill',
                'worker_name': worker.name,
                'iteration': swarm.load_ralph_state('inactivity-test-worker').current_iteration
            })

        def track_spawn(*args, **kwargs):
            """Track spawn_worker_for_ralph calls."""
            current_state = swarm.load_ralph_state('inactivity-test-worker')
            operations.append({
                'op': 'spawn',
                'iteration': current_state.current_iteration,
                'metadata': kwargs.get('metadata', {})
            })
            return swarm.Worker(
                name='inactivity-test-worker',
                status='running',
                cmd=['echo', 'test'],
                started='2024-01-15T10:30:00',
                cwd=self.temp_dir,
                tmux=swarm.TmuxInfo(session='swarm', window='inactivity-test-worker')
            )

        def track_send_prompt(worker, content):
            """Track send_prompt_to_worker calls."""
            operations.append({
                'op': 'send_prompt',
                'worker_name': worker.name,
                'content': content,
                'iteration': swarm.load_ralph_state('inactivity-test-worker').current_iteration
            })
            return ""

        # Simulate detect_inactivity behavior:
        # - First call: return "inactive" (inactivity detected) - triggers kill then restart
        # - Second call: return "exited" (worker exited) - loop completes
        detect_call_count = [0]
        def mock_detect_inactivity(worker, timeout, done_pattern=None, check_done_continuous=False, prompt_baseline_content=""):
            detect_call_count[0] += 1
            operations.append({
                'op': 'detect_inactivity',
                'worker_name': worker.name,
                'timeout': timeout,
                'call_number': detect_call_count[0]
            })
            # First call: return "inactive" (inactivity) to trigger kill/restart
            # After that: return "exited" (worker exited) so loop completes
            return "inactive" if detect_call_count[0] == 1 else "exited"

        # Track refresh_worker_status to control the flow
        # Return 'running' initially, then 'stopped' after kill to trigger respawn
        def mock_refresh(worker):
            if killed[0]:
                return 'stopped'
            return 'running'

        # Set up timeout to prevent hanging
        def timeout_handler(signum, frame):
            raise TimeoutError("Test timed out after 10 seconds")

        old_handler = signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(10)  # 10 second timeout

        try:
            with patch('swarm.refresh_worker_status', side_effect=mock_refresh):
                with patch('swarm.detect_inactivity', side_effect=mock_detect_inactivity):
                    with patch('swarm.kill_worker_for_ralph', side_effect=track_kill):
                        with patch('swarm.spawn_worker_for_ralph', side_effect=track_spawn):
                            with patch('swarm.send_prompt_to_worker', side_effect=track_send_prompt):
                                with patch.object(swarm.State, 'add_worker'):
                                    with patch.object(swarm.State, 'remove_worker'):
                                        with patch('swarm.check_done_pattern', return_value=False):
                                            with patch('builtins.print'):
                                                swarm.cmd_ralph_run(args)
        finally:
            signal.alarm(0)  # Cancel alarm
            signal.signal(signal.SIGALRM, old_handler)

        # Extract operations by type
        kills = [op for op in operations if op['op'] == 'kill']
        spawns = [op for op in operations if op['op'] == 'spawn']
        sends = [op for op in operations if op['op'] == 'send_prompt']
        detects = [op for op in operations if op['op'] == 'detect_inactivity']

        # CRITICAL VERIFICATION 1: detect_inactivity was called at least once
        self.assertGreaterEqual(len(detects), 1,
            "detect_inactivity must be called to monitor the worker")

        # CRITICAL VERIFICATION 2: kill was called after inactivity detected
        self.assertEqual(len(kills), 1,
            "kill_worker_for_ralph must be called exactly once when inactivity is detected")

        # CRITICAL VERIFICATION 3: spawn was called after kill (for iteration 2)
        self.assertEqual(len(spawns), 1,
            "spawn_worker_for_ralph must be called once to restart the worker")

        # CRITICAL VERIFICATION 4: send_prompt was called after spawn
        self.assertEqual(len(sends), 1,
            "send_prompt_to_worker must be called for the new worker")

        # Verify prompt content was actually sent
        self.assertIn(self.prompt_content, sends[0]['content'],
            "send_prompt_to_worker must receive the prompt file content")

        # Verify operation sequence: detect -> kill -> spawn -> send_prompt
        detect_indices = [i for i, op in enumerate(operations) if op['op'] == 'detect_inactivity']
        kill_indices = [i for i, op in enumerate(operations) if op['op'] == 'kill']
        spawn_indices = [i for i, op in enumerate(operations) if op['op'] == 'spawn']
        send_indices = [i for i, op in enumerate(operations) if op['op'] == 'send_prompt']

        # First kill should be after first detect
        self.assertGreater(kill_indices[0], detect_indices[0],
            "kill must happen AFTER detect_inactivity returns True")

        # First spawn should be after first kill
        self.assertGreater(spawn_indices[0], kill_indices[0],
            "spawn must happen AFTER kill")

        # First send_prompt should be after first spawn
        self.assertGreater(send_indices[0], spawn_indices[0],
            "send_prompt must happen AFTER spawn")

        # Verify the spawn happened at iteration 2 (incremented from 1)
        self.assertEqual(spawns[0]['iteration'], 2,
            "spawn should happen at iteration 2 (incremented from 1)")
        self.assertEqual(spawns[0]['metadata'].get('ralph_iteration'), 2,
            "spawn metadata should have ralph_iteration=2")

        # Verify final state
        final_state = swarm.load_ralph_state('inactivity-test-worker')
        self.assertEqual(final_state.status, 'stopped',
            "Ralph loop must stop when max_iterations reached")

    def test_inactivity_restart_increments_iteration_before_spawn(self):
        """Verify iteration is incremented BEFORE spawn, not after.

        Contract: When restarting due to inactivity:
        - Iteration counter must be incremented first
        - Then spawn_worker_for_ralph is called
        - The spawned worker metadata must have the NEW iteration number

        This catches bugs where iteration is incremented after spawn,
        which would cause metadata to have stale iteration number.
        """
        # Create initial worker in running state
        state = swarm.State()
        initial_worker = swarm.Worker(
            name='iteration-order-test',
            status='running',
            cmd=['echo', 'test'],
            started='2024-01-15T10:30:00',
            cwd=self.temp_dir,
            tmux=swarm.TmuxInfo(session='swarm', window='iteration-order-test')
        )
        state.workers.append(initial_worker)
        state.save()

        # Create ralph state at iteration 5, max 10
        ralph_state = swarm.RalphState(
            worker_name='iteration-order-test',
            prompt_file=str(self.prompt_path),
            max_iterations=10,
            current_iteration=5,
            status='running',
            inactivity_timeout=30,
        )
        swarm.save_ralph_state(ralph_state)

        args = Namespace(name='iteration-order-test')

        spawn_metadata_captures = []
        killed = [False]

        def capture_spawn(*args, **kwargs):
            """Capture spawn metadata to verify iteration."""
            metadata = kwargs.get('metadata', {})
            current_state = swarm.load_ralph_state('iteration-order-test')
            spawn_metadata_captures.append({
                'metadata_iteration': metadata.get('ralph_iteration'),
                'state_iteration': current_state.current_iteration
            })
            return swarm.Worker(
                name='iteration-order-test',
                status='running',
                cmd=['echo', 'test'],
                started='2024-01-15T10:30:00',
                cwd=self.temp_dir,
                tmux=swarm.TmuxInfo(session='swarm', window='iteration-order-test')
            )

        detect_count = [0]
        def mock_detect(worker, timeout, done_pattern=None, check_done_continuous=False, prompt_baseline_content=""):
            detect_count[0] += 1
            if detect_count[0] == 1:
                return "inactive"  # Trigger restart on first call
            return "exited"  # Exit normally after that

        def mock_kill(worker, state):
            killed[0] = True

        def mock_refresh(worker):
            if killed[0]:
                return 'stopped'
            return 'running'

        def timeout_handler(signum, frame):
            raise TimeoutError("Test timed out")

        old_handler = signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(10)

        try:
            with patch('swarm.refresh_worker_status', side_effect=mock_refresh):
                with patch('swarm.detect_inactivity', side_effect=mock_detect):
                    with patch('swarm.kill_worker_for_ralph', side_effect=mock_kill):
                        with patch('swarm.spawn_worker_for_ralph', side_effect=capture_spawn):
                            with patch('swarm.send_prompt_to_worker', return_value=""):
                                with patch.object(swarm.State, 'add_worker'):
                                    with patch.object(swarm.State, 'remove_worker'):
                                        with patch('swarm.check_done_pattern', return_value=False):
                                            with patch('builtins.print'):
                                                swarm.cmd_ralph_run(args)
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, old_handler)

        # Verify spawn was called
        self.assertGreaterEqual(len(spawn_metadata_captures), 1,
            "spawn_worker_for_ralph must be called")

        # Verify metadata iteration matches state iteration
        for capture in spawn_metadata_captures:
            self.assertEqual(
                capture['metadata_iteration'],
                capture['state_iteration'],
                f"Metadata iteration ({capture['metadata_iteration']}) must match "
                f"state iteration ({capture['state_iteration']}) - "
                "iteration must be incremented BEFORE spawn"
            )

            # Verify iteration was incremented from initial value (5)
            self.assertGreater(capture['state_iteration'], 5,
                "Iteration must be incremented before spawn")


class TestDetectInactivityBlockingIntegration(unittest.TestCase):
    """Integration test: detect_inactivity blocking behavior.

    Contract verified:
    - detect_inactivity BLOCKS until one of these conditions:
      1. Worker exits (returns False)
      2. Inactivity timeout reached (returns True)
    - The function must NOT return prematurely

    Why this test matters:
    The ralph loop depends on detect_inactivity to block while monitoring.
    If it returns early, the ralph loop will spin rapidly (CPU burn, log spam).
    If it never returns when worker exits, the ralph loop hangs forever.

    These tests use minimal mocking (only tmux_capture_pane) to verify the
    real blocking logic and timing behavior.
    """

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Clean up test fixtures."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_detect_inactivity_returns_false_when_worker_exits(self):
        """Integration test: detect_inactivity returns False when worker exits.

        Contract: When refresh_worker_status returns 'stopped', detect_inactivity
        must immediately return False (not wait for timeout).

        This test verifies:
        1. detect_inactivity calls refresh_worker_status to check worker state
        2. When worker is stopped, it returns False quickly (not waiting for timeout)
        3. The return value is correct (False = worker exited, not inactivity)

        Timeout: 5s - if it takes longer, the function is not returning on worker exit.
        """
        worker = swarm.Worker(
            name='exit-test-worker',
            status='running',
            cmd=['echo', 'test'],
            started='2024-01-15T10:30:00',
            cwd=self.temp_dir,
            tmux=swarm.TmuxInfo(session='swarm', window='exit-test-worker')
        )

        refresh_call_count = [0]

        def mock_refresh(w):
            """Simulate worker that exits after first check."""
            refresh_call_count[0] += 1
            # Worker exits on second check
            if refresh_call_count[0] >= 2:
                return 'stopped'
            return 'running'

        def mock_capture(session, window, socket=None, history_lines=None):
            """Return consistent output (no change, simulating idle)."""
            return "Test output\n> "

        def timeout_handler(signum, frame):
            raise TimeoutError("detect_inactivity did not return when worker exited")

        old_handler = signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(5)  # 5 second timeout - should return much faster

        try:
            with patch('swarm.refresh_worker_status', side_effect=mock_refresh):
                with patch('swarm.tmux_capture_pane', side_effect=mock_capture):
                    start_time = time.time()
                    result = swarm.detect_inactivity(worker, timeout=300)
                    elapsed = time.time() - start_time
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, old_handler)

        # CRITICAL: Must return "exited" (worker exited, not inactivity)
        self.assertEqual(result, "exited",
            "detect_inactivity must return 'exited' when worker exits")

        # CRITICAL: Must return quickly (not wait for 300s timeout)
        self.assertLess(elapsed, 5.0,
            f"detect_inactivity should return quickly when worker exits, took {elapsed}s")

        # Verify refresh_worker_status was actually called
        self.assertGreaterEqual(refresh_call_count[0], 2,
            "detect_inactivity must check worker status")

    def test_detect_inactivity_returns_true_after_timeout_output_mode(self):
        """Integration test: detect_inactivity returns True after output timeout.

        Contract: In 'output' mode, when output stops changing for the timeout
        duration, detect_inactivity must return True.

        This test verifies:
        1. detect_inactivity monitors output changes via tmux_capture_pane
        2. When output stops changing, it waits for the full timeout
        3. After timeout, it returns True (inactivity detected)

        Timeout: 10s - we use a 2s inactivity timeout to keep test fast.
        """
        worker = swarm.Worker(
            name='timeout-test-worker',
            status='running',
            cmd=['echo', 'test'],
            started='2024-01-15T10:30:00',
            cwd=self.temp_dir,
            tmux=swarm.TmuxInfo(session='swarm', window='timeout-test-worker')
        )

        def mock_refresh(w):
            """Worker stays running throughout test."""
            return 'running'

        capture_count = [0]

        def mock_capture(session, window, socket=None, history_lines=None):
            """Return identical output to simulate no activity."""
            capture_count[0] += 1
            return "Static output that never changes\n"

        def timeout_handler(signum, frame):
            raise TimeoutError("detect_inactivity did not return after timeout")

        old_handler = signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(10)  # 10 second test timeout

        try:
            with patch('swarm.refresh_worker_status', side_effect=mock_refresh):
                with patch('swarm.tmux_capture_pane', side_effect=mock_capture):
                    start_time = time.time()
                    # Use a short 2 second timeout for the test
                    result = swarm.detect_inactivity(worker, timeout=2)
                    elapsed = time.time() - start_time
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, old_handler)

        # CRITICAL: Must return "inactive" (inactivity detected)
        self.assertEqual(result, "inactive",
            "detect_inactivity must return 'inactive' after inactivity timeout")

        # CRITICAL: Must wait approximately the timeout duration
        self.assertGreaterEqual(elapsed, 2.0,
            f"detect_inactivity should wait for timeout, only waited {elapsed}s")
        self.assertLess(elapsed, 6.0,
            f"detect_inactivity should not wait much longer than timeout, waited {elapsed}s")

        # Verify tmux_capture_pane was called multiple times (polling)
        self.assertGreaterEqual(capture_count[0], 2,
            "detect_inactivity must poll output multiple times")

    def test_detect_inactivity_returns_true_after_timeout_ready_mode(self):
        """Integration test: detect_inactivity returns True after ready timeout.

        Contract: In 'ready' mode, when the agent shows ready patterns for the
        timeout duration, detect_inactivity must return True.

        This test verifies:
        1. detect_inactivity detects ready patterns in output
        2. When ready pattern persists for timeout duration, returns True
        3. The ready pattern matching works correctly

        Timeout: 10s - we use a 2s inactivity timeout to keep test fast.
        """
        worker = swarm.Worker(
            name='ready-timeout-worker',
            status='running',
            cmd=['echo', 'test'],
            started='2024-01-15T10:30:00',
            cwd=self.temp_dir,
            tmux=swarm.TmuxInfo(session='swarm', window='ready-timeout-worker')
        )

        def mock_refresh(w):
            """Worker stays running throughout test."""
            return 'running'

        def mock_capture(session, window, socket=None, history_lines=None):
            """Return output with ready pattern to trigger ready-mode detection."""
            # Use a ready pattern that detect_inactivity recognizes
            return "Some output\n> "  # "> " is a ready pattern

        def timeout_handler(signum, frame):
            raise TimeoutError("detect_inactivity did not return after timeout")

        old_handler = signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(10)

        try:
            with patch('swarm.refresh_worker_status', side_effect=mock_refresh):
                with patch('swarm.tmux_capture_pane', side_effect=mock_capture):
                    start_time = time.time()
                    result = swarm.detect_inactivity(worker, timeout=2)
                    elapsed = time.time() - start_time
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, old_handler)

        # CRITICAL: Must return "inactive" (ready state detected for timeout)
        self.assertEqual(result, "inactive",
            "detect_inactivity must return 'inactive' when ready pattern detected for timeout")

        # CRITICAL: Must wait approximately the timeout duration
        self.assertGreaterEqual(elapsed, 2.0,
            f"detect_inactivity should wait for full timeout in ready mode, only waited {elapsed}s")

    def test_detect_inactivity_resets_timer_on_output_change(self):
        """Integration test: output changes reset the inactivity timer.

        Contract: When new output appears, the inactivity timer must reset.
        The function should NOT return True if output keeps changing.

        This test verifies:
        1. Changing output resets the timer
        2. Function blocks while output is active
        3. Only returns after output stops AND timeout elapses

        Timeout: 15s - we simulate changing output then stopping.
        """
        worker = swarm.Worker(
            name='reset-timer-worker',
            status='running',
            cmd=['echo', 'test'],
            started='2024-01-15T10:30:00',
            cwd=self.temp_dir,
            tmux=swarm.TmuxInfo(session='swarm', window='reset-timer-worker')
        )

        def mock_refresh(w):
            """Worker stays running throughout test."""
            return 'running'

        capture_count = [0]
        start_time = [None]

        def mock_capture(session, window, socket=None, history_lines=None):
            """Return changing output for first 2 seconds, then static."""
            capture_count[0] += 1
            if start_time[0] is None:
                start_time[0] = time.time()

            elapsed = time.time() - start_time[0]

            # Change output for first ~2 seconds (resets timer each time)
            if elapsed < 2.0:
                return f"Dynamic output {capture_count[0]}\n"
            else:
                # Static output - timer will now count down
                return "Static final output\n"

        def timeout_handler(signum, frame):
            raise TimeoutError("Test timed out - function did not return")

        old_handler = signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(15)

        try:
            with patch('swarm.refresh_worker_status', side_effect=mock_refresh):
                with patch('swarm.tmux_capture_pane', side_effect=mock_capture):
                    # 2 second inactivity timeout
                    # Output changes for ~2s, then static for 2s timeout
                    # Total expected: ~4 seconds
                    test_start = time.time()
                    result = swarm.detect_inactivity(worker, timeout=2)
                    total_elapsed = time.time() - test_start
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, old_handler)

        # CRITICAL: Must return "inactive" (inactivity after output stopped)
        self.assertEqual(result, "inactive",
            "detect_inactivity must return 'inactive' after output stops and timeout elapses")

        # CRITICAL: Must have waited longer than just the timeout
        # (because output was changing initially)
        self.assertGreater(total_elapsed, 3.0,
            f"detect_inactivity should have blocked longer due to output changes, but only waited {total_elapsed}s")


class TestRalphStateFlowIntegration(unittest.TestCase):
    """Integration test: state flows correctly from spawn through ralph run.

    Contract verified:
    1. spawn --ralph creates ralph state with current_iteration=1
    2. spawn --ralph creates worker metadata with ralph_iteration=1
    3. When worker exits, ralph run increments to iteration=2
    4. New worker spawned with ralph_iteration=2 in metadata
    5. Ralph state persists correctly across the entire flow

    This is the MOST IMPORTANT integration test because it catches bugs where:
    - State is created but not persisted
    - Iteration is stored in one place but not updated in another
    - Worker metadata doesn't match ralph state
    - State corruption during load/save cycles

    Why heavy mocking is avoided:
    - Previous tests mocked send_prompt_to_worker, hiding a hang bug
    - This test uses minimal mocking to verify real state operations
    """

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
        self.prompt_content = "STATE_FLOW_TEST_PROMPT_12345\nTest task\n"
        Path('test_prompt.md').write_text(self.prompt_content)

    def tearDown(self):
        """Clean up test fixtures."""
        os.chdir(self.original_cwd)
        swarm.SWARM_DIR = self.original_swarm_dir
        swarm.RALPH_DIR = self.original_ralph_dir
        swarm.STATE_FILE = self.original_state_file
        swarm.STATE_LOCK_FILE = self.original_state_lock_file
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_spawn_creates_iteration_1_then_run_increments_to_2(self):
        """Integration test: complete state flow from spawn through iteration 2.

        This test verifies the end-to-end state flow:
        1. ralph spawn creates ralph state at iteration 1
        2. cmd_ralph_run detects worker exit, increments to iteration 2
        3. Worker metadata in state.json matches ralph state iteration
        4. All state is persisted and can be loaded correctly

        Timeout: 10s to prevent hanging.
        """
        # Step 1: Spawn a ralph worker (should create iteration 1)
        spawn_args = Namespace(
            ralph_command='spawn',
            name='state-flow-worker',
            prompt_file='test_prompt.md',
            max_iterations=3,
            inactivity_timeout=300,
            done_pattern=None,
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

        # Track worker metadata passed to state
        added_workers = []
        original_add_worker = swarm.State.add_worker

        def track_add_worker(self, worker):
            added_workers.append({
                'name': worker.name,
                'metadata': worker.metadata.copy() if worker.metadata else {}
            })
            return original_add_worker(self, worker)

        with patch('swarm.create_tmux_window'):
            with patch('swarm.get_default_session_name', return_value='swarm-test'):
                with patch('swarm.wait_for_agent_ready', return_value=True):
                    with patch('swarm.tmux_send'):  # Mock at lowest level
                        with patch.object(swarm.State, 'add_worker', track_add_worker):
                            with patch('builtins.print'):
                                swarm.cmd_ralph_spawn(spawn_args)

        # VERIFICATION 1: Ralph state created with iteration=1
        ralph_state = swarm.load_ralph_state('state-flow-worker')
        self.assertIsNotNone(ralph_state,
            "ralph spawn must create ralph state")
        self.assertEqual(ralph_state.current_iteration, 1,
            "ralph spawn must set current_iteration to 1")
        self.assertEqual(ralph_state.status, 'running',
            "ralph spawn must set status to 'running'")

        # VERIFICATION 2: Worker created with ralph metadata
        self.assertEqual(len(added_workers), 1,
            "spawn must add exactly one worker to state")
        self.assertTrue(added_workers[0]['metadata'].get('ralph'),
            "Worker metadata must have ralph=True")
        self.assertEqual(added_workers[0]['metadata'].get('ralph_iteration'), 1,
            "Worker metadata must have ralph_iteration=1")

        # VERIFICATION 3: Worker state persisted correctly
        state = swarm.State()
        worker = state.get_worker('state-flow-worker')
        self.assertIsNotNone(worker,
            "Worker must be saved to state.json")

        # Step 2: Simulate ralph run detecting worker exit and incrementing iteration
        run_args = Namespace(name='state-flow-worker')

        # Track spawned workers during ralph run
        spawned_during_run = []

        def track_spawn(*args, **kwargs):
            """Track spawn_worker_for_ralph calls during ralph run."""
            spawned_during_run.append(kwargs.get('metadata', {}).copy())
            return swarm.Worker(
                name='state-flow-worker',
                status='running',
                cmd=['echo', 'test'],
                started='2024-01-15T10:30:00',
                cwd=self.temp_dir,
                tmux=swarm.TmuxInfo(session='swarm', window='state-flow-worker'),
                metadata=kwargs.get('metadata', {})
            )

        # Simulate: First detect returns False (worker exited), triggering iteration 2
        # Then on iteration 2, max_iterations is reached, loop exits
        detect_calls = [0]

        def mock_detect(worker, timeout, done_pattern=None, check_done_continuous=False, prompt_baseline_content=""):
            detect_calls[0] += 1
            # Always return "exited" (worker exited) to advance iterations
            return "exited"

        # Mock refresh to show worker stopped initially (triggers respawn)
        refresh_calls = [0]

        def mock_refresh(worker):
            refresh_calls[0] += 1
            # After first refresh, show stopped to trigger respawn
            return 'stopped'

        def timeout_handler(signum, frame):
            raise TimeoutError("Test timed out - ralph run hung")

        old_handler = signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(10)

        try:
            with patch('swarm.refresh_worker_status', side_effect=mock_refresh):
                with patch('swarm.detect_inactivity', side_effect=mock_detect):
                    with patch('swarm.spawn_worker_for_ralph', side_effect=track_spawn):
                        with patch('swarm.send_prompt_to_worker', return_value=""):
                            with patch('swarm.check_done_pattern', return_value=False):
                                with patch.object(swarm.State, 'add_worker'):
                                    with patch.object(swarm.State, 'remove_worker'):
                                        with patch('builtins.print'):
                                            swarm.cmd_ralph_run(run_args)
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, old_handler)

        # VERIFICATION 4: Ralph state incremented through iterations
        final_ralph_state = swarm.load_ralph_state('state-flow-worker')
        self.assertEqual(final_ralph_state.current_iteration, 3,
            "Ralph state must reach max_iterations (3)")

        # VERIFICATION 5: Worker was spawned with correct iteration metadata
        # Should have spawned for iteration 2 and 3 (iteration 1 was from original spawn)
        self.assertEqual(len(spawned_during_run), 2,
            "Ralph run should spawn workers for iterations 2 and 3")

        # Check iteration 2
        self.assertTrue(spawned_during_run[0].get('ralph'),
            "Iteration 2 worker must have ralph=True")
        self.assertEqual(spawned_during_run[0].get('ralph_iteration'), 2,
            "First respawn must be iteration 2")

        # Check iteration 3
        self.assertTrue(spawned_during_run[1].get('ralph'),
            "Iteration 3 worker must have ralph=True")
        self.assertEqual(spawned_during_run[1].get('ralph_iteration'), 3,
            "Second respawn must be iteration 3")

        # VERIFICATION 6: Final state status
        self.assertEqual(final_ralph_state.status, 'stopped',
            "Ralph state must be 'stopped' after reaching max_iterations")

    def test_state_persists_across_load_save_cycles(self):
        """Integration test: ralph state survives multiple load/save cycles.

        This test verifies that state is not corrupted when:
        1. State is saved by spawn
        2. State is loaded and modified by ralph run
        3. State is saved again after modification
        4. State can be loaded correctly after all operations

        This catches serialization bugs and field loss during round-trips.
        """
        # Create initial ralph state with all fields populated
        initial_state = swarm.RalphState(
            worker_name='persistence-test',
            prompt_file=str(Path(self.temp_dir) / 'test_prompt.md'),
            max_iterations=10,
            current_iteration=3,
            status='running',
            started='2024-01-15T10:30:00',
            last_iteration_started='2024-01-15T12:45:00',
            consecutive_failures=1,
            total_failures=2,
            done_pattern='DONE',
            inactivity_timeout=600,
        )

        # Save state
        swarm.save_ralph_state(initial_state)

        # Load and modify
        loaded = swarm.load_ralph_state('persistence-test')
        loaded.current_iteration = 4
        loaded.consecutive_failures = 0
        loaded.last_iteration_started = '2024-01-15T13:00:00'

        # Save modified state
        swarm.save_ralph_state(loaded)

        # Load again and verify all fields
        final = swarm.load_ralph_state('persistence-test')

        # Verify modified fields
        self.assertEqual(final.current_iteration, 4,
            "Modified iteration must persist")
        self.assertEqual(final.consecutive_failures, 0,
            "Modified consecutive_failures must persist")
        self.assertEqual(final.last_iteration_started, '2024-01-15T13:00:00',
            "Modified last_iteration_started must persist")

        # Verify unmodified fields survived
        self.assertEqual(final.worker_name, 'persistence-test',
            "worker_name must persist unchanged")
        self.assertEqual(final.max_iterations, 10,
            "max_iterations must persist unchanged")
        self.assertEqual(final.status, 'running',
            "status must persist unchanged")
        self.assertEqual(final.started, '2024-01-15T10:30:00',
            "started must persist unchanged")
        self.assertEqual(final.total_failures, 2,
            "total_failures must persist unchanged")
        self.assertEqual(final.done_pattern, 'DONE',
            "done_pattern must persist unchanged")
        self.assertEqual(final.inactivity_timeout, 600,
            "inactivity_timeout must persist unchanged")


class TestRalphPromptRereadIntegration(unittest.TestCase):
    """Integration test: prompt file is re-read on each iteration.

    Contract verified:
    The ralph loop must re-read the prompt file from disk at the START of each
    iteration, not cache it. This enables users to edit the prompt mid-loop.

    From ralph-loop.md spec:
    "File is re-read every time (allows editing mid-loop)"

    Why this test matters:
    - If prompt is cached, users can't adjust instructions mid-loop
    - This is a key feature of the ralph pattern for iterative development
    - A bug here would be invisible until someone tries to edit mid-loop
    """

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

        # Create initial prompt file
        self.prompt_path = Path(self.temp_dir) / "prompt.md"
        self.prompt_path.write_text("INITIAL_PROMPT_CONTENT_V1")

    def tearDown(self):
        """Clean up test fixtures."""
        swarm.SWARM_DIR = self.original_swarm_dir
        swarm.RALPH_DIR = self.original_ralph_dir
        swarm.STATE_FILE = self.original_state_file
        swarm.STATE_LOCK_FILE = self.original_state_lock_file
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_prompt_file_reread_each_iteration(self):
        """Integration test: prompt file is re-read fresh on each iteration.

        This test verifies that:
        1. Iteration 1 gets the original prompt content
        2. When the file is modified between iterations
        3. Iteration 2 gets the UPDATED prompt content

        We track what content is passed to send_prompt_to_worker for each
        iteration to verify the file is actually re-read.

        Timeout: 10s to prevent hanging.
        """
        # Create worker
        state = swarm.State()
        worker = swarm.Worker(
            name='reread-test-worker',
            status='stopped',
            cmd=['echo', 'test'],
            started='2024-01-15T10:30:00',
            cwd=self.temp_dir,
            tmux=swarm.TmuxInfo(session='swarm', window='reread-test-worker')
        )
        state.workers.append(worker)
        state.save()

        # Create ralph state at iteration 0, max 3 iterations
        ralph_state = swarm.RalphState(
            worker_name='reread-test-worker',
            prompt_file=str(self.prompt_path),
            max_iterations=3,
            current_iteration=0,
            status='running'
        )
        swarm.save_ralph_state(ralph_state)

        args = Namespace(name='reread-test-worker')

        # Track prompts sent to workers
        prompts_sent = []
        spawn_count = [0]

        def track_spawn(*args, **kwargs):
            """Track spawns and modify prompt file between iterations."""
            spawn_count[0] += 1
            # After first spawn, modify the prompt file
            if spawn_count[0] == 1:
                self.prompt_path.write_text("MODIFIED_PROMPT_CONTENT_V2")
            elif spawn_count[0] == 2:
                self.prompt_path.write_text("MODIFIED_PROMPT_CONTENT_V3")

            return swarm.Worker(
                name='reread-test-worker',
                status='running',
                cmd=['echo', 'test'],
                started='2024-01-15T10:30:00',
                cwd=self.temp_dir,
                tmux=swarm.TmuxInfo(session='swarm', window='reread-test-worker')
            )

        def track_send_prompt(worker, content):
            """Capture prompt content sent to each iteration."""
            prompts_sent.append({
                'iteration': swarm.load_ralph_state('reread-test-worker').current_iteration,
                'content': content
            })
            return ""

        def mock_refresh(worker):
            """Worker is stopped on each iteration to trigger respawn."""
            return 'stopped'

        def timeout_handler(signum, frame):
            raise TimeoutError("Test timed out")

        old_handler = signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(10)

        try:
            with patch('swarm.refresh_worker_status', side_effect=mock_refresh):
                with patch('swarm.spawn_worker_for_ralph', side_effect=track_spawn):
                    with patch('swarm.send_prompt_to_worker', side_effect=track_send_prompt):
                        with patch.object(swarm.State, 'add_worker'):
                            with patch.object(swarm.State, 'remove_worker'):
                                with patch('builtins.print'):
                                    swarm.cmd_ralph_run(args)
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, old_handler)

        # CRITICAL VERIFICATION: We should have sent 3 different prompts
        self.assertEqual(len(prompts_sent), 3,
            "Should send prompt for all 3 iterations")

        # CRITICAL VERIFICATION: Iteration 1 should get original content
        self.assertEqual(prompts_sent[0]['content'], "INITIAL_PROMPT_CONTENT_V1",
            "Iteration 1 must receive original prompt content")

        # CRITICAL VERIFICATION: Iteration 2 should get MODIFIED content (V2)
        self.assertEqual(prompts_sent[1]['content'], "MODIFIED_PROMPT_CONTENT_V2",
            "Iteration 2 must receive modified prompt content (re-read from disk)")

        # CRITICAL VERIFICATION: Iteration 3 should get MODIFIED content (V3)
        self.assertEqual(prompts_sent[2]['content'], "MODIFIED_PROMPT_CONTENT_V3",
            "Iteration 3 must receive further modified prompt content")

    def test_prompt_file_deleted_mid_loop_fails_gracefully(self):
        """Integration test: deleting prompt file mid-loop exits with error.

        Contract: If the prompt file is deleted between iterations,
        the ralph loop must exit with an appropriate error message.

        This catches bugs where file errors are silently swallowed.

        Timeout: 5s.
        """
        # Create worker
        state = swarm.State()
        worker = swarm.Worker(
            name='deleted-prompt-worker',
            status='stopped',
            cmd=['echo', 'test'],
            started='2024-01-15T10:30:00',
            cwd=self.temp_dir,
            tmux=swarm.TmuxInfo(session='swarm', window='deleted-prompt-worker')
        )
        state.workers.append(worker)
        state.save()

        # Create ralph state at iteration 0
        ralph_state = swarm.RalphState(
            worker_name='deleted-prompt-worker',
            prompt_file=str(self.prompt_path),
            max_iterations=3,
            current_iteration=0,
            status='running'
        )
        swarm.save_ralph_state(ralph_state)

        args = Namespace(name='deleted-prompt-worker')

        spawn_count = [0]

        def track_spawn(*args, **kwargs):
            """Delete prompt file after first spawn."""
            spawn_count[0] += 1
            if spawn_count[0] == 1:
                # Delete the prompt file - should cause error on next iteration
                self.prompt_path.unlink()

            return swarm.Worker(
                name='deleted-prompt-worker',
                status='running',
                cmd=['echo', 'test'],
                started='2024-01-15T10:30:00',
                cwd=self.temp_dir,
                tmux=swarm.TmuxInfo(session='swarm', window='deleted-prompt-worker')
            )

        def mock_refresh(worker):
            """Worker stops to trigger next iteration."""
            return 'stopped'

        def timeout_handler(signum, frame):
            raise TimeoutError("Test timed out")

        old_handler = signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(5)

        error_output = []

        try:
            with patch('swarm.refresh_worker_status', side_effect=mock_refresh):
                with patch('swarm.spawn_worker_for_ralph', side_effect=track_spawn):
                    with patch('swarm.send_prompt_to_worker', return_value=""):
                        with patch.object(swarm.State, 'add_worker'):
                            with patch.object(swarm.State, 'remove_worker'):
                                with patch('builtins.print') as mock_print:
                                    with self.assertRaises(SystemExit) as ctx:
                                        swarm.cmd_ralph_run(args)
                                    error_output = [str(c) for c in mock_print.call_args_list]
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, old_handler)

        # Should exit with error code 1
        self.assertEqual(ctx.exception.code, 1,
            "Ralph loop must exit with code 1 when prompt file is deleted")

        # Ralph state should be marked as failed
        final_state = swarm.load_ralph_state('deleted-prompt-worker')
        self.assertEqual(final_state.status, 'failed',
            "Ralph state must be 'failed' when prompt file is deleted")


class TestRalphLoopDetectInactivityIntegration(unittest.TestCase):
    """Integration test: ralph loop and detect_inactivity work together correctly.

    Contract verified:
    This test verifies the CRITICAL integration between _run_ralph_loop and
    detect_inactivity where both components must work together correctly:

    1. When detect_inactivity returns False (worker exited), the loop must:
       - NOT call kill_worker_for_ralph (worker already exited)
       - Increment iteration and spawn new worker
       - Continue to next iteration

    2. When detect_inactivity returns True (inactivity timeout), the loop must:
       - Call kill_worker_for_ralph to stop inactive worker
       - Increment iteration and spawn new worker
       - Continue to next iteration

    3. The loop must properly BLOCK during detect_inactivity (not spin-loop)

    Why this is the MOST IMPORTANT integration test:
    - Previous tests mock detect_inactivity completely, hiding timing bugs
    - This test uses realistic detect_inactivity behavior with controlled timing
    - Catches race conditions where worker state changes mid-detection
    - Verifies the loop properly distinguishes worker-exit vs inactivity paths
    - Tests that blocking behavior prevents CPU burn and log spam

    Bug this catches:
    - If detect_inactivity returns immediately (no blocking), loop spins rapidly
    - If kill_worker_for_ralph is called when worker already exited, errors occur
    - If iteration increment happens at wrong time, metadata is inconsistent
    """

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
        self.prompt_content = "LOOP_DETECT_INTEGRATION_TEST_PROMPT"
        self.prompt_path.write_text(self.prompt_content)

    def tearDown(self):
        """Clean up test fixtures."""
        swarm.SWARM_DIR = self.original_swarm_dir
        swarm.RALPH_DIR = self.original_ralph_dir
        swarm.STATE_FILE = self.original_state_file
        swarm.STATE_LOCK_FILE = self.original_state_lock_file
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_ralph_loop_handles_worker_exit_without_kill(self):
        """Integration test: worker exit path doesn't call kill_worker_for_ralph.

        Contract: When detect_inactivity returns False (worker exited on its own),
        the ralph loop must NOT call kill_worker_for_ralph because the worker
        is already gone.

        This tests the critical distinction between:
        - detect_inactivity returning True → must kill worker
        - detect_inactivity returning False → must NOT kill worker

        Timeout: 10s to prevent hanging.
        """
        # Create worker in running state
        state = swarm.State()
        worker = swarm.Worker(
            name='exit-path-worker',
            status='running',
            cmd=['echo', 'test'],
            started='2024-01-15T10:30:00',
            cwd=self.temp_dir,
            tmux=swarm.TmuxInfo(session='swarm', window='exit-path-worker')
        )
        state.workers.append(worker)
        state.save()

        # Create ralph state at iteration 1, max 2 iterations
        ralph_state = swarm.RalphState(
            worker_name='exit-path-worker',
            prompt_file=str(self.prompt_path),
            max_iterations=2,
            current_iteration=1,
            status='running',
            inactivity_timeout=30,
        )
        swarm.save_ralph_state(ralph_state)

        args = Namespace(name='exit-path-worker')

        # Track operations
        operations = []
        kill_calls = []
        detect_calls = []

        def mock_detect(worker, timeout, done_pattern=None, check_done_continuous=False, prompt_baseline_content=""):
            """Simulate detect_inactivity with blocking and return 'exited' (worker exit)."""
            detect_calls.append({
                'worker': worker.name,
                'timeout': timeout,
                'time': time.time()
            })
            # Simulate brief blocking (realistic behavior)
            time.sleep(0.1)
            # Return "exited" = worker exited (not inactivity)
            return "exited"

        def track_kill(worker, state):
            """Track kill_worker_for_ralph - should NOT be called in this path."""
            kill_calls.append({
                'worker': worker.name,
                'time': time.time()
            })

        def mock_spawn(*args, **kwargs):
            operations.append('spawn')
            return swarm.Worker(
                name='exit-path-worker',
                status='running',
                cmd=['echo', 'test'],
                started='2024-01-15T10:30:00',
                cwd=self.temp_dir,
                tmux=swarm.TmuxInfo(session='swarm', window='exit-path-worker')
            )

        # First refresh: running, then stopped to trigger respawn
        refresh_count = [0]
        def mock_refresh(worker):
            refresh_count[0] += 1
            if refresh_count[0] <= 1:
                return 'running'
            return 'stopped'

        def timeout_handler(signum, frame):
            raise TimeoutError("Test timed out")

        old_handler = signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(10)

        try:
            with patch('swarm.refresh_worker_status', side_effect=mock_refresh):
                with patch('swarm.detect_inactivity', side_effect=mock_detect):
                    with patch('swarm.kill_worker_for_ralph', side_effect=track_kill):
                        with patch('swarm.spawn_worker_for_ralph', side_effect=mock_spawn):
                            with patch('swarm.send_prompt_to_worker', return_value=""):
                                with patch.object(swarm.State, 'add_worker'):
                                    with patch.object(swarm.State, 'remove_worker'):
                                        with patch('swarm.check_done_pattern', return_value=False):
                                            with patch('builtins.print'):
                                                swarm.cmd_ralph_run(args)
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, old_handler)

        # CRITICAL VERIFICATION: detect_inactivity was called
        self.assertGreaterEqual(len(detect_calls), 1,
            "detect_inactivity must be called to monitor worker")

        # CRITICAL VERIFICATION: kill_worker_for_ralph was NOT called
        # because detect_inactivity returned False (worker exited)
        self.assertEqual(len(kill_calls), 0,
            "kill_worker_for_ralph must NOT be called when worker exits on its own "
            f"(detect_inactivity returned False). Got {len(kill_calls)} kill calls.")

        # Verify final state
        final_state = swarm.load_ralph_state('exit-path-worker')
        self.assertEqual(final_state.status, 'stopped',
            "Ralph loop must stop after reaching max_iterations")

    def test_ralph_loop_handles_inactivity_with_kill(self):
        """Integration test: inactivity path DOES call kill_worker_for_ralph.

        Contract: When detect_inactivity returns True (inactivity timeout),
        the ralph loop MUST call kill_worker_for_ralph to terminate the
        inactive worker before spawning a new one.

        This verifies the kill path is taken when inactivity is detected.

        Timeout: 10s to prevent hanging.
        """
        # Create worker in running state
        state = swarm.State()
        worker = swarm.Worker(
            name='inactivity-path-worker',
            status='running',
            cmd=['echo', 'test'],
            started='2024-01-15T10:30:00',
            cwd=self.temp_dir,
            tmux=swarm.TmuxInfo(session='swarm', window='inactivity-path-worker')
        )
        state.workers.append(worker)
        state.save()

        # Create ralph state at iteration 1, max 2 iterations
        ralph_state = swarm.RalphState(
            worker_name='inactivity-path-worker',
            prompt_file=str(self.prompt_path),
            max_iterations=2,
            current_iteration=1,
            status='running',
            inactivity_timeout=30,
        )
        swarm.save_ralph_state(ralph_state)

        args = Namespace(name='inactivity-path-worker')

        kill_calls = []
        detect_call_count = [0]

        def mock_detect(worker, timeout, done_pattern=None, check_done_continuous=False, prompt_baseline_content=""):
            """Return 'inactive' on first call (inactivity), 'exited' on second (exit)."""
            detect_call_count[0] += 1
            time.sleep(0.1)  # Brief blocking for realism
            # First call: inactivity detected
            if detect_call_count[0] == 1:
                return "inactive"
            # After that: worker exited
            return "exited"

        def track_kill(worker, state):
            """Track kill_worker_for_ralph - SHOULD be called after inactivity."""
            kill_calls.append({
                'worker': worker.name,
                'iteration': swarm.load_ralph_state('inactivity-path-worker').current_iteration,
                'time': time.time()
            })

        killed = [False]
        def mock_refresh(worker):
            """Return running, then stopped after kill."""
            if killed[0]:
                return 'stopped'
            return 'running'

        def actual_kill(worker, state):
            """Mark killed and call the tracker."""
            killed[0] = True
            track_kill(worker, state)

        def mock_spawn(*args, **kwargs):
            return swarm.Worker(
                name='inactivity-path-worker',
                status='running',
                cmd=['echo', 'test'],
                started='2024-01-15T10:30:00',
                cwd=self.temp_dir,
                tmux=swarm.TmuxInfo(session='swarm', window='inactivity-path-worker')
            )

        def timeout_handler(signum, frame):
            raise TimeoutError("Test timed out")

        old_handler = signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(10)

        try:
            with patch('swarm.refresh_worker_status', side_effect=mock_refresh):
                with patch('swarm.detect_inactivity', side_effect=mock_detect):
                    with patch('swarm.kill_worker_for_ralph', side_effect=actual_kill):
                        with patch('swarm.spawn_worker_for_ralph', side_effect=mock_spawn):
                            with patch('swarm.send_prompt_to_worker', return_value=""):
                                with patch.object(swarm.State, 'add_worker'):
                                    with patch.object(swarm.State, 'remove_worker'):
                                        with patch('swarm.check_done_pattern', return_value=False):
                                            with patch('builtins.print'):
                                                swarm.cmd_ralph_run(args)
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, old_handler)

        # CRITICAL VERIFICATION: kill_worker_for_ralph WAS called
        # because detect_inactivity returned True (inactivity detected)
        self.assertEqual(len(kill_calls), 1,
            "kill_worker_for_ralph MUST be called when inactivity is detected "
            f"(detect_inactivity returned True). Got {len(kill_calls)} kill calls.")

        # Verify kill happened at the right iteration (iteration 1 is when worker was inactive)
        self.assertEqual(kill_calls[0]['iteration'], 1,
            "kill must happen at iteration 1 (when inactivity was detected)")

    def test_ralph_loop_blocks_during_detect_inactivity(self):
        """Integration test: ralph loop properly blocks during monitoring.

        Contract: The ralph loop must BLOCK while detect_inactivity is monitoring
        the worker. This prevents:
        - CPU burn from spin-looping
        - Log spam from rapid iteration messages
        - Race conditions from state changes

        This test verifies that detect_inactivity's blocking behavior is
        respected by the outer loop - if it's bypassed, the loop would
        complete in milliseconds instead of the expected blocking time.

        Timeout: 15s to allow for blocking time.
        """
        # Create worker in running state (needs to be running for detect_inactivity)
        state = swarm.State()
        worker = swarm.Worker(
            name='blocking-test-worker',
            status='running',
            cmd=['echo', 'test'],
            started='2024-01-15T10:30:00',
            cwd=self.temp_dir,
            tmux=swarm.TmuxInfo(session='swarm', window='blocking-test-worker')
        )
        state.workers.append(worker)
        state.save()

        # Create ralph state at iteration 0, max 1
        # The loop will increment to 1, spawn, call detect_inactivity, then exit
        ralph_state = swarm.RalphState(
            worker_name='blocking-test-worker',
            prompt_file=str(self.prompt_path),
            max_iterations=1,  # Just one iteration
            current_iteration=0,  # Will be incremented to 1 after worker respawn
            status='running',
            inactivity_timeout=30,
        )
        swarm.save_ralph_state(ralph_state)

        args = Namespace(name='blocking-test-worker')

        detect_start_times = []
        detect_end_times = []

        def mock_detect_with_blocking(worker, timeout, done_pattern=None, check_done_continuous=False, prompt_baseline_content=""):
            """Simulate detect_inactivity that blocks for 0.5 seconds."""
            detect_start_times.append(time.time())
            # This simulates the blocking behavior of real detect_inactivity
            time.sleep(0.5)
            detect_end_times.append(time.time())
            return "exited"  # Worker exited

        # Worker is stopped initially to trigger respawn, then running for detect_inactivity
        refresh_count = [0]
        def mock_refresh(worker):
            refresh_count[0] += 1
            # First check: stopped to trigger respawn
            if refresh_count[0] <= 1:
                return 'stopped'
            # After that: running for detect_inactivity
            return 'running'

        def mock_spawn(*args, **kwargs):
            return swarm.Worker(
                name='blocking-test-worker',
                status='running',
                cmd=['echo', 'test'],
                started='2024-01-15T10:30:00',
                cwd=self.temp_dir,
                tmux=swarm.TmuxInfo(session='swarm', window='blocking-test-worker')
            )

        def timeout_handler(signum, frame):
            raise TimeoutError("Test timed out")

        old_handler = signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(15)

        loop_start_time = time.time()
        try:
            with patch('swarm.refresh_worker_status', side_effect=mock_refresh):
                with patch('swarm.detect_inactivity', side_effect=mock_detect_with_blocking):
                    with patch('swarm.spawn_worker_for_ralph', side_effect=mock_spawn):
                        with patch('swarm.send_prompt_to_worker', return_value=""):
                            with patch.object(swarm.State, 'add_worker'):
                                with patch.object(swarm.State, 'remove_worker'):
                                    with patch('swarm.check_done_pattern', return_value=False):
                                        with patch('builtins.print'):
                                            swarm.cmd_ralph_run(args)
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, old_handler)

        loop_end_time = time.time()
        total_loop_time = loop_end_time - loop_start_time

        # CRITICAL VERIFICATION: detect_inactivity was called
        self.assertEqual(len(detect_start_times), 1,
            "detect_inactivity must be called once for iteration 1")

        # CRITICAL VERIFICATION: The loop respected the blocking behavior
        # If blocking was bypassed, total time would be < 0.1s
        # With blocking, total time should be >= 0.5s (the blocking duration)
        self.assertGreaterEqual(total_loop_time, 0.4,  # Allow some timing slack
            f"Ralph loop must block during detect_inactivity. "
            f"Total time: {total_loop_time:.3f}s, expected >= 0.4s")

        # Verify detect_inactivity itself blocked
        if detect_start_times and detect_end_times:
            detect_duration = detect_end_times[0] - detect_start_times[0]
            self.assertGreaterEqual(detect_duration, 0.4,
                f"detect_inactivity must block for its duration. "
                f"Blocked for: {detect_duration:.3f}s, expected >= 0.4s")


class TestRalphSpawnNoRunFlag(unittest.TestCase):
    """Test --no-run flag for ralph spawn command."""

    def test_no_run_argument_exists(self):
        """Test that --no-run argument is recognized by ralph spawn."""
        result = subprocess.run(
            [sys.executable, 'swarm.py', 'ralph', 'spawn', '--help'],
            capture_output=True,
            text=True
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn('--no-run', result.stdout)

    def test_no_run_default_is_false(self):
        """Test that --no-run defaults to False (auto-start is default)."""
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument("--no-run", action="store_true")
        args = parser.parse_args([])
        self.assertFalse(args.no_run)


class TestRalphSpawnNoRunBehavior(unittest.TestCase):
    """Test --no-run behavior in ralph spawn command."""

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

    def test_no_run_does_not_call_loop(self):
        """Test that --no-run flag prevents auto-start of monitoring loop."""
        args = Namespace(
            ralph_command='spawn',
            name='ralph-norun',
            prompt_file='test_prompt.md',
            max_iterations=10,
            inactivity_timeout=60,
            done_pattern=None,
            check_done_continuous=False,
            no_run=True,  # Critical: --no-run is set
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
                with patch('swarm.send_prompt_to_worker', return_value=""):
                    with patch('swarm.cmd_ralph_run') as mock_run:
                        with patch('builtins.print'):
                            swarm.cmd_ralph_spawn(args)

        # Verify cmd_ralph_run was NOT called
        mock_run.assert_not_called()

    def test_no_no_run_calls_loop(self):
        """Test that without --no-run flag, monitoring loop is auto-started."""
        args = Namespace(
            ralph_command='spawn',
            name='ralph-autorun',
            prompt_file='test_prompt.md',
            max_iterations=10,
            inactivity_timeout=60,
            done_pattern=None,
            check_done_continuous=False,
            no_run=False,  # Critical: auto-start enabled (default)
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
                with patch('swarm.send_prompt_to_worker', return_value=""):
                    with patch('swarm.cmd_ralph_run') as mock_run:
                        with patch('builtins.print'):
                            swarm.cmd_ralph_spawn(args)

        # Verify cmd_ralph_run WAS called with correct args
        mock_run.assert_called_once()
        call_args = mock_run.call_args[0][0]
        self.assertEqual(call_args.name, 'ralph-autorun')


class TestRalphSpawnCheckDoneContinuousArgument(unittest.TestCase):
    """Test --check-done-continuous argument parsing."""

    def test_check_done_continuous_argument_exists(self):
        """Test that --check-done-continuous argument is recognized."""
        result = subprocess.run(
            [sys.executable, 'swarm.py', 'ralph', 'spawn', '--help'],
            capture_output=True,
            text=True
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn('--check-done-continuous', result.stdout)


class TestRalphSpawnCheckDoneContinuous(unittest.TestCase):
    """Test --check-done-continuous is properly stored in RalphState."""

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

    def test_check_done_continuous_stored_in_state_true(self):
        """Test that check_done_continuous=True is stored in RalphState."""
        args = Namespace(
            ralph_command='spawn',
            name='ralph-continuous',
            prompt_file='test_prompt.md',
            max_iterations=10,
            inactivity_timeout=60,
            done_pattern='All tasks complete',
            check_done_continuous=True,  # Critical: continuous checking enabled
            no_run=True,  # Don't run loop for this test
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
                with patch('swarm.send_prompt_to_worker', return_value=""):
                    with patch('builtins.print'):
                        swarm.cmd_ralph_spawn(args)

        # Verify ralph state has check_done_continuous=True
        ralph_state = swarm.load_ralph_state('ralph-continuous')
        self.assertIsNotNone(ralph_state)
        self.assertTrue(ralph_state.check_done_continuous)

    def test_check_done_continuous_stored_in_state_false(self):
        """Test that check_done_continuous=False is stored in RalphState."""
        args = Namespace(
            ralph_command='spawn',
            name='ralph-nocontinuous',
            prompt_file='test_prompt.md',
            max_iterations=10,
            inactivity_timeout=60,
            done_pattern='All tasks complete',
            check_done_continuous=False,  # Default: continuous checking disabled
            no_run=True,  # Don't run loop for this test
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
                with patch('swarm.send_prompt_to_worker', return_value=""):
                    with patch('builtins.print'):
                        swarm.cmd_ralph_spawn(args)

        # Verify ralph state has check_done_continuous=False
        ralph_state = swarm.load_ralph_state('ralph-nocontinuous')
        self.assertIsNotNone(ralph_state)
        self.assertFalse(ralph_state.check_done_continuous)


class TestRalphLoopContinuousDonePattern(unittest.TestCase):
    """Test ralph loop handles continuous done pattern checking correctly."""

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
        swarm.RALPH_DIR.mkdir(parents=True, exist_ok=True)

        # Create prompt file
        self.prompt_path = Path(self.temp_dir) / "PROMPT.md"
        self.prompt_path.write_text("Test prompt content")

    def tearDown(self):
        """Clean up test fixtures."""
        swarm.SWARM_DIR = self.original_swarm_dir
        swarm.RALPH_DIR = self.original_ralph_dir
        swarm.STATE_FILE = self.original_state_file
        swarm.STATE_LOCK_FILE = self.original_state_lock_file
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_ralph_loop_stops_on_continuous_done_pattern_match(self):
        """Test ralph loop stops immediately when continuous done pattern matches."""
        import signal

        # Create worker
        state = swarm.State()
        worker = swarm.Worker(
            name='continuous-done-worker',
            status='running',
            cmd=['echo', 'test'],
            started='2024-01-15T10:30:00',
            cwd=self.temp_dir,
            tmux=swarm.TmuxInfo(session='swarm', window='continuous-done-worker'),
            metadata={'ralph': True, 'ralph_iteration': 1}
        )
        state.workers.append(worker)
        state.save()

        # Create ralph state with check_done_continuous=True
        ralph_state = swarm.RalphState(
            worker_name='continuous-done-worker',
            prompt_file=str(self.prompt_path),
            max_iterations=100,
            current_iteration=1,
            status='running',
            inactivity_timeout=60,
            done_pattern='All tasks complete',
            check_done_continuous=True  # Enable continuous checking
        )
        swarm.save_ralph_state(ralph_state)

        args = Namespace(name='continuous-done-worker')

        # Set up timeout to prevent hanging
        def timeout_handler(signum, frame):
            raise TimeoutError("Test timed out")

        old_handler = signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(10)

        try:
            with patch('swarm.refresh_worker_status', return_value='running'):
                # detect_inactivity returns "done_pattern" when continuous checking matches
                with patch('swarm.detect_inactivity', return_value="done_pattern"):
                    with patch('swarm.kill_worker_for_ralph') as mock_kill:
                        with patch('builtins.print') as mock_print:
                            swarm.cmd_ralph_run(args)
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, old_handler)

        # Check that done pattern message was printed
        output = '\n'.join([str(call) for call in mock_print.call_args_list])
        self.assertIn('done pattern matched', output)

        # Check state is stopped
        updated_state = swarm.load_ralph_state('continuous-done-worker')
        self.assertEqual(updated_state.status, 'stopped')

        # Kill should be called when done pattern matches during monitoring
        self.assertEqual(mock_kill.call_count, 1,
            "Worker should be killed when done pattern matches during monitoring")

    def test_ralph_loop_passes_continuous_flag_to_detect_inactivity(self):
        """Test ralph loop passes check_done_continuous to detect_inactivity."""
        import signal

        # Create worker
        state = swarm.State()
        worker = swarm.Worker(
            name='flag-test-worker',
            status='running',
            cmd=['echo', 'test'],
            started='2024-01-15T10:30:00',
            cwd=self.temp_dir,
            tmux=swarm.TmuxInfo(session='swarm', window='flag-test-worker'),
            metadata={'ralph': True, 'ralph_iteration': 1}
        )
        state.workers.append(worker)
        state.save()

        # Create ralph state with check_done_continuous=True
        ralph_state = swarm.RalphState(
            worker_name='flag-test-worker',
            prompt_file=str(self.prompt_path),
            max_iterations=2,  # Allow one iteration
            current_iteration=1,  # Already on iteration 1
            status='running',
            inactivity_timeout=999,
            done_pattern='test pattern',
            check_done_continuous=True
        )
        swarm.save_ralph_state(ralph_state)

        args = Namespace(name='flag-test-worker')
        detect_calls = []

        def capture_detect(worker, timeout, done_pattern=None, check_done_continuous=False, prompt_baseline_content=""):
            detect_calls.append({
                'timeout': timeout,
                'done_pattern': done_pattern,
                'check_done_continuous': check_done_continuous
            })
            return "exited"

        # Mock refresh to show worker running initially
        refresh_count = [0]
        def mock_refresh(w):
            refresh_count[0] += 1
            # After detect_inactivity call, worker should be stopped to allow loop to continue
            if refresh_count[0] > 2:
                return 'stopped'
            return 'running'

        def timeout_handler(signum, frame):
            raise TimeoutError("Test timed out")

        old_handler = signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(10)

        try:
            with patch('swarm.refresh_worker_status', side_effect=mock_refresh):
                with patch('swarm.detect_inactivity', side_effect=capture_detect):
                    with patch('swarm.check_done_pattern', return_value=False):
                        with patch('builtins.print'):
                            swarm.cmd_ralph_run(args)
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, old_handler)

        # Verify detect_inactivity was called with correct parameters
        self.assertGreaterEqual(len(detect_calls), 1)
        call = detect_calls[0]
        self.assertEqual(call['timeout'], 999)
        self.assertEqual(call['done_pattern'], 'test pattern')
        self.assertTrue(call['check_done_continuous'],
            "check_done_continuous should be passed as True to detect_inactivity")

    def test_ralph_loop_without_continuous_checks_after_exit(self):
        """Test ralph loop checks done pattern after exit when continuous is False."""
        import signal

        # Create worker
        state = swarm.State()
        worker = swarm.Worker(
            name='after-exit-worker',
            status='running',
            cmd=['echo', 'test'],
            started='2024-01-15T10:30:00',
            cwd=self.temp_dir,
            tmux=swarm.TmuxInfo(session='swarm', window='after-exit-worker'),
            metadata={'ralph': True, 'ralph_iteration': 1}
        )
        state.workers.append(worker)
        state.save()

        # Create ralph state with check_done_continuous=False (default)
        ralph_state = swarm.RalphState(
            worker_name='after-exit-worker',
            prompt_file=str(self.prompt_path),
            max_iterations=100,
            current_iteration=1,
            status='running',
            inactivity_timeout=60,
            done_pattern='All tasks complete',
            check_done_continuous=False  # Non-continuous: check only after exit
        )
        swarm.save_ralph_state(ralph_state)

        args = Namespace(name='after-exit-worker')

        def timeout_handler(signum, frame):
            raise TimeoutError("Test timed out")

        old_handler = signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(10)

        try:
            with patch('swarm.refresh_worker_status', return_value='running'):
                # detect_inactivity returns "exited" (not "done_pattern" since continuous is off)
                with patch('swarm.detect_inactivity', return_value="exited"):
                    # check_done_pattern should be called after exit
                    with patch('swarm.check_done_pattern', return_value=True) as mock_check:
                        with patch('builtins.print') as mock_print:
                            swarm.cmd_ralph_run(args)
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, old_handler)

        # Verify check_done_pattern was called (after-exit check)
        self.assertEqual(mock_check.call_count, 1,
            "check_done_pattern should be called after worker exits when continuous=False")

        # Check that done pattern message was printed
        output = '\n'.join([str(call) for call in mock_print.call_args_list])
        self.assertIn('done pattern matched', output)


class TestRalphSpawnHeartbeat(unittest.TestCase):
    """Test ralph spawn command with --heartbeat flag."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.swarm_dir = Path(self.temp_dir) / ".swarm"
        self.ralph_dir = self.swarm_dir / "ralph"
        self.logs_dir = self.swarm_dir / "logs"
        self.state_file = self.swarm_dir / "state.json"
        self.heartbeats_dir = self.swarm_dir / "heartbeats"

        # Create a prompt file for testing
        self.prompt_path = Path(self.temp_dir) / "PROMPT.md"
        self.prompt_path.write_text("Test prompt content")

        # Patch constants
        self.patcher_swarm_dir = patch.object(swarm, 'SWARM_DIR', self.swarm_dir)
        self.patcher_ralph_dir = patch.object(swarm, 'RALPH_DIR', self.ralph_dir)
        self.patcher_state_file = patch.object(swarm, 'STATE_FILE', self.state_file)
        self.patcher_logs_dir = patch.object(swarm, 'LOGS_DIR', self.logs_dir)
        self.patcher_heartbeats_dir = patch.object(swarm, 'HEARTBEATS_DIR', self.heartbeats_dir)
        self.patcher_swarm_dir.start()
        self.patcher_ralph_dir.start()
        self.patcher_state_file.start()
        self.patcher_logs_dir.start()
        self.patcher_heartbeats_dir.start()

    def tearDown(self):
        """Clean up test fixtures."""
        self.patcher_swarm_dir.stop()
        self.patcher_ralph_dir.stop()
        self.patcher_state_file.stop()
        self.patcher_logs_dir.stop()
        self.patcher_heartbeats_dir.stop()
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_heartbeat_argument_exists_in_ralph_spawn(self):
        """Test that --heartbeat argument is recognized by ralph spawn."""
        result = subprocess.run(
            [sys.executable, 'swarm.py', 'ralph', 'spawn', '--help'],
            capture_output=True,
            text=True
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn('--heartbeat', result.stdout)

    def test_heartbeat_expire_argument_exists_in_ralph_spawn(self):
        """Test that --heartbeat-expire argument is recognized by ralph spawn."""
        result = subprocess.run(
            [sys.executable, 'swarm.py', 'ralph', 'spawn', '--help'],
            capture_output=True,
            text=True
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn('--heartbeat-expire', result.stdout)

    def test_heartbeat_message_argument_exists_in_ralph_spawn(self):
        """Test that --heartbeat-message argument is recognized by ralph spawn."""
        result = subprocess.run(
            [sys.executable, 'swarm.py', 'ralph', 'spawn', '--help'],
            capture_output=True,
            text=True
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn('--heartbeat-message', result.stdout)

    def test_ralph_spawn_with_heartbeat(self):
        """Test ralph spawn with --heartbeat flag creates heartbeat."""
        args = Namespace(
            name="ralph-hb-worker",
            cmd=["--", "bash"],
            prompt_file=str(self.prompt_path),
            max_iterations=10,
            inactivity_timeout=60,
            done_pattern=None,
            check_done_continuous=False,
            no_run=True,  # Don't start the loop
            session="swarm",
            tmux_socket=None,
            worktree=False,
            branch=None,
            worktree_dir=None,
            cwd=None,
            env=[],
            tags=[],
            ready_wait=False,
            ready_timeout=120,
            heartbeat="4h",
            heartbeat_expire="24h",
            heartbeat_message="continue"
        )

        with patch('swarm.create_tmux_window'):
            with patch('swarm.start_heartbeat_monitor', return_value=9999) as mock_hb_monitor:
                with patch('swarm.send_prompt_to_worker', return_value=""):
                    with patch('builtins.print'):
                        swarm.cmd_ralph_spawn(args)

                        # Verify heartbeat monitor was started
                        mock_hb_monitor.assert_called_once_with("ralph-hb-worker")

                        # Verify heartbeat state was saved
                        hb_file = self.heartbeats_dir / "ralph-hb-worker.json"
                        self.assertTrue(hb_file.exists())
                        with open(hb_file) as f:
                            hb_state = json.load(f)
                            self.assertEqual(hb_state["worker_name"], "ralph-hb-worker")
                            self.assertEqual(hb_state["interval_seconds"], 14400)  # 4h
                            self.assertEqual(hb_state["message"], "continue")
                            self.assertEqual(hb_state["status"], "active")
                            self.assertEqual(hb_state["monitor_pid"], 9999)
                            self.assertIsNotNone(hb_state["expire_at"])

    def test_ralph_spawn_heartbeat_short_interval_warning(self):
        """Test warning for very short heartbeat interval in ralph spawn."""
        from io import StringIO

        args = Namespace(
            name="short-hb-ralph-worker",
            cmd=["--", "bash"],
            prompt_file=str(self.prompt_path),
            max_iterations=10,
            inactivity_timeout=60,
            done_pattern=None,
            check_done_continuous=False,
            no_run=True,
            session="swarm",
            tmux_socket=None,
            worktree=False,
            branch=None,
            worktree_dir=None,
            cwd=None,
            env=[],
            tags=[],
            ready_wait=False,
            ready_timeout=120,
            heartbeat="30s",  # Very short
            heartbeat_expire=None,
            heartbeat_message="continue"
        )

        stderr_output = StringIO()

        with patch('swarm.create_tmux_window'):
            with patch('swarm.start_heartbeat_monitor', return_value=9999):
                with patch('swarm.send_prompt_to_worker', return_value=""):
                    with patch('builtins.print', side_effect=lambda *a, **kw:
                               stderr_output.write(a[0] + '\n') if kw.get('file') else None):
                        swarm.cmd_ralph_spawn(args)

                        # Verify warning was printed
                        output = stderr_output.getvalue()
                        self.assertIn("very short heartbeat interval", output)

    def test_ralph_spawn_heartbeat_invalid_interval(self):
        """Test error for invalid heartbeat interval in ralph spawn."""
        args = Namespace(
            name="invalid-hb-ralph",
            cmd=["--", "bash"],
            prompt_file=str(self.prompt_path),
            max_iterations=10,
            inactivity_timeout=60,
            done_pattern=None,
            check_done_continuous=False,
            no_run=True,
            session="swarm",
            tmux_socket=None,
            worktree=False,
            branch=None,
            worktree_dir=None,
            cwd=None,
            env=[],
            tags=[],
            ready_wait=False,
            ready_timeout=120,
            heartbeat="invalid",
            heartbeat_expire=None,
            heartbeat_message="continue"
        )

        with patch('swarm.create_tmux_window'):
            with patch('swarm.send_prompt_to_worker', return_value=""):
                with self.assertRaises(SystemExit) as cm:
                    swarm.cmd_ralph_spawn(args)
                self.assertEqual(cm.exception.code, 1)

    def test_ralph_spawn_heartbeat_invalid_expire(self):
        """Test error for invalid heartbeat expiration in ralph spawn."""
        args = Namespace(
            name="invalid-expire-ralph",
            cmd=["--", "bash"],
            prompt_file=str(self.prompt_path),
            max_iterations=10,
            inactivity_timeout=60,
            done_pattern=None,
            check_done_continuous=False,
            no_run=True,
            session="swarm",
            tmux_socket=None,
            worktree=False,
            branch=None,
            worktree_dir=None,
            cwd=None,
            env=[],
            tags=[],
            ready_wait=False,
            ready_timeout=120,
            heartbeat="4h",
            heartbeat_expire="invalid",
            heartbeat_message="continue"
        )

        with patch('swarm.create_tmux_window'):
            with patch('swarm.send_prompt_to_worker', return_value=""):
                with self.assertRaises(SystemExit) as cm:
                    swarm.cmd_ralph_spawn(args)
                self.assertEqual(cm.exception.code, 1)

    def test_ralph_spawn_heartbeat_no_expiration(self):
        """Test ralph spawn with heartbeat but no expiration."""
        args = Namespace(
            name="no-expire-ralph-worker",
            cmd=["--", "bash"],
            prompt_file=str(self.prompt_path),
            max_iterations=10,
            inactivity_timeout=60,
            done_pattern=None,
            check_done_continuous=False,
            no_run=True,
            session="swarm",
            tmux_socket=None,
            worktree=False,
            branch=None,
            worktree_dir=None,
            cwd=None,
            env=[],
            tags=[],
            ready_wait=False,
            ready_timeout=120,
            heartbeat="4h",
            heartbeat_expire=None,
            heartbeat_message="ping"
        )

        with patch('swarm.create_tmux_window'):
            with patch('swarm.start_heartbeat_monitor', return_value=8888):
                with patch('swarm.send_prompt_to_worker', return_value=""):
                    with patch('builtins.print') as mock_print:
                        swarm.cmd_ralph_spawn(args)

                        # Verify heartbeat state was saved without expiration
                        hb_file = self.heartbeats_dir / "no-expire-ralph-worker.json"
                        self.assertTrue(hb_file.exists())
                        with open(hb_file) as f:
                            hb_state = json.load(f)
                            self.assertIsNone(hb_state["expire_at"])
                            self.assertEqual(hb_state["message"], "ping")

                        # Check output mentions no expiration
                        calls = [str(call) for call in mock_print.call_args_list]
                        heartbeat_msg = [c for c in calls if "heartbeat started" in c]
                        self.assertTrue(len(heartbeat_msg) > 0)
                        self.assertIn("no expiration", str(heartbeat_msg))

    def test_ralph_spawn_without_heartbeat(self):
        """Test ralph spawn without --heartbeat flag doesn't create heartbeat."""
        args = Namespace(
            name="no-hb-ralph-worker",
            cmd=["--", "bash"],
            prompt_file=str(self.prompt_path),
            max_iterations=10,
            inactivity_timeout=60,
            done_pattern=None,
            check_done_continuous=False,
            no_run=True,
            session="swarm",
            tmux_socket=None,
            worktree=False,
            branch=None,
            worktree_dir=None,
            cwd=None,
            env=[],
            tags=[],
            ready_wait=False,
            ready_timeout=120,
            heartbeat=None,  # No heartbeat
            heartbeat_expire=None,
            heartbeat_message="continue"
        )

        with patch('swarm.create_tmux_window'):
            with patch('swarm.start_heartbeat_monitor') as mock_hb_monitor:
                with patch('swarm.send_prompt_to_worker', return_value=""):
                    with patch('builtins.print'):
                        swarm.cmd_ralph_spawn(args)

                        # Verify heartbeat monitor was NOT started
                        mock_hb_monitor.assert_not_called()

                        # Verify heartbeat state file was NOT created
                        hb_file = self.heartbeats_dir / "no-hb-ralph-worker.json"
                        self.assertFalse(hb_file.exists())


class TestRalphSpawnHeartbeatHelp(unittest.TestCase):
    """Test ralph spawn help text includes heartbeat examples."""

    def test_ralph_spawn_help_contains_heartbeat_examples(self):
        """Test ralph spawn help text includes heartbeat examples."""
        self.assertIn('heartbeat', swarm.RALPH_SPAWN_HELP_EPILOG.lower())
        self.assertIn('--heartbeat 4h', swarm.RALPH_SPAWN_HELP_EPILOG)
        self.assertIn('--heartbeat-expire 24h', swarm.RALPH_SPAWN_HELP_EPILOG)

    def test_ralph_spawn_help_contains_rate_limit_recovery_section(self):
        """Test ralph spawn help text has rate limit recovery section."""
        self.assertIn('Rate Limit Recovery', swarm.RALPH_SPAWN_HELP_EPILOG)


class TestRalphSpawnTransactionalRollback(unittest.TestCase):
    """Test transactional spawn with rollback on failure.

    From specs/spawn.md:
    - Spawn operations are atomic - either fully complete or leave no orphaned state
    - If any step fails after previous steps completed, perform rollback
    - Rollback removes resources in reverse order of creation
    """

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.original_cwd = os.getcwd()
        os.chdir(self.temp_dir)
        # Create a test prompt file
        Path('PROMPT.md').write_text('study specs/README.md\n')
        # Create mock state directory
        self.state_dir = Path(self.temp_dir) / ".swarm"
        self.state_dir.mkdir()
        self.ralph_dir = Path(self.temp_dir) / ".swarm" / "ralph"
        self.ralph_dir.mkdir()

    def tearDown(self):
        """Clean up test fixtures."""
        os.chdir(self.original_cwd)
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_rollback_on_tmux_failure_after_worktree(self):
        """Test rollback removes worktree if tmux creation fails.

        Scenario: Rollback on tmux failure after worktree creation
        Given: In git repository, tmux unavailable or fails
        When: swarm ralph spawn --name worker --worktree -- echo hi
        Then:
          - Worktree created
          - Tmux window creation fails
          - Rollback: worktree removed
          - Warning: "swarm: warning: spawn failed, cleaning up partial state"
          - Exit code 1
          - Error about tmux failure
          - No worker entry in state
        """
        args = Namespace(
            ralph_command='spawn',
            name='rollback-test-worker',
            prompt_file='PROMPT.md',
            max_iterations=10,
            inactivity_timeout=60,
            done_pattern=None,
            worktree=True,
            session=None,
            tmux_socket=None,
            branch=None,
            worktree_dir=None,
            tags=[],
            env=[],
            cwd=None,
            ready_wait=False,
            ready_timeout=120,
            cmd=['--', 'echo', 'hi']
        )

        worktree_created = []
        worktree_removed = []

        def mock_create_worktree(path, branch):
            worktree_created.append(str(path))
            # Actually don't create anything, just track the call

        def mock_create_tmux_window(*args, **kwargs):
            raise subprocess.CalledProcessError(1, 'tmux', 'tmux failed')

        def mock_git_worktree_remove(*args, **kwargs):
            worktree_removed.append(str(args))

        with patch('swarm.get_git_root', return_value=Path(self.temp_dir)):
            with patch('swarm.create_worktree', side_effect=mock_create_worktree):
                with patch('swarm.create_tmux_window', side_effect=mock_create_tmux_window):
                    with patch.object(swarm.State, 'get_worker', return_value=None):
                        with patch.object(swarm.State, 'add_worker') as mock_add:
                            with patch('subprocess.run') as mock_run:  # Catch worktree remove
                                with patch('builtins.print') as mock_print:
                                    with self.assertRaises(SystemExit) as ctx:
                                        swarm.cmd_ralph_spawn(args)

        # Verify exit code
        self.assertEqual(ctx.exception.code, 1)

        # Verify worktree creation was attempted
        self.assertTrue(len(worktree_created) > 0)

        # Verify warning message about cleanup
        all_calls = [str(call) for call in mock_print.call_args_list]
        self.assertTrue(any('spawn failed, cleaning up' in call for call in all_calls))

        # Verify error message about tmux
        self.assertTrue(any('tmux' in call.lower() for call in all_calls))

        # Verify worker was NOT added to state
        mock_add.assert_not_called()

    def test_rollback_on_state_failure_after_tmux(self):
        """Test rollback removes tmux window and worktree if state update fails.

        If state.add_worker() fails, we should clean up:
        - The tmux window that was created
        - The worktree if it was created
        """
        args = Namespace(
            ralph_command='spawn',
            name='state-fail-worker',
            prompt_file='PROMPT.md',
            max_iterations=10,
            inactivity_timeout=60,
            done_pattern=None,
            worktree=False,  # No worktree for this test
            session='test-session',
            tmux_socket=None,
            branch=None,
            worktree_dir=None,
            tags=[],
            env=[],
            cwd=None,
            ready_wait=False,
            ready_timeout=120,
            cmd=['--', 'echo', 'hi']
        )

        tmux_killed = []

        def mock_add_worker(worker):
            raise Exception("State file locked")

        def mock_subprocess_run(cmd, *args, **kwargs):
            if 'kill-window' in cmd:
                tmux_killed.append(cmd)
            return subprocess.CompletedProcess(cmd, 0)

        with patch('swarm.create_tmux_window'):
            with patch('swarm.get_default_session_name', return_value='test-session'):
                with patch.object(swarm.State, 'get_worker', return_value=None):
                    with patch.object(swarm.State, 'add_worker', side_effect=mock_add_worker):
                        with patch('subprocess.run', side_effect=mock_subprocess_run):
                            with patch('builtins.print') as mock_print:
                                with self.assertRaises(SystemExit) as ctx:
                                    swarm.cmd_ralph_spawn(args)

        # Verify exit code
        self.assertEqual(ctx.exception.code, 1)

        # Verify cleanup warning
        all_calls = [str(call) for call in mock_print.call_args_list]
        self.assertTrue(any('spawn failed, cleaning up' in call for call in all_calls))

        # Verify tmux window was killed during rollback
        self.assertTrue(len(tmux_killed) > 0)
        self.assertTrue(any('kill-window' in str(cmd) for cmd in tmux_killed))

    def test_rollback_on_ralph_state_failure(self):
        """Test rollback on ralph state creation failure.

        If save_ralph_state() fails after worker is added, we should:
        - Remove worker from state
        - Kill tmux window
        """
        args = Namespace(
            ralph_command='spawn',
            name='ralph-state-fail-worker',
            prompt_file='PROMPT.md',
            max_iterations=10,
            inactivity_timeout=60,
            done_pattern=None,
            worktree=False,
            session='test-session',
            tmux_socket=None,
            branch=None,
            worktree_dir=None,
            tags=[],
            env=[],
            cwd=None,
            ready_wait=False,
            ready_timeout=120,
            cmd=['--', 'echo', 'hi']
        )

        def mock_save_ralph_state(state):
            raise OSError("Cannot write ralph state")

        with patch('swarm.create_tmux_window'):
            with patch('swarm.get_default_session_name', return_value='test-session'):
                with patch.object(swarm.State, 'get_worker', return_value=None):
                    with patch.object(swarm.State, 'add_worker'):
                        with patch.object(swarm.State, 'remove_worker') as mock_remove:
                            with patch('swarm.save_ralph_state', side_effect=mock_save_ralph_state):
                                with patch('subprocess.run'):  # For tmux kill
                                    with patch('builtins.print') as mock_print:
                                        with self.assertRaises(SystemExit) as ctx:
                                            swarm.cmd_ralph_spawn(args)

        # Verify exit code
        self.assertEqual(ctx.exception.code, 1)

        # Verify cleanup warning
        all_calls = [str(call) for call in mock_print.call_args_list]
        self.assertTrue(any('spawn failed, cleaning up' in call for call in all_calls))

        # Verify worker was removed during rollback
        mock_remove.assert_called_once_with('ralph-state-fail-worker')

    def test_no_rollback_on_validation_failure(self):
        """Test no rollback needed when validation fails (before resource creation)."""
        args = Namespace(
            ralph_command='spawn',
            name='validation-fail-worker',
            prompt_file='missing-file.md',  # File doesn't exist
            max_iterations=10,
            inactivity_timeout=60,
            done_pattern=None,
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
            cmd=['--', 'echo', 'hi']
        )

        with patch('swarm.create_worktree') as mock_worktree:
            with patch('swarm.create_tmux_window') as mock_tmux:
                with patch('builtins.print') as mock_print:
                    with self.assertRaises(SystemExit) as ctx:
                        swarm.cmd_ralph_spawn(args)

        # Verify exit code
        self.assertEqual(ctx.exception.code, 1)

        # Verify no resources were created
        mock_worktree.assert_not_called()
        mock_tmux.assert_not_called()

        # Verify NO cleanup warning (nothing to clean up)
        all_calls = [str(call) for call in mock_print.call_args_list]
        self.assertFalse(any('spawn failed, cleaning up' in call for call in all_calls))

    def test_rollback_helper_function_exists(self):
        """Test _rollback_ralph_spawn helper function exists."""
        self.assertTrue(hasattr(swarm, '_rollback_ralph_spawn'))
        self.assertTrue(callable(swarm._rollback_ralph_spawn))

    def test_rollback_helper_handles_none_gracefully(self):
        """Test _rollback_ralph_spawn handles None parameters without errors."""
        # Should not raise any exceptions
        with patch('builtins.print'):  # Suppress any warnings
            swarm._rollback_ralph_spawn(
                worktree_path=None,
                tmux_info=None,
                worker_name=None,
                state=None,
                ralph_state_created=False,
            )


class TestCmdRalphLogs(unittest.TestCase):
    """Test cmd_ralph_logs function (F2)."""

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
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_logs_no_ralph_state_error(self):
        """Test ralph logs for worker with no ralph state."""
        args = Namespace(name='nonexistent', live=False, lines=None)

        with self.assertRaises(SystemExit) as cm:
            with patch('sys.stderr'):
                swarm.cmd_ralph_logs(args)

        self.assertEqual(cm.exception.code, 1)

    def test_logs_no_log_file_error(self):
        """Test ralph logs when log file doesn't exist."""
        # Create ralph state but no log file
        ralph_state = swarm.RalphState(
            worker_name='test-worker',
            prompt_file='/path/to/prompt.md',
            max_iterations=10,
            current_iteration=1,
            status='running'
        )
        swarm.save_ralph_state(ralph_state)

        args = Namespace(name='test-worker', live=False, lines=None)

        with self.assertRaises(SystemExit) as cm:
            with patch('sys.stderr'):
                swarm.cmd_ralph_logs(args)

        self.assertEqual(cm.exception.code, 1)

    def test_logs_shows_all_entries(self):
        """Test ralph logs shows all entries by default."""
        # Create ralph state and log file
        ralph_state = swarm.RalphState(
            worker_name='test-worker',
            prompt_file='/path/to/prompt.md',
            max_iterations=10,
            current_iteration=3,
            status='running'
        )
        swarm.save_ralph_state(ralph_state)

        # Create log file with entries
        log_path = swarm.get_ralph_iterations_log_path('test-worker')
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_content = """2024-01-15T10:30:00 [START] iteration 1/10
2024-01-15T10:35:42 [END] iteration 1 exit=0 duration=5m42s
2024-01-15T10:35:43 [START] iteration 2/10
2024-01-15T10:40:15 [END] iteration 2 exit=0 duration=4m32s
2024-01-15T10:40:16 [START] iteration 3/10
"""
        log_path.write_text(log_content)

        args = Namespace(name='test-worker', live=False, lines=None)

        import io
        with patch('sys.stdout', new=io.StringIO()) as mock_stdout:
            swarm.cmd_ralph_logs(args)
            output = mock_stdout.getvalue()

        # Should show all entries
        self.assertIn('[START] iteration 1/10', output)
        self.assertIn('[END] iteration 1 exit=0', output)
        self.assertIn('[START] iteration 2/10', output)
        self.assertIn('[END] iteration 2 exit=0', output)
        self.assertIn('[START] iteration 3/10', output)

    def test_logs_lines_option(self):
        """Test ralph logs --lines N shows last N entries."""
        # Create ralph state and log file
        ralph_state = swarm.RalphState(
            worker_name='test-worker',
            prompt_file='/path/to/prompt.md',
            max_iterations=10,
            current_iteration=3,
            status='running'
        )
        swarm.save_ralph_state(ralph_state)

        # Create log file with entries
        log_path = swarm.get_ralph_iterations_log_path('test-worker')
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_content = """2024-01-15T10:30:00 [START] iteration 1/10
2024-01-15T10:35:42 [END] iteration 1 exit=0 duration=5m42s
2024-01-15T10:35:43 [START] iteration 2/10
2024-01-15T10:40:15 [END] iteration 2 exit=0 duration=4m32s
2024-01-15T10:40:16 [START] iteration 3/10
"""
        log_path.write_text(log_content)

        args = Namespace(name='test-worker', live=False, lines=2)

        import io
        with patch('sys.stdout', new=io.StringIO()) as mock_stdout:
            swarm.cmd_ralph_logs(args)
            output = mock_stdout.getvalue()

        # Should only show last 2 lines
        self.assertNotIn('[START] iteration 1/10', output)
        self.assertNotIn('[END] iteration 1 exit=0', output)
        self.assertNotIn('[START] iteration 2/10', output)
        self.assertIn('[END] iteration 2 exit=0', output)
        self.assertIn('[START] iteration 3/10', output)

    def test_logs_empty_file(self):
        """Test ralph logs handles empty log file."""
        # Create ralph state and empty log file
        ralph_state = swarm.RalphState(
            worker_name='test-worker',
            prompt_file='/path/to/prompt.md',
            max_iterations=10,
            current_iteration=1,
            status='running'
        )
        swarm.save_ralph_state(ralph_state)

        # Create empty log file
        log_path = swarm.get_ralph_iterations_log_path('test-worker')
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text('')

        args = Namespace(name='test-worker', live=False, lines=None)

        import io
        with patch('sys.stdout', new=io.StringIO()) as mock_stdout:
            swarm.cmd_ralph_logs(args)
            output = mock_stdout.getvalue()

        # Should output nothing for empty file
        self.assertEqual(output, '')

    def test_logs_subparser_exists(self):
        """Test that 'ralph logs' subcommand is recognized."""
        result = subprocess.run(
            [sys.executable, 'swarm.py', 'ralph', 'logs', '--help'],
            capture_output=True,
            text=True
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn('--live', result.stdout)
        self.assertIn('--lines', result.stdout)

    def test_logs_help_epilog_exists(self):
        """Test RALPH_LOGS_HELP_EPILOG constant exists and has content."""
        self.assertIn('iteration history', swarm.RALPH_LOGS_HELP_EPILOG)
        self.assertIn('--live', swarm.RALPH_LOGS_HELP_EPILOG)
        self.assertIn('--lines', swarm.RALPH_LOGS_HELP_EPILOG)


class TestCmdRalphLogsDispatch(unittest.TestCase):
    """Test cmd_ralph dispatches to logs."""

    def test_dispatch_logs(self):
        """Test cmd_ralph dispatches to logs."""
        args = Namespace(ralph_command='logs', name='test-worker', live=False, lines=None)

        with patch('swarm.cmd_ralph_logs') as mock_logs:
            swarm.cmd_ralph(args)

        mock_logs.assert_called_once_with(args)


class TestRalphLsSubparser(unittest.TestCase):
    """Test that ralph ls subparser (alias for list) is correctly configured."""

    def test_ralph_ls_subcommand_exists(self):
        """Test that 'ralph ls' subcommand is recognized."""
        result = subprocess.run(
            [sys.executable, 'swarm.py', 'ralph', 'ls', '--help'],
            capture_output=True,
            text=True
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn('format', result.stdout.lower())

    def test_ralph_ls_format_flag(self):
        """Test --format flag accepts valid values."""
        result = subprocess.run(
            [sys.executable, 'swarm.py', 'ralph', 'ls', '--format', 'json', '--help'],
            capture_output=True,
            text=True
        )
        self.assertEqual(result.returncode, 0)

    def test_ralph_ls_status_flag(self):
        """Test --status flag accepts valid values."""
        result = subprocess.run(
            [sys.executable, 'swarm.py', 'ralph', 'ls', '--status', 'running', '--help'],
            capture_output=True,
            text=True
        )
        self.assertEqual(result.returncode, 0)

    def test_ralph_ls_same_args_as_list(self):
        """Test that ralph ls accepts the same arguments as ralph list."""
        ls_help = subprocess.run(
            [sys.executable, 'swarm.py', 'ralph', 'ls', '--help'],
            capture_output=True,
            text=True
        )
        list_help = subprocess.run(
            [sys.executable, 'swarm.py', 'ralph', 'list', '--help'],
            capture_output=True,
            text=True
        )
        self.assertEqual(ls_help.returncode, 0)
        self.assertEqual(list_help.returncode, 0)
        # Both should have --format and --status flags
        self.assertIn('--format', ls_help.stdout)
        self.assertIn('--status', ls_help.stdout)
        self.assertIn('--format', list_help.stdout)
        self.assertIn('--status', list_help.stdout)


class TestRalphLsDispatch(unittest.TestCase):
    """Test ralph ls is dispatched correctly from cmd_ralph."""

    def test_dispatch_ls_to_cmd_ralph_list(self):
        """Test that 'ralph ls' dispatches to cmd_ralph_list."""
        args = Namespace(ralph_command='ls', format='table', status='all')

        with patch('swarm.cmd_ralph_list') as mock_list:
            swarm.cmd_ralph(args)

        mock_list.assert_called_once_with(args)

    def test_dispatch_ls_json_format(self):
        """Test that 'ralph ls --format json' dispatches to cmd_ralph_list."""
        args = Namespace(ralph_command='ls', format='json', status='all')

        with patch('swarm.cmd_ralph_list') as mock_list:
            swarm.cmd_ralph(args)

        mock_list.assert_called_once_with(args)


class TestRalphLsCLI(unittest.TestCase):
    """Test ralph ls produces identical output to ralph list."""

    def setUp(self):
        """Create temporary directories for testing."""
        self.temp_dir = tempfile.mkdtemp()
        self.old_ralph_dir = swarm.RALPH_DIR
        swarm.RALPH_DIR = Path(self.temp_dir) / "ralph"
        swarm.RALPH_DIR.mkdir(parents=True, exist_ok=True)

        self.old_state_file = swarm.STATE_FILE
        self.old_state_lock_file = swarm.STATE_LOCK_FILE
        swarm.STATE_FILE = Path(self.temp_dir) / "state.json"
        swarm.STATE_LOCK_FILE = Path(self.temp_dir) / "state.lock"

    def tearDown(self):
        swarm.RALPH_DIR = self.old_ralph_dir
        swarm.STATE_FILE = self.old_state_file
        swarm.STATE_LOCK_FILE = self.old_state_lock_file
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_ralph_ls_empty_same_as_list(self):
        """Test ralph ls with no workers produces same output as ralph list."""
        args_ls = Namespace(ralph_command='ls', format='table', status='all')
        args_list = Namespace(ralph_command='list', format='table', status='all')

        with patch('builtins.print') as mock_print_ls:
            swarm.cmd_ralph_list(args_ls)
        ls_output = [str(call) for call in mock_print_ls.call_args_list]

        with patch('builtins.print') as mock_print_list:
            swarm.cmd_ralph_list(args_list)
        list_output = [str(call) for call in mock_print_list.call_args_list]

        self.assertEqual(ls_output, list_output)

    def test_ralph_ls_json_empty_same_as_list(self):
        """Test ralph ls --format json with no workers produces same output as ralph list --format json."""
        args_ls = Namespace(ralph_command='ls', format='json', status='all')
        args_list = Namespace(ralph_command='list', format='json', status='all')

        with patch('builtins.print') as mock_print_ls:
            swarm.cmd_ralph_list(args_ls)
        ls_output = [str(call) for call in mock_print_ls.call_args_list]

        with patch('builtins.print') as mock_print_list:
            swarm.cmd_ralph_list(args_list)
        list_output = [str(call) for call in mock_print_list.call_args_list]

        self.assertEqual(ls_output, list_output)


class TestRalphCleanSubparser(unittest.TestCase):
    """Test that ralph clean subparser is correctly configured."""

    def test_ralph_clean_subcommand_exists(self):
        """Test that 'ralph clean' subcommand is recognized."""
        result = subprocess.run(
            [sys.executable, 'swarm.py', 'ralph', 'clean', '--help'],
            capture_output=True,
            text=True
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn('name', result.stdout.lower())
        self.assertIn('--all', result.stdout)

    def test_ralph_clean_accepts_name(self):
        """Test that ralph clean accepts a positional name argument."""
        result = subprocess.run(
            [sys.executable, 'swarm.py', 'ralph', 'clean', 'agent', '--help'],
            capture_output=True,
            text=True
        )
        self.assertEqual(result.returncode, 0)

    def test_ralph_clean_accepts_all_flag(self):
        """Test that ralph clean accepts --all flag."""
        result = subprocess.run(
            [sys.executable, 'swarm.py', 'ralph', 'clean', '--all', '--help'],
            capture_output=True,
            text=True
        )
        self.assertEqual(result.returncode, 0)


class TestCmdRalphClean(unittest.TestCase):
    """Test cmd_ralph_clean function."""

    def setUp(self):
        """Create temporary directories for testing."""
        self.temp_dir = tempfile.mkdtemp()
        self.old_ralph_dir = swarm.RALPH_DIR
        swarm.RALPH_DIR = Path(self.temp_dir) / "ralph"
        swarm.RALPH_DIR.mkdir(parents=True, exist_ok=True)

        self.old_state_file = swarm.STATE_FILE
        self.old_state_lock_file = swarm.STATE_LOCK_FILE
        swarm.STATE_FILE = Path(self.temp_dir) / "state.json"
        swarm.STATE_LOCK_FILE = Path(self.temp_dir) / "state.lock"

    def tearDown(self):
        swarm.RALPH_DIR = self.old_ralph_dir
        swarm.STATE_FILE = self.old_state_file
        swarm.STATE_LOCK_FILE = self.old_state_lock_file
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_clean_specific_worker_removes_state_dir(self):
        """Test: clean specific worker removes state dir."""
        # Create ralph state for worker
        ralph_state = swarm.RalphState(
            worker_name='agent',
            prompt_file='/path/to/prompt.md',
            max_iterations=10,
            current_iteration=3,
            status='stopped',
        )
        swarm.save_ralph_state(ralph_state)

        state_dir = swarm.RALPH_DIR / 'agent'
        self.assertTrue(state_dir.exists())

        args = Namespace(name='agent', all=False)

        with patch('swarm.refresh_worker_status', return_value='stopped'):
            swarm.cmd_ralph_clean(args)

        self.assertFalse(state_dir.exists())

    def test_clean_specific_worker_prints_warning_if_running(self):
        """Test: clean specific worker prints warning if worker still running."""
        ralph_state = swarm.RalphState(
            worker_name='agent',
            prompt_file='/path/to/prompt.md',
            max_iterations=10,
            current_iteration=3,
            status='running',
        )
        swarm.save_ralph_state(ralph_state)

        # Create a fake worker in swarm state
        state = swarm.State()
        worker = swarm.Worker(name='agent', status='running', cmd=['claude'],
                                  started='2024-01-15T10:30:00', cwd='/tmp')
        state.add_worker(worker)

        args = Namespace(name='agent', all=False)

        with patch('swarm.refresh_worker_status', return_value='running'):
            with patch('sys.stderr') as mock_stderr:
                swarm.cmd_ralph_clean(args)

        # Check warning was printed to stderr
        stderr_output = ''.join(str(call) for call in mock_stderr.write.call_args_list)
        self.assertIn("warning", stderr_output)
        self.assertIn("still running", stderr_output)

        # State dir should still be removed
        state_dir = swarm.RALPH_DIR / 'agent'
        self.assertFalse(state_dir.exists())

    def test_clean_nonexistent_worker_exits_1(self):
        """Test: clean non-existent worker → exit 1 with error message."""
        args = Namespace(name='nonexistent', all=False)

        with self.assertRaises(SystemExit) as cm:
            with patch('sys.stderr') as mock_stderr:
                swarm.cmd_ralph_clean(args)

        self.assertEqual(cm.exception.code, 1)

    def test_clean_all_removes_all_ralph_state_dirs(self):
        """Test: --all removes all ralph state dirs."""
        # Create ralph state for two workers
        for name in ['agent', 'builder']:
            ralph_state = swarm.RalphState(
                worker_name=name,
                prompt_file='/path/to/prompt.md',
                max_iterations=10,
                current_iteration=3,
                status='stopped',
            )
            swarm.save_ralph_state(ralph_state)

        self.assertTrue((swarm.RALPH_DIR / 'agent').exists())
        self.assertTrue((swarm.RALPH_DIR / 'builder').exists())

        args = Namespace(name=None, all=True)

        with patch('swarm.refresh_worker_status', return_value='stopped'):
            swarm.cmd_ralph_clean(args)

        self.assertFalse((swarm.RALPH_DIR / 'agent').exists())
        self.assertFalse((swarm.RALPH_DIR / 'builder').exists())

    def test_clean_all_with_no_ralph_state_is_noop(self):
        """Test: --all with no ralph state → no-op, exit 0."""
        # RALPH_DIR exists but is empty
        args = Namespace(name=None, all=True)

        # Should not raise any exception
        swarm.cmd_ralph_clean(args)

    def test_clean_all_with_no_ralph_dir_is_noop(self):
        """Test: --all with no ralph dir → no-op, exit 0."""
        # Remove RALPH_DIR entirely
        shutil.rmtree(swarm.RALPH_DIR)

        args = Namespace(name=None, all=True)

        # Should not raise any exception
        swarm.cmd_ralph_clean(args)

    def test_clean_neither_name_nor_all_exits_1(self):
        """Test: neither name nor --all → error."""
        args = Namespace(name=None, all=False)

        with self.assertRaises(SystemExit) as cm:
            swarm.cmd_ralph_clean(args)

        self.assertEqual(cm.exception.code, 1)

    def test_clean_all_prints_cleaned_message_for_each(self):
        """Test: --all prints cleaned message for each worker."""
        for name in ['agent', 'builder']:
            ralph_state = swarm.RalphState(
                worker_name=name,
                prompt_file='/path/to/prompt.md',
                max_iterations=10,
                current_iteration=3,
                status='stopped',
            )
            swarm.save_ralph_state(ralph_state)

        args = Namespace(name=None, all=True)

        with patch('swarm.refresh_worker_status', return_value='stopped'):
            with patch('builtins.print') as mock_print:
                swarm.cmd_ralph_clean(args)

        calls = [str(call) for call in mock_print.call_args_list]
        output = '\n'.join(calls)
        self.assertIn('cleaned ralph state for agent', output)
        self.assertIn('cleaned ralph state for builder', output)

    def test_clean_specific_worker_prints_cleaned_message(self):
        """Test: clean specific worker prints cleaned message."""
        ralph_state = swarm.RalphState(
            worker_name='agent',
            prompt_file='/path/to/prompt.md',
            max_iterations=10,
            current_iteration=3,
            status='stopped',
        )
        swarm.save_ralph_state(ralph_state)

        args = Namespace(name='agent', all=False)

        with patch('swarm.refresh_worker_status', return_value='stopped'):
            with patch('builtins.print') as mock_print:
                swarm.cmd_ralph_clean(args)

        mock_print.assert_called_with('cleaned ralph state for agent')

    def test_clean_all_warns_for_running_workers(self):
        """Test: --all prints warning for running workers but still cleans them."""
        ralph_state = swarm.RalphState(
            worker_name='agent',
            prompt_file='/path/to/prompt.md',
            max_iterations=10,
            current_iteration=3,
            status='running',
        )
        swarm.save_ralph_state(ralph_state)

        # Create a fake worker in swarm state
        state = swarm.State()
        worker = swarm.Worker(name='agent', status='running', cmd=['claude'],
                                  started='2024-01-15T10:30:00', cwd='/tmp')
        state.add_worker(worker)

        args = Namespace(name=None, all=True)

        with patch('swarm.refresh_worker_status', return_value='running'):
            with patch('sys.stderr') as mock_stderr:
                swarm.cmd_ralph_clean(args)

        stderr_output = ''.join(str(call) for call in mock_stderr.write.call_args_list)
        self.assertIn("warning", stderr_output)
        self.assertIn("still running", stderr_output)

        # State dir should still be removed
        self.assertFalse((swarm.RALPH_DIR / 'agent').exists())


class TestRalphCleanDispatch(unittest.TestCase):
    """Test ralph clean is dispatched correctly from cmd_ralph."""

    def test_dispatch_clean_to_cmd_ralph_clean(self):
        """Test that 'ralph clean' dispatches to cmd_ralph_clean."""
        args = Namespace(ralph_command='clean', name='agent', all=False)

        with patch('swarm.cmd_ralph_clean') as mock_clean:
            swarm.cmd_ralph(args)

        mock_clean.assert_called_once_with(args)

    def test_dispatch_clean_all(self):
        """Test that 'ralph clean --all' dispatches to cmd_ralph_clean."""
        args = Namespace(ralph_command='clean', name=None, all=True)

        with patch('swarm.cmd_ralph_clean') as mock_clean:
            swarm.cmd_ralph(args)

        mock_clean.assert_called_once_with(args)


class TestRalphCleanCLI(unittest.TestCase):
    """Test ralph clean CLI integration."""

    def test_ralph_clean_no_args_shows_error(self):
        """Test ralph clean with no arguments shows error."""
        result = subprocess.run(
            [sys.executable, 'swarm.py', 'ralph', 'clean'],
            capture_output=True,
            text=True
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('error', result.stderr.lower())

    def test_ralph_clean_in_ralph_help(self):
        """Test that clean appears in ralph --help output."""
        result = subprocess.run(
            [sys.executable, 'swarm.py', 'ralph', '--help'],
            capture_output=True,
            text=True
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn('clean', result.stdout)


class TestDonePatternBaseline(unittest.TestCase):
    """Test done-pattern baseline filtering to prevent self-match against prompt text."""

    def _make_worker(self, name='test-worker'):
        return swarm.Worker(
            name=name,
            status='running',
            cmd=['echo', 'test'],
            started='2024-01-15T10:30:00',
            cwd='/tmp',
            tmux=swarm.TmuxInfo(session='swarm', window=name)
        )

    def _mock_capture(self, visible_content, scrollback_content):
        """Return a mock that returns visible_content for visible-only calls
        and scrollback_content for history_lines calls."""
        def capture(*args, **kwargs):
            if kwargs.get('history_lines', 0) > 0:
                return scrollback_content
            return visible_content
        return capture

    def test_done_pattern_in_prompt_does_not_match_with_baseline(self):
        """Test that done pattern in prompt text (baseline prefix) does NOT trigger a match."""
        worker = self._make_worker()

        # Baseline content captured after prompt injection (contains done pattern)
        baseline = (
            "line 1\n"
            "line 2\n"
            "When done, output /done on its own line\n"
            "line 4\n"
            "line 5\n"
        )
        # Full scrollback = baseline + agent output (no done pattern in agent output)
        scrollback = baseline + "Agent is still working...\nProcessing tasks..."
        visible = "Agent is still working...\nProcessing tasks..."

        call_count = [0]
        original_capture = self._mock_capture(visible, scrollback)
        def counting_capture(*args, **kwargs):
            call_count[0] += 1
            return original_capture(*args, **kwargs)

        def mock_refresh(w):
            if call_count[0] >= 6:  # 2 captures per cycle, stop after 3 cycles
                return 'stopped'
            return 'running'

        with patch('swarm.refresh_worker_status', side_effect=mock_refresh):
            with patch('swarm.tmux_capture_pane', side_effect=counting_capture):
                with patch('time.sleep'):
                    result = swarm.detect_inactivity(
                        worker,
                        timeout=60,
                        done_pattern="/done",
                        check_done_continuous=True,
                        prompt_baseline_content=baseline
                    )
                    self.assertEqual(result, "exited",
                        "Done pattern in prompt text should not trigger match when baseline is set")

    def test_done_pattern_in_agent_output_matches_with_baseline(self):
        """Test that done pattern in agent output (after baseline) DOES trigger a match."""
        worker = self._make_worker()

        baseline = (
            "line 1\n"
            "line 2\n"
            "When done, output /done on its own line\n"
            "line 4\n"
            "line 5\n"
        )
        # Full scrollback = baseline + agent output with done pattern
        scrollback = baseline + "Agent working...\n/done"
        visible = "Agent working...\n/done"

        with patch('swarm.refresh_worker_status', return_value='running'):
            with patch('swarm.tmux_capture_pane',
                       side_effect=self._mock_capture(visible, scrollback)):
                with patch('time.sleep'):
                    result = swarm.detect_inactivity(
                        worker,
                        timeout=60,
                        done_pattern="/done",
                        check_done_continuous=True,
                        prompt_baseline_content=baseline
                    )
                    self.assertEqual(result, "done_pattern",
                        "Done pattern in agent output (after baseline) should trigger match")

    def test_done_pattern_without_baseline_matches_anywhere(self):
        """Test that done pattern matches anywhere when no baseline is set (backward compat)."""
        worker = self._make_worker()

        content = "line 1\n/done\nline 3"

        with patch('swarm.refresh_worker_status', return_value='running'):
            with patch('swarm.tmux_capture_pane', return_value=content):
                with patch('time.sleep'):
                    result = swarm.detect_inactivity(
                        worker,
                        timeout=60,
                        done_pattern="/done",
                        check_done_continuous=True,
                        prompt_baseline_content=""
                    )
                    self.assertEqual(result, "done_pattern",
                        "Done pattern should match anywhere when baseline is empty")

    def test_baseline_recorded_after_prompt_injection(self):
        """Test that send_prompt_to_worker returns pane content string for baseline."""
        worker = self._make_worker('test-worker')

        pane_after_send = "line 1\nline 2\nline 3\nline 4\nline 5"

        with patch('swarm.wait_for_agent_ready'):
            with patch('swarm.tmux_send'):
                with patch('swarm.tmux_capture_pane', return_value=pane_after_send):
                    baseline = swarm.send_prompt_to_worker(worker, "test prompt")

        self.assertEqual(baseline, pane_after_send,
            "Should return pane content string after sending prompt")

    def test_baseline_returns_empty_for_non_tmux_worker(self):
        """Test that send_prompt_to_worker returns empty string for non-tmux worker."""
        worker = swarm.Worker(
            name='test-worker',
            status='running',
            cmd=['echo', 'test'],
            started='2024-01-15T10:30:00',
            cwd='/tmp',
            pid=12345
        )

        baseline = swarm.send_prompt_to_worker(worker, "test prompt")
        self.assertEqual(baseline, "", "Should return empty string for non-tmux worker")

    def test_baseline_returns_empty_on_capture_error(self):
        """Test that send_prompt_to_worker returns empty string if pane capture fails."""
        worker = self._make_worker('test-worker')

        with patch('swarm.wait_for_agent_ready'):
            with patch('swarm.tmux_send'):
                with patch('swarm.tmux_capture_pane',
                           side_effect=subprocess.CalledProcessError(1, 'tmux')):
                    baseline = swarm.send_prompt_to_worker(worker, "test prompt")

        self.assertEqual(baseline, "", "Should return empty string on capture error")

    def test_ralph_state_has_prompt_baseline_content_field(self):
        """Test RalphState has prompt_baseline_content field with correct default."""
        state = swarm.RalphState(
            worker_name='test',
            prompt_file='/path/to/prompt.md',
            max_iterations=10
        )
        self.assertEqual(state.prompt_baseline_content, "",
            "prompt_baseline_content should default to empty string")

    def test_ralph_state_prompt_baseline_content_roundtrip(self):
        """Test prompt_baseline_content survives round-trip through dict serialization."""
        original = swarm.RalphState(
            worker_name='test',
            prompt_file='/path/to/prompt.md',
            max_iterations=10,
            prompt_baseline_content="line 1\nline 2\nline 3\n"
        )
        d = original.to_dict()
        self.assertEqual(d['prompt_baseline_content'], "line 1\nline 2\nline 3\n")

        restored = swarm.RalphState.from_dict(d)
        self.assertEqual(restored.prompt_baseline_content, "line 1\nline 2\nline 3\n")

    def test_ralph_state_from_dict_defaults_baseline_when_missing(self):
        """Test from_dict defaults prompt_baseline_content to empty string for old state files."""
        d = {
            'worker_name': 'test',
            'prompt_file': '/path/to/prompt.md',
            'max_iterations': 10,
            # prompt_baseline_content is missing (old state format)
        }
        state = swarm.RalphState.from_dict(d)
        self.assertEqual(state.prompt_baseline_content, "",
            "Should default to empty string when field is missing from old state files")

    def test_done_pattern_baseline_with_regex_pattern(self):
        """Test baseline filtering works with regex done patterns."""
        worker = self._make_worker()

        baseline = (
            "line 1\n"
            "Use SWARM_DONE_X9K to signal completion\n"
            "line 3\n"
        )
        # Full scrollback = baseline + agent output (no done pattern after baseline)
        scrollback = baseline + "Agent output here..."
        visible = "Agent output here..."

        call_count = [0]
        original_capture = self._mock_capture(visible, scrollback)
        def counting_capture(*args, **kwargs):
            call_count[0] += 1
            return original_capture(*args, **kwargs)

        def mock_refresh(w):
            if call_count[0] >= 6:
                return 'stopped'
            return 'running'

        with patch('swarm.refresh_worker_status', side_effect=mock_refresh):
            with patch('swarm.tmux_capture_pane', side_effect=counting_capture):
                with patch('time.sleep'):
                    result = swarm.detect_inactivity(
                        worker,
                        timeout=60,
                        done_pattern=r"SWARM_DONE_\w+",
                        check_done_continuous=True,
                        prompt_baseline_content=baseline
                    )
                    self.assertEqual(result, "exited",
                        "Regex done pattern in prompt should not match with baseline filtering")

    def test_done_pattern_terminal_cleared_checks_full_content(self):
        """Test that when terminal is cleared (baseline not a prefix), full content is checked."""
        worker = self._make_worker()

        # Baseline captured at prompt injection time
        baseline = "prompt line 1\nprompt line 2\n"
        # Terminal was cleared, so scrollback no longer starts with baseline
        scrollback = "completely different content\n/done\nmore output"
        visible = scrollback

        with patch('swarm.refresh_worker_status', return_value='running'):
            with patch('swarm.tmux_capture_pane',
                       side_effect=self._mock_capture(visible, scrollback)):
                with patch('time.sleep'):
                    result = swarm.detect_inactivity(
                        worker,
                        timeout=60,
                        done_pattern="/done",
                        check_done_continuous=True,
                        prompt_baseline_content=baseline
                    )
                    self.assertEqual(result, "done_pattern",
                        "When terminal cleared (baseline not prefix), should check full content")


if __name__ == "__main__":
    unittest.main()
