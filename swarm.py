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

# Stuck patterns: screen content substrings that indicate the worker is stuck
# at an interactive prompt and not making progress. Maps pattern to warning message.
STUCK_PATTERNS = {
    "Select login method": "Worker stuck at login prompt. Check auth credentials.",
    "Choose the text style": "Worker stuck at theme picker. Check settings.local.json.",
    "looks best with your terminal": "Worker stuck at theme picker. Check settings.local.json.",
    "Paste code here": "Worker stuck at OAuth code entry. Use ANTHROPIC_API_KEY instead.",
}

# Fatal patterns: screen content substrings that indicate the worker has hit an
# unrecoverable state and should be immediately killed and restarted.
FATAL_PATTERNS = ["Compacting conversation"]

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

SANDBOX_PROMPT_TEMPLATE = """Read CLAUDE.md, then read IMPLEMENTATION_PLAN.md and pick ONE incomplete task (marked with `[ ]`).

IMPORTANT:
- Do ONE task per iteration — keep changes small and focused
- Do NOT assume anything is already done — verify by reading actual code/files
- Run tests after changes (do NOT run `make test` if CLAUDE.md warns against it)
- Mark the task `[x]` in IMPLEMENTATION_PLAN.md when done
- Commit and push when done
- If ALL tasks are already marked `[x]`, output exactly `/done` on its own line and stop
""".lstrip()

# Sandbox template files for `swarm init --with-sandbox`
# These are generic starting points; users customize per project.

SANDBOX_SH_TEMPLATE = r"""#!/bin/bash
# sandbox.sh — Run Claude Code inside a sandboxed Docker container.
# Usage: ./sandbox.sh [claude args...]
# Example: ./sandbox.sh --dangerously-skip-permissions
#
# Swarm integration:
#   swarm ralph spawn --name dev --prompt-file PROMPT.md --max-iterations 50 \
#       -- ./sandbox.sh --dangerously-skip-permissions
#
# Git auth: Uses GH_TOKEN (GitHub CLI token) over HTTPS. No SSH keys mounted.
#   Requires: gh auth login (once on host), repo cloned via HTTPS or remote
#   set to HTTPS (git remote set-url origin https://github.com/user/repo.git).
#
# Environment overrides:
#   SANDBOX_IMAGE=sandbox-loop    Docker image name
#   SANDBOX_NETWORK=sandbox-net   Docker network name
#   MEMORY_LIMIT=8g               Container memory cap
#   CPU_LIMIT=4                   Container CPU cap
#   PIDS_LIMIT=512                Container PID cap

set -euo pipefail

IMAGE="${SANDBOX_IMAGE:-sandbox-loop}"
NETWORK="${SANDBOX_NETWORK:-sandbox-net}"
MEMORY="${MEMORY_LIMIT:-8g}"
CPUS="${CPU_LIMIT:-4}"
PIDS="${PIDS_LIMIT:-512}"

# Auto-build image if missing
if ! docker image inspect "$IMAGE" &>/dev/null; then
    echo "Image '$IMAGE' not found — building..." >&2
    docker build \
        --build-arg USER_ID="$(id -u)" \
        --build-arg GROUP_ID="$(id -g)" \
        -t "$IMAGE" \
        -f Dockerfile.sandbox . >&2
fi

# Resolve symlinked settings (Claude often symlinks settings.json)
CLAUDE_SETTINGS=$(readlink -f "$HOME/.claude/settings.json" 2>/dev/null || echo "$HOME/.claude/settings.json")

# Git auth via short-lived GitHub token (no SSH keys in the container).
# Falls back to gh auth token, then GITHUB_TOKEN env var, then warns.
GH_TOKEN="${GH_TOKEN:-}"
if [ -z "$GH_TOKEN" ] && command -v gh &>/dev/null; then
    GH_TOKEN=$(gh auth token 2>/dev/null || true)
fi
if [ -z "$GH_TOKEN" ]; then
    echo "warning: no GH_TOKEN found. git push will fail inside the container." >&2
    echo "  fix: run 'gh auth login' or export GH_TOKEN=ghp_..." >&2
fi

# --- Claude auth ---
# Priority: ANTHROPIC_API_KEY (direct API key, no expiry)
#         > CLAUDE_CODE_OAUTH_TOKEN (explicit OAuth token)
#         > auto-extract from ~/.claude/.credentials.json (subscription users)
#
# OAuth tokens expire after ~8h but sandbox.sh re-extracts each iteration.
# For long sessions, ANTHROPIC_API_KEY is more reliable.
if [ -z "${ANTHROPIC_API_KEY:-}" ] && [ -z "${CLAUDE_CODE_OAUTH_TOKEN:-}" ]; then
    CREDS="$HOME/.claude/.credentials.json"
    if [ -f "$CREDS" ]; then
        CLAUDE_CODE_OAUTH_TOKEN=$(python3 -c "
import json, sys
try:
    d = json.load(open(sys.argv[1]))
    print(d.get('claudeAiOauth', {}).get('accessToken', ''))
except Exception:
    pass
" "$CREDS" 2>/dev/null || true)
        export CLAUDE_CODE_OAUTH_TOKEN
    fi
    if [ -z "${CLAUDE_CODE_OAUTH_TOKEN:-}" ]; then
        echo "warning: no Claude auth found. Worker will show login prompt." >&2
        echo "  fix: export ANTHROPIC_API_KEY=sk-ant-... or run 'claude login' on host." >&2
    fi
fi

exec docker run --rm -it \
    --memory="$MEMORY" \
    --memory-swap="$MEMORY" \
    --cpus="$CPUS" \
    --pids-limit="$PIDS" \
    --network="$NETWORK" \
    -v "$(pwd):/workspace" \
    -v "$CLAUDE_SETTINGS:/home/loopuser/.claude/settings.json:ro" \
    -v "$HOME/.claude/projects:/home/loopuser/.claude/projects" \
    -e ANTHROPIC_API_KEY \
    -e CLAUDE_CODE_OAUTH_TOKEN \
    -e DISABLE_AUTOUPDATER=1 \
    -e "GH_TOKEN=$GH_TOKEN" \
    -w /workspace \
    "$IMAGE" \
    claude "$@"
""".lstrip()

DOCKERFILE_SANDBOX_TEMPLATE = """\
FROM node:22-slim

# Base tools required by Claude Code and git operations.
# Add your project's toolchain below (e.g., python3, ruby, golang).
RUN apt-get update && \\
    apt-get install -y --no-install-recommends \\
        git jq curl ca-certificates \\
    && rm -rf /var/lib/apt/lists/*

RUN npm install -g @anthropic-ai/claude-code

# Run as non-root user matching host UID (avoids permission issues on bind mounts)
ARG USER_ID=1000
ARG GROUP_ID=1000
RUN if getent passwd $USER_ID >/dev/null; then userdel -r $(getent passwd $USER_ID | cut -d: -f1); fi && \\
    if getent group $GROUP_ID >/dev/null; then groupdel $(getent group $GROUP_ID | cut -d: -f1) 2>/dev/null || true; fi && \\
    groupadd -g $GROUP_ID loopuser && \\
    useradd -m -u $USER_ID -g $GROUP_ID loopuser

# Skip first-time theme picker in fresh containers
RUN mkdir -p /home/loopuser/.claude && \\
    echo '{"theme":"dark"}' > /home/loopuser/.claude/settings.local.json && \\
    chown -R $USER_ID:$GROUP_ID /home/loopuser/.claude

USER loopuser

# Git auth: use GH_TOKEN env var for HTTPS pushes (no SSH keys needed).
# This credential helper makes git use $GH_TOKEN for any github.com HTTPS request.
RUN git config --global credential.https://github.com.helper \\
    '!f() { echo "protocol=https"; echo "host=github.com"; echo "username=x-access-token"; echo "password=$GH_TOKEN"; }; f'

WORKDIR /workspace
ENTRYPOINT []
CMD ["bash"]
"""

SETUP_SANDBOX_NETWORK_TEMPLATE = r"""#!/bin/bash
# setup-sandbox-network.sh — Create Docker network with iptables allowlist.
# Run with: sudo ./setup-sandbox-network.sh
#
# Allowlist: Claude API, Statsig, Sentry, GitHub, DNS.
# Everything else from the sandbox subnet is REJECTED.
#
# Re-run to refresh IPs (domain IPs rotate). Rules don't survive reboot.

set -euo pipefail

# --- Require root ---
if [ "$(id -u)" -ne 0 ]; then
    echo "error: this script must be run as root (sudo ./setup-sandbox-network.sh)" >&2
    exit 1
fi

# --- Check dependencies ---
for cmd in docker dig curl jq iptables; do
    if ! command -v "$cmd" &>/dev/null; then
        echo "error: '$cmd' is required but not found" >&2
        exit 1
    fi
done

NETWORK_NAME="sandbox-net"
SUBNET="172.30.0.0/24"

# --- Create network (idempotent) ---
if ! docker network inspect "$NETWORK_NAME" &>/dev/null; then
    docker network create --driver bridge --subnet "$SUBNET" "$NETWORK_NAME"
    echo "Created network: $NETWORK_NAME ($SUBNET)"
else
    echo "Network $NETWORK_NAME already exists"
fi

# --- Resolve required domains ---
resolve() {
    local ips
    ips=$(dig +short "$1" | grep -E '^[0-9]' | head -5)
    if [ -z "$ips" ]; then
        echo "warning: could not resolve $1" >&2
    fi
    echo "$ips"
}

ANTHROPIC_IPS=$(resolve api.anthropic.com)
STATSIG_ANTHROPIC_IPS=$(resolve statsig.anthropic.com)
STATSIG_IPS=$(resolve statsig.com)
SENTRY_IPS=$(resolve sentry.io)

# GitHub IP ranges from their meta API (HTTPS only — git uses GH_TOKEN, no SSH)
GITHUB_META=$(curl -sf https://api.github.com/meta) || { echo "warning: could not fetch GitHub meta API" >&2; GITHUB_META="{}"; }
GITHUB_WEB_CIDRS=$(echo "$GITHUB_META" | jq -r '.web[]' 2>/dev/null || true)
GITHUB_API_CIDRS=$(echo "$GITHUB_META" | jq -r '.api[]' 2>/dev/null || true)

# --- Flush existing sandbox rules ---
iptables -S DOCKER-USER 2>/dev/null | grep "172.30.0.0/24" | while read -r rule; do
    iptables $(echo "$rule" | sed 's/^-A/-D/')
done

# --- Default deny for sandbox subnet ---
iptables -A DOCKER-USER -s "$SUBNET" -j REJECT --reject-with icmp-port-unreachable

# --- Allow DNS (udp/53, tcp/53) ---
iptables -I DOCKER-USER -s "$SUBNET" -p udp --dport 53 -j ACCEPT
iptables -I DOCKER-USER -s "$SUBNET" -p tcp --dport 53 -j ACCEPT

# --- Allow established/related connections ---
iptables -I DOCKER-USER -s "$SUBNET" -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT

# --- Allow Anthropic API (HTTPS) ---
for ip in $ANTHROPIC_IPS; do
    iptables -I DOCKER-USER -s "$SUBNET" -d "$ip" -p tcp --dport 443 -j ACCEPT
done

# --- Allow Statsig (telemetry) ---
for ip in $STATSIG_ANTHROPIC_IPS $STATSIG_IPS; do
    iptables -I DOCKER-USER -s "$SUBNET" -d "$ip" -p tcp --dport 443 -j ACCEPT
done

# --- Allow Sentry (error reporting) ---
for ip in $SENTRY_IPS; do
    iptables -I DOCKER-USER -s "$SUBNET" -d "$ip" -p tcp --dport 443 -j ACCEPT
done

# --- Allow GitHub (HTTPS only — git auth via GH_TOKEN, no SSH needed) ---
for cidr in $GITHUB_WEB_CIDRS $GITHUB_API_CIDRS; do
    iptables -I DOCKER-USER -s "$SUBNET" -d "$cidr" -p tcp --dport 443 -j ACCEPT
done

echo ""
echo "Sandbox network rules applied for $SUBNET"
echo "Allowed: api.anthropic.com, statsig, sentry.io, github.com:443, DNS"
echo "Everything else from $SUBNET is REJECTED"
""".lstrip()

