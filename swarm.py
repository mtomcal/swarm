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
import yaml
from contextlib import contextmanager
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional


# Constants
# SWARM_DIR can be overridden via environment variable for testing isolation
SWARM_DIR = Path(os.environ.get("SWARM_DIR", str(Path.home() / ".swarm")))
STATE_FILE = SWARM_DIR / "state.json"
STATE_LOCK_FILE = SWARM_DIR / "state.lock"
LOGS_DIR = SWARM_DIR / "logs"
RALPH_DIR = SWARM_DIR / "ralph"  # Ralph loop state directory
HEARTBEATS_DIR = SWARM_DIR / "heartbeats"  # Heartbeat state directory
WORKFLOWS_DIR = SWARM_DIR / "workflows"  # Workflow state directory

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

# CLI Help Text Constants
# Defined at module level for testability and coverage

ROOT_HELP_DESCRIPTION = """\
Spawn, track, and control AI agent processes with Unix-style simplicity.

Swarm manages parallel agents in isolated git worktrees via tmux, enabling
concurrent development without merge conflicts. Each worker gets its own
branch and directory, automatically cleaned up when done.

Key Features:
  - Worktree isolation: Each agent works in its own git branch/directory
  - Tmux integration: Attach, send commands, view logs in real-time
  - Ralph mode: Autonomous multi-iteration loops across context windows
  - Process control: Start, stop, pause, resume workers at will
"""

ROOT_HELP_EPILOG = """\
Quick Start:
  1. Spawn a worker:     swarm spawn --name my-agent --tmux --worktree -- claude --dangerously-skip-permissions
  2. Check status:       swarm ls
  3. Send a message:     swarm send my-agent "implement feature X"
  4. View output:        swarm logs my-agent --follow
  5. Clean up:           swarm kill my-agent --rm-worktree

Command Groups:
  Worker Lifecycle:
    spawn               Create a new worker process
    kill                Stop a worker (optionally remove worktree)
    clean               Remove stopped workers and their worktrees
    respawn             Restart a stopped worker with same config

  Monitoring:
    ls                  List all workers and their status
    status              Show detailed status of a single worker
    logs                View worker output (supports --follow)
    attach              Attach to worker's tmux window

  Interaction:
    send                Send text/commands to a running worker
    interrupt           Send Ctrl-C to interrupt current operation
    eof                 Send Ctrl-D (end of file)
    wait                Block until worker(s) complete

  Autonomous Mode:
    ralph spawn         Start autonomous multi-iteration loop
    ralph status        Check loop progress (iterations, failures)
    ralph pause/resume  Control loop execution

  Setup:
    init                Add swarm instructions to CLAUDE.md

Examples:
  # Spawn parallel workers for different features
  swarm spawn --name auth --tmux --worktree -- claude --dangerously-skip-permissions
  swarm spawn --name api --tmux --worktree -- claude --dangerously-skip-permissions

  # Autonomous overnight work with ralph
  swarm ralph spawn --name dev --prompt-file PROMPT.md --max-iterations 50 -- claude --dangerously-skip-permissions

  # Broadcast to all workers
  swarm send --all "wrap up and commit your changes"

State: ~/.swarm/state.json    Logs: ~/.swarm/logs/
"""

# Spawn command help
SPAWN_HELP_DESCRIPTION = """\
Create a new worker to run a command as a managed process.

Workers can run either as background processes (default) or in tmux windows
(--tmux). For AI agent workflows, tmux mode enables interactive features like
sending messages, viewing live output, and attaching to the terminal.

Git worktree isolation (--worktree) creates a dedicated branch and directory
for each worker, enabling parallel development without merge conflicts. Each
agent works independently, and changes can be merged via pull requests.
"""

SPAWN_HELP_EPILOG = """\
Examples:
  # Basic: spawn an agent in tmux (autonomous mode)
  swarm spawn --name worker1 --tmux -- claude --dangerously-skip-permissions

  # With git worktree isolation (recommended for parallel work)
  swarm spawn --name feature-auth --tmux --worktree -- claude --dangerously-skip-permissions

  # Custom branch name (worktree dir still uses --name)
  swarm spawn --name w1 --tmux --worktree --branch feature/auth -- claude --dangerously-skip-permissions

  # With environment variables
  swarm spawn --name api-dev --tmux --worktree \\
    --env API_KEY=test-key --env DEBUG=1 -- claude --dangerously-skip-permissions

  # With tags for filtering
  swarm spawn --name backend --tmux --worktree \\
    --tag team-a --tag priority -- claude --dangerously-skip-permissions

  # Wait for agent to be ready before returning
  swarm spawn --name worker1 --tmux --ready-wait -- claude --dangerously-skip-permissions

  # With custom ready timeout (default: 120s)
  swarm spawn --name worker1 --tmux --ready-wait --ready-timeout 60 -- claude --dangerously-skip-permissions

  # Background process mode (no tmux)
  swarm spawn --name batch-job -- python process_data.py

Common Patterns:
  Parallel Feature Development:
    swarm spawn --name auth --tmux --worktree -- claude --dangerously-skip-permissions
    swarm spawn --name api --tmux --worktree -- claude --dangerously-skip-permissions
    swarm spawn --name ui --tmux --worktree -- claude --dangerously-skip-permissions
    swarm ls  # see all workers

  Scripted Orchestration:
    swarm spawn --name worker --tmux --ready-wait -- claude --dangerously-skip-permissions
    swarm send worker "implement the login feature"
    swarm wait worker

Tips:
  - Use --tmux for AI agents (enables send, logs, attach commands)
  - Use --worktree when running multiple agents on the same repo
  - Use --ready-wait in scripts that send commands after spawn
  - Tags help organize workers: filter with 'swarm ls --tag <tag>'

Security Note:
  The --dangerously-skip-permissions flag is required for autonomous operation.
  Consider using Claude's native sandbox (/sandbox) or Docker Sandboxes for
  isolation. See README.md for sandboxing options.

See Also:
  swarm ls --help        List workers
  swarm send --help      Send commands to workers
  swarm kill --help      Stop workers
  swarm ralph --help     Autonomous looping mode
"""

# ls command help
LS_HELP_DESCRIPTION = """\
List all registered workers with their current status.

Displays worker name, status (running/stopped), process or tmux info, start
time, worktree path, and tags. Status is refreshed on each call by checking
the actual tmux window or process state.
"""

LS_HELP_EPILOG = """\
Output Formats:
  table   Aligned columns with header (default)
  json    Full worker details as JSON array
  names   Worker names only, one per line (for scripting)

Table Columns:
  NAME        Worker identifier
  STATUS      running or stopped (live-checked)
  PID/WINDOW  Tmux session:window or process PID
  STARTED     Relative time (e.g., 5s, 2m, 1h, 3d)
  WORKTREE    Git worktree path or - if none
  TAG         Comma-separated tags or - if none

Examples:
  # List all workers
  swarm ls

  # Show only running workers
  swarm ls --status running

  # Filter by tag
  swarm ls --tag team-a

  # Combine filters
  swarm ls --status running --tag backend

  # JSON output for scripting
  swarm ls --format json

  # Names only (useful for piping)
  swarm ls --format names | xargs -I {} swarm status {}

  # Count running workers
  swarm ls --status running --format names | wc -l

See Also:
  swarm status --help    Detailed info for single worker
  swarm spawn --help     Create new workers
  swarm kill --help      Stop workers
"""

# Status command help
STATUS_HELP_DESCRIPTION = """\
Show detailed status information for a single worker.

Displays the worker's current state (running/stopped) along with execution
context: tmux session and window (for tmux workers), process ID (for background
workers), worktree path (if using git isolation), and uptime since spawn.

Exit Codes:
  0  Worker is running
  1  Worker is stopped
  2  Worker not found
"""

STATUS_HELP_EPILOG = """\
Output Format:
  <name>: <status> (<context>, uptime <duration>)

  Where:
    status    running or stopped (live-checked against tmux/process)
    context   tmux window (e.g., "tmux window swarm-abc:feature1")
              or process ID (e.g., "pid 12345")
              plus worktree path if applicable
    uptime    Time since spawn (e.g., 5s, 2m, 1h, 3d)

Examples:
  # Check if a worker is running
  swarm status my-worker

  # Use in a script with exit code
  if swarm status worker1 >/dev/null 2>&1; then
    echo "Worker is running"
  else
    echo "Worker is not running"
  fi

  # Check all workers in a loop
  swarm ls --format names | while read name; do
    swarm status "$name"
  done

  # Get status with full output
  swarm status feature-auth
  # Output: feature-auth: running (tmux window swarm-abc:feature-auth, worktree /code-worktrees/feature-auth, uptime 2h)

See Also:
  swarm ls --help        List all workers with status
  swarm logs --help      View worker output
  swarm attach --help    Attach to worker's tmux window
"""

# Send command help
SEND_HELP_DESCRIPTION = """\
Send text input to tmux-based workers.

Transmits text to running workers via tmux send-keys, enabling orchestration
scripts to send prompts, commands, or interventions to agent CLIs. Only works
with workers spawned using --tmux (not background process workers).

By default, sends the text followed by Enter. Use --no-enter to send text
without submitting it (useful for partial input or special characters).
"""

SEND_HELP_EPILOG = """\
Examples:
  # Send a prompt to a single worker
  swarm send my-worker "implement the login feature"

  # Send to worker without pressing Enter (partial input)
  swarm send my-worker "partial text" --no-enter

  # Broadcast to all running tmux workers
  swarm send --all "please wrap up and commit your changes"

  # Send follow-up instructions
  swarm send feature-auth "skip the OAuth approach, use JWT instead"

  # Send empty line (just presses Enter)
  swarm send my-worker ""

Intervention Patterns:
  Redirect agent mid-task:
    swarm send dev "stop working on X, instead do Y"

  Request status update:
    swarm send dev "give me a brief status update on progress"

  Ask agent to wrap up:
    swarm send dev "please commit your current changes and exit"

  Course correction during review:
    swarm send --all "remember to run tests before committing"

Tips:
  - Text is sent literally; special characters like quotes work correctly
  - Newlines in text are sent as-is (may cause multi-line input)
  - Use --no-enter when building up input incrementally
  - Broadcast (--all) silently skips non-running and non-tmux workers
  - Check worker is running first: swarm status <name>

See Also:
  swarm interrupt --help   Send Ctrl-C to cancel current operation
  swarm eof --help         Send Ctrl-D (EOF signal)
  swarm attach --help      Attach to worker's tmux window for direct interaction
  swarm logs --help        View what the worker is outputting
"""

# Kill command help
KILL_HELP_DESCRIPTION = """\
Stop running workers and optionally clean up their worktrees.

Terminates worker processes by killing tmux windows (for tmux workers) or
sending SIGTERM/SIGKILL signals (for process workers). Workers are marked
as "stopped" in state but not removed - use 'swarm clean' to fully remove.

For tmux workers, the window is destroyed and the process receives SIGHUP.
For process workers, SIGTERM is sent first with a 5-second grace period,
followed by SIGKILL if the process doesn't terminate.
"""

KILL_HELP_EPILOG = """\
Examples:
  # Kill a single worker
  swarm kill my-worker

  # Kill worker and remove its git worktree
  swarm kill feature-auth --rm-worktree

  # Force remove worktree with uncommitted changes (DATA LOSS!)
  swarm kill dirty-worker --rm-worktree --force-dirty

  # Kill all workers at once
  swarm kill --all

  # Kill all workers and remove all worktrees
  swarm kill --all --rm-worktree

Warnings:
  - --force-dirty will DELETE UNCOMMITTED CHANGES permanently
  - Killing a worker does NOT remove it from state (use 'swarm clean')
  - Worktree removal without --force-dirty fails if changes exist
  - Empty tmux sessions are automatically destroyed after kill

Recovery Commands:
  # If worktree removal failed, check uncommitted changes:
  cd /path/to/worktree && git status

  # Manually commit and push before removing:
  cd /path/to/worktree && git add -A && git commit -m "save work"

  # Then clean up the stopped worker:
  swarm clean <name> --rm-worktree

  # Check remaining tmux sessions:
  tmux list-sessions

  # If state shows worker as running but it's dead:
  swarm status <name>   # Refreshes status
  swarm clean <name>    # Removes from state

Tips:
  - Always check 'swarm status <name>' before killing to see worktree path
  - Use 'swarm ls' to see all workers and their states
  - Workers with worktrees show their path in status output
  - After kill, worker remains in 'swarm ls' with status "stopped"
  - Use 'swarm respawn <name>' to restart a stopped worker

See Also:
  swarm clean --help     Remove stopped workers from state
  swarm respawn --help   Restart a stopped worker
  swarm status --help    Check worker details before killing
  swarm ls --help        List all workers and their states
"""

# Logs command help
LOGS_HELP_DESCRIPTION = """\
View worker output from tmux panes or log files.

For tmux workers, captures output directly from the tmux pane. By default,
shows only the visible pane content. Use --history to include scrollback
buffer (up to --lines lines). Use --follow for live tailing.

For background (non-tmux) workers, reads from log files stored in
~/.swarm/logs/<name>.stdout.log. Use --follow to tail the log file.
"""

LOGS_HELP_EPILOG = r"""Log Storage:
  Tmux workers:     Output captured directly from tmux pane
  Non-tmux workers: ~/.swarm/logs/<name>.stdout.log

Examples:
  # View current visible output for a tmux worker
  swarm logs my-worker

  # Include scrollback history (last 1000 lines)
  swarm logs my-worker --history

  # Include more scrollback (last 5000 lines)
  swarm logs my-worker --history --lines 5000

  # Follow output in real-time (Ctrl-C to stop)
  swarm logs my-worker --follow

  # Follow with scrollback history included
  swarm logs my-worker --follow --history

  # Pipe output to search for patterns
  swarm logs my-worker --history | grep "error"

  # Save output to file for analysis
  swarm logs my-worker --history > worker-output.txt

Common Patterns:
  Check what an agent is currently doing:
    swarm logs <name>

  Search for errors in worker output:
    swarm logs <name> --history | grep -i "error\|failed\|exception"

  Monitor a long-running task:
    swarm logs <name> --follow

  Get full output after completion:
    swarm logs <name> --history --lines 10000

Tips:
  - --follow mode for tmux workers refreshes every 1 second
  - --follow mode for non-tmux workers uses 'tail -f'
  - Press Ctrl-C to exit --follow mode
  - Increase --lines if you need more history (default: 1000)
  - --history only affects tmux workers (non-tmux reads full log file)

See Also:
  swarm status --help    Check if worker is still running
  swarm attach --help    Attach to tmux window for direct interaction
  swarm send --help      Send commands to the worker
"""

# Wait command help
WAIT_HELP_DESCRIPTION = """\
Wait for workers to finish and report their exit status.

Blocks until the specified worker(s) stop running, polling status every second.
Useful in scripts for sequencing operations, running post-completion tasks, or
coordinating multiple workers. Exit codes allow conditional logic based on
completion vs timeout.

Exit Codes:
  0 - All workers finished successfully (exited/stopped)
  1 - Timeout reached with workers still running, or error occurred
"""

WAIT_HELP_EPILOG = """\
Examples:
  # Wait for a single worker to finish
  swarm wait my-worker

  # Wait with a timeout (fail if not done in 5 minutes)
  swarm wait my-worker --timeout 300

  # Wait for all running workers to finish
  swarm wait --all

  # Wait for all workers with timeout
  swarm wait --all --timeout 600

  # Use exit code in scripts for conditional logic
  swarm wait my-worker --timeout 120 && echo "Done!" || echo "Timed out"

  # Chain operations: wait then clean up
  swarm wait my-worker && swarm clean my-worker --rm-worktree

Common Patterns:
  Wait for build to complete before testing:
    swarm spawn --name build --tmux -- make build
    swarm wait build --timeout 300
    swarm spawn --name test --tmux -- make test

  Coordinate parallel workers:
    swarm spawn --name worker-1 --tmux --worktree -- claude
    swarm spawn --name worker-2 --tmux --worktree -- claude
    swarm wait --all --timeout 1800

  Script with timeout handling:
    if swarm wait my-worker --timeout 600; then
      echo "Worker completed successfully"
      swarm clean my-worker --rm-worktree
    else
      echo "Worker timed out or failed"
      swarm logs my-worker --history
    fi

Tips:
  - Use --timeout to prevent infinite waits on stuck workers
  - Exit code 1 on timeout lets scripts detect and handle failures
  - Combine with 'swarm logs' to check what happened after completion
  - Workers print "<name>: exited" as they finish
  - Status is polled every 1 second

See Also:
  swarm status --help    Check current worker state
  swarm logs --help      View worker output after completion
  swarm clean --help     Remove stopped workers from state
  swarm kill --help      Forcefully stop workers that are stuck
"""

CLEAN_HELP_DESCRIPTION = """\
Remove stopped workers from swarm state and clean up associated resources.

Removes worker entries from ~/.swarm/state.json and deletes associated log files
(~/.swarm/logs/<name>.{stdout,stderr}.log). By default, git worktrees are also
removed unless they have uncommitted changes. Only stopped workers can be cleaned;
running workers must be killed first with 'swarm kill'.

What Gets Cleaned:
  - Worker entry in state file (~/.swarm/state.json)
  - Log files (~/.swarm/logs/<name>.stdout.log, <name>.stderr.log)
  - Git worktree directory (with --rm-worktree, default: enabled)
  - Empty tmux sessions (automatically destroyed if no other workers)
"""

CLEAN_HELP_EPILOG = """\
Examples:
  # Clean a single stopped worker
  swarm clean my-worker

  # Clean all stopped workers at once
  swarm clean --all

  # Clean worker but preserve its worktree
  swarm clean my-worker --no-rm-worktree

  # Force clean worktree with uncommitted changes (DATA LOSS!)
  swarm clean dirty-worker --force-dirty

  # Clean all stopped workers and force-remove dirty worktrees
  swarm clean --all --force-dirty

Warnings:
  - Cannot clean running workers - use 'swarm kill' first
  - --force-dirty will DELETE UNCOMMITTED CHANGES permanently
  - Without --force-dirty, worktrees with uncommitted changes are preserved
  - Log files are deleted without confirmation
  - This action cannot be undone

Recovery Commands:
  # If worktree removal failed, check uncommitted changes:
  cd /path/to/worktree && git status

  # Manually commit and push before cleaning:
  cd /path/to/worktree && git add -A && git commit -m "save work" && git push

  # Then clean up the worker:
  swarm clean <name>

  # To see worktree path before cleaning:
  swarm status <name>

  # List all worktrees in the repo:
  git worktree list

Common Patterns:
  Kill then clean (typical workflow):
    swarm kill my-worker && swarm clean my-worker

  Wait for completion then clean:
    swarm wait my-worker && swarm clean my-worker

  Clean up all finished workers:
    swarm clean --all

See Also:
  swarm kill --help      Stop running workers
  swarm respawn --help   Restart a stopped worker (instead of cleaning)
  swarm status --help    Check worker state and worktree path
  swarm ls --help        List all workers and their states
"""

# Respawn command help
RESPAWN_HELP_DESCRIPTION = """\
Restart a stopped or dead worker using its original configuration.

Re-spawns a worker preserving its original command, environment variables, tags,
working directory, and worktree settings. If the worker is still running, it will
be killed first. Useful for recovering crashed workers or restarting completed
workers for additional iterations.

What Gets Preserved:
  - Full command with all arguments
  - Environment variables (--env values from original spawn)
  - Tags (--tag values from original spawn)
  - Tmux session (new window created in same session)
  - Worktree configuration (path, branch, base repo)

What Gets Reset:
  - Worker status (set to "running")
  - Started timestamp (current time)
  - Process ID (new PID assigned)
"""

RESPAWN_HELP_EPILOG = """\
Examples:
  # Respawn a stopped worker with original configuration
  swarm respawn my-worker

  # Respawn and recreate worktree from scratch (fresh checkout)
  swarm respawn feature-auth --clean-first

  # Force recreate worktree even with uncommitted changes (DATA LOSS!)
  swarm respawn dirty-worker --clean-first --force-dirty

Common Patterns:
  Restart a crashed agent:
    swarm status my-worker        # Check if really stopped
    swarm respawn my-worker       # Restart with original config

  Fresh restart with clean worktree:
    swarm respawn feature-auth --clean-first

  Iterate on a task (multiple runs with same config):
    # First run
    swarm spawn --name task-worker --tmux --worktree -- claude
    # ... worker completes or crashes ...
    # Restart for another iteration
    swarm respawn task-worker

Worktree Behavior:
  - Without --clean-first: Reuses existing worktree (preserves local changes)
  - With --clean-first: Removes and recreates worktree (fresh checkout)
  - If worktree was deleted: Automatically recreated at original path

Warnings:
  - --force-dirty will DELETE UNCOMMITTED CHANGES permanently
  - If worker is running, it will be killed before respawn
  - Original worker is removed from state before new one is created
  - If respawn fails midway, worker may be removed from state

Recovery Commands:
  # If respawn fails, re-spawn manually:
  swarm spawn --name <name> --tmux --worktree -- <original-command>

  # Check worktree status if unsure about changes:
  cd /path/to/worktree && git status

  # List all worktrees to find paths:
  git worktree list

See Also:
  swarm spawn --help     Create new workers
  swarm kill --help      Stop running workers
  swarm clean --help     Remove stopped workers from state
  swarm status --help    Check worker details before respawn
"""

# Interrupt command help
INTERRUPT_HELP_DESCRIPTION = """\
Send Ctrl-C (interrupt signal) to a tmux worker to stop a running command.

Sends the interrupt signal (SIGINT) to the process running in a worker's tmux
window. This is equivalent to pressing Ctrl-C in the terminal. Useful for
stopping long-running commands, canceling agent operations, or recovering
from stuck states without killing the entire worker.

The worker remains running after interrupt - only the currently executing
command receives the signal. The agent or shell will typically return to
its prompt, ready for new input.
"""

INTERRUPT_HELP_EPILOG = """\
Examples:
  # Interrupt a single worker
  swarm interrupt my-worker

  # Interrupt all running tmux workers
  swarm interrupt --all

  # Stop a stuck agent and send new instructions
  swarm interrupt my-agent
  swarm send my-agent "Let's try a different approach."

Use Cases:
  Stop a long-running build or test:
    swarm interrupt build-worker

  Cancel an agent's current task without killing it:
    swarm interrupt my-agent

  Emergency stop all agents:
    swarm interrupt --all

  Recover from stuck state:
    swarm interrupt stuck-worker
    swarm logs stuck-worker           # Check what happened
    swarm send stuck-worker "continue"

Behavior Notes:
  - Only works on tmux workers (not background process workers)
  - Worker must be in "running" status
  - --all silently skips non-tmux and non-running workers
  - Multiple interrupts may be needed for some commands
  - Does NOT kill the worker, just sends Ctrl-C

If Interrupt Doesn't Work:
  Some processes ignore SIGINT. Options:
  1. Send interrupt again: swarm interrupt <name>
  2. Send EOF (Ctrl-D): swarm eof <name>
  3. Kill the worker: swarm kill <name>

See Also:
  swarm eof --help        Send Ctrl-D (EOF) to worker
  swarm send --help       Send text input to worker
  swarm kill --help       Forcefully stop worker
  swarm logs --help       View worker output
"""

EOF_HELP_DESCRIPTION = """\
Send Ctrl-D (EOF/end-of-file) to a tmux worker to signal input completion.

Sends the end-of-file signal (Ctrl-D) to the process running in a worker's tmux
window. This is equivalent to pressing Ctrl-D in the terminal. Commonly used to:
- Signal end of input to programs reading from stdin
- Close interactive shells or REPL sessions
- Exit applications waiting for user input

Unlike interrupt (Ctrl-C), EOF signals completion rather than cancellation.
This can cause shells to exit entirely, so use with caution. The worker's
status will change to "stopped" if the shell exits.
"""

EOF_HELP_EPILOG = """\
Examples:
  # Send EOF to a worker
  swarm eof my-worker

  # Signal end of input to an agent waiting for stdin
  swarm eof data-processor

  # Exit an interactive shell session
  swarm eof shell-worker

Use Cases:
  Signal end of piped input:
    swarm send my-worker "line 1"
    swarm send my-worker "line 2"
    swarm eof my-worker           # Signal no more input

  Exit an interactive Python/Node REPL:
    swarm eof repl-worker         # Exits the REPL cleanly

  Close a shell session gracefully:
    swarm eof shell-worker        # Like typing 'exit'

Behavior Notes:
  - Only works on tmux workers (not background process workers)
  - Worker must be in "running" status
  - May cause the worker to exit if it closes the shell
  - Unlike interrupt, EOF does NOT support --all flag (intentional)
  - Some programs require multiple Ctrl-D to exit

If Worker Exits Unexpectedly:
  EOF can cause shells to exit. If this was unintended:
  1. Check worker status: swarm status <name>
  2. Respawn if needed: swarm respawn <name>

EOF vs Interrupt:
  - Ctrl-C (interrupt): Cancels current command, returns to prompt
  - Ctrl-D (eof): Signals input complete, may exit shell

See Also:
  swarm interrupt --help    Send Ctrl-C (interrupt) to worker
  swarm send --help         Send text input to worker
  swarm kill --help         Forcefully stop worker
  swarm status --help       Check worker status
"""

ATTACH_HELP_DESCRIPTION = """\
Attach to a tmux worker's terminal window for live interaction.

Opens the worker's tmux window in your terminal, allowing you to observe the
agent's output in real-time and interact directly with the session. This is
useful for watching long-running tasks, debugging agent behavior, or taking
manual control when needed.

Your terminal will be replaced by the tmux session. To detach (return to your
shell without stopping the worker), press Ctrl-B then D.
"""

ATTACH_HELP_EPILOG = """\
Examples:
  # Attach to a worker's tmux window
  swarm attach my-worker

  # Watch an agent work on a feature
  swarm attach feature-auth

  # Debug a stuck worker
  swarm attach stuck-worker

Detaching from Tmux:
  Press Ctrl-B then D to detach from the session and return to your shell.
  The worker continues running in the background after detachment.

  Other useful tmux key bindings while attached:
    Ctrl-B D          Detach from session (return to shell)
    Ctrl-B [          Enter scroll/copy mode (q to exit)
    Ctrl-B PageUp     Scroll up through output history
    Ctrl-B c          Create new window in session
    Ctrl-B n/p        Next/previous window

Tips:
  - Use 'swarm logs --follow' if you just want to watch output without attaching
  - Attach is useful when you need to manually type commands to the agent
  - Custom tmux sockets (from --socket) are handled automatically
  - Worker must be running; use 'swarm status <name>' to check first

Common Workflow:
  1. Spawn worker:    swarm spawn --name dev --tmux --worktree -- claude
  2. Send initial:    swarm send dev "implement login feature"
  3. Watch progress:  swarm attach dev
  4. (Ctrl-B D to detach when satisfied)
  5. Check later:     swarm logs dev --follow

See Also:
  swarm logs --help       View worker output without attaching
  swarm send --help       Send commands to worker
  swarm status --help     Check worker status
  swarm spawn --help      Create new workers
"""

INIT_HELP_DESCRIPTION = """\
Initialize swarm in your project by adding agent instructions to a markdown file.

This command adds a "Process Management (swarm)" section to your project's agent
instruction file (AGENTS.md or CLAUDE.md). This section teaches AI agents how to
use swarm commands for parallel task execution and worktree isolation.

Auto-discovery: If no --file is specified, init checks for AGENTS.md first, then
CLAUDE.md. If neither exists, it creates AGENTS.md. The command is idempotent -
running it multiple times on the same file has no effect unless --force is used.
"""

INIT_HELP_EPILOG = """\
Examples:
  # Auto-discover and initialize (recommended)
  swarm init

  # Preview what would be done without making changes
  swarm init --dry-run

  # Explicitly target CLAUDE.md
  swarm init --file CLAUDE.md

  # Update existing swarm instructions to latest version
  swarm init --force

What Gets Added:
  A "Process Management (swarm)" section containing:
  - Quick reference for common swarm commands
  - Worktree isolation usage patterns
  - Ralph mode (autonomous looping) documentation
  - Power user tips and environment variable options

Auto-Discovery Order:
  1. If --file specified, use that file
  2. If AGENTS.md exists, append to it
  3. If CLAUDE.md exists, append to it
  4. Otherwise, create AGENTS.md

Idempotent Behavior:
  - If the marker "Process Management (swarm)" already exists in the target
    file, init reports this and exits without changes
  - Use --force to replace the existing section with the latest version

Common Workflow:
  1. Clone a project:     git clone <repo>
  2. Initialize swarm:    cd <repo> && swarm init
  3. Spawn a worker:      swarm spawn --name dev --tmux --worktree -- claude
  4. Send instructions:   swarm send dev "read AGENTS.md and start working"

See Also:
  swarm spawn --help      Create new workers
  swarm ralph --help      Autonomous agent looping
  swarm --help            Overview of all commands
"""

