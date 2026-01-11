#!/usr/bin/env python3
"""swarm - Unix-style agent process manager.

A minimal CLI tool for spawning, tracking, and controlling agent processes via tmux.
"""

import argparse
import fcntl
import hashlib
import json
import os
import shlex
import signal
import subprocess
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional


# Constants
SWARM_DIR = Path.home() / ".swarm"
STATE_FILE = SWARM_DIR / "state.json"
STATE_LOCK_FILE = SWARM_DIR / "state.lock"
LOGS_DIR = SWARM_DIR / "logs"


@dataclass
class TmuxInfo:
    """Tmux window information."""
    session: str
    window: str
    socket: Optional[str] = None


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


@contextmanager
def state_file_lock():
    """Context manager for exclusive locking of state file.

    This prevents race conditions when multiple swarm processes
    attempt to read/modify/write the state file concurrently.

    Uses fcntl.flock() for exclusive (LOCK_EX) file locking.
    The lock is automatically released when the context exits,
    even if an exception occurs.

    Yields:
        File object for the lock file (callers don't need to use this)
    """
    ensure_dirs()
    lock_file = open(STATE_LOCK_FILE, 'w')
    try:
        # Acquire exclusive lock (blocks if another process holds it)
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        yield lock_file
    finally:
        # Release lock and close file
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
        lock_file.close()


class State:
    """Manages the swarm state file."""

    def __init__(self):
        self.workers: list[Worker] = []
        self._load()

    def _load(self) -> None:
        """Load state from disk with exclusive locking.

        Acquires an exclusive lock before reading to prevent race conditions
        where another process might be writing to the file simultaneously.
        """
        with state_file_lock():
            ensure_dirs()
            if STATE_FILE.exists():
                with open(STATE_FILE, "r") as f:
                    data = json.load(f)
                    self.workers = [Worker.from_dict(w) for w in data.get("workers", [])]
            else:
                self.workers = []

    def save(self) -> None:
        """Save state to disk with exclusive locking.

        Acquires an exclusive lock before writing to prevent race conditions
        where multiple processes might try to update the state file concurrently.
        This ensures that:
        1. We read the most current state
        2. Our writes aren't overwritten by concurrent operations
        3. No partial/corrupted data is written

        IMPORTANT: This method does NOT reload state before saving. The caller
        must ensure they have current state. For atomic updates, use the pattern:
        1. Create State() - loads current state
        2. Modify state
        3. Call save() - writes with lock
        """
        with state_file_lock():
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
        """Add a worker to state atomically.

        This method reloads state, adds the worker, and saves - all within
        a single lock to prevent race conditions with concurrent operations.
        """
        with state_file_lock():
            # Reload to get latest state
            self._load_unlocked()
            # Add worker
            self.workers.append(worker)
            # Save immediately while holding lock
            self._save_unlocked()

    def remove_worker(self, name: str) -> None:
        """Remove a worker from state atomically.

        This method reloads state, removes the worker, and saves - all within
        a single lock to prevent race conditions with concurrent operations.
        """
        with state_file_lock():
            # Reload to get latest state
            self._load_unlocked()
            # Remove worker
            self.workers = [w for w in self.workers if w.name != name]
            # Save immediately while holding lock
            self._save_unlocked()

    def update_worker(self, name: str, **kwargs) -> None:
        """Update a worker's fields atomically.

        This method reloads state, updates the worker, and saves - all within
        a single lock to prevent race conditions with concurrent operations.
        """
        with state_file_lock():
            # Reload to get latest state
            self._load_unlocked()
            # Update worker
            worker = self.get_worker(name)
            if worker:
                for key, value in kwargs.items():
                    setattr(worker, key, value)
            # Save immediately while holding lock
            self._save_unlocked()

    def _load_unlocked(self) -> None:
        """Load state from disk WITHOUT acquiring lock.

        This is used internally when the lock is already held.
        External callers should use _load() or State() constructor.
        """
        ensure_dirs()
        if STATE_FILE.exists():
            with open(STATE_FILE, "r") as f:
                data = json.load(f)
                self.workers = [Worker.from_dict(w) for w in data.get("workers", [])]
        else:
            self.workers = []

    def _save_unlocked(self) -> None:
        """Save state to disk WITHOUT acquiring lock.

        This is used internally when the lock is already held.
        External callers should use save().
        """
        ensure_dirs()
        data = {"workers": [w.to_dict() for w in self.workers]}
        with open(STATE_FILE, "w") as f:
            json.dump(data, f, indent=2)


def ensure_dirs() -> None:
    """Create swarm directories if they don't exist."""
    SWARM_DIR.mkdir(parents=True, exist_ok=True)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)