TEARDOWN_SANDBOX_NETWORK_TEMPLATE = r"""#!/bin/bash
# teardown-sandbox-network.sh — Remove sandbox iptables rules and Docker network.
# Run with: sudo ./teardown-sandbox-network.sh

set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
    echo "error: this script must be run as root (sudo ./teardown-sandbox-network.sh)" >&2
    exit 1
fi

SUBNET="172.30.0.0/24"
NETWORK_NAME="sandbox-net"

# Remove iptables rules
iptables -S DOCKER-USER 2>/dev/null | grep "172.30.0.0/24" | while read -r rule; do
    iptables $(echo "$rule" | sed 's/^-A/-D/')
done
echo "Removed iptables rules for $SUBNET"

# Remove network
if docker network inspect "$NETWORK_NAME" &>/dev/null; then
    docker network rm "$NETWORK_NAME"
    echo "Removed network: $NETWORK_NAME"
fi
""".lstrip()

ORCHESTRATOR_TEMPLATE = """\
# Director Runbook

The director is you (a human using an interactive Claude session). Workers run autonomously inside Docker containers via `sandbox.sh`.

## Prerequisites

```bash
# 1. Network lockdown (does not survive reboot)
sudo ./setup-sandbox-network.sh

# 2. Build Docker image
docker build --build-arg USER_ID=$(id -u) --build-arg GROUP_ID=$(id -g) \\
    -t sandbox-loop -f Dockerfile.sandbox .

# 3. Git auth (token passed to container, no SSH keys)
gh auth login
```

Verify lockdown:
```bash
docker run --rm --network=sandbox-net sandbox-loop curl -v --max-time 5 https://example.com
# Should fail with "Connection refused"
```

## Quick Status
```bash
swarm ralph status dev
swarm ls --status running
swarm peek dev
git log --oneline -5
grep -cE '^\\s*-\\s*\\[x\\]' IMPLEMENTATION_PLAN.md  # Tasks done
grep -cE '^\\s*-\\s*\\[ \\]' IMPLEMENTATION_PLAN.md   # Tasks remaining
```

## Start Worker
```bash
swarm ralph spawn --name dev --prompt-file PROMPT.md --max-iterations 50 \\
    -- ./sandbox.sh --dangerously-skip-permissions
```

## Monitor
```bash
# Task progress
grep -cE '^\\s*-\\s*\\[x\\]' IMPLEMENTATION_PLAN.md  # Done
grep -cE '^\\s*-\\s*\\[ \\]' IMPLEMENTATION_PLAN.md   # Remaining

# Recent commits
git log --oneline -5

# Worker terminal output (lightweight, non-interactive)
swarm peek dev

# Container resource usage (use exact name from docker ps)
docker ps --filter "ancestor=sandbox-loop" --format '{{.Names}}'
docker stats <exact-container-name> --no-stream

# Ralph iteration progress
swarm ralph status dev
swarm ralph logs dev
```

## Stop / Restart
```bash
swarm kill dev --rm-worktree
swarm ralph spawn --name dev --replace --prompt-file PROMPT.md --max-iterations 50 \\
    -- ./sandbox.sh --dangerously-skip-permissions
```

## OOM Recovery
Exit 137 = container hit memory limit. Loop auto-continues.
```bash
MEMORY_LIMIT=12g swarm ralph spawn --name dev --replace \\
    --prompt-file PROMPT.md --max-iterations 50 \\
    -- ./sandbox.sh --dangerously-skip-permissions
```

## Rate Limit Recovery
```bash
swarm heartbeat start dev --interval 4h --expire 24h
```

## Operational Learnings

### Docker Monitoring
- Use `docker ps --filter "ancestor=sandbox-loop"` to find running containers, then pass the exact name to `docker stats`
- The `--filter` flag on `docker stats` can miss containers — use the exact container name instead
- Typical worker memory: ~300 MiB / 8 GiB (3-4%) — well within the default limit
- No container visible = between iterations (normal, container exited before next spawns)

### Task Granularity
- If tightly-coupled tasks cause workers to deliberate endlessly, **consolidate them** or add guidance to PROMPT.md allowing the worker to combine related tasks
- Example: removing a class (task A) without removing functions that reference it (task B) breaks imports — the worker correctly identifies this but stalls trying to follow the plan exactly

### Done Signal
- PROMPT.md **must** instruct workers to output `/done` when all tasks are complete
- Without this, workers keep verifying completion each iteration but never emit the stop signal, wasting iterations

### Timing Expectations
- Workers spend 5-10 min reading and reasoning before making changes — this is normal
- Complex iterations (removing thousands of lines): 20-30 min including pre-commit hooks
- Simple iterations (doc updates, file deletions): ~10 min
- Budget accordingly and don't intervene too early

## Progress

| Phase | Description | Tasks |
|-------|-------------|-------|
| Phase 1 | TODO | 0 tasks |
"""

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
  Consider using Docker isolation (sandbox.sh) for unattended workers.
  See README.md for sandboxing options.

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

Displays the worker's PROCESS state (running/stopped) along with execution
context: tmux session and window (for tmux workers), process ID (for background
workers), worktree path (if using git isolation), and uptime since spawn.

NOTE: For ralph LOOP status (iteration progress, ETA, failures),
use: swarm ralph status <name>

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

# Peek command help
PEEK_HELP_DESCRIPTION = """\
Capture and display recent terminal output from a worker.

Captures the last N lines of a worker's tmux pane, providing a lightweight,
non-interactive way to check what a worker is doing without attaching to the
tmux session. Only works with tmux-based workers.

Exit Codes:
  0  Success — output captured and printed
  1  Error — worker not running, not tmux, or capture failed
  2  Not found — worker does not exist
"""

PEEK_HELP_EPILOG = """\
Output Format:
  For single worker: raw pane content is printed to stdout.
  For --all: each worker's output is preceded by a header:
    === worker-name ===
    [last N lines of terminal output]

Examples:
  # Peek at a worker's terminal output (last 30 lines)
  swarm peek my-worker

  # Peek with more history
  swarm peek my-worker -n 100

  # Peek all running workers
  swarm peek --all

  # Peek all with custom line count
  swarm peek --all -n 50

See Also:
  swarm attach --help    Attach to worker's tmux window (interactive)
  swarm logs --help      View worker log files
  swarm status --help    Check worker status
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

  # Kill ralph worker with full cleanup (removes worktree AND ralph state)
  swarm kill my-ralph-worker --rm-worktree

Warnings:
  - --force-dirty will DELETE UNCOMMITTED CHANGES permanently
  - Killing a worker does NOT remove it from state (use 'swarm clean')
  - Worktree removal without --force-dirty fails if changes exist
  - Empty tmux sessions are automatically destroyed after kill
  - For ralph workers, --rm-worktree also removes ralph state (~/.swarm/ralph/<name>/)

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
View worker TERMINAL output from tmux panes or log files.

For tmux workers, captures output directly from the tmux pane. By default,
shows only the visible pane content. Use --history to include scrollback
buffer (up to --lines lines). Use --follow for live tailing.

For background (non-tmux) workers, reads from log files stored in
~/.swarm/logs/<name>.stdout.log. Use --follow to tail the log file.

NOTE: For ralph ITERATION history (start/stop timestamps, durations),
use: swarm ralph logs <name>
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
Remove stopped WORKERS from swarm state and clean up associated resources.

Removes worker entries from ~/.swarm/state.json and deletes associated log files
(~/.swarm/logs/<name>.{stdout,stderr}.log). By default, git worktrees are also
removed unless they have uncommitted changes. Only stopped workers can be cleaned;
running workers must be killed first with 'swarm kill'.

NOTE: For ralph STATE cleanup (iterations.log, state.json),
use: swarm ralph clean <name>

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

  # Initialize with sandbox scaffolding for Docker isolation
  swarm init --with-sandbox

  # Preview what would be done without making changes
  swarm init --dry-run
  swarm init --with-sandbox --dry-run

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

  With --with-sandbox, also creates:
  - sandbox.sh              Docker wrapper for Claude (chmod +x)
  - Dockerfile.sandbox      Container image definition
  - setup-sandbox-network.sh    Network lockdown (chmod +x, run with sudo)
  - teardown-sandbox-network.sh Network teardown (chmod +x, run with sudo)
  - ORCHESTRATOR.md         Template for monitoring autonomous loops

Auto-Discovery Order:
  1. If --file specified, use that file
  2. If AGENTS.md exists, append to it
  3. If CLAUDE.md exists, append to it
  4. Otherwise, create AGENTS.md

Idempotent Behavior:
  - If the marker "Process Management (swarm)" already exists in the target
    file, init reports this and exits without changes
  - Use --force to replace the existing section with the latest version
  - Sandbox files are skipped if they already exist (never overwritten)

Common Workflow:
  1. Clone a project:     git clone <repo>
  2. Initialize swarm:    cd <repo> && swarm init --with-sandbox
  3. Build sandbox:       docker build --build-arg USER_ID=$(id -u) \\
                            --build-arg GROUP_ID=$(id -g) \\
                            -t sandbox-loop -f Dockerfile.sandbox .
  4. Network lockdown:    sudo ./setup-sandbox-network.sh
  5. Create prompt:       swarm ralph init
  6. Start loop:          swarm ralph spawn --name dev \\
                            --prompt-file PROMPT.md --max-iterations 50 \\
                            -- ./sandbox.sh --dangerously-skip-permissions

See Also:
  swarm spawn --help      Create new workers
  swarm ralph --help      Autonomous agent looping
  swarm --help            Overview of all commands
  docs/autonomous-loop-guide.md   Full guide for sandbox setup
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
  swarm ralph status <name>           Check iteration progress (with ETA)
  swarm ralph logs <name>             View iteration history
  swarm ralph pause <name>            Pause the loop
  swarm ralph resume <name>           Resume the loop
  swarm ralph list                    List all ralph workers
  swarm send <name> "message"         Intervene mid-iteration

See: https://github.com/ghuntley/how-to-ralph-wiggum
"""