RALPH_HELP_DESCRIPTION = """\
Autonomous agent looping using the Ralph Wiggum pattern.

Ralph mode enables agents to work through task lists across multiple context
windows without human intervention. Each iteration: reads a prompt file,
spawns the agent, waits for completion/inactivity, then restarts.

Workflow:
  1. Create a task list (e.g., IMPLEMENTATION_PLAN.md)
  2. Create a prompt file: swarm ralph init
  3. Start the loop: swarm ralph spawn --name dev --prompt-file PROMPT.md \\
                       --max-iterations 50 -- claude

The agent reads the prompt each iteration, picks a task, implements it,
commits changes, and updates the task list. The loop continues until
max iterations or a done pattern is matched.
"""

RALPH_HELP_EPILOG = """\
Prompt Design Principles:
  - Keep prompts SHORT (<20 lines) to maximize context for work
  - ONE task per iteration (prevents partial completion)
  - Always verify code state before changes (don't assume)
  - Commit and push each iteration (persists work across context windows)
  - Update the task list (so next iteration knows what's done)

Quick Reference:
  swarm ralph init                    Create starter PROMPT.md
  swarm ralph spawn ... -- claude     Start autonomous loop
  swarm ralph status <name>           Check iteration progress
  swarm ralph pause <name>            Pause the loop
  swarm ralph resume <name>           Resume the loop
  swarm send <name> "message"         Intervene mid-iteration

See: https://github.com/ghuntley/how-to-ralph-wiggum
"""

RALPH_SPAWN_HELP_DESCRIPTION = """\
Spawn a new worker with ralph loop mode enabled.

By default, spawns the worker AND starts the monitoring loop (blocking).
Use --no-run to spawn without starting the loop.
"""

RALPH_SPAWN_HELP_EPILOG = """\
Examples:
  # Basic autonomous loop (blocks while running)
  swarm ralph spawn --name dev --prompt-file PROMPT.md --max-iterations 50 -- claude --dangerously-skip-permissions

  # With isolated git worktree
  swarm ralph spawn --name feature --prompt-file PROMPT.md --max-iterations 20 \\
    --worktree -- claude --dangerously-skip-permissions

  # With heartbeat for overnight work (recovers from rate limits)
  swarm ralph spawn --name dev --prompt-file PROMPT.md --max-iterations 100 \\
    --heartbeat 4h --heartbeat-expire 24h -- claude --dangerously-skip-permissions

  # Stop when pattern matched (checked after each agent exit)
  swarm ralph spawn --name dev --prompt-file PROMPT.md --max-iterations 100 \\
    --done-pattern "All tasks complete" -- claude --dangerously-skip-permissions

  # Stop immediately when pattern appears (continuous checking)
  swarm ralph spawn --name dev --prompt-file PROMPT.md --max-iterations 100 \\
    --done-pattern "All tasks complete" --check-done-continuous -- claude --dangerously-skip-permissions

  # Spawn only (run loop separately or later)
  swarm ralph spawn --name dev --prompt-file PROMPT.md --max-iterations 50 \\
    --no-run -- claude --dangerously-skip-permissions
  swarm ralph run dev

Heartbeat for Rate Limit Recovery:
  # Nudge every 4 hours for overnight work (24h expiry)
  swarm ralph spawn --name agent --prompt-file PROMPT.md --max-iterations 100 \\
    --heartbeat 4h --heartbeat-expire 24h -- claude --dangerously-skip-permissions

  # Custom message for specific recovery behavior
  swarm ralph spawn --name agent --prompt-file PROMPT.md --max-iterations 50 \\
    --heartbeat 4h --heartbeat-message "please continue where you left off" -- claude --dangerously-skip-permissions

Intervention:
  # Send a message to the running agent mid-iteration
  swarm send dev "please wrap up and commit your changes"
  swarm send dev "skip that approach, try using X instead"

Monitoring:
  swarm ralph status dev      # Check iteration progress
  swarm attach dev            # Watch agent live (detach: Ctrl-B D)
  swarm logs dev --follow     # Stream agent output

Security Note:
  The --dangerously-skip-permissions flag is required for autonomous operation.
  For overnight/unattended work, consider using Claude's native sandbox (/sandbox)
  or Docker Sandboxes for isolation. See README.md for sandboxing options.
"""

RALPH_INIT_HELP_EPILOG = """\
Creates a starter PROMPT.md in the current directory with best-practice
instructions for autonomous agent looping.

The template is intentionally minimal - customize it for your project:
  - Add project-specific test commands
  - Specify which files to study
  - Include deployment instructions if needed

Example:
  swarm ralph init
  vim PROMPT.md  # customize for your project
  swarm ralph spawn --name dev --prompt-file PROMPT.md --max-iterations 50 -- claude
"""

RALPH_TEMPLATE_HELP_EPILOG = """\
Prints the prompt template to stdout for piping or inspection.

Examples:
  swarm ralph template                     # View template
  swarm ralph template > MY_PROMPT.md      # Save to custom file
  swarm ralph template | pbcopy            # Copy to clipboard (macOS)
"""

RALPH_STATUS_HELP_EPILOG = """\
Shows detailed ralph loop status including iteration progress, failures,
and timing information.

Output includes:
  - Current status (running/paused/stopped/failed)
  - Iteration progress (e.g., 7/100)
  - Start times and failure counts
  - Done pattern and timeout settings
"""

RALPH_PAUSE_HELP_EPILOG = """\
Pauses the ralph loop. The current agent continues running, but when it
exits, the loop will not restart a new iteration.

Use 'swarm ralph resume <name>' to continue the loop.
"""

RALPH_RESUME_HELP_EPILOG = """\
Resumes a paused ralph loop. Continues from the current iteration count
(does not reset progress).

If the worker is not currently running, spawns a fresh agent for the
next iteration.
"""

RALPH_RUN_HELP_EPILOG = """\
Runs the monitoring loop for an existing ralph worker. This command blocks
while the loop is running.

Typically used after 'ralph spawn --no-run' when you want to spawn and
run the loop separately. By default, 'ralph spawn' runs the loop
automatically.

Example:
  swarm ralph spawn --name dev --prompt-file PROMPT.md --max-iterations 50 \\
    --no-run -- claude
  swarm ralph run dev
"""

RALPH_LIST_HELP_EPILOG = """\
Lists all workers that are running in ralph mode.

Examples:
  swarm ralph list                      # Table view
  swarm ralph list --format json        # JSON for scripting
  swarm ralph list --status running     # Only running loops
"""


# Heartbeat help text constants
HEARTBEAT_HELP_DESCRIPTION = """\
Periodic nudges to help workers recover from rate limits.

Heartbeat sends messages to workers on a schedule. This helps agents
recover from API rate limits that renew on fixed intervals (e.g., every
4 hours). Instead of detecting rate limits, heartbeat blindly nudges -
if the agent is stuck, it retries; if working, it ignores the nudge.
"""

HEARTBEAT_HELP_EPILOG = """\
Quick Reference:
  swarm heartbeat start builder --interval 4h --expire 24h
  swarm heartbeat list
  swarm heartbeat status builder
  swarm heartbeat pause builder
  swarm heartbeat resume builder
  swarm heartbeat stop builder

Common Patterns:
  # Nudge every 4 hours for overnight work (24h expiry)
  swarm heartbeat start agent --interval 4h --expire 24h

  # Custom message for specific recovery
  swarm heartbeat start agent --interval 4h --message "please continue where you left off"

  # Attach heartbeat at spawn time (see: swarm spawn --heartbeat)
  swarm spawn --name agent --tmux --heartbeat 4h --heartbeat-expire 24h -- claude

Duration Format:
  Accepts: "4h", "30m", "90s", "3600" (seconds), or combinations "1h30m"
  Examples: "4h" = 4 hours, "30m" = 30 minutes, "1h30m" = 90 minutes

See Also:
  swarm heartbeat start --help   # Detailed start options
  swarm spawn --help             # --heartbeat flag for spawn-time setup
  swarm send --help              # Manual intervention
"""

HEARTBEAT_START_HELP_DESCRIPTION = """\
Start periodic heartbeat nudges for a worker.

Creates a heartbeat that sends a message to the specified worker at
regular intervals. This is useful for helping agents recover from
API rate limits that renew on fixed schedules.
"""

HEARTBEAT_START_HELP_EPILOG = """\
Duration Format:
  Accepts: "4h", "30m", "90s", "3600" (seconds), or combinations "1h30m"

Examples:
  # Basic 4-hour heartbeat with 24-hour expiry
  swarm heartbeat start builder --interval 4h --expire 24h

  # Custom recovery message
  swarm heartbeat start builder --interval 4h \\
    --message "If you hit a rate limit, please continue now"

  # Short interval for testing
  swarm heartbeat start builder --interval 5m --expire 1h

  # No expiration (manual stop required)
  swarm heartbeat start builder --interval 4h

  # Replace an existing heartbeat with new settings
  swarm heartbeat start builder --interval 2h --expire 12h --force

Rate Limit Recovery:
  API rate limits often renew on fixed intervals. Set --interval to match
  your rate limit renewal period. The heartbeat will nudge the agent at
  each interval, prompting it to retry if it was blocked.

  Example: Claude API limits renew every 4 hours
    swarm heartbeat start agent --interval 4h --expire 24h

Safety:
  Always set --expire for unattended work to prevent infinite nudging.
  Heartbeats automatically stop when:
    - Expiration time is reached
    - Worker is killed
    - Manual stop via: swarm heartbeat stop <worker>

Tips:
  - Set --interval to match your API's rate limit renewal period
  - Use --expire slightly longer than your expected work duration
  - The message "continue" works well for most AI agents
  - Check status with: swarm heartbeat status <worker>
  - Monitor beats sent to confirm heartbeat is working

See Also:
  swarm spawn --help             # --heartbeat flag for spawn-time setup
  swarm heartbeat status --help  # Check heartbeat state
  swarm heartbeat pause --help   # Temporarily pause beats
"""

HEARTBEAT_STOP_HELP_DESCRIPTION = """\
Stop heartbeat for a worker permanently.

Terminates the heartbeat monitor and sets status to "stopped".
Unlike pause, stopped heartbeats cannot be resumed.
"""

HEARTBEAT_STOP_HELP_EPILOG = """\
The heartbeat state file is preserved for inspection. If the heartbeat
was already stopped, expired, or doesn't exist, this command is a no-op.

Examples:
  # Stop heartbeat for a specific worker
  swarm heartbeat stop builder

  # Clean up after worker is killed (usually automatic)
  swarm kill myworker
  swarm heartbeat stop myworker

  # Stop after work is complete
  swarm wait myworker && swarm heartbeat stop myworker

Tips:
  - Heartbeats auto-stop when their worker is killed
  - Use pause instead if you might want to resume later
  - State file is preserved at ~/.swarm/heartbeats/<worker>.json

See Also:
  swarm heartbeat list --help      # Find active heartbeats
  swarm heartbeat pause --help     # Pause without stopping
"""

HEARTBEAT_LIST_HELP_DESCRIPTION = """\
List all heartbeats and their current status.

Shows a table with all configured heartbeats, including active, paused,
expired, and stopped heartbeats. Use --format json for scripting.
"""

HEARTBEAT_LIST_HELP_EPILOG = """\
Output Columns:
  WORKER     Worker name
  INTERVAL   Time between beats
  NEXT BEAT  Time until next beat (or status if not active)
  EXPIRES    Expiration time (or "never")
  STATUS     active/paused/expired/stopped
  BEATS      Number of beats sent

Examples:
  # Show all heartbeats in table format
  swarm heartbeat list

  # Get JSON output for scripting
  swarm heartbeat list --format json

  # Count active heartbeats
  swarm heartbeat list --format json | jq '[.[] | select(.status == "active")] | length'

See Also:
  swarm heartbeat status --help  # Detailed status for one heartbeat
  swarm heartbeat start --help   # Start a new heartbeat
"""

HEARTBEAT_STATUS_HELP_DESCRIPTION = """\
Show detailed status for a single heartbeat.

Displays comprehensive information about a heartbeat's configuration,
timing, and activity. Useful for monitoring and debugging.
"""

HEARTBEAT_STATUS_HELP_EPILOG = """\
Output Fields:
  Status        active/paused/expired/stopped
  Worker        Target worker name
  Interval      Time between beats
  Message       Message sent on each beat
  Created       When heartbeat was started
  Expires       When heartbeat will expire (or "never")
  Last beat     When last beat was sent
  Next beat     When next beat is scheduled
  Beat count    Total number of beats sent

Output Formats:
  text (default)    Human-readable key-value pairs
  json              Machine-readable JSON object

Examples:
  # Show status for a worker's heartbeat
  swarm heartbeat status builder

  # Get JSON output for scripting
  swarm heartbeat status builder --format json

  # Check when next beat will occur
  swarm heartbeat status builder | grep "Next beat"

  # Verify heartbeat is active
  swarm heartbeat status builder --format json | jq -r '.status'

See Also:
  swarm heartbeat list --help    # List all heartbeats
  swarm heartbeat pause --help   # Pause a heartbeat
"""

HEARTBEAT_PAUSE_HELP_DESCRIPTION = """\
Pause heartbeat temporarily without stopping it.

The heartbeat configuration is preserved but beats stop being sent.
This is useful when you need to interact with a worker manually
without heartbeat interference, then resume later.
"""

HEARTBEAT_PAUSE_HELP_EPILOG = """\
Examples:
  # Pause heartbeat while debugging
  swarm heartbeat pause builder

  # Pause, interact manually, then resume
  swarm heartbeat pause builder
  swarm send builder "let me check something"
  # ... do manual work ...
  swarm heartbeat resume builder

  # Pause all heartbeats for maintenance
  swarm heartbeat list --format json | jq -r '.[].worker_name' | \\
    xargs -I{} swarm heartbeat pause {}

Tips:
  - Paused heartbeats don't count against expiration time
  - Use 'swarm heartbeat status <worker>' to check if paused
  - Prefer pause over stop when you want to resume later

See Also:
  swarm heartbeat resume --help  # Resume paused heartbeat
  swarm heartbeat stop --help    # Permanently stop heartbeat
"""

HEARTBEAT_RESUME_HELP_DESCRIPTION = """\
Resume a paused heartbeat.

Continues sending beats at the configured interval. The next beat
will be scheduled based on the interval from when resume is called.
"""

HEARTBEAT_RESUME_HELP_EPILOG = """\
Examples:
  # Resume a paused heartbeat
  swarm heartbeat resume builder

  # Check status then resume
  swarm heartbeat status builder   # Verify it's paused
  swarm heartbeat resume builder

  # Resume and verify
  swarm heartbeat resume builder && swarm heartbeat status builder

Tips:
  - Only works on paused heartbeats (not stopped or expired)
  - The next beat is scheduled immediately from resume time
  - Check status first if unsure: swarm heartbeat status <worker>

See Also:
  swarm heartbeat pause --help   # Pause a heartbeat
  swarm heartbeat start --help   # Start a new heartbeat
"""


# ==============================================================================
# Workflow Help Text
# ==============================================================================

WORKFLOW_HELP_DESCRIPTION = """\
Multi-stage agent pipelines with scheduling and rate limit recovery.

Workflow orchestrates sequential agent stages (plan → build → validate)
defined in YAML. Each stage can be a one-shot worker or a ralph loop.
Workflows support scheduling, heartbeats for rate limit recovery, and
configurable failure handling.
"""

WORKFLOW_HELP_EPILOG = """\
Quick Start:
  1. Create workflow.yaml (see: swarm workflow run --help for format)
  2. Run: swarm workflow run workflow.yaml
  3. Monitor: swarm workflow status my-workflow

Scheduling:
  # Run at 2am tonight
  swarm workflow run workflow.yaml --at "02:00"

  # Run in 4 hours
  swarm workflow run workflow.yaml --in 4h

Rate Limit Recovery:
  Set heartbeat in workflow.yaml to automatically nudge agents when
  they might be stuck on rate limits:

    heartbeat: 4h           # Nudge every 4 hours
    heartbeat-expire: 24h   # Stop after 24 hours

Storage:
  Workflow state: ~/.swarm/workflows/<name>/
  Repo-local definitions: .swarm/workflows/ (searched first)
  Global definitions: ~/.swarm/workflows/

File Resolution:
  Workflow files can be specified by path or by name:

    # By path (explicit file location)
    swarm workflow run ./workflows/build.yaml
    swarm workflow run /absolute/path/to/workflow.yaml

    # By name (searches .swarm/workflows/ then ~/.swarm/workflows/)
    swarm workflow run build              # Finds build.yaml or build.yml
    swarm workflow run overnight-build    # Finds overnight-build.yaml

  Search order for name-based lookup:
    1. .swarm/workflows/<name>[.yaml|.yml]  (repo-local, searched first)
    2. ~/.swarm/workflows/<name>[.yaml|.yml] (global)

Examples:
  # Run by path
  swarm workflow run ./build-feature.yaml
  swarm workflow run ./overnight-work.yaml --at "02:00"

  # Run by name (from .swarm/workflows/ or ~/.swarm/workflows/)
  swarm workflow run build                # Finds build.yaml in search paths
  swarm workflow validate overnight       # Validates overnight.yaml

  # Other workflow commands
  swarm workflow status feature-build
  swarm workflow cancel feature-build
  swarm workflow resume feature-build --from validate

Director Pattern (Agent-in-the-Loop):
  For monitored workflows, spawn a separate "director" agent that watches
  and intervenes using existing swarm commands:

    # Start workflow in background
    swarm workflow run build.yaml &

    # Spawn director to monitor
    swarm spawn --name director --tmux -- claude
    swarm send director "Monitor 'feature-build', intervene if stages fail"

  The director uses: workflow status, send, attach, pause, resume, cancel.
  See: swarm workflow run --help (Director Pattern section)
"""

WORKFLOW_VALIDATE_HELP_DESCRIPTION = """\
Validate workflow YAML without running it.

Checks the workflow definition for syntax errors, missing required fields,
invalid values, and verifies that all prompt files exist. Use this to
catch errors before attempting to run a workflow.
"""

WORKFLOW_VALIDATE_HELP_EPILOG = """\
Validation Checks:
  - YAML syntax is valid
  - Required fields present (name, stages, stage type, prompt)
  - Stage types are valid (worker or ralph)
  - on-failure values are valid (stop, retry, skip)
  - on-complete values are valid (next, stop, goto:<stage>)
  - ralph stages have max-iterations
  - No duplicate stage names
  - No circular goto references
  - All prompt files exist and are readable

File Resolution:
  Workflow files can be specified by path or by name. Name-based lookup
  searches .swarm/workflows/ (repo-local) then ~/.swarm/workflows/ (global).

Examples:
  # Validate a workflow file by path
  swarm workflow validate ./build-feature.yaml

  # Validate by name (finds in .swarm/workflows/ or ~/.swarm/workflows/)
  swarm workflow validate build
  swarm workflow validate overnight

  # Validate before running
  swarm workflow validate ./workflow.yaml && swarm workflow run ./workflow.yaml

  # Check multiple files
  for f in workflows/*.yaml; do swarm workflow validate "$f"; done

Output:
  On success: "Workflow '<name>' is valid (N stages)"
  On failure: Lists all validation errors found

Common Errors:
  "workflow missing required field 'name'"
    → Add 'name: my-workflow' to YAML

  "stage 'build' missing required field 'type'"
    → Add 'type: worker' or 'type: ralph' to stage

  "stage 'build' requires prompt or prompt-file"
    → Add inline 'prompt:' or 'prompt-file:' path

  "ralph stage 'build' requires max-iterations"
    → Add 'max-iterations: 50' to ralph stages

  "prompt file not found: ./prompts/build.md"
    → Create the file or fix the path

See Also:
  swarm workflow run --help    # Run a workflow
"""

WORKFLOW_RUN_HELP_DESCRIPTION = """\
Run a workflow from a YAML definition file.

A workflow defines sequential stages that execute one after another.
Each stage can be a 'worker' (single run agent) or 'ralph' (looping agent).
Workflows support scheduling, heartbeats for rate limit recovery, and
configurable failure handling.
"""

WORKFLOW_RUN_HELP_EPILOG = """\
Workflow YAML Format:
  A workflow defines sequential stages that execute one after another.
  Each stage is either a 'worker' (single run) or 'ralph' (loop).

  Required Fields:
    name: my-workflow           # Unique identifier

  Optional Global Settings:
    description: "..."          # Human description
    schedule: "02:00"           # Default start time (HH:MM)
    delay: "4h"                 # Alternative: start after delay
    heartbeat: 4h               # Rate limit recovery interval
    heartbeat-expire: 24h       # Stop heartbeat after duration
    heartbeat-message: "..."    # Custom nudge message
    worktree: true              # Git worktree isolation
    cwd: ./path                 # Working directory

  Stages (required, list):
    stages:
      - name: stage-name        # Required: stage identifier
        type: worker            # Required: worker | ralph

        # Prompt (exactly one required):
        prompt: |               # Inline prompt
          Your instructions...
        prompt-file: ./file.md  # OR file path

        # Completion (optional):
        done-pattern: "/done"   # Regex to detect completion
        timeout: 2h             # Max time before moving on

        # Failure handling (optional):
        on-failure: stop        # stop | retry | skip (default: stop)
        max-retries: 3          # Attempts if on-failure: retry

        # Ralph-specific (type: ralph only):
        max-iterations: 50      # Required for ralph
        inactivity-timeout: 60  # Seconds (default: 60)
        check-done-continuous: true

        # Stage overrides (optional):
        heartbeat: 2h           # Override global
        worktree: false         # Override global
        env:
          KEY: "value"
        tags:
          - my-tag

        # Flow control (optional):
        on-complete: next       # next | stop | goto:<stage>

Minimal Example:
  name: simple-task
  stages:
    - name: work
      type: worker
      prompt: |
        Complete the task in TASK.md.
        Say /done when finished.
      done-pattern: "/done"
      timeout: 1h

Full Example:
  name: feature-build
  description: Plan, build, and validate a feature
  heartbeat: 4h
  heartbeat-expire: 24h
  worktree: true

  stages:
    - name: plan
      type: worker
      prompt: |
        Read TASK.md. Create implementation plan in PLAN.md.
        Say /done when the plan is complete.
      done-pattern: "/done"
      timeout: 1h
      on-complete: next

    - name: build
      type: ralph
      prompt-file: ./prompts/build.md
      max-iterations: 50
      check-done-continuous: true
      done-pattern: "ALL TASKS COMPLETE"
      on-failure: retry
      max-retries: 2
      on-complete: next

    - name: validate
      type: ralph
      prompt: |
        Review implementation against PLAN.md.
        Run tests: python -m pytest
        Fix any failures. Say /done when all tests pass.
      max-iterations: 20
      done-pattern: "/done"
      on-complete: stop

Stage Type Reference:

  worker (single-run agent):
    - Spawns agent once
    - Waits for done-pattern or timeout
    - Good for: planning, review, one-shot tasks

  ralph (looping agent):
    - Spawns agent repeatedly (ralph loop)
    - Continues until max-iterations or done-pattern
    - Good for: implementation, multi-step tasks

Failure Handling:

  on-failure: stop    - Stop entire workflow (default)
  on-failure: retry   - Retry stage up to max-retries times
  on-failure: skip    - Skip stage, continue to next

Flow Control:

  on-complete: next       - Continue to next stage (default)
  on-complete: stop       - End workflow successfully
  on-complete: goto:name  - Jump to named stage (future)

File Resolution:
  Workflow files can be specified by path or by name:

    # By path (explicit file location)
    swarm workflow run ./workflows/build.yaml

    # By name (searches .swarm/workflows/ then ~/.swarm/workflows/)
    swarm workflow run build              # Finds build.yaml or build.yml

  Search order for name-based lookup:
    1. .swarm/workflows/<name>[.yaml|.yml]  (repo-local, searched first)
    2. ~/.swarm/workflows/<name>[.yaml|.yml] (global)

Examples:
  # Run workflow by path
  swarm workflow run ./build-feature.yaml

  # Run workflow by name (from .swarm/workflows/ or ~/.swarm/workflows/)
  swarm workflow run build
  swarm workflow run overnight-build

  # Run overnight at 2am
  swarm workflow run ./overnight-work.yaml --at "02:00"

  # Run after 4 hours
  swarm workflow run ./workflow.yaml --in "4h"

  # Run with custom name
  swarm workflow run ./generic-build.yaml --name "auth-feature"

  # Force overwrite existing workflow
  swarm workflow run ./build.yaml --force

Scheduling Notes:
  --at TIME     Schedule start time (HH:MM, 24-hour format)
                If the time has passed today, schedules for tomorrow.
  --in DURATION Schedule start delay (e.g., "4h", "30m", "1h30m")

Duration Format:
  Accepts: "4h", "30m", "90s", "1h30m", or seconds as integer

Tips:
  - Keep prompts SHORT (<20 lines) to maximize context for work
  - Use prompt-file for complex prompts with multiple instructions
  - Set heartbeat for overnight/unattended workflows
  - Always set timeout or max-iterations to prevent infinite runs
  - Use done-pattern for reliable stage completion detection

Debugging:
  swarm workflow validate file.yaml   # Check syntax without running
  swarm workflow status <name>        # Check progress
  swarm workflow logs <name>          # View all logs
  swarm attach <workflow>-<stage>     # Attach to running stage

Director Pattern (Agent-in-the-Loop):
  For workflows that need monitoring/intervention, spawn a separate
  "director" agent instead of building orchestration into the workflow:

    # Start workflow
    swarm workflow run build.yaml &

    # Spawn director agent to monitor and intervene
    swarm spawn --name director --tmux -- claude
    swarm send director "Monitor workflow 'my-workflow'. Check status
      every 10 min. Intervene with 'swarm send <worker> msg' if stuck."

  The director uses existing commands (workflow status, send, attach,
  pause, resume) to monitor and control the workflow.

  Director can be a ralph loop for long-running monitoring:
    swarm ralph spawn --name director --prompt-file director.md \\
      --max-iterations 100 -- claude

See Also:
  swarm workflow validate --help  # Validate YAML before running
  swarm workflow status --help    # Check workflow progress
"""

WORKFLOW_STATUS_HELP_DESCRIPTION = """\
Show detailed status of a workflow.

Displays the overall workflow status, current stage, and the status
of each individual stage. Use this to monitor workflow progress and
diagnose issues.
"""

WORKFLOW_STATUS_HELP_EPILOG = """\
Output Fields:
  Workflow      Workflow name
  Status        created/scheduled/running/completed/failed/cancelled
  Current       Currently executing stage (if running)
  Started       When workflow started executing
  Scheduled     When workflow is scheduled to start (if scheduled)
  Completed     When workflow finished (if completed/failed/cancelled)
  Source        Path to workflow YAML file

Stage Fields:
  Name          Stage identifier
  Status        pending/running/completed/failed/skipped
  Worker        Associated worker name (if started)
  Attempts      Number of execution attempts
  Started       When stage started
  Completed     When stage finished
  Exit Reason   How stage completed (done_pattern/timeout/error/skipped)

Output Formats:
  text (default)    Human-readable format with stages table
  json              Machine-readable JSON object

Examples:
  # Show workflow status
  swarm workflow status my-workflow

  # Get JSON output for scripting
  swarm workflow status my-workflow --format json

  # Check current stage
  swarm workflow status my-workflow | grep "Current"

  # Monitor workflow in a loop
  watch -n 10 swarm workflow status my-workflow

Stage Status Values:
  pending     Stage not yet started
  running     Stage currently executing
  completed   Stage finished successfully
  failed      Stage failed (exhausted retries)
  skipped     Stage skipped due to on-failure: skip

Workflow Status Values:
  created     Parsed but not started
  scheduled   Waiting for scheduled start time
  running     Currently executing stages
  completed   All stages finished successfully
  failed      Stage failed and on-failure: stop
  cancelled   Manually cancelled

See Also:
  swarm workflow list --help      # List all workflows
  swarm workflow logs --help      # View workflow logs
  swarm attach <workflow>-<stage> # Attach to running stage
"""

WORKFLOW_LIST_HELP_DESCRIPTION = """\
List all workflows.

Shows all workflow states with their current status, stage, and timing
information. Use this to monitor multiple workflows or find workflow names.
"""

WORKFLOW_LIST_HELP_EPILOG = """\
Output Columns:
  NAME          Workflow identifier
  STATUS        created/scheduled/running/completed/failed/cancelled
  CURRENT       Currently executing stage (or last stage if finished)
  STARTED       When workflow started (relative time)
  SOURCE        Path to workflow YAML file

Output Formats:
  table (default)    Human-readable table format
  json               Machine-readable JSON array

Examples:
  # List all workflows
  swarm workflow list

  # Get JSON output for scripting
  swarm workflow list --format json

  # Find running workflows
  swarm workflow list | grep running

  # Count workflows by status
  swarm workflow list --format json | jq 'group_by(.status) | map({status: .[0].status, count: length})'

Workflow States:
  created     Parsed but not started
  scheduled   Waiting for scheduled start time
  running     Currently executing stages
  completed   All stages finished successfully
  failed      Stage failed and on-failure: stop
  cancelled   Manually cancelled

See Also:
  swarm workflow status <name>    # Detailed status of single workflow
  swarm workflow run --help       # Start a new workflow
  swarm workflow cancel --help    # Cancel a running workflow
"""

WORKFLOW_CANCEL_HELP_DESCRIPTION = """\
Cancel a running workflow.

Stops the workflow and kills the current stage worker. If the workflow has
an active heartbeat, it will also be stopped. The workflow status is set
to 'cancelled'.
"""

