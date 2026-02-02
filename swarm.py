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
RALPH_DIR = SWARM_DIR / "ralph"  # Ralph loop state directory

# Agent instructions template for AGENTS.md/CLAUDE.md injection
# Marker string 'Process Management (swarm)' used for idempotent detection
SWARM_INSTRUCTIONS = """
## Process Management (swarm)

Swarm manages parallel agent workers in isolated git worktrees via tmux.

### Quick Reference
```bash
swarm spawn --name <id> --tmux --worktree -- claude  # Start agent in isolated worktree
swarm ls                          # List all workers
swarm status <name>               # Check worker status
swarm send <name> "prompt"        # Send prompt to worker
swarm logs <name>                 # View worker output
swarm attach <name>               # Attach to tmux window
swarm kill <name> --rm-worktree   # Stop and cleanup
```

### Worktree Isolation
Each `--worktree` worker gets its own git branch and directory:
```bash
swarm spawn --name feature-auth --tmux --worktree -- claude
# Creates: <repo>-worktrees/feature-auth on branch 'feature-auth'
```

### Power User Tips
- `--ready-wait`: Block until agent is ready for input
- `--tag team-a`: Tag workers for filtering (`swarm ls --tag team-a`)
- `--env KEY=VAL`: Pass environment variables to worker
- `swarm send --all "msg"`: Broadcast to all running workers
- `swarm wait --all`: Wait for all workers to complete

State stored in `~/.swarm/state.json`. Logs in `~/.swarm/logs/`.
""".strip()

# Ralph prompt template for autonomous agent looping
# Intentionally minimal and direct - less prompt = more context for actual work
RALPH_PROMPT_TEMPLATE = """study specs/README.md
study CLAUDE.md and pick the most important incomplete task

IMPORTANT:

- do not assume anything is implemented - verify by reading code
- update IMPLEMENTATION_PLAN.md when the task is done
- if tests are missing, add them (choose unit/integration/property as appropriate, follow existing patterns)
- run tests after changes
- commit and push when you are done
""".strip()


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
    metadata: dict = field(default_factory=dict)  # Extensible metadata (e.g., ralph info)

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
            "metadata": self.metadata,
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
            metadata=d.get("metadata", {}),
        )


@dataclass
class RalphState:
    """Ralph loop state for a worker."""
    worker_name: str
    prompt_file: str
    max_iterations: int
    current_iteration: int = 0
    status: str = "running"  # running, paused, stopped, failed
    started: str = ""
    last_iteration_started: str = ""
    consecutive_failures: int = 0
    total_failures: int = 0
    done_pattern: Optional[str] = None
    inactivity_timeout: int = 300
    inactivity_mode: str = "ready"  # output, ready, both

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "worker_name": self.worker_name,
            "prompt_file": self.prompt_file,
            "max_iterations": self.max_iterations,
            "current_iteration": self.current_iteration,
            "status": self.status,
            "started": self.started,
            "last_iteration_started": self.last_iteration_started,
            "consecutive_failures": self.consecutive_failures,
            "total_failures": self.total_failures,
            "done_pattern": self.done_pattern,
            "inactivity_timeout": self.inactivity_timeout,
            "inactivity_mode": self.inactivity_mode,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "RalphState":
        """Create RalphState from dictionary."""
        return cls(
            worker_name=d["worker_name"],
            prompt_file=d["prompt_file"],
            max_iterations=d["max_iterations"],
            current_iteration=d.get("current_iteration", 0),
            status=d.get("status", "running"),
            started=d.get("started", ""),
            last_iteration_started=d.get("last_iteration_started", ""),
            consecutive_failures=d.get("consecutive_failures", 0),
            total_failures=d.get("total_failures", 0),
            done_pattern=d.get("done_pattern"),
            inactivity_timeout=d.get("inactivity_timeout", 300),
            inactivity_mode=d.get("inactivity_mode", "ready"),
        )


def get_ralph_state_path(worker_name: str) -> Path:
    """Get the path to a worker's ralph state file."""
    return RALPH_DIR / worker_name / "state.json"


def load_ralph_state(worker_name: str) -> Optional[RalphState]:
    """Load ralph state for a worker.

    Args:
        worker_name: Name of the worker

    Returns:
        RalphState if it exists, None otherwise
    """
    state_path = get_ralph_state_path(worker_name)
    if not state_path.exists():
        return None

    with open(state_path, "r") as f:
        data = json.load(f)
        return RalphState.from_dict(data)


def save_ralph_state(ralph_state: RalphState) -> None:
    """Save ralph state for a worker.

    Args:
        ralph_state: RalphState to save
    """
    state_path = get_ralph_state_path(ralph_state.worker_name)
    state_path.parent.mkdir(parents=True, exist_ok=True)

    with open(state_path, "w") as f:
        json.dump(ralph_state.to_dict(), f, indent=2)


def get_ralph_iterations_log_path(worker_name: str) -> Path:
    """Get the path to a worker's ralph iterations log file."""
    return RALPH_DIR / worker_name / "iterations.log"