def get_default_session_name() -> str:
    """Generate default session name with hash suffix for isolation."""
    h = hashlib.sha256(str(SWARM_DIR.resolve()).encode()).hexdigest()[:8]
    return f"swarm-{h}"


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


def worktree_is_dirty(path: Path) -> bool:
    """Check if a worktree has uncommitted changes.

    Args:
        path: Path to the worktree

    Returns:
        True if the worktree has uncommitted changes (staged, unstaged, or untracked)
    """
    if not path.exists():
        return False

    # Check for any changes: staged, unstaged, or untracked files
    # Using --porcelain for machine-readable output
    result = subprocess.run(
        ["git", "-C", str(path), "status", "--porcelain"],
        capture_output=True,
        text=True,
    )

    # If command failed, assume dirty to be safe
    if result.returncode != 0:
        return True

    # Any output means there are changes
    return bool(result.stdout.strip())


def remove_worktree(path: Path, force: bool = False) -> tuple[bool, str]:
    """Remove a git worktree.

    Args:
        path: Path to the worktree
        force: If True, remove even if worktree has uncommitted changes

    Returns:
        Tuple of (success: bool, message: str)
        - On success: (True, "")
        - On failure due to dirty worktree: (False, description of uncommitted changes)
        - On failure due to other error: raises exception
    """
    path = Path(path)

    if not path.exists():
        return (True, "")

    # Check for uncommitted changes unless force is specified
    if not force and worktree_is_dirty(path):
        # Get summary of what's dirty
        result = subprocess.run(
            ["git", "-C", str(path), "status", "--porcelain"],
            capture_output=True,
            text=True,
        )
        changes = result.stdout.strip().split('\n')
        num_changes = len(changes)
        return (False, f"worktree has {num_changes} uncommitted change(s)")

    subprocess.run(
        ["git", "worktree", "remove", "--force", str(path)],
        capture_output=True,
        text=True,
        check=True,
    )
    return (True, "")


# =============================================================================
# Tmux Operations
# =============================================================================

def tmux_cmd_prefix(socket: Optional[str] = None) -> list[str]:
    """Build tmux command prefix with optional socket.

    Args:
        socket: Optional tmux socket name for isolated tmux servers

    Returns:
        List starting with ["tmux"] or ["tmux", "-L", socket]
    """
    if socket:
        return ["tmux", "-L", socket]
    return ["tmux"]


def ensure_tmux_session(session: str, socket: Optional[str] = None) -> None:
    """Create tmux session if it doesn't exist."""
    # Check if session exists
    cmd_prefix = tmux_cmd_prefix(socket)
    result = subprocess.run(
        cmd_prefix + ["has-session", "-t", shlex.quote(session)],
        capture_output=True,
    )
    if result.returncode != 0:
        # Create detached session
        subprocess.run(
            cmd_prefix + ["new-session", "-d", "-s", session],
            capture_output=True,
            check=True,
        )


def create_tmux_window(session: str, window: str, cwd: Path, cmd: list[str], socket: Optional[str] = None) -> None:
    """Create a tmux window and run command."""
    ensure_tmux_session(session, socket)

    # Build the command string safely
    cmd_str = " ".join(shlex.quote(c) for c in cmd)

    cmd_prefix = tmux_cmd_prefix(socket)
    subprocess.run(
        cmd_prefix + [
            "new-window",
            "-a",  # Append after current window (avoids index conflicts with base-index)
            "-t", session,
            "-n", window,
            "-c", str(cwd),
            cmd_str,
        ],
        capture_output=True,
        check=True,
    )


def tmux_send(session: str, window: str, text: str, enter: bool = True, socket: Optional[str] = None) -> None:
    """Send text to a tmux window."""
    target = f"{session}:{window}"

    # Use send-keys with literal text
    cmd_prefix = tmux_cmd_prefix(socket)
    cmd = cmd_prefix + ["send-keys", "-t", target, "-l", text]
    subprocess.run(cmd, capture_output=True, check=True)

    if enter:
        subprocess.run(
            cmd_prefix + ["send-keys", "-t", target, "Enter"],
            capture_output=True,
            check=True,
        )


def tmux_window_exists(session: str, window: str, socket: Optional[str] = None) -> bool:
    """Check if a tmux window exists."""
    target = f"{session}:{window}"
    cmd_prefix = tmux_cmd_prefix(socket)
    result = subprocess.run(
        cmd_prefix + ["has-session", "-t", target],
        capture_output=True,
    )
    return result.returncode == 0