WORKFLOW_CANCEL_HELP_EPILOG = """\
Warnings:
  - Cancellation is immediate - the current stage worker is killed
  - If stage worker has uncommitted changes (e.g., in a worktree), they are
    preserved but the agent stops working on them
  - With --force, the worker is killed immediately without graceful shutdown
  - Cancelled workflows cannot automatically resume - use 'workflow resume'

Side Effects:
  - Sets workflow status to 'cancelled'
  - Kills the current stage worker (if any)
  - Stops any active heartbeat for the stage worker
  - Current stage is marked as 'failed' with exit_reason 'cancelled'

Options:
  --force         Kill workers without graceful shutdown (immediate SIGKILL).
                  Use when the worker is unresponsive or hanging.

Examples:
  # Cancel a running workflow
  swarm workflow cancel my-workflow

  # Force-kill a stuck workflow (worker unresponsive)
  swarm workflow cancel my-workflow --force

  # Cancel and verify
  swarm workflow cancel my-workflow && swarm workflow status my-workflow

Recovery:
  After cancelling, you can resume from a specific stage:
    swarm workflow resume my-workflow --from <stage-name>

  Or clean up and start fresh:
    swarm workflow run workflow.yaml --force

  Check for uncommitted work in worktrees:
    git -C <repo>-worktrees/<workflow>-<stage> status

What Gets Cancelled:
  - The running workflow transitions to 'cancelled' status
  - The current stage worker (named <workflow>-<stage>) is killed
  - Any heartbeat monitoring the stage worker is stopped
  - Pending stages remain 'pending' (not executed)

See Also:
  swarm workflow status <name>    # Check current workflow state
  swarm workflow resume --help    # Resume a cancelled workflow
  swarm kill --help               # Manually kill workers
  swarm heartbeat stop --help     # Manually stop heartbeats
"""

WORKFLOW_RESUME_HELP_DESCRIPTION = """\
Resume a failed or cancelled workflow.

Restarts a workflow that was previously cancelled or failed. By default,
resumes from the stage where the workflow stopped. Use --from to restart
from a specific stage (useful for skipping problematic stages or re-running
earlier stages after fixing issues).
"""

WORKFLOW_RESUME_HELP_EPILOG = """\
Resumable States:
  - failed: Workflow stopped due to stage failure
  - cancelled: Workflow was manually cancelled

Options:
  --from STAGE    Resume from a specific stage (resets that stage and all
                  subsequent stages to pending). Without this flag, resumes
                  from the failed/current stage.

Examples:
  # Resume from where it stopped
  swarm workflow resume my-workflow

  # Resume from a specific stage (skips earlier stages)
  swarm workflow resume my-workflow --from validate

  # Re-run the entire workflow from the beginning
  swarm workflow resume my-workflow --from plan

What Gets Reset:
  When resuming, the specified stage and all subsequent stages are reset:
  - Stage status set to 'pending'
  - Attempt counts preserved (for retry tracking)
  - Previous stage results are kept

  Completed stages before the resume point are NOT re-run.

Typical Workflow:
  1. Workflow fails: swarm workflow status my-workflow
  2. Fix the issue (code, prompts, etc.)
  3. Resume: swarm workflow resume my-workflow
  4. Or restart from specific stage: swarm workflow resume my-workflow --from build

See Also:
  swarm workflow status <name>    # Check failure details
  swarm workflow cancel <name>    # Cancel a running workflow
  swarm workflow run --force      # Start fresh (deletes old state)
"""

WORKFLOW_RESUME_ALL_HELP_DESCRIPTION = """\
Resume all interrupted workflows after system restart.

When the system restarts or workflow monitors are killed, this command
finds workflows that were 'running' or 'scheduled' and offers to resume
them. Useful after unexpected shutdowns or when workflow monitors were
stopped externally.
"""

WORKFLOW_RESUME_ALL_HELP_EPILOG = """\
Resumable States:
  - running: Workflow was actively running when interrupted
  - scheduled: Workflow was waiting for scheduled start time

What Happens:
  1. Finds all workflows with status 'running' or 'scheduled'
  2. For 'running' workflows: resumes from the current stage
  3. For 'scheduled' workflows: restarts the scheduling wait

Options:
  --dry-run       Show which workflows would be resumed, without resuming
  --background    Run each workflow monitor in background (nohup)
                  Without this flag, workflows are resumed sequentially

Examples:
  # See which workflows need resuming (dry run)
  swarm workflow resume-all --dry-run

  # Resume all interrupted workflows sequentially (foreground)
  swarm workflow resume-all

  # Resume all interrupted workflows in background
  swarm workflow resume-all --background

Typical Use:
  After a system restart or unexpected shutdown:
  1. Check for interrupted workflows: swarm workflow list
  2. See what would be resumed: swarm workflow resume-all --dry-run
  3. Resume in background: swarm workflow resume-all --background

Note:
  This command is automatically called (in dry-run mode) on swarm startup
  to notify you of any interrupted workflows.

See Also:
  swarm workflow list             # List all workflows
  swarm workflow status <name>    # Check workflow details
  swarm workflow resume <name>    # Resume a single workflow
"""

WORKFLOW_LOGS_HELP_DESCRIPTION = """\
View logs from workflow stages.

Shows output from stage workers that have run or are currently running.
Stage workers are named '<workflow>-<stage>', and their logs are captured
from tmux panes (for tmux workers) or log files (for non-tmux workers).
"""

WORKFLOW_LOGS_HELP_EPILOG = """\
Options:
  --stage STAGE   Show logs only for a specific stage. Without this flag,
                  shows logs from all stages in execution order.
  --follow        Continuously poll for new output (like tail -f). Only
                  works when viewing a single stage (use --stage).
  --lines N       Number of history lines to show (default: 1000).

Output Format:
  Logs are displayed with stage headers:

    === Stage: plan (worker: my-workflow-plan) ===
    [stage output...]

    === Stage: build (worker: my-workflow-build) ===
    [stage output...]

  For pending stages (no worker spawned yet), a placeholder is shown.

Examples:
  # View all stage logs
  swarm workflow logs my-workflow

  # View logs for a specific stage
  swarm workflow logs my-workflow --stage build

  # Follow logs for a running stage (Ctrl-C to stop)
  swarm workflow logs my-workflow --stage validate --follow

  # Show more history lines
  swarm workflow logs my-workflow --lines 5000

Worker Log Sources:
  - tmux workers: Captured from tmux pane scrollback buffer
  - Non-tmux workers: Read from ~/.swarm/logs/<worker>.stdout.log

  For running stages, logs show current tmux pane content plus history.
  For completed stages, logs show the captured output from when the
  stage was running (if worker still exists in state).

Troubleshooting:
  If a stage shows "no logs available", the worker may have been:
  - Cleaned up (use 'swarm clean' carefully)
  - Never spawned (stage still pending)
  - A non-tmux worker without a log file

See Also:
  swarm workflow status <name>    # Check which stages have run
  swarm logs <worker>             # View logs for individual workers
  swarm attach <worker>           # Attach to running tmux worker
"""


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
    inactivity_timeout: int = 60
    check_done_continuous: bool = False

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
            "check_done_continuous": self.check_done_continuous,
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
            inactivity_timeout=d.get("inactivity_timeout", 60),
            check_done_continuous=d.get("check_done_continuous", False),
        )


@dataclass
class HeartbeatState:
    """Heartbeat state for periodic nudges to a worker.

    Heartbeat sends messages to workers on a schedule to help them recover
    from API rate limits or other blocking states.
    """
    worker_name: str
    interval_seconds: int
    message: str = "continue"
    expire_at: Optional[str] = None  # ISO 8601 timestamp, None = no expiration
    created_at: str = ""  # ISO 8601 timestamp
    last_beat_at: Optional[str] = None  # ISO 8601 timestamp of last beat, None if no beats yet
    beat_count: int = 0
    status: str = "active"  # active, paused, expired, stopped
    monitor_pid: Optional[int] = None  # PID of background monitor process

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "worker_name": self.worker_name,
            "interval_seconds": self.interval_seconds,
            "message": self.message,
            "expire_at": self.expire_at,
            "created_at": self.created_at,
            "last_beat_at": self.last_beat_at,
            "beat_count": self.beat_count,
            "status": self.status,
            "monitor_pid": self.monitor_pid,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "HeartbeatState":
        """Create HeartbeatState from dictionary."""
        return cls(
            worker_name=d["worker_name"],
            interval_seconds=d["interval_seconds"],
            message=d.get("message", "continue"),
            expire_at=d.get("expire_at"),
            created_at=d.get("created_at", ""),
            last_beat_at=d.get("last_beat_at"),
            beat_count=d.get("beat_count", 0),
            status=d.get("status", "active"),
            monitor_pid=d.get("monitor_pid"),
        )


@dataclass
class StageState:
    """State for a single workflow stage.

    Each stage tracks its execution status, timing, worker association,
    retry attempts, and how it completed (or failed).
    """
    status: str = "pending"  # pending, running, completed, failed, skipped
    started_at: Optional[str] = None  # ISO 8601 timestamp
    completed_at: Optional[str] = None  # ISO 8601 timestamp
    worker_name: Optional[str] = None  # Name of worker running this stage
    attempts: int = 0  # Number of execution attempts
    exit_reason: Optional[str] = None  # done_pattern, timeout, error, skipped

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "status": self.status,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "worker_name": self.worker_name,
            "attempts": self.attempts,
            "exit_reason": self.exit_reason,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "StageState":
        """Create StageState from dictionary."""
        return cls(
            status=d.get("status", "pending"),
            started_at=d.get("started_at"),
            completed_at=d.get("completed_at"),
            worker_name=d.get("worker_name"),
            attempts=d.get("attempts", 0),
            exit_reason=d.get("exit_reason"),
        )


@dataclass
class WorkflowState:
    """State for a multi-stage workflow.

    Workflows orchestrate sequential agent stages (plan → build → validate)
    with support for scheduling, heartbeats, and configurable failure handling.
    """
    name: str
    status: str = "created"  # created, scheduled, running, completed, failed, cancelled
    current_stage: Optional[str] = None  # Name of currently executing stage
    current_stage_index: int = 0  # Index in stages list
    created_at: str = ""  # ISO 8601 timestamp
    started_at: Optional[str] = None  # ISO 8601 timestamp
    scheduled_for: Optional[str] = None  # ISO 8601 timestamp for scheduled start
    completed_at: Optional[str] = None  # ISO 8601 timestamp
    stages: dict[str, StageState] = field(default_factory=dict)  # stage_name -> StageState
    workflow_file: str = ""  # Path to workflow YAML file
    workflow_hash: str = ""  # Hash of workflow YAML for change detection

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "name": self.name,
            "status": self.status,
            "current_stage": self.current_stage,
            "current_stage_index": self.current_stage_index,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "scheduled_for": self.scheduled_for,
            "completed_at": self.completed_at,
            "stages": {name: stage.to_dict() for name, stage in self.stages.items()},
            "workflow_file": self.workflow_file,
            "workflow_hash": self.workflow_hash,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "WorkflowState":
        """Create WorkflowState from dictionary."""
        stages = {}
        for name, stage_dict in d.get("stages", {}).items():
            stages[name] = StageState.from_dict(stage_dict)
        return cls(
            name=d["name"],
            status=d.get("status", "created"),
            current_stage=d.get("current_stage"),
            current_stage_index=d.get("current_stage_index", 0),
            created_at=d.get("created_at", ""),
            started_at=d.get("started_at"),
            scheduled_for=d.get("scheduled_for"),
            completed_at=d.get("completed_at"),
            stages=stages,
            workflow_file=d.get("workflow_file", ""),
            workflow_hash=d.get("workflow_hash", ""),
        )


@dataclass
class StageDefinition:
    """Definition of a workflow stage from YAML.

    Represents the configuration for a single stage in a workflow,
    including its type, prompt, completion criteria, and failure handling.
    """
    name: str
    type: str  # "worker" or "ralph"
    prompt: Optional[str] = None  # Inline prompt
    prompt_file: Optional[str] = None  # Path to prompt file
    done_pattern: Optional[str] = None  # Regex to detect completion
    timeout: Optional[str] = None  # Duration string e.g. "2h"
    on_failure: str = "stop"  # stop, retry, skip
    max_retries: int = 3  # Attempts if on_failure: retry
    on_complete: str = "next"  # next, stop, goto:<stage-name>

    # Ralph-specific options
    max_iterations: Optional[int] = None  # Required for ralph type
    inactivity_timeout: int = 60  # Seconds
    check_done_continuous: bool = False

    # Stage-specific overrides
    heartbeat: Optional[str] = None  # Override global heartbeat
    heartbeat_expire: Optional[str] = None  # Override global heartbeat-expire
    heartbeat_message: Optional[str] = None  # Override global heartbeat-message
    worktree: Optional[bool] = None  # Override global worktree
    cwd: Optional[str] = None  # Override global cwd
    env: dict[str, str] = field(default_factory=dict)  # Environment variables
    tags: list[str] = field(default_factory=list)  # Worker tags

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "name": self.name,
            "type": self.type,
            "prompt": self.prompt,
            "prompt_file": self.prompt_file,
            "done_pattern": self.done_pattern,
            "timeout": self.timeout,
            "on_failure": self.on_failure,
            "max_retries": self.max_retries,
            "on_complete": self.on_complete,
            "max_iterations": self.max_iterations,
            "inactivity_timeout": self.inactivity_timeout,
            "check_done_continuous": self.check_done_continuous,
            "heartbeat": self.heartbeat,
            "heartbeat_expire": self.heartbeat_expire,
            "heartbeat_message": self.heartbeat_message,
            "worktree": self.worktree,
            "cwd": self.cwd,
            "env": self.env,
            "tags": self.tags,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "StageDefinition":
        """Create StageDefinition from dictionary."""
        return cls(
            name=d["name"],
            type=d["type"],
            prompt=d.get("prompt"),
            prompt_file=d.get("prompt_file") or d.get("prompt-file"),
            done_pattern=d.get("done_pattern") or d.get("done-pattern"),
            timeout=d.get("timeout"),
            on_failure=d.get("on_failure") or d.get("on-failure", "stop"),
            max_retries=d.get("max_retries") or d.get("max-retries", 3),
            on_complete=d.get("on_complete") or d.get("on-complete", "next"),
            max_iterations=d.get("max_iterations") or d.get("max-iterations"),
            inactivity_timeout=d.get("inactivity_timeout") or d.get("inactivity-timeout", 60),
            check_done_continuous=d.get("check_done_continuous") or d.get("check-done-continuous", False),
            heartbeat=d.get("heartbeat"),
            heartbeat_expire=d.get("heartbeat_expire") or d.get("heartbeat-expire"),
            heartbeat_message=d.get("heartbeat_message") or d.get("heartbeat-message"),
            worktree=d.get("worktree"),
            cwd=d.get("cwd"),
            env=d.get("env", {}),
            tags=d.get("tags", []),
        )


@dataclass
class WorkflowDefinition:
    """Definition of a workflow from YAML.

    Represents the complete configuration for a workflow including
    global settings and all stage definitions.
    """
    name: str
    description: Optional[str] = None
    schedule: Optional[str] = None  # Start time (HH:MM, 24h format)
    delay: Optional[str] = None  # Start delay duration string

    # Global settings
    heartbeat: Optional[str] = None  # Nudge interval
    heartbeat_expire: Optional[str] = None  # Stop heartbeat after duration
    heartbeat_message: str = "continue"  # Message to send
    worktree: bool = False  # Use git worktrees
    cwd: Optional[str] = None  # Working directory

    # Stage definitions
    stages: list[StageDefinition] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "name": self.name,
            "description": self.description,
            "schedule": self.schedule,
            "delay": self.delay,
            "heartbeat": self.heartbeat,
            "heartbeat_expire": self.heartbeat_expire,
            "heartbeat_message": self.heartbeat_message,
            "worktree": self.worktree,
            "cwd": self.cwd,
            "stages": [s.to_dict() for s in self.stages],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "WorkflowDefinition":
        """Create WorkflowDefinition from dictionary."""
        stages = []
        for stage_dict in d.get("stages", []):
            stages.append(StageDefinition.from_dict(stage_dict))
        return cls(
            name=d["name"],
            description=d.get("description"),
            schedule=d.get("schedule"),
            delay=d.get("delay"),
            heartbeat=d.get("heartbeat"),
            heartbeat_expire=d.get("heartbeat_expire") or d.get("heartbeat-expire"),
            heartbeat_message=d.get("heartbeat_message") or d.get("heartbeat-message", "continue"),
            worktree=d.get("worktree", False),
            cwd=d.get("cwd"),
            stages=stages,
        )


class WorkflowValidationError(Exception):
    """Raised when workflow YAML validation fails."""
    pass


def parse_workflow_yaml(yaml_path: str) -> WorkflowDefinition:
    """Parse and validate a workflow YAML file.

    Args:
        yaml_path: Path to the workflow YAML file

    Returns:
        WorkflowDefinition: Parsed and validated workflow definition

    Raises:
        WorkflowValidationError: If validation fails
        FileNotFoundError: If the YAML file doesn't exist
        yaml.YAMLError: If YAML parsing fails
    """
    path = Path(yaml_path)

    # Check file exists
    if not path.exists():
        raise FileNotFoundError(f"workflow file not found: {yaml_path}")

    # Parse YAML
    try:
        with open(path, 'r') as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise WorkflowValidationError(f"invalid workflow YAML: {e}")

    if data is None:
        raise WorkflowValidationError("workflow file is empty")

    if not isinstance(data, dict):
        raise WorkflowValidationError("workflow must be a YAML mapping")

    # Validate required fields
    if "name" not in data:
        raise WorkflowValidationError("workflow missing required field 'name'")

    if "stages" not in data:
        raise WorkflowValidationError("workflow missing required field 'stages'")

    if not isinstance(data["stages"], list):
        raise WorkflowValidationError("'stages' must be a list")

    if len(data["stages"]) == 0:
        raise WorkflowValidationError("workflow must have at least one stage")

    # Validate each stage
    seen_stage_names = set()
    stage_names = []  # For goto validation

    for i, stage_data in enumerate(data["stages"]):
        if not isinstance(stage_data, dict):
            raise WorkflowValidationError(f"stage {i + 1} must be a YAML mapping")

        # Check required stage fields
        if "name" not in stage_data:
            raise WorkflowValidationError(f"stage {i + 1} missing required field 'name'")

        stage_name = stage_data["name"]
        stage_names.append(stage_name)

        # Check for duplicate stage names
        if stage_name in seen_stage_names:
            raise WorkflowValidationError(f"duplicate stage name: '{stage_name}'")
        seen_stage_names.add(stage_name)

        if "type" not in stage_data:
            raise WorkflowValidationError(f"stage '{stage_name}' missing required field 'type'")

        stage_type = stage_data["type"]

        # Validate stage type
        if stage_type not in ("worker", "ralph"):
            raise WorkflowValidationError(
                f"stage '{stage_name}' has invalid type '{stage_type}' (must be 'worker' or 'ralph')"
            )

        # Check prompt/prompt-file (exactly one required)
        has_prompt = "prompt" in stage_data and stage_data["prompt"]
        has_prompt_file = ("prompt_file" in stage_data and stage_data["prompt_file"]) or \
                          ("prompt-file" in stage_data and stage_data["prompt-file"])

        if has_prompt and has_prompt_file:
            raise WorkflowValidationError(f"stage '{stage_name}' has both prompt and prompt-file")

        if not has_prompt and not has_prompt_file:
            raise WorkflowValidationError(f"stage '{stage_name}' requires prompt or prompt-file")

        # Validate ralph-specific requirements
        if stage_type == "ralph":
            max_iterations = stage_data.get("max_iterations") or stage_data.get("max-iterations")
            if max_iterations is None:
                raise WorkflowValidationError(f"ralph stage '{stage_name}' requires max-iterations")
            if not isinstance(max_iterations, int) or max_iterations < 1:
                raise WorkflowValidationError(
                    f"stage '{stage_name}': max-iterations must be a positive integer"
                )

        # Validate on-failure
        on_failure = stage_data.get("on_failure") or stage_data.get("on-failure", "stop")
        if on_failure not in ("stop", "retry", "skip"):
            raise WorkflowValidationError(
                f"stage '{stage_name}' has invalid on-failure '{on_failure}' (must be 'stop', 'retry', or 'skip')"
            )

        # Validate max-retries if on-failure is retry
        if on_failure == "retry":
            max_retries = stage_data.get("max_retries") or stage_data.get("max-retries", 3)
            if not isinstance(max_retries, int) or max_retries < 1:
                raise WorkflowValidationError(
                    f"stage '{stage_name}': max-retries must be a positive integer"
                )

        # Validate on-complete
        on_complete = stage_data.get("on_complete") or stage_data.get("on-complete", "next")
        if on_complete not in ("next", "stop") and not on_complete.startswith("goto:"):
            raise WorkflowValidationError(
                f"stage '{stage_name}' has invalid on-complete '{on_complete}' (must be 'next', 'stop', or 'goto:<stage>')"
            )

    # Validate goto targets after all stages are collected
    for stage_data in data["stages"]:
        stage_name = stage_data["name"]
        on_complete = stage_data.get("on_complete") or stage_data.get("on-complete", "next")
        if on_complete.startswith("goto:"):
            target = on_complete[5:]  # Remove "goto:" prefix
            if target not in stage_names:
                raise WorkflowValidationError(f"unknown stage in goto: '{target}'")

    # Check for circular goto references (simple cycle detection)
    # Build a graph of goto relationships and check for cycles
    goto_graph = {}
    for stage_data in data["stages"]:
        stage_name = stage_data["name"]
        on_complete = stage_data.get("on_complete") or stage_data.get("on-complete", "next")
        if on_complete.startswith("goto:"):
            target = on_complete[5:]
            goto_graph[stage_name] = target

    # DFS to detect cycles
    def detect_cycle(start, visited, path):
        if start not in goto_graph:
            return False
        target = goto_graph[start]
        if target in path:
            return True
        if target in visited:
            return False
        visited.add(target)
        path.add(target)
        result = detect_cycle(target, visited, path)
        path.remove(target)
        return result

    for stage_name in goto_graph:
        visited = {stage_name}
        path = {stage_name}
        if detect_cycle(stage_name, visited, path):
            raise WorkflowValidationError("circular stage reference detected")

    # Create and return the WorkflowDefinition
    return WorkflowDefinition.from_dict(data)


def validate_workflow_prompt_files(workflow: WorkflowDefinition, base_path: Optional[Path] = None) -> list[str]:
    """Validate that all prompt files in a workflow exist.

    Args:
        workflow: The workflow definition to validate
        base_path: Base path for resolving relative prompt file paths.
                   If None, uses current working directory.

    Returns:
        List of error messages (empty if all files exist)
    """
    errors = []
    if base_path is None:
        base_path = Path.cwd()

    for stage in workflow.stages:
        if stage.prompt_file:
            prompt_path = Path(stage.prompt_file)
            if not prompt_path.is_absolute():
                prompt_path = base_path / prompt_path
            if not prompt_path.exists():
                errors.append(f"prompt file not found: {stage.prompt_file}")

    return errors


def resolve_workflow_file(file_arg: str) -> str:
    """Resolve a workflow file path, checking repo-local then global locations.

    Search order:
    1. If file_arg is an absolute path or contains path separators, use it directly
    2. If file_arg exists relative to current directory, use it
    3. Check .swarm/workflows/<file_arg> (repo-local)
    4. Check .swarm/workflows/<file_arg>.yaml (repo-local with extension)
    5. Check ~/.swarm/workflows/<file_arg> (global)
    6. Check ~/.swarm/workflows/<file_arg>.yaml (global with extension)

    Args:
        file_arg: The file argument from the command line. Can be:
            - A full path: /path/to/workflow.yaml
            - A relative path: ./workflows/build.yaml
            - A name: build (looks up in .swarm/workflows/ then ~/.swarm/workflows/)

    Returns:
        Resolved path to the workflow file

    Raises:
        FileNotFoundError: If the workflow file cannot be found in any location
    """
    path = Path(file_arg)

    # Case 1: Absolute path - use directly
    if path.is_absolute():
        if path.exists():
            return str(path)
        raise FileNotFoundError(f"workflow file not found: {file_arg}")

    # Case 2: Has path separators (e.g., ./foo.yaml, dir/foo.yaml) - use relative to cwd
    if os.sep in file_arg or file_arg.startswith("."):
        resolved = Path.cwd() / path
        if resolved.exists():
            return str(resolved)
        raise FileNotFoundError(f"workflow file not found: {file_arg}")

    # Case 3: File exists in current directory
    if path.exists():
        return str(path)

    # Case 4 & 5: Look up by name in .swarm/workflows/ (repo-local) then ~/.swarm/workflows/ (global)
    search_dirs = [
        Path.cwd() / ".swarm" / "workflows",  # Repo-local
        WORKFLOWS_DIR,  # Global (~/.swarm/workflows/)
    ]

    for search_dir in search_dirs:
        # Try exact name
        candidate = search_dir / file_arg
        if candidate.exists():
            return str(candidate)

        # Try with .yaml extension
        candidate_yaml = search_dir / f"{file_arg}.yaml"
        if candidate_yaml.exists():
            return str(candidate_yaml)

        # Try with .yml extension
        candidate_yml = search_dir / f"{file_arg}.yml"
        if candidate_yml.exists():
            return str(candidate_yml)

    # Nothing found - provide helpful error message
    repo_local = Path.cwd() / ".swarm" / "workflows"
    raise FileNotFoundError(
        f"workflow file not found: {file_arg}\n"
        f"  Searched: {file_arg} in current directory\n"
        f"            {repo_local / file_arg}[.yaml|.yml]\n"
        f"            {WORKFLOWS_DIR / file_arg}[.yaml|.yml]"
    )


# Heartbeat state lock file path
HEARTBEAT_LOCK_FILE = SWARM_DIR / "heartbeat.lock"


@contextmanager
def heartbeat_file_lock():
    """Context manager for exclusive locking of heartbeat state files.

    This prevents race conditions when multiple swarm processes
    attempt to read/modify/write heartbeat state files concurrently.

    Uses fcntl.flock() for exclusive (LOCK_EX) file locking.
    The lock is automatically released when the context exits,
    even if an exception occurs.

    Yields:
        File object for the lock file (callers don't need to use this)
    """
    ensure_dirs()
    lock_file = open(HEARTBEAT_LOCK_FILE, 'w')
    try:
        # Acquire exclusive lock (blocks if another process holds it)
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        yield lock_file
    finally:
        # Release lock and close file
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
        lock_file.close()


def get_heartbeat_state_path(worker_name: str) -> Path:
    """Get the path to a worker's heartbeat state file.

    Heartbeat state is stored per-worker at:
    ~/.swarm/heartbeats/<worker-name>.json

    Args:
        worker_name: Name of the worker

    Returns:
        Path to the heartbeat state file
    """
    return HEARTBEATS_DIR / f"{worker_name}.json"


def load_heartbeat_state(worker_name: str) -> Optional[HeartbeatState]:
    """Load heartbeat state for a worker.

    Reads heartbeat state from disk with exclusive file locking to
    prevent race conditions with concurrent processes.

    Args:
        worker_name: Name of the worker

    Returns:
        HeartbeatState if it exists, None otherwise
    """
    with heartbeat_file_lock():
        state_path = get_heartbeat_state_path(worker_name)
        if not state_path.exists():
            return None

        with open(state_path, "r") as f:
            data = json.load(f)
            return HeartbeatState.from_dict(data)


def save_heartbeat_state(heartbeat_state: HeartbeatState) -> None:
    """Save heartbeat state for a worker.

    Writes heartbeat state to disk with exclusive file locking to
    prevent race conditions with concurrent processes.

    Args:
        heartbeat_state: HeartbeatState to save
    """
    with heartbeat_file_lock():
        HEARTBEATS_DIR.mkdir(parents=True, exist_ok=True)
        state_path = get_heartbeat_state_path(heartbeat_state.worker_name)

        with open(state_path, "w") as f:
            json.dump(heartbeat_state.to_dict(), f, indent=2)


def delete_heartbeat_state(worker_name: str) -> bool:
    """Delete heartbeat state file for a worker.

    Removes the heartbeat state file with exclusive file locking.

    Args:
        worker_name: Name of the worker

    Returns:
        True if file was deleted, False if it didn't exist
    """
    with heartbeat_file_lock():
        state_path = get_heartbeat_state_path(worker_name)
        if state_path.exists():
            state_path.unlink()
            return True
        return False


def list_heartbeat_states() -> list[HeartbeatState]:
    """List all heartbeat states.

    Loads all heartbeat state files from the heartbeats directory
    with exclusive file locking.

    Returns:
        List of HeartbeatState objects, sorted by worker name
    """
    with heartbeat_file_lock():
        if not HEARTBEATS_DIR.exists():
            return []

        states = []
        for state_file in HEARTBEATS_DIR.glob("*.json"):
            try:
                with open(state_file, "r") as f:
                    data = json.load(f)
                    states.append(HeartbeatState.from_dict(data))
            except (json.JSONDecodeError, KeyError):
                # Skip invalid state files
                continue

        return sorted(states, key=lambda s: s.worker_name)


