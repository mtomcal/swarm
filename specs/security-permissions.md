# Security and Permissions

## Overview

Swarm workers require special permission handling to operate autonomously. By default, Claude Code prompts for user confirmation before executing bash commands, editing files, or making network requests. This interactive permission model is incompatible with background agent workers that run unattended. This spec documents the permission requirements, security tradeoffs, and available mitigation strategies.

## Dependencies

- External: Claude Code CLI (`claude`), Docker (optional for container sandboxing)
- Internal: `spawn.md`, `ralph-loop.md`, `workflow.md`

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

### Native Sandbox Integration

**Description**: Use Claude Code's built-in sandboxing for OS-level isolation while maintaining autonomous operation.

**Inputs**:
- Sandbox configuration via `/sandbox` command in Claude (interactive setup)
- Sandbox settings in `~/.claude/settings.json`

**Outputs**:
- Success: Agent operates within defined filesystem and network boundaries
- Failure: Operations outside sandbox boundaries are blocked at OS level

**Side Effects**:
- Filesystem writes restricted to allowed directories (default: working directory)
- Network access restricted to allowed domains
- All child processes inherit sandbox restrictions

**Error Conditions**:
| Condition | Behavior |
|-----------|----------|
| bubblewrap not installed (Linux) | Sandbox unavailable, falls back to no isolation |
| Sandbox violation attempt | Operation blocked, user notified |
| Incompatible command (e.g., docker) | Command fails, may need `excludedCommands` config |

### Docker Sandbox Integration

**Description**: Run swarm workers inside Docker containers with microVM-based isolation.

**Inputs**:
- Docker Desktop 4.50+ with Sandboxes feature
- Container image with Claude Code installed

**Outputs**:
- Success: Worker runs in isolated microVM with dedicated Docker daemon
- Failure: Container fails to start or sandbox feature unavailable

**Side Effects**:
- Complete filesystem isolation from host
- Network isolation with configurable allow/deny lists
- Dedicated Docker daemon per sandbox (no access to host Docker)

**Error Conditions**:
| Condition | Behavior |
|-----------|----------|
| Docker Desktop < 4.50 | Sandboxes feature unavailable |
| No sandbox license | Feature disabled |
| Host socket mounted | Security bypass possible (avoid mounting docker.sock) |

### Tool Restriction

**Description**: Limit which tools Claude can use via allowlist.

**Inputs**:
- `--allowedTools` (string, optional): Space-separated list of tool names

**Outputs**:
- Success: Agent can only use specified tools
- Failure: Agent attempts to use disallowed tool, operation blocked

**Side Effects**:
- Reduces attack surface by preventing bash execution
- May limit agent capabilities (e.g., cannot run tests without Bash)

**Error Conditions**:
| Condition | Behavior |
|-----------|----------|
| Unknown tool name | Tool not available to agent |
| Empty allowlist | All tools disabled (agent non-functional) |

## Scenarios

### Scenario: Autonomous worker without sandbox

- **Given**: A user spawning a swarm worker for autonomous operation
- **When**: `swarm spawn --name agent --tmux --worktree -- claude --dangerously-skip-permissions`
- **Then**:
  - Worker starts successfully
  - Agent operates without permission prompts
  - Agent has full access to filesystem, network, and shell
  - No isolation is in place

### Scenario: Autonomous worker with native sandbox

- **Given**: A user with Claude sandbox configured (via `/sandbox` command)
- **When**: `swarm spawn --name agent --tmux --worktree -- claude --dangerously-skip-permissions`
- **Then**:
  - Worker starts successfully
  - Agent operates without permission prompts
  - Filesystem writes restricted to working directory
  - Network access restricted to allowed domains
  - Violations blocked at OS level

### Scenario: Autonomous worker in Docker sandbox

- **Given**: Docker Desktop 4.50+ with Sandboxes enabled
- **When**: `docker sandbox run --image claude-code -- swarm spawn --name agent --tmux -- claude --dangerously-skip-permissions`
- **Then**:
  - Worker runs inside isolated microVM
  - Complete filesystem and network isolation from host
  - Worker has its own Docker daemon
  - Host system protected from agent actions

### Scenario: Worker without permission bypass

- **Given**: A user forgetting the permission bypass flag
- **When**: `swarm spawn --name agent --tmux --worktree -- claude`
- **Then**:
  - Worker starts, Claude CLI launches
  - Agent prompts for first tool use
  - Worker stalls indefinitely waiting for input
  - No work is accomplished
  - User must kill worker and respawn with correct flag

### Scenario: Worker with restricted tools

- **Given**: A user wanting to limit agent to file operations only
- **When**: `swarm spawn --name agent --tmux --worktree -- claude --dangerously-skip-permissions --allowedTools "Edit Read Grep Glob"`
- **Then**:
  - Worker starts successfully
  - Agent can read and edit files
  - Agent cannot execute bash commands
  - Agent cannot make network requests (WebFetch disabled)

## Edge Cases

- **Sandbox + permission bypass**: Both flags work together. Sandbox provides isolation boundaries; permission bypass enables autonomous operation within those boundaries.
- **Nested sandboxes**: Running Docker sandbox inside native sandbox is not recommended; may cause conflicts.
- **WSL1**: Native sandbox requires WSL2. WSL1 users must use Docker sandboxing or no sandbox.
- **macOS**: Native sandbox uses Seatbelt, works out of the box without additional packages.
- **Linux**: Native sandbox requires `bubblewrap` and `socat` packages.
- **Domain fronting**: Network sandbox can potentially be bypassed via domain fronting on allowed domains; be conservative with domain allowlist.
- **Unix sockets**: Allowing unix sockets (especially docker.sock) can bypass sandbox; avoid unless necessary.

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

### Sandbox blocking legitimate operations

```bash
# Check Claude sandbox configuration
claude
> /sandbox  # Review current settings

# Add needed domain to allowlist
# Edit ~/.claude/settings.json or use /sandbox menu

# For incompatible commands, add to excludedCommands
# in sandbox settings
```

### Worker escaped sandbox (security incident)

```bash
# Stop all workers immediately
swarm kill --all

# Review what happened
swarm logs <compromised-worker> --history

# Check for unauthorized changes
git status
git diff

# If using Docker sandbox, destroy the container
docker sandbox rm <sandbox-name>

# Rotate any credentials that may have been exposed
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

### Sandbox Configuration Persistence

Claude's sandbox settings persist in `~/.claude/settings.json`. Workers inherit these settings. To configure sandbox:

1. Run `claude` interactively
2. Use `/sandbox` command to configure
3. Settings apply to all future Claude sessions, including swarm workers

### Docker Sandbox Images

The official Claude Code sandbox image is `claude-code-sandbox`. Custom images should:
- Have Claude Code installed
- Have swarm available (either installed or mounted)
- Not mount sensitive host paths (especially `~/.ssh`, `~/.aws`, `/var/run/docker.sock`)

### Security Model Comparison

| Approach | Filesystem | Network | Bash | Setup Effort |
|----------|------------|---------|------|--------------|
| No sandbox | Full access | Full access | Yes | None |
| Native sandbox | Working dir only | Allowed domains | Yes | Low (install bubblewrap) |
| Docker sandbox | Container only | Configurable | Yes | Medium (Docker Desktop) |
| Tool restriction | Full access | Configurable | No | None |
| Native + restriction | Working dir only | Allowed domains | No | Low |