RALPH_SPAWN_HELP_DESCRIPTION = """\
Spawn a new worker with ralph loop mode enabled.

By default, spawns the worker AND starts the monitoring loop as a background
process, then returns immediately. Use --foreground to block while the loop
runs. Use --no-run to spawn without starting the loop. Use --replace to
auto-clean an existing worker before respawning, or --clean-state to
reset iteration count without killing the worker.
"""

RALPH_SPAWN_HELP_EPILOG = """\
Examples:
  # Basic autonomous loop (background, returns immediately)
  swarm ralph spawn --name dev --prompt-file PROMPT.md --max-iterations 50 -- claude --dangerously-skip-permissions

  # Foreground mode (blocks while running)
  swarm ralph spawn --name dev --prompt-file PROMPT.md --max-iterations 50 \\
    --foreground -- claude --dangerously-skip-permissions

  # With isolated git worktree
  swarm ralph spawn --name feature --prompt-file PROMPT.md --max-iterations 20 \\
    --worktree -- claude --dangerously-skip-permissions

  # Replace existing worker (auto-cleans worker, worktree, and ralph state)
  swarm ralph spawn --name dev --replace --prompt-file PROMPT.md --max-iterations 50 \\
    -- claude --dangerously-skip-permissions

  # Reset ralph state only (keep worker/worktree, start fresh iteration count)
  swarm ralph spawn --name dev --clean-state --prompt-file PROMPT.md --max-iterations 50 \\
    --no-run -- claude --dangerously-skip-permissions

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

  # Longer inactivity timeout for repos with slow pre-commit hooks
  swarm ralph spawn --name dev --prompt-file PROMPT.md --max-iterations 50 \\
    --inactivity-timeout 300 -- claude --dangerously-skip-permissions

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
  swarm ralph status dev      # Check iteration progress and ETA
  swarm ralph logs dev        # View iteration history
  swarm attach dev            # Watch agent live (detach: Ctrl-B D)
  swarm logs dev --follow     # Stream agent output

Tips:
  - This command BLOCKS until the loop completes. Use --no-run to spawn only.
  - The prompt file is re-read each iteration, so you can modify it mid-loop.
  - Default inactivity timeout is 180s. Increase for repos with slow CI hooks.
  - Use --replace to cleanly restart a worker without manual cleanup.
  - Use --clean-state to reset iteration count without killing the worker.

Security Note:
  The --dangerously-skip-permissions flag is required for autonomous operation.
  For overnight/unattended work, consider using Docker isolation (sandbox.sh)
  for unattended workers. See README.md for sandboxing options.

See Also:
  swarm ralph status --help    Check iteration progress and ETA
  swarm ralph logs --help      View iteration history
  swarm ralph pause --help     Pause the loop temporarily
  swarm ralph run --help       Start loop separately from spawn
"""

RALPH_INIT_HELP_EPILOG = """\
Creates a starter PROMPT.md in the current directory with best-practice
instructions for autonomous agent looping.

The template is intentionally minimal - customize it for your project:
  - Add project-specific test commands
  - Specify which files to study
  - Include deployment instructions if needed

Examples:
  # Create default PROMPT.md and customize
  swarm ralph init
  vim PROMPT.md

  # Overwrite existing PROMPT.md with fresh template
  swarm ralph init --force

  # Full workflow: init, customize, start loop
  swarm ralph init
  vim PROMPT.md  # customize for your project
  swarm ralph spawn --name dev --prompt-file PROMPT.md --max-iterations 50 -- claude

See Also:
  swarm ralph template --help  Output template to stdout (for piping)
  swarm ralph spawn --help     Start the autonomous loop
"""

RALPH_TEMPLATE_HELP_EPILOG = """\
Prints the prompt template to stdout for piping or inspection.

Examples:
  swarm ralph template                     # View template
  swarm ralph template > MY_PROMPT.md      # Save to custom file
  swarm ralph template | pbcopy            # Copy to clipboard (macOS)

See Also:
  swarm ralph init --help      Create PROMPT.md in current directory
"""

RALPH_STATUS_HELP_EPILOG = """\
Shows detailed ralph LOOP status including iteration progress, failures,
timing information, and estimated time remaining.

NOTE: For worker PROCESS status (running/stopped),
use: swarm status <name>

Output includes:
  - Current status (running/paused/stopped/failed)
  - Iteration progress with ETA (e.g., "7/100 (avg 4m/iter, ~6h12m remaining)")
  - Exit reason for completed loops (done_pattern, max_iterations, killed, failed)
  - Start times, failure counts, and inactivity timeout settings
  - Monitor disconnect detection (shows if monitor stopped but worker is alive)

Examples:
  swarm ralph status dev              # Show full ralph status
  swarm ralph status feature-auth     # Check specific worker

See Also:
  swarm ralph logs --help      View iteration history
  swarm ralph pause --help     Pause the loop
  swarm status --help          Show general worker status
"""

RALPH_PAUSE_HELP_EPILOG = """\
Pauses the ralph loop. The current agent continues running, but when it
exits, the loop will not restart a new iteration.

Use 'swarm ralph resume <name>' to continue the loop.

Examples:
  swarm ralph pause dev               # Pause the dev worker's loop
  swarm ralph pause feature-auth      # Pause while you review changes

See Also:
  swarm ralph resume --help    Resume a paused loop
  swarm ralph status --help    Check current loop state
"""

RALPH_RESUME_HELP_EPILOG = """\
Resumes a paused ralph loop. Continues from the current iteration count
(does not reset progress).

If the worker is not currently running, spawns a fresh agent for the
next iteration. Also useful when the monitor disconnected but the worker
is still alive.

Examples:
  swarm ralph resume dev              # Resume paused loop
  swarm ralph resume feature-auth     # Resume after reviewing changes

See Also:
  swarm ralph pause --help     Pause the loop
  swarm ralph status --help    Check if loop is paused or disconnected
"""

RALPH_RUN_HELP_EPILOG = """\
Runs the monitoring loop for an existing ralph worker. This command blocks
while the loop is running.

Typically used after 'ralph spawn --no-run' when you want to spawn and
run the loop separately. By default, 'ralph spawn' runs the loop
automatically.

Examples:
  # Spawn then run separately
  swarm ralph spawn --name dev --prompt-file PROMPT.md --max-iterations 50 \\
    --no-run -- claude --dangerously-skip-permissions
  swarm ralph run dev

  # Run in background
  swarm ralph run dev &

See Also:
  swarm ralph spawn --help     Spawn with automatic loop start
  swarm ralph status --help    Check loop progress
"""

RALPH_LIST_HELP_EPILOG = """\
Lists all workers that are running in ralph mode.

Examples:
  swarm ralph list                      # Table view
  swarm ralph list --format json        # JSON for scripting
  swarm ralph list --status running     # Only running loops

See Also:
  swarm ls --help              List all workers (not just ralph)
  swarm ralph status --help    Detailed status for a specific worker
"""

RALPH_CLEAN_HELP_EPILOG = """\
Remove ralph state for one or all workers. Does NOT kill worker processes
or remove worktrees — use 'swarm kill --rm-worktree' for full cleanup.

Examples:
  swarm ralph clean agent              # Remove state for 'agent'
  swarm ralph clean --all              # Remove all ralph state

See Also:
  swarm kill --help              Kill workers and optionally remove worktrees
  swarm ralph status --help      Check ralph status before cleaning
"""

RALPH_LOGS_HELP_EPILOG = """\
Shows the iteration history log for a ralph worker. This is separate from
'swarm logs' which shows the worker's tmux output.

The log shows timestamped events for each iteration: start, end, failures,
timeouts, and loop completion.

Examples:
  swarm ralph logs agent                # Show all entries
  swarm ralph logs agent --lines 10     # Show last 10 entries
  swarm ralph logs agent --live         # Tail log in real-time

Log Format:
  2024-01-15T10:30:00 [START] iteration 1/100
  2024-01-15T10:35:42 [END] iteration 1 exit=0 duration=5m42s
  2024-01-15T12:00:00 [DONE] loop complete after 10 iterations reason=done_pattern

See Also:
  swarm logs --help            View worker tmux output (different from ralph logs)
  swarm ralph status --help    Check iteration progress and ETA
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
    last_iteration_ended: str = ""
    iteration_durations: list = field(default_factory=list)  # Duration of each iteration in seconds
    consecutive_failures: int = 0
    total_failures: int = 0
    done_pattern: Optional[str] = None
    inactivity_timeout: int = 180
    check_done_continuous: bool = False
    exit_reason: Optional[str] = None  # done_pattern, max_iterations, killed, failed, monitor_disconnected
    prompt_baseline_content: str = ""  # Pane content snapshot after prompt injection, for done-pattern baseline filtering
    last_screen_change: Optional[str] = None  # ISO format timestamp of last screen content change
    monitor_pid: Optional[int] = None  # PID of background monitoring loop process
    max_context: Optional[int] = None  # Context percentage threshold for nudge/kill
    context_nudge_sent: bool = False  # Whether context nudge has been sent this iteration

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
            "last_iteration_ended": self.last_iteration_ended,
            "iteration_durations": self.iteration_durations,
            "consecutive_failures": self.consecutive_failures,
            "total_failures": self.total_failures,
            "done_pattern": self.done_pattern,
            "inactivity_timeout": self.inactivity_timeout,
            "check_done_continuous": self.check_done_continuous,
            "exit_reason": self.exit_reason,
            "prompt_baseline_content": self.prompt_baseline_content,
            "last_screen_change": self.last_screen_change,
            "monitor_pid": self.monitor_pid,
            "max_context": self.max_context,
            "context_nudge_sent": self.context_nudge_sent,
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
            last_iteration_ended=d.get("last_iteration_ended", ""),
            iteration_durations=d.get("iteration_durations", []),
            consecutive_failures=d.get("consecutive_failures", 0),
            total_failures=d.get("total_failures", 0),
            done_pattern=d.get("done_pattern"),
            inactivity_timeout=d.get("inactivity_timeout", 180),
            check_done_continuous=d.get("check_done_continuous", False),
            exit_reason=d.get("exit_reason"),
            prompt_baseline_content=d.get("prompt_baseline_content", ""),
            last_screen_change=d.get("last_screen_change"),
            monitor_pid=d.get("monitor_pid"),
            max_context=d.get("max_context"),
            context_nudge_sent=d.get("context_nudge_sent", False),
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

        tmp_path = state_path.with_suffix('.json.tmp')
        with open(tmp_path, "w") as f:
            json.dump(heartbeat_state.to_dict(), f, indent=2)
        os.replace(tmp_path, state_path)


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
            # Check if previous message is still pending in pane
            try:
                pane_content = tmux_capture_pane(
                    worker.tmux.session,
                    worker.tmux.window,
                    socket=worker.tmux.socket
                )
                lines = [l for l in pane_content.rstrip().split('\n') if l.strip()]
                last_line = lines[-1] if lines else ""
                if heartbeat_state.message in last_line:
                    # Previous beat unconsumed, skip this one
                    last_beat_monotonic = time.monotonic()
                    continue
            except Exception:
                pass  # If capture fails, proceed with send

            # Time to send a beat
            try:
                tmux_send(
                    worker.tmux.session,
                    worker.tmux.window,
                    heartbeat_state.message,
                    enter=True,
                    socket=worker.tmux.socket,
                    pre_clear=False
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
        RalphState if it exists, None otherwise.
        If the state file is corrupt JSON, backs up to state.json.corrupted
        and returns a fresh default RalphState.
    """
    state_path = get_ralph_state_path(worker_name)
    if not state_path.exists():
        return None

    try:
        with open(state_path, "r") as f:
            data = json.load(f)
            return RalphState.from_dict(data)
    except json.JSONDecodeError:
        print(f"swarm: warning: corrupt ralph state for '{worker_name}', resetting",
              file=sys.stderr)
        # Back up corrupted file
        corrupted_path = state_path.parent / "state.json.corrupted"
        try:
            import shutil
            shutil.copy2(state_path, corrupted_path)
        except OSError:
            pass  # Best-effort backup
        # Return fresh default state
        return RalphState(
            worker_name=worker_name,
            prompt_file="PROMPT.md",
            max_iterations=0,
        )