# Workflow state lock file path
WORKFLOW_LOCK_FILE = SWARM_DIR / "workflow.lock"


@contextmanager
def workflow_file_lock():
    """Context manager for exclusive locking of workflow state files.

    This prevents race conditions when multiple swarm processes
    attempt to read/modify/write workflow state files concurrently.

    Uses fcntl.flock() for exclusive (LOCK_EX) file locking.
    The lock is automatically released when the context exits,
    even if an exception occurs.

    Yields:
        File object for the lock file (callers don't need to use this)
    """
    ensure_dirs()
    lock_file = open(WORKFLOW_LOCK_FILE, 'w')
    try:
        # Acquire exclusive lock (blocks if another process holds it)
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        yield lock_file
    finally:
        # Release lock and close file
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
        lock_file.close()


def get_workflow_state_dir(workflow_name: str) -> Path:
    """Get the directory for a workflow's state.

    Workflow state is stored per-workflow at:
    ~/.swarm/workflows/<workflow-name>/

    Args:
        workflow_name: Name of the workflow

    Returns:
        Path to the workflow state directory
    """
    return WORKFLOWS_DIR / workflow_name


def get_workflow_state_path(workflow_name: str) -> Path:
    """Get the path to a workflow's state file.

    Workflow state is stored per-workflow at:
    ~/.swarm/workflows/<workflow-name>/state.json

    Args:
        workflow_name: Name of the workflow

    Returns:
        Path to the workflow state file
    """
    return get_workflow_state_dir(workflow_name) / "state.json"


def get_workflow_yaml_copy_path(workflow_name: str) -> Path:
    """Get the path where workflow YAML is copied.

    A copy of the original workflow YAML is stored at:
    ~/.swarm/workflows/<workflow-name>/workflow.yaml

    Args:
        workflow_name: Name of the workflow

    Returns:
        Path to the workflow YAML copy
    """
    return get_workflow_state_dir(workflow_name) / "workflow.yaml"


def get_workflow_logs_dir(workflow_name: str) -> Path:
    """Get the directory for a workflow's logs.

    Workflow logs are stored at:
    ~/.swarm/workflows/<workflow-name>/logs/

    Args:
        workflow_name: Name of the workflow

    Returns:
        Path to the workflow logs directory
    """
    return get_workflow_state_dir(workflow_name) / "logs"


def compute_workflow_hash(yaml_content: str) -> str:
    """Compute a hash of workflow YAML content.

    Used to detect if the workflow definition has changed since
    the workflow was started.

    Args:
        yaml_content: The raw YAML content string

    Returns:
        SHA-256 hash of the content (first 16 hex characters)
    """
    import hashlib
    return hashlib.sha256(yaml_content.encode()).hexdigest()[:16]


def load_workflow_state(workflow_name: str) -> Optional[WorkflowState]:
    """Load workflow state from disk.

    Reads workflow state from disk with exclusive file locking to
    prevent race conditions with concurrent processes.

    Args:
        workflow_name: Name of the workflow

    Returns:
        WorkflowState if it exists, None otherwise
    """
    with workflow_file_lock():
        state_path = get_workflow_state_path(workflow_name)
        if not state_path.exists():
            return None

        with open(state_path, "r") as f:
            data = json.load(f)
            return WorkflowState.from_dict(data)


def save_workflow_state(workflow_state: WorkflowState) -> None:
    """Save workflow state to disk.

    Writes workflow state to disk with exclusive file locking to
    prevent race conditions with concurrent processes.

    Args:
        workflow_state: WorkflowState to save
    """
    with workflow_file_lock():
        state_dir = get_workflow_state_dir(workflow_state.name)
        state_dir.mkdir(parents=True, exist_ok=True)
        state_path = get_workflow_state_path(workflow_state.name)

        with open(state_path, "w") as f:
            json.dump(workflow_state.to_dict(), f, indent=2)


def delete_workflow_state(workflow_name: str) -> bool:
    """Delete workflow state directory for a workflow.

    Removes the entire workflow state directory including state file,
    YAML copy, and logs, with exclusive file locking.

    Args:
        workflow_name: Name of the workflow

    Returns:
        True if directory was deleted, False if it didn't exist
    """
    import shutil
    with workflow_file_lock():
        state_dir = get_workflow_state_dir(workflow_name)
        if state_dir.exists():
            shutil.rmtree(state_dir)
            return True
        return False


def list_workflow_states() -> list[WorkflowState]:
    """List all workflow states.

    Loads all workflow state files from the workflows directory
    with exclusive file locking.

    Returns:
        List of WorkflowState objects, sorted by name
    """
    with workflow_file_lock():
        if not WORKFLOWS_DIR.exists():
            return []

        states = []
        for state_dir in WORKFLOWS_DIR.iterdir():
            if not state_dir.is_dir():
                continue
            state_file = state_dir / "state.json"
            if not state_file.exists():
                continue
            try:
                with open(state_file, "r") as f:
                    data = json.load(f)
                    states.append(WorkflowState.from_dict(data))
            except (json.JSONDecodeError, KeyError):
                # Skip invalid state files
                continue

        return sorted(states, key=lambda s: s.name)


def create_workflow_state(
    definition: WorkflowDefinition,
    yaml_path: str,
    yaml_content: str,
) -> WorkflowState:
    """Create a new WorkflowState from a workflow definition.

    Creates the workflow state directory, copies the original YAML file,
    computes the hash for change detection, and initializes stage states.

    Args:
        definition: The parsed workflow definition
        yaml_path: Path to the original workflow YAML file
        yaml_content: Raw content of the workflow YAML file

    Returns:
        Initialized WorkflowState ready for execution
    """
    # Initialize stage states
    stages = {}
    for stage_def in definition.stages:
        stages[stage_def.name] = StageState(status="pending")

    # Compute hash for change detection
    workflow_hash = compute_workflow_hash(yaml_content)

    # Create workflow state
    workflow_state = WorkflowState(
        name=definition.name,
        status="created",
        current_stage=None,
        current_stage_index=0,
        created_at=datetime.now(timezone.utc).isoformat(),
        started_at=None,
        scheduled_for=None,
        completed_at=None,
        stages=stages,
        workflow_file=str(Path(yaml_path).resolve()),
        workflow_hash=workflow_hash,
    )

    # Create state directory and copy YAML
    with workflow_file_lock():
        state_dir = get_workflow_state_dir(definition.name)
        state_dir.mkdir(parents=True, exist_ok=True)

        # Create logs directory
        logs_dir = get_workflow_logs_dir(definition.name)
        logs_dir.mkdir(parents=True, exist_ok=True)

        # Copy YAML to state directory
        yaml_copy_path = get_workflow_yaml_copy_path(definition.name)
        with open(yaml_copy_path, "w") as f:
            f.write(yaml_content)

        # Save state
        state_path = get_workflow_state_path(definition.name)
        with open(state_path, "w") as f:
            json.dump(workflow_state.to_dict(), f, indent=2)

    return workflow_state


def workflow_exists(workflow_name: str) -> bool:
    """Check if a workflow with the given name already exists.

    Args:
        workflow_name: Name of the workflow to check

    Returns:
        True if a workflow state exists, False otherwise
    """
    with workflow_file_lock():
        state_path = get_workflow_state_path(workflow_name)
        return state_path.exists()


def run_heartbeat_monitor(worker_name: str) -> None:
    """Run the heartbeat monitor loop for a worker.

    This function runs as a daemon process and:
    1. Checks every 30 seconds (poll interval)
    2. Sends heartbeat message at the configured interval
    3. Checks for expiration and auto-stops
    4. Detects worker death and auto-stops

    Uses monotonic time to avoid clock drift issues.

    Args:
        worker_name: Name of the worker to monitor
    """
    # Poll interval - check state every 30 seconds
    POLL_INTERVAL = 30

    # Use monotonic time to track when next beat should occur
    # This avoids issues with system clock changes
    last_beat_monotonic = time.monotonic()

    while True:
        # Sleep for poll interval
        time.sleep(POLL_INTERVAL)

        # Load heartbeat state
        heartbeat_state = load_heartbeat_state(worker_name)
        if heartbeat_state is None:
            # State file deleted, exit
            return

        # Check status
        if heartbeat_state.status == "stopped":
            return
        if heartbeat_state.status == "paused":
            # Reset beat tracking when paused so next beat happens
            # at full interval after resume
            last_beat_monotonic = time.monotonic()
            continue
        if heartbeat_state.status == "expired":
            return

        # Check expiration
        if heartbeat_state.expire_at:
            expire_dt = datetime.fromisoformat(heartbeat_state.expire_at.replace('Z', '+00:00'))
            now = datetime.now(timezone.utc)
            if now >= expire_dt:
                heartbeat_state.status = "expired"
                save_heartbeat_state(heartbeat_state)
                return

        # Check if worker is still alive
        state = State()
        worker = state.get_worker(worker_name)
        if worker is None:
            # Worker no longer exists in state
            heartbeat_state.status = "stopped"
            save_heartbeat_state(heartbeat_state)
            return

        # Check actual worker status
        actual_status = refresh_worker_status(worker)
        if actual_status != "running":
            # Worker died
            heartbeat_state.status = "stopped"
            save_heartbeat_state(heartbeat_state)
            return

        # Check if it's time to send a beat
        elapsed = time.monotonic() - last_beat_monotonic
        if elapsed >= heartbeat_state.interval_seconds:
            # Time to send a beat
            try:
                tmux_send(
                    worker.tmux.session,
                    worker.tmux.window,
                    heartbeat_state.message,
                    enter=True,
                    socket=worker.tmux.socket
                )
                # Update state
                heartbeat_state.last_beat_at = datetime.now(timezone.utc).isoformat()
                heartbeat_state.beat_count += 1
                save_heartbeat_state(heartbeat_state)

                # Reset monotonic timer
                last_beat_monotonic = time.monotonic()
            except Exception:
                # Failed to send, worker may have died
                # Will be detected on next iteration
                pass


def start_heartbeat_monitor(worker_name: str) -> int:
    """Start the heartbeat monitor as a daemon process.

    Spawns a background process that runs run_heartbeat_monitor.
    The process is double-forked to become a proper daemon.

    Args:
        worker_name: Name of the worker to monitor

    Returns:
        PID of the monitor process
    """
    # Fork to create child process
    pid = os.fork()
    if pid > 0:
        # Parent process - return child PID
        return pid

    # Child process - become session leader
    os.setsid()

    # Fork again to prevent zombie processes
    pid = os.fork()
    if pid > 0:
        # Exit first child
        os._exit(0)

    # Grandchild process - this is the actual daemon
    # Close standard file descriptors
    sys.stdin.close()
    sys.stdout.close()
    sys.stderr.close()

    # Redirect to /dev/null
    devnull = os.open(os.devnull, os.O_RDWR)
    os.dup2(devnull, 0)
    os.dup2(devnull, 1)
    os.dup2(devnull, 2)
    os.close(devnull)

    # Run the monitor loop
    try:
        run_heartbeat_monitor(worker_name)
    except Exception:
        pass
    finally:
        os._exit(0)


def stop_heartbeat_monitor(heartbeat_state: HeartbeatState) -> bool:
    """Stop the heartbeat monitor process.

    Terminates the background monitor process if it's running.

    Args:
        heartbeat_state: HeartbeatState with monitor_pid

    Returns:
        True if process was stopped, False if not running
    """
    if heartbeat_state.monitor_pid is None:
        return False

    try:
        # Check if process is running
        os.kill(heartbeat_state.monitor_pid, 0)
        # Send SIGTERM
        os.kill(heartbeat_state.monitor_pid, signal.SIGTERM)
        return True
    except OSError:
        # Process not running
        return False


def is_heartbeat_monitor_running(heartbeat_state: HeartbeatState) -> bool:
    """Check if the heartbeat monitor process is still running.

    Args:
        heartbeat_state: HeartbeatState with monitor_pid

    Returns:
        True if process is running, False otherwise
    """
    if heartbeat_state.monitor_pid is None:
        return False

    try:
        # Signal 0 checks if process exists without sending a signal
        os.kill(heartbeat_state.monitor_pid, 0)
        return True
    except OSError:
        return False


def resume_active_heartbeats() -> int:
    """Resume heartbeat monitors for active heartbeats.

    Called on swarm startup to restart monitor processes for heartbeats
    that were active when swarm last ran. This handles the case where
    the system rebooted or the monitor processes were killed.

    Returns:
        Number of heartbeats resumed
    """
    states = list_heartbeat_states()
    resumed_count = 0

    for heartbeat_state in states:
        # Only resume active heartbeats
        if heartbeat_state.status != "active":
            continue

        # Check if monitor is already running
        if is_heartbeat_monitor_running(heartbeat_state):
            continue

        # Check if worker is still alive before resuming
        state = State()
        worker = state.get_worker(heartbeat_state.worker_name)
        if worker is None:
            # Worker no longer exists, mark heartbeat as stopped
            heartbeat_state.status = "stopped"
            heartbeat_state.monitor_pid = None
            save_heartbeat_state(heartbeat_state)
            continue

        # Check actual worker status
        actual_status = refresh_worker_status(worker)
        if actual_status != "running":
            # Worker is not running, mark heartbeat as stopped
            heartbeat_state.status = "stopped"
            heartbeat_state.monitor_pid = None
            save_heartbeat_state(heartbeat_state)
            continue

        # Check if heartbeat has expired
        if heartbeat_state.expire_at:
            expire_dt = datetime.fromisoformat(
                heartbeat_state.expire_at.replace('Z', '+00:00')
            )
            now = datetime.now(timezone.utc)
            if now >= expire_dt:
                heartbeat_state.status = "expired"
                heartbeat_state.monitor_pid = None
                save_heartbeat_state(heartbeat_state)
                continue

        # Restart the monitor process
        monitor_pid = start_heartbeat_monitor(heartbeat_state.worker_name)
        heartbeat_state.monitor_pid = monitor_pid
        save_heartbeat_state(heartbeat_state)
        resumed_count += 1

    return resumed_count


def check_interrupted_workflows() -> list[WorkflowState]:
    """Check for workflows that were interrupted (running or scheduled).

    Called on swarm startup to detect workflows that were active when
    the system last ran. These workflows may need to be resumed.

    Returns:
        List of WorkflowState objects that are in 'running' or 'scheduled' status
    """
    states = list_workflow_states()
    interrupted = []

    for workflow_state in states:
        # Only include running or scheduled workflows
        if workflow_state.status in ("running", "scheduled"):
            interrupted.append(workflow_state)

    return interrupted


def notify_interrupted_workflows() -> int:
    """Notify user about interrupted workflows on startup.

    Called on swarm startup to alert users about workflows that may
    need to be resumed. Prints a message if there are interrupted
    workflows and suggests the resume-all command.

    Returns:
        Number of interrupted workflows found
    """
    interrupted = check_interrupted_workflows()
    if not interrupted:
        return 0

    count = len(interrupted)
    workflow_word = "workflow" if count == 1 else "workflows"
    print(f"swarm: {count} interrupted {workflow_word} found", file=sys.stderr)
    for workflow_state in interrupted:
        stage_info = ""
        if workflow_state.status == "running" and workflow_state.current_stage:
            stage_info = f" (stage: {workflow_state.current_stage})"
        elif workflow_state.status == "scheduled" and workflow_state.scheduled_for:
            stage_info = f" (scheduled: {workflow_state.scheduled_for})"
        print(f"swarm:   - {workflow_state.name}: {workflow_state.status}{stage_info}", file=sys.stderr)
    print(f"swarm: use 'swarm workflow resume-all' to resume", file=sys.stderr)

    return count


def parse_duration(duration_str: str) -> int:
    """Parse a duration string into seconds.

    Accepts formats:
    - "4h", "30m", "90s" - single unit
    - "1h30m", "2h30m15s" - combinations
    - "3600" - bare number treated as seconds

    Args:
        duration_str: Duration string to parse

    Returns:
        Duration in seconds

    Raises:
        ValueError: If duration format is invalid or value is <= 0
    """
    if not duration_str:
        raise ValueError("empty duration string")

    duration_str = duration_str.strip().lower()

    # Try bare number (seconds)
    if duration_str.isdigit():
        seconds = int(duration_str)
        if seconds <= 0:
            raise ValueError("duration must be positive")
        return seconds

    # Parse duration with units (e.g., "1h30m", "4h", "30m", "90s")
    total_seconds = 0
    remaining = duration_str
    units = [('h', 3600), ('m', 60), ('s', 1)]

    for unit, multiplier in units:
        if unit in remaining:
            parts = remaining.split(unit, 1)
            if parts[0]:
                try:
                    value = int(parts[0])
                    total_seconds += value * multiplier
                except ValueError:
                    raise ValueError(f"invalid duration: '{duration_str}'")
            remaining = parts[1]

    # Check if there's leftover unparsed content
    if remaining and not remaining.isspace():
        raise ValueError(f"invalid duration: '{duration_str}'")

    if total_seconds <= 0:
        raise ValueError("duration must be positive")

    return total_seconds


def parse_schedule_time(time_str: str) -> datetime:
    """Parse a schedule time string into a datetime.

    Accepts HH:MM format (24-hour). If the time has already passed today,
    schedules for tomorrow at that time.

    Args:
        time_str: Time string in HH:MM format (e.g., "02:00", "14:30")

    Returns:
        datetime: The next occurrence of that time (today or tomorrow)

    Raises:
        ValueError: If time format is invalid
    """
    if not time_str:
        raise ValueError("empty time string")

    time_str = time_str.strip()

    # Parse HH:MM format
    import re
    match = re.match(r'^(\d{1,2}):(\d{2})$', time_str)
    if not match:
        raise ValueError(f"invalid time format '{time_str}' (use HH:MM)")

    try:
        hour = int(match.group(1))
        minute = int(match.group(2))
    except ValueError:
        raise ValueError(f"invalid time format '{time_str}' (use HH:MM)")

    if hour < 0 or hour > 23:
        raise ValueError(f"invalid hour {hour} (must be 0-23)")
    if minute < 0 or minute > 59:
        raise ValueError(f"invalid minute {minute} (must be 0-59)")

    now = datetime.now(timezone.utc)
    today = now.date()

    # Create time for today at the specified hour:minute (in UTC)
    scheduled = datetime(
        year=today.year,
        month=today.month,
        day=today.day,
        hour=hour,
        minute=minute,
        tzinfo=timezone.utc
    )

    # If the time has passed today, schedule for tomorrow
    if scheduled <= now:
        scheduled = scheduled + timedelta(days=1)

    return scheduled


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