def log_ralph_iteration(worker_name: str, event: str, **kwargs) -> None:
    """Log a ralph iteration event.

    Appends a timestamped log entry to the worker's iterations.log file.
    Log format: ISO_TIMESTAMP [EVENT] message

    Args:
        worker_name: Name of the worker
        event: Event type (START, END, FAIL, TIMEOUT, DONE)
        **kwargs: Additional event-specific data (iteration, max_iterations, exit_code, duration)
    """
    log_path = get_ralph_iterations_log_path(worker_name)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().isoformat(timespec='seconds')

    # Format the log message based on event type
    if event == "START":
        iteration = kwargs.get('iteration', 0)
        max_iterations = kwargs.get('max_iterations', 0)
        message = f"iteration {iteration}/{max_iterations}"
    elif event == "END":
        iteration = kwargs.get('iteration', 0)
        exit_code = kwargs.get('exit_code', 0)
        duration = kwargs.get('duration', '')
        message = f"iteration {iteration} exit={exit_code} duration={duration}"
    elif event == "FAIL":
        iteration = kwargs.get('iteration', 0)
        exit_code = kwargs.get('exit_code', 1)
        attempt = kwargs.get('attempt', 1)
        backoff = kwargs.get('backoff', 0)
        message = f"iteration {iteration} exit={exit_code} attempt={attempt}/5 backoff={backoff}s"
    elif event == "TIMEOUT":
        iteration = kwargs.get('iteration', 0)
        timeout = kwargs.get('timeout', 300)
        message = f"iteration {iteration} inactivity_timeout={timeout}s"
    elif event == "DONE":
        total_iterations = kwargs.get('total_iterations', 0)
        reason = kwargs.get('reason', 'max_iterations')
        message = f"loop complete after {total_iterations} iterations reason={reason}"
    elif event == "PAUSE":
        reason = kwargs.get('reason', 'manual')
        message = f"loop paused reason={reason}"
    else:
        message = kwargs.get('message', '')

    log_line = f"{timestamp} [{event}] {message}\n"

    with open(log_path, "a") as f:
        f.write(log_line)


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


def session_has_other_workers(state: "State", session: str, exclude_worker: str, socket: Optional[str] = None) -> bool:
    """Check if other workers are using the same tmux session.

    Args:
        state: Current swarm state
        session: Tmux session name to check
        exclude_worker: Worker name to exclude from the check
        socket: Optional tmux socket name (workers must match both session and socket)

    Returns:
        True if other workers exist in the same session (and socket), False otherwise
    """
    for worker in state.workers:
        if worker.name == exclude_worker:
            continue
        if not worker.tmux:
            continue
        if worker.tmux.session != session:
            continue
        # Check socket matches (both None or both same value)
        worker_socket = worker.tmux.socket
        if worker_socket != socket:
            continue
        # Found another worker in the same session/socket
        return True
    return False