def tmux_capture_pane(session: str, window: str, history_lines: int = 0, socket: Optional[str] = None) -> str:
    """Capture contents of a tmux pane.

    Args:
        session: Tmux session name
        window: Tmux window name
        history_lines: Number of scrollback lines to include (0 = visible only)
        socket: Optional tmux socket name

    Returns:
        Captured pane content as string
    """
    target = f"{session}:{window}"
    cmd_prefix = tmux_cmd_prefix(socket)
    cmd = cmd_prefix + ["capture-pane", "-t", target, "-p"]

    if history_lines > 0:
        # Include scrollback history
        cmd.extend(["-S", f"-{history_lines}"])

    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return result.stdout


def wait_for_agent_ready(session: str, window: str, timeout: int = 30, socket: Optional[str] = None) -> bool:
    """Wait for an agent CLI to be ready for input.

    Detects readiness by looking for common prompt patterns:
    - Claude Code: "> " prompt at start of line, or "bypass permissions" indicator
    - Generic: Shell prompt patterns like "$ " or "> "

    Args:
        session: Tmux session name
        window: Tmux window name
        timeout: Maximum seconds to wait
        socket: Optional tmux socket name

    Returns:
        True if agent became ready, False if timeout
    """
    import re

    # Patterns that indicate the agent is ready for input
    # Designed to be resilient to Claude Code version changes:
    # - Match permission mode indicators (most reliable)
    # - Match version banners (catches startup completion)
    # - Match common prompt patterns
    ready_patterns = [
        # Claude Code permission mode indicators (most reliable, version-independent)
        r"bypass\s+permissions",          # "bypass permissions on" or similar
        r"permissions?\s+mode",           # "permission mode" variants
        r"shift\+tab\s+to\s+cycle",       # UI hint in permission line
        # Claude Code version banner (catches startup completion)
        r"Claude\s+Code\s+v\d+",          # "Claude Code v2.1.4" etc
        # Claude Code prompt patterns (ANSI-aware)
        r"(?:^|\x1b\[[0-9;]*m)>\s",       # "> " prompt with optional ANSI
        r"❯\s",                            # Unicode prompt character
        # Generic CLI prompts (ANSI-aware)
        r"(?:^|\x1b\[[0-9;]*m)\$\s",      # Shell "$ " prompt
        r"(?:^|\x1b\[[0-9;]*m)>>>\s",     # Python REPL ">>> "
    ]

    start = time.time()
    while (time.time() - start) < timeout:
        try:
            output = tmux_capture_pane(session, window, socket=socket)
            # Check each line for ready patterns
            for line in output.split('\n'):
                for pattern in ready_patterns:
                    if re.search(pattern, line):
                        return True
        except subprocess.CalledProcessError:
            # Window might not exist yet, keep waiting
            pass

        time.sleep(0.5)

    return False


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
        socket = worker.tmux.socket if worker.tmux else None
        if tmux_window_exists(worker.tmux.session, worker.tmux.window, socket):
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