def save_ralph_state(ralph_state: RalphState) -> None:
    """Save ralph state for a worker.

    Args:
        ralph_state: RalphState to save
    """
    state_path = get_ralph_state_path(ralph_state.worker_name)
    state_path.parent.mkdir(parents=True, exist_ok=True)

    tmp_path = state_path.with_suffix('.json.tmp')
    with open(tmp_path, "w") as f:
        json.dump(ralph_state.to_dict(), f, indent=2)
    os.replace(tmp_path, state_path)


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
                    try:
                        data = json.load(f)
                    except json.JSONDecodeError:
                        print("swarm: warning: corrupt state file, resetting",
                              file=sys.stderr)
                        # Back up corrupted file
                        corrupted_path = STATE_FILE.parent / "state.json.corrupted"
                        try:
                            import shutil
                            shutil.copy2(STATE_FILE, corrupted_path)
                        except OSError:
                            pass  # Best-effort backup
                        self.workers = []
                        return
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
            tmp_path = STATE_FILE.with_suffix('.json.tmp')
            with open(tmp_path, "w") as f:
                json.dump(data, f, indent=2)
            os.replace(tmp_path, STATE_FILE)

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
        tmp_path = STATE_FILE.with_suffix('.json.tmp')
        with open(tmp_path, "w") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp_path, STATE_FILE)


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


def create_tmux_window(session: str, window: str, cwd: Path, cmd: list[str], socket: Optional[str] = None, env: Optional[dict[str, str]] = None) -> None:
    """Create a tmux window and run command."""
    ensure_tmux_session(session, socket)

    # Build the command string safely
    cmd_str = " ".join(shlex.quote(c) for c in cmd)

    # Wrap command with env prefix if environment variables are provided
    if env:
        env_prefix = " ".join(
            f"{shlex.quote(k)}={shlex.quote(v)}" for k, v in env.items()
        )
        cmd_str = f"env {env_prefix} {cmd_str}"

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