def kill_tmux_session(session: str, socket: Optional[str] = None) -> None:
    """Kill a tmux session.

    Args:
        session: Tmux session name to kill
        socket: Optional tmux socket name
    """
    cmd_prefix = tmux_cmd_prefix(socket)
    subprocess.run(
        cmd_prefix + ["kill-session", "-t", session],
        capture_output=True
    )


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
        # OpenCode CLI ready patterns
        r"opencode\s+v\d+",               # "opencode v1.0.115" version banner
        r"tab\s+switch\s+agent",          # UI hint at bottom
        r"ctrl\+p\s+commands",            # UI hint at bottom
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
    spawn_p.add_argument("--worktree-dir", default=None,
                        help="Parent dir for worktrees (default: <repo>-worktrees, sibling to repo)")
    spawn_p.add_argument("--tag", action="append", default=[], dest="tags",
                        help="Tag for filtering (repeatable)")
    spawn_p.add_argument("--env", action="append", default=[],
                        help="Environment variable KEY=VAL (repeatable)")
    spawn_p.add_argument("--cwd", help="Working directory")
    spawn_p.add_argument("--ready-wait", action="store_true",
                        help="Wait for agent to be ready before returning (tmux only)")
    spawn_p.add_argument("--ready-timeout", type=int, default=120,
                        help="Timeout in seconds for --ready-wait (default: 120, suitable for Claude Code startup)")
    # Ralph mode arguments
    spawn_p.add_argument("--ralph", action="store_true",
                        help="Enable ralph loop mode (autonomous agent looping)")
    spawn_p.add_argument("--prompt-file", type=str, default=None,
                        help="Path to prompt file for ralph mode (required with --ralph)")
    spawn_p.add_argument("--max-iterations", type=int, default=None,
                        help="Maximum loop iterations for ralph mode (required with --ralph)")
    spawn_p.add_argument("--inactivity-timeout", type=int, default=300,
                        help="Inactivity timeout in seconds for ralph mode (default: 300)")
    spawn_p.add_argument("--inactivity-mode", type=str, choices=["output", "ready", "both"],
                        default="ready",
                        help="Inactivity detection mode: output|ready|both (default: ready)")
    spawn_p.add_argument("--done-pattern", type=str, default=None,
                        help="Regex pattern to stop ralph loop when matched in output")
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

    # init
    init_p = subparsers.add_parser("init", help="Initialize swarm in project")
    init_p.add_argument("--dry-run", action="store_true",
                        help="Show what would be done without making changes")
    init_p.add_argument("--file", choices=["AGENTS.md", "CLAUDE.md"], default=None,
                        help="Output file name (default: auto-detect AGENTS.md or CLAUDE.md)")
    init_p.add_argument("--force", action="store_true",
                        help="Overwrite existing file")

    # ralph - autonomous agent looping (Ralph Wiggum pattern)
    ralph_p = subparsers.add_parser("ralph", help="Ralph loop management (autonomous agent looping)")
    ralph_subparsers = ralph_p.add_subparsers(dest="ralph_command", required=True)

    # ralph init - create PROMPT.md
    ralph_init_p = ralph_subparsers.add_parser("init", help="Create PROMPT.md with starter template")
    ralph_init_p.add_argument("--force", action="store_true",
                              help="Overwrite existing PROMPT.md")

    # ralph template - output template to stdout
    ralph_subparsers.add_parser("template", help="Output prompt template to stdout")

    # ralph status - show ralph loop status
    ralph_status_p = ralph_subparsers.add_parser("status", help="Show ralph loop status for a worker")
    ralph_status_p.add_argument("name", help="Worker name")

    # ralph pause - pause the ralph loop
    ralph_pause_p = ralph_subparsers.add_parser("pause", help="Pause ralph loop for a worker")
    ralph_pause_p.add_argument("name", help="Worker name")

    # ralph resume - resume the ralph loop
    ralph_resume_p = ralph_subparsers.add_parser("resume", help="Resume ralph loop for a worker")
    ralph_resume_p.add_argument("name", help="Worker name")

    # ralph run - run the ralph loop (main outer loop execution)
    ralph_run_p = ralph_subparsers.add_parser("run", help="Run the ralph loop for a worker")
    ralph_run_p.add_argument("name", help="Worker name")

    # ralph list - list all ralph workers
    ralph_list_p = ralph_subparsers.add_parser("list", help="List all ralph workers")
    ralph_list_p.add_argument("--format", choices=["table", "json", "names"],
                              default="table", help="Output format (default: table)")
    ralph_list_p.add_argument("--status", choices=["all", "running", "paused", "stopped", "failed"],
                              default="all", help="Filter by ralph status (default: all)")

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
    elif args.command == "init":
        cmd_init(args)
    elif args.command == "ralph":
        cmd_ralph(args)


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

    # Ralph mode validation
    if args.ralph:
        # --ralph requires --prompt-file
        if args.prompt_file is None:
            print("swarm: error: --ralph requires --prompt-file", file=sys.stderr)
            sys.exit(1)

        # --ralph requires --max-iterations
        if args.max_iterations is None:
            print("swarm: error: --ralph requires --max-iterations", file=sys.stderr)
            sys.exit(1)

        # Validate prompt file exists
        prompt_path = Path(args.prompt_file)
        if not prompt_path.exists():
            print(f"swarm: error: prompt file not found: {args.prompt_file}", file=sys.stderr)
            sys.exit(1)

        # Warn for high iteration count
        if args.max_iterations > 50:
            print("swarm: warning: high iteration count (>50) may consume significant resources", file=sys.stderr)

        # Auto-enable tmux mode for ralph
        args.tmux = True

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
        if args.worktree_dir is None:
            # Default: <repo-name>-worktrees as sibling to repo
            worktree_dir = git_root.parent / f"{git_root.name}-worktrees"
        else:
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

    # Build metadata for ralph workers
    metadata = {}
    if args.ralph:
        metadata = {
            "ralph": True,
            "ralph_iteration": 1,  # Starting with iteration 1
        }

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
        metadata=metadata,
    )

    # Add to state
    state.add_worker(worker)

    # Create ralph state if in ralph mode
    if args.ralph:
        ralph_state = RalphState(
            worker_name=args.name,
            prompt_file=str(Path(args.prompt_file).resolve()),
            max_iterations=args.max_iterations,
            current_iteration=1,  # Starting at iteration 1, not 0
            status="running",
            started=datetime.now().isoformat(),
            last_iteration_started=datetime.now().isoformat(),
            inactivity_timeout=args.inactivity_timeout,
            inactivity_mode=args.inactivity_mode,
            done_pattern=args.done_pattern,
        )
        save_ralph_state(ralph_state)

        # Log the iteration start
        log_ralph_iteration(
            args.name,
            "START",
            iteration=1,
            max_iterations=args.max_iterations
        )

    # Wait for agent to be ready if requested
    if args.ready_wait and tmux_info:
        socket = tmux_info.socket if tmux_info else None
        if not wait_for_agent_ready(tmux_info.session, tmux_info.window, args.ready_timeout, socket):
            print(f"swarm: warning: agent '{args.name}' did not become ready within {args.ready_timeout}s", file=sys.stderr)

    # Print success message
    if tmux_info:
        msg = f"spawned {args.name} (tmux: {tmux_info.session}:{tmux_info.window})"
        if args.ralph:
            msg += f" [ralph mode: iteration 1/{args.max_iterations}]"
        print(msg)
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

    # Track sessions to clean up (session, socket) tuples
    sessions_to_cleanup: set[tuple[str, Optional[str]]] = set()

    # Kill each worker
    for worker in workers_to_kill:
        # Handle tmux workers
        if worker.tmux:
            socket = worker.tmux.socket if worker.tmux else None
            session = worker.tmux.session
            cmd_prefix = tmux_cmd_prefix(socket)
            subprocess.run(
                cmd_prefix + ["kill-window", "-t", f"{session}:{worker.tmux.window}"],
                capture_output=True
            )

            # Check if we should clean up the session after killing this worker
            # We need to check against remaining workers (excluding those being killed)
            workers_being_killed = {w.name for w in workers_to_kill}
            has_other = any(
                w.name != worker.name and
                w.name not in workers_being_killed and
                w.tmux and
                w.tmux.session == session and
                w.tmux.socket == socket
                for w in state.workers
            )
            if not has_other:
                sessions_to_cleanup.add((session, socket))

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

    # Clean up empty tmux sessions
    for session, socket in sessions_to_cleanup:
        kill_tmux_session(session, socket=socket)

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

    # Track sessions to clean up (session, socket) tuples
    sessions_to_cleanup: set[tuple[str, Optional[str]]] = set()

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

        # Check if we need to clean up the tmux session after removing this worker
        if worker.tmux:
            session = worker.tmux.session
            socket = worker.tmux.socket
            # Check against workers not being cleaned
            workers_being_cleaned = {w.name for w in workers_to_clean}
            has_other = any(
                w.name != worker.name and
                w.name not in workers_being_cleaned and
                w.tmux and
                w.tmux.session == session and
                w.tmux.socket == socket
                for w in state.workers
            )
            if not has_other:
                sessions_to_cleanup.add((session, socket))

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

    # Clean up empty tmux sessions
    for session, socket in sessions_to_cleanup:
        kill_tmux_session(session, socket=socket)


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


