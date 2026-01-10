#!/usr/bin/env python3
"""swarm - Unix-style agent process manager.

A minimal CLI tool for spawning, tracking, and controlling agent processes via tmux.
"""

import argparse
import json
import os
import shlex
import subprocess
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional


# Constants
SWARM_DIR = Path.home() / ".swarm"
STATE_FILE = SWARM_DIR / "state.json"
LOGS_DIR = SWARM_DIR / "logs"


@dataclass
class TmuxInfo:
    """Tmux window information."""
    session: str
    window: str


@dataclass
class WorktreeInfo:
    """Git worktree information."""
    path: str
    branch: str
    base_repo: str


@dataclass
class Worker:
    """A tracked worker process."""
    name: str
    status: str  # "running", "stopped"
    cmd: list[str]
    started: str  # ISO format timestamp
    cwd: str
    env: dict[str, str] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)
    tmux: Optional[TmuxInfo] = None
    worktree: Optional[WorktreeInfo] = None
    pid: Optional[int] = None

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        d = {
            "name": self.name,
            "status": self.status,
            "cmd": self.cmd,
            "started": self.started,
            "cwd": self.cwd,
            "env": self.env,
            "tags": self.tags,
            "tmux": asdict(self.tmux) if self.tmux else None,
            "worktree": asdict(self.worktree) if self.worktree else None,
            "pid": self.pid,
        }
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Worker":
        """Create Worker from dictionary."""
        tmux = TmuxInfo(**d["tmux"]) if d.get("tmux") else None
        worktree = WorktreeInfo(**d["worktree"]) if d.get("worktree") else None
        return cls(
            name=d["name"],
            status=d["status"],
            cmd=d["cmd"],
            started=d["started"],
            cwd=d["cwd"],
            env=d.get("env", {}),
            tags=d.get("tags", []),
            tmux=tmux,
            worktree=worktree,
            pid=d.get("pid"),
        )


class State:
    """Manages the swarm state file."""

    def __init__(self):
        self.workers: list[Worker] = []
        self._load()

    def _load(self) -> None:
        """Load state from disk."""
        ensure_dirs()
        if STATE_FILE.exists():
            with open(STATE_FILE, "r") as f:
                data = json.load(f)
                self.workers = [Worker.from_dict(w) for w in data.get("workers", [])]
        else:
            self.workers = []

    def save(self) -> None:
        """Save state to disk."""
        ensure_dirs()
        data = {"workers": [w.to_dict() for w in self.workers]}
        with open(STATE_FILE, "w") as f:
            json.dump(data, f, indent=2)

    def get_worker(self, name: str) -> Optional[Worker]:
        """Get a worker by name."""
        for w in self.workers:
            if w.name == name:
                return w
        return None

    def add_worker(self, worker: Worker) -> None:
        """Add a worker to state."""
        self.workers.append(worker)
        self.save()

    def remove_worker(self, name: str) -> None:
        """Remove a worker from state."""
        self.workers = [w for w in self.workers if w.name != name]
        self.save()

    def update_worker(self, name: str, **kwargs) -> None:
        """Update a worker's fields."""
        worker = self.get_worker(name)
        if worker:
            for key, value in kwargs.items():
                setattr(worker, key, value)
            self.save()


def ensure_dirs() -> None:
    """Create swarm directories if they don't exist."""
    SWARM_DIR.mkdir(parents=True, exist_ok=True)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)


# =============================================================================
# Git Operations
# =============================================================================

def get_git_root() -> Path:
    """Get root of current git repo."""
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        check=True,
    )
    return Path(result.stdout.strip())


