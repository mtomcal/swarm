# SWARM — Unix-Style Agent Process Manager

## Overview

`swarm` is a minimal CLI tool for spawning, tracking, and controlling agent processes via tmux. It follows the Unix philosophy: do one thing well, compose with other tools.

**What swarm does:**

- Spawn processes in tmux windows
- Optionally create git worktrees for isolation
- Send commands to running processes via tmux send-keys
- Track process state (pid, status, worktree info)
- Provide lifecycle management (kill, wait, clean)

**What swarm does NOT do:**

- Know about Beads, amail, or any other tools
- Make decisions about agent orchestration
- Parse or understand what agents are doing
- Provide supervision logic

Swarm is a sharp knife. The user composes it with other tools to build orchestration.

-----

## Installation Target

Single Python file: `swarm.py`
Zero dependencies beyond stdlib.
Executable via: `python swarm.py <command>` or `./swarm.py <command>` or symlinked as `swarm`

-----

## Commands

### `swarm spawn`

Spawn a new process, optionally in a tmux window and/or git worktree.

```bash
swarm spawn --name <name> [options] -- <command...>
```

**Required:**

- `--name <name>` — Unique identifier for this worker

**Options:**

- `--tmux` — Run in a tmux window (required for `swarm send`)
- `--session <name>` — Tmux session name (default: “swarm”)
- `--worktree` — Create a git worktree before spawning
- `--branch <name>` — Branch name for worktree (default: same as –name)
- `--worktree-dir <path>` — Parent dir for worktrees (default: `../swarm-worktrees`)
- `--tag <tag>` — Tag for filtering in `swarm ls`
- `--env KEY=VAL` — Environment variable (repeatable)
- `--cwd <path>` — Working directory (overridden by –worktree if both specified)

**Behavior:**

1. Validate name is unique (not already in state)
1. If `--worktree`:
- Detect git repo root from cwd
- Compute worktree path: `{worktree-dir}/{name}`
- Run: `git worktree add {worktree_path} -b {branch}`
- Set working directory to worktree path
1. If `--tmux`:
- Ensure session exists: `tmux has-session -t {session} || tmux new-session -d -s {session}`
- Create window: `tmux new-window -t {session} -n {name} -c {workdir}`
- Send command: `tmux send-keys -t {session}:{name} '{command}' Enter`
- PID tracking: Store the tmux window target, not a direct PID
1. If not `--tmux`:
- Spawn via `subprocess.Popen`
- Capture stdout/stderr to `~/.swarm/logs/{name}.stdout` and `.stderr`
- Store PID directly
1. Record state to `~/.swarm/state.json`

**Example:**

```bash
swarm spawn --name w1 --tmux --worktree --branch work/bd-001 -- claude
```

-----

### `swarm ls`

List all tracked workers.

```bash
swarm ls [options]
```

**Options:**

- `--format <fmt>` — Output format: `table` (default), `json`, `names`
- `--status <status>` — Filter by status: `running`, `stopped`, `all` (default: `all`)
- `--tag <tag>` — Filter by tag

**Output (table):**

```
NAME    STATUS   PID/WINDOW      STARTED   WORKTREE                  TAG
w1      running  swarm:w1        5m ago    ../swarm-worktrees/w1     pr-review
w2      running  swarm:w2        3m ago    ../swarm-worktrees/w2     pr-review
w3      stopped  -               10m ago   ../swarm-worktrees/w3     impl
```

**Output (names):**

```
w1
w2
w3
```

**Output (json):**

```json
[
  {"name": "w1", "status": "running", ...},
  ...
]
```

-----

### `swarm status`

Get status of a specific worker.

```bash
swarm status <name>
```

**Output:**

```
w1: running (tmux window swarm:w1, worktree ../swarm-worktrees/w1, uptime 5m)
```

**Exit codes:**

- 0: running
- 1: stopped/dead
- 2: not found

-----

### `swarm send`

Send text to a tmux-based worker.

```bash
swarm send <name> <text>
swarm send --all <text>
```

**Options:**

- `--no-enter` — Don’t append Enter key after text
- `--all` — Send to all running tmux workers

**Behavior:**

```bash
tmux send-keys -t {session}:{name} "{text}" Enter
```

**Examples:**

```bash
swarm send w1 "implement the auth flow"
swarm send w1 "/review"
swarm send w1 "/pr --title 'feat: auth'"
swarm send --all "check your amail inbox"
```

**Errors:**

- If worker is not tmux-based, exit with error
- If worker is not running, exit with error

-----

### `swarm interrupt`