def cmd_init(args) -> None:
    """Initialize swarm in a project by creating agent instructions file.

    Implements the following logic:
    1. If --file is specified, use that file directly
    2. Otherwise, auto-discover: check AGENTS.md first, then CLAUDE.md
    3. If marker 'Process Management (swarm)' found, report already exists (idempotent)
    4. If file exists but no marker, append SWARM_INSTRUCTIONS
    5. If neither file exists, create AGENTS.md with SWARM_INSTRUCTIONS

    Args:
        args: Namespace with dry_run, file, force attributes
    """
    # Marker string for idempotent detection
    marker = "Process Management (swarm)"

    # Determine target file
    if args.file:
        # Explicit file choice overrides auto-discovery
        target_file = Path(args.file)
        file_exists = target_file.exists()
    else:
        # Auto-discover: check AGENTS.md first, then CLAUDE.md
        agents_path = Path("AGENTS.md")
        claude_path = Path("CLAUDE.md")

        if agents_path.exists():
            target_file = agents_path
            file_exists = True
        elif claude_path.exists():
            target_file = claude_path
            file_exists = True
        else:
            # Neither exists, default to AGENTS.md
            target_file = agents_path
            file_exists = False

    # Check for existing marker in the target file (or in both files for auto-discovery)
    if not args.force:
        # Check target file
        if file_exists:
            existing_content = target_file.read_text()
            if marker in existing_content:
                print(f"swarm: {target_file} already contains swarm instructions")
                return

        # For auto-discovery, also check CLAUDE.md even if AGENTS.md was selected
        if not args.file:
            for check_path in [Path("AGENTS.md"), Path("CLAUDE.md")]:
                if check_path.exists() and check_path != target_file:
                    check_content = check_path.read_text()
                    if marker in check_content:
                        print(f"swarm: {check_path} already contains swarm instructions")
                        return

    # Handle --dry-run
    if args.dry_run:
        if file_exists:
            print(f"Would append swarm instructions to {target_file}")
        else:
            print(f"Would create {target_file} with swarm agent instructions")
        return

    # Prepare content with SWARM_INSTRUCTIONS
    if file_exists:
        existing_content = target_file.read_text()

        if args.force and marker in existing_content:
            # Replace existing section with new SWARM_INSTRUCTIONS
            # Find the marker and remove everything after it until the next ## heading or EOF
            import re
            pattern = r'(## Process Management \(swarm\).*?)(?=\n## |\Z)'
            new_content = re.sub(pattern, SWARM_INSTRUCTIONS, existing_content, flags=re.DOTALL)
            target_file.write_text(new_content)
            print(f"Updated swarm instructions in {target_file}")
        else:
            # Append to existing file
            # Normalize trailing newlines: strip and add exactly two newlines
            normalized = existing_content.rstrip('\n')
            new_content = normalized + "\n\n" + SWARM_INSTRUCTIONS + "\n"
            target_file.write_text(new_content)
            print(f"Added swarm instructions to {target_file}")
    else:
        # Create new file
        target_file.write_text(SWARM_INSTRUCTIONS + "\n")
        print(f"Created {target_file}")


def cmd_ralph(args) -> None:
    """Ralph loop management commands.

    Dispatches to ralph subcommands:
    - init: Create PROMPT.md with starter template
    - template: Output template to stdout
    - status: Show ralph loop status for a worker
    - pause: Pause ralph loop for a worker
    - resume: Resume ralph loop for a worker
    - run: Run the ralph loop (main outer loop execution)
    - list: List all ralph workers
    """
    if args.ralph_command == "init":
        cmd_ralph_init(args)
    elif args.ralph_command == "template":
        cmd_ralph_template(args)
    elif args.ralph_command == "status":
        cmd_ralph_status(args)
    elif args.ralph_command == "pause":
        cmd_ralph_pause(args)
    elif args.ralph_command == "resume":
        cmd_ralph_resume(args)
    elif args.ralph_command == "run":
        cmd_ralph_run(args)
    elif args.ralph_command == "list":
        cmd_ralph_list(args)


def cmd_ralph_init(args) -> None:
    """Create PROMPT.md with starter template.

    Creates a PROMPT.md file in the current directory with the ralph
    prompt template. Fails if the file already exists unless --force
    is specified.

    Args:
        args: Namespace with force attribute
    """
    target_file = Path("PROMPT.md")

    # Check if file already exists
    if target_file.exists() and not args.force:
        print("swarm: error: PROMPT.md already exists (use --force to overwrite)", file=sys.stderr)
        sys.exit(1)

    # Write template to file
    target_file.write_text(RALPH_PROMPT_TEMPLATE + "\n")

    if args.force and target_file.exists():
        print("created PROMPT.md (overwritten)")
    else:
        print("created PROMPT.md")


