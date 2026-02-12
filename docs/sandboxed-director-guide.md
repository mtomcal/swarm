# Director Guide

How to run an interactive Claude session (the director) that manages Docker-sandboxed workers.

## Overview

- **Director** = you, in an interactive Claude session on the host
- **Workers** = autonomous ralph loops inside Docker containers via `sandbox.sh`
- **Docker is the only isolation mechanism**, applied to workers only

The director doesn't need sandboxing because it's interactive — you see and approve everything it does.

## Prerequisites

### One-time setup

```bash
# 1. Scaffold sandbox files
swarm init --with-sandbox

# 2. Build Docker image
docker build --build-arg USER_ID=$(id -u) --build-arg GROUP_ID=$(id -g) \
    -t sandbox-loop -f Dockerfile.sandbox .

# 3. Network lockdown (iptables allowlist — does not survive reboot)
sudo ./setup-sandbox-network.sh

# 4. Git auth (token passed to container, no SSH keys)
gh auth login
```

### Before each session

```bash
# Re-apply network rules if machine was rebooted
sudo ./setup-sandbox-network.sh

# Verify lockdown
docker run --rm --network=sandbox-net sandbox-loop curl -v --max-time 5 https://example.com
# Should fail with "Connection refused"
```

## Workflow

### 1. Start workers

```bash
swarm ralph spawn --name dev --prompt-file PROMPT.md --max-iterations 50 \
    -- ./sandbox.sh --dangerously-skip-permissions
```

### 2. Start the director (interactive)

```bash
claude --dangerously-skip-permissions
# Tell it: "Read ORCHESTRATOR.md and manage the epic."
```

### 3. Monitor

```bash
# Task progress
grep -cE '^\s*-\s*\[x\]' IMPLEMENTATION_PLAN.md  # Done
grep -cE '^\s*-\s*\[ \]' IMPLEMENTATION_PLAN.md   # Remaining

# Worker status
swarm ralph status dev
swarm ralph logs dev
git log --oneline -5

# Container resources
docker ps --filter "ancestor=sandbox-loop" --format '{{.Names}}'
docker stats <exact-container-name> --no-stream
```

### 4. Intervene when stuck

- Worker loops on same task 2+ iterations: update `PROMPT.md` or `IMPLEMENTATION_PLAN.md`
- OOM (exit 137): bump memory with `MEMORY_LIMIT=12g`
- Rate limited: `swarm heartbeat start dev --interval 4h --expire 24h`

### 5. Verify completion

When all tasks are `[x]`, confirm tests pass and no stale references remain.

## References

- [Autonomous Loop Guide](autonomous-loop-guide.md) — Docker sandbox setup for workers
- [Sandbox Loop Spec](sandbox-loop-spec.md) — Detailed Docker sandbox architecture