Send Ctrl-C to a worker.

```bash
swarm interrupt <name>
swarm interrupt --all
```

**Behavior:**

```bash
tmux send-keys -t {session}:{name} C-c
```

-----

### `swarm eof`

Send Ctrl-D (EOF) to a worker. This typically exits interactive programs like claude.

```bash
swarm eof <name>
```

**Behavior:**

```bash
tmux send-keys -t {session}:{name} C-d
```

-----

### `swarm attach`

Attach to a worker’s tmux window.

```bash
swarm attach <name>
```

**Behavior:**

```bash
tmux select-window -t {session}:{name}
tmux attach-session -t {session}
```

-----

### `swarm logs`

Capture output from a worker.

```bash
swarm logs <name> [options]
```

**Options:**

- `--history` — Include scrollback buffer (default: visible pane only)
- `--lines <n>` — Number of scrollback lines (default: 1000)
- `--follow` — Continuously poll and display (like tail -f)

**Behavior (tmux workers):**

```bash
# Default
tmux capture-pane -t {session}:{name} -p

# With history
tmux capture-pane -t {session}:{name} -p -S -{lines}

# Follow (poll every 1s)
watch -n1 "tmux capture-pane -t {session}:{name} -p | tail -30"
```

**Behavior (non-tmux workers):**

```bash
cat ~/.swarm/logs/{name}.stdout
# or
tail -f ~/.swarm/logs/{name}.stdout
```

-----

### `swarm kill`

Kill a worker.

```bash
swarm kill <name> [options]
swarm kill --all [options]
```

**Options:**

- `--rm-worktree` — Also remove the git worktree
- `--all` — Kill all workers

**Behavior:**

1. If tmux: `tmux kill-window -t {session}:{name}`
1. If not tmux: `kill {pid}` (SIGTERM, then SIGKILL after 5s)
1. Update state to `stopped`
1. If `--rm-worktree` and worker has worktree:
- `git worktree remove {worktree_path} --force`

-----

### `swarm wait`

Wait for worker(s) to finish.

```bash
swarm wait <name>
swarm wait --all [options]
```

**Options:**

- `--timeout <seconds>` — Max wait time (default: infinite)
- `--all` — Wait for all workers

**Behavior (tmux):**

- Poll `tmux list-windows -t {session}` until window disappears
- Return exit code 0 when done

**Behavior (non-tmux):**

- `waitpid()` or poll `/proc/{pid}`

**Output:**

```
w1: exited
w2: exited
w3: still running (timeout)
```

-----

### `swarm clean`

Clean up dead workers and their worktrees.

```bash
swarm clean <name> [options]
swarm clean --all [options]
```

**Options:**

- `--rm-worktree` — Remove git worktree (default: true for clean)
- `--all` — Clean all stopped workers

**Behavior:**

1. Verify worker is stopped
1. If worktree exists: `git worktree remove {path} --force`
1. Remove from state.json
1. Remove log files if they exist

-----

### `swarm respawn`

Respawn a dead worker with its original command.

```bash
swarm respawn <name> [options]
```

**Options:**

- `--clean-first` — Run clean before respawn (removes old worktree)

**Behavior:**

1. Read original spawn config from state
1. If `--clean-first`, clean up old worktree
1. Kill if still somehow running
1. Spawn with same options

-----

## State File

Location: `~/.swarm/state.json`

```json
{
  "workers": [
    {
      "name": "w1",
      "status": "running",
      "cmd": ["claude"],
      "started": "2024-01-10T14:30:00Z",
      "cwd": "/home/user/code/myrepo",
      "env": {"FOO": "bar"},
      "tags": ["pr-review"],
      "tmux": {
        "session": "swarm",
        "window": "w1"
      },
      "worktree": {
        "path": "/home/user/code/swarm-worktrees/w1",
        "branch": "work/bd-001",
        "base_repo": "/home/user/code/myrepo"
      },
      "pid": null
    },
    {
      "name": "w2",
      "status": "running",
      "cmd": ["python", "agent.py"],
      "started": "2024-01-10T14:35:00Z",
      "cwd": "/home/user/code/myrepo",
      "env": {},
      "tags": [],
      "tmux": null,
      "worktree": null,
      "pid": 12345
    }
  ]
}
```

-----

## Log Directory

Location: `~/.swarm/logs/`

Only used for non-tmux workers:

```
~/.swarm/logs/
├── w2.stdout
└── w2.stderr
```

Tmux workers use `tmux capture-pane` instead.

-----

## Helper Functions Needed

### Git Operations