def cmd_ralph_template(args) -> None:
    """Output prompt template to stdout.

    Prints the ralph prompt template to stdout for inspection or
    piping to a custom file.

    Args:
        args: Namespace (unused, but required for consistency)
    """
    print(RALPH_PROMPT_TEMPLATE)


def cmd_ralph_status(args) -> None:
    """Show ralph loop status for a worker.

    Displays the current state of a ralph loop including iteration count,
    status, failure counts, and configuration.

    Args:
        args: Namespace with name attribute
    """
    # Load swarm state to verify worker exists
    state = State()
    worker = state.get_worker(args.name)

    if not worker:
        print(f"swarm: error: worker '{args.name}' not found", file=sys.stderr)
        sys.exit(1)

    # Load ralph state
    ralph_state = load_ralph_state(args.name)

    if not ralph_state:
        print(f"swarm: error: worker '{args.name}' is not a ralph worker", file=sys.stderr)
        sys.exit(1)

    # Format output per spec
    print(f"Ralph Loop: {ralph_state.worker_name}")
    print(f"Status: {ralph_state.status}")
    print(f"Iteration: {ralph_state.current_iteration}/{ralph_state.max_iterations}")

    if ralph_state.started:
        # Parse ISO format and format nicely
        started_dt = datetime.fromisoformat(ralph_state.started)
        print(f"Started: {started_dt.strftime('%Y-%m-%d %H:%M:%S')}")

    if ralph_state.last_iteration_started:
        last_iter_dt = datetime.fromisoformat(ralph_state.last_iteration_started)
        print(f"Current iteration started: {last_iter_dt.strftime('%Y-%m-%d %H:%M:%S')}")

    print(f"Consecutive failures: {ralph_state.consecutive_failures}")
    print(f"Total failures: {ralph_state.total_failures}")
    print(f"Inactivity timeout: {ralph_state.inactivity_timeout}s")
    print(f"Inactivity mode: {ralph_state.inactivity_mode}")

    if ralph_state.done_pattern:
        print(f"Done pattern: {ralph_state.done_pattern}")


def cmd_ralph_pause(args) -> None:
    """Pause ralph loop for a worker.

    Sets the ralph state status to "paused". The current worker continues
    running, but the loop will not restart when it exits.

    Args:
        args: Namespace with name attribute
    """
    # Load swarm state to verify worker exists
    state = State()
    worker = state.get_worker(args.name)

    if not worker:
        print(f"swarm: error: worker '{args.name}' not found", file=sys.stderr)
        sys.exit(1)

    # Load ralph state
    ralph_state = load_ralph_state(args.name)

    if not ralph_state:
        print(f"swarm: error: worker '{args.name}' is not a ralph worker", file=sys.stderr)
        sys.exit(1)

    # Check if already paused
    if ralph_state.status == "paused":
        print(f"swarm: warning: worker '{args.name}' is already paused", file=sys.stderr)
        return

    # Update status to paused
    ralph_state.status = "paused"
    save_ralph_state(ralph_state)

    print(f"paused ralph loop for {args.name}")


def cmd_ralph_resume(args) -> None:
    """Resume ralph loop for a worker.

    Sets the ralph state status to "running". If the worker is not running,
    a fresh agent will need to be spawned.

    Args:
        args: Namespace with name attribute
    """
    # Load swarm state to verify worker exists
    state = State()
    worker = state.get_worker(args.name)

    if not worker:
        print(f"swarm: error: worker '{args.name}' not found", file=sys.stderr)
        sys.exit(1)

    # Load ralph state
    ralph_state = load_ralph_state(args.name)

    if not ralph_state:
        print(f"swarm: error: worker '{args.name}' is not a ralph worker", file=sys.stderr)
        sys.exit(1)

    # Check if not paused
    if ralph_state.status != "paused":
        print(f"swarm: warning: worker '{args.name}' is not paused", file=sys.stderr)
        return

    # Update status to running
    ralph_state.status = "running"
    save_ralph_state(ralph_state)

    print(f"resumed ralph loop for {args.name}")


def cmd_ralph_list(args) -> None:
    """List all ralph workers.

    Shows all workers that have ralph state (are/were ralph workers).
    Supports filtering by ralph status and multiple output formats.

    Args:
        args: Namespace with format and status attributes
    """
    # Load swarm state
    state = State()

    # Find all ralph workers by checking for ralph state files
    ralph_workers = []
    if RALPH_DIR.exists():
        for worker_dir in RALPH_DIR.iterdir():
            if worker_dir.is_dir():
                state_file = worker_dir / "state.json"
                if state_file.exists():
                    ralph_state = load_ralph_state(worker_dir.name)
                    if ralph_state:
                        # Get the worker from swarm state (may not exist)
                        worker = state.get_worker(ralph_state.worker_name)
                        ralph_workers.append((ralph_state, worker))

    # Filter by ralph status if specified
    if args.status != "all":
        ralph_workers = [(rs, w) for rs, w in ralph_workers if rs.status == args.status]

    # Output based on format
    if args.format == "json":
        # JSON format - include ralph state and worker info
        output = []
        for ralph_state, worker in ralph_workers:
            entry = ralph_state.to_dict()
            if worker:
                entry["worker_status"] = refresh_worker_status(worker)
            else:
                entry["worker_status"] = "removed"
            output.append(entry)
        print(json.dumps(output, indent=2))

    elif args.format == "names":
        # Names format - one per line
        for ralph_state, _ in ralph_workers:
            print(ralph_state.worker_name)

    else:  # table format
        if not ralph_workers:
            return

        # Prepare rows
        rows = []
        for ralph_state, worker in ralph_workers:
            # WORKER_STATUS column
            if worker:
                worker_status = refresh_worker_status(worker)
            else:
                worker_status = "removed"

            # ITERATION column
            iteration = f"{ralph_state.current_iteration}/{ralph_state.max_iterations}"

            # FAILURES column
            failures = f"{ralph_state.consecutive_failures}/{ralph_state.total_failures}"

            rows.append({
                "NAME": ralph_state.worker_name,
                "RALPH_STATUS": ralph_state.status,
                "WORKER_STATUS": worker_status,
                "ITERATION": iteration,
                "FAILURES": failures,
            })

        # Calculate column widths
        headers = ["NAME", "RALPH_STATUS", "WORKER_STATUS", "ITERATION", "FAILURES"]
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


