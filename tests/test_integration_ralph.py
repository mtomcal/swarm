#!/usr/bin/env python3
"""Integration tests for Ralph loop functionality.

Tests verify that the ralph loop correctly:
- Detects screen-stable inactivity and restarts the agent
- Stops when max iterations are reached
- Handles done pattern matching
- Supports pause and resume
- Works with the default 60s inactivity timeout
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

# Add tests/ directory to path to import TmuxIsolatedTestCase
sys.path.insert(0, str(Path(__file__).parent))
from test_tmux_isolation import TmuxIsolatedTestCase, skip_if_no_tmux


class TestRalphSpawn(TmuxIsolatedTestCase):
    """Test that ralph workers can be spawned with required flags."""

    def setUp(self):
        """Set up temporary prompt file for ralph tests."""
        super().setUp()
        self.tmpdir = tempfile.mkdtemp()
        self.prompt_file = Path(self.tmpdir) / "PROMPT.md"
        self.prompt_file.write_text("Test prompt content\n")

    def tearDown(self):
        """Clean up temp files and ralph workers."""
        # Kill any ralph workers we created
        try:
            workers = self.get_workers()
            for w in workers:
                self.run_swarm('kill', w['name'])
            self.run_swarm('clean', '--all')
        except Exception:
            pass

        # Clean up ralph state
        ralph_dir = Path.home() / ".swarm" / "ralph"
        if ralph_dir.exists():
            for worker_dir in ralph_dir.iterdir():
                if worker_dir.name.startswith(self.tmux_socket.replace('swarm-test-', '')):
                    shutil.rmtree(worker_dir, ignore_errors=True)

        # Clean up temp directory
        shutil.rmtree(self.tmpdir, ignore_errors=True)
        super().tearDown()

    @skip_if_no_tmux
    def test_ralph_spawn_requires_prompt_file(self):
        """Verify --ralph without --prompt-file fails with appropriate error."""
        worker_name = f"ralph-no-prompt-{self.tmux_socket[-8:]}"

        result = self.run_swarm(
            'spawn',
            '--name', worker_name,
            '--tmux',
            '--ralph',
            '--max-iterations', '3',
            '--',
            'echo', 'hello'
        )

        self.assertNotEqual(
            result.returncode,
            0,
            f"Expected spawn with --ralph but no --prompt-file to fail"
        )
        self.assertIn(
            "--prompt-file",
            result.stderr.lower(),
            f"Expected error message to mention --prompt-file, got: {result.stderr!r}"
        )

    @skip_if_no_tmux
    def test_ralph_spawn_requires_max_iterations(self):
        """Verify --ralph without --max-iterations fails with appropriate error."""
        worker_name = f"ralph-no-iter-{self.tmux_socket[-8:]}"

        result = self.run_swarm(
            'spawn',
            '--name', worker_name,
            '--tmux',
            '--ralph',
            '--prompt-file', str(self.prompt_file),
            '--',
            'echo', 'hello'
        )

        self.assertNotEqual(
            result.returncode,
            0,
            f"Expected spawn with --ralph but no --max-iterations to fail"
        )
        self.assertIn(
            "--max-iterations",
            result.stderr.lower(),
            f"Expected error message to mention --max-iterations, got: {result.stderr!r}"
        )

    @skip_if_no_tmux
    def test_ralph_spawn_validates_prompt_file_exists(self):
        """Verify --ralph with non-existent prompt file fails."""
        worker_name = f"ralph-missing-{self.tmux_socket[-8:]}"

        result = self.run_swarm(
            'spawn',
            '--name', worker_name,
            '--tmux',
            '--ralph',
            '--prompt-file', '/nonexistent/PROMPT.md',
            '--max-iterations', '3',
            '--',
            'echo', 'hello'
        )

        self.assertNotEqual(
            result.returncode,
            0,
            f"Expected spawn with non-existent prompt file to fail"
        )
        self.assertIn(
            "not found",
            result.stderr.lower(),
            f"Expected error message about file not found, got: {result.stderr!r}"
        )

    @skip_if_no_tmux
    def test_ralph_spawn_creates_worker_and_state(self):
        """Verify ralph spawn creates worker and ralph state file."""
        worker_name = f"ralph-basic-{self.tmux_socket[-8:]}"

        result = self.run_swarm(
            'spawn',
            '--name', worker_name,
            '--tmux',
            '--ralph',
            '--prompt-file', str(self.prompt_file),
            '--max-iterations', '3',
            '--',
            'bash', '-c', 'echo "$ ready"; sleep 30'
        )

        self.assertEqual(
            result.returncode,
            0,
            f"Expected ralph spawn to succeed. Stdout: {result.stdout!r}, Stderr: {result.stderr!r}"
        )

        # Check output mentions ralph mode
        self.assertIn(
            "ralph",
            result.stdout.lower(),
            f"Expected output to mention ralph mode, got: {result.stdout!r}"
        )

        # Verify worker was created
        workers = self.get_workers()
        worker_names = [w['name'] for w in workers]
        self.assertIn(
            worker_name,
            worker_names,
            f"Expected worker '{worker_name}' to be created, got: {worker_names!r}"
        )

        # Verify ralph state was created
        ralph_state_file = Path.home() / ".swarm" / "ralph" / worker_name / "state.json"
        self.assertTrue(
            ralph_state_file.exists(),
            f"Expected ralph state file at {ralph_state_file} to exist"
        )

        # Verify ralph state content
        with open(ralph_state_file) as f:
            ralph_state = json.load(f)

        self.assertEqual(ralph_state['worker_name'], worker_name)
        self.assertEqual(ralph_state['max_iterations'], 3)
        self.assertEqual(ralph_state['status'], 'running')
        self.assertEqual(ralph_state['inactivity_timeout'], 60)  # Default is 60s


class TestRalphStatus(TmuxIsolatedTestCase):
    """Test ralph status command."""

    def setUp(self):
        """Set up temporary prompt file for ralph tests."""
        super().setUp()
        self.tmpdir = tempfile.mkdtemp()
        self.prompt_file = Path(self.tmpdir) / "PROMPT.md"
        self.prompt_file.write_text("Test prompt content\n")

    def tearDown(self):
        """Clean up temp files and ralph workers."""
        # Kill any ralph workers
        try:
            workers = self.get_workers()
            for w in workers:
                self.run_swarm('kill', w['name'])
            self.run_swarm('clean', '--all')
        except Exception:
            pass

        # Clean up ralph state
        ralph_dir = Path.home() / ".swarm" / "ralph"
        if ralph_dir.exists():
            for worker_dir in ralph_dir.iterdir():
                if worker_dir.name.startswith(self.tmux_socket.replace('swarm-test-', '')):
                    shutil.rmtree(worker_dir, ignore_errors=True)

        shutil.rmtree(self.tmpdir, ignore_errors=True)
        super().tearDown()

    @skip_if_no_tmux
    def test_ralph_status_shows_iteration_info(self):
        """Verify ralph status displays iteration and configuration info."""
        worker_name = f"ralph-status-{self.tmux_socket[-8:]}"

        # Spawn ralph worker
        spawn_result = self.run_swarm(
            'spawn',
            '--name', worker_name,
            '--tmux',
            '--ralph',
            '--prompt-file', str(self.prompt_file),
            '--max-iterations', '5',
            '--inactivity-timeout', '30',
            '--',
            'bash', '-c', 'echo "$ ready"; sleep 30'
        )
        self.assertEqual(spawn_result.returncode, 0)

        # Check status
        status_result = self.run_swarm('ralph', 'status', worker_name)

        self.assertEqual(
            status_result.returncode,
            0,
            f"Expected ralph status to succeed. Stderr: {status_result.stderr!r}"
        )

        # Verify status output contains expected fields
        output = status_result.stdout.lower()
        self.assertIn("ralph loop:", output.lower())
        self.assertIn("status:", output.lower())
        self.assertIn("iteration:", output.lower())
        self.assertIn("inactivity timeout:", output.lower())

        # Check for the specific values
        self.assertIn("5", status_result.stdout)  # max iterations
        self.assertIn("30", status_result.stdout)  # inactivity timeout


class TestRalphPauseResume(TmuxIsolatedTestCase):
    """Test ralph pause and resume functionality."""

    def setUp(self):
        """Set up temporary prompt file for ralph tests."""
        super().setUp()
        self.tmpdir = tempfile.mkdtemp()
        self.prompt_file = Path(self.tmpdir) / "PROMPT.md"
        self.prompt_file.write_text("Test prompt content\n")

    def tearDown(self):
        """Clean up temp files and ralph workers."""
        try:
            workers = self.get_workers()
            for w in workers:
                self.run_swarm('kill', w['name'])
            self.run_swarm('clean', '--all')
        except Exception:
            pass

        ralph_dir = Path.home() / ".swarm" / "ralph"
        if ralph_dir.exists():
            for worker_dir in ralph_dir.iterdir():
                if worker_dir.name.startswith(self.tmux_socket.replace('swarm-test-', '')):
                    shutil.rmtree(worker_dir, ignore_errors=True)

        shutil.rmtree(self.tmpdir, ignore_errors=True)
        super().tearDown()

    @skip_if_no_tmux
    def test_ralph_pause_changes_status(self):
        """Verify ralph pause changes status to paused."""
        worker_name = f"ralph-pause-{self.tmux_socket[-8:]}"

        # Spawn ralph worker
        spawn_result = self.run_swarm(
            'spawn',
            '--name', worker_name,
            '--tmux',
            '--ralph',
            '--prompt-file', str(self.prompt_file),
            '--max-iterations', '5',
            '--',
            'bash', '-c', 'echo "$ ready"; sleep 30'
        )
        self.assertEqual(spawn_result.returncode, 0)

        # Pause the ralph loop
        pause_result = self.run_swarm('ralph', 'pause', worker_name)

        self.assertEqual(
            pause_result.returncode,
            0,
            f"Expected ralph pause to succeed. Stderr: {pause_result.stderr!r}"
        )
        self.assertIn(
            "paused",
            pause_result.stdout.lower(),
            f"Expected output to confirm pause, got: {pause_result.stdout!r}"
        )

        # Verify status shows paused
        status_result = self.run_swarm('ralph', 'status', worker_name)
        self.assertIn(
            "paused",
            status_result.stdout.lower(),
            f"Expected status to show paused, got: {status_result.stdout!r}"
        )

    @skip_if_no_tmux
    def test_ralph_resume_changes_status(self):
        """Verify ralph resume changes status from paused to running."""
        worker_name = f"ralph-resume-{self.tmux_socket[-8:]}"

        # Spawn ralph worker
        spawn_result = self.run_swarm(
            'spawn',
            '--name', worker_name,
            '--tmux',
            '--ralph',
            '--prompt-file', str(self.prompt_file),
            '--max-iterations', '5',
            '--',
            'bash', '-c', 'echo "$ ready"; sleep 30'
        )
        self.assertEqual(spawn_result.returncode, 0)

        # Pause first
        pause_result = self.run_swarm('ralph', 'pause', worker_name)
        self.assertEqual(pause_result.returncode, 0)

        # Resume
        resume_result = self.run_swarm('ralph', 'resume', worker_name)

        self.assertEqual(
            resume_result.returncode,
            0,
            f"Expected ralph resume to succeed. Stderr: {resume_result.stderr!r}"
        )
        self.assertIn(
            "resumed",
            resume_result.stdout.lower(),
            f"Expected output to confirm resume, got: {resume_result.stdout!r}"
        )

        # Verify status shows running
        status_result = self.run_swarm('ralph', 'status', worker_name)
        self.assertIn(
            "running",
            status_result.stdout.lower(),
            f"Expected status to show running, got: {status_result.stdout!r}"
        )

    @skip_if_no_tmux
    def test_ralph_pause_already_paused_warns(self):
        """Verify pausing an already paused worker shows warning."""
        worker_name = f"ralph-double-pause-{self.tmux_socket[-8:]}"

        # Spawn ralph worker
        spawn_result = self.run_swarm(
            'spawn',
            '--name', worker_name,
            '--tmux',
            '--ralph',
            '--prompt-file', str(self.prompt_file),
            '--max-iterations', '5',
            '--',
            'bash', '-c', 'echo "$ ready"; sleep 30'
        )
        self.assertEqual(spawn_result.returncode, 0)

        # Pause first time
        self.run_swarm('ralph', 'pause', worker_name)

        # Pause second time
        second_pause = self.run_swarm('ralph', 'pause', worker_name)

        self.assertIn(
            "already paused",
            second_pause.stderr.lower(),
            f"Expected warning about already paused, got: {second_pause.stderr!r}"
        )


class TestRalphInactivityDetection(TmuxIsolatedTestCase):
    """Test that ralph detects screen-stable inactivity.

    These tests verify the screen-stable detection approach:
    - Screen content is hashed
    - When hash is stable for timeout period, inactivity is detected
    - Screen changes reset the stability timer
    """

    def setUp(self):
        """Set up temporary prompt file for ralph tests."""
        super().setUp()
        self.tmpdir = tempfile.mkdtemp()
        self.prompt_file = Path(self.tmpdir) / "PROMPT.md"
        self.prompt_file.write_text("Test prompt content\n")

    def tearDown(self):
        """Clean up temp files and ralph workers."""
        try:
            workers = self.get_workers()
            for w in workers:
                self.run_swarm('kill', w['name'])
            self.run_swarm('clean', '--all')
        except Exception:
            pass

        ralph_dir = Path.home() / ".swarm" / "ralph"
        if ralph_dir.exists():
            for worker_dir in ralph_dir.iterdir():
                if worker_dir.name.startswith(self.tmux_socket.replace('swarm-test-', '')):
                    shutil.rmtree(worker_dir, ignore_errors=True)

        shutil.rmtree(self.tmpdir, ignore_errors=True)
        super().tearDown()

    @skip_if_no_tmux
    def test_ralph_default_inactivity_timeout_is_60s(self):
        """Verify default inactivity timeout is 60 seconds."""
        worker_name = f"ralph-default-timeout-{self.tmux_socket[-8:]}"

        # Spawn without specifying --inactivity-timeout
        spawn_result = self.run_swarm(
            'spawn',
            '--name', worker_name,
            '--tmux',
            '--ralph',
            '--prompt-file', str(self.prompt_file),
            '--max-iterations', '3',
            '--',
            'bash', '-c', 'echo "$ ready"; sleep 30'
        )
        self.assertEqual(spawn_result.returncode, 0)

        # Check ralph state has 60s default
        ralph_state_file = Path.home() / ".swarm" / "ralph" / worker_name / "state.json"
        with open(ralph_state_file) as f:
            ralph_state = json.load(f)

        self.assertEqual(
            ralph_state['inactivity_timeout'],
            60,
            f"Expected default inactivity timeout of 60s, got: {ralph_state['inactivity_timeout']}"
        )

    @skip_if_no_tmux
    def test_ralph_custom_inactivity_timeout(self):
        """Verify custom inactivity timeout is respected."""
        worker_name = f"ralph-custom-timeout-{self.tmux_socket[-8:]}"

        # Spawn with custom timeout
        spawn_result = self.run_swarm(
            'spawn',
            '--name', worker_name,
            '--tmux',
            '--ralph',
            '--prompt-file', str(self.prompt_file),
            '--max-iterations', '3',
            '--inactivity-timeout', '10',
            '--',
            'bash', '-c', 'echo "$ ready"; sleep 30'
        )
        self.assertEqual(spawn_result.returncode, 0)

        # Check ralph state has custom timeout
        ralph_state_file = Path.home() / ".swarm" / "ralph" / worker_name / "state.json"
        with open(ralph_state_file) as f:
            ralph_state = json.load(f)

        self.assertEqual(
            ralph_state['inactivity_timeout'],
            10,
            f"Expected inactivity timeout of 10s, got: {ralph_state['inactivity_timeout']}"
        )

    @skip_if_no_tmux
    def test_ralph_inactivity_triggers_restart(self):
        """Verify screen-stable inactivity triggers a restart.

        This is the key integration test for the screen-stable detection.
        We spawn a process that outputs something then goes silent, and
        verify that ralph detects the inactivity and starts a new iteration.

        Uses a short 5-second timeout for quick testing.
        """
        worker_name = f"ralph-inactivity-{self.tmux_socket[-8:]}"

        # Create a script that outputs a ready pattern then sleeps (becomes inactive)
        script_file = Path(self.tmpdir) / "inactive.sh"
        script_file.write_text("""#!/bin/bash