def tmux_send(session: str, window: str, text: str, enter: bool = True, socket: Optional[str] = None, pre_clear: bool = True) -> None:
    """Send text to a tmux window.

    Args:
        session: Tmux session name
        window: Tmux window name
        text: Text to send
        enter: Whether to send Enter after text
        socket: Optional tmux socket name
        pre_clear: If True, send Escape + Ctrl-U before text to clear any
                   partial input on the command line. Default True for
                   user-facing sends; internal callers should pass False.
    """
    target = f"{session}:{window}"
    cmd_prefix = tmux_cmd_prefix(socket)

    # Pre-clear: send Escape (exit any mode) + Ctrl-U (clear line) before text
    if pre_clear:
        subprocess.run(
            cmd_prefix + ["send-keys", "-t", target, "Escape"],
            capture_output=True, check=True,
        )
        subprocess.run(
            cmd_prefix + ["send-keys", "-t", target, "C-u"],
            capture_output=True, check=True,
        )

    # Use send-keys with literal text
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

    # Patterns that indicate the agent is NOT ready and is blocked on an
    # interactive prompt (e.g., theme picker in fresh Docker containers).
    # When detected, send Enter to dismiss and continue waiting.
    not_ready_patterns = [
        r"Choose the text style",           # First-time theme picker
        r"looks best with your terminal",   # Theme picker subtitle
        r"Select login method",             # Login/OAuth prompt
        r"Paste code here",                 # OAuth code entry prompt
    ]

    start = time.time()
    while (time.time() - start) < timeout:
        try:
            output = tmux_capture_pane(session, window, socket=socket)
            lines = output.split('\n')

            # Check for not-ready patterns first (e.g., theme picker)
            not_ready = False
            for line in lines:
                for pattern in not_ready_patterns:
                    if re.search(pattern, line):
                        not_ready = True
                        break
                if not_ready:
                    break

            if not_ready:
                # Dismiss the blocking prompt by sending Enter, then continue polling
                try:
                    cmd_prefix = tmux_cmd_prefix(socket)
                    target = f"{session}:{window}"
                    subprocess.run(
                        cmd_prefix + ["send-keys", "-t", target, "Enter"],
                        capture_output=True,
                        check=True,
                    )
                except subprocess.CalledProcessError:
                    pass
                time.sleep(0.5)
                continue

            # Check each line for ready patterns
            for line in lines:
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

    # peek
    peek_p = subparsers.add_parser(
        "peek",
        help="Peek at worker terminal output",
        description=PEEK_HELP_DESCRIPTION,
        epilog=PEEK_HELP_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    peek_p.add_argument("name", nargs="?",
                        help="Worker name. Required unless using --all. Must be a "
                             "tmux-based worker (spawned with --tmux).")
    peek_p.add_argument("-n", "--lines", type=int, default=30,
                        help="Number of lines to capture (default: 30). Captures "
                             "from scrollback history.")
    peek_p.add_argument("--all", action="store_true",
                        help="Peek all running tmux workers. Non-tmux and "
                             "non-running workers are silently skipped.")

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
    send_p.add_argument("--raw", action="store_true",
                       help="Skip the pre-clear sequence (Escape + Ctrl-U) that is "
                            "normally sent before the text. Use this when sending to "
                            "programs that should not receive escape sequences.")

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
                            "For ralph workers, also removes ralph state (~/.swarm/ralph/<name>/). "
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
    init_p.add_argument("--with-sandbox", action="store_true",
                        help="Scaffold sandbox files for Docker-isolated autonomous loops. "
                             "Creates: sandbox.sh, Dockerfile.sandbox, setup-sandbox-network.sh, "
                             "teardown-sandbox-network.sh, ORCHESTRATOR.md. "
                             "See: docs/autonomous-loop-guide.md")

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
                              help="Overwrite existing PROMPT.md. Default: error if file exists.")

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
    ralph_status_p.add_argument("name", help="Name of the ralph worker to check")

    # ralph pause - pause the ralph loop
    ralph_pause_p = ralph_subparsers.add_parser(
        "pause",
        help="Pause ralph loop for a worker",
        epilog=RALPH_PAUSE_HELP_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ralph_pause_p.add_argument("name", help="Name of the ralph worker to pause")

    # ralph resume - resume the ralph loop
    ralph_resume_p = ralph_subparsers.add_parser(
        "resume",
        help="Resume ralph loop for a worker",
        epilog=RALPH_RESUME_HELP_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ralph_resume_p.add_argument("name", help="Name of the ralph worker to resume")

    # ralph run - run the ralph loop (main outer loop execution)
    ralph_run_p = ralph_subparsers.add_parser(
        "run",
        help="Run the ralph loop for a worker",
        epilog=RALPH_RUN_HELP_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ralph_run_p.add_argument("name", help="Name of the ralph worker to run the loop for")

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

    # ralph ls - alias for ralph list
    ralph_ls_p = ralph_subparsers.add_parser(
        "ls",
        help="List all ralph workers (alias for 'list')",
        epilog=RALPH_LIST_HELP_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ralph_ls_p.add_argument("--format", choices=["table", "json", "names"],
                            default="table", help="Output format (default: table)")
    ralph_ls_p.add_argument("--status", choices=["all", "running", "paused", "stopped", "failed"],
                            default="all", help="Filter by ralph status (default: all)")

    # ralph clean - remove ralph state
    ralph_clean_p = ralph_subparsers.add_parser(
        "clean",
        help="Remove ralph state for one or all workers",
        epilog=RALPH_CLEAN_HELP_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ralph_clean_p.add_argument("name", nargs="?", default=None,
                                help="Name of the ralph worker to clean state for")
    ralph_clean_p.add_argument("--all", action="store_true", dest="all",
                                help="Clean ralph state for all workers")

    # ralph logs - view iteration history
    ralph_logs_p = ralph_subparsers.add_parser(
        "logs",
        help="Show iteration history log for a ralph worker",
        epilog=RALPH_LOGS_HELP_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ralph_logs_p.add_argument("name", help="Name of the ralph worker to view logs for")
    ralph_logs_p.add_argument("--live", action="store_true",
                              help="Tail the log file in real-time (like tail -f). Press Ctrl-C to stop.")
    ralph_logs_p.add_argument("--lines", type=int, default=None,
                              help="Show last N entries. Default: show all entries.")

    # ralph spawn - spawn a new ralph worker
    ralph_spawn_p = ralph_subparsers.add_parser(
        "spawn",
        help="Spawn a new ralph worker",
        description=RALPH_SPAWN_HELP_DESCRIPTION,
        epilog=RALPH_SPAWN_HELP_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ralph_spawn_p.add_argument("--name", required=True,
                               help="Unique identifier for this worker. Used in status, logs, and kill commands.")
    ralph_spawn_p.add_argument("--prompt-file", required=True,
                               help="Path to prompt file read at the start of each iteration. "
                                    "Can be modified mid-loop to change agent behavior.")
    ralph_spawn_p.add_argument("--max-iterations", type=int, default=50,
                               help="Maximum number of loop iterations before stopping. Default: 50.")
    ralph_spawn_p.add_argument("--inactivity-timeout", type=int, default=180,
                               help="Screen stability timeout in seconds. Default: 180. "
                                    "Agent is restarted when tmux screen is unchanged for this duration. "
                                    "Increase for repos with slow CI/pre-commit hooks (e.g., 300).")
    ralph_spawn_p.add_argument("--max-context", type=int, default=None,
                               help="Context percentage threshold for nudge/kill. "
                                    "When the agent's context usage reaches this %%, send a nudge. "
                                    "At threshold+15%%, force-kill the worker. Default: none (disabled).")
    ralph_spawn_p.add_argument("--done-pattern", type=str, default=None,
                               help="Regex pattern to stop the loop when matched in output. "
                                    "Default: none. Example: '/done' or 'All tasks complete'.")
    ralph_spawn_p.add_argument("--check-done-continuous", action=argparse.BooleanOptionalAction, default=None,
                               help="Check done pattern continuously during monitoring, not just after agent exit. "
                                    "Auto-enabled when --done-pattern is set. Use --no-check-done-continuous to disable.")
    ralph_spawn_p.add_argument("--no-run", action="store_true",
                               help="Spawn worker only, don't start monitoring loop. "
                                    "Use 'swarm ralph run <name>' to start the loop later.")
    ralph_spawn_p.add_argument("--foreground", action="store_true",
                               help="Run monitoring loop in the foreground (blocking). "
                                    "Default: start monitoring loop as a background process and return immediately.")
    ralph_spawn_p.add_argument("--replace", action="store_true",
                               help="Auto-clean existing worker, worktree, and ralph state before spawning. "
                                    "Saves the manual kill/clean/rm dance when respawning.")
    ralph_spawn_p.add_argument("--clean-state", action="store_true",
                               help="Clear ralph state (iteration count, status) without killing worker or worktree. "
                                    "Useful when respawning with different config.")
    ralph_spawn_p.add_argument("--session", default=None,
                               help="Tmux session name. Default: hash-based for isolation.")
    ralph_spawn_p.add_argument("--tmux-socket", default=None,
                               help="Tmux socket name for isolation. Used in testing.")
    ralph_spawn_p.add_argument("--worktree", action=argparse.BooleanOptionalAction, default=True,
                               help="Create isolated git worktree for this worker. "
                                    "Default: True. Use --no-worktree to skip. "
                                    "Worktree created at <repo>-worktrees/<name>/.")
    ralph_spawn_p.add_argument("--branch",
                               help="Branch name for worktree. Default: same as --name.")
    ralph_spawn_p.add_argument("--worktree-dir", default=None,
                               help="Parent directory for worktrees. Default: <repo>-worktrees/.")
    ralph_spawn_p.add_argument("--tag", action="append", default=[], dest="tags",
                               help="Tag for filtering workers. Repeatable: --tag a --tag b.")
    ralph_spawn_p.add_argument("--env", action="append", default=[],
                               help="Environment variable in KEY=VAL format. Repeatable.")
    ralph_spawn_p.add_argument("--cwd",
                               help="Working directory for the worker command. Default: current directory.")
    ralph_spawn_p.add_argument("--ready-wait", action="store_true",
                               help="Wait for agent ready pattern before returning. Default: false.")
    ralph_spawn_p.add_argument("--ready-timeout", type=int, default=120,
                               help="Timeout in seconds for --ready-wait. Default: 120.")
    ralph_spawn_p.add_argument("--heartbeat",
                               help='Start heartbeat after spawn. Interval format: "4h", "30m", "90s". '
                                    'Sends periodic nudges to help recover from rate limits.')
    ralph_spawn_p.add_argument("--heartbeat-expire",
                               help='Stop heartbeat after this duration (e.g., "24h"). Default: no expiration.')
    ralph_spawn_p.add_argument("--heartbeat-message", default="continue",
                               help='Message to send on each heartbeat beat. Default: "continue".')
    ralph_spawn_p.add_argument("--tmux", action="store_true",
                               help="Accepted for consistency with 'swarm spawn'. "
                                    "Ralph workers always use tmux; this flag has no effect.")
    ralph_spawn_p.add_argument("cmd", nargs=argparse.REMAINDER, metavar="-- command...",
                               help="Command to run in the worker (after --). Required.")

    # ralph stop - alias for kill
    ralph_stop_p = ralph_subparsers.add_parser(
        "stop",
        help="Stop a ralph worker (alias for 'swarm kill')",
        description="Stop a ralph worker. This is a convenience alias for 'swarm kill'.",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ralph_stop_p.add_argument("name", help="Worker name to stop.")
    ralph_stop_p.add_argument("--rm-worktree", action="store_true",
                              help="Remove the git worktree after stopping. "
                                   "Also removes ralph state (~/.swarm/ralph/<name>/).")
    ralph_stop_p.add_argument("--force-dirty", action="store_true",
                              help="Force removal of worktree even with uncommitted changes.")

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

    # heartbeat ls - alias for list
    heartbeat_ls_p = heartbeat_subparsers.add_parser(
        "ls",
        help="List all heartbeats (alias for 'list')",
        description=HEARTBEAT_LIST_HELP_DESCRIPTION,
        epilog=HEARTBEAT_LIST_HELP_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    heartbeat_ls_p.add_argument("--format", choices=["table", "json"],
                                default="table", help="Output format (default: table)")

    args = parser.parse_args()

    # Resume active heartbeats on startup
    # This restarts monitor processes for heartbeats that were active
    # when swarm last ran (e.g., after system reboot)
    resume_active_heartbeats()


    # Dispatch to command handlers
    if args.command == "spawn":
        cmd_spawn(args)
    elif args.command == "ls":
        cmd_ls(args)
    elif args.command == "status":
        cmd_status(args)
    elif args.command == "peek":
        cmd_peek(args)
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


def _rollback_spawn(
    worktree_path: Optional[Path],
    tmux_info: Optional[TmuxInfo],
    pid: Optional[int],
    worker_name: Optional[str],
    state: Optional["State"],
) -> None:
    """Rollback resources created during spawn on failure.

    Cleans up resources in reverse order of creation to ensure no orphaned state.
    Rollback failures are logged as warnings but don't override the original error.

    Args:
        worktree_path: Path to worktree if created, None otherwise
        tmux_info: TmuxInfo if tmux window created, None otherwise
        pid: Process ID if background process spawned, None otherwise
        worker_name: Worker name if added to state, None otherwise
        state: State instance for removing worker, None if not added
    """
    # Remove worker from state (last created)
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

    # Kill background process
    if pid:
        try:
            os.kill(pid, signal.SIGTERM)
        except Exception as e:
            print(f"swarm: warning: rollback failed: could not kill process {pid}: {e}", file=sys.stderr)

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


# Command stubs - to be implemented in subsequent tasks
def cmd_spawn(args) -> None:
    """Spawn a new worker.

    Uses transactional semantics: if any step fails after resources are created,
    all previously created resources are cleaned up via _rollback_spawn().
    """
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

    # Parse environment variables from KEY=VAL format
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
    pid: Optional[int] = None
    worker_added = False

    # Determine working directory
    cwd = Path.cwd()

    try:
        # Step 1: Create worktree (if requested)
        if args.worktree:
            # Fix core.bare misconfiguration before checking git root
            _check_and_fix_core_bare()

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

        # Step 2: Spawn the worker (tmux or process)
        if args.tmux:
            # Spawn in tmux
            session = args.session if args.session else get_default_session_name()
            socket = args.tmux_socket
            create_tmux_window(session, args.name, cwd, cmd, socket, env=env_dict)
            tmux_info = TmuxInfo(session=session, window=args.name, socket=socket)
        else:
            # Spawn as background process
            log_prefix = LOGS_DIR / args.name
            pid = spawn_process(cmd, cwd, env_dict, log_prefix)

        # Step 3: Create Worker object and add to state
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

        state.add_worker(worker)
        worker_added = True

    except subprocess.CalledProcessError as e:
        # Handle worktree or tmux creation failures
        print("swarm: warning: spawn failed, cleaning up partial state", file=sys.stderr)
        _rollback_spawn(
            worktree_path if worktree_info else None,
            tmux_info,
            pid,
            args.name if worker_added else None,
            state if worker_added else None,
        )
        if "worktree" in str(e).lower() or (worktree_path and not worktree_info):
            print(f"swarm: error: failed to create worktree: {e}", file=sys.stderr)
        elif args.tmux:
            print(f"swarm: error: failed to create tmux window: {e}", file=sys.stderr)
        else:
            print(f"swarm: error: failed to spawn process: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        # Handle any other unexpected errors
        print("swarm: warning: spawn failed, cleaning up partial state", file=sys.stderr)
        _rollback_spawn(
            worktree_path if worktree_info else None,
            tmux_info,
            pid,
            args.name if worker_added else None,
            state if worker_added else None,
        )
        print(f"swarm: error: spawn failed: {e}", file=sys.stderr)
        sys.exit(1)

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


def cmd_peek(args) -> None:
    """Peek at worker terminal output."""
    # Load state
    state = State()

    # Handle --all: peek all running tmux workers
    if args.all:
        workers = [w for w in state.workers if w.tmux is not None]
        for worker in workers:
            # Check if tmux window is still alive
            if not tmux_window_exists(worker.tmux.session, worker.tmux.window,
                                       socket=worker.tmux.socket):
                continue
            # Capture pane content
            try:
                content = tmux_capture_pane(
                    worker.tmux.session, worker.tmux.window,
                    history_lines=args.lines, socket=worker.tmux.socket
                )
            except Exception:
                continue
            print(f"=== {worker.name} ===")
            print(content)
        sys.exit(0)

    # Single worker path
    if not args.name:
        print("swarm: error: worker name required (or use --all)", file=sys.stderr)
        sys.exit(1)

    worker = state.get_worker(args.name)
    if not worker:
        print(f"swarm: error: worker '{args.name}' not found", file=sys.stderr)
        sys.exit(2)

    if not worker.tmux:
        print(f"swarm: error: worker '{args.name}' is not a tmux worker", file=sys.stderr)
        sys.exit(1)

    if not tmux_window_exists(worker.tmux.session, worker.tmux.window,
                               socket=worker.tmux.socket):
        print(f"swarm: error: worker '{args.name}' is not running", file=sys.stderr)
        sys.exit(1)

    try:
        content = tmux_capture_pane(
            worker.tmux.session, worker.tmux.window,
            history_lines=args.lines, socket=worker.tmux.socket
        )
    except Exception as e:
        print(f"swarm: error: failed to capture pane for '{args.name}': {e}", file=sys.stderr)
        sys.exit(1)

    print(content, end="")
    sys.exit(0)


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
        tmux_send(worker.tmux.session, worker.tmux.window, args.text, enter=not args.no_enter, socket=socket, pre_clear=not args.raw)

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
                ralph_state.exit_reason = "killed"
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
    original_metadata = worker.metadata

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
            create_tmux_window(original_tmux.session, args.name, cwd, original_cmd, socket, env=original_env)
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
        metadata=original_metadata,
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
    skip_instructions = False
    if not args.force:
        # Check target file
        if file_exists:
            existing_content = target_file.read_text()
            if marker in existing_content:
                print(f"swarm: {target_file} already contains swarm instructions")
                skip_instructions = True

        # For auto-discovery, also check CLAUDE.md even if AGENTS.md was selected
        if not skip_instructions and not args.file:
            for check_path in [Path("AGENTS.md"), Path("CLAUDE.md")]:
                if check_path.exists() and check_path != target_file:
                    check_content = check_path.read_text()
                    if marker in check_content:
                        print(f"swarm: {check_path} already contains swarm instructions")
                        skip_instructions = True
                        break

    # Handle --dry-run
    if args.dry_run:
        if not skip_instructions:
            if file_exists:
                print(f"Would append swarm instructions to {target_file}")
            else:
                print(f"Would create {target_file} with swarm agent instructions")
        if getattr(args, 'with_sandbox', False):
            _init_sandbox_files(dry_run=True)
        return

    # Prepare content with SWARM_INSTRUCTIONS
    if not skip_instructions:
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

    # Handle --with-sandbox: scaffold sandbox files
    if getattr(args, 'with_sandbox', False):
        _init_sandbox_files(args.dry_run)


def _init_sandbox_files(dry_run: bool) -> None:
    """Scaffold sandbox files for Docker-isolated autonomous loops.

    Creates sandbox.sh, Dockerfile.sandbox, setup-sandbox-network.sh,
    teardown-sandbox-network.sh, ORCHESTRATOR.md, and PROMPT.md if they don't exist.

    Args:
        dry_run: If True, only print what would be done.
    """
    sandbox_files = [
        ("sandbox.sh", SANDBOX_SH_TEMPLATE, True),
        ("Dockerfile.sandbox", DOCKERFILE_SANDBOX_TEMPLATE, False),
        ("setup-sandbox-network.sh", SETUP_SANDBOX_NETWORK_TEMPLATE, True),
        ("teardown-sandbox-network.sh", TEARDOWN_SANDBOX_NETWORK_TEMPLATE, True),
        ("ORCHESTRATOR.md", ORCHESTRATOR_TEMPLATE, False),
        ("PROMPT.md", SANDBOX_PROMPT_TEMPLATE, False),
    ]

    for filename, template, make_executable in sandbox_files:
        path = Path(filename)
        if path.exists():
            print(f"swarm: {filename} already exists, skipping")
            continue

        if dry_run:
            print(f"Would create {filename}")
            continue

        path.write_text(template)
        if make_executable:
            path.chmod(path.stat().st_mode | 0o755)
        print(f"Created {filename}")


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
    - ls: Alias for list
    - clean: Clean ralph state for a worker
    - logs: Show iteration history log for a worker
    - stop: Stop a ralph worker (alias for kill)
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
    elif args.ralph_command == "ls":
        cmd_ralph_list(args)
    elif args.ralph_command == "clean":
        cmd_ralph_clean(args)
    elif args.ralph_command == "logs":
        cmd_ralph_logs(args)
    elif args.ralph_command == "stop":
        cmd_ralph_stop(args)


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

    # Auto-enable --check-done-continuous when --done-pattern is set (unless explicitly disabled)
    check_done = getattr(args, 'check_done_continuous', None)
    if args.done_pattern and check_done is None:
        args.check_done_continuous = True
    elif check_done is None:
        args.check_done_continuous = False

    # Warn for high iteration count
    if args.max_iterations > 50:
        print("swarm: warning: high iteration count (>50) may consume significant resources", file=sys.stderr)

    # Note about --tmux flag (it's a no-op for ralph, but accepted for consistency)
    if getattr(args, 'tmux', False):
        print("swarm: note: Ralph workers always use tmux (--tmux flag has no effect)", file=sys.stderr)

    # Load state and check for duplicate name
    state = State()
    existing_worker = state.get_worker(args.name)

    # Handle --replace flag: clean up existing worker before spawning
    if existing_worker is not None:
        if getattr(args, 'replace', False):
            # Kill the existing worker
            if existing_worker.tmux:
                socket = existing_worker.tmux.socket if existing_worker.tmux else None
                session = existing_worker.tmux.session
                cmd_prefix = tmux_cmd_prefix(socket)
                subprocess.run(
                    cmd_prefix + ["kill-window", "-t", f"{session}:{existing_worker.tmux.window}"],
                    capture_output=True
                )

            # Remove worktree if present
            if existing_worker.worktree:
                success, msg = remove_worktree(Path(existing_worker.worktree.path), force=True)
                if not success:
                    print(f"swarm: warning: cannot remove worktree for '{args.name}': {msg}", file=sys.stderr)

            # Stop ralph monitoring loop if running
            try:
                existing_ralph_state = load_ralph_state(args.name)
                if existing_ralph_state and existing_ralph_state.monitor_pid:
                    try:
                        os.kill(existing_ralph_state.monitor_pid, 0)  # Check if alive
                        os.kill(existing_ralph_state.monitor_pid, signal.SIGTERM)
                    except OSError:
                        pass  # Process not running
            except (KeyError, TypeError):
                pass  # Malformed state, skip monitor cleanup

            # Remove ralph state if present
            ralph_state_dir = RALPH_DIR / args.name
            if ralph_state_dir.exists():
                import shutil
                try:
                    shutil.rmtree(ralph_state_dir)
                except OSError as e:
                    print(f"swarm: warning: cannot remove ralph state for '{args.name}': {e}", file=sys.stderr)

            # Stop heartbeat if active
            heartbeat_state = load_heartbeat_state(args.name)
            if heartbeat_state and heartbeat_state.status in ("active", "paused"):
                stop_heartbeat_monitor(heartbeat_state)
                heartbeat_state.status = "stopped"
                heartbeat_state.monitor_pid = None
                save_heartbeat_state(heartbeat_state)

            # Remove worker from state
            state.remove_worker(args.name)
            state.save()

            print(f"replaced existing worker {args.name}")
        else:
            print(f"swarm: error: worker '{args.name}' already exists", file=sys.stderr)
            sys.exit(1)

    # Handle --clean-state flag: clear ralph state without affecting worker/worktree
    if getattr(args, 'clean_state', False):
        ralph_state_dir = RALPH_DIR / args.name
        if ralph_state_dir.exists():
            import shutil
            try:
                shutil.rmtree(ralph_state_dir)
                print(f"cleared ralph state for {args.name}")
            except OSError as e:
                print(f"swarm: warning: cannot remove ralph state for '{args.name}': {e}", file=sys.stderr)

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
            # Fix core.bare misconfiguration before checking git root
            _check_and_fix_core_bare()

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
        create_tmux_window(session, args.name, cwd, cmd, socket, env=env_dict)
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
            check_done_continuous=bool(args.check_done_continuous),
            max_context=getattr(args, 'max_context', None),
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
        baseline_content = send_prompt_to_worker(worker, prompt_content)

        # Record baseline content for done-pattern self-match mitigation
        ralph_state.prompt_baseline_content = baseline_content
        save_ralph_state(ralph_state)

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

    # Determine launch mode
    foreground = getattr(args, 'foreground', False)

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
    should_start_loop = hasattr(args, 'no_run') and not args.no_run
    if should_start_loop:
        if foreground:
            # Foreground mode: block while running (original behavior)
            from argparse import Namespace
            loop_args = Namespace(name=args.name)
            cmd_ralph_run(loop_args)
        else:
            # Background mode (default): start monitoring loop as a background process
            monitor_proc = subprocess.Popen(
                [sys.executable, os.path.abspath('swarm.py'), 'ralph', 'run', args.name],
                start_new_session=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
            )
            # Store monitor PID in ralph state for --replace cleanup
            ralph_state = load_ralph_state(args.name)
            if ralph_state:
                ralph_state.monitor_pid = monitor_proc.pid
                save_ralph_state(ralph_state)

            # Print monitoring commands
            print(f"\nMonitor:")
            print(f"  swarm ralph status {args.name}    # loop progress")
            print(f"  swarm peek {args.name}            # terminal output")
            print(f"  swarm ralph logs {args.name}      # iteration history")
            print(f"  swarm kill {args.name}            # stop worker")


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

    # Pre-calculate screen change age for use in Status line and display
    screen_change_seconds_ago = None
    if ralph_state.last_screen_change:
        try:
            last_change_dt = datetime.fromisoformat(ralph_state.last_screen_change)
            now = datetime.now(timezone.utc)
            # Ensure last_change_dt is timezone-aware for comparison
            if last_change_dt.tzinfo is None:
                last_change_dt = last_change_dt.replace(tzinfo=timezone.utc)
            screen_change_seconds_ago = int((now - last_change_dt).total_seconds())
        except (ValueError, TypeError):
            pass

    # Format output per spec
    print(f"Ralph Loop: {ralph_state.worker_name}")

    # Build status line — append stuck warning if screen unchanged >60s
    status_line = f"Status: {ralph_state.status}"
    if screen_change_seconds_ago is not None and screen_change_seconds_ago > 60:
        status_line += f" (possibly stuck — no output change for {screen_change_seconds_ago}s)"
    print(status_line)

    # Build iteration line with ETA if we have timing data
    iteration_line = f"Iteration: {ralph_state.current_iteration}/{ralph_state.max_iterations}"
    if ralph_state.iteration_durations:
        avg_duration = sum(ralph_state.iteration_durations) / len(ralph_state.iteration_durations)
        remaining_iterations = ralph_state.max_iterations - ralph_state.current_iteration
        if remaining_iterations > 0 and ralph_state.status == "running":
            remaining_secs = int(avg_duration * remaining_iterations)
            iteration_line += f" (avg {format_duration(int(avg_duration))}/iter, ~{format_duration(remaining_secs)} remaining)"
        else:
            iteration_line += f" (avg {format_duration(int(avg_duration))}/iter)"
    print(iteration_line)

    if ralph_state.started:
        # Parse ISO format and format nicely
        started_dt = datetime.fromisoformat(ralph_state.started)
        print(f"Started: {started_dt.strftime('%Y-%m-%d %H:%M:%S')}")

    if ralph_state.last_iteration_started:
        last_iter_dt = datetime.fromisoformat(ralph_state.last_iteration_started)
        print(f"Current iteration started: {last_iter_dt.strftime('%Y-%m-%d %H:%M:%S')}")

    if ralph_state.last_iteration_ended and ralph_state.status == "stopped":
        last_ended_dt = datetime.fromisoformat(ralph_state.last_iteration_ended)
        print(f"Last iteration ended: {last_ended_dt.strftime('%Y-%m-%d %H:%M:%S')}")

    print(f"Consecutive failures: {ralph_state.consecutive_failures}")
    print(f"Total failures: {ralph_state.total_failures}")
    print(f"Inactivity timeout: {ralph_state.inactivity_timeout}s")

    # Display last screen change timestamp
    if screen_change_seconds_ago is not None:
        print(f"Last screen change: {screen_change_seconds_ago}s ago")
    elif ralph_state.last_screen_change:
        print("Last screen change: (unknown)")
    else:
        print("Last screen change: (none)")

    if ralph_state.done_pattern:
        print(f"Done pattern: {ralph_state.done_pattern}")

    # Show last 5 terminal lines when possibly stuck (screen unchanged >60s)
    if screen_change_seconds_ago is not None and screen_change_seconds_ago > 60 and worker and worker.tmux:
        try:
            pane_content = tmux_capture_pane(
                session=worker.tmux.session,
                window=worker.tmux.window,
                socket=worker.tmux.socket,
            )
            lines = [l for l in pane_content.rstrip('\n').split('\n') if l.strip()]
            last_lines = lines[-5:] if len(lines) >= 5 else lines
            if last_lines:
                print("Last output:")
                for line in last_lines:
                    print(f"  {line}")
        except Exception:
            pass  # tmux may not be available in status check

    # Show exit reason (B5: special handling for monitor_disconnected)
    if ralph_state.exit_reason:
        if ralph_state.exit_reason == "monitor_disconnected":
            # Check current worker status to provide helpful context
            worker_status = refresh_worker_status(worker) if worker else "unknown"
            print(f"Exit reason: monitor_disconnected (worker {worker_status})")
            print(f"Worker status: {worker_status}")
        else:
            print(f"Exit reason: {ralph_state.exit_reason}")
    elif ralph_state.status == "running":
        print(f"Exit reason: (none - still running)")


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


def cmd_ralph_clean(args) -> None:
    """Remove ralph state for one or all workers.

    Removes the ralph state directory (~/.swarm/ralph/<name>/) without
    killing worker processes or removing worktrees.

    Args:
        args: Namespace with optional name and all attributes
    """
    # Validate: one of name or --all required
    if not args.name and not args.all:
        print("swarm: error: must specify worker name or use --all", file=sys.stderr)
        sys.exit(1)

    if args.all:
        # Clean all ralph state directories
        if not RALPH_DIR.exists():
            return

        state = State()
        cleaned = False
        for worker_dir in sorted(RALPH_DIR.iterdir()):
            if worker_dir.is_dir():
                worker_name = worker_dir.name
                # Check if worker is still running
                worker = state.get_worker(worker_name)
                if worker and refresh_worker_status(worker) == "running":
                    print(f"swarm: warning: worker '{worker_name}' is still running (only ralph state removed)", file=sys.stderr)
                import shutil
                shutil.rmtree(worker_dir)
                print(f"cleaned ralph state for {worker_name}")
                cleaned = True
        return

    # Clean specific worker
    ralph_state_dir = RALPH_DIR / args.name
    if not ralph_state_dir.exists():
        print(f"swarm: error: no ralph state found for worker '{args.name}'", file=sys.stderr)
        sys.exit(1)

    # Check if worker is still running
    state = State()
    worker = state.get_worker(args.name)
    if worker and refresh_worker_status(worker) == "running":
        print(f"swarm: warning: worker '{args.name}' is still running (only ralph state removed)", file=sys.stderr)

    import shutil
    shutil.rmtree(ralph_state_dir)
    print(f"cleaned ralph state for {args.name}")


def cmd_ralph_logs(args) -> None:
    """Show iteration history log for a ralph worker.

    Displays the ralph iteration log from ~/.swarm/ralph/<name>/iterations.log.
    Supports showing all entries, last N entries, or tailing in real-time.

    Args:
        args: Namespace with name, live, and lines attributes
    """
    # Check ralph state exists (don't need full state, just verify worker exists)
    ralph_state = load_ralph_state(args.name)

    if not ralph_state:
        print(f"swarm: error: no ralph state found for worker '{args.name}'", file=sys.stderr)
        sys.exit(1)

    # Get log file path
    log_path = get_ralph_iterations_log_path(args.name)

    if not log_path.exists():
        print(f"swarm: error: no iteration log found for worker '{args.name}'", file=sys.stderr)
        sys.exit(1)

    if args.live:
        # Tail the log file in real-time (like tail -f)
        try:
            # First print existing content
            with open(log_path, 'r') as f:
                content = f.read()
                if content:
                    print(content, end='')

            # Then tail for new content
            with open(log_path, 'r') as f:
                # Seek to end of file
                f.seek(0, 2)
                while True:
                    line = f.readline()
                    if line:
                        print(line, end='', flush=True)
                    else:
                        time.sleep(0.5)
        except KeyboardInterrupt:
            # User pressed Ctrl+C, exit gracefully
            pass
    elif args.lines is not None:
        # Show last N entries
        with open(log_path, 'r') as f:
            lines = f.readlines()
            # Get last N lines
            last_lines = lines[-args.lines:] if len(lines) >= args.lines else lines
            for line in last_lines:
                print(line, end='')
    else:
        # Show all entries
        with open(log_path, 'r') as f:
            content = f.read()
            if content:
                print(content, end='')


def cmd_ralph_stop(args) -> None:
    """Stop a ralph worker (alias for 'swarm kill').

    Delegates to cmd_kill() with equivalent arguments.

    Args:
        args: Namespace with name, rm_worktree, and force_dirty attributes
    """
    from argparse import Namespace
    kill_args = Namespace(
        name=args.name,
        rm_worktree=getattr(args, 'rm_worktree', False),
        force_dirty=getattr(args, 'force_dirty', False),
        all=False,
    )
    cmd_kill(kill_args)


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
    check_done_continuous: bool = False,
    prompt_baseline_content: str = "",
    ralph_state: Optional["RalphState"] = None
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
        prompt_baseline_content: Pane content snapshot captured after prompt injection.
            When non-empty, done pattern is only checked against content after this
            baseline prefix, preventing self-match against the prompt text itself.
        ralph_state: Optional RalphState to update last_screen_change timestamp

    Returns:
        String indicating why monitoring ended:
        - "exited": Worker exited on its own
        - "inactive": Inactivity timeout reached
        - "done_pattern": Done pattern matched (only if check_done_continuous)
        - "compaction": Fatal pattern detected (e.g. "Compacting conversation")
        - "context_nudge": Context usage reached max_context threshold (first time only)
        - "context_threshold": Context usage reached max_context+15 threshold (force kill)
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

    # Compile done pattern regex for window loss check (works regardless of check_done_continuous)
    done_regex_for_window_loss = None
    if done_pattern:
        try:
            done_regex_for_window_loss = re.compile(done_pattern)
        except re.error:
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

    # Track which stuck patterns have already been warned about this iteration
    warned_stuck_patterns: set = set()

    # Track last successfully captured content for window loss done-pattern check
    last_content: Optional[str] = None

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
            last_content = current_output

            # Check done pattern continuously if enabled
            if done_regex:
                # Capture with scrollback for done-pattern checking
                try:
                    full_output = tmux_capture_pane(
                        worker.tmux.session,
                        worker.tmux.window,
                        history_lines=2000,
                        socket=socket
                    )
                except subprocess.CalledProcessError:
                    full_output = current_output

                # Strip baseline prefix to avoid self-matching against prompt text
                if prompt_baseline_content and full_output.startswith(prompt_baseline_content):
                    check_content = full_output[len(prompt_baseline_content):]
                else:
                    # Baseline isn't a prefix (terminal cleared or no baseline) — check full content
                    check_content = full_output if not prompt_baseline_content else full_output

                if done_regex.search(check_content):
                    return "done_pattern"

            # Normalize and hash the content
            normalized = normalize_content(current_output)
            current_hash = hash_content(normalized)

            # Check for stuck patterns (warn once per pattern per iteration)
            if ralph_state is not None:
                for stuck_text, stuck_msg in STUCK_PATTERNS.items():
                    if stuck_text in normalized and stuck_text not in warned_stuck_patterns:
                        warned_stuck_patterns.add(stuck_text)
                        log_ralph_iteration(
                            ralph_state.worker_name, "WARN",
                            message=f"iteration {ralph_state.current_iteration}: {stuck_msg}"
                        )

            # Check for fatal patterns (compaction, etc.) — immediate kill required
            # Use full pane content (ANSI-stripped) instead of normalized (last 20 lines)
            # because the fatal text may not be in the last 20 visible lines
            full_clean = ansi_escape.sub('', current_output)
            if any(p in full_clean for p in FATAL_PATTERNS):
                return "compaction"

            # Check context percentage if max_context is set
            if ralph_state is not None and ralph_state.max_context is not None:
                # Scan last 3 lines for percentage pattern
                last_3_lines = normalized.split('\n')[-3:]
                pct_pattern = re.compile(r'(\d+)%')
                for line in last_3_lines:
                    match = pct_pattern.search(line)
                    if match:
                        pct = int(match.group(1))
                        kill_threshold = ralph_state.max_context + 15
                        if pct >= kill_threshold:
                            return "context_threshold"
                        if pct >= ralph_state.max_context and not ralph_state.context_nudge_sent:
                            return "context_nudge"

            # Compare hashes
            if current_hash != last_hash:
                # Screen changed, reset timer
                last_hash = current_hash
                stable_start = None
                # Track screen change timestamp in ralph state
                if ralph_state is not None:
                    ralph_state.last_screen_change = datetime.now(timezone.utc).isoformat()
                    save_ralph_state(ralph_state)
            else:
                # Screen unchanged
                if stable_start is None:
                    stable_start = time.time()
                elif (time.time() - stable_start) >= timeout:
                    return "inactive"

        except subprocess.CalledProcessError:
            # Window might have closed — check done pattern against last content
            if done_regex_for_window_loss and last_content is not None:
                if prompt_baseline_content and last_content.startswith(prompt_baseline_content):
                    check_content = last_content[len(prompt_baseline_content):]
                else:
                    check_content = last_content
                if done_regex_for_window_loss.search(check_content):
                    return "done"
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
    create_tmux_window(session, name, cwd, cmd, socket, env=env)
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


def send_prompt_to_worker(worker: Worker, prompt_content: str) -> str:
    """Send prompt content to a worker.

    Args:
        worker: The worker to send to
        prompt_content: The prompt content to send

    Returns:
        Pane content snapshot (with scrollback) after sending the prompt,
        used as baseline for done-pattern filtering. Returns "" if the
        worker has no tmux info or capture fails.
    """
    if not worker.tmux:
        return ""

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
        socket=socket,
        pre_clear=False
    )

    # Capture pane content (with scrollback) after prompt injection for done-pattern baseline
    try:
        pane_content = tmux_capture_pane(
            worker.tmux.session,
            worker.tmux.window,
            history_lines=2000,
            socket=socket
        )
        return pane_content
    except subprocess.CalledProcessError:
        return ""


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

    # Main ralph loop - wrapped in try/finally to detect monitor disconnect (B5)
    try:
        _run_ralph_loop_inner(args, original_cmd, original_cwd, original_env, original_tags, session, socket, original_worktree)
    finally:
        # B5: Check for monitor disconnect - if we're exiting but worker is still running
        _check_monitor_disconnect(args.name)


def _check_monitor_disconnect(worker_name: str) -> None:
    """Check if monitor is disconnecting while worker is still running (B5).

    This is called when the ralph monitor loop exits for any reason.
    If the worker is still running, we set exit_reason to monitor_disconnected
    to help users understand what happened.

    Args:
        worker_name: Name of the worker to check
    """
    ralph_state = load_ralph_state(worker_name)
    if not ralph_state:
        return

    # Only update if the ralph state indicates it should be running or is in an
    # indeterminate state (no exit_reason yet, status is 'running')
    if ralph_state.status == "running" and ralph_state.exit_reason is None:
        # Check if worker is actually still running
        state = State()
        worker = state.get_worker(worker_name)
        if worker and refresh_worker_status(worker) == "running":
            # Worker is still running but monitor is exiting
            ralph_state.status = "stopped"
            ralph_state.exit_reason = "monitor_disconnected"
            save_ralph_state(ralph_state)
            log_ralph_iteration(
                worker_name,
                "DISCONNECT",
                reason="monitor_disconnected",
                worker_status="running"
            )
            print(f"[ralph] {worker_name}: monitor disconnected (worker still running)")


def _run_preflight_check(worker_name: str) -> None:
    """Run pre-flight check on iteration 1 to detect stuck patterns.

    Waits 10 seconds after spawn, captures terminal output (including scrollback),
    and checks for known stuck patterns (login prompts, theme pickers, etc.).
    If a stuck pattern is detected, kills the worker and exits with error.

    Args:
        worker_name: Name of the worker to check
    """
    import re

    ralph_state = load_ralph_state(worker_name)
    if not ralph_state or ralph_state.current_iteration != 1:
        return

    state = State()
    worker = state.get_worker(worker_name)
    if not worker or not worker.tmux:
        return

    time.sleep(10)
    try:
        preflight_output = tmux_capture_pane(
            worker.tmux.session,
            worker.tmux.window,
            history_lines=100,
            socket=worker.tmux.socket
        )
        preflight_clean = re.sub(r'\x1b\[[0-9;]*m', '', preflight_output)
        for stuck_text, stuck_msg in STUCK_PATTERNS.items():
            if stuck_text in preflight_clean:
                log_ralph_iteration(
                    ralph_state.worker_name, "ERROR",
                    message=f"iteration 1: pre-flight check failed — {stuck_msg}"
                )
                print(
                    f"swarm: error: pre-flight check failed — {stuck_msg}\n"
                    f"  fix: resolve the issue and re-run ralph spawn",
                    file=sys.stderr
                )
                kill_worker_for_ralph(worker, state)
                state.remove_worker(worker_name)
                ralph_state.status = "failed"
                ralph_state.exit_reason = "preflight_failed"
                save_ralph_state(ralph_state)
                sys.exit(1)
    except subprocess.CalledProcessError:
        pass  # tmux capture failed, skip pre-flight


def _run_ralph_loop_inner(
    args,
    original_cmd: list[str],
    original_cwd: Path,
    original_env: dict[str, str],
    original_tags: list[str],
    session: str,
    socket: Optional[str],
    original_worktree: Optional[WorktreeInfo]
) -> None:
    """Inner implementation of the ralph loop.

    This function contains the actual loop logic, separated to allow
    proper monitor disconnect detection in the outer function.

    Args:
        args: Namespace with name attribute
        original_cmd: Original command to spawn
        original_cwd: Original working directory
        original_env: Original environment variables
        original_tags: Original tags
        session: Tmux session name
        socket: Tmux socket path
        original_worktree: Original worktree info
    """
    import re

    # Pre-flight check: on iteration 1 only, wait and check for stuck patterns
    _run_preflight_check(args.name)

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
            ralph_state.exit_reason = "max_iterations"
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
            # Increment iteration counter and reset per-iteration flags
            ralph_state.current_iteration += 1
            ralph_state.last_iteration_started = datetime.now().isoformat()
            ralph_state.context_nudge_sent = False
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
                baseline_content = send_prompt_to_worker(worker, prompt_content)

                # Record baseline content for done-pattern self-match mitigation
                ralph_state.prompt_baseline_content = baseline_content
                save_ralph_state(ralph_state)

            except Exception as e:
                print(f"swarm: error: failed to spawn worker: {e}", file=sys.stderr)
                ralph_state.consecutive_failures += 1
                ralph_state.total_failures += 1
                save_ralph_state(ralph_state)

                # Apply backoff
                if ralph_state.consecutive_failures >= 5:
                    print(f"[ralph] {args.name}: 5 consecutive failures, stopping loop")
                    ralph_state.status = "failed"
                    ralph_state.exit_reason = "failed"
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
            check_done_continuous=ralph_state.check_done_continuous,
            prompt_baseline_content=ralph_state.prompt_baseline_content,
            ralph_state=ralph_state
        )

        # Reload ralph state (could have been paused while monitoring)
        ralph_state = load_ralph_state(args.name)
        if not ralph_state or ralph_state.status == "paused":
            print(f"[ralph] {args.name}: paused, exiting loop")
            break

        # Check worker status
        state = State()
        worker = state.get_worker(args.name)

        if monitor_result == "done_pattern" or monitor_result == "done":
            # Done pattern matched during continuous monitoring or on window loss
            if monitor_result == "done":
                print(f"[ralph] {args.name}: done pattern matched (tmux window lost), stopping loop")
                log_ralph_iteration(
                    args.name,
                    "END",
                    iteration=ralph_state.current_iteration,
                    message=f"iteration {ralph_state.current_iteration} -- tmux window lost"
                )
            else:
                print(f"[ralph] {args.name}: done pattern matched, stopping loop")
            log_ralph_iteration(
                args.name,
                "DONE",
                total_iterations=ralph_state.current_iteration,
                reason="done_pattern"
            )
            ralph_state.status = "stopped"
            ralph_state.exit_reason = "done_pattern"
            save_ralph_state(ralph_state)
            # Kill the worker since we're stopping
            if worker:
                kill_worker_for_ralph(worker, state)
            return

        if monitor_result == "context_nudge":
            # Context usage reached threshold — send nudge and continue monitoring
            pct_msg = f"{ralph_state.max_context}%" if ralph_state.max_context else "?"
            nudge_text = f"You're at {pct_msg} context. Commit WIP and /exit NOW."
            print(f"[ralph] {args.name}: context nudge sent ({pct_msg})")
            log_ralph_iteration(
                args.name,
                "WARN",
                iteration=ralph_state.current_iteration,
                message=f"iteration {ralph_state.current_iteration} -- context nudge sent at {pct_msg}"
            )
            ralph_state.context_nudge_sent = True
            save_ralph_state(ralph_state)

            # Send nudge to worker
            if worker and worker.tmux:
                tmux_send(
                    worker.tmux.session,
                    worker.tmux.window,
                    nudge_text,
                    enter=True,
                    socket=worker.tmux.socket,
                    pre_clear=False,
                )
            # Continue monitoring (don't restart) — loop back to detect_inactivity
            continue

        elif monitor_result == "context_threshold":
            # Context usage exceeded kill threshold — force kill
            kill_pct = (ralph_state.max_context + 15) if ralph_state.max_context else "?"
            print(f"[ralph] {args.name}: context threshold exceeded ({kill_pct}%), killing iteration {ralph_state.current_iteration}")
            log_ralph_iteration(
                args.name,
                "FATAL",
                iteration=ralph_state.current_iteration,
                message=f"iteration {ralph_state.current_iteration} -- context threshold exceeded, killing"
            )
            ralph_state.exit_reason = "context_threshold"
            save_ralph_state(ralph_state)

            # Kill the worker — do NOT count as consecutive failure
            if worker:
                kill_worker_for_ralph(worker, state)
            # Proceed to next iteration (continue the while loop)

        elif monitor_result == "compaction":
            # Fatal pattern detected (e.g. "Compacting conversation") — kill and restart
            print(f"[ralph] {args.name}: compaction detected, killing iteration {ralph_state.current_iteration}")
            log_ralph_iteration(
                args.name,
                "FATAL",
                iteration=ralph_state.current_iteration,
                message=f"iteration {ralph_state.current_iteration} -- compaction detected, killing"
            )
            ralph_state.exit_reason = "compaction"
            save_ralph_state(ralph_state)

            # Kill the worker — do NOT count as consecutive failure
            if worker:
                kill_worker_for_ralph(worker, state)
            # Proceed to next iteration (continue the while loop)

        elif monitor_result == "inactive":
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
            iteration_duration_secs = int(time.time() - iteration_start)
            duration = format_duration(iteration_duration_secs)
            print(f"[ralph] {args.name}: iteration {ralph_state.current_iteration} completed (exit: 0, duration: {duration})")
            log_ralph_iteration(
                args.name,
                "END",
                iteration=ralph_state.current_iteration,
                exit_code=0,
                duration=duration
            )

            # Reset consecutive failures on success and track iteration timing
            ralph_state.consecutive_failures = 0
            ralph_state.last_iteration_ended = datetime.now().isoformat()
            ralph_state.iteration_durations.append(iteration_duration_secs)
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
                    ralph_state.exit_reason = "done_pattern"
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
    - ls: Alias for list
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
    elif args.heartbeat_command == "ls":
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


if __name__ == "__main__":
    main()