def wait_for_worker_exit(worker: Worker, timeout: Optional[int] = None) -> tuple[bool, str]:
    """Wait for a worker to exit.

    Monitors the worker and returns when it exits or times out.

    Args:
        worker: The worker to monitor
        timeout: Optional timeout in seconds (None = no timeout)

    Returns:
        Tuple of (exited: bool, reason: str)
        - (True, "exit") if worker exited normally
        - (False, "timeout") if timeout was reached
        - (False, "running") if still running (shouldn't happen with blocking)
    """
    start = time.time()

    while True:
        # Check if worker has stopped
        status = refresh_worker_status(worker)
        if status == "stopped":
            return (True, "exit")

        # Check timeout
        if timeout is not None and (time.time() - start) >= timeout:
            return (False, "timeout")

        # Poll every second
        time.sleep(1)


def detect_inactivity(worker: Worker, timeout: int, mode: str = "ready") -> bool:
    """Detect if a worker has become inactive.

    Supports three detection modes:
    - "output": Detects when output stops changing for timeout seconds
    - "ready": Detects when agent returns to ready state (prompt visible) for timeout seconds
    - "both": Triggers on either condition (most sensitive)

    Args:
        worker: The worker to monitor
        timeout: Inactivity timeout in seconds
        mode: Detection mode ("output", "ready", or "both")

    Returns:
        True if inactivity detected, False otherwise (worker exited or still active)
    """
    import re

    if not worker.tmux:
        return False

    socket = worker.tmux.socket
    last_output = ""
    output_inactive_start = None
    ready_inactive_start = None

    # Ready patterns (same as wait_for_agent_ready)
    ready_patterns = [
        r"bypass\s+permissions",
        r"permissions?\s+mode",
        r"shift\+tab\s+to\s+cycle",
        r"Claude\s+Code\s+v\d+",
        r"(?:^|\x1b\[[0-9;]*m)>\s",
        r"❯\s",
        r"opencode\s+v\d+",
        r"tab\s+switch\s+agent",
        r"ctrl\+p\s+commands",
        r"(?:^|\x1b\[[0-9;]*m)\$\s",
        r"(?:^|\x1b\[[0-9;]*m)>>>\s",
    ]

    def is_ready(output: str) -> bool:
        """Check if output contains ready patterns."""
        for line in output.split('\n'):
            for pattern in ready_patterns:
                if re.search(pattern, line):
                    return True
        return False

    while True:
        # Check if worker is still running
        if refresh_worker_status(worker) == "stopped":
            return False

        try:
            # Capture current output
            current_output = tmux_capture_pane(
                worker.tmux.session,
                worker.tmux.window,
                socket=socket
            )

            # Output-based detection
            if mode in ("output", "both"):
                if current_output != last_output:
                    last_output = current_output
                    output_inactive_start = None
                else:
                    if output_inactive_start is None:
                        output_inactive_start = time.time()
                    elif (time.time() - output_inactive_start) >= timeout:
                        return True
            else:
                # Still track output for ready mode
                last_output = current_output

            # Ready-based detection
            if mode in ("ready", "both"):
                if is_ready(current_output):
                    if ready_inactive_start is None:
                        ready_inactive_start = time.time()
                    elif (time.time() - ready_inactive_start) >= timeout:
                        return True
                else:
                    ready_inactive_start = None

        except subprocess.CalledProcessError:
            # Window might have closed
            return False

        time.sleep(1)


def check_done_pattern(worker: Worker, pattern: str) -> bool:
    """Check if output matches done pattern.

    Args:
        worker: The worker to check
        pattern: Regex pattern to match

    Returns:
        True if pattern matched in output, False otherwise
    """
    import re

    if not worker.tmux:
        return False

    socket = worker.tmux.socket

    try:
        output = tmux_capture_pane(
            worker.tmux.session,
            worker.tmux.window,
            history_lines=1000,  # Include scrollback
            socket=socket
        )
        return bool(re.search(pattern, output))
    except subprocess.CalledProcessError:
        return False


def format_duration(seconds: float) -> str:
    """Format a duration in seconds to human-readable string.

    Args:
        seconds: Duration in seconds

    Returns:
        Human-readable string like "5m 30s" or "1h 15m"
    """
    if seconds < 60:
        return f"{int(seconds)}s"
    elif seconds < 3600:
        minutes = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{minutes}m {secs}s"
    else:
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        return f"{hours}h {minutes}m"