def relative_time(iso_str: str) -> str:
    """Convert ISO timestamp to human-readable relative time.

    Args:
        iso_str: ISO format timestamp string

    Returns:
        Human-readable time delta (e.g., "5m", "2h", "3d")
    """
    dt = datetime.fromisoformat(iso_str)
    delta = datetime.now() - dt
    seconds = int(delta.total_seconds())

    if seconds < 60:
        return f"{seconds}s"
    elif seconds < 3600:
        return f"{seconds // 60}m"
    elif seconds < 86400:
        return f"{seconds // 3600}h"
    else:
        return f"{seconds // 86400}d"


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
    spawn_p.add_argument("--session", default=None, help="Tmux session name (default: hash-based isolation)")
    spawn_p.add_argument("--tmux-socket", default=None, help="Tmux socket name (for testing/isolation)")
    spawn_p.add_argument("--worktree", action="store_true", help="Create a git worktree")
    spawn_p.add_argument("--branch", help="Branch name for worktree (default: same as --name)")
    spawn_p.add_argument("--worktree-dir", default="../swarm-worktrees",
                        help="Parent dir for worktrees (default: ../swarm-worktrees)")
    spawn_p.add_argument("--tag", action="append", default=[], dest="tags",
                        help="Tag for filtering (repeatable)")
    spawn_p.add_argument("--env", action="append", default=[],
                        help="Environment variable KEY=VAL (repeatable)")
    spawn_p.add_argument("--cwd", help="Working directory")
    spawn_p.add_argument("--ready-wait", action="store_true",
                        help="Wait for agent to be ready before returning (tmux only)")
    spawn_p.add_argument("--ready-timeout", type=int, default=120,
                        help="Timeout in seconds for --ready-wait (default: 120, suitable for Claude Code startup)")
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
    kill_p.add_argument("--force-dirty", action="store_true",
                       help="Force removal of worktree even with uncommitted changes")
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
    clean_p.add_argument("--force-dirty", action="store_true",
                        help="Force removal of worktree even with uncommitted changes")
    clean_p.add_argument("--all", action="store_true", help="Clean all stopped workers")

    # respawn
    respawn_p = subparsers.add_parser("respawn", help="Respawn a dead worker")
    respawn_p.add_argument("name", help="Worker name")
    respawn_p.add_argument("--clean-first", action="store_true",
                          help="Run clean before respawn")
    respawn_p.add_argument("--force-dirty", action="store_true",
                          help="Force removal of worktree even with uncommitted changes")

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
    # Parse command from args.cmd (strip leading '--' if present)
    cmd = args.cmd
    if cmd and cmd[0] == "--":
        cmd = cmd[1:]

    # Validate command is not empty
    if not cmd:
        print("swarm: error: no command provided (use -- command...)", file=sys.stderr)
        sys.exit(1)

    # Load state and check for duplicate name
    state = State()
    if state.get_worker(args.name) is not None:
        print(f"swarm: error: worker '{args.name}' already exists", file=sys.stderr)
        sys.exit(1)

    # Determine working directory
    cwd = Path.cwd()
    worktree_info = None

    if args.worktree:
        # Get git root
        try:
            git_root = get_git_root()
        except subprocess.CalledProcessError:
            print("swarm: error: not in a git repository (required for --worktree)", file=sys.stderr)
            sys.exit(1)

        # Compute worktree path relative to git root
        worktree_dir = Path(args.worktree_dir)
        if not worktree_dir.is_absolute():
            worktree_dir = git_root.parent / worktree_dir

        worktree_path = worktree_dir / args.name

        # Determine branch name
        branch = args.branch if args.branch else args.name

        # Create worktree
        try:
            create_worktree(worktree_path, branch)
        except subprocess.CalledProcessError as e:
            print(f"swarm: error: failed to create worktree: {e}", file=sys.stderr)
            sys.exit(1)

        # Set cwd to worktree
        cwd = worktree_path

        # Store worktree info
        worktree_info = WorktreeInfo(
            path=str(worktree_path),
            branch=branch,
            base_repo=str(git_root)
        )
    elif args.cwd:
        cwd = Path(args.cwd)

    # Parse environment variables from KEY=VAL format
    env_dict = {}
    for env_str in args.env:
        if "=" not in env_str:
            print(f"swarm: error: invalid env format '{env_str}' (expected KEY=VAL)", file=sys.stderr)
            sys.exit(1)
        key, val = env_str.split("=", 1)
        env_dict[key] = val

    # Spawn the worker
    tmux_info = None
    pid = None

    if args.tmux:
        # Spawn in tmux
        # Determine session name (use hash-based default if not specified)
        session = args.session if args.session else get_default_session_name()
        socket = args.tmux_socket
        try:
            create_tmux_window(session, args.name, cwd, cmd, socket)
            tmux_info = TmuxInfo(session=session, window=args.name, socket=socket)
        except subprocess.CalledProcessError as e:
            print(f"swarm: error: failed to create tmux window: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        # Spawn as background process
        log_prefix = LOGS_DIR / args.name
        try:
            pid = spawn_process(cmd, cwd, env_dict, log_prefix)
        except Exception as e:
            print(f"swarm: error: failed to spawn process: {e}", file=sys.stderr)
            sys.exit(1)

    # Create Worker object
    worker = Worker(
        name=args.name,
        status="running",
        cmd=cmd,
        started=datetime.now().isoformat(),
        cwd=str(cwd),
        env=env_dict,
        tags=args.tags,
        tmux=tmux_info,
        worktree=worktree_info,
        pid=pid,
    )

    # Add to state
    state.add_worker(worker)

    # Wait for agent to be ready if requested
    if args.ready_wait and tmux_info:
        socket = tmux_info.socket if tmux_info else None
        if not wait_for_agent_ready(tmux_info.session, tmux_info.window, args.ready_timeout, socket):
            print(f"swarm: warning: agent '{args.name}' did not become ready within {args.ready_timeout}s", file=sys.stderr)

    # Print success message
    if tmux_info:
        print(f"spawned {args.name} (tmux: {tmux_info.session}:{tmux_info.window})")
    else:
        print(f"spawned {args.name} (pid: {pid})")


def cmd_ls(args) -> None:
    """List workers."""
    # Load state
    state = State()

    # Refresh status for each worker
    workers = []
    for worker in state.workers:
        worker.status = refresh_worker_status(worker)
        workers.append(worker)

    # Filter by status if not "all"
    if args.status != "all":
        workers = [w for w in workers if w.status == args.status]

    # Filter by tag if specified
    if args.tag:
        workers = [w for w in workers if args.tag in w.tags]

    # Output based on format
    if args.format == "json":
        # JSON format
        print(json.dumps([w.to_dict() for w in workers], indent=2))

    elif args.format == "names":
        # Names format - one per line
        for worker in workers:
            print(worker.name)

    else:  # table format
        # Table format with aligned columns
        if not workers:
            # No workers to display
            return

        # Prepare rows
        rows = []
        for worker in workers:
            # PID/WINDOW column
            if worker.tmux:
                pid_window = f"{worker.tmux.session}:{worker.tmux.window}"
            elif worker.pid:
                pid_window = str(worker.pid)
            else:
                pid_window = "-"

            # STARTED column
            started = relative_time(worker.started)

            # WORKTREE column
            worktree = worker.worktree.path if worker.worktree else "-"

            # TAG column
            tag = ",".join(worker.tags) if worker.tags else "-"

            rows.append({
                "NAME": worker.name,
                "STATUS": worker.status,
                "PID/WINDOW": pid_window,
                "STARTED": started,
                "WORKTREE": worktree,
                "TAG": tag,
            })

        # Calculate column widths
        headers = ["NAME", "STATUS", "PID/WINDOW", "STARTED", "WORKTREE", "TAG"]
        col_widths = {}
        for header in headers:
            col_widths[header] = len(header)
            for row in rows:
                col_widths[header] = max(col_widths[header], len(row[header]))

        # Print header
        header_parts = []
        for header in headers:
            header_parts.append(header.ljust(col_widths[header]))
        print("  ".join(header_parts))

        # Print rows
        for row in rows:
            row_parts = []
            for header in headers:
                row_parts.append(row[header].ljust(col_widths[header]))
            print("  ".join(row_parts))


def cmd_status(args) -> None:
    """Get worker status."""
    # Load state
    state = State()

    # Get worker by name
    worker = state.get_worker(args.name)
    if not worker:
        print(f"swarm: error: worker '{args.name}' not found", file=sys.stderr)
        sys.exit(2)

    # Refresh actual status
    actual_status = refresh_worker_status(worker)

    # Build status string
    status_str = f"{worker.name}: {actual_status} ("

    # Add tmux or pid info
    if worker.tmux:
        status_str += f"tmux window {worker.tmux.session}:{worker.tmux.window}"
    elif worker.pid:
        status_str += f"pid {worker.pid}"

    # Add worktree info if present
    if worker.worktree:
        status_str += f", worktree {worker.worktree.path}"

    # Add uptime
    uptime = relative_time(worker.started)
    status_str += f", uptime {uptime})"

    # Print status line
    print(status_str)

    # Exit with appropriate code
    if actual_status == "running":
        sys.exit(0)
    else:
        sys.exit(1)


def cmd_send(args) -> None:
    """Send text to worker."""
    # Load state
    state = State()

    # Handle --all: get all running tmux workers
    if args.all:
        workers = [
            w for w in state.workers
            if w.tmux is not None
        ]
    else:
        # Get single worker by name
        if not args.name:
            print("swarm: error: --name required when not using --all", file=sys.stderr)
            sys.exit(1)

        worker = state.get_worker(args.name)

        # Validation: worker not found
        if worker is None:
            print(f"swarm: error: worker '{args.name}' not found", file=sys.stderr)
            sys.exit(1)

        # Validation: worker is not tmux
        if worker.tmux is None:
            print(f"swarm: error: worker '{args.name}' is not a tmux worker", file=sys.stderr)
            sys.exit(1)

        workers = [worker]

    # For each worker, validate and send
    for worker in workers:
        # Refresh status and check if running
        current_status = refresh_worker_status(worker)

        # Validation: worker is not running
        if current_status != "running":
            if args.all:
                # For --all, skip non-running workers silently
                continue
            else:
                # For single worker, error and exit
                print(f"swarm: error: worker '{worker.name}' is not running", file=sys.stderr)
                sys.exit(1)

        # Send text to tmux window
        socket = worker.tmux.socket if worker.tmux else None
        tmux_send(worker.tmux.session, worker.tmux.window, args.text, enter=not args.no_enter, socket=socket)

        # Print confirmation
        print(f"sent to {worker.name}")


def cmd_interrupt(args) -> None:
    """Send Ctrl-C to worker."""
    # Load state
    state = State()

    # Handle --all flag or single worker
    if args.all:
        # Get all running tmux workers
        workers_to_interrupt = []
        for worker in state.workers:
            # Refresh status
            actual_status = refresh_worker_status(worker)
            if actual_status == "running" and worker.tmux:
                workers_to_interrupt.append(worker)
    else:
        # Get single worker by name
        if not args.name:
            print("swarm: error: worker name required when not using --all", file=sys.stderr)
            sys.exit(1)

        worker = state.get_worker(args.name)
        if not worker:
            print(f"swarm: error: worker '{args.name}' not found", file=sys.stderr)
            sys.exit(1)

        # Validate worker is tmux
        if not worker.tmux:
            print(f"swarm: error: worker '{args.name}' is not a tmux worker", file=sys.stderr)
            sys.exit(1)

        # Validate worker is running
        actual_status = refresh_worker_status(worker)
        if actual_status != "running":
            print(f"swarm: error: worker '{args.name}' is not running", file=sys.stderr)
            sys.exit(1)

        workers_to_interrupt = [worker]

    # Send Ctrl-C to each worker
    for worker in workers_to_interrupt:
        session = worker.tmux.session
        window = worker.tmux.window
        socket = worker.tmux.socket if worker.tmux else None
        cmd_prefix = tmux_cmd_prefix(socket)
        subprocess.run(
            cmd_prefix + ["send-keys", "-t", f"{session}:{window}", "C-c"],
            capture_output=True
        )
        print(f"interrupted {worker.name}")


def cmd_eof(args) -> None:
    """Send Ctrl-D to worker."""
    # Load state
    state = State()

    # Get worker by name
    worker = state.get_worker(args.name)
    if not worker:
        print(f"swarm: error: worker '{args.name}' not found", file=sys.stderr)
        sys.exit(1)

    # Validate worker is tmux
    if not worker.tmux:
        print(f"swarm: error: worker '{args.name}' is not a tmux worker", file=sys.stderr)
        sys.exit(1)

    # Validate worker is running
    actual_status = refresh_worker_status(worker)
    if actual_status != "running":
        print(f"swarm: error: worker '{args.name}' is not running", file=sys.stderr)
        sys.exit(1)

    # Send Ctrl-D
    session = worker.tmux.session
    window = worker.tmux.window
    socket = worker.tmux.socket if worker.tmux else None
    cmd_prefix = tmux_cmd_prefix(socket)
    subprocess.run(
        cmd_prefix + ["send-keys", "-t", f"{session}:{window}", "C-d"],
        capture_output=True
    )
    print(f"sent eof to {worker.name}")


def cmd_attach(args) -> None:
    """Attach to worker tmux window."""
    # Load state
    state = State()

    # Get worker by name
    worker = state.get_worker(args.name)

    # Validation: worker not found
    if not worker:
        print(f"swarm: error: worker '{args.name}' not found", file=sys.stderr)
        sys.exit(1)

    # Validation: not a tmux worker
    if not worker.tmux:
        print(f"swarm: error: worker '{args.name}' is not a tmux worker", file=sys.stderr)
        sys.exit(1)

    # Select the window first
    session = worker.tmux.session
    window = worker.tmux.window
    socket = worker.tmux.socket if worker.tmux else None
    cmd_prefix = tmux_cmd_prefix(socket)
    subprocess.run(cmd_prefix + ["select-window", "-t", f"{session}:{window}"], check=True)

    # Then attach to session (this replaces current process)
    if socket:
        os.execvp("tmux", ["tmux", "-L", socket, "attach-session", "-t", session])
    else:
        os.execvp("tmux", ["tmux", "attach-session", "-t", session])


def cmd_logs(args) -> None:
    """View worker output."""
    # Load state
    state = State()

    # Get worker by name
    worker = state.get_worker(args.name)
    if not worker:
        print(f"swarm: no worker named '{args.name}'", file=sys.stderr)
        sys.exit(1)

    # Handle tmux workers
    if worker.tmux:
        socket = worker.tmux.socket if worker.tmux else None
        if args.follow:
            # Follow mode: poll every 1s, clear screen, show last 30 lines
            try:
                while True:
                    history = args.lines if args.history else 0
                    output = tmux_capture_pane(worker.tmux.session, worker.tmux.window, history_lines=history, socket=socket)

                    # Clear screen and print last 30 lines
                    print("\033[2J\033[H", end="")  # ANSI clear
                    lines = output.strip().split('\n')
                    print('\n'.join(lines[-30:]))

                    time.sleep(1)
            except KeyboardInterrupt:
                # Clean exit on Ctrl-C
                pass
        else:
            # Default or history mode
            history = args.lines if args.history else 0
            output = tmux_capture_pane(worker.tmux.session, worker.tmux.window, history_lines=history, socket=socket)
            print(output, end="")

    # Handle non-tmux workers
    else:
        log_path = LOGS_DIR / f"{worker.name}.stdout.log"

        if args.follow:
            # Use tail -f for follow mode
            os.execvp("tail", ["tail", "-f", str(log_path)])
        else:
            # Read and print entire file
            if log_path.exists():
                print(log_path.read_text(), end="")
            else:
                print(f"swarm: no logs found for {worker.name}", file=sys.stderr)
                sys.exit(1)


def cmd_kill(args) -> None:
    """Kill worker processes.

    Handles both tmux and non-tmux workers. For non-tmux workers,
    attempts graceful shutdown with SIGTERM first, then SIGKILL after 5 seconds.
    """
    state = State()

    # Determine which workers to kill
    if args.all:
        workers_to_kill = state.workers[:]
    else:
        if not args.name:
            print("swarm: error: must specify worker name or --all", file=sys.stderr)
            sys.exit(1)

        worker = state.get_worker(args.name)
        if not worker:
            print(f"swarm: error: worker '{args.name}' not found", file=sys.stderr)
            sys.exit(1)
        workers_to_kill = [worker]

    # Kill each worker
    for worker in workers_to_kill:
        # Handle tmux workers
        if worker.tmux:
            socket = worker.tmux.socket if worker.tmux else None
            cmd_prefix = tmux_cmd_prefix(socket)
            subprocess.run(
                cmd_prefix + ["kill-window", "-t", f"{worker.tmux.session}:{worker.tmux.window}"],
                capture_output=True
            )

        # Handle non-tmux workers with PID
        elif worker.pid:
            try:
                # First try graceful shutdown with SIGTERM
                os.kill(worker.pid, signal.SIGTERM)

                # Wait up to 5 seconds for process to die
                for _ in range(50):  # Check every 0.1 seconds
                    time.sleep(0.1)
                    if not process_alive(worker.pid):
                        break
                else:
                    # Process still alive after 5 seconds, use SIGKILL
                    if process_alive(worker.pid):
                        os.kill(worker.pid, signal.SIGKILL)
            except ProcessLookupError:
                # Process already dead
                pass

        # Update worker status
        worker.status = "stopped"

        # Remove worktree if requested
        if args.rm_worktree and worker.worktree:
            force = getattr(args, 'force_dirty', False)
            success, msg = remove_worktree(Path(worker.worktree.path), force=force)
            if not success:
                print(f"swarm: warning: cannot remove worktree for '{worker.name}': {msg}", file=sys.stderr)
                print(f"swarm: use --force-dirty to remove anyway", file=sys.stderr)

        print(f"killed {worker.name}")

    # Save updated state
    state.save()


def cmd_wait(args) -> None:
    """Wait for worker to finish."""
    state = State()

    if args.all:
        workers = [w for w in state.workers if refresh_worker_status(w) == "running"]
    else:
        if not args.name:
            print("swarm: error: name required (or use --all)", file=sys.stderr)
            sys.exit(1)
        worker = state.get_worker(args.name)
        if not worker:
            print(f"swarm: error: worker '{args.name}' not found", file=sys.stderr)
            sys.exit(1)
        workers = [worker]

    start = time.time()
    pending = {w.name: w for w in workers}

    while pending:
        if args.timeout and (time.time() - start) > args.timeout:
            for name in pending:
                print(f"{name}: still running (timeout)")
            sys.exit(1)

        for name in list(pending.keys()):
            w = pending[name]
            if refresh_worker_status(w) == "stopped":
                print(f"{name}: exited")
                del pending[name]

        if pending:
            time.sleep(1)

    sys.exit(0)


def cmd_clean(args) -> None:
    """Clean up dead workers."""
    state = State()

    # Determine which workers to clean
    workers_to_clean = []

    if args.all:
        # Refresh actual status before filtering
        for w in state.workers:
            w.status = refresh_worker_status(w)
        state.save()
        # Get all workers with status "stopped"
        workers_to_clean = [w for w in state.workers if w.status == "stopped"]
    else:
        # Get single worker by name
        if not args.name:
            print("swarm: error: must specify worker name or use --all", file=sys.stderr)
            sys.exit(1)

        worker = state.get_worker(args.name)
        if not worker:
            print(f"swarm: error: worker '{args.name}' not found", file=sys.stderr)
            sys.exit(1)

        workers_to_clean = [worker]

    # Clean each worker
    for worker in workers_to_clean:
        # Refresh status first to confirm stopped
        current_status = refresh_worker_status(worker)

        if current_status == "running":
            if args.all:
                # For --all, skip with warning
                print(f"swarm: warning: skipping '{worker.name}' (still running)", file=sys.stderr)
                continue
            else:
                # For single worker, error and exit
                print(f"swarm: error: cannot clean running worker '{worker.name}'", file=sys.stderr)
                sys.exit(1)

        # Remove worktree if it exists and args.rm_worktree is True
        if worker.worktree and args.rm_worktree:
            worktree_path = Path(worker.worktree.path)
            if worktree_path.exists():
                force = getattr(args, 'force_dirty', False)
                success, msg = remove_worktree(worktree_path, force=force)
                if not success:
                    print(f"swarm: warning: preserving worktree for '{worker.name}': {msg}", file=sys.stderr)
                    print(f"swarm: worktree at: {worktree_path}", file=sys.stderr)
                    print(f"swarm: use --force-dirty to remove anyway", file=sys.stderr)

        # Remove log files if they exist
        stdout_log = LOGS_DIR / f"{worker.name}.stdout.log"
        stderr_log = LOGS_DIR / f"{worker.name}.stderr.log"

        if stdout_log.exists():
            stdout_log.unlink()
        if stderr_log.exists():
            stderr_log.unlink()

        # Remove worker from state
        state.remove_worker(worker.name)

        # Print success message
        print(f"cleaned {worker.name}")


def cmd_respawn(args) -> None:
    """Respawn a dead worker.

    Re-spawns a worker using its original configuration (command, options, etc.).
    The worker must exist in state. If --clean-first is specified, the old
    worktree is removed before respawning.
    """
    state = State()

    # Get worker by name
    worker = state.get_worker(args.name)
    if not worker:
        print(f"swarm: error: worker '{args.name}' not found", file=sys.stderr)
        sys.exit(1)

    # Check current status
    current_status = refresh_worker_status(worker)

    # Kill if still running
    if current_status == "running":
        if worker.tmux:
            socket = worker.tmux.socket if worker.tmux else None
            cmd_prefix = tmux_cmd_prefix(socket)
            subprocess.run(
                cmd_prefix + ["kill-window", "-t", f"{worker.tmux.session}:{worker.tmux.window}"],
                capture_output=True
            )
        elif worker.pid:
            try:
                os.kill(worker.pid, signal.SIGTERM)
                # Wait briefly for graceful shutdown
                for _ in range(50):
                    time.sleep(0.1)
                    if not process_alive(worker.pid):
                        break
                else:
                    if process_alive(worker.pid):
                        os.kill(worker.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass

    # Handle --clean-first: remove worktree if it exists
    if args.clean_first and worker.worktree:
        worktree_path = Path(worker.worktree.path)
        if worktree_path.exists():
            force = getattr(args, 'force_dirty', False)
            success, msg = remove_worktree(worktree_path, force=force)
            if not success:
                print(f"swarm: error: cannot remove worktree: {msg}", file=sys.stderr)
                print(f"swarm: worktree at: {worktree_path}", file=sys.stderr)
                print(f"swarm: use --force-dirty to remove anyway, or commit changes first", file=sys.stderr)
                sys.exit(1)

    # Store original config before removing from state
    original_cmd = worker.cmd
    original_cwd = worker.cwd
    original_env = worker.env
    original_tags = worker.tags
    original_tmux = worker.tmux
    original_worktree = worker.worktree

    # Remove old worker from state
    state.remove_worker(args.name)

    # Determine working directory
    cwd = Path(original_cwd)
    worktree_info = None

    # Recreate worktree if needed
    if original_worktree:
        if args.clean_first or not Path(original_worktree.path).exists():
            # Need to recreate worktree
            worktree_path = Path(original_worktree.path)
            branch = original_worktree.branch
            try:
                create_worktree(worktree_path, branch)
            except subprocess.CalledProcessError as e:
                print(f"swarm: error: failed to create worktree: {e}", file=sys.stderr)
                sys.exit(1)
            cwd = worktree_path
        else:
            # Worktree still exists, use it
            cwd = Path(original_worktree.path)

        worktree_info = WorktreeInfo(
            path=str(cwd),
            branch=original_worktree.branch,
            base_repo=original_worktree.base_repo
        )

    # Spawn the worker
    tmux_info = None
    pid = None

    if original_tmux:
        # Spawn in tmux
        socket = original_tmux.socket if original_tmux else None
        try:
            create_tmux_window(original_tmux.session, args.name, cwd, original_cmd, socket)
            tmux_info = TmuxInfo(session=original_tmux.session, window=args.name, socket=socket)
        except subprocess.CalledProcessError as e:
            print(f"swarm: error: failed to create tmux window: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        # Spawn as background process
        log_prefix = LOGS_DIR / args.name
        try:
            pid = spawn_process(original_cmd, cwd, original_env, log_prefix)
        except Exception as e:
            print(f"swarm: error: failed to spawn process: {e}", file=sys.stderr)
            sys.exit(1)

    # Create new Worker object
    new_worker = Worker(
        name=args.name,
        status="running",
        cmd=original_cmd,
        started=datetime.now().isoformat(),
        cwd=str(cwd),
        env=original_env,
        tags=original_tags,
        tmux=tmux_info,
        worktree=worktree_info,
        pid=pid,
    )

    # Add to state
    state.add_worker(new_worker)

    # Print success message
    if tmux_info:
        print(f"respawned {args.name} (tmux: {tmux_info.session}:{tmux_info.window})")
    else:
        print(f"respawned {args.name} (pid: {pid})")


if __name__ == "__main__":
    main()
