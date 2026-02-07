# Autonomous Loop Guide

How to set up sandboxed, autonomous Claude Code loops for any project using swarm.

## The Pattern

```
project/
├── ORCHESTRATOR.md              # Task plan + monitoring (per-epic)
├── PROMPT.md                    # Per-iteration instructions
├── IMPLEMENTATION_PLAN.md       # Checklist of tasks
├── sandbox.sh                   # Docker wrapper for Claude (per-project)
├── Dockerfile.sandbox           # Container image
├── setup-sandbox-network.sh     # Network lockdown (run manually once)
└── teardown-sandbox-network.sh  # Network teardown
```

Two layers:

1. **Run config** (how Claude executes) — `sandbox.sh`, `Dockerfile.sandbox`, network scripts. Per-project, rarely changes.
2. **Task plan** (what Claude does) — `ORCHESTRATOR.md`, `PROMPT.md`, `IMPLEMENTATION_PLAN.md`. Changes per epic/task.

## Quick Start

```bash
# Scaffold sandbox files in your project
swarm init --with-sandbox

# One-time setup
gh auth login                     # Git auth (token passed to container, no SSH keys)
docker build --build-arg USER_ID=$(id -u) --build-arg GROUP_ID=$(id -g) \
    -t sandbox-loop -f Dockerfile.sandbox .
sudo ./setup-sandbox-network.sh

# Create your task plan
swarm ralph init          # Creates PROMPT.md
vim ORCHESTRATOR.md       # Write your task plan

# Run sandboxed with ralph
swarm ralph spawn --name dev --prompt-file PROMPT.md --max-iterations 50 \
    -- ./sandbox.sh --dangerously-skip-permissions

# Or run sandboxed with loop.sh
SANDBOX=1 ./loop.sh 30
```

## Layer 1: Run Config

### sandbox.sh

A shell script that wraps `claude` inside `docker run`. This is the key insight: swarm doesn't need to know about Docker. The `-- command...` in `swarm spawn` accepts any executable, and `sandbox.sh` is just an executable that happens to run Claude inside a container.

```bash
#!/bin/bash
# sandbox.sh — Run Claude Code inside a sandboxed Docker container.
# Usage: ./sandbox.sh [claude args...]
# Example: ./sandbox.sh --dangerously-skip-permissions

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

# Resolve symlinked settings
CLAUDE_SETTINGS=$(readlink -f "$HOME/.claude/settings.json" 2>/dev/null || echo "$HOME/.claude/settings.json")

# Git auth via short-lived GitHub token (no SSH keys in the container)
GH_TOKEN="${GH_TOKEN:-}"
if [ -z "$GH_TOKEN" ] && command -v gh &>/dev/null; then
    GH_TOKEN=$(gh auth token 2>/dev/null || true)
fi
if [ -z "$GH_TOKEN" ]; then
    echo "warning: no GH_TOKEN found. git push will fail inside the container." >&2
    echo "  fix: run 'gh auth login' or export GH_TOKEN=ghp_..." >&2
fi

exec docker run --rm \
    --memory="$MEMORY" \
    --memory-swap="$MEMORY" \
    --cpus="$CPUS" \
    --pids-limit="$PIDS" \
    --network="$NETWORK" \
    -v "$(pwd):/workspace" \
    -v "$HOME/.claude/.credentials.json:/home/loopuser/.claude/.credentials.json:ro" \
    -v "$CLAUDE_SETTINGS:/home/loopuser/.claude/settings.json:ro" \
    -v "$HOME/.claude/projects:/home/loopuser/.claude/projects" \
    -e ANTHROPIC_API_KEY \
    -e DISABLE_AUTOUPDATER=1 \
    -e "GH_TOKEN=$GH_TOKEN" \
    -w /workspace \
    "$IMAGE" \
    claude "$@"
```

**Security posture**:
- **No SSH keys mounted** — git auth uses `GH_TOKEN` over HTTPS
- Token lives only in container memory (env var), dies with the container
- Claude credentials mounted **read-only**
- Only `projects/` directory is read-write (Claude needs this for project memory)
- No `.gitconfig` mounted (credential helper is baked into the image)