def kill_worker_for_ralph(worker: Worker, state: State) -> None:
    """Kill a worker as part of ralph loop iteration.

    Similar to cmd_kill but without removing from state.

    Args:
        worker: The worker to kill
        state: The current state
    """
    if worker.tmux:
        socket = worker.tmux.socket
        cmd_prefix = tmux_cmd_prefix(socket)
        subprocess.run(
            cmd_prefix + ["kill-window", "-t", f"{worker.tmux.session}:{worker.tmux.window}"],
            capture_output=True
        )


def spawn_worker_for_ralph(
    name: str,
    cmd: list[str],
    cwd: Path,
    env: dict[str, str],
    tags: list[str],
    session: str,
    socket: Optional[str],
    worktree_info: Optional[WorktreeInfo],
    metadata: dict
) -> Worker:
    """Spawn a worker for a ralph loop iteration.

    Creates a new tmux window for the worker.

    Args:
        name: Worker name
        cmd: Command to run
        cwd: Working directory
        env: Environment variables
        tags: Worker tags
        session: Tmux session name
        socket: Optional tmux socket
        worktree_info: Optional worktree info
        metadata: Worker metadata

    Returns:
        The created Worker object
    """
    # Create tmux window
    create_tmux_window(session, name, cwd, cmd, socket)
    tmux_info = TmuxInfo(session=session, window=name, socket=socket)

    # Create worker object
    worker = Worker(
        name=name,
        status="running",
        cmd=cmd,
        started=datetime.now().isoformat(),
        cwd=str(cwd),
        env=env,
        tags=tags,
        tmux=tmux_info,
        worktree=worktree_info,
        pid=None,
        metadata=metadata,
    )

    return worker


def send_prompt_to_worker(worker: Worker, prompt_content: str) -> None:
    """Send prompt content to a worker.

    Args:
        worker: The worker to send to
        prompt_content: The prompt content to send
    """
    if not worker.tmux:
        return

    socket = worker.tmux.socket

    # Wait briefly for agent to be ready
    wait_for_agent_ready(
        worker.tmux.session,
        worker.tmux.window,
        timeout=30,
        socket=socket
    )

    # Send the prompt content
    tmux_send(
        worker.tmux.session,
        worker.tmux.window,
        prompt_content,
        enter=True,
        socket=socket
    )


def cmd_ralph_run(args) -> None:
    """Run the ralph loop for a worker.

    This is the main outer loop execution that:
    1. Monitors the worker for exit or inactivity
    2. Checks for done pattern
    3. Restarts the worker with fresh prompt
    4. Handles failures with exponential backoff

    Graceful shutdown: On SIGTERM, the loop is paused and the current
    agent is allowed to complete before exiting.

    Args:
        args: Namespace with name attribute
    """
    import re

    # Track if we received SIGTERM for graceful shutdown
    sigterm_received = False

    def sigterm_handler(signum, frame):
        """Handle SIGTERM by pausing the ralph loop gracefully."""
        nonlocal sigterm_received
        sigterm_received = True
        print(f"\n[ralph] {args.name}: received SIGTERM, pausing loop (current agent will complete)")
        # Pause the ralph state so the loop exits gracefully
        ralph_state = load_ralph_state(args.name)
        if ralph_state and ralph_state.status == "running":
            ralph_state.status = "paused"
            save_ralph_state(ralph_state)
            log_ralph_iteration(args.name, "PAUSE", reason="sigterm")

    # Install signal handler for graceful shutdown
    old_sigterm_handler = signal.signal(signal.SIGTERM, sigterm_handler)

    try:
        _run_ralph_loop(args)
    finally:
        # Restore original signal handler
        signal.signal(signal.SIGTERM, old_sigterm_handler)