```python
def get_git_root() -> Path:
    """Get root of current git repo."""
    result = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True)
    if result.returncode != 0:
        raise Error("Not in a git repository")
    return Path(result.stdout.strip())

def create_worktree(path: Path, branch: str) -> None:
    """Create a git worktree."""
    subprocess.run(["git", "worktree", "add", str(path), "-b", branch], check=True)

def remove_worktree(path: Path) -> None:
    """Remove a git worktree."""
    subprocess.run(["git", "worktree", "remove", str(path), "--force"], check=True)
```

### Tmux Operations

```python
def ensure_tmux_session(session: str) -> None:
    """Create tmux session if it doesn't exist."""
    result = subprocess.run(["tmux", "has-session", "-t", session], capture_output=True)
    if result.returncode != 0:
        subprocess.run(["tmux", "new-session", "-d", "-s", session], check=True)

def create_tmux_window(session: str, window: str, cwd: Path, cmd: list[str]) -> None:
    """Create a tmux window and run command."""
    # Create window
    subprocess.run([
        "tmux", "new-window",
        "-t", session,
        "-n", window,
        "-c", str(cwd)
    ], check=True)
    # Send command
    cmd_str = " ".join(shlex.quote(c) for c in cmd)
    subprocess.run([
        "tmux", "send-keys",
        "-t", f"{session}:{window}",
        cmd_str, "Enter"
    ], check=True)

def tmux_send(session: str, window: str, text: str, enter: bool = True) -> None:
    """Send text to a tmux window."""
    args = ["tmux", "send-keys", "-t", f"{session}:{window}", text]
    if enter:
        args.append("Enter")
    subprocess.run(args, check=True)

def tmux_window_exists(session: str, window: str) -> bool:
    """Check if a tmux window exists."""
    result = subprocess.run(
        ["tmux", "list-windows", "-t", session, "-F", "#{window_name}"],
        capture_output=True, text=True
    )
    return window in result.stdout.splitlines()

def tmux_capture_pane(session: str, window: str, history_lines: int = 0) -> str:
    """Capture contents of a tmux pane."""
    args = ["tmux", "capture-pane", "-t", f"{session}:{window}", "-p"]
    if history_lines > 0:
        args.extend(["-S", f"-{history_lines}"])
    result = subprocess.run(args, capture_output=True, text=True, check=True)
    return result.stdout
```

### Process Operations

```python
def spawn_process(cmd: list[str], cwd: Path, env: dict, log_prefix: Path) -> int:
    """Spawn a background process, return PID."""
    stdout = open(f"{log_prefix}.stdout", "w")
    stderr = open(f"{log_prefix}.stderr", "w")
    proc = subprocess.Popen(
        cmd,
        cwd=cwd,
        env={**os.environ, **env},
        stdout=stdout,
        stderr=stderr,
        start_new_session=True
    )
    return proc.pid

def process_alive(pid: int) -> bool:
    """Check if a process is alive."""
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False
```

-----

## CLI Structure (using argparse)

```python
def main():
    parser = argparse.ArgumentParser(prog="swarm", description="Unix-style agent process manager")
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    # spawn
    spawn_p = subparsers.add_parser("spawn", help="Spawn a new worker")
    spawn_p.add_argument("--name", required=True)
    spawn_p.add_argument("--tmux", action="store_true")
    spawn_p.add_argument("--session", default="swarm")
    spawn_p.add_argument("--worktree", action="store_true")
    spawn_p.add_argument("--branch")
    spawn_p.add_argument("--worktree-dir", default="../swarm-worktrees")
    spawn_p.add_argument("--tag", action="append", default=[])
    spawn_p.add_argument("--env", action="append", default=[])
    spawn_p.add_argument("--cwd")
    spawn_p.add_argument("cmd", nargs=argparse.REMAINDER)
    
    # ls
    ls_p = subparsers.add_parser("ls", help="List workers")
    ls_p.add_argument("--format", choices=["table", "json", "names"], default="table")
    ls_p.add_argument("--status", choices=["running", "stopped", "all"], default="all")
    ls_p.add_argument("--tag")
    
    # status
    status_p = subparsers.add_parser("status", help="Get worker status")
    status_p.add_argument("name")
    
    # send
    send_p = subparsers.add_parser("send", help="Send text to worker")
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
    kill_p = subparsers.add_parser("kill", help="Kill worker")
    kill_p.add_argument("name", nargs="?")
    kill_p.add_argument("--rm-worktree", action="store_true")
    kill_p.add_argument("--all", action="store_true")
    
    # wait
    wait_p = subparsers.add_parser("wait", help="Wait for worker to finish")
    wait_p.add_argument("name", nargs="?")
    wait_p.add_argument("--timeout", type=int)
    wait_p.add_argument("--all", action="store_true")
    
    # clean
    clean_p = subparsers.add_parser("clean", help="Clean up dead workers")
    clean_p.add_argument("name", nargs="?")
    clean_p.add_argument("--rm-worktree", action="store_true", default=True)
    clean_p.add_argument("--all", action="store_true")
    
    # respawn
    respawn_p = subparsers.add_parser("respawn", help="Respawn a dead worker")
    respawn_p.add_argument("name")
    respawn_p.add_argument("--clean-first", action="store_true")
    
    args = parser.parse_args()
    # dispatch to command handlers...
```