def create_worktree(path: Path, branch: str) -> None:
    """Create a git worktree.

    Creates a new worktree at the specified path with the given branch name.
    If the branch doesn't exist, it's created from the current HEAD.
    """
    path = Path(path)
    # Create parent directory if needed
    path.parent.mkdir(parents=True, exist_ok=True)

    # Try to create with new branch first, fall back to existing branch
    result = subprocess.run(
        ["git", "worktree", "add", "-b", branch, str(path)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        # Branch might already exist, try without -b
        subprocess.run(
            ["git", "worktree", "add", str(path), branch],
            capture_output=True,
            text=True,
            check=True,
        )


def remove_worktree(path: Path) -> None:
    """Remove a git worktree."""
    subprocess.run(
        ["git", "worktree", "remove", "--force", str(path)],
        capture_output=True,
        text=True,
        check=True,
    )


# =============================================================================
# Tmux Operations
# =============================================================================

def ensure_tmux_session(session: str) -> None:
    """Create tmux session if it doesn't exist."""
    # Check if session exists
    result = subprocess.run(
        ["tmux", "has-session", "-t", shlex.quote(session)],
        capture_output=True,
    )
    if result.returncode != 0:
        # Create detached session
        subprocess.run(
            ["tmux", "new-session", "-d", "-s", session],
            capture_output=True,
            check=True,
        )


def create_tmux_window(session: str, window: str, cwd: Path, cmd: list[str]) -> None:
    """Create a tmux window and run command."""
    ensure_tmux_session(session)

    # Build the command string safely
    cmd_str = " ".join(shlex.quote(c) for c in cmd)

    subprocess.run(
        [
            "tmux", "new-window",
            "-t", session,
            "-n", window,
            "-c", str(cwd),
            cmd_str,
        ],
        capture_output=True,
        check=True,
    )


def tmux_send(session: str, window: str, text: str, enter: bool = True) -> None:
    """Send text to a tmux window."""
    target = f"{session}:{window}"

    # Use send-keys with literal text
    cmd = ["tmux", "send-keys", "-t", target, "-l", text]
    subprocess.run(cmd, capture_output=True, check=True)

    if enter:
        subprocess.run(
            ["tmux", "send-keys", "-t", target, "Enter"],
            capture_output=True,
            check=True,
        )


def tmux_window_exists(session: str, window: str) -> bool:
    """Check if a tmux window exists."""
    target = f"{session}:{window}"
    result = subprocess.run(
        ["tmux", "has-session", "-t", target],
        capture_output=True,
    )
    return result.returncode == 0


def tmux_capture_pane(session: str, window: str, history_lines: int = 0) -> str:
    """Capture contents of a tmux pane.

    Args:
        session: Tmux session name
        window: Tmux window name
        history_lines: Number of scrollback lines to include (0 = visible only)

    Returns:
        Captured pane content as string
    """
    target = f"{session}:{window}"
    cmd = ["tmux", "capture-pane", "-t", target, "-p"]

    if history_lines > 0:
        # Include scrollback history
        cmd.extend(["-S", f"-{history_lines}"])

    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return result.stdout


# =============================================================================
# Process Operations
# =============================================================================

def spawn_process(cmd: list[str], cwd: Path, env: dict, log_prefix: Path) -> int:
    """Spawn a background process, return PID.

    Args:
        cmd: Command to run as list of strings
        cwd: Working directory
        env: Environment variables to set (merged with current env)
        log_prefix: Path prefix for stdout/stderr log files

    Returns:
        PID of the spawned process
    """
    # Merge with current environment
    full_env = os.environ.copy()
    full_env.update(env)

    # Open log files
    stdout_log = open(f"{log_prefix}.stdout.log", "w")
    stderr_log = open(f"{log_prefix}.stderr.log", "w")

    process = subprocess.Popen(
        cmd,
        cwd=str(cwd),
        env=full_env,
        stdout=stdout_log,
        stderr=stderr_log,
        start_new_session=True,  # Detach from parent
    )

    return process.pid


def process_alive(pid: int) -> bool:
    """Check if a process is alive."""
    try:
        os.kill(pid, 0)  # Signal 0 doesn't kill, just checks
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        # Process exists but we can't signal it
        return True


# =============================================================================
# Status Refresh
# =============================================================================

def refresh_worker_status(worker: Worker) -> str:
    """Check actual status of a worker (tmux or pid).

    Returns:
        Updated status: "running" or "stopped"
    """
    if worker.tmux:
        # Check tmux window
        if tmux_window_exists(worker.tmux.session, worker.tmux.window):
            return "running"
        else:
            return "stopped"
    elif worker.pid:
        # Check process
        if process_alive(worker.pid):
            return "running"
        else:
            return "stopped"
    else:
        # No tmux or pid, assume stopped
        return "stopped"


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        prog="swarm",
        description="Unix-style agent process manager"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # spawn
    spawn_p = subparsers.add_parser("spawn", help="Spawn a new worker")
    spawn_p.add_argument("--name", required=True, help="Unique identifier for this worker")
    spawn_p.add_argument("--tmux", action="store_true", help="Run in a tmux window")
    spawn_p.add_argument("--session", default="swarm", help="Tmux session name (default: swarm)")
    spawn_p.add_argument("--worktree", action="store_true", help="Create a git worktree")
    spawn_p.add_argument("--branch", help="Branch name for worktree (default: same as --name)")
    spawn_p.add_argument("--worktree-dir", default="../swarm-worktrees",
                        help="Parent dir for worktrees (default: ../swarm-worktrees)")
    spawn_p.add_argument("--tag", action="append", default=[], dest="tags",
                        help="Tag for filtering (repeatable)")
    spawn_p.add_argument("--env", action="append", default=[],
                        help="Environment variable KEY=VAL (repeatable)")
    spawn_p.add_argument("--cwd", help="Working directory")
    spawn_p.add_argument("cmd", nargs=argparse.REMAINDER, metavar="-- command...",
                        help="Command to run (after --)")

    # ls
    ls_p = subparsers.add_parser("ls", help="List workers")
    ls_p.add_argument("--format", choices=["table", "json", "names"], default="table",
                     help="Output format (default: table)")
    ls_p.add_argument("--status", choices=["running", "stopped", "all"], default="all",
                     help="Filter by status (default: all)")
    ls_p.add_argument("--tag", help="Filter by tag")

    # status
    status_p = subparsers.add_parser("status", help="Get worker status")
    status_p.add_argument("name", help="Worker name")

    # send
    send_p = subparsers.add_parser("send", help="Send text to worker")
    send_p.add_argument("name", nargs="?", help="Worker name")
    send_p.add_argument("text", help="Text to send")
    send_p.add_argument("--no-enter", action="store_true", help="Don't append Enter key")
    send_p.add_argument("--all", action="store_true", help="Send to all running tmux workers")

    # interrupt
    int_p = subparsers.add_parser("interrupt", help="Send Ctrl-C to worker")
    int_p.add_argument("name", nargs="?", help="Worker name")
    int_p.add_argument("--all", action="store_true", help="Send to all workers")

    # eof
    eof_p = subparsers.add_parser("eof", help="Send Ctrl-D to worker")
    eof_p.add_argument("name", help="Worker name")

    # attach
    attach_p = subparsers.add_parser("attach", help="Attach to worker tmux window")
    attach_p.add_argument("name", help="Worker name")

    # logs
    logs_p = subparsers.add_parser("logs", help="View worker output")
    logs_p.add_argument("name", help="Worker name")
    logs_p.add_argument("--history", action="store_true",
                       help="Include scrollback buffer (default: visible pane only)")
    logs_p.add_argument("--lines", type=int, default=1000,
                       help="Number of scrollback lines (default: 1000)")
    logs_p.add_argument("--follow", action="store_true",
                       help="Continuously poll and display")

    # kill
    kill_p = subparsers.add_parser("kill", help="Kill worker")
    kill_p.add_argument("name", nargs="?", help="Worker name")
    kill_p.add_argument("--rm-worktree", action="store_true",
                       help="Also remove the git worktree")
    kill_p.add_argument("--all", action="store_true", help="Kill all workers")

    # wait
    wait_p = subparsers.add_parser("wait", help="Wait for worker to finish")
    wait_p.add_argument("name", nargs="?", help="Worker name")
    wait_p.add_argument("--timeout", type=int, help="Max wait time in seconds")
    wait_p.add_argument("--all", action="store_true", help="Wait for all workers")

    # clean
    clean_p = subparsers.add_parser("clean", help="Clean up dead workers")
    clean_p.add_argument("name", nargs="?", help="Worker name")
    clean_p.add_argument("--rm-worktree", action="store_true", default=True,
                        help="Remove git worktree (default: true)")
    clean_p.add_argument("--all", action="store_true", help="Clean all stopped workers")

    # respawn
    respawn_p = subparsers.add_parser("respawn", help="Respawn a dead worker")
    respawn_p.add_argument("name", help="Worker name")
    respawn_p.add_argument("--clean-first", action="store_true",
                          help="Run clean before respawn")

    args = parser.parse_args()

    # Dispatch to command handlers
    if args.command == "spawn":
        cmd_spawn(args)
    elif args.command == "ls":
        cmd_ls(args)
    elif args.command == "status":
        cmd_status(args)
    elif args.command == "send":
        cmd_send(args)
    elif args.command == "interrupt":
        cmd_interrupt(args)
    elif args.command == "eof":
        cmd_eof(args)
    elif args.command == "attach":
        cmd_attach(args)
    elif args.command == "logs":
        cmd_logs(args)
    elif args.command == "kill":
        cmd_kill(args)
    elif args.command == "wait":
        cmd_wait(args)
    elif args.command == "clean":
        cmd_clean(args)
    elif args.command == "respawn":
        cmd_respawn(args)


# Command stubs - to be implemented in subsequent tasks
def cmd_spawn(args) -> None:
    """Spawn a new worker."""
    print("swarm: error: spawn command not yet implemented", file=os.sys.stderr)
    os.sys.exit(1)


def cmd_ls(args) -> None:
    """List workers."""
    print("swarm: error: ls command not yet implemented", file=os.sys.stderr)
    os.sys.exit(1)


def cmd_status(args) -> None:
    """Get worker status."""
    print("swarm: error: status command not yet implemented", file=os.sys.stderr)
    os.sys.exit(1)


def cmd_send(args) -> None:
    """Send text to worker."""
    print("swarm: error: send command not yet implemented", file=os.sys.stderr)
    os.sys.exit(1)


def cmd_interrupt(args) -> None:
    """Send Ctrl-C to worker."""
    print("swarm: error: interrupt command not yet implemented", file=os.sys.stderr)
    os.sys.exit(1)


def cmd_eof(args) -> None:
    """Send Ctrl-D to worker."""
    print("swarm: error: eof command not yet implemented", file=os.sys.stderr)
    os.sys.exit(1)


def cmd_attach(args) -> None:
    """Attach to worker tmux window."""
    print("swarm: error: attach command not yet implemented", file=os.sys.stderr)
    os.sys.exit(1)


def cmd_logs(args) -> None:
    """View worker output."""
    print("swarm: error: logs command not yet implemented", file=os.sys.stderr)
    os.sys.exit(1)


def cmd_kill(args) -> None:
    """Kill worker."""
    print("swarm: error: kill command not yet implemented", file=os.sys.stderr)
    os.sys.exit(1)


def cmd_wait(args) -> None:
    """Wait for worker to finish."""
    print("swarm: error: wait command not yet implemented", file=os.sys.stderr)
    os.sys.exit(1)


def cmd_clean(args) -> None:
    """Clean up dead workers."""
    print("swarm: error: clean command not yet implemented", file=os.sys.stderr)
    os.sys.exit(1)


def cmd_respawn(args) -> None:
    """Respawn a dead worker."""
    print("swarm: error: respawn command not yet implemented", file=os.sys.stderr)
    os.sys.exit(1)


if __name__ == "__main__":
    main()