**Why a script instead of a swarm flag**: Unix philosophy. Swarm manages processes; Docker wraps processes. Keeping them separate means:
- You can version `sandbox.sh` per project (different toolchains need different images)
- You can use it with `loop.sh`, `swarm ralph`, or any other orchestrator
- No swarm code changes needed when Docker flags evolve

### Dockerfile.sandbox

Base image with Claude CLI and essential tools. Add your project's toolchain.

```dockerfile
FROM node:22-slim

# Base tools for Claude Code and git. Add your project's toolchain below.
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        git jq curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN npm install -g @anthropic-ai/claude-code

ARG USER_ID=1000
ARG GROUP_ID=1000
RUN if getent passwd $USER_ID >/dev/null; then userdel -r $(getent passwd $USER_ID | cut -d: -f1); fi && \
    if getent group $GROUP_ID >/dev/null; then groupdel $(getent group $GROUP_ID | cut -d: -f1) 2>/dev/null || true; fi && \
    groupadd -g $GROUP_ID loopuser && \
    useradd -m -u $USER_ID -g $GROUP_ID loopuser

USER loopuser

# Git auth: GH_TOKEN env var is used for HTTPS pushes (no SSH keys needed)
RUN git config --global credential.https://github.com.helper \
    '!f() { echo "protocol=https"; echo "host=github.com"; echo "username=x-access-token"; echo "password=$GH_TOKEN"; }; f'

WORKDIR /workspace
ENTRYPOINT []
CMD ["bash"]
```

**Customization**: The base image is intentionally minimal. Add your project's toolchain:
- Python project: `python3 python3-pip`
- Ruby: `ruby`
- Go: `golang`
- Swarm's own tests need: `tmux python3 python3-yaml make procps`

### Network Lockdown

`setup-sandbox-network.sh` creates a Docker network with iptables rules allowing only:
- `api.anthropic.com:443` (Claude API)
- `statsig.anthropic.com:443` + `statsig.com:443` (feature flags)
- `sentry.io:443` (error reporting)
- `github.com:443` (git push via HTTPS + API)
- DNS (udp+tcp/53)

Everything else is REJECTED.

```bash
# One-time setup (must run as root)
sudo ./setup-sandbox-network.sh

# Verify lockdown
docker run --rm --network=sandbox-net sandbox-loop curl -v --max-time 5 https://example.com
# ^ Should fail with "Connection refused"

# Teardown when done
sudo ./teardown-sandbox-network.sh
```

**Notes**:
- iptables rules don't survive reboot. Re-run after restart.
- Domain IPs can rotate. Re-run periodically for long sessions.
- These scripts require elevated privileges. Run them manually.

### Resource Limits

| Limit | Default | Rationale |
|-------|---------|-----------|
| Memory | 8g | Claude (~500MB) + test suite. No swap — OOM kills container, not host. |
| CPUs | 4 | Leaves cores for host. Prevents container from starving system. |
| PIDs | 512 | Headroom for tmux sessions in tests. Caps fork bombs. |

Override via environment:
```bash
MEMORY_LIMIT=12g CPU_LIMIT=6 PIDS_LIMIT=1024 ./sandbox.sh --dangerously-skip-permissions
```

## Layer 2: Task Plan

### ORCHESTRATOR.md

A markdown file that tells a human (or director Claude) how to run and monitor the loop for a specific epic. Not a rigid YAML pipeline — a flexible plan that adapts to reality.

Template structure:

```markdown
# [Epic Name] Orchestrator

## Quick Status
\`\`\`bash
swarm ralph status dev          # Iteration progress + ETA
git log --oneline -5            # Recent commits
grep -cE '^\s*-\s*\[x\]' IMPLEMENTATION_PLAN.md  # Tasks done
grep -cE '^\s*-\s*\[ \]' IMPLEMENTATION_PLAN.md   # Tasks remaining
\`\`\`

## Start
\`\`\`bash
swarm ralph spawn --name dev --prompt-file PROMPT.md --max-iterations 50 \
    -- ./sandbox.sh --dangerously-skip-permissions
\`\`\`

## Monitor
Check every 15-30 minutes:
\`\`\`bash
swarm ralph status dev
docker stats --filter "name=sandbox-loop" --no-stream
swarm logs dev --follow
\`\`\`

## Stop / Restart
\`\`\`bash
swarm kill dev --rm-worktree
swarm ralph spawn --name dev --replace --prompt-file PROMPT.md --max-iterations 50 \
    -- ./sandbox.sh --dangerously-skip-permissions
\`\`\`

## OOM Recovery
Exit code 137 = container hit memory limit. Loop auto-continues.
\`\`\`bash
docker stats --filter "name=sandbox-loop" --no-stream  # Check memory
MEMORY_LIMIT=12g swarm ralph spawn --name dev --replace ...  # Bump if needed
\`\`\`

## Rate Limit
If Claude hits rate limit, add heartbeat:
\`\`\`bash
swarm heartbeat start dev --interval 4h --expire 24h
\`\`\`

## Progress Summary

| Phase | Description | Tasks |
|-------|-------------|-------|
| Phase 1 | ... | N tasks |
| Phase 2 | ... | N tasks |
```

### PROMPT.md

Per-iteration instructions. Read by Claude at the start of each context window. Keep it minimal — less prompt = more context for actual work.

```markdown
study CLAUDE.md and pick the most important incomplete task from IMPLEMENTATION_PLAN.md

IMPORTANT:
- do not assume anything is implemented - verify by reading code
- update IMPLEMENTATION_PLAN.md when the task is done
- if tests are missing, add them
- run tests after changes
- commit and push when you are done
```

Customize per project. The key rules:
- **One task per iteration** — don't try to do everything
- **Verify before assuming** — each context window starts fresh
- **Commit before exiting** — uncommitted work is lost if the container dies

### IMPLEMENTATION_PLAN.md

A checklist that persists across iterations. Claude reads it to find the next task and checks off completed ones.

```markdown
# Implementation Plan

## Phase 1: Core Features
- [x] Task 1 (completed in iteration 3)
- [ ] Task 2
- [ ] Task 3

## Phase 2: Testing
- [ ] Add unit tests for feature X
- [ ] Add integration tests for feature Y
```

## Choosing: loop.sh vs swarm ralph

Both orchestrate autonomous loops. Choose based on your needs:

| | `loop.sh` | `swarm ralph` |
|---|---|---|
| Sandbox support | Built-in (`SANDBOX=1`) | Via `-- ./sandbox.sh` |
| State tracking | Log files | `~/.swarm/ralph/<name>/state.json` |
| Monitoring | `tail` log files | `swarm ralph status`, `swarm logs` |
| Pause/resume | Kill and restart | `swarm ralph pause/resume` |
| Multiple workers | Run multiple loop.sh | `swarm ralph spawn` per worker |
| ETA display | No | Yes (`swarm ralph status`) |
| Best for | Simple single loops | Multi-worker orchestration |

**Both work with `sandbox.sh`**. Ralph just passes it as the command; loop.sh uses `SANDBOX=1` env var internally.

## OOM Behavior

When a container hits the memory limit:
1. Kernel cgroup OOM-killer fires
2. Container is killed (exit 137) — host is unaffected
3. Loop auto-continues to next iteration
4. Committed work is preserved (bind-mounted repo)
5. Uncommitted work in that iteration is lost

This is the primary reason to use sandboxed execution for unattended runs.

## Adapting to Your Project

1. **Toolchain**: Edit `Dockerfile.sandbox` to add your language runtime
2. **Resource limits**: Tune `MEMORY_LIMIT`, `CPU_LIMIT`, `PIDS_LIMIT` in `sandbox.sh`
3. **Network allowlist**: Edit `setup-sandbox-network.sh` to add domains your project needs (e.g., `registry.npmjs.org` for npm install)
4. **Git remote**: Ensure your repo uses HTTPS, not SSH (`git remote set-url origin https://github.com/user/repo.git`)
5. **Git auth**: Run `gh auth login` on the host (sandbox.sh auto-fetches the token)
6. **Prompt**: Customize `PROMPT.md` for your project's conventions and tooling
7. **Plan**: Write `ORCHESTRATOR.md` fresh for each epic