def _check_and_fix_core_bare() -> bool:
    """Check if core.bare is misconfigured and fix it.

    Returns:
        True if core.bare was fixed, False if no fix was needed.
    """
    result = subprocess.run(
        ["git", "config", "--get", "core.bare"],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0 and result.stdout.strip().lower() == "true":
        # Fix the misconfiguration
        subprocess.run(
            ["git", "config", "core.bare", "false"],
            capture_output=True,
            text=True,
            check=True,
        )
        print("swarm: warning: Fixed core.bare=true in git config", file=sys.stderr)
        return True
    return False


def _is_truly_bare_repo() -> bool:
    """Check if this is actually a bare repository (not just misconfigured).

    Returns:
        True if the repository is genuinely bare (no working directory).
    """
    # A bare repo has no worktree, check if we can get the git dir
    result = subprocess.run(
        ["git", "rev-parse", "--is-bare-repository"],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0 and result.stdout.strip().lower() == "true":
        # Double-check: a truly bare repo won't have a working tree
        wt_result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
        )
        # If we can't get the toplevel, it's truly bare
        return wt_result.returncode != 0
    return False


def create_worktree(path: Path, branch: str) -> None:
    """Create a git worktree.

    Creates a new worktree at the specified path with the given branch name.
    If the branch doesn't exist, it's created from the current HEAD.

    Raises:
        RuntimeError: If worktree creation fails or the repository is bare.
    """
    path = Path(path)

    # Step 1: Check for and fix core.bare misconfiguration
    _check_and_fix_core_bare()

    # Step 2: Check if this is a truly bare repository
    if _is_truly_bare_repo():
        raise RuntimeError(
            "Cannot create worktree: repository is bare. "
            "Worktrees require a working directory."
        )

    # Step 3: Create parent directory if needed
    path.parent.mkdir(parents=True, exist_ok=True)

    # Step 4: Try to create with new branch first, fall back to existing branch
    result = subprocess.run(
        ["git", "worktree", "add", "-b", branch, str(path)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        # Branch might already exist, try without -b
        result = subprocess.run(
            ["git", "worktree", "add", str(path), branch],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            # Clean up any partial state
            subprocess.run(
                ["git", "worktree", "prune"],
                capture_output=True,
                text=True,
            )
            # Remove partial directory if it was created but is empty/invalid
            if path.exists():
                try:
                    # Only remove if it's not a valid git worktree
                    git_check = subprocess.run(
                        ["git", "-C", str(path), "rev-parse", "--git-dir"],
                        capture_output=True,
                        text=True,
                    )
                    if git_check.returncode != 0:
                        import shutil
                        shutil.rmtree(path, ignore_errors=True)
                except Exception:
                    pass

            raise RuntimeError(
                f"Failed to create worktree at {path}: {result.stderr.strip()}"
            )

    # Step 5: Validate worktree was created successfully
    if not path.exists():
        # Clean up git's worktree registry
        subprocess.run(
            ["git", "worktree", "prune"],
            capture_output=True,
            text=True,
        )
        raise RuntimeError(
            f"Worktree creation failed: directory not created at {path}. "
            "Try running 'git worktree prune' and retry."
        )

    # Verify it's actually a valid git worktree
    git_check = subprocess.run(
        ["git", "-C", str(path), "rev-parse", "--git-dir"],
        capture_output=True,
        text=True,
    )
    if git_check.returncode != 0:
        # Clean up the invalid directory
        import shutil
        shutil.rmtree(path, ignore_errors=True)
        subprocess.run(
            ["git", "worktree", "prune"],
            capture_output=True,
            text=True,
        )
        raise RuntimeError(
            f"Worktree creation failed: {path} is not a valid git worktree. "
            "Try running 'git worktree prune' and retry."
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
        # Delay to ensure text is fully received before Enter
        # Longer delay for multiline content which takes more time to process
        delay = 0.5 if '\n' in text else 0.1
        time.sleep(delay)
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


def time_until(iso_str: str) -> str:
    """Convert ISO timestamp to human-readable time until.

    Args:
        iso_str: ISO format timestamp string (future time)

    Returns:
        Human-readable time delta (e.g., "in 5m", "in 2h", "in 3d")
        or "now" if time has passed
    """
    dt = datetime.fromisoformat(iso_str.replace('Z', '+00:00'))
    now = datetime.now(timezone.utc)
    delta = dt - now
    seconds = int(delta.total_seconds())

    if seconds <= 0:
        return "now"
    elif seconds < 60:
        return f"in {seconds}s"
    elif seconds < 3600:
        return f"in {seconds // 60}m"
    elif seconds < 86400:
        return f"in {seconds // 3600}h"
    else:
        return f"in {seconds // 86400}d"


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        prog="swarm",
        description=ROOT_HELP_DESCRIPTION,
        epilog=ROOT_HELP_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # spawn
    spawn_p = subparsers.add_parser(
        "spawn",
        help="Spawn a new worker",
        description=SPAWN_HELP_DESCRIPTION,
        epilog=SPAWN_HELP_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    spawn_p.add_argument("--name", required=True,
                        help="Unique identifier for this worker. Used as window name "
                             "(tmux), worktree directory, and branch name by default.")
    spawn_p.add_argument("--tmux", action="store_true",
                        help="Run in tmux window. Default: false. Enables send, logs, "
                             "attach commands. Required for --ready-wait.")
    spawn_p.add_argument("--session", default=None,
                        help="Tmux session name. Default: hash-based unique name. "
                             "Workers in same session share a tmux server.")
    spawn_p.add_argument("--tmux-socket", default=None,
                        help="Tmux socket name for isolation. Default: none (uses "
                             "default tmux server). Useful for testing.")
    spawn_p.add_argument("--worktree", action="store_true",
                        help="Create isolated git worktree for this worker. Default: "
                             "false. Creates <repo>-worktrees/<name>/ with its own "
                             "branch. Enables parallel work without conflicts.")
    spawn_p.add_argument("--branch",
                        help="Branch name for worktree. Default: same as --name. "
                             "Only used with --worktree.")
    spawn_p.add_argument("--worktree-dir", default=None,
                        help="Parent directory for worktrees. Default: <repo>-worktrees "
                             "(sibling to repository). Worktree created at "
                             "<worktree-dir>/<name>/.")
    spawn_p.add_argument("--tag", action="append", default=[], dest="tags",
                        help="Tag for filtering workers. Repeatable. Use with "
                             "'swarm ls --tag <tag>' to filter.")
    spawn_p.add_argument("--env", action="append", default=[],
                        help="Environment variable in KEY=VAL format. Repeatable. "
                             "Passed to the spawned command.")
    spawn_p.add_argument("--cwd",
                        help="Working directory for the command. Default: current "
                             "directory. Ignored when --worktree is used.")
    spawn_p.add_argument("--ready-wait", action="store_true",
                        help="Wait for agent to be ready before returning. Default: "
                             "false. Only works with --tmux. Detects ready patterns "
                             "like '$ ' prompt.")
    spawn_p.add_argument("--ready-timeout", type=int, default=120,
                        help="Timeout in seconds for --ready-wait. Default: 120 "
                             "(suitable for Claude Code startup). Worker created "
                             "regardless of timeout, but warning printed.")
    spawn_p.add_argument("--heartbeat",
                        help="Start heartbeat after spawn with this interval. "
                             "Sends periodic nudges to help agent recover from "
                             "rate limits. Format: '4h', '30m', '3600s'. "
                             "Requires --tmux.")
    spawn_p.add_argument("--heartbeat-expire",
                        help="Stop heartbeat after this duration. Default: no "
                             "expiration. Recommended for unattended work to "
                             "prevent infinite nudging. Format: '24h', '8h'.")
    spawn_p.add_argument("--heartbeat-message", default="continue",
                        help="Message to send on each heartbeat. Default: "
                             "'continue'. Use a custom message to prompt "
                             "specific recovery behavior.")
    spawn_p.add_argument("cmd", nargs=argparse.REMAINDER, metavar="-- command...",
                        help="Command to execute. Place after '--' separator. "
                             "Example: -- claude")

    # ls
    ls_p = subparsers.add_parser(
        "ls",
        help="List workers",
        description=LS_HELP_DESCRIPTION,
        epilog=LS_HELP_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ls_p.add_argument("--format", choices=["table", "json", "names"], default="table",
                     help="Output format. Default: table. Use 'json' for full worker "
                          "details, 'names' for simple list (one per line).")
    ls_p.add_argument("--status", choices=["running", "stopped", "all"], default="all",
                     help="Filter by worker status. Default: all. Status is refreshed "
                          "by checking actual tmux/process state.")
    ls_p.add_argument("--tag",
                     help="Filter by tag (exact match). Only workers with this tag "
                          "in their tag list are shown.")

    # status
    status_p = subparsers.add_parser(
        "status",
        help="Get worker status",
        description=STATUS_HELP_DESCRIPTION,
        epilog=STATUS_HELP_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    status_p.add_argument("name",
                         help="Worker name. Must match a registered worker exactly.")

    # send
    send_p = subparsers.add_parser(
        "send",
        help="Send text to tmux worker",
        description=SEND_HELP_DESCRIPTION,
        epilog=SEND_HELP_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    send_p.add_argument("name", nargs="?",
                       help="Worker name. Required unless using --all. Must be a "
                            "tmux-based worker (spawned with --tmux).")
    send_p.add_argument("text",
                       help="Text to send to the worker. Sent literally via tmux "
                            "send-keys. Special characters and quotes are handled correctly.")
    send_p.add_argument("--no-enter", action="store_true",
                       help="Don't append Enter key after the text. Default: false "
                            "(Enter is sent). Useful for partial input or when you "
                            "want to build up a command incrementally.")
    send_p.add_argument("--all", action="store_true",
                       help="Broadcast to all running tmux workers. Non-tmux and "
                            "non-running workers are silently skipped. Cannot be "
                            "used with a worker name.")

    # interrupt
    int_p = subparsers.add_parser(
        "interrupt",
        help="Send Ctrl-C (interrupt) to worker",
        description=INTERRUPT_HELP_DESCRIPTION,
        epilog=INTERRUPT_HELP_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    int_p.add_argument("name", nargs="?",
                       help="Worker name to interrupt. Required unless --all is used. "
                            "Worker must be a tmux worker and currently running.")
    int_p.add_argument("--all", action="store_true",
                       help="Send interrupt to all running tmux workers. Non-tmux "
                            "workers and non-running workers are silently skipped. "
                            "Cannot be used with a worker name.")

    # eof
    eof_p = subparsers.add_parser(
        "eof",
        help="Send Ctrl-D to worker",
        description=EOF_HELP_DESCRIPTION,
        epilog=EOF_HELP_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    eof_p.add_argument("name",
                       help="Worker name to send EOF to. Worker must be a tmux worker "
                            "and currently running. Use 'swarm ls' to see available workers.")

    # attach
    attach_p = subparsers.add_parser(
        "attach",
        help="Attach to worker tmux window",
        description=ATTACH_HELP_DESCRIPTION,
        epilog=ATTACH_HELP_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    attach_p.add_argument("name",
                          help="Worker name to attach to. Worker must be a tmux worker "
                               "and currently running. Use 'swarm ls' to see available workers.")

    # logs
    logs_p = subparsers.add_parser(
        "logs",
        help="View worker output",
        description=LOGS_HELP_DESCRIPTION,
        epilog=LOGS_HELP_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    logs_p.add_argument("name",
                       help="Worker name. Must match a registered worker exactly.")
    logs_p.add_argument("--history", action="store_true",
                       help="Include scrollback buffer for tmux workers. Default: false "
                            "(shows only visible pane content). For non-tmux workers, "
                            "the full log file is always read regardless of this flag.")
    logs_p.add_argument("--lines", type=int, default=1000,
                       help="Number of scrollback lines to capture. Default: 1000. "
                            "Only used with --history for tmux workers. Increase for "
                            "longer-running workers with more output.")
    logs_p.add_argument("--follow", action="store_true",
                       help="Continuously display new output (like tail -f). Default: false. "
                            "Press Ctrl-C to stop following. For tmux workers, refreshes "
                            "every 1 second. For non-tmux workers, uses tail -f.")

    # kill
    kill_p = subparsers.add_parser(
        "kill",
        help="Stop running workers",
        description=KILL_HELP_DESCRIPTION,
        epilog=KILL_HELP_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    kill_p.add_argument("name", nargs="?",
                       help="Worker name to kill. Required unless using --all.")
    kill_p.add_argument("--rm-worktree", action="store_true",
                       help="Remove the git worktree after killing. Default: false. "
                            "Fails if worktree has uncommitted changes unless "
                            "--force-dirty is also specified.")
    kill_p.add_argument("--force-dirty", action="store_true",
                       help="Force removal of worktree even with uncommitted changes. "
                            "WARNING: This permanently deletes uncommitted work! "
                            "Only use when you're sure changes are not needed.")
    kill_p.add_argument("--all", action="store_true",
                       help="Kill all workers. Cannot be used with a worker name.")

    # wait
    wait_p = subparsers.add_parser(
        "wait",
        help="Wait for worker to finish",
        description=WAIT_HELP_DESCRIPTION,
        epilog=WAIT_HELP_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    wait_p.add_argument("name", nargs="?",
                       help="Worker name to wait for. Required unless using --all. "
                            "Worker must be registered in swarm state.")
    wait_p.add_argument("--timeout", type=int,
                       help="Maximum time to wait in seconds. Default: no limit (wait "
                            "forever). If timeout is reached with workers still running, "
                            "exits with code 1. Use 0 for no timeout (same as default).")
    wait_p.add_argument("--all", action="store_true",
                       help="Wait for all running workers to finish. Cannot be combined "
                            "with a worker name. Useful for coordinating parallel workers.")

    # clean
    clean_p = subparsers.add_parser(
        "clean",
        help="Remove stopped workers from state",
        description=CLEAN_HELP_DESCRIPTION,
        epilog=CLEAN_HELP_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    clean_p.add_argument("name", nargs="?",
                        help="Worker name to clean. Required unless using --all. "
                             "Worker must be stopped (not running).")
    clean_p.add_argument("--rm-worktree", action="store_true", default=True,
                        help="Remove git worktree directory. Default: true. "
                             "Use --no-rm-worktree to preserve worktree while "
                             "removing worker from state.")
    clean_p.add_argument("--no-rm-worktree", action="store_false", dest="rm_worktree",
                        help="Preserve git worktree directory while removing worker "
                             "from state. Useful for manual cleanup or inspection.")
    clean_p.add_argument("--force-dirty", action="store_true",
                        help="Force removal of worktree even with uncommitted changes. "
                             "WARNING: This permanently deletes any uncommitted work!")
    clean_p.add_argument("--all", action="store_true",
                        help="Clean all stopped workers. Running workers are skipped "
                             "with a warning. Cannot be combined with a worker name.")

    # respawn
    respawn_p = subparsers.add_parser(
        "respawn",
        help="Restart a stopped worker with original config",
        description=RESPAWN_HELP_DESCRIPTION,
        epilog=RESPAWN_HELP_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    respawn_p.add_argument("name",
                          help="Worker name to respawn. Must exist in swarm state. "
                               "Worker can be stopped or running (running workers "
                               "are killed first).")
    respawn_p.add_argument("--clean-first", action="store_true",
                          help="Remove existing worktree before respawning for a fresh "
                               "checkout. Default: false (reuse existing worktree). "
                               "Fails if worktree has uncommitted changes unless "
                               "--force-dirty is also specified.")
    respawn_p.add_argument("--force-dirty", action="store_true",
                          help="Force removal of worktree even with uncommitted changes. "
                               "Requires --clean-first. WARNING: This permanently deletes "
                               "uncommitted work! Only use when you're sure changes are "
                               "not needed.")

    # init
    init_p = subparsers.add_parser(
        "init",
        help="Initialize swarm in project",
        description=INIT_HELP_DESCRIPTION,
        epilog=INIT_HELP_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    init_p.add_argument("--dry-run", action="store_true",
                        help="Preview what would be done without making changes. "
                             "Shows target file and action (create/append/update).")
    init_p.add_argument("--file", choices=["AGENTS.md", "CLAUDE.md"], default=None,
                        help="Target file for swarm instructions. Default: auto-detect "
                             "(checks AGENTS.md, then CLAUDE.md, creates AGENTS.md if neither exists).")
    init_p.add_argument("--force", action="store_true",
                        help="Replace existing swarm instructions section with latest version. "
                             "Without --force, init is idempotent and skips if marker exists.")

    # ralph - autonomous agent looping (Ralph Wiggum pattern)
    ralph_p = subparsers.add_parser(
        "ralph",
        help="Ralph loop management (autonomous agent looping)",
        description=RALPH_HELP_DESCRIPTION,
        epilog=RALPH_HELP_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ralph_subparsers = ralph_p.add_subparsers(dest="ralph_command", required=True)

    # ralph init - create PROMPT.md
    ralph_init_p = ralph_subparsers.add_parser(
        "init",
        help="Create PROMPT.md with starter template",
        epilog=RALPH_INIT_HELP_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ralph_init_p.add_argument("--force", action="store_true",
                              help="Overwrite existing PROMPT.md")

    # ralph template - output template to stdout
    ralph_subparsers.add_parser(
        "template",
        help="Output prompt template to stdout",
        epilog=RALPH_TEMPLATE_HELP_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    # ralph status - show ralph loop status
    ralph_status_p = ralph_subparsers.add_parser(
        "status",
        help="Show ralph loop status for a worker",
        epilog=RALPH_STATUS_HELP_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ralph_status_p.add_argument("name", help="Worker name")

    # ralph pause - pause the ralph loop
    ralph_pause_p = ralph_subparsers.add_parser(
        "pause",
        help="Pause ralph loop for a worker",
        epilog=RALPH_PAUSE_HELP_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ralph_pause_p.add_argument("name", help="Worker name")

    # ralph resume - resume the ralph loop
    ralph_resume_p = ralph_subparsers.add_parser(
        "resume",
        help="Resume ralph loop for a worker",
        epilog=RALPH_RESUME_HELP_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ralph_resume_p.add_argument("name", help="Worker name")

    # ralph run - run the ralph loop (main outer loop execution)
    ralph_run_p = ralph_subparsers.add_parser(
        "run",
        help="Run the ralph loop for a worker",
        epilog=RALPH_RUN_HELP_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ralph_run_p.add_argument("name", help="Worker name")

    # ralph list - list all ralph workers
    ralph_list_p = ralph_subparsers.add_parser(
        "list",
        help="List all ralph workers",
        epilog=RALPH_LIST_HELP_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ralph_list_p.add_argument("--format", choices=["table", "json", "names"],
                              default="table", help="Output format (default: table)")
    ralph_list_p.add_argument("--status", choices=["all", "running", "paused", "stopped", "failed"],
                              default="all", help="Filter by ralph status (default: all)")

    # ralph spawn - spawn a new ralph worker
    ralph_spawn_p = ralph_subparsers.add_parser(
        "spawn",
        help="Spawn a new ralph worker",
        description=RALPH_SPAWN_HELP_DESCRIPTION,
        epilog=RALPH_SPAWN_HELP_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ralph_spawn_p.add_argument("--name", required=True, help="Unique identifier for this worker")
    ralph_spawn_p.add_argument("--prompt-file", required=True,
                               help="Path to prompt file (required)")
    ralph_spawn_p.add_argument("--max-iterations", type=int, required=True,
                               help="Maximum loop iterations (required)")
    ralph_spawn_p.add_argument("--inactivity-timeout", type=int, default=60,
                               help="Screen stability timeout in seconds (default: 60)")
    ralph_spawn_p.add_argument("--done-pattern", type=str, default=None,
                               help="Regex pattern to stop ralph loop when matched in output")
    ralph_spawn_p.add_argument("--check-done-continuous", action="store_true",
                               help="Check done pattern during monitoring, not just after exit")
    ralph_spawn_p.add_argument("--no-run", action="store_true",
                               help="Spawn worker but don't start monitoring loop (default: auto-start)")
    ralph_spawn_p.add_argument("--session", default=None,
                               help="Tmux session name (default: hash-based isolation)")
    ralph_spawn_p.add_argument("--tmux-socket", default=None,
                               help="Tmux socket name (for testing/isolation)")
    ralph_spawn_p.add_argument("--worktree", action="store_true",
                               help="Create a git worktree")
    ralph_spawn_p.add_argument("--branch", help="Branch name for worktree (default: same as --name)")
    ralph_spawn_p.add_argument("--worktree-dir", default=None,
                               help="Parent dir for worktrees (default: <repo>-worktrees)")
    ralph_spawn_p.add_argument("--tag", action="append", default=[], dest="tags",
                               help="Tag for filtering (repeatable)")
    ralph_spawn_p.add_argument("--env", action="append", default=[],
                               help="Environment variable KEY=VAL (repeatable)")
    ralph_spawn_p.add_argument("--cwd", help="Working directory")
    ralph_spawn_p.add_argument("--ready-wait", action="store_true",
                               help="Wait for agent to be ready before returning")
    ralph_spawn_p.add_argument("--ready-timeout", type=int, default=120,
                               help="Timeout in seconds for --ready-wait (default: 120)")
    ralph_spawn_p.add_argument("--heartbeat",
                               help='Heartbeat interval (e.g., "4h", "30m"). Sends periodic nudges to help recover from rate limits.')
    ralph_spawn_p.add_argument("--heartbeat-expire",
                               help='Stop heartbeat after this duration (e.g., "24h"). Default: no expiration')
    ralph_spawn_p.add_argument("--heartbeat-message", default="continue",
                               help='Message to send on each heartbeat. Default: "continue"')
    ralph_spawn_p.add_argument("cmd", nargs=argparse.REMAINDER, metavar="-- command...",
                               help="Command to run (after --)")

    # heartbeat - periodic nudges to workers
    heartbeat_p = subparsers.add_parser(
        "heartbeat",
        help="Periodic nudges to help workers recover from rate limits",
        description=HEARTBEAT_HELP_DESCRIPTION,
        epilog=HEARTBEAT_HELP_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    heartbeat_subparsers = heartbeat_p.add_subparsers(dest="heartbeat_command", required=True)

    # heartbeat start
    heartbeat_start_p = heartbeat_subparsers.add_parser(
        "start",
        help="Start heartbeat for a worker",
        description=HEARTBEAT_START_HELP_DESCRIPTION,
        epilog=HEARTBEAT_START_HELP_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    heartbeat_start_p.add_argument("worker", help="Worker name to send heartbeats to")
    heartbeat_start_p.add_argument("--interval", required=True,
                                   help='Time between heartbeats (e.g., "4h", "30m", "3600s")')
    heartbeat_start_p.add_argument("--expire",
                                   help='Stop heartbeat after this duration (e.g., "24h"). Default: no expiration')
    heartbeat_start_p.add_argument("--message", default="continue",
                                   help='Message to send on each beat. Default: "continue"')
    heartbeat_start_p.add_argument("--force", action="store_true",
                                   help="Replace existing heartbeat if one exists")

    # heartbeat stop
    heartbeat_stop_p = heartbeat_subparsers.add_parser(
        "stop",
        help="Stop heartbeat for a worker",
        description=HEARTBEAT_STOP_HELP_DESCRIPTION,
        epilog=HEARTBEAT_STOP_HELP_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    heartbeat_stop_p.add_argument("worker", help="Worker name")

    # heartbeat list
    heartbeat_list_p = heartbeat_subparsers.add_parser(
        "list",
        help="List all heartbeats",
        description=HEARTBEAT_LIST_HELP_DESCRIPTION,
        epilog=HEARTBEAT_LIST_HELP_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    heartbeat_list_p.add_argument("--format", choices=["table", "json"],
                                  default="table", help="Output format (default: table)")

    # heartbeat status
    heartbeat_status_p = heartbeat_subparsers.add_parser(
        "status",
        help="Show heartbeat status",
        description=HEARTBEAT_STATUS_HELP_DESCRIPTION,
        epilog=HEARTBEAT_STATUS_HELP_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    heartbeat_status_p.add_argument("worker", help="Worker name")
    heartbeat_status_p.add_argument("--format", choices=["text", "json"],
                                    default="text", help="Output format (default: text)")

    # heartbeat pause
    heartbeat_pause_p = heartbeat_subparsers.add_parser(
        "pause",
        help="Pause heartbeat temporarily",
        description=HEARTBEAT_PAUSE_HELP_DESCRIPTION,
        epilog=HEARTBEAT_PAUSE_HELP_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    heartbeat_pause_p.add_argument("worker", help="Worker name")

    # heartbeat resume
    heartbeat_resume_p = heartbeat_subparsers.add_parser(
        "resume",
        help="Resume paused heartbeat",
        description=HEARTBEAT_RESUME_HELP_DESCRIPTION,
        epilog=HEARTBEAT_RESUME_HELP_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    heartbeat_resume_p.add_argument("worker", help="Worker name")

    # workflow - multi-stage pipelines
    workflow_p = subparsers.add_parser(
        "workflow",
        help="Multi-stage agent pipelines with scheduling",
        description=WORKFLOW_HELP_DESCRIPTION,
        epilog=WORKFLOW_HELP_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    workflow_subparsers = workflow_p.add_subparsers(dest="workflow_command", required=True)

    # workflow validate
    workflow_validate_p = workflow_subparsers.add_parser(
        "validate",
        help="Validate workflow YAML without running",
        description=WORKFLOW_VALIDATE_HELP_DESCRIPTION,
        epilog=WORKFLOW_VALIDATE_HELP_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    workflow_validate_p.add_argument("file", help="Path to workflow YAML file")

    # workflow run
    workflow_run_p = workflow_subparsers.add_parser(
        "run",
        help="Run a workflow from YAML file",
        description=WORKFLOW_RUN_HELP_DESCRIPTION,
        epilog=WORKFLOW_RUN_HELP_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    workflow_run_p.add_argument("file", help="Path to workflow YAML file")
    workflow_run_p.add_argument("--at", dest="at_time", metavar="TIME",
                                help='Schedule start time (HH:MM, 24h format). Example: --at "02:00"')
    workflow_run_p.add_argument("--in", dest="in_delay", metavar="DURATION",
                                help='Schedule start delay. Example: --in "4h"')
    workflow_run_p.add_argument("--name",
                                help="Override workflow name from YAML")
    workflow_run_p.add_argument("--force", action="store_true",
                                help="Overwrite existing workflow with same name")

    # workflow status
    workflow_status_p = workflow_subparsers.add_parser(
        "status",
        help="Show workflow status",
        description=WORKFLOW_STATUS_HELP_DESCRIPTION,
        epilog=WORKFLOW_STATUS_HELP_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    workflow_status_p.add_argument("name", help="Workflow name")
    workflow_status_p.add_argument("--format", choices=["text", "json"],
                                   default="text", help="Output format (default: text)")

    # workflow list
    workflow_list_p = workflow_subparsers.add_parser(
        "list",
        help="List all workflows",
        description=WORKFLOW_LIST_HELP_DESCRIPTION,
        epilog=WORKFLOW_LIST_HELP_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    workflow_list_p.add_argument("--format", choices=["table", "json"],
                                 default="table", help="Output format (default: table)")

    # workflow cancel
    workflow_cancel_p = workflow_subparsers.add_parser(
        "cancel",
        help="Cancel a running workflow",
        description=WORKFLOW_CANCEL_HELP_DESCRIPTION,
        epilog=WORKFLOW_CANCEL_HELP_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    workflow_cancel_p.add_argument("name", help="Workflow name")
    workflow_cancel_p.add_argument("--force", action="store_true",
                                   help="Kill workers without graceful shutdown")

    # workflow resume
    workflow_resume_p = workflow_subparsers.add_parser(
        "resume",
        help="Resume a failed/cancelled workflow",
        description=WORKFLOW_RESUME_HELP_DESCRIPTION,
        epilog=WORKFLOW_RESUME_HELP_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    workflow_resume_p.add_argument("name", help="Workflow name")
    workflow_resume_p.add_argument("--from", dest="from_stage", metavar="STAGE",
                                   help="Resume from a specific stage")

    # workflow resume-all
    workflow_resume_all_p = workflow_subparsers.add_parser(
        "resume-all",
        help="Resume all interrupted workflows",
        description=WORKFLOW_RESUME_ALL_HELP_DESCRIPTION,
        epilog=WORKFLOW_RESUME_ALL_HELP_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    workflow_resume_all_p.add_argument("--dry-run", action="store_true",
                                       help="Show which workflows would be resumed without resuming")
    workflow_resume_all_p.add_argument("--background", action="store_true",
                                       help="Run each workflow monitor in background")

    # workflow logs
    workflow_logs_p = workflow_subparsers.add_parser(
        "logs",
        help="View logs from workflow stages",
        description=WORKFLOW_LOGS_HELP_DESCRIPTION,
        epilog=WORKFLOW_LOGS_HELP_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    workflow_logs_p.add_argument("name", help="Workflow name")
    workflow_logs_p.add_argument("--stage", metavar="STAGE",
                                 help="Show logs only for a specific stage")
    workflow_logs_p.add_argument("--follow", "-f", action="store_true",
                                 help="Continuously poll for new output (requires --stage)")
    workflow_logs_p.add_argument("--lines", "-n", type=int, default=1000,
                                 help="Number of history lines to show (default: 1000)")

    args = parser.parse_args()

    # Resume active heartbeats on startup
    # This restarts monitor processes for heartbeats that were active
    # when swarm last ran (e.g., after system reboot)
    resume_active_heartbeats()

    # Notify about interrupted workflows on startup
    # Workflows run in foreground so we can't auto-resume, but we alert the user
    notify_interrupted_workflows()

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
    elif args.command == "heartbeat":
        cmd_heartbeat(args)
    elif args.command == "workflow":
        cmd_workflow(args)


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

    # Start heartbeat if requested
    if getattr(args, 'heartbeat', None):
        if not tmux_info:
            print(f"swarm: warning: --heartbeat requires --tmux, skipping heartbeat", file=sys.stderr)
        else:
            # Parse and validate heartbeat interval
            try:
                interval_seconds = parse_duration(args.heartbeat)
            except ValueError:
                print(f"swarm: error: invalid heartbeat interval '{args.heartbeat}'", file=sys.stderr)
                sys.exit(1)

            # Warn if interval is very short
            if interval_seconds < 60:
                print(f"swarm: warning: very short heartbeat interval ({args.heartbeat}), consider using at least 1m", file=sys.stderr)

            # Parse expiration
            expire_at = None
            if args.heartbeat_expire:
                try:
                    expire_seconds = parse_duration(args.heartbeat_expire)
                    expire_at = datetime.now(timezone.utc) + timedelta(seconds=expire_seconds)
                    expire_at = expire_at.isoformat()
                except ValueError:
                    print(f"swarm: error: invalid heartbeat-expire '{args.heartbeat_expire}'", file=sys.stderr)
                    sys.exit(1)

            # Create heartbeat state
            now = datetime.now(timezone.utc).isoformat()
            heartbeat_state = HeartbeatState(
                worker_name=args.name,
                interval_seconds=interval_seconds,
                message=args.heartbeat_message,
                expire_at=expire_at,
                created_at=now,
                last_beat_at=None,
                beat_count=0,
                status="active",
                monitor_pid=None,
            )

            # Save heartbeat state
            save_heartbeat_state(heartbeat_state)

            # Start background monitor process
            monitor_pid = start_heartbeat_monitor(args.name)

            # Update state with monitor PID
            heartbeat_state.monitor_pid = monitor_pid
            save_heartbeat_state(heartbeat_state)

            # Print heartbeat confirmation
            interval_str = format_duration(interval_seconds)
            if expire_at:
                expire_str = format_duration(parse_duration(args.heartbeat_expire))
                print(f"heartbeat started (every {interval_str}, expires in {expire_str})")
            else:
                print(f"heartbeat started (every {interval_str}, no expiration)")


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

        # Update ralph state if this is a ralph worker
        ralph_state = load_ralph_state(worker.name)
        if ralph_state:
            # Log the iteration before potentially deleting state
            log_ralph_iteration(
                worker.name, "DONE",
                total_iterations=ralph_state.current_iteration,
                reason="killed"
            )

            if args.rm_worktree:
                # Delete ralph state directory when --rm-worktree is specified
                ralph_state_dir = RALPH_DIR / worker.name
                try:
                    import shutil
                    shutil.rmtree(ralph_state_dir)
                except OSError as e:
                    print(f"swarm: warning: cannot remove ralph state for '{worker.name}': {e}", file=sys.stderr)
            else:
                # Just update status if not removing
                ralph_state.status = "stopped"
                save_ralph_state(ralph_state)

        # Stop heartbeat if active for this worker
        heartbeat_state = load_heartbeat_state(worker.name)
        if heartbeat_state and heartbeat_state.status in ("active", "paused"):
            stop_heartbeat_monitor(heartbeat_state)
            heartbeat_state.status = "stopped"
            heartbeat_state.monitor_pid = None
            save_heartbeat_state(heartbeat_state)

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
    - spawn: Spawn a new ralph worker
    - init: Create PROMPT.md with starter template
    - template: Output template to stdout
    - status: Show ralph loop status for a worker
    - pause: Pause ralph loop for a worker
    - resume: Resume ralph loop for a worker
    - run: Run the ralph loop (main outer loop execution)
    - list: List all ralph workers
    """
    if args.ralph_command == "spawn":
        cmd_ralph_spawn(args)
    elif args.ralph_command == "init":
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


def _rollback_ralph_spawn(
    worktree_path: Optional[Path],
    tmux_info: Optional[TmuxInfo],
    worker_name: Optional[str],
    state: Optional["State"],
    ralph_state_created: bool,
) -> None:
    """Rollback resources created during ralph spawn on failure.

    Cleans up resources in reverse order of creation to ensure no orphaned state.
    Rollback failures are logged as warnings but don't override the original error.

    Args:
        worktree_path: Path to worktree if created, None otherwise
        tmux_info: TmuxInfo if window created, None otherwise
        worker_name: Worker name if added to state, None otherwise
        state: State instance for removing worker, None if not added
        ralph_state_created: True if ralph state was saved
    """
    # Remove ralph state first (last created)
    if ralph_state_created and worker_name:
        ralph_state_dir = RALPH_DIR / worker_name
        try:
            import shutil
            if ralph_state_dir.exists():
                shutil.rmtree(ralph_state_dir)
        except OSError as e:
            print(f"swarm: warning: rollback failed: could not remove ralph state: {e}", file=sys.stderr)

    # Remove worker from state
    if worker_name and state:
        try:
            state.remove_worker(worker_name)
        except Exception as e:
            print(f"swarm: warning: rollback failed: could not remove worker state: {e}", file=sys.stderr)

    # Kill tmux window
    if tmux_info:
        try:
            cmd_prefix = tmux_cmd_prefix(tmux_info.socket)
            subprocess.run(
                cmd_prefix + ["kill-window", "-t", f"{tmux_info.session}:{tmux_info.window}"],
                capture_output=True
            )
        except Exception as e:
            print(f"swarm: warning: rollback failed: could not kill tmux window: {e}", file=sys.stderr)

    # Remove worktree (first created)
    if worktree_path and worktree_path.exists():
        try:
            subprocess.run(
                ["git", "worktree", "remove", "--force", str(worktree_path)],
                capture_output=True,
                text=True,
            )
        except Exception as e:
            print(f"swarm: warning: rollback failed: could not remove worktree: {e}", file=sys.stderr)


def cmd_ralph_spawn(args) -> None:
    """Spawn a new ralph worker.

    Spawns a worker in tmux mode with ralph loop configuration.
    Creates both the worker and ralph state for autonomous looping.

    Uses transactional semantics: if any step fails, all previously created
    resources are cleaned up (worktree, tmux window, worker state, ralph state).

    Args:
        args: Namespace with spawn arguments
    """
    # Parse command from args.cmd (strip leading '--' if present)
    cmd = args.cmd
    if cmd and cmd[0] == "--":
        cmd = cmd[1:]

    # Validate command is not empty
    if not cmd:
        print("swarm: error: no command provided (use -- command...)", file=sys.stderr)
        sys.exit(1)

    # Validate prompt file exists
    prompt_path = Path(args.prompt_file)
    if not prompt_path.exists():
        print(f"swarm: error: prompt file not found: {args.prompt_file}", file=sys.stderr)
        sys.exit(1)

    # Warn for high iteration count
    if args.max_iterations > 50:
        print("swarm: warning: high iteration count (>50) may consume significant resources", file=sys.stderr)

    # Load state and check for duplicate name
    state = State()
    if state.get_worker(args.name) is not None:
        print(f"swarm: error: worker '{args.name}' already exists", file=sys.stderr)
        sys.exit(1)

    # Parse environment variables from KEY=VAL format (validation only, no resources created)
    env_dict = {}
    for env_str in args.env:
        if "=" not in env_str:
            print(f"swarm: error: invalid env format '{env_str}' (expected KEY=VAL)", file=sys.stderr)
            sys.exit(1)
        key, val = env_str.split("=", 1)
        env_dict[key] = val

    # Track resources for rollback
    worktree_path: Optional[Path] = None
    worktree_info: Optional[WorktreeInfo] = None
    tmux_info: Optional[TmuxInfo] = None
    worker_added = False
    ralph_state_created = False

    # Determine working directory
    cwd = Path.cwd()

    try:
        # Step 1: Create worktree (if requested)
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

            # Create worktree (first resource)
            create_worktree(worktree_path, branch)

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

        # Step 2: Create tmux window
        session = args.session if args.session else get_default_session_name()
        socket = args.tmux_socket
        create_tmux_window(session, args.name, cwd, cmd, socket)
        tmux_info = TmuxInfo(session=session, window=args.name, socket=socket)

        # Step 3: Add worker to state
        metadata = {
            "ralph": True,
            "ralph_iteration": 1,  # Starting with iteration 1
        }

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
            pid=None,
            metadata=metadata,
        )

        state.add_worker(worker)
        worker_added = True

        # Step 4: Create ralph state
        ralph_state = RalphState(
            worker_name=args.name,
            prompt_file=str(Path(args.prompt_file).resolve()),
            max_iterations=args.max_iterations,
            current_iteration=1,  # Starting at iteration 1, not 0
            status="running",
            started=datetime.now().isoformat(),
            last_iteration_started=datetime.now().isoformat(),
            inactivity_timeout=args.inactivity_timeout,
            done_pattern=args.done_pattern,
            check_done_continuous=getattr(args, 'check_done_continuous', False),
        )
        save_ralph_state(ralph_state)
        ralph_state_created = True

        # Step 5: Log the iteration start
        log_ralph_iteration(
            args.name,
            "START",
            iteration=1,
            max_iterations=args.max_iterations
        )

        # Step 6: Send the prompt to the worker for the first iteration
        prompt_content = Path(args.prompt_file).read_text()
        send_prompt_to_worker(worker, prompt_content)

    except subprocess.CalledProcessError as e:
        # Handle worktree or tmux creation failures
        print("swarm: warning: spawn failed, cleaning up partial state", file=sys.stderr)
        _rollback_ralph_spawn(
            worktree_path if worktree_info else None,
            tmux_info,
            args.name if worker_added else None,
            state if worker_added else None,
            ralph_state_created,
        )
        if "worktree" in str(e).lower() or (worktree_path and not tmux_info):
            print(f"swarm: error: failed to create worktree: {e}", file=sys.stderr)
        else:
            print(f"swarm: error: failed to create tmux window: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        # Handle any other unexpected errors
        print("swarm: warning: spawn failed, cleaning up partial state", file=sys.stderr)
        _rollback_ralph_spawn(
            worktree_path if worktree_info else None,
            tmux_info,
            args.name if worker_added else None,
            state if worker_added else None,
            ralph_state_created,
        )
        print(f"swarm: error: spawn failed: {e}", file=sys.stderr)
        sys.exit(1)

    # Wait for agent to be ready if requested
    if args.ready_wait:
        socket = tmux_info.socket if tmux_info else None
        if not wait_for_agent_ready(tmux_info.session, tmux_info.window, args.ready_timeout, socket):
            print(f"swarm: warning: agent '{args.name}' did not become ready within {args.ready_timeout}s", file=sys.stderr)

    # Print success message
    msg = f"spawned {args.name} (tmux: {tmux_info.session}:{tmux_info.window})"
    msg += f" [ralph mode: iteration 1/{args.max_iterations}]"
    print(msg)

    # Start heartbeat if requested
    if getattr(args, 'heartbeat', None):
        # Parse and validate heartbeat interval
        try:
            interval_seconds = parse_duration(args.heartbeat)
        except ValueError:
            print(f"swarm: error: invalid heartbeat interval '{args.heartbeat}'", file=sys.stderr)
            sys.exit(1)

        # Warn if interval is very short
        if interval_seconds < 60:
            print(f"swarm: warning: very short heartbeat interval ({args.heartbeat}), consider using at least 1m", file=sys.stderr)

        # Parse expiration
        expire_at = None
        if args.heartbeat_expire:
            try:
                expire_seconds = parse_duration(args.heartbeat_expire)
                expire_at = datetime.now(timezone.utc) + timedelta(seconds=expire_seconds)
                expire_at = expire_at.isoformat()
            except ValueError:
                print(f"swarm: error: invalid heartbeat-expire '{args.heartbeat_expire}'", file=sys.stderr)
                sys.exit(1)

        # Create heartbeat state
        now = datetime.now(timezone.utc).isoformat()
        heartbeat_state = HeartbeatState(
            worker_name=args.name,
            interval_seconds=interval_seconds,
            message=args.heartbeat_message,
            expire_at=expire_at,
            created_at=now,
            last_beat_at=None,
            beat_count=0,
            status="active",
            monitor_pid=None,
        )

        # Save heartbeat state
        save_heartbeat_state(heartbeat_state)

        # Start background monitor process
        monitor_pid = start_heartbeat_monitor(args.name)

        # Update state with monitor PID
        heartbeat_state.monitor_pid = monitor_pid
        save_heartbeat_state(heartbeat_state)

        # Print heartbeat confirmation
        interval_str = format_duration(interval_seconds)
        if expire_at:
            expire_str = format_duration(parse_duration(args.heartbeat_expire))
            print(f"heartbeat started (every {interval_str}, expires in {expire_str})")
        else:
            print(f"heartbeat started (every {interval_str}, no expiration)")

    # Auto-start the monitoring loop unless --no-run is specified
    # Note: We check hasattr to maintain backwards compatibility with existing tests
    # that don't include no_run in their args. CLI usage will always have no_run set.
    if hasattr(args, 'no_run') and not args.no_run:
        # Create a simple args object with just the name for the loop
        from argparse import Namespace
        loop_args = Namespace(name=args.name)
        cmd_ralph_run(loop_args)


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


def detect_inactivity(
    worker: Worker,
    timeout: int,
    done_pattern: Optional[str] = None,
    check_done_continuous: bool = False
) -> str:
    """Detect if a worker has become inactive using screen-stable detection.

    Uses the "screen stable" approach inspired by Playwright's networkidle pattern:
    waits until the screen has not changed for the specified timeout duration.

    Algorithm:
    1. Capture last 20 lines of tmux pane every 2 seconds
    2. Strip ANSI escape codes to normalize content
    3. Hash the normalized content (MD5)
    4. If hash unchanged for timeout seconds, trigger restart
    5. Any screen change resets the timer
    6. If check_done_continuous, check done pattern each poll cycle

    Args:
        worker: The worker to monitor
        timeout: Seconds of screen stability before restart
        done_pattern: Optional regex pattern to check for completion
        check_done_continuous: If True, check done pattern during monitoring

    Returns:
        String indicating why monitoring ended:
        - "exited": Worker exited on its own
        - "inactive": Inactivity timeout reached
        - "done_pattern": Done pattern matched (only if check_done_continuous)
    """
    import hashlib
    import re

    if not worker.tmux:
        return "exited"

    socket = worker.tmux.socket
    last_hash = None
    stable_start = None

    # Regex to strip ANSI escape codes
    ansi_escape = re.compile(r'\x1b\[[0-9;]*m')

    # Compile done pattern regex if provided for continuous checking
    done_regex = None
    if check_done_continuous and done_pattern:
        try:
            done_regex = re.compile(done_pattern)
        except re.error:
            # Invalid pattern - skip continuous checking
            pass

    def normalize_content(output: str) -> str:
        """Normalize screen content by taking last 20 lines and stripping ANSI codes."""
        lines = output.split('\n')
        last_20 = lines[-20:] if len(lines) > 20 else lines
        joined = '\n'.join(last_20)
        return ansi_escape.sub('', joined)

    def hash_content(content: str) -> str:
        """Hash normalized content with MD5."""
        return hashlib.md5(content.encode()).hexdigest()

    while True:
        # Check if worker is still running
        if refresh_worker_status(worker) == "stopped":
            return "exited"

        try:
            # Capture current output
            current_output = tmux_capture_pane(
                worker.tmux.session,
                worker.tmux.window,
                socket=socket
            )

            # Check done pattern continuously if enabled
            if done_regex and done_regex.search(current_output):
                return "done_pattern"

            # Normalize and hash the content
            normalized = normalize_content(current_output)
            current_hash = hash_content(normalized)

            # Compare hashes
            if current_hash != last_hash:
                # Screen changed, reset timer
                last_hash = current_hash
                stable_start = None
            else:
                # Screen unchanged
                if stable_start is None:
                    stable_start = time.time()
                elif (time.time() - stable_start) >= timeout:
                    return "inactive"

        except subprocess.CalledProcessError:
            # Window might have closed
            return "exited"

        time.sleep(2)


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

        # Monitor the worker - detect_inactivity blocks until worker exits, goes inactive,
        # or done pattern matches (if check_done_continuous)
        monitor_result = detect_inactivity(
            worker,
            ralph_state.inactivity_timeout,
            done_pattern=ralph_state.done_pattern,
            check_done_continuous=ralph_state.check_done_continuous
        )

        # Reload ralph state (could have been paused while monitoring)
        ralph_state = load_ralph_state(args.name)
        if not ralph_state or ralph_state.status == "paused":
            print(f"[ralph] {args.name}: paused, exiting loop")
            break

        # Check worker status
        state = State()
        worker = state.get_worker(args.name)

        if monitor_result == "done_pattern":
            # Done pattern matched during continuous monitoring
            print(f"[ralph] {args.name}: done pattern matched, stopping loop")
            log_ralph_iteration(
                args.name,
                "DONE",
                total_iterations=ralph_state.current_iteration,
                reason="done_pattern"
            )
            ralph_state.status = "stopped"
            save_ralph_state(ralph_state)
            # Kill the worker since we're stopping
            if worker:
                kill_worker_for_ralph(worker, state)
            return

        if monitor_result == "inactive":
            # Worker went inactive - restart it
            print(f"[ralph] {args.name}: inactivity timeout ({ralph_state.inactivity_timeout}s), restarting")
            log_ralph_iteration(
                args.name,
                "TIMEOUT",
                iteration=ralph_state.current_iteration,
                timeout=ralph_state.inactivity_timeout
            )

            # Kill the worker
            if worker:
                kill_worker_for_ralph(worker, state)
        else:
            # Worker exited on its own (monitor_result == "exited")
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

            # Check for done pattern (after exit, non-continuous mode)
            if ralph_state.done_pattern and worker and not ralph_state.check_done_continuous:
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

        # Check if we should exit (paused)
        ralph_state = load_ralph_state(args.name)
        if not ralph_state or ralph_state.status == "paused":
            break


def cmd_heartbeat(args) -> None:
    """Heartbeat management commands.

    Dispatches to heartbeat subcommands:
    - start: Start heartbeat for a worker
    - stop: Stop heartbeat for a worker
    - list: List all heartbeats
    - status: Show heartbeat status
    - pause: Pause heartbeat temporarily
    - resume: Resume paused heartbeat
    """
    if args.heartbeat_command == "start":
        cmd_heartbeat_start(args)
    elif args.heartbeat_command == "stop":
        cmd_heartbeat_stop(args)
    elif args.heartbeat_command == "list":
        cmd_heartbeat_list(args)
    elif args.heartbeat_command == "status":
        cmd_heartbeat_status(args)
    elif args.heartbeat_command == "pause":
        cmd_heartbeat_pause(args)
    elif args.heartbeat_command == "resume":
        cmd_heartbeat_resume(args)


def cmd_heartbeat_start(args) -> None:
    """Start heartbeat for a worker.

    Creates a heartbeat configuration and saves it to disk.
    The heartbeat will send periodic messages to the worker.

    Args:
        args: Namespace with start arguments
    """
    worker_name = args.worker

    # Load worker state
    state = State()
    worker = state.get_worker(worker_name)

    # Validate worker exists
    if worker is None:
        print(f"Error: worker '{worker_name}' not found", file=sys.stderr)
        sys.exit(1)

    # Validate worker is tmux
    if worker.tmux is None:
        print(f"Error: heartbeat requires tmux worker", file=sys.stderr)
        sys.exit(1)

    # Check for existing heartbeat
    existing = load_heartbeat_state(worker_name)
    if existing is not None and existing.status in ("active", "paused"):
        if not args.force:
            print(f"Error: heartbeat already active for '{worker_name}' (use --force to replace)", file=sys.stderr)
            sys.exit(1)
        # Stop existing monitor if using --force
        stop_heartbeat_monitor(existing)

    # Parse interval
    try:
        interval_seconds = parse_duration(args.interval)
    except ValueError as e:
        print(f"Error: invalid interval '{args.interval}'", file=sys.stderr)
        sys.exit(1)

    # Warn if interval is very short
    if interval_seconds < 60:
        print(f"Warning: very short interval ({args.interval}), consider using at least 1m", file=sys.stderr)

    # Parse expiration
    expire_at = None
    if args.expire:
        try:
            expire_seconds = parse_duration(args.expire)
            expire_at = datetime.now(timezone.utc) + timedelta(seconds=expire_seconds)
            expire_at = expire_at.isoformat()
        except ValueError as e:
            print(f"Error: invalid expire '{args.expire}'", file=sys.stderr)
            sys.exit(1)

    # Create heartbeat state
    now = datetime.now(timezone.utc).isoformat()
    heartbeat_state = HeartbeatState(
        worker_name=worker_name,
        interval_seconds=interval_seconds,
        message=args.message,
        expire_at=expire_at,
        created_at=now,
        last_beat_at=None,
        beat_count=0,
        status="active",
        monitor_pid=None,  # Will be set after spawning monitor
    )

    # Save heartbeat state first (monitor needs it to exist)
    save_heartbeat_state(heartbeat_state)

    # Start background monitor process
    monitor_pid = start_heartbeat_monitor(worker_name)

    # Update state with monitor PID
    heartbeat_state.monitor_pid = monitor_pid
    save_heartbeat_state(heartbeat_state)

    # Format output
    interval_str = format_duration(interval_seconds)
    if expire_at:
        expire_delta = parse_duration(args.expire)
        expire_str = format_duration(expire_delta)
        print(f"Heartbeat started for {worker_name} (every {interval_str}, expires in {expire_str})")
    else:
        print(f"Heartbeat started for {worker_name} (every {interval_str}, no expiration)")


def cmd_heartbeat_stop(args) -> None:
    """Stop heartbeat for a worker.

    Sets the heartbeat status to stopped and terminates the monitor process.

    Args:
        args: Namespace with stop arguments
    """
    worker_name = args.worker

    # Load heartbeat state
    heartbeat_state = load_heartbeat_state(worker_name)
    if heartbeat_state is None:
        print(f"No active heartbeat for {worker_name}")
        return

    # Stop the monitor process
    stop_heartbeat_monitor(heartbeat_state)

    # Update status to stopped
    heartbeat_state.status = "stopped"
    heartbeat_state.monitor_pid = None
    save_heartbeat_state(heartbeat_state)
    print(f"Heartbeat stopped for {worker_name}")


def cmd_heartbeat_list(args) -> None:
    """List all heartbeats.

    Shows a table or JSON of all heartbeat configurations.

    Args:
        args: Namespace with list arguments
    """
    states = list_heartbeat_states()

    if not states:
        if args.format == "json":
            print("[]")
        else:
            print("No heartbeats found")
        return

    if args.format == "json":
        import json
        output = []
        for s in states:
            output.append(s.to_dict())
        print(json.dumps(output, indent=2))
    else:
        # Table format
        print(f"{'WORKER':<15} {'INTERVAL':<10} {'NEXT BEAT':<12} {'EXPIRES':<12} {'STATUS':<10} {'BEATS':<6}")
        for s in states:
            interval_str = format_duration(s.interval_seconds)
            # Calculate next beat time
            if s.status in ("paused", "expired", "stopped"):
                next_beat_str = "-"
            else:
                # Next beat is last_beat_at + interval, or created_at + interval if no beats yet
                base_time = s.last_beat_at if s.last_beat_at else s.created_at
                if base_time:
                    try:
                        base_dt = datetime.fromisoformat(base_time.replace('Z', '+00:00'))
                        next_dt = base_dt + timedelta(seconds=s.interval_seconds)
                        next_beat_str = time_until(next_dt.isoformat())
                    except ValueError:
                        next_beat_str = "?"
                else:
                    next_beat_str = "?"
            # Format expiration
            if s.expire_at:
                try:
                    expire_str = time_until(s.expire_at)
                except ValueError:
                    expire_str = s.expire_at
            else:
                expire_str = "never"
            print(f"{s.worker_name:<15} {interval_str:<10} {next_beat_str:<12} {expire_str:<12} {s.status:<10} {s.beat_count:<6}")


def cmd_heartbeat_status(args) -> None:
    """Show detailed heartbeat status.

    Args:
        args: Namespace with status arguments
    """
    worker_name = args.worker

    heartbeat_state = load_heartbeat_state(worker_name)
    if heartbeat_state is None:
        print(f"No heartbeat found for {worker_name}", file=sys.stderr)
        sys.exit(1)

    # Calculate next beat time
    if heartbeat_state.status in ("paused", "expired", "stopped"):
        next_beat_str = "-"
        next_beat_iso = None
    else:
        base_time = heartbeat_state.last_beat_at if heartbeat_state.last_beat_at else heartbeat_state.created_at
        if base_time:
            try:
                base_dt = datetime.fromisoformat(base_time.replace('Z', '+00:00'))
                next_dt = base_dt + timedelta(seconds=heartbeat_state.interval_seconds)
                next_beat_iso = next_dt.isoformat()
                next_beat_str = time_until(next_beat_iso)
            except ValueError:
                next_beat_str = "?"
                next_beat_iso = None
        else:
            next_beat_str = "?"
            next_beat_iso = None

    # Calculate expires string
    if heartbeat_state.expire_at:
        try:
            expire_str = time_until(heartbeat_state.expire_at)
        except ValueError:
            expire_str = heartbeat_state.expire_at
    else:
        expire_str = "never"

    if args.format == "json":
        import json
        output = heartbeat_state.to_dict()
        output["next_beat_at"] = next_beat_iso
        print(json.dumps(output, indent=2))
    else:
        print(f"Worker: {heartbeat_state.worker_name}")
        print(f"Status: {heartbeat_state.status}")
        print(f"Interval: {format_duration(heartbeat_state.interval_seconds)}")
        print(f"Message: {heartbeat_state.message}")
        print(f"Created: {heartbeat_state.created_at}")
        if heartbeat_state.expire_at:
            print(f"Expires: {heartbeat_state.expire_at} ({expire_str})")
        else:
            print(f"Expires: never")
        if heartbeat_state.last_beat_at:
            print(f"Last beat: {heartbeat_state.last_beat_at}")
        else:
            print(f"Last beat: none")
        print(f"Next beat: {next_beat_str}")
        print(f"Beat count: {heartbeat_state.beat_count}")


def cmd_heartbeat_pause(args) -> None:
    """Pause heartbeat for a worker.

    Args:
        args: Namespace with pause arguments
    """
    worker_name = args.worker

    heartbeat_state = load_heartbeat_state(worker_name)
    if heartbeat_state is None:
        print(f"No heartbeat found for {worker_name}", file=sys.stderr)
        sys.exit(1)

    if heartbeat_state.status != "active":
        print(f"Heartbeat for {worker_name} is not active (status: {heartbeat_state.status})", file=sys.stderr)
        sys.exit(1)

    heartbeat_state.status = "paused"
    save_heartbeat_state(heartbeat_state)
    print(f"Heartbeat paused for {worker_name}")


def cmd_heartbeat_resume(args) -> None:
    """Resume paused heartbeat for a worker.

    Args:
        args: Namespace with resume arguments
    """
    worker_name = args.worker

    heartbeat_state = load_heartbeat_state(worker_name)
    if heartbeat_state is None:
        print(f"No heartbeat found for {worker_name}", file=sys.stderr)
        sys.exit(1)

    if heartbeat_state.status != "paused":
        print(f"Heartbeat for {worker_name} is not paused (status: {heartbeat_state.status})", file=sys.stderr)
        sys.exit(1)

    heartbeat_state.status = "active"

    # Check if monitor process is still running, restart if needed
    monitor_running = False
    if heartbeat_state.monitor_pid:
        try:
            os.kill(heartbeat_state.monitor_pid, 0)
            monitor_running = True
        except OSError:
            monitor_running = False

    if not monitor_running:
        # Restart monitor process
        monitor_pid = start_heartbeat_monitor(worker_name)
        heartbeat_state.monitor_pid = monitor_pid

    save_heartbeat_state(heartbeat_state)
    print(f"Heartbeat resumed for {worker_name}")


# ==============================================================================
# Workflow Commands
# ==============================================================================


def spawn_workflow_stage(
    workflow_name: str,
    workflow_def: WorkflowDefinition,
    stage_def: StageDefinition,
    workflow_dir: Path,
) -> Worker:
    """Spawn a worker for a workflow stage.

    Creates and spawns a worker for the given stage, applying global workflow
    settings and stage-specific overrides. Handles both 'worker' and 'ralph'
    stage types.

    Stage workers are named '<workflow>-<stage>' to avoid naming conflicts.

    Args:
        workflow_name: Name of the workflow
        workflow_def: The parsed workflow definition (for global settings)
        stage_def: The stage definition to spawn
        workflow_dir: Directory containing the workflow YAML (for resolving relative paths)

    Returns:
        The created Worker object

    Raises:
        RuntimeError: If worker spawning fails
    """
    # Determine worker name: <workflow>-<stage>
    worker_name = f"{workflow_name}-{stage_def.name}"

    # Check for duplicate worker name
    state = State()
    if state.get_worker(worker_name) is not None:
        raise RuntimeError(f"worker '{worker_name}' already exists")

    # Resolve prompt content
    if stage_def.prompt:
        prompt_content = stage_def.prompt
    elif stage_def.prompt_file:
        # Resolve prompt file path relative to workflow directory
        prompt_path = Path(stage_def.prompt_file)
        if not prompt_path.is_absolute():
            prompt_path = workflow_dir / prompt_path
        prompt_content = prompt_path.read_text()
    else:
        raise RuntimeError(f"stage '{stage_def.name}' has no prompt or prompt_file")

    # Determine working directory
    # Stage cwd overrides global cwd
    cwd_setting = stage_def.cwd if stage_def.cwd else workflow_def.cwd
    if cwd_setting:
        cwd = Path(cwd_setting)
        if not cwd.is_absolute():
            cwd = workflow_dir / cwd
    else:
        cwd = Path.cwd()

    # Determine worktree setting (stage overrides global)
    use_worktree = stage_def.worktree if stage_def.worktree is not None else workflow_def.worktree
    worktree_info = None

    if use_worktree:
        # Get git root
        try:
            git_root = get_git_root()
        except subprocess.CalledProcessError:
            raise RuntimeError("not in a git repository (required for worktree)")

        # Compute worktree path: <repo>-worktrees/<worker-name>
        worktree_dir = git_root.parent / f"{git_root.name}-worktrees"
        worktree_path = worktree_dir / worker_name

        # Use worker name as branch name
        branch = worker_name

        # Create worktree
        try:
            create_worktree(worktree_path, branch)
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"failed to create worktree: {e}")

        # Set cwd to worktree
        cwd = worktree_path

        # Store worktree info
        worktree_info = WorktreeInfo(
            path=str(worktree_path),
            branch=branch,
            base_repo=str(git_root)
        )

    # Build environment variables from stage definition
    env_dict = dict(stage_def.env) if stage_def.env else {}

    # Default command for workflow stages is 'claude' (the standard agent)
    # In a real workflow, this would be configurable, but for now we use claude
    cmd = ["claude"]

    # Get tmux session name
    session = get_default_session_name()

    # Create tmux window
    try:
        create_tmux_window(session, worker_name, cwd, cmd, socket=None)
        tmux_info = TmuxInfo(session=session, window=worker_name, socket=None)
    except subprocess.CalledProcessError as e:
        # Clean up worktree if we created one
        if worktree_info:
            try:
                remove_worktree(Path(worktree_info.path), force=True)
            except Exception:
                pass
        raise RuntimeError(f"failed to create tmux window: {e}")

    # Build metadata
    metadata = {}
    if stage_def.type == "ralph":
        metadata["ralph"] = True
        metadata["ralph_iteration"] = 1

    # Create Worker object
    worker = Worker(
        name=worker_name,
        status="running",
        cmd=cmd,
        started=datetime.now().isoformat(),
        cwd=str(cwd),
        env=env_dict,
        tags=list(stage_def.tags) if stage_def.tags else [],
        tmux=tmux_info,
        worktree=worktree_info,
        pid=None,
        metadata=metadata,
    )

    # Add to state
    state.add_worker(worker)

    # Handle type-specific setup
    if stage_def.type == "ralph":
        # Create ralph state for looping stages
        # For inline prompts, we need to write to a temp file
        if stage_def.prompt:
            # Write inline prompt to workflow state directory
            prompt_temp_path = get_workflow_state_dir(workflow_name) / f"{stage_def.name}-prompt.md"
            prompt_temp_path.write_text(prompt_content)
            prompt_file_path = str(prompt_temp_path)
        else:
            # Use resolved prompt file path
            prompt_path = Path(stage_def.prompt_file)
            if not prompt_path.is_absolute():
                prompt_path = workflow_dir / prompt_path
            prompt_file_path = str(prompt_path.resolve())

        ralph_state = RalphState(
            worker_name=worker_name,
            prompt_file=prompt_file_path,
            max_iterations=stage_def.max_iterations or 50,
            current_iteration=1,
            status="running",
            started=datetime.now().isoformat(),
            last_iteration_started=datetime.now().isoformat(),
            inactivity_timeout=stage_def.inactivity_timeout,
            done_pattern=stage_def.done_pattern,
            check_done_continuous=stage_def.check_done_continuous,
        )
        save_ralph_state(ralph_state)

        # Log the iteration start
        log_ralph_iteration(
            worker_name,
            "START",
            iteration=1,
            max_iterations=ralph_state.max_iterations
        )

    # Send the prompt to the worker
    send_prompt_to_worker(worker, prompt_content)

    # Set up heartbeat if configured
    # Stage heartbeat overrides global heartbeat
    heartbeat_setting = stage_def.heartbeat if stage_def.heartbeat else workflow_def.heartbeat
    heartbeat_expire_setting = stage_def.heartbeat_expire if stage_def.heartbeat_expire else workflow_def.heartbeat_expire
    heartbeat_message_setting = stage_def.heartbeat_message if stage_def.heartbeat_message else workflow_def.heartbeat_message

    if heartbeat_setting:
        try:
            interval_seconds = parse_duration(heartbeat_setting)
        except ValueError:
            # Log warning but don't fail - heartbeat is optional
            print(f"swarm: warning: invalid heartbeat interval '{heartbeat_setting}' for stage {stage_def.name}", file=sys.stderr)
            interval_seconds = None

        if interval_seconds:
            # Parse expiration
            expire_at = None
            if heartbeat_expire_setting:
                try:
                    expire_seconds = parse_duration(heartbeat_expire_setting)
                    expire_at = datetime.now(timezone.utc) + timedelta(seconds=expire_seconds)
                    expire_at = expire_at.isoformat()
                except ValueError:
                    print(f"swarm: warning: invalid heartbeat-expire '{heartbeat_expire_setting}' for stage {stage_def.name}", file=sys.stderr)

            # Create heartbeat state
            now = datetime.now(timezone.utc).isoformat()
            heartbeat_state = HeartbeatState(
                worker_name=worker_name,
                interval_seconds=interval_seconds,
                message=heartbeat_message_setting or "continue",
                expire_at=expire_at,
                created_at=now,
                last_beat_at=None,
                beat_count=0,
                status="active",
                monitor_pid=None,
            )

            # Save heartbeat state
            save_heartbeat_state(heartbeat_state)

            # Start background monitor process
            monitor_pid = start_heartbeat_monitor(worker_name)

            # Update state with monitor PID
            heartbeat_state.monitor_pid = monitor_pid
            save_heartbeat_state(heartbeat_state)

    return worker


@dataclass
class StageCompletionResult:
    """Result of monitoring a workflow stage for completion.

    Captures how a stage completed, including whether it succeeded,
    the reason for completion, and timing information.
    """
    completed: bool  # True if stage finished (success or failure)
    success: bool  # True if stage succeeded (done_pattern matched, ralph completed normally)
    reason: str  # Reason for completion: done_pattern, timeout, worker_exit, ralph_complete, ralph_failed, error
    details: Optional[str] = None  # Additional details about the completion


def monitor_stage_completion(
    workflow_name: str,
    stage_def: StageDefinition,
    worker: Worker,
    poll_interval: float = 2.0,
) -> StageCompletionResult:
    """Monitor a workflow stage for completion.

    Monitors the given stage's worker for completion conditions based on the
    stage type:

    For 'worker' type stages:
    - Checks for done-pattern match in tmux output
    - Handles timeout (if configured)
    - Detects worker exit

    For 'ralph' type stages:
    - Monitors ralph state for loop completion or failure
    - Done pattern is handled by ralph loop itself

    Args:
        workflow_name: Name of the workflow
        stage_def: The stage definition being monitored
        worker: The worker running the stage
        poll_interval: Seconds between status checks (default 2.0)

    Returns:
        StageCompletionResult indicating how the stage completed
    """
    import re

    worker_name = worker.name
    start_time = time.time()

    # Parse timeout if specified
    timeout_seconds = None
    if stage_def.timeout:
        try:
            timeout_seconds = parse_duration(stage_def.timeout)
        except ValueError:
            # Invalid timeout - proceed without timeout
            pass

    # Compile done pattern regex if specified
    done_regex = None
    if stage_def.done_pattern:
        try:
            done_regex = re.compile(stage_def.done_pattern)
        except re.error:
            # Invalid regex - proceed without pattern matching
            pass

    if stage_def.type == "ralph":
        # For ralph stages, monitor ralph state
        return _monitor_ralph_stage_completion(
            worker_name=worker_name,
            timeout_seconds=timeout_seconds,
            start_time=start_time,
            poll_interval=poll_interval,
        )
    else:
        # For worker stages, monitor for done pattern, timeout, or exit
        return _monitor_worker_stage_completion(
            worker=worker,
            done_regex=done_regex,
            timeout_seconds=timeout_seconds,
            start_time=start_time,
            poll_interval=poll_interval,
        )


def _monitor_ralph_stage_completion(
    worker_name: str,
    timeout_seconds: Optional[float],
    start_time: float,
    poll_interval: float,
) -> StageCompletionResult:
    """Monitor a ralph-type stage for completion.

    Ralph stages complete when:
    - The ralph loop finishes (max iterations reached)
    - The done pattern is matched (if check_done_continuous is set)
    - The ralph loop fails (consecutive failures)
    - Timeout is reached

    Args:
        worker_name: Name of the worker (same as ralph name)
        timeout_seconds: Optional timeout in seconds
        start_time: When monitoring started (for timeout calculation)
        poll_interval: Seconds between status checks

    Returns:
        StageCompletionResult indicating how the stage completed
    """
    while True:
        # Check for timeout first
        if timeout_seconds is not None:
            elapsed = time.time() - start_time
            if elapsed >= timeout_seconds:
                return StageCompletionResult(
                    completed=True,
                    success=False,
                    reason="timeout",
                    details=f"Stage timed out after {format_duration(timeout_seconds)}",
                )

        # Load ralph state to check status
        ralph_state = load_ralph_state(worker_name)

        if ralph_state is None:
            # Ralph state doesn't exist - worker may have been killed
            return StageCompletionResult(
                completed=True,
                success=False,
                reason="error",
                details="Ralph state not found - worker may have been killed",
            )

        # Check ralph status
        if ralph_state.status == "stopped":
            # Ralph loop completed normally (done pattern or max iterations)
            return StageCompletionResult(
                completed=True,
                success=True,
                reason="ralph_complete",
                details=f"Ralph loop completed after {ralph_state.current_iteration} iterations",
            )

        elif ralph_state.status == "failed":
            # Ralph loop failed
            return StageCompletionResult(
                completed=True,
                success=False,
                reason="ralph_failed",
                details=f"Ralph loop failed after {ralph_state.total_failures} total failures",
            )

        elif ralph_state.status == "paused":
            # Ralph was paused externally - this is a special case
            # We don't treat paused as completed - it's a suspended state
            # Continue polling in case it's resumed
            pass

        # Ralph is still running, sleep and continue
        time.sleep(poll_interval)


def _monitor_worker_stage_completion(
    worker: Worker,
    done_regex: Optional["re.Pattern"],
    timeout_seconds: Optional[float],
    start_time: float,
    poll_interval: float,
) -> StageCompletionResult:
    """Monitor a worker-type stage for completion.

    Worker stages complete when:
    - Done pattern is matched in tmux output
    - Worker exits (process terminates)
    - Timeout is reached

    Args:
        worker: The worker to monitor
        done_regex: Compiled regex for done pattern (or None)
        timeout_seconds: Optional timeout in seconds
        start_time: When monitoring started (for timeout calculation)
        poll_interval: Seconds between status checks

    Returns:
        StageCompletionResult indicating how the stage completed
    """
    while True:
        # Check for timeout first
        if timeout_seconds is not None:
            elapsed = time.time() - start_time
            if elapsed >= timeout_seconds:
                return StageCompletionResult(
                    completed=True,
                    success=False,
                    reason="timeout",
                    details=f"Stage timed out after {format_duration(timeout_seconds)}",
                )

        # Check if worker has exited
        worker_status = refresh_worker_status(worker)
        if worker_status == "stopped":
            # Worker exited - check if done pattern was matched before exit
            if done_regex and worker.tmux:
                try:
                    output = tmux_capture_pane(
                        worker.tmux.session,
                        worker.tmux.window,
                        history_lines=1000,
                        socket=worker.tmux.socket,
                    )
                    if done_regex.search(output):
                        return StageCompletionResult(
                            completed=True,
                            success=True,
                            reason="done_pattern",
                            details="Worker exited after done pattern matched",
                        )
                except subprocess.CalledProcessError:
                    pass

            # Worker exited without done pattern
            return StageCompletionResult(
                completed=True,
                success=False,
                reason="worker_exit",
                details="Worker exited before done pattern matched",
            )

        # Check for done pattern in running worker
        if done_regex and worker.tmux:
            try:
                output = tmux_capture_pane(
                    worker.tmux.session,
                    worker.tmux.window,
                    history_lines=1000,
                    socket=worker.tmux.socket,
                )
                if done_regex.search(output):
                    return StageCompletionResult(
                        completed=True,
                        success=True,
                        reason="done_pattern",
                        details="Done pattern matched in worker output",
                    )
            except subprocess.CalledProcessError:
                # Window might have closed
                pass

        # Still running, sleep and continue
        time.sleep(poll_interval)


@dataclass
class StageTransitionResult:
    """Result of a stage transition operation.

    Captures what happened during a stage transition, including whether
    the workflow should continue, what the next stage is (if any),
    and the updated workflow state.
    """
    action: str  # "next_stage", "retry", "skip", "complete", "fail", "stop"
    next_stage_name: Optional[str] = None  # Name of next stage (if action is "next_stage")
    next_stage_index: int = -1  # Index of next stage (if action is "next_stage")
    message: str = ""  # Human-readable message about what happened


def handle_stage_transition(
    workflow_state: WorkflowState,
    workflow_def: WorkflowDefinition,
    completion_result: StageCompletionResult,
    workflow_dir: Path,
) -> StageTransitionResult:
    """Handle the transition after a workflow stage completes.

    Determines what to do after a stage completes based on the completion
    result and the stage's on-failure/on-complete configuration:

    For successful completion:
    - on-complete: next -> advance to next stage
    - on-complete: stop -> complete workflow
    - on-complete: goto:<stage> -> jump to named stage

    For failure:
    - on-failure: stop -> fail workflow
    - on-failure: retry -> retry stage (up to max-retries)
    - on-failure: skip -> mark stage skipped, advance to next

    Updates the workflow state and stage states accordingly.

    Args:
        workflow_state: Current workflow state (will be modified)
        workflow_def: The parsed workflow definition
        completion_result: How the stage completed
        workflow_dir: Directory containing the workflow YAML

    Returns:
        StageTransitionResult indicating what action to take next
    """
    current_stage_name = workflow_state.current_stage
    current_stage_index = workflow_state.current_stage_index

    if current_stage_name is None or current_stage_index < 0:
        return StageTransitionResult(
            action="fail",
            message="Workflow has no current stage",
        )

    # Get the stage definition
    if current_stage_index >= len(workflow_def.stages):
        return StageTransitionResult(
            action="fail",
            message=f"Stage index {current_stage_index} out of range",
        )

    stage_def = workflow_def.stages[current_stage_index]
    stage_state = workflow_state.stages.get(current_stage_name)

    if stage_state is None:
        return StageTransitionResult(
            action="fail",
            message=f"Stage state for '{current_stage_name}' not found",
        )

    now = datetime.now(timezone.utc).isoformat()

    # Handle based on whether the stage succeeded or failed
    if completion_result.success:
        # Stage completed successfully
        return _handle_stage_success(
            workflow_state=workflow_state,
            workflow_def=workflow_def,
            stage_def=stage_def,
            stage_state=stage_state,
            current_stage_index=current_stage_index,
            completion_result=completion_result,
            now=now,
        )
    else:
        # Stage failed
        return _handle_stage_failure(
            workflow_state=workflow_state,
            workflow_def=workflow_def,
            stage_def=stage_def,
            stage_state=stage_state,
            current_stage_index=current_stage_index,
            completion_result=completion_result,
            workflow_dir=workflow_dir,
            now=now,
        )


def _handle_stage_success(
    workflow_state: WorkflowState,
    workflow_def: WorkflowDefinition,
    stage_def: StageDefinition,
    stage_state: StageState,
    current_stage_index: int,
    completion_result: StageCompletionResult,
    now: str,
) -> StageTransitionResult:
    """Handle a successful stage completion.

    Marks the stage as completed and determines the next action based on
    the stage's on-complete configuration.

    Args:
        workflow_state: Current workflow state (will be modified)
        workflow_def: The parsed workflow definition
        stage_def: The stage definition
        stage_state: The stage state (will be modified)
        current_stage_index: Index of current stage in stages list
        completion_result: How the stage completed
        now: Current timestamp in ISO format

    Returns:
        StageTransitionResult indicating next action
    """
    # Mark stage as completed
    stage_state.status = "completed"
    stage_state.completed_at = now
    stage_state.exit_reason = completion_result.reason

    # Determine next action based on on-complete setting
    on_complete = stage_def.on_complete

    if on_complete == "stop":
        # Workflow is complete
        workflow_state.status = "completed"
        workflow_state.completed_at = now
        return StageTransitionResult(
            action="complete",
            message=f"Stage '{stage_def.name}' completed, workflow finished (on-complete: stop)",
        )

    elif on_complete == "next":
        # Advance to next stage
        next_index = current_stage_index + 1

        if next_index >= len(workflow_def.stages):
            # No more stages - workflow is complete
            workflow_state.status = "completed"
            workflow_state.completed_at = now
            return StageTransitionResult(
                action="complete",
                message=f"Stage '{stage_def.name}' completed, all stages finished",
            )

        next_stage = workflow_def.stages[next_index]
        return StageTransitionResult(
            action="next_stage",
            next_stage_name=next_stage.name,
            next_stage_index=next_index,
            message=f"Stage '{stage_def.name}' completed, starting '{next_stage.name}'",
        )

    elif on_complete.startswith("goto:"):
        # Jump to a specific stage
        target_name = on_complete[5:]  # Remove "goto:" prefix

        # Find the target stage index
        target_index = None
        for i, stage in enumerate(workflow_def.stages):
            if stage.name == target_name:
                target_index = i
                break

        if target_index is None:
            # This shouldn't happen if validation worked, but handle it
            workflow_state.status = "failed"
            workflow_state.completed_at = now
            return StageTransitionResult(
                action="fail",
                message=f"Stage '{stage_def.name}': goto target '{target_name}' not found",
            )

        return StageTransitionResult(
            action="next_stage",
            next_stage_name=target_name,
            next_stage_index=target_index,
            message=f"Stage '{stage_def.name}' completed, jumping to '{target_name}'",
        )

    else:
        # Unknown on-complete value (shouldn't happen after validation)
        workflow_state.status = "failed"
        workflow_state.completed_at = now
        return StageTransitionResult(
            action="fail",
            message=f"Stage '{stage_def.name}': unknown on-complete value '{on_complete}'",
        )


def _handle_stage_failure(
    workflow_state: WorkflowState,
    workflow_def: WorkflowDefinition,
    stage_def: StageDefinition,
    stage_state: StageState,
    current_stage_index: int,
    completion_result: StageCompletionResult,
    workflow_dir: Path,
    now: str,
) -> StageTransitionResult:
    """Handle a failed stage.

    Determines the next action based on the stage's on-failure configuration:
    - stop: Fail the workflow
    - retry: Retry the stage (up to max-retries)
    - skip: Mark stage as skipped and continue

    Args:
        workflow_state: Current workflow state (will be modified)
        workflow_def: The parsed workflow definition
        stage_def: The stage definition
        stage_state: The stage state (will be modified)
        current_stage_index: Index of current stage in stages list
        completion_result: How the stage completed
        workflow_dir: Directory containing the workflow YAML
        now: Current timestamp in ISO format

    Returns:
        StageTransitionResult indicating next action
    """
    on_failure = stage_def.on_failure

    if on_failure == "stop":
        # Fail the workflow
        stage_state.status = "failed"
        stage_state.completed_at = now
        stage_state.exit_reason = completion_result.reason
        workflow_state.status = "failed"
        workflow_state.completed_at = now

        return StageTransitionResult(
            action="fail",
            message=f"Stage '{stage_def.name}' failed ({completion_result.reason}), workflow stopped",
        )

    elif on_failure == "retry":
        # Check if we have retries left
        max_retries = stage_def.max_retries
        attempts = stage_state.attempts

        if attempts < max_retries:
            # Retry the stage
            return StageTransitionResult(
                action="retry",
                next_stage_name=stage_def.name,
                next_stage_index=current_stage_index,
                message=f"Stage '{stage_def.name}' failed, retrying (attempt {attempts + 1}/{max_retries})",
            )
        else:
            # Exhausted retries - fail the workflow
            stage_state.status = "failed"
            stage_state.completed_at = now
            stage_state.exit_reason = completion_result.reason
            workflow_state.status = "failed"
            workflow_state.completed_at = now

            return StageTransitionResult(
                action="fail",
                message=f"Stage '{stage_def.name}' failed after {attempts} attempts, workflow stopped",
            )

    elif on_failure == "skip":
        # Skip the stage and continue
        stage_state.status = "skipped"
        stage_state.completed_at = now
        stage_state.exit_reason = "skipped"

        # Advance to next stage
        next_index = current_stage_index + 1

        if next_index >= len(workflow_def.stages):
            # No more stages - workflow is complete
            workflow_state.status = "completed"
            workflow_state.completed_at = now
            return StageTransitionResult(
                action="complete",
                message=f"Stage '{stage_def.name}' skipped ({completion_result.reason}), all stages finished",
            )

        next_stage = workflow_def.stages[next_index]
        return StageTransitionResult(
            action="skip",
            next_stage_name=next_stage.name,
            next_stage_index=next_index,
            message=f"Stage '{stage_def.name}' skipped ({completion_result.reason}), starting '{next_stage.name}'",
        )

    else:
        # Unknown on-failure value (shouldn't happen after validation)
        stage_state.status = "failed"
        stage_state.completed_at = now
        stage_state.exit_reason = completion_result.reason
        workflow_state.status = "failed"
        workflow_state.completed_at = now

        return StageTransitionResult(
            action="fail",
            message=f"Stage '{stage_def.name}': unknown on-failure value '{on_failure}'",
        )


def start_next_stage(
    workflow_state: WorkflowState,
    workflow_def: WorkflowDefinition,
    transition: StageTransitionResult,
    workflow_dir: Path,
    is_retry: bool = False,
) -> Optional[Worker]:
    """Start the next stage of a workflow after a transition.

    Updates the workflow state to reflect the new stage and spawns the
    worker for that stage.

    Args:
        workflow_state: Current workflow state (will be modified)
        workflow_def: The parsed workflow definition
        transition: The transition result indicating which stage to start
        workflow_dir: Directory containing the workflow YAML
        is_retry: Whether this is a retry attempt (affects attempt counting)

    Returns:
        The spawned Worker if successful, None if there's no next stage
        or if spawning fails

    Raises:
        RuntimeError: If worker spawning fails
    """
    if transition.next_stage_name is None or transition.next_stage_index < 0:
        return None

    next_stage_name = transition.next_stage_name
    next_stage_index = transition.next_stage_index
    next_stage_def = workflow_def.stages[next_stage_index]

    now = datetime.now(timezone.utc).isoformat()

    # Update workflow state
    workflow_state.current_stage = next_stage_name
    workflow_state.current_stage_index = next_stage_index

    # Get or create stage state
    if next_stage_name not in workflow_state.stages:
        workflow_state.stages[next_stage_name] = StageState()

    stage_state = workflow_state.stages[next_stage_name]
    stage_state.status = "running"
    stage_state.started_at = now
    stage_state.worker_name = f"{workflow_state.name}-{next_stage_name}"

    if is_retry:
        # Increment attempt count for retry
        stage_state.attempts += 1
    else:
        # First attempt (could be fresh start or skip to new stage)
        stage_state.attempts = 1

    # Save workflow state before spawning (in case spawn fails)
    save_workflow_state(workflow_state)

    # Spawn the stage worker
    worker = spawn_workflow_stage(
        workflow_name=workflow_state.name,
        workflow_def=workflow_def,
        stage_def=next_stage_def,
        workflow_dir=workflow_dir,
    )

    return worker


def run_workflow_monitor(
    workflow_name: str,
    workflow_def: WorkflowDefinition,
    workflow_dir: Path,
    poll_interval: float = 2.0,
) -> None:
    """Run the workflow monitor loop in foreground.

    Manages the execution of a workflow from start to completion by:
    1. Waiting for scheduled start time (if scheduled)
    2. Monitoring the current stage for completion
    3. Handling stage transitions (success, failure, retry, skip)
    4. Starting the next stage or completing the workflow

    This runs as a foreground process. Users can background it with & or nohup.

    The monitor prints progress messages to stdout and saves workflow state
    to disk after each transition.

    Args:
        workflow_name: Name of the workflow to monitor
        workflow_def: The parsed workflow definition
        workflow_dir: Directory containing the workflow YAML
        poll_interval: Seconds between status checks (default 2.0)
    """
    while True:
        # Load current workflow state
        workflow_state = load_workflow_state(workflow_name)
        if workflow_state is None:
            print(f"swarm: workflow '{workflow_name}' not found, exiting monitor")
            return

        # Handle based on workflow status
        if workflow_state.status == "scheduled":
            # Wait for scheduled start time
            if workflow_state.scheduled_for:
                scheduled_time = datetime.fromisoformat(
                    workflow_state.scheduled_for.replace('Z', '+00:00')
                )
                now = datetime.now(timezone.utc)
                if now < scheduled_time:
                    # Not yet time, sleep and check again
                    # Sleep for shorter interval as we get closer
                    remaining = (scheduled_time - now).total_seconds()
                    sleep_time = min(poll_interval, remaining, 60)
                    time.sleep(sleep_time)
                    continue

            # Time to start - transition to running
            workflow_state.status = "running"
            workflow_state.started_at = datetime.now(timezone.utc).isoformat()

            # Start first stage
            first_stage = workflow_def.stages[0]
            workflow_state.current_stage = first_stage.name
            workflow_state.current_stage_index = 0
            workflow_state.stages[first_stage.name].status = "running"
            workflow_state.stages[first_stage.name].started_at = workflow_state.started_at
            workflow_state.stages[first_stage.name].attempts = 1
            workflow_state.stages[first_stage.name].worker_name = f"{workflow_name}-{first_stage.name}"

            save_workflow_state(workflow_state)

            stage_count = len(workflow_def.stages)
            print(f"swarm: workflow '{workflow_name}' starting (stage 1/{stage_count}: {first_stage.name})")

            # Spawn the first stage worker
            try:
                worker = spawn_workflow_stage(
                    workflow_name=workflow_name,
                    workflow_def=workflow_def,
                    stage_def=first_stage,
                    workflow_dir=workflow_dir,
                )
                print(f"swarm: spawned worker '{worker.name}'")
            except RuntimeError as e:
                # Failed to spawn worker - update workflow state
                workflow_state.status = "failed"
                workflow_state.stages[first_stage.name].status = "failed"
                workflow_state.stages[first_stage.name].exit_reason = "error"
                workflow_state.completed_at = datetime.now(timezone.utc).isoformat()
                save_workflow_state(workflow_state)
                print(f"swarm: error: failed to spawn stage worker: {e}", file=sys.stderr)
                return

        elif workflow_state.status == "running":
            # Monitor current stage for completion
            current_stage_name = workflow_state.current_stage
            current_stage_index = workflow_state.current_stage_index

            if current_stage_name is None:
                # Should not happen, but handle gracefully
                print(f"swarm: error: workflow running but no current stage", file=sys.stderr)
                workflow_state.status = "failed"
                workflow_state.completed_at = datetime.now(timezone.utc).isoformat()
                save_workflow_state(workflow_state)
                return

            # Get stage definition and state
            stage_def = workflow_def.stages[current_stage_index]
            stage_state = workflow_state.stages.get(current_stage_name)

            if stage_state is None:
                print(f"swarm: error: stage state for '{current_stage_name}' not found", file=sys.stderr)
                workflow_state.status = "failed"
                workflow_state.completed_at = datetime.now(timezone.utc).isoformat()
                save_workflow_state(workflow_state)
                return

            # Get the worker for this stage
            state = State()
            worker = state.get_worker(stage_state.worker_name)

            if worker is None:
                # Worker doesn't exist - might have been killed externally
                # Check if worker already completed (could have been removed after completion)
                if stage_state.status == "completed":
                    # Already completed, proceed with transition
                    pass
                else:
                    # Worker killed externally - treat as failure
                    print(f"swarm: stage worker '{stage_state.worker_name}' not found, treating as failure")
                    completion_result = StageCompletionResult(
                        completed=True,
                        success=False,
                        reason="error",
                        details="Worker not found - may have been killed externally",
                    )
                    _handle_workflow_transition(
                        workflow_name=workflow_name,
                        workflow_state=workflow_state,
                        workflow_def=workflow_def,
                        stage_def=stage_def,
                        completion_result=completion_result,
                        workflow_dir=workflow_dir,
                    )
                    continue

            # Monitor stage completion
            completion_result = monitor_stage_completion(
                workflow_name=workflow_name,
                stage_def=stage_def,
                worker=worker,
                poll_interval=poll_interval,
            )

            # Stage completed - handle transition
            _handle_workflow_transition(
                workflow_name=workflow_name,
                workflow_state=workflow_state,
                workflow_def=workflow_def,
                stage_def=stage_def,
                completion_result=completion_result,
                workflow_dir=workflow_dir,
            )

            # Reload state to check if workflow finished
            workflow_state = load_workflow_state(workflow_name)
            if workflow_state is None or workflow_state.status in ("completed", "failed", "cancelled"):
                return

        elif workflow_state.status in ("completed", "failed", "cancelled"):
            # Workflow finished
            return

        elif workflow_state.status == "created":
            # Workflow created but not started - shouldn't happen if called from cmd_workflow_run
            # But handle by starting it
            workflow_state.status = "running"
            workflow_state.started_at = datetime.now(timezone.utc).isoformat()
            save_workflow_state(workflow_state)
            continue

        else:
            # Unknown status
            print(f"swarm: unknown workflow status '{workflow_state.status}', exiting monitor", file=sys.stderr)
            return


def _handle_workflow_transition(
    workflow_name: str,
    workflow_state: WorkflowState,
    workflow_def: WorkflowDefinition,
    stage_def: StageDefinition,
    completion_result: StageCompletionResult,
    workflow_dir: Path,
) -> None:
    """Handle workflow transition after stage completion.

    Updates workflow state, logs transition, and spawns next stage if needed.

    Args:
        workflow_name: Name of the workflow
        workflow_state: Current workflow state (will be reloaded for update)
        workflow_def: The parsed workflow definition
        stage_def: The stage that just completed
        completion_result: How the stage completed
        workflow_dir: Directory containing the workflow YAML
    """
    # Reload state with lock for update
    workflow_state = load_workflow_state(workflow_name)
    if workflow_state is None:
        return

    # Handle the transition
    transition = handle_stage_transition(
        workflow_state=workflow_state,
        workflow_def=workflow_def,
        completion_result=completion_result,
        workflow_dir=workflow_dir,
    )

    # Log the transition
    stage_count = len(workflow_def.stages)
    current_index = workflow_state.current_stage_index + 1  # 1-based for display

    if completion_result.success:
        print(f"swarm: stage '{stage_def.name}' completed ({completion_result.reason})")
    else:
        print(f"swarm: stage '{stage_def.name}' failed ({completion_result.reason})")

    print(f"swarm: {transition.message}")

    # Save state after transition decision
    save_workflow_state(workflow_state)

    # Handle the action
    if transition.action == "complete":
        print(f"swarm: workflow '{workflow_name}' completed successfully")

    elif transition.action == "fail":
        print(f"swarm: workflow '{workflow_name}' failed")

    elif transition.action in ("next_stage", "skip", "retry"):
        # Start the next stage
        is_retry = transition.action == "retry"
        try:
            worker = start_next_stage(
                workflow_state=workflow_state,
                workflow_def=workflow_def,
                transition=transition,
                workflow_dir=workflow_dir,
                is_retry=is_retry,
            )
            if worker:
                next_index = transition.next_stage_index + 1  # 1-based for display
                print(f"swarm: started stage {next_index}/{stage_count}: '{transition.next_stage_name}'")
                print(f"swarm: spawned worker '{worker.name}'")
            else:
                # Failed to spawn next stage
                workflow_state.status = "failed"
                workflow_state.completed_at = datetime.now(timezone.utc).isoformat()
                save_workflow_state(workflow_state)
                print(f"swarm: error: failed to start next stage", file=sys.stderr)
        except RuntimeError as e:
            workflow_state.status = "failed"
            workflow_state.completed_at = datetime.now(timezone.utc).isoformat()
            save_workflow_state(workflow_state)
            print(f"swarm: error: failed to spawn stage worker: {e}", file=sys.stderr)


def cmd_workflow(args) -> None:
    """Workflow management commands.

    Dispatches to workflow subcommands:
    - validate: Validate workflow YAML without running
    - run: Run a workflow from YAML file
    - status: Show workflow status
    - list: List all workflows
    - cancel: Cancel a running workflow
    - resume: Resume a failed/cancelled workflow
    - resume-all: Resume all interrupted workflows
    - logs: View workflow logs
    """
    if args.workflow_command == "validate":
        cmd_workflow_validate(args)
    elif args.workflow_command == "run":
        cmd_workflow_run(args)
    elif args.workflow_command == "status":
        cmd_workflow_status(args)
    elif args.workflow_command == "list":
        cmd_workflow_list(args)
    elif args.workflow_command == "cancel":
        cmd_workflow_cancel(args)
    elif args.workflow_command == "resume":
        cmd_workflow_resume(args)
    elif args.workflow_command == "resume-all":
        cmd_workflow_resume_all(args)
    elif args.workflow_command == "logs":
        cmd_workflow_logs(args)
    else:
        print(f"Error: workflow subcommand '{args.workflow_command}' not yet implemented", file=sys.stderr)
        sys.exit(1)


def cmd_workflow_validate(args) -> None:
    """Validate workflow YAML without running it.

    Checks the workflow definition for syntax errors, missing required fields,
    invalid values, and verifies that all prompt files exist.

    Args:
        args: Namespace with validate arguments (file: path to YAML file)

    Exit codes:
        0: Validation passed
        1: Validation failed (errors printed to stderr)
    """
    # Resolve the workflow file path (checks repo-local then global)
    try:
        yaml_path = resolve_workflow_file(args.file)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    errors = []

    # Parse and validate the YAML structure
    try:
        workflow = parse_workflow_yaml(yaml_path)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except WorkflowValidationError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    # Validate that all prompt files exist
    # Use the directory containing the workflow file as the base path
    workflow_dir = Path(yaml_path).parent
    prompt_errors = validate_workflow_prompt_files(workflow, workflow_dir)
    errors.extend(prompt_errors)

    # If there are errors, report them and exit with error
    if errors:
        print("Validation errors:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        sys.exit(1)

    # Success message
    stage_count = len(workflow.stages)
    stage_word = "stage" if stage_count == 1 else "stages"
    print(f"Workflow '{workflow.name}' is valid ({stage_count} {stage_word})")


def cmd_workflow_status(args) -> None:
    """Show detailed status of a workflow.

    Displays the overall workflow status, current stage, and the status
    of each individual stage. Supports both text and JSON output formats.

    Args:
        args: Namespace with status arguments:
            - name: Workflow name
            - format: Output format ('text' or 'json')

    Exit codes:
        0: Success
        1: Workflow not found
    """
    workflow_name = args.name
    output_format = args.format

    # Load workflow state
    workflow_state = load_workflow_state(workflow_name)
    if workflow_state is None:
        print(f"Error: workflow '{workflow_name}' not found", file=sys.stderr)
        sys.exit(1)

    if output_format == "json":
        # JSON output
        output = workflow_state.to_dict()
        print(json.dumps(output, indent=2))
    else:
        # Text output
        print(f"Workflow: {workflow_state.name}")
        print(f"Status: {workflow_state.status}")

        if workflow_state.current_stage:
            print(f"Current: {workflow_state.current_stage}")

        if workflow_state.scheduled_for:
            try:
                scheduled_str = time_until(workflow_state.scheduled_for)
                print(f"Scheduled: {workflow_state.scheduled_for} ({scheduled_str})")
            except (ValueError, TypeError):
                print(f"Scheduled: {workflow_state.scheduled_for}")

        if workflow_state.started_at:
            try:
                started_str = relative_time(workflow_state.started_at)
                print(f"Started: {workflow_state.started_at} ({started_str} ago)")
            except (ValueError, TypeError):
                print(f"Started: {workflow_state.started_at}")

        if workflow_state.completed_at:
            try:
                completed_str = relative_time(workflow_state.completed_at)
                print(f"Completed: {workflow_state.completed_at} ({completed_str} ago)")
            except (ValueError, TypeError):
                print(f"Completed: {workflow_state.completed_at}")

        print(f"Source: {workflow_state.workflow_file}")

        # Print stages table
        if workflow_state.stages:
            print()
            print("Stages:")
            print(f"  {'Name':<20} {'Status':<12} {'Worker':<30} {'Attempts':<8} {'Exit Reason'}")
            print(f"  {'-'*20} {'-'*12} {'-'*30} {'-'*8} {'-'*15}")

            # Get stage order from workflow definition if available, otherwise use dict order
            stage_names = list(workflow_state.stages.keys())

            for stage_name in stage_names:
                stage_state = workflow_state.stages[stage_name]
                worker_name = stage_state.worker_name or "-"
                attempts = str(stage_state.attempts) if stage_state.attempts > 0 else "-"
                exit_reason = stage_state.exit_reason or "-"
                print(f"  {stage_name:<20} {stage_state.status:<12} {worker_name:<30} {attempts:<8} {exit_reason}")


def cmd_workflow_list(args) -> None:
    """List all workflows.

    Shows a table or JSON of all workflow states with their current status,
    stage, and timing information.

    Args:
        args: Namespace with list arguments:
            - format: Output format ('table' or 'json')

    Exit codes:
        0: Success (even if no workflows found)
    """
    workflows = list_workflow_states()

    if not workflows:
        if args.format == "json":
            print("[]")
        else:
            print("No workflows found")
        return

    if args.format == "json":
        output = []
        for wf in workflows:
            output.append(wf.to_dict())
        print(json.dumps(output, indent=2))
    else:
        # Table format
        # Calculate column widths for better formatting
        print(f"{'NAME':<25} {'STATUS':<12} {'CURRENT':<15} {'STARTED':<12} {'SOURCE'}")

        for wf in workflows:
            # Format current stage
            current_stage = wf.current_stage or "-"

            # Format started time
            if wf.started_at:
                try:
                    started_str = relative_time(wf.started_at) + " ago"
                except (ValueError, TypeError):
                    started_str = wf.started_at[:10] if wf.started_at else "-"
            else:
                started_str = "-"

            # Truncate source path for display
            source = wf.workflow_file
            if len(source) > 40:
                source = "..." + source[-37:]

            print(f"{wf.name:<25} {wf.status:<12} {current_stage:<15} {started_str:<12} {source}")


def cmd_workflow_cancel(args) -> None:
    """Cancel a running workflow.

    Stops the workflow execution by:
    1. Killing the current stage worker (if any)
    2. Stopping any active heartbeat for the stage worker
    3. Setting the workflow status to 'cancelled'

    Args:
        args: Namespace with cancel arguments:
            - name: Workflow name
            - force: Whether to use SIGKILL instead of graceful shutdown

    Exit codes:
        0: Workflow cancelled successfully
        1: Workflow not found or not in cancellable state
    """
    workflow_name = args.name
    force = args.force

    # Load workflow state
    workflow_state = load_workflow_state(workflow_name)
    if workflow_state is None:
        print(f"Error: workflow '{workflow_name}' not found", file=sys.stderr)
        sys.exit(1)

    # Check if workflow is in a cancellable state
    if workflow_state.status not in ("running", "scheduled"):
        print(f"Error: workflow '{workflow_name}' is not running or scheduled (status: {workflow_state.status})", file=sys.stderr)
        sys.exit(1)

    # Get the current stage worker name (if workflow is running)
    worker_name = None
    current_stage_name = workflow_state.current_stage
    if current_stage_name and current_stage_name in workflow_state.stages:
        stage_state = workflow_state.stages[current_stage_name]
        worker_name = stage_state.worker_name

    # Kill the current stage worker if it exists
    if worker_name:
        state = State()
        worker = state.get_worker(worker_name)
        if worker:
            # Kill tmux worker
            if worker.tmux:
                socket = worker.tmux.socket if worker.tmux else None
                cmd_prefix = tmux_cmd_prefix(socket)
                subprocess.run(
                    cmd_prefix + ["kill-window", "-t", f"{worker.tmux.session}:{worker.tmux.window}"],
                    capture_output=True
                )
            # Kill non-tmux worker with PID
            elif worker.pid:
                try:
                    if force:
                        os.kill(worker.pid, signal.SIGKILL)
                    else:
                        # Graceful shutdown with SIGTERM first
                        os.kill(worker.pid, signal.SIGTERM)
                        # Wait up to 5 seconds for process to die
                        for _ in range(50):
                            time.sleep(0.1)
                            if not process_alive(worker.pid):
                                break
                        else:
                            # Process still alive, use SIGKILL
                            if process_alive(worker.pid):
                                os.kill(worker.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass  # Process already dead

            # Update worker status
            worker.status = "stopped"
            state.save()

            # Stop heartbeat if active for this worker
            heartbeat_state = load_heartbeat_state(worker_name)
            if heartbeat_state and heartbeat_state.status in ("active", "paused"):
                stop_heartbeat_monitor(heartbeat_state)
                heartbeat_state.status = "stopped"
                heartbeat_state.monitor_pid = None
                save_heartbeat_state(heartbeat_state)

    # Update current stage state to failed/cancelled
    if current_stage_name and current_stage_name in workflow_state.stages:
        stage_state = workflow_state.stages[current_stage_name]
        if stage_state.status == "running":
            stage_state.status = "failed"
            stage_state.exit_reason = "cancelled"
            stage_state.completed_at = datetime.now(timezone.utc).isoformat()

    # Update workflow state
    workflow_state.status = "cancelled"
    workflow_state.completed_at = datetime.now(timezone.utc).isoformat()
    save_workflow_state(workflow_state)

    print(f"Workflow '{workflow_name}' cancelled")


def cmd_workflow_resume(args) -> None:
    """Resume a failed or cancelled workflow.

    Restarts a workflow from the failed/current stage or from a specified
    stage using the --from flag. Resets the resume stage and all subsequent
    stages to pending before starting.

    Args:
        args: Namespace with resume arguments:
            - name: Workflow name
            - from_stage: Optional stage name to resume from

    Exit codes:
        0: Workflow resumed successfully
        1: Workflow not found, not in resumable state, or invalid stage name
    """
    workflow_name = args.name
    from_stage = args.from_stage

    # Load workflow state
    workflow_state = load_workflow_state(workflow_name)
    if workflow_state is None:
        print(f"Error: workflow '{workflow_name}' not found", file=sys.stderr)
        sys.exit(1)

    # Check if workflow is in a resumable state
    if workflow_state.status not in ("failed", "cancelled"):
        print(f"Error: workflow '{workflow_name}' is not in a resumable state (status: {workflow_state.status})", file=sys.stderr)
        print("Only 'failed' or 'cancelled' workflows can be resumed.", file=sys.stderr)
        sys.exit(1)

    # Load the workflow definition from the stored YAML copy
    yaml_copy_path = get_workflow_yaml_copy_path(workflow_name)
    if not yaml_copy_path.exists():
        print(f"Error: workflow definition not found at {yaml_copy_path}", file=sys.stderr)
        print("The workflow state exists but the YAML definition is missing.", file=sys.stderr)
        sys.exit(1)

    try:
        workflow_def = parse_workflow_yaml(str(yaml_copy_path))
    except (FileNotFoundError, WorkflowValidationError) as e:
        print(f"Error: failed to parse workflow definition: {e}", file=sys.stderr)
        sys.exit(1)

    # Get the workflow directory (parent of the original workflow file)
    if workflow_state.workflow_file:
        workflow_dir = Path(workflow_state.workflow_file).parent
    else:
        workflow_dir = yaml_copy_path.parent

    # Determine which stage to resume from
    stage_names = [s.name for s in workflow_def.stages]

    if from_stage:
        # Validate the specified stage exists
        if from_stage not in stage_names:
            print(f"Error: stage '{from_stage}' not found in workflow", file=sys.stderr)
            print(f"Available stages: {', '.join(stage_names)}", file=sys.stderr)
            sys.exit(1)
        resume_stage_name = from_stage
        resume_stage_index = stage_names.index(from_stage)
    else:
        # Resume from the failed/current stage
        if workflow_state.current_stage and workflow_state.current_stage in stage_names:
            resume_stage_name = workflow_state.current_stage
            resume_stage_index = stage_names.index(resume_stage_name)
        else:
            # Fallback: find the first non-completed stage
            resume_stage_index = 0
            for i, stage_name in enumerate(stage_names):
                stage_state = workflow_state.stages.get(stage_name)
                if stage_state is None or stage_state.status != "completed":
                    resume_stage_index = i
                    break
            resume_stage_name = stage_names[resume_stage_index]

    # Reset the resume stage and all subsequent stages to pending
    for i in range(resume_stage_index, len(stage_names)):
        stage_name = stage_names[i]
        if stage_name in workflow_state.stages:
            stage_state = workflow_state.stages[stage_name]
            # Keep attempt count for retry tracking
            old_attempts = stage_state.attempts
            # Reset stage state
            stage_state.status = "pending"
            stage_state.started_at = None
            stage_state.completed_at = None
            stage_state.worker_name = None
            stage_state.exit_reason = None
            # Preserve attempts for the resume stage (for retry tracking)
            if i == resume_stage_index:
                stage_state.attempts = old_attempts
            else:
                stage_state.attempts = 0
        else:
            # Create new stage state
            workflow_state.stages[stage_name] = StageState(status="pending")

    # Update workflow state to running
    now = datetime.now(timezone.utc).isoformat()
    workflow_state.status = "running"
    workflow_state.completed_at = None  # Clear completion time

    # Update started_at only if this is the first run
    if not workflow_state.started_at:
        workflow_state.started_at = now

    # Set up the resume stage
    resume_stage_def = workflow_def.stages[resume_stage_index]
    workflow_state.current_stage = resume_stage_name
    workflow_state.current_stage_index = resume_stage_index
    workflow_state.stages[resume_stage_name].status = "running"
    workflow_state.stages[resume_stage_name].started_at = now
    workflow_state.stages[resume_stage_name].attempts += 1
    workflow_state.stages[resume_stage_name].worker_name = f"{workflow_name}-{resume_stage_name}"

    save_workflow_state(workflow_state)

    stage_count = len(workflow_def.stages)
    print(f"Workflow '{workflow_name}' resumed from stage '{resume_stage_name}'")

    # Spawn the resume stage worker
    try:
        worker = spawn_workflow_stage(
            workflow_name=workflow_name,
            workflow_def=workflow_def,
            stage_def=resume_stage_def,
            workflow_dir=workflow_dir,
        )
        print(f"Spawned worker '{worker.name}' (stage {resume_stage_index + 1}/{stage_count})")
    except RuntimeError as e:
        # Failed to spawn worker - update workflow state
        workflow_state.status = "failed"
        workflow_state.stages[resume_stage_name].status = "failed"
        workflow_state.stages[resume_stage_name].exit_reason = "error"
        workflow_state.completed_at = now
        save_workflow_state(workflow_state)
        print(f"Error: failed to spawn stage worker: {e}", file=sys.stderr)
        sys.exit(1)

    # Start monitor loop to manage workflow execution
    run_workflow_monitor(
        workflow_name=workflow_name,
        workflow_def=workflow_def,
        workflow_dir=workflow_dir,
    )


def cmd_workflow_resume_all(args) -> None:
    """Resume all interrupted workflows.

    Finds workflows that were 'running' or 'scheduled' when the system
    was interrupted (e.g., after reboot or monitor killed). Offers to
    resume them either in foreground (sequentially) or background.

    Args:
        args: Namespace with resume-all arguments:
            - dry_run: If True, show what would be resumed without resuming
            - background: If True, run workflow monitors in background

    Exit codes:
        0: Success (or no workflows to resume)
        1: Error during resume
    """
    dry_run = args.dry_run
    background = args.background

    # Find interrupted workflows
    interrupted = check_interrupted_workflows()

    if not interrupted:
        print("No interrupted workflows found.")
        return

    count = len(interrupted)
    workflow_word = "workflow" if count == 1 else "workflows"

    if dry_run:
        print(f"Found {count} interrupted {workflow_word}:")
        for workflow_state in interrupted:
            stage_info = ""
            if workflow_state.status == "running" and workflow_state.current_stage:
                stage_info = f" (stage: {workflow_state.current_stage})"
            elif workflow_state.status == "scheduled" and workflow_state.scheduled_for:
                stage_info = f" (scheduled: {workflow_state.scheduled_for})"
            print(f"  - {workflow_state.name}: {workflow_state.status}{stage_info}")
        print(f"\nRun without --dry-run to resume these workflows.")
        return

    print(f"Resuming {count} interrupted {workflow_word}...")

    resumed_count = 0
    failed_count = 0

    for workflow_state in interrupted:
        workflow_name = workflow_state.name
        print(f"\nResuming workflow '{workflow_name}'...")

        # Load the workflow definition from the stored YAML copy
        yaml_copy_path = get_workflow_yaml_copy_path(workflow_name)
        if not yaml_copy_path.exists():
            print(f"  Error: workflow definition not found at {yaml_copy_path}", file=sys.stderr)
            failed_count += 1
            continue

        try:
            workflow_def = parse_workflow_yaml(str(yaml_copy_path))
        except (FileNotFoundError, WorkflowValidationError) as e:
            print(f"  Error: failed to parse workflow definition: {e}", file=sys.stderr)
            failed_count += 1
            continue

        # Get the workflow directory
        if workflow_state.workflow_file:
            workflow_dir = Path(workflow_state.workflow_file).parent
        else:
            workflow_dir = yaml_copy_path.parent

        if background:
            # Spawn workflow monitor in background using nohup
            # We need to start a subprocess that runs the workflow monitor
            try:
                _resume_workflow_in_background(
                    workflow_name=workflow_name,
                    workflow_state=workflow_state,
                    workflow_def=workflow_def,
                    workflow_dir=workflow_dir,
                )
                print(f"  Started workflow '{workflow_name}' in background")
                resumed_count += 1
            except Exception as e:
                print(f"  Error: failed to start background monitor: {e}", file=sys.stderr)
                failed_count += 1
        else:
            # Resume workflow in foreground (sequential)
            # For foreground mode, we resume each workflow one at a time
            try:
                _resume_workflow_foreground(
                    workflow_name=workflow_name,
                    workflow_state=workflow_state,
                    workflow_def=workflow_def,
                    workflow_dir=workflow_dir,
                )
                resumed_count += 1
            except Exception as e:
                print(f"  Error: failed to resume workflow: {e}", file=sys.stderr)
                failed_count += 1

    # Print summary
    print(f"\n{resumed_count} {workflow_word} resumed, {failed_count} failed")

    if failed_count > 0:
        sys.exit(1)


def _resume_workflow_foreground(
    workflow_name: str,
    workflow_state: WorkflowState,
    workflow_def: WorkflowDefinition,
    workflow_dir: Path,
) -> None:
    """Resume a workflow in foreground (blocking).

    This handles both 'running' and 'scheduled' workflows:
    - For 'running': restarts from the current stage
    - For 'scheduled': restarts the scheduling wait

    Args:
        workflow_name: Name of the workflow
        workflow_state: Current workflow state
        workflow_def: Parsed workflow definition
        workflow_dir: Directory containing the workflow YAML

    Raises:
        RuntimeError: If workflow fails to resume
    """
    if workflow_state.status == "scheduled":
        # For scheduled workflows, just restart the monitor to wait for the schedule
        print(f"  Workflow '{workflow_name}' is scheduled, resuming schedule wait...")
        run_workflow_monitor(
            workflow_name=workflow_name,
            workflow_def=workflow_def,
            workflow_dir=workflow_dir,
        )
    elif workflow_state.status == "running":
        # For running workflows, we need to restart the current stage
        current_stage_name = workflow_state.current_stage
        current_stage_index = workflow_state.current_stage_index

        if current_stage_name is None:
            raise RuntimeError("Running workflow has no current stage")

        # Get the stage definition
        stage_def = workflow_def.stages[current_stage_index]

        # Check if the stage worker is still running
        state = State()
        stage_state = workflow_state.stages.get(current_stage_name)
        worker_name = stage_state.worker_name if stage_state else None

        if worker_name:
            worker = state.get_worker(worker_name)
            if worker:
                actual_status = refresh_worker_status(worker)
                if actual_status == "running":
                    # Worker is still running, just restart the monitor
                    print(f"  Stage worker '{worker_name}' still running, resuming monitoring...")
                    run_workflow_monitor(
                        workflow_name=workflow_name,
                        workflow_def=workflow_def,
                        workflow_dir=workflow_dir,
                    )
                    return

        # Worker not running, need to respawn it
        print(f"  Stage worker not running, respawning stage '{current_stage_name}'...")

        # Update stage state
        now = datetime.now(timezone.utc).isoformat()
        if stage_state:
            stage_state.started_at = now
            stage_state.attempts += 1
            stage_state.worker_name = f"{workflow_name}-{current_stage_name}"

        save_workflow_state(workflow_state)

        # Spawn the stage worker
        worker = spawn_workflow_stage(
            workflow_name=workflow_name,
            workflow_def=workflow_def,
            stage_def=stage_def,
            workflow_dir=workflow_dir,
        )
        print(f"  Spawned worker '{worker.name}'")

        # Start monitor loop
        run_workflow_monitor(
            workflow_name=workflow_name,
            workflow_def=workflow_def,
            workflow_dir=workflow_dir,
        )


def _resume_workflow_in_background(
    workflow_name: str,
    workflow_state: WorkflowState,
    workflow_def: WorkflowDefinition,
    workflow_dir: Path,
) -> None:
    """Resume a workflow in background using subprocess.

    Spawns a new process that runs the workflow monitor. The process
    is detached using nohup-like behavior.

    Args:
        workflow_name: Name of the workflow
        workflow_state: Current workflow state
        workflow_def: Parsed workflow definition
        workflow_dir: Directory containing the workflow YAML

    Raises:
        RuntimeError: If failed to start background process
    """
    import subprocess
    import os

    # For running workflows, we may need to respawn the stage worker first
    if workflow_state.status == "running":
        current_stage_name = workflow_state.current_stage
        current_stage_index = workflow_state.current_stage_index

        if current_stage_name is not None:
            stage_state = workflow_state.stages.get(current_stage_name)
            worker_name = stage_state.worker_name if stage_state else None

            if worker_name:
                state = State()
                worker = state.get_worker(worker_name)
                if not worker:
                    # Worker not found, need to respawn it
                    stage_def = workflow_def.stages[current_stage_index]
                    now = datetime.now(timezone.utc).isoformat()
                    if stage_state:
                        stage_state.started_at = now
                        stage_state.attempts += 1
                        stage_state.worker_name = f"{workflow_name}-{current_stage_name}"
                    save_workflow_state(workflow_state)

                    worker = spawn_workflow_stage(
                        workflow_name=workflow_name,
                        workflow_def=workflow_def,
                        stage_def=stage_def,
                        workflow_dir=workflow_dir,
                    )

    # Start workflow monitor in background
    # Use a subprocess that runs swarm workflow internal-monitor
    # Since we don't have an internal-monitor command, we'll use nohup + python
    yaml_copy_path = get_workflow_yaml_copy_path(workflow_name)

    # Create a simple Python script to run the monitor
    monitor_script = f'''
import sys
sys.path.insert(0, "{Path(__file__).parent}")
import swarm
workflow_def = swarm.parse_workflow_yaml("{yaml_copy_path}")
workflow_dir = swarm.Path("{workflow_dir}")
swarm.run_workflow_monitor("{workflow_name}", workflow_def, workflow_dir)
'''

    # Write to temp file and run with nohup
    import tempfile
    script_path = Path(tempfile.gettempdir()) / f"swarm_workflow_monitor_{workflow_name}.py"
    with open(script_path, "w") as f:
        f.write(monitor_script)

    # Get workflow logs dir for output
    logs_dir = get_workflow_logs_dir(workflow_name)
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_file = logs_dir / "monitor.log"

    # Start subprocess with nohup-like behavior
    with open(log_file, "a") as log_out:
        process = subprocess.Popen(
            [sys.executable, str(script_path)],
            stdout=log_out,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            start_new_session=True,  # Detach from terminal
            cwd=str(workflow_dir),
        )

    print(f"  Monitor PID: {process.pid}, log: {log_file}")


def cmd_workflow_logs(args) -> None:
    """View logs from workflow stages.

    Shows output from stage workers that have run or are currently running.
    Logs are retrieved from tmux panes (for tmux workers) or log files
    (for non-tmux workers).

    Args:
        args: Namespace with logs arguments:
            - name: Workflow name
            - stage: Optional stage name to filter
            - follow: Whether to continuously poll for new output
            - lines: Number of history lines to show

    Exit codes:
        0: Success
        1: Workflow not found or invalid stage
    """
    workflow_name = args.name
    stage_filter = args.stage
    follow = args.follow
    history_lines = args.lines

    # Validate follow mode requires a specific stage
    if follow and not stage_filter:
        print("Error: --follow requires --stage to be specified", file=sys.stderr)
        sys.exit(1)

    # Load workflow state
    workflow_state = load_workflow_state(workflow_name)
    if workflow_state is None:
        print(f"Error: workflow '{workflow_name}' not found", file=sys.stderr)
        sys.exit(1)

    # Get ordered list of stage names
    stage_names = list(workflow_state.stages.keys())

    # Validate stage filter if provided
    if stage_filter and stage_filter not in stage_names:
        print(f"Error: stage '{stage_filter}' not found in workflow", file=sys.stderr)
        print(f"Available stages: {', '.join(stage_names)}", file=sys.stderr)
        sys.exit(1)

    # Determine which stages to show
    stages_to_show = [stage_filter] if stage_filter else stage_names

    # Load worker state for looking up workers
    state = State()

    if follow:
        # Follow mode: poll a single stage's logs continuously
        stage_name = stages_to_show[0]
        stage_state = workflow_state.stages.get(stage_name)
        worker_name = stage_state.worker_name if stage_state else None

        if not worker_name:
            print(f"Error: stage '{stage_name}' has no worker (stage may be pending)", file=sys.stderr)
            sys.exit(1)

        worker = state.get_worker(worker_name)
        if not worker:
            print(f"Error: worker '{worker_name}' not found", file=sys.stderr)
            sys.exit(1)

        if not worker.tmux:
            # Non-tmux worker: use tail -f
            log_path = LOGS_DIR / f"{worker.name}.stdout.log"
            if not log_path.exists():
                print(f"Error: no log file found for worker '{worker_name}'", file=sys.stderr)
                sys.exit(1)
            os.execvp("tail", ["tail", "-f", str(log_path)])
        else:
            # Tmux worker: poll and redraw
            try:
                socket = worker.tmux.socket if worker.tmux else None
                while True:
                    output = tmux_capture_pane(
                        worker.tmux.session,
                        worker.tmux.window,
                        history_lines=history_lines,
                        socket=socket
                    )

                    # Clear screen and print
                    print("\033[2J\033[H", end="")  # ANSI clear
                    print(f"=== Stage: {stage_name} (worker: {worker_name}) ===")
                    lines = output.strip().split('\n')
                    print('\n'.join(lines[-30:]))

                    time.sleep(1)
            except KeyboardInterrupt:
                # Clean exit on Ctrl-C
                pass
    else:
        # Normal mode: show logs for each stage
        for stage_name in stages_to_show:
            stage_state = workflow_state.stages.get(stage_name)
            worker_name = stage_state.worker_name if stage_state else None

            # Print stage header
            if worker_name:
                print(f"=== Stage: {stage_name} (worker: {worker_name}) ===")
            else:
                print(f"=== Stage: {stage_name} (no worker - stage pending) ===")
                print()
                continue

            # Try to get logs for this worker
            worker = state.get_worker(worker_name)
            if not worker:
                print(f"(worker '{worker_name}' not found in state - may have been cleaned up)")
                print()
                continue

            # Get logs based on worker type
            if worker.tmux:
                socket = worker.tmux.socket if worker.tmux else None
                try:
                    output = tmux_capture_pane(
                        worker.tmux.session,
                        worker.tmux.window,
                        history_lines=history_lines,
                        socket=socket
                    )
                    print(output, end="")
                except Exception as e:
                    print(f"(error capturing tmux pane: {e})")
            else:
                # Non-tmux worker: read from log file
                log_path = LOGS_DIR / f"{worker.name}.stdout.log"
                if log_path.exists():
                    try:
                        content = log_path.read_text()
                        # Apply line limit if needed
                        if history_lines > 0:
                            lines = content.split('\n')
                            content = '\n'.join(lines[-history_lines:])
                        print(content, end="")
                    except Exception as e:
                        print(f"(error reading log file: {e})")
                else:
                    print(f"(no log file found at {log_path})")

            print()  # Blank line between stages


def cmd_workflow_run(args) -> None:
    """Run a workflow from a YAML definition file.

    Parses the workflow YAML, validates it, creates workflow state, and either
    schedules the workflow for later or starts running immediately.

    Args:
        args: Namespace with run arguments:
            - file: Path to workflow YAML file
            - at_time: Optional schedule time (HH:MM format)
            - in_delay: Optional schedule delay (duration string)
            - name: Optional name override
            - force: Whether to overwrite existing workflow

    Exit codes:
        0: Workflow started or scheduled successfully
        1: Error (validation failed, duplicate name, etc.)
    """
    # Resolve the workflow file path (checks repo-local then global)
    try:
        yaml_path = resolve_workflow_file(args.file)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    # Read the raw YAML content (needed for hashing)
    try:
        with open(yaml_path, 'r') as f:
            yaml_content = f.read()
    except IOError as e:
        print(f"Error: cannot read workflow file: {e}", file=sys.stderr)
        sys.exit(1)

    # Parse and validate the YAML structure
    try:
        workflow_def = parse_workflow_yaml(yaml_path)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except WorkflowValidationError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    # Validate that all prompt files exist
    workflow_dir = Path(yaml_path).parent
    prompt_errors = validate_workflow_prompt_files(workflow_def, workflow_dir)
    if prompt_errors:
        print("Validation errors:", file=sys.stderr)
        for error in prompt_errors:
            print(f"  - {error}", file=sys.stderr)
        sys.exit(1)

    # Apply name override if provided
    workflow_name = args.name if args.name else workflow_def.name

    # Check for duplicate workflow name (unless --force)
    if workflow_exists(workflow_name) and not args.force:
        print(f"Error: workflow '{workflow_name}' already exists (use --force to overwrite)", file=sys.stderr)
        sys.exit(1)

    # If --force and workflow exists, delete old state and cleanup workers
    if workflow_exists(workflow_name) and args.force:
        # Load old workflow state to find workers to clean up
        old_workflow_state = load_workflow_state(workflow_name)
        if old_workflow_state:
            state = State()
            for stage_name, stage_state in old_workflow_state.stages.items():
                if stage_state.worker_name:
                    worker = state.get_worker(stage_state.worker_name)
                    if worker:
                        # Remove worker from state (don't kill process, just unregister)
                        state.remove_worker(stage_state.worker_name)
        delete_workflow_state(workflow_name)

    # Validate --at and --in are mutually exclusive
    if args.at_time and args.in_delay:
        print("Error: cannot use both --at and --in (choose one scheduling option)", file=sys.stderr)
        sys.exit(1)

    # Parse scheduling options
    scheduled_for = None
    schedule_source = None  # Track where scheduling came from

    if args.at_time:
        try:
            scheduled_for = parse_schedule_time(args.at_time)
            schedule_source = "at"
        except ValueError as e:
            print(f"Error: invalid time format '{args.at_time}' (use HH:MM)", file=sys.stderr)
            sys.exit(1)

    elif args.in_delay:
        try:
            delay_seconds = parse_duration(args.in_delay)
            scheduled_for = datetime.now(timezone.utc) + timedelta(seconds=delay_seconds)
            schedule_source = "in"
        except ValueError as e:
            print(f"Error: invalid duration '{args.in_delay}'", file=sys.stderr)
            sys.exit(1)

    # Check if workflow YAML has schedule/delay and no CLI override
    elif workflow_def.schedule:
        try:
            scheduled_for = parse_schedule_time(workflow_def.schedule)
            schedule_source = "yaml"
        except ValueError as e:
            print(f"Error: invalid schedule time in workflow: '{workflow_def.schedule}' (use HH:MM)", file=sys.stderr)
            sys.exit(1)

    elif workflow_def.delay:
        try:
            delay_seconds = parse_duration(workflow_def.delay)
            scheduled_for = datetime.now(timezone.utc) + timedelta(seconds=delay_seconds)
            schedule_source = "yaml"
        except ValueError as e:
            print(f"Error: invalid delay in workflow: '{workflow_def.delay}'", file=sys.stderr)
            sys.exit(1)

    # Create workflow definition with potentially overridden name
    if args.name:
        # Create a copy with the new name
        workflow_def = WorkflowDefinition(
            name=workflow_name,
            description=workflow_def.description,
            schedule=workflow_def.schedule,
            delay=workflow_def.delay,
            heartbeat=workflow_def.heartbeat,
            heartbeat_expire=workflow_def.heartbeat_expire,
            heartbeat_message=workflow_def.heartbeat_message,
            worktree=workflow_def.worktree,
            cwd=workflow_def.cwd,
            stages=workflow_def.stages,
        )

    # Create the workflow state
    workflow_state = create_workflow_state(workflow_def, yaml_path, yaml_content)

    # Handle scheduling
    if scheduled_for:
        workflow_state.status = "scheduled"
        workflow_state.scheduled_for = scheduled_for.isoformat()
        save_workflow_state(workflow_state)

        # Format the time nicely for output
        time_str = scheduled_for.strftime("%H:%M")
        if schedule_source == "at":
            # Show if it's tomorrow
            now = datetime.now(timezone.utc)
            if scheduled_for.date() > now.date():
                time_str = f"{time_str} tomorrow"
        elif schedule_source == "in":
            time_str = f"in {args.in_delay}"

        print(f"Workflow '{workflow_name}' scheduled for {time_str}")

        # Start monitor loop (will wait for scheduled time)
        run_workflow_monitor(
            workflow_name=workflow_name,
            workflow_def=workflow_def,
            workflow_dir=workflow_dir,
        )
    else:
        # Start immediately
        workflow_state.status = "running"
        workflow_state.started_at = datetime.now(timezone.utc).isoformat()

        # Set up first stage
        first_stage = workflow_def.stages[0]
        workflow_state.current_stage = first_stage.name
        workflow_state.current_stage_index = 0
        workflow_state.stages[first_stage.name].status = "running"
        workflow_state.stages[first_stage.name].started_at = workflow_state.started_at
        workflow_state.stages[first_stage.name].attempts = 1
        workflow_state.stages[first_stage.name].worker_name = f"{workflow_name}-{first_stage.name}"

        save_workflow_state(workflow_state)

        stage_count = len(workflow_def.stages)
        print(f"Workflow '{workflow_name}' started (stage 1/{stage_count}: {first_stage.name})")

        # Spawn the first stage worker
        try:
            worker = spawn_workflow_stage(
                workflow_name=workflow_name,
                workflow_def=workflow_def,
                stage_def=first_stage,
                workflow_dir=workflow_dir,
            )
            print(f"Spawned worker '{worker.name}' (tmux: {worker.tmux.session}:{worker.tmux.window})")
        except RuntimeError as e:
            # Failed to spawn worker - update workflow state
            workflow_state.status = "failed"
            workflow_state.stages[first_stage.name].status = "failed"
            workflow_state.stages[first_stage.name].exit_reason = "error"
            workflow_state.completed_at = datetime.now(timezone.utc).isoformat()
            save_workflow_state(workflow_state)
            print(f"Error: failed to spawn stage worker: {e}", file=sys.stderr)
            sys.exit(1)

        # Start monitor loop to manage workflow execution
        run_workflow_monitor(
            workflow_name=workflow_name,
            workflow_def=workflow_def,
            workflow_dir=workflow_dir,
        )


if __name__ == "__main__":
    main()