def _run_ralph_loop(args) -> None:
    """Internal implementation of the ralph loop.

    This is the actual loop logic, separated from cmd_ralph_run to allow
    for signal handler setup and cleanup.

    Args:
        args: Namespace with name attribute
    """
    import re

    # Load swarm state to verify worker exists
    state = State()
    worker = state.get_worker(args.name)

    if not worker:
        print(f"swarm: error: worker '{args.name}' not found", file=sys.stderr)
        sys.exit(1)

    # Load ralph state
    ralph_state = load_ralph_state(args.name)

    if not ralph_state:
        print(f"swarm: error: worker '{args.name}' is not a ralph worker", file=sys.stderr)
        sys.exit(1)

    # Check if ralph is in a runnable state
    if ralph_state.status not in ("running", "paused"):
        print(f"swarm: error: ralph loop for '{args.name}' has status '{ralph_state.status}'", file=sys.stderr)
        sys.exit(1)

    # If paused, just exit (user needs to resume first)
    if ralph_state.status == "paused":
        print(f"swarm: error: ralph loop for '{args.name}' is paused (use 'swarm ralph resume {args.name}' first)", file=sys.stderr)
        sys.exit(1)

    # Store worker configuration for respawning
    original_cmd = worker.cmd
    original_cwd = Path(worker.cwd)
    original_env = worker.env
    original_tags = worker.tags
    original_tmux = worker.tmux
    original_worktree = worker.worktree

    if not original_tmux:
        print(f"swarm: error: ralph requires tmux mode", file=sys.stderr)
        sys.exit(1)

    session = original_tmux.session
    socket = original_tmux.socket

    # Main ralph loop
    while True:
        # Reload ralph state (could have been paused externally)
        ralph_state = load_ralph_state(args.name)
        if not ralph_state:
            break

        # Check if paused
        if ralph_state.status == "paused":
            print(f"[ralph] {args.name}: paused, exiting loop")
            break

        # Check if we've hit max iterations
        if ralph_state.current_iteration >= ralph_state.max_iterations:
            print(f"[ralph] {args.name}: loop complete after {ralph_state.current_iteration} iterations")
            log_ralph_iteration(
                args.name,
                "DONE",
                total_iterations=ralph_state.current_iteration,
                reason="max_iterations"
            )
            ralph_state.status = "stopped"
            save_ralph_state(ralph_state)
            break

        # Read prompt file
        prompt_path = Path(ralph_state.prompt_file)
        if not prompt_path.exists():
            print(f"swarm: error: prompt file not found: {ralph_state.prompt_file}", file=sys.stderr)
            ralph_state.status = "failed"
            save_ralph_state(ralph_state)
            sys.exit(1)

        try:
            prompt_content = prompt_path.read_text()
        except Exception as e:
            print(f"swarm: error: cannot read prompt file: {ralph_state.prompt_file}", file=sys.stderr)
            ralph_state.status = "failed"
            save_ralph_state(ralph_state)
            sys.exit(1)

        # Get current worker status
        state = State()
        worker = state.get_worker(args.name)

        # Track iteration timing
        iteration_start = time.time()

        # If worker is not running, spawn a new one
        if not worker or refresh_worker_status(worker) == "stopped":
            # Increment iteration counter
            ralph_state.current_iteration += 1
            ralph_state.last_iteration_started = datetime.now().isoformat()
            save_ralph_state(ralph_state)

            print(f"[ralph] {args.name}: starting iteration {ralph_state.current_iteration}/{ralph_state.max_iterations}")
            log_ralph_iteration(
                args.name,
                "START",
                iteration=ralph_state.current_iteration,
                max_iterations=ralph_state.max_iterations
            )

            # Remove old worker from state if it exists
            if worker:
                state.remove_worker(args.name)

            # Build metadata
            metadata = {
                "ralph": True,
                "ralph_iteration": ralph_state.current_iteration,
            }

            # Spawn new worker
            try:
                worker = spawn_worker_for_ralph(
                    name=args.name,
                    cmd=original_cmd,
                    cwd=original_cwd,
                    env=original_env,
                    tags=original_tags,
                    session=session,
                    socket=socket,
                    worktree_info=original_worktree,
                    metadata=metadata
                )
                state = State()
                state.add_worker(worker)

                # Send prompt to the worker
                send_prompt_to_worker(worker, prompt_content)

            except Exception as e:
                print(f"swarm: error: failed to spawn worker: {e}", file=sys.stderr)
                ralph_state.consecutive_failures += 1
                ralph_state.total_failures += 1
                save_ralph_state(ralph_state)

                # Apply backoff
                if ralph_state.consecutive_failures >= 5:
                    print(f"[ralph] {args.name}: 5 consecutive failures, stopping loop")
                    ralph_state.status = "failed"
                    save_ralph_state(ralph_state)
                    sys.exit(1)

                backoff = min(2 ** (ralph_state.consecutive_failures - 1), 300)
                print(f"[ralph] {args.name}: spawn failed, retrying in {backoff}s (attempt {ralph_state.consecutive_failures}/5)")
                log_ralph_iteration(
                    args.name,
                    "FAIL",
                    iteration=ralph_state.current_iteration,
                    exit_code=1,
                    attempt=ralph_state.consecutive_failures,
                    backoff=backoff
                )
                time.sleep(backoff)
                continue

        # Monitor the worker
        while True:
            # Reload ralph state (could have been paused externally)
            ralph_state = load_ralph_state(args.name)
            if not ralph_state or ralph_state.status == "paused":
                print(f"[ralph] {args.name}: paused, exiting loop")
                break

            # Check worker status
            state = State()
            worker = state.get_worker(args.name)
            if not worker:
                break

            worker_status = refresh_worker_status(worker)

            if worker_status == "stopped":
                # Worker exited
                duration = format_duration(time.time() - iteration_start)
                print(f"[ralph] {args.name}: iteration {ralph_state.current_iteration} completed (exit: 0, duration: {duration})")
                log_ralph_iteration(
                    args.name,
                    "END",
                    iteration=ralph_state.current_iteration,
                    exit_code=0,
                    duration=duration
                )

                # Reset consecutive failures on success
                ralph_state.consecutive_failures = 0
                save_ralph_state(ralph_state)

                # Check for done pattern
                if ralph_state.done_pattern:
                    if check_done_pattern(worker, ralph_state.done_pattern):
                        print(f"[ralph] {args.name}: done pattern matched, stopping loop")
                        log_ralph_iteration(
                            args.name,
                            "DONE",
                            total_iterations=ralph_state.current_iteration,
                            reason="done_pattern"
                        )
                        ralph_state.status = "stopped"
                        save_ralph_state(ralph_state)
                        return

                break  # Continue to next iteration

            # Check for inactivity
            if detect_inactivity(worker, ralph_state.inactivity_timeout, ralph_state.inactivity_mode):
                print(f"[ralph] {args.name}: inactivity timeout ({ralph_state.inactivity_timeout}s, mode={ralph_state.inactivity_mode}), restarting")
                log_ralph_iteration(
                    args.name,
                    "TIMEOUT",
                    iteration=ralph_state.current_iteration,
                    timeout=ralph_state.inactivity_timeout
                )

                # Kill the worker
                kill_worker_for_ralph(worker, state)
                break  # Continue to next iteration

            # Brief sleep before next check
            time.sleep(1)

        # Check if we should exit (paused)
        ralph_state = load_ralph_state(args.name)
        if not ralph_state or ralph_state.status == "paused":
            break


if __name__ == "__main__":
    main()