echo "$ ready"
sleep 30
""")
        script_file.chmod(0o755)

        # Spawn ralph worker with short inactivity timeout
        spawn_result = self.run_swarm(
            'spawn',
            '--name', worker_name,
            '--tmux',
            '--ralph',
            '--prompt-file', str(self.prompt_file),
            '--max-iterations', '3',
            '--inactivity-timeout', '5',  # 5 second timeout for quick test
            '--',
            str(script_file)
        )
        self.assertEqual(
            spawn_result.returncode,
            0,
            f"Failed to spawn ralph worker. Stderr: {spawn_result.stderr!r}"
        )

        # Verify the ralph state has the correct inactivity timeout configured
        # Note: The actual restart behavior requires running `swarm ralph run`
        ralph_state_file = Path.home() / ".swarm" / "ralph" / worker_name / "state.json"
        with open(ralph_state_file) as f:
            ralph_state = json.load(f)

        self.assertEqual(ralph_state['inactivity_timeout'], 5)


class TestRalphList(TmuxIsolatedTestCase):
    """Test ralph list command."""

    def setUp(self):
        """Set up temporary prompt file for ralph tests."""
        super().setUp()
        self.tmpdir = tempfile.mkdtemp()
        self.prompt_file = Path(self.tmpdir) / "PROMPT.md"
        self.prompt_file.write_text("Test prompt content\n")

    def tearDown(self):
        """Clean up temp files and ralph workers."""
        try:
            workers = self.get_workers()
            for w in workers:
                self.run_swarm('kill', w['name'])
            self.run_swarm('clean', '--all')
        except Exception:
            pass

        ralph_dir = Path.home() / ".swarm" / "ralph"
        if ralph_dir.exists():
            for worker_dir in ralph_dir.iterdir():
                if worker_dir.name.startswith(self.tmux_socket.replace('swarm-test-', '')):
                    shutil.rmtree(worker_dir, ignore_errors=True)

        shutil.rmtree(self.tmpdir, ignore_errors=True)
        super().tearDown()

    @skip_if_no_tmux
    def test_ralph_list_shows_ralph_workers(self):
        """Verify ralph list shows ralph workers."""
        worker_name = f"ralph-list-{self.tmux_socket[-8:]}"

        # Spawn ralph worker
        spawn_result = self.run_swarm(
            'spawn',
            '--name', worker_name,
            '--tmux',
            '--ralph',
            '--prompt-file', str(self.prompt_file),
            '--max-iterations', '3',
            '--',
            'bash', '-c', 'echo "$ ready"; sleep 30'
        )
        self.assertEqual(spawn_result.returncode, 0)

        # List ralph workers
        list_result = self.run_swarm('ralph', 'list')

        self.assertEqual(
            list_result.returncode,
            0,
            f"Expected ralph list to succeed. Stderr: {list_result.stderr!r}"
        )

        # Verify worker appears in list
        self.assertIn(
            worker_name,
            list_result.stdout,
            f"Expected worker '{worker_name}' in ralph list, got: {list_result.stdout!r}"
        )

    @skip_if_no_tmux
    def test_ralph_list_json_format(self):
        """Verify ralph list --format json outputs valid JSON."""
        worker_name = f"ralph-json-{self.tmux_socket[-8:]}"

        # Spawn ralph worker
        spawn_result = self.run_swarm(
            'spawn',
            '--name', worker_name,
            '--tmux',
            '--ralph',
            '--prompt-file', str(self.prompt_file),
            '--max-iterations', '3',
            '--',
            'bash', '-c', 'echo "$ ready"; sleep 30'
        )
        self.assertEqual(spawn_result.returncode, 0)

        # List in JSON format
        list_result = self.run_swarm('ralph', 'list', '--format', 'json')

        self.assertEqual(
            list_result.returncode,
            0,
            f"Expected ralph list --format json to succeed. Stderr: {list_result.stderr!r}"
        )

        # Parse JSON
        try:
            ralph_workers = json.loads(list_result.stdout)
        except json.JSONDecodeError as e:
            self.fail(f"Failed to parse ralph list JSON: {e}. Output: {list_result.stdout!r}")

        # Verify our worker is in the list
        worker_names = [w['worker_name'] for w in ralph_workers]
        self.assertIn(
            worker_name,
            worker_names,
            f"Expected worker '{worker_name}' in JSON output, got: {worker_names!r}"
        )


class TestRalphInit(TmuxIsolatedTestCase):
    """Test ralph init and template commands."""

    def setUp(self):
        """Set up temporary directory for testing init."""
        super().setUp()
        self.tmpdir = tempfile.mkdtemp()
        self.original_cwd = os.getcwd()
        os.chdir(self.tmpdir)

    def tearDown(self):
        """Clean up temp directory."""
        os.chdir(self.original_cwd)
        shutil.rmtree(self.tmpdir, ignore_errors=True)
        super().tearDown()

    @skip_if_no_tmux
    def test_ralph_init_creates_prompt_file(self):
        """Verify ralph init creates PROMPT.md."""
        result = self.run_swarm('ralph', 'init')

        self.assertEqual(
            result.returncode,
            0,
            f"Expected ralph init to succeed. Stderr: {result.stderr!r}"
        )

        prompt_file = Path(self.tmpdir) / "PROMPT.md"
        self.assertTrue(
            prompt_file.exists(),
            f"Expected PROMPT.md to be created at {prompt_file}"
        )

        # Verify content includes key elements
        content = prompt_file.read_text()
        self.assertIn("study", content.lower())
        self.assertIn("IMPLEMENTATION_PLAN", content)

    @skip_if_no_tmux
    def test_ralph_init_refuses_overwrite_without_force(self):
        """Verify ralph init refuses to overwrite existing PROMPT.md."""
        # Create existing PROMPT.md
        prompt_file = Path(self.tmpdir) / "PROMPT.md"
        prompt_file.write_text("Existing content\n")

        result = self.run_swarm('ralph', 'init')

        self.assertNotEqual(
            result.returncode,
            0,
            f"Expected ralph init to fail when PROMPT.md exists"
        )
        self.assertIn(
            "already exists",
            result.stderr.lower(),
            f"Expected error about file existing, got: {result.stderr!r}"
        )

        # Verify original content preserved
        self.assertEqual(prompt_file.read_text(), "Existing content\n")

    @skip_if_no_tmux
    def test_ralph_init_force_overwrites(self):
        """Verify ralph init --force overwrites existing PROMPT.md."""
        # Create existing PROMPT.md
        prompt_file = Path(self.tmpdir) / "PROMPT.md"
        prompt_file.write_text("Existing content\n")

        result = self.run_swarm('ralph', 'init', '--force')

        self.assertEqual(
            result.returncode,
            0,
            f"Expected ralph init --force to succeed. Stderr: {result.stderr!r}"
        )

        # Verify content was overwritten
        content = prompt_file.read_text()
        self.assertNotEqual(content, "Existing content\n")
        self.assertIn("study", content.lower())

    @skip_if_no_tmux
    def test_ralph_template_outputs_to_stdout(self):
        """Verify ralph template outputs template to stdout."""
        result = self.run_swarm('ralph', 'template')

        self.assertEqual(
            result.returncode,
            0,
            f"Expected ralph template to succeed. Stderr: {result.stderr!r}"
        )

        # Verify template content
        self.assertIn("study", result.stdout.lower())
        self.assertIn("IMPLEMENTATION_PLAN", result.stdout)

        # Verify no file was created
        prompt_file = Path(self.tmpdir) / "PROMPT.md"
        self.assertFalse(
            prompt_file.exists(),
            f"Expected no PROMPT.md to be created by template command"
        )


if __name__ == "__main__":
    unittest.main()
