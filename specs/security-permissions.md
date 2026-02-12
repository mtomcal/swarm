# Security and Permissions

## Overview

Swarm workers require special permission handling to operate autonomously. By default, Claude Code prompts for user confirmation before executing bash commands, editing files, or making network requests. This interactive permission model is incompatible with background agent workers that run unattended. This spec documents the permission requirements, security tradeoffs, and available mitigation strategies.

## Dependencies

- External: Claude Code CLI (`claude`), Docker (optional for container sandboxing)
- Internal: `spawn.md`, `ralph-loop.md`

## Behavior

### Permission Bypass Requirement

**Description**: Enable autonomous agent operation by bypassing interactive permission prompts.

**Inputs**:
- `--dangerously-skip-permissions` (flag, required for autonomy): Passed to Claude CLI after the `--` separator

**Outputs**:
- Success: Agent runs without prompting for tool confirmations
- Failure: Without the flag, agent stalls waiting for user input that never arrives

**Side Effects**:
- Agent can execute arbitrary bash commands without confirmation
- Agent can read, write, and delete files without confirmation
- Agent can make network requests without confirmation
- Agent can install packages without confirmation

**Error Conditions**:
| Condition | Behavior |
|-----------|----------|
| Flag omitted | Agent prompts for permission, worker stalls indefinitely |
| Misspelled flag | Claude CLI rejects unknown flag, worker fails to start |

### Docker Sandbox (sandbox.sh)

**Description**: Run swarm workers inside Docker containers with resource limits, network lockdown, and filesystem isolation via `sandbox.sh`.

**Inputs**:
- `sandbox.sh` (script, required): Docker wrapper that runs `claude` inside a container
- `Dockerfile.sandbox` (file, required): Container image with Claude Code and project toolchain
- `setup-sandbox-network.sh` (script, optional): iptables allowlist for container network
- Resource limits via environment: `MEMORY_LIMIT`, `CPU_LIMIT`, `PIDS_LIMIT`

**Outputs**:
- Success: Worker runs inside a Docker container with hard resource caps and network restrictions
- Failure: Container fails to start (missing image, network not created, etc.)

**Side Effects**:
- Filesystem limited to bind-mounted project repo and read-only credentials
- Network restricted to iptables allowlist (Anthropic API, GitHub, DNS)
- Memory capped via cgroup (OOM kills container, not host)
- CPU and PID limits enforced

**Error Conditions**:
| Condition | Behavior |
|-----------|----------|
| Docker not installed | `sandbox.sh` fails with "docker: command not found" |
| Image not built | `sandbox.sh` auto-builds if missing (slow on first run) |
| Network not created | Container starts but has unrestricted network access |
| Missing `-it` flags | Claude gets no TTY and exits silently |
| No `GH_TOKEN` | Git push fails inside container |

## Scenarios

### Scenario: Autonomous worker without sandbox

- **Given**: A user spawning a swarm worker for autonomous operation
- **When**: `swarm spawn --name agent --tmux --worktree -- claude --dangerously-skip-permissions`
- **Then**:
  - Worker starts successfully
  - Agent operates without permission prompts
  - Agent has full access to filesystem, network, and shell
  - No isolation is in place

### Scenario: Autonomous worker in Docker sandbox

- **Given**: Docker installed, `sandbox.sh` and `Dockerfile.sandbox` present, network rules applied
- **When**: `swarm ralph spawn --name dev --prompt-file PROMPT.md --max-iterations 50 -- ./sandbox.sh --dangerously-skip-permissions`
- **Then**:
  - Worker runs inside Docker container
  - Memory capped at 8g (configurable via `MEMORY_LIMIT`)
  - Network restricted to iptables allowlist
  - Filesystem limited to bind-mounted repo
  - OOM kills container (exit 137), loop auto-continues

### Scenario: Worker without permission bypass

- **Given**: A user forgetting the permission bypass flag
- **When**: `swarm spawn --name agent --tmux --worktree -- claude`
- **Then**:
  - Worker starts, Claude CLI launches
  - Agent prompts for first tool use
  - Worker stalls indefinitely waiting for input
  - No work is accomplished
  - User must kill worker and respawn with correct flag

## Edge Cases

- **Domain fronting**: Network allowlist can potentially be bypassed via domain fronting on allowed domains; be conservative with the allowlist.
- **iptables rules don't survive reboot**: Re-run `setup-sandbox-network.sh` after restart.
- **Domain IP rotation**: IPs can rotate for long sessions. Re-run network setup periodically.
- **Docker socket**: Never mount `docker.sock` inside the container — this bypasses all isolation.

## Recovery Procedures

### Worker stalled waiting for permissions

```bash
# Check if worker is stalled
swarm logs agent  # Shows permission prompt waiting for input

# Kill the stalled worker
swarm kill agent

# Respawn with correct flag
swarm spawn --name agent --tmux --worktree -- claude --dangerously-skip-permissions
```

### Container OOM (exit 137)

```bash
# Loop auto-continues. To increase memory:
MEMORY_LIMIT=12g swarm ralph spawn --name dev --replace \
    --prompt-file PROMPT.md --max-iterations 50 \
    -- ./sandbox.sh --dangerously-skip-permissions
```

## Implementation Notes

### Flag Ordering

The `--dangerously-skip-permissions` flag must come AFTER the `--` separator that delimits swarm arguments from the command to run:

```bash
# Correct
swarm spawn --name agent --tmux -- claude --dangerously-skip-permissions

# Incorrect (flag interpreted by swarm, not claude)
swarm spawn --name agent --tmux --dangerously-skip-permissions -- claude
```
