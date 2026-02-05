#!/usr/bin/env python3
"""Unit tests for main() argument parsing.

This tests that the argument parser in main() correctly parses arguments
for all commands without actually executing the commands.
"""

import argparse
import io
import sys
import unittest
from contextlib import redirect_stderr


def create_parser():
    """Create the argument parser (mirrors main() setup).

    This recreates the parser from main() for testing purposes.
    We import swarm and extract constants, but build parser locally
    to avoid triggering side effects in main().
    """
    import swarm

    parser = argparse.ArgumentParser(
        prog="swarm",
        description=swarm.ROOT_HELP_DESCRIPTION,
        epilog=swarm.ROOT_HELP_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # spawn
    spawn_p = subparsers.add_parser(
        "spawn",
        help="Spawn a new worker",
        description=swarm.SPAWN_HELP_DESCRIPTION,
        epilog=swarm.SPAWN_HELP_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    spawn_p.add_argument("--name", required=True)
    spawn_p.add_argument("--tmux", action="store_true")
    spawn_p.add_argument("--session", default=None)
    spawn_p.add_argument("--tmux-socket", default=None)
    spawn_p.add_argument("--worktree", action="store_true")
    spawn_p.add_argument("--branch")
    spawn_p.add_argument("--worktree-dir", default=None)
    spawn_p.add_argument("--tag", action="append", default=[], dest="tags")
    spawn_p.add_argument("--env", action="append", default=[])
    spawn_p.add_argument("--cwd")
    spawn_p.add_argument("--ready-wait", action="store_true")
    spawn_p.add_argument("--ready-timeout", type=int, default=120)
    spawn_p.add_argument("--heartbeat")
    spawn_p.add_argument("--heartbeat-expire")
    spawn_p.add_argument("--heartbeat-message", default="continue")
    spawn_p.add_argument("cmd", nargs=argparse.REMAINDER, metavar="-- command...")

    # ls
    ls_p = subparsers.add_parser("ls", help="List workers")
    ls_p.add_argument("--format", choices=["table", "json", "names"], default="table")
    ls_p.add_argument("--status", choices=["running", "stopped", "all"], default="all")
    ls_p.add_argument("--tag")

    # status
    status_p = subparsers.add_parser("status", help="Get worker status")
    status_p.add_argument("name")

    # send
    send_p = subparsers.add_parser("send", help="Send text to tmux worker")
    send_p.add_argument("name", nargs="?")
    send_p.add_argument("text")
    send_p.add_argument("--no-enter", action="store_true")
    send_p.add_argument("--all", action="store_true")

    # interrupt
    int_p = subparsers.add_parser("interrupt", help="Send Ctrl-C to worker")
    int_p.add_argument("name", nargs="?")
    int_p.add_argument("--all", action="store_true")

    # eof
    eof_p = subparsers.add_parser("eof", help="Send Ctrl-D to worker")
    eof_p.add_argument("name")

    # attach
    attach_p = subparsers.add_parser("attach", help="Attach to worker tmux window")
    attach_p.add_argument("name")

    # logs
    logs_p = subparsers.add_parser("logs", help="View worker output")
    logs_p.add_argument("name")
    logs_p.add_argument("--history", action="store_true")
    logs_p.add_argument("--lines", type=int, default=1000)
    logs_p.add_argument("--follow", action="store_true")

    # kill
    kill_p = subparsers.add_parser("kill", help="Stop running workers")
    kill_p.add_argument("name", nargs="?")
    kill_p.add_argument("--rm-worktree", action="store_true")
    kill_p.add_argument("--force-dirty", action="store_true")
    kill_p.add_argument("--all", action="store_true")

    # wait
    wait_p = subparsers.add_parser("wait", help="Wait for worker to finish")
    wait_p.add_argument("name", nargs="?")
    wait_p.add_argument("--timeout", type=int)
    wait_p.add_argument("--all", action="store_true")

    # clean
    clean_p = subparsers.add_parser("clean", help="Remove stopped workers from state")
    clean_p.add_argument("name", nargs="?")
    clean_p.add_argument("--rm-worktree", action="store_true", default=True)
    clean_p.add_argument("--no-rm-worktree", action="store_false", dest="rm_worktree")
    clean_p.add_argument("--force-dirty", action="store_true")
    clean_p.add_argument("--all", action="store_true")

    # respawn
    respawn_p = subparsers.add_parser("respawn", help="Restart a stopped worker")
    respawn_p.add_argument("name")
    respawn_p.add_argument("--clean-first", action="store_true")
    respawn_p.add_argument("--force-dirty", action="store_true")

    # init
    init_p = subparsers.add_parser("init", help="Initialize swarm in project")
    init_p.add_argument("--dry-run", action="store_true")
    init_p.add_argument("--file", choices=["AGENTS.md", "CLAUDE.md"], default=None)
    init_p.add_argument("--force", action="store_true")

    # ralph
    ralph_p = subparsers.add_parser("ralph", help="Ralph loop management")
    ralph_subparsers = ralph_p.add_subparsers(dest="ralph_command", required=True)

    ralph_init_p = ralph_subparsers.add_parser("init", help="Create PROMPT.md")
    ralph_init_p.add_argument("--force", action="store_true")

    ralph_subparsers.add_parser("template", help="Output template to stdout")

    ralph_status_p = ralph_subparsers.add_parser("status", help="Show ralph loop status")
    ralph_status_p.add_argument("name")

    ralph_pause_p = ralph_subparsers.add_parser("pause", help="Pause ralph loop")
    ralph_pause_p.add_argument("name")

    ralph_resume_p = ralph_subparsers.add_parser("resume", help="Resume ralph loop")
    ralph_resume_p.add_argument("name")

    ralph_run_p = ralph_subparsers.add_parser("run", help="Run the ralph loop")
    ralph_run_p.add_argument("name")

    ralph_list_p = ralph_subparsers.add_parser("list", help="List all ralph workers")
    ralph_list_p.add_argument("--format", choices=["table", "json", "names"], default="table")
    ralph_list_p.add_argument("--status", choices=["all", "running", "paused", "stopped", "failed"], default="all")

    ralph_spawn_p = ralph_subparsers.add_parser("spawn", help="Spawn a new ralph worker")
    ralph_spawn_p.add_argument("--name", required=True)
    ralph_spawn_p.add_argument("--prompt-file", required=True)
    ralph_spawn_p.add_argument("--max-iterations", type=int, required=True)
    ralph_spawn_p.add_argument("--inactivity-timeout", type=int, default=60)
    ralph_spawn_p.add_argument("--done-pattern", type=str, default=None)
    ralph_spawn_p.add_argument("--check-done-continuous", action="store_true")
    ralph_spawn_p.add_argument("--no-run", action="store_true")
    ralph_spawn_p.add_argument("--session", default=None)
    ralph_spawn_p.add_argument("--tmux-socket", default=None)
    ralph_spawn_p.add_argument("--worktree", action="store_true")
    ralph_spawn_p.add_argument("--branch")
    ralph_spawn_p.add_argument("--worktree-dir", default=None)
    ralph_spawn_p.add_argument("--tag", action="append", default=[], dest="tags")
    ralph_spawn_p.add_argument("--env", action="append", default=[])
    ralph_spawn_p.add_argument("--cwd")
    ralph_spawn_p.add_argument("--ready-wait", action="store_true")
    ralph_spawn_p.add_argument("--ready-timeout", type=int, default=120)
    ralph_spawn_p.add_argument("--heartbeat")
    ralph_spawn_p.add_argument("--heartbeat-expire")
    ralph_spawn_p.add_argument("--heartbeat-message", default="continue")
    ralph_spawn_p.add_argument("cmd", nargs=argparse.REMAINDER, metavar="-- command...")

    # heartbeat
    heartbeat_p = subparsers.add_parser("heartbeat", help="Periodic nudges to workers")
    heartbeat_subparsers = heartbeat_p.add_subparsers(dest="heartbeat_command", required=True)

    heartbeat_start_p = heartbeat_subparsers.add_parser("start", help="Start heartbeat")
    heartbeat_start_p.add_argument("worker")
    heartbeat_start_p.add_argument("--interval", required=True)
    heartbeat_start_p.add_argument("--expire")
    heartbeat_start_p.add_argument("--message", default="continue")
    heartbeat_start_p.add_argument("--force", action="store_true")

    heartbeat_stop_p = heartbeat_subparsers.add_parser("stop", help="Stop heartbeat")
    heartbeat_stop_p.add_argument("worker")

    heartbeat_list_p = heartbeat_subparsers.add_parser("list", help="List all heartbeats")
    heartbeat_list_p.add_argument("--format", choices=["table", "json"], default="table")

    heartbeat_status_p = heartbeat_subparsers.add_parser("status", help="Show heartbeat status")
    heartbeat_status_p.add_argument("worker")
    heartbeat_status_p.add_argument("--format", choices=["text", "json"], default="text")

    heartbeat_pause_p = heartbeat_subparsers.add_parser("pause", help="Pause heartbeat")
    heartbeat_pause_p.add_argument("worker")

    heartbeat_resume_p = heartbeat_subparsers.add_parser("resume", help="Resume heartbeat")
    heartbeat_resume_p.add_argument("worker")

    # workflow
    workflow_p = subparsers.add_parser("workflow", help="Multi-stage agent pipelines")
    workflow_subparsers = workflow_p.add_subparsers(dest="workflow_command", required=True)

    workflow_validate_p = workflow_subparsers.add_parser("validate", help="Validate workflow YAML")
    workflow_validate_p.add_argument("file")

    workflow_run_p = workflow_subparsers.add_parser("run", help="Run a workflow")
    workflow_run_p.add_argument("file")
    workflow_run_p.add_argument("--at", dest="at_time", metavar="TIME")
    workflow_run_p.add_argument("--in", dest="in_delay", metavar="DURATION")
    workflow_run_p.add_argument("--name")
    workflow_run_p.add_argument("--force", action="store_true")

    workflow_status_p = workflow_subparsers.add_parser("status", help="Show workflow status")
    workflow_status_p.add_argument("name")
    workflow_status_p.add_argument("--format", choices=["text", "json"], default="text")

    workflow_list_p = workflow_subparsers.add_parser("list", help="List all workflows")
    workflow_list_p.add_argument("--format", choices=["table", "json"], default="table")

    workflow_cancel_p = workflow_subparsers.add_parser("cancel", help="Cancel a workflow")
    workflow_cancel_p.add_argument("name")
    workflow_cancel_p.add_argument("--force", action="store_true")

    workflow_resume_p = workflow_subparsers.add_parser("resume", help="Resume a workflow")
    workflow_resume_p.add_argument("name")
    workflow_resume_p.add_argument("--from", dest="from_stage", metavar="STAGE")

    workflow_resume_all_p = workflow_subparsers.add_parser("resume-all", help="Resume all workflows")
    workflow_resume_all_p.add_argument("--dry-run", action="store_true")
    workflow_resume_all_p.add_argument("--background", action="store_true")

    workflow_logs_p = workflow_subparsers.add_parser("logs", help="View workflow logs")
    workflow_logs_p.add_argument("name")
    workflow_logs_p.add_argument("--stage", metavar="STAGE")
    workflow_logs_p.add_argument("--follow", "-f", action="store_true")
    workflow_logs_p.add_argument("--lines", "-n", type=int, default=1000)

    return parser


class TestSpawnArgParsing(unittest.TestCase):
    """Test spawn command argument parsing."""

    def setUp(self):
        self.parser = create_parser()

    def test_spawn_basic(self):
        """Test basic spawn command parsing."""
        args = self.parser.parse_args(["spawn", "--name", "worker1", "--", "echo", "hello"])
        self.assertEqual(args.command, "spawn")
        self.assertEqual(args.name, "worker1")
        self.assertEqual(args.cmd, ["--", "echo", "hello"])
        self.assertFalse(args.tmux)
        self.assertFalse(args.worktree)

    def test_spawn_with_tmux(self):
        """Test spawn with tmux flag."""
        args = self.parser.parse_args(["spawn", "--name", "w1", "--tmux", "--", "claude"])
        self.assertTrue(args.tmux)
        self.assertIsNone(args.session)

    def test_spawn_with_session(self):
        """Test spawn with custom tmux session."""
        args = self.parser.parse_args(["spawn", "--name", "w1", "--session", "my-session", "--", "cmd"])
        self.assertEqual(args.session, "my-session")

    def test_spawn_with_worktree(self):
        """Test spawn with worktree options."""
        args = self.parser.parse_args([
            "spawn", "--name", "feature",
            "--worktree", "--branch", "feature-branch",
            "--worktree-dir", "/custom/path",
            "--", "claude"
        ])
        self.assertTrue(args.worktree)
        self.assertEqual(args.branch, "feature-branch")
        self.assertEqual(args.worktree_dir, "/custom/path")

    def test_spawn_with_tags(self):
        """Test spawn with multiple tags."""
        args = self.parser.parse_args([
            "spawn", "--name", "w1",
            "--tag", "frontend", "--tag", "priority",
            "--", "cmd"
        ])
        self.assertEqual(args.tags, ["frontend", "priority"])

    def test_spawn_with_env(self):
        """Test spawn with environment variables."""
        args = self.parser.parse_args([
            "spawn", "--name", "w1",
            "--env", "FOO=bar", "--env", "BAZ=qux",
            "--", "cmd"
        ])
        self.assertEqual(args.env, ["FOO=bar", "BAZ=qux"])

    def test_spawn_with_cwd(self):
        """Test spawn with custom working directory."""
        args = self.parser.parse_args(["spawn", "--name", "w1", "--cwd", "/some/path", "--", "cmd"])
        self.assertEqual(args.cwd, "/some/path")

    def test_spawn_with_ready_wait(self):
        """Test spawn with ready-wait options."""
        args = self.parser.parse_args([
            "spawn", "--name", "w1",
            "--ready-wait", "--ready-timeout", "60",
            "--", "claude"
        ])
        self.assertTrue(args.ready_wait)
        self.assertEqual(args.ready_timeout, 60)

    def test_spawn_ready_timeout_default(self):
        """Test spawn ready-timeout default value."""
        args = self.parser.parse_args(["spawn", "--name", "w1", "--", "cmd"])
        self.assertEqual(args.ready_timeout, 120)

    def test_spawn_with_heartbeat(self):
        """Test spawn with heartbeat options."""
        args = self.parser.parse_args([
            "spawn", "--name", "w1",
            "--heartbeat", "4h",
            "--heartbeat-expire", "24h",
            "--heartbeat-message", "keep going",
            "--", "cmd"
        ])
        self.assertEqual(args.heartbeat, "4h")
        self.assertEqual(args.heartbeat_expire, "24h")
        self.assertEqual(args.heartbeat_message, "keep going")

    def test_spawn_heartbeat_message_default(self):
        """Test spawn heartbeat-message default value."""
        args = self.parser.parse_args(["spawn", "--name", "w1", "--", "cmd"])
        self.assertEqual(args.heartbeat_message, "continue")

    def test_spawn_missing_name(self):
        """Test that spawn requires --name."""
        with self.assertRaises(SystemExit):
            stderr = io.StringIO()
            with redirect_stderr(stderr):
                self.parser.parse_args(["spawn", "--", "cmd"])

    def test_spawn_all_options(self):
        """Test spawn with all options combined."""
        args = self.parser.parse_args([
            "spawn", "--name", "full-worker",
            "--tmux", "--session", "test-session", "--tmux-socket", "test-socket",
            "--worktree", "--branch", "my-branch", "--worktree-dir", "/wt",
            "--tag", "t1", "--tag", "t2",
            "--env", "A=1", "--env", "B=2",
            "--cwd", "/work",
            "--ready-wait", "--ready-timeout", "30",
            "--heartbeat", "1h", "--heartbeat-expire", "12h", "--heartbeat-message", "ping",
            "--", "claude", "-p", "hi"
        ])
        self.assertEqual(args.name, "full-worker")
        self.assertTrue(args.tmux)
        self.assertEqual(args.session, "test-session")
        self.assertEqual(args.tmux_socket, "test-socket")
        self.assertTrue(args.worktree)
        self.assertEqual(args.branch, "my-branch")
        self.assertEqual(args.worktree_dir, "/wt")
        self.assertEqual(args.tags, ["t1", "t2"])
        self.assertEqual(args.env, ["A=1", "B=2"])
        self.assertEqual(args.cwd, "/work")
        self.assertTrue(args.ready_wait)
        self.assertEqual(args.ready_timeout, 30)
        self.assertEqual(args.heartbeat, "1h")
        self.assertEqual(args.heartbeat_expire, "12h")
        self.assertEqual(args.heartbeat_message, "ping")
        self.assertEqual(args.cmd, ["--", "claude", "-p", "hi"])


class TestLsArgParsing(unittest.TestCase):
    """Test ls command argument parsing."""

    def setUp(self):
        self.parser = create_parser()

    def test_ls_basic(self):
        """Test basic ls command."""
        args = self.parser.parse_args(["ls"])
        self.assertEqual(args.command, "ls")
        self.assertEqual(args.format, "table")
        self.assertEqual(args.status, "all")
        self.assertIsNone(args.tag)

    def test_ls_format_json(self):
        """Test ls with JSON format."""
        args = self.parser.parse_args(["ls", "--format", "json"])
        self.assertEqual(args.format, "json")

    def test_ls_format_names(self):
        """Test ls with names format."""
        args = self.parser.parse_args(["ls", "--format", "names"])
        self.assertEqual(args.format, "names")

    def test_ls_status_running(self):
        """Test ls filtering by running status."""
        args = self.parser.parse_args(["ls", "--status", "running"])
        self.assertEqual(args.status, "running")

    def test_ls_status_stopped(self):
        """Test ls filtering by stopped status."""
        args = self.parser.parse_args(["ls", "--status", "stopped"])
        self.assertEqual(args.status, "stopped")

    def test_ls_with_tag(self):
        """Test ls filtering by tag."""
        args = self.parser.parse_args(["ls", "--tag", "backend"])
        self.assertEqual(args.tag, "backend")

    def test_ls_invalid_format(self):
        """Test ls with invalid format."""
        with self.assertRaises(SystemExit):
            stderr = io.StringIO()
            with redirect_stderr(stderr):
                self.parser.parse_args(["ls", "--format", "invalid"])


class TestStatusArgParsing(unittest.TestCase):
    """Test status command argument parsing."""

    def setUp(self):
        self.parser = create_parser()

    def test_status_basic(self):
        """Test basic status command."""
        args = self.parser.parse_args(["status", "worker1"])
        self.assertEqual(args.command, "status")
        self.assertEqual(args.name, "worker1")

    def test_status_missing_name(self):
        """Test that status requires a name."""
        with self.assertRaises(SystemExit):
            stderr = io.StringIO()
            with redirect_stderr(stderr):
                self.parser.parse_args(["status"])


class TestSendArgParsing(unittest.TestCase):
    """Test send command argument parsing."""

    def setUp(self):
        self.parser = create_parser()

    def test_send_basic(self):
        """Test basic send command."""
        args = self.parser.parse_args(["send", "worker1", "hello"])
        self.assertEqual(args.command, "send")
        self.assertEqual(args.name, "worker1")
        self.assertEqual(args.text, "hello")
        self.assertFalse(args.no_enter)
        self.assertFalse(args.all)

    def test_send_no_enter(self):
        """Test send with --no-enter."""
        args = self.parser.parse_args(["send", "worker1", "text", "--no-enter"])
        self.assertTrue(args.no_enter)

    def test_send_all(self):
        """Test send with --all (broadcast)."""
        args = self.parser.parse_args(["send", "--all", "broadcast message"])
        self.assertTrue(args.all)
        self.assertEqual(args.text, "broadcast message")
        self.assertIsNone(args.name)


class TestInterruptArgParsing(unittest.TestCase):
    """Test interrupt command argument parsing."""

    def setUp(self):
        self.parser = create_parser()

    def test_interrupt_basic(self):
        """Test basic interrupt command."""
        args = self.parser.parse_args(["interrupt", "worker1"])
        self.assertEqual(args.command, "interrupt")
        self.assertEqual(args.name, "worker1")
        self.assertFalse(args.all)

    def test_interrupt_all(self):
        """Test interrupt with --all."""
        args = self.parser.parse_args(["interrupt", "--all"])
        self.assertTrue(args.all)
        self.assertIsNone(args.name)


class TestEofArgParsing(unittest.TestCase):
    """Test eof command argument parsing."""

    def setUp(self):
        self.parser = create_parser()

    def test_eof_basic(self):
        """Test basic eof command."""
        args = self.parser.parse_args(["eof", "worker1"])
        self.assertEqual(args.command, "eof")
        self.assertEqual(args.name, "worker1")

    def test_eof_missing_name(self):
        """Test that eof requires a name."""
        with self.assertRaises(SystemExit):
            stderr = io.StringIO()
            with redirect_stderr(stderr):
                self.parser.parse_args(["eof"])


class TestAttachArgParsing(unittest.TestCase):
    """Test attach command argument parsing."""

    def setUp(self):
        self.parser = create_parser()

    def test_attach_basic(self):
        """Test basic attach command."""
        args = self.parser.parse_args(["attach", "worker1"])
        self.assertEqual(args.command, "attach")
        self.assertEqual(args.name, "worker1")

    def test_attach_missing_name(self):
        """Test that attach requires a name."""
        with self.assertRaises(SystemExit):
            stderr = io.StringIO()
            with redirect_stderr(stderr):
                self.parser.parse_args(["attach"])


class TestLogsArgParsing(unittest.TestCase):
    """Test logs command argument parsing."""

    def setUp(self):
        self.parser = create_parser()

    def test_logs_basic(self):
        """Test basic logs command."""
        args = self.parser.parse_args(["logs", "worker1"])
        self.assertEqual(args.command, "logs")
        self.assertEqual(args.name, "worker1")
        self.assertFalse(args.history)
        self.assertEqual(args.lines, 1000)
        self.assertFalse(args.follow)

    def test_logs_with_history(self):
        """Test logs with --history."""
        args = self.parser.parse_args(["logs", "worker1", "--history"])
        self.assertTrue(args.history)

    def test_logs_with_lines(self):
        """Test logs with custom lines count."""
        args = self.parser.parse_args(["logs", "worker1", "--lines", "500"])
        self.assertEqual(args.lines, 500)

    def test_logs_with_follow(self):
        """Test logs with --follow."""
        args = self.parser.parse_args(["logs", "worker1", "--follow"])
        self.assertTrue(args.follow)


class TestKillArgParsing(unittest.TestCase):
    """Test kill command argument parsing."""

    def setUp(self):
        self.parser = create_parser()

    def test_kill_basic(self):
        """Test basic kill command."""
        args = self.parser.parse_args(["kill", "worker1"])
        self.assertEqual(args.command, "kill")
        self.assertEqual(args.name, "worker1")
        self.assertFalse(args.rm_worktree)
        self.assertFalse(args.force_dirty)
        self.assertFalse(args.all)

    def test_kill_rm_worktree(self):
        """Test kill with --rm-worktree."""
        args = self.parser.parse_args(["kill", "worker1", "--rm-worktree"])
        self.assertTrue(args.rm_worktree)

    def test_kill_force_dirty(self):
        """Test kill with --force-dirty."""
        args = self.parser.parse_args(["kill", "worker1", "--force-dirty"])
        self.assertTrue(args.force_dirty)

    def test_kill_all(self):
        """Test kill with --all."""
        args = self.parser.parse_args(["kill", "--all"])
        self.assertTrue(args.all)
        self.assertIsNone(args.name)


class TestWaitArgParsing(unittest.TestCase):
    """Test wait command argument parsing."""

    def setUp(self):
        self.parser = create_parser()

    def test_wait_basic(self):
        """Test basic wait command."""
        args = self.parser.parse_args(["wait", "worker1"])
        self.assertEqual(args.command, "wait")
        self.assertEqual(args.name, "worker1")
        self.assertIsNone(args.timeout)
        self.assertFalse(args.all)

    def test_wait_with_timeout(self):
        """Test wait with --timeout."""
        args = self.parser.parse_args(["wait", "worker1", "--timeout", "60"])
        self.assertEqual(args.timeout, 60)

    def test_wait_all(self):
        """Test wait with --all."""
        args = self.parser.parse_args(["wait", "--all"])
        self.assertTrue(args.all)
        self.assertIsNone(args.name)


class TestCleanArgParsing(unittest.TestCase):
    """Test clean command argument parsing."""

    def setUp(self):
        self.parser = create_parser()

    def test_clean_basic(self):
        """Test basic clean command."""
        args = self.parser.parse_args(["clean", "worker1"])
        self.assertEqual(args.command, "clean")
        self.assertEqual(args.name, "worker1")
        self.assertTrue(args.rm_worktree)  # Default is True
        self.assertFalse(args.force_dirty)
        self.assertFalse(args.all)

    def test_clean_no_rm_worktree(self):
        """Test clean with --no-rm-worktree."""
        args = self.parser.parse_args(["clean", "worker1", "--no-rm-worktree"])
        self.assertFalse(args.rm_worktree)

    def test_clean_force_dirty(self):
        """Test clean with --force-dirty."""
        args = self.parser.parse_args(["clean", "worker1", "--force-dirty"])
        self.assertTrue(args.force_dirty)

    def test_clean_all(self):
        """Test clean with --all."""
        args = self.parser.parse_args(["clean", "--all"])
        self.assertTrue(args.all)


class TestRespawnArgParsing(unittest.TestCase):
    """Test respawn command argument parsing."""

    def setUp(self):
        self.parser = create_parser()

    def test_respawn_basic(self):
        """Test basic respawn command."""
        args = self.parser.parse_args(["respawn", "worker1"])
        self.assertEqual(args.command, "respawn")
        self.assertEqual(args.name, "worker1")
        self.assertFalse(args.clean_first)
        self.assertFalse(args.force_dirty)

    def test_respawn_clean_first(self):
        """Test respawn with --clean-first."""
        args = self.parser.parse_args(["respawn", "worker1", "--clean-first"])
        self.assertTrue(args.clean_first)

    def test_respawn_force_dirty(self):
        """Test respawn with --force-dirty."""
        args = self.parser.parse_args(["respawn", "worker1", "--force-dirty"])
        self.assertTrue(args.force_dirty)

    def test_respawn_missing_name(self):
        """Test that respawn requires a name."""
        with self.assertRaises(SystemExit):
            stderr = io.StringIO()
            with redirect_stderr(stderr):
                self.parser.parse_args(["respawn"])


class TestInitArgParsing(unittest.TestCase):
    """Test init command argument parsing."""

    def setUp(self):
        self.parser = create_parser()

    def test_init_basic(self):
        """Test basic init command."""
        args = self.parser.parse_args(["init"])
        self.assertEqual(args.command, "init")
        self.assertFalse(args.dry_run)
        self.assertIsNone(args.file)
        self.assertFalse(args.force)

    def test_init_dry_run(self):
        """Test init with --dry-run."""
        args = self.parser.parse_args(["init", "--dry-run"])
        self.assertTrue(args.dry_run)

    def test_init_file_agents(self):
        """Test init with --file AGENTS.md."""
        args = self.parser.parse_args(["init", "--file", "AGENTS.md"])
        self.assertEqual(args.file, "AGENTS.md")

    def test_init_file_claude(self):
        """Test init with --file CLAUDE.md."""
        args = self.parser.parse_args(["init", "--file", "CLAUDE.md"])
        self.assertEqual(args.file, "CLAUDE.md")

    def test_init_force(self):
        """Test init with --force."""
        args = self.parser.parse_args(["init", "--force"])
        self.assertTrue(args.force)


class TestRalphArgParsing(unittest.TestCase):
    """Test ralph command argument parsing."""

    def setUp(self):
        self.parser = create_parser()

    def test_ralph_init_basic(self):
        """Test ralph init command."""
        args = self.parser.parse_args(["ralph", "init"])
        self.assertEqual(args.command, "ralph")
        self.assertEqual(args.ralph_command, "init")
        self.assertFalse(args.force)

    def test_ralph_init_force(self):
        """Test ralph init with --force."""
        args = self.parser.parse_args(["ralph", "init", "--force"])
        self.assertTrue(args.force)

    def test_ralph_template(self):
        """Test ralph template command."""
        args = self.parser.parse_args(["ralph", "template"])
        self.assertEqual(args.ralph_command, "template")

    def test_ralph_status(self):
        """Test ralph status command."""
        args = self.parser.parse_args(["ralph", "status", "worker1"])
        self.assertEqual(args.ralph_command, "status")
        self.assertEqual(args.name, "worker1")

    def test_ralph_pause(self):
        """Test ralph pause command."""
        args = self.parser.parse_args(["ralph", "pause", "worker1"])
        self.assertEqual(args.ralph_command, "pause")
        self.assertEqual(args.name, "worker1")

    def test_ralph_resume(self):
        """Test ralph resume command."""
        args = self.parser.parse_args(["ralph", "resume", "worker1"])
        self.assertEqual(args.ralph_command, "resume")
        self.assertEqual(args.name, "worker1")

    def test_ralph_run(self):
        """Test ralph run command."""
        args = self.parser.parse_args(["ralph", "run", "worker1"])
        self.assertEqual(args.ralph_command, "run")
        self.assertEqual(args.name, "worker1")

    def test_ralph_list_basic(self):
        """Test ralph list command."""
        args = self.parser.parse_args(["ralph", "list"])
        self.assertEqual(args.ralph_command, "list")
        self.assertEqual(args.format, "table")
        self.assertEqual(args.status, "all")

    def test_ralph_list_format_json(self):
        """Test ralph list with JSON format."""
        args = self.parser.parse_args(["ralph", "list", "--format", "json"])
        self.assertEqual(args.format, "json")

    def test_ralph_list_status_running(self):
        """Test ralph list filtering by status."""
        args = self.parser.parse_args(["ralph", "list", "--status", "running"])
        self.assertEqual(args.status, "running")

    def test_ralph_spawn_basic(self):
        """Test ralph spawn command."""
        args = self.parser.parse_args([
            "ralph", "spawn",
            "--name", "agent1",
            "--prompt-file", "PROMPT.md",
            "--max-iterations", "100",
            "--", "claude"
        ])
        self.assertEqual(args.ralph_command, "spawn")
        self.assertEqual(args.name, "agent1")
        self.assertEqual(args.prompt_file, "PROMPT.md")
        self.assertEqual(args.max_iterations, 100)
        self.assertEqual(args.inactivity_timeout, 60)  # Default
        self.assertIsNone(args.done_pattern)
        self.assertFalse(args.check_done_continuous)
        self.assertFalse(args.no_run)

    def test_ralph_spawn_all_options(self):
        """Test ralph spawn with all options."""
        args = self.parser.parse_args([
            "ralph", "spawn",
            "--name", "full-agent",
            "--prompt-file", "/path/to/PROMPT.md",
            "--max-iterations", "50",
            "--inactivity-timeout", "120",
            "--done-pattern", "/done",
            "--check-done-continuous",
            "--no-run",
            "--session", "my-session",
            "--tmux-socket", "test-sock",
            "--worktree", "--branch", "dev",
            "--worktree-dir", "/wt",
            "--tag", "backend", "--tag", "urgent",
            "--env", "DEBUG=1",
            "--cwd", "/work",
            "--ready-wait", "--ready-timeout", "90",
            "--heartbeat", "2h",
            "--heartbeat-expire", "12h",
            "--heartbeat-message", "nudge",
            "--", "claude", "--dangerously-skip-permissions"
        ])
        self.assertEqual(args.name, "full-agent")
        self.assertEqual(args.prompt_file, "/path/to/PROMPT.md")
        self.assertEqual(args.max_iterations, 50)
        self.assertEqual(args.inactivity_timeout, 120)
        self.assertEqual(args.done_pattern, "/done")
        self.assertTrue(args.check_done_continuous)
        self.assertTrue(args.no_run)
        self.assertEqual(args.session, "my-session")
        self.assertEqual(args.tmux_socket, "test-sock")
        self.assertTrue(args.worktree)
        self.assertEqual(args.branch, "dev")
        self.assertEqual(args.worktree_dir, "/wt")
        self.assertEqual(args.tags, ["backend", "urgent"])
        self.assertEqual(args.env, ["DEBUG=1"])
        self.assertEqual(args.cwd, "/work")
        self.assertTrue(args.ready_wait)
        self.assertEqual(args.ready_timeout, 90)
        self.assertEqual(args.heartbeat, "2h")
        self.assertEqual(args.heartbeat_expire, "12h")
        self.assertEqual(args.heartbeat_message, "nudge")
        self.assertEqual(args.cmd, ["--", "claude", "--dangerously-skip-permissions"])

    def test_ralph_spawn_missing_required(self):
        """Test ralph spawn missing required args."""
        with self.assertRaises(SystemExit):
            stderr = io.StringIO()
            with redirect_stderr(stderr):
                self.parser.parse_args(["ralph", "spawn", "--name", "test"])


class TestHeartbeatArgParsing(unittest.TestCase):
    """Test heartbeat command argument parsing."""

    def setUp(self):
        self.parser = create_parser()

    def test_heartbeat_start_basic(self):
        """Test heartbeat start command."""
        args = self.parser.parse_args(["heartbeat", "start", "worker1", "--interval", "4h"])
        self.assertEqual(args.command, "heartbeat")
        self.assertEqual(args.heartbeat_command, "start")
        self.assertEqual(args.worker, "worker1")
        self.assertEqual(args.interval, "4h")
        self.assertIsNone(args.expire)
        self.assertEqual(args.message, "continue")
        self.assertFalse(args.force)

    def test_heartbeat_start_all_options(self):
        """Test heartbeat start with all options."""
        args = self.parser.parse_args([
            "heartbeat", "start", "agent1",
            "--interval", "30m",
            "--expire", "8h",
            "--message", "keep going",
            "--force"
        ])
        self.assertEqual(args.worker, "agent1")
        self.assertEqual(args.interval, "30m")
        self.assertEqual(args.expire, "8h")
        self.assertEqual(args.message, "keep going")
        self.assertTrue(args.force)

    def test_heartbeat_start_missing_interval(self):
        """Test heartbeat start requires --interval."""
        with self.assertRaises(SystemExit):
            stderr = io.StringIO()
            with redirect_stderr(stderr):
                self.parser.parse_args(["heartbeat", "start", "worker1"])

    def test_heartbeat_stop(self):
        """Test heartbeat stop command."""
        args = self.parser.parse_args(["heartbeat", "stop", "worker1"])
        self.assertEqual(args.heartbeat_command, "stop")
        self.assertEqual(args.worker, "worker1")

    def test_heartbeat_list_basic(self):
        """Test heartbeat list command."""
        args = self.parser.parse_args(["heartbeat", "list"])
        self.assertEqual(args.heartbeat_command, "list")
        self.assertEqual(args.format, "table")

    def test_heartbeat_list_json(self):
        """Test heartbeat list with JSON format."""
        args = self.parser.parse_args(["heartbeat", "list", "--format", "json"])
        self.assertEqual(args.format, "json")

    def test_heartbeat_status(self):
        """Test heartbeat status command."""
        args = self.parser.parse_args(["heartbeat", "status", "worker1"])
        self.assertEqual(args.heartbeat_command, "status")
        self.assertEqual(args.worker, "worker1")
        self.assertEqual(args.format, "text")

    def test_heartbeat_status_json(self):
        """Test heartbeat status with JSON format."""
        args = self.parser.parse_args(["heartbeat", "status", "worker1", "--format", "json"])
        self.assertEqual(args.format, "json")

    def test_heartbeat_pause(self):
        """Test heartbeat pause command."""
        args = self.parser.parse_args(["heartbeat", "pause", "worker1"])
        self.assertEqual(args.heartbeat_command, "pause")
        self.assertEqual(args.worker, "worker1")

    def test_heartbeat_resume(self):
        """Test heartbeat resume command."""
        args = self.parser.parse_args(["heartbeat", "resume", "worker1"])
        self.assertEqual(args.heartbeat_command, "resume")
        self.assertEqual(args.worker, "worker1")


class TestWorkflowArgParsing(unittest.TestCase):
    """Test workflow command argument parsing."""

    def setUp(self):
        self.parser = create_parser()

    def test_workflow_validate(self):
        """Test workflow validate command."""
        args = self.parser.parse_args(["workflow", "validate", "workflow.yaml"])
        self.assertEqual(args.command, "workflow")
        self.assertEqual(args.workflow_command, "validate")
        self.assertEqual(args.file, "workflow.yaml")

    def test_workflow_run_basic(self):
        """Test workflow run command."""
        args = self.parser.parse_args(["workflow", "run", "workflow.yaml"])
        self.assertEqual(args.workflow_command, "run")
        self.assertEqual(args.file, "workflow.yaml")
        self.assertIsNone(args.at_time)
        self.assertIsNone(args.in_delay)
        self.assertIsNone(args.name)
        self.assertFalse(args.force)

    def test_workflow_run_scheduled_at(self):
        """Test workflow run with --at scheduling."""
        args = self.parser.parse_args(["workflow", "run", "workflow.yaml", "--at", "02:00"])
        self.assertEqual(args.at_time, "02:00")

    def test_workflow_run_scheduled_in(self):
        """Test workflow run with --in scheduling."""
        args = self.parser.parse_args(["workflow", "run", "workflow.yaml", "--in", "4h"])
        self.assertEqual(args.in_delay, "4h")

    def test_workflow_run_name_override(self):
        """Test workflow run with --name override."""
        args = self.parser.parse_args(["workflow", "run", "workflow.yaml", "--name", "custom-name"])
        self.assertEqual(args.name, "custom-name")

    def test_workflow_run_force(self):
        """Test workflow run with --force."""
        args = self.parser.parse_args(["workflow", "run", "workflow.yaml", "--force"])
        self.assertTrue(args.force)

    def test_workflow_status_basic(self):
        """Test workflow status command."""
        args = self.parser.parse_args(["workflow", "status", "my-workflow"])
        self.assertEqual(args.workflow_command, "status")
        self.assertEqual(args.name, "my-workflow")
        self.assertEqual(args.format, "text")

    def test_workflow_status_json(self):
        """Test workflow status with JSON format."""
        args = self.parser.parse_args(["workflow", "status", "my-workflow", "--format", "json"])
        self.assertEqual(args.format, "json")

    def test_workflow_list_basic(self):
        """Test workflow list command."""
        args = self.parser.parse_args(["workflow", "list"])
        self.assertEqual(args.workflow_command, "list")
        self.assertEqual(args.format, "table")

    def test_workflow_list_json(self):
        """Test workflow list with JSON format."""
        args = self.parser.parse_args(["workflow", "list", "--format", "json"])
        self.assertEqual(args.format, "json")

    def test_workflow_cancel_basic(self):
        """Test workflow cancel command."""
        args = self.parser.parse_args(["workflow", "cancel", "my-workflow"])
        self.assertEqual(args.workflow_command, "cancel")
        self.assertEqual(args.name, "my-workflow")
        self.assertFalse(args.force)

    def test_workflow_cancel_force(self):
        """Test workflow cancel with --force."""
        args = self.parser.parse_args(["workflow", "cancel", "my-workflow", "--force"])
        self.assertTrue(args.force)

    def test_workflow_resume_basic(self):
        """Test workflow resume command."""
        args = self.parser.parse_args(["workflow", "resume", "my-workflow"])
        self.assertEqual(args.workflow_command, "resume")
        self.assertEqual(args.name, "my-workflow")
        self.assertIsNone(args.from_stage)

    def test_workflow_resume_from_stage(self):
        """Test workflow resume with --from stage."""
        args = self.parser.parse_args(["workflow", "resume", "my-workflow", "--from", "build"])
        self.assertEqual(args.from_stage, "build")

    def test_workflow_resume_all_basic(self):
        """Test workflow resume-all command."""
        args = self.parser.parse_args(["workflow", "resume-all"])
        self.assertEqual(args.workflow_command, "resume-all")
        self.assertFalse(args.dry_run)
        self.assertFalse(args.background)

    def test_workflow_resume_all_dry_run(self):
        """Test workflow resume-all with --dry-run."""
        args = self.parser.parse_args(["workflow", "resume-all", "--dry-run"])
        self.assertTrue(args.dry_run)

    def test_workflow_resume_all_background(self):
        """Test workflow resume-all with --background."""
        args = self.parser.parse_args(["workflow", "resume-all", "--background"])
        self.assertTrue(args.background)

    def test_workflow_logs_basic(self):
        """Test workflow logs command."""
        args = self.parser.parse_args(["workflow", "logs", "my-workflow"])
        self.assertEqual(args.workflow_command, "logs")
        self.assertEqual(args.name, "my-workflow")
        self.assertIsNone(args.stage)
        self.assertFalse(args.follow)
        self.assertEqual(args.lines, 1000)

    def test_workflow_logs_stage(self):
        """Test workflow logs with --stage."""
        args = self.parser.parse_args(["workflow", "logs", "my-workflow", "--stage", "build"])
        self.assertEqual(args.stage, "build")

    def test_workflow_logs_follow(self):
        """Test workflow logs with --follow."""
        args = self.parser.parse_args(["workflow", "logs", "my-workflow", "-f"])
        self.assertTrue(args.follow)

    def test_workflow_logs_lines(self):
        """Test workflow logs with --lines."""
        args = self.parser.parse_args(["workflow", "logs", "my-workflow", "-n", "500"])
        self.assertEqual(args.lines, 500)


class TestHelpTextGeneration(unittest.TestCase):
    """Test that help text is generated correctly."""

    def setUp(self):
        self.parser = create_parser()

    def test_root_help_contains_description(self):
        """Test root command has description in help."""
        help_text = self.parser.format_help()
        # Should contain some text about swarm
        self.assertIn("swarm", help_text.lower())

    def test_spawn_help_contains_options(self):
        """Test spawn subparser help contains all options."""
        spawn_parser = None
        for action in self.parser._subparsers._group_actions:
            if hasattr(action, '_parser_class'):
                for name, parser in action.choices.items():
                    if name == "spawn":
                        spawn_parser = parser
                        break

        self.assertIsNotNone(spawn_parser)
        help_text = spawn_parser.format_help()

        # Verify key options are documented
        self.assertIn("--name", help_text)
        self.assertIn("--tmux", help_text)
        self.assertIn("--worktree", help_text)
        self.assertIn("--heartbeat", help_text)

    def test_all_commands_have_help(self):
        """Test all commands have help text."""
        root_help = self.parser.format_help()

        # All main commands should be listed
        commands = ["spawn", "ls", "status", "send", "interrupt", "eof", "attach",
                   "logs", "kill", "wait", "clean", "respawn", "init", "ralph",
                   "heartbeat", "workflow"]

        for cmd in commands:
            self.assertIn(cmd, root_help, f"Command '{cmd}' not in root help")


class TestErrorMessages(unittest.TestCase):
    """Test error messages for invalid arguments."""

    def setUp(self):
        self.parser = create_parser()

    def test_no_command_shows_error(self):
        """Test that no command provided shows error."""
        with self.assertRaises(SystemExit) as cm:
            stderr = io.StringIO()
            with redirect_stderr(stderr):
                self.parser.parse_args([])
        self.assertEqual(cm.exception.code, 2)

    def test_invalid_command_shows_error(self):
        """Test that invalid command shows error."""
        with self.assertRaises(SystemExit) as cm:
            stderr = io.StringIO()
            with redirect_stderr(stderr):
                self.parser.parse_args(["invalid-command"])
        self.assertEqual(cm.exception.code, 2)

    def test_invalid_type_shows_error(self):
        """Test that invalid type for numeric argument shows error."""
        with self.assertRaises(SystemExit) as cm:
            stderr = io.StringIO()
            with redirect_stderr(stderr):
                self.parser.parse_args(["spawn", "--name", "w1", "--ready-timeout", "not-a-number", "--", "cmd"])
        self.assertEqual(cm.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