-----

## Error Handling

- All errors print to stderr and exit non-zero
- Use clear error messages: `swarm: error: worker 'foo' not found`
- Validate state consistency on load (check if tmux windows / PIDs still exist)

-----

## Status Refresh Logic

When loading state, refresh actual status:

```python
def refresh_worker_status(worker: dict) -> str:
    """Check actual status of a worker."""
    if worker["tmux"]:
        if tmux_window_exists(worker["tmux"]["session"], worker["tmux"]["window"]):
            return "running"
        else:
            return "stopped"
    elif worker["pid"]:
        if process_alive(worker["pid"]):
            return "running"
        else:
            return "stopped"
    return "unknown"
```

-----

## Usage Examples

### Basic: Spawn claude workers with worktrees

```bash
# Spawn three workers
swarm spawn --name w1 --tmux --worktree --branch work/task-1 -- claude
swarm spawn --name w2 --tmux --worktree --branch work/task-2 -- claude
swarm spawn --name w3 --tmux --worktree --branch work/task-3 -- claude

# Send them instructions
swarm send w1 "Implement the login flow. Update beads as you go."
swarm send w2 "Write tests for the auth module."
swarm send w3 "Review the code in src/api/ and file issues."

# Check status
swarm ls

# Attach to watch one work
swarm attach w1

# Send slash commands
swarm send w1 "/review"
swarm send w1 "/pr --title 'feat: login flow'"

# Kill when done
swarm kill --all --rm-worktree
```

### Non-tmux: Background processes

```bash
# Spawn a background script
swarm spawn --name worker1 -- python my_agent.py --task foo

# Check logs
swarm logs worker1 --follow

# Wait for completion
swarm wait worker1
echo "Exit code: $?"
```

### Supervisor script composition

```bash
#!/bin/bash
# supervisor.sh - composes swarm with bd (beads) and amail

for bead in $(bd list --status ready --format ids | head -3); do
    swarm spawn --name "w-$bead" --tmux --worktree --branch "work/$bead" -- claude
    sleep 2
    swarm send "w-$bead" "Work on $bead. Check bd show $bead for details. Send status to supervisor via amail."
done

while [ "$(swarm ls --status running --format names | wc -l)" -gt 0 ]; do
    # Check for messages
    amail inbox --agent supervisor
    
    # Check for stale workers (would query beads here)
    sleep 60
done

swarm clean --all
```

-----

## Testing Checklist

1. [ ] `swarm spawn --name test -- echo hello` works (non-tmux)
1. [ ] `swarm spawn --name test --tmux -- bash` works (tmux)
1. [ ] `swarm ls` shows the worker
1. [ ] `swarm send test "echo foo"` sends to tmux
1. [ ] `swarm logs test` captures output
1. [ ] `swarm kill test` kills the worker
1. [ ] `swarm spawn --worktree` creates worktree
1. [ ] `swarm kill --rm-worktree` removes worktree
1. [ ] `swarm wait test` blocks until exit
1. [ ] `swarm clean --all` cleans up everything
1. [ ] State persists across swarm invocations
1. [ ] Status refresh detects dead processes correctly

-----

## Implementation Notes

- Use `pathlib.Path` throughout
- Use `json` for state (not pickle, not yaml)
- Use `argparse` (stdlib, no dependencies)
- Use `subprocess.run` for simple commands, `Popen` for background
- Use `shlex.quote` when building shell commands
- Handle SIGTERM gracefully if possible
- Make sure `--` separator works for arbitrary commands

-----

## Out of Scope (Do Not Implement)

- Web UI
- Daemon mode
- Remote workers
- Integration with beads/amail (user composes these)
- Automatic restart/supervision
- Resource limits (cgroups, etc.)
- Windows support (tmux doesn’t exist there)`
