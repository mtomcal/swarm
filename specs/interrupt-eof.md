# Interrupt and EOF

## Overview

The `interrupt` and `eof` commands send control signals to tmux workers. `interrupt` sends Ctrl-C (interrupt/SIGINT) and `eof` sends Ctrl-D (end-of-file). These are essential for gracefully stopping running commands or signaling input completion within agent sessions.

## Dependencies

- **External**: tmux
- **Internal**: state-management.md, tmux-integration.md

## Behavior

### Interrupt (Ctrl-C)

**Description**: Send interrupt signal (Ctrl-C) to a tmux worker, typically to stop a running command.

**Inputs**:
- `name` (string, optional): Worker name to interrupt (required if not using `--all`)
- `--all` (flag, optional): Send interrupt to all running tmux workers

**Outputs**:
- Success: `interrupted <name>` for each worker
- Error: Error message and exit code 1

**Side Effects**:
- Sends `C-c` key sequence via `tmux send-keys`
- May terminate running processes in the worker's shell/agent

**Error Conditions (single worker mode)**:

| Condition | Behavior |
|-----------|----------|
| Name not provided (no --all) | Print `swarm: error: worker name required when not using --all` to stderr, exit 1 |
| Worker not found | Print `swarm: error: worker '<name>' not found` to stderr, exit 1 |
| Not a tmux worker | Print `swarm: error: worker '<name>' is not a tmux worker` to stderr, exit 1 |
| Worker not running | Print `swarm: error: worker '<name>' is not running` to stderr, exit 1 |

### EOF (Ctrl-D)

**Description**: Send end-of-file signal (Ctrl-D) to a tmux worker, typically to signal input completion or logout.

**Inputs**:
- `name` (string, required): Worker name to send EOF to

**Outputs**:
- Success: `sent eof to <name>`
- Error: Error message and exit code 1

**Side Effects**:
- Sends `C-d` key sequence via `tmux send-keys`
- May close stdin or trigger shell logout

**Error Conditions**:

| Condition | Behavior |
|-----------|----------|
| Worker not found | Print `swarm: error: worker '<name>' not found` to stderr, exit 1 |
| Not a tmux worker | Print `swarm: error: worker '<name>' is not a tmux worker` to stderr, exit 1 |
| Worker not running | Print `swarm: error: worker '<name>' is not running` to stderr, exit 1 |

## Implementation Details

### Tmux Send-Keys

Both commands use the tmux `send-keys` command with control character notation:

```bash
# Interrupt (Ctrl-C)
tmux send-keys -t <session>:<window> C-c

# EOF (Ctrl-D)
tmux send-keys -t <session>:<window> C-d
```

The `-t` flag specifies the target as `session:window` format.

### Socket Handling

Both commands respect the worker's tmux socket:
- If `worker.tmux.socket` is set, use `-L <socket>` flag
- Otherwise, use default tmux socket

## Scenarios

### Scenario: Interrupt single running worker
- **Given**: A running tmux worker "my-agent" executing a long command
- **When**: `swarm interrupt my-agent` is executed
- **Then**:
  - Ctrl-C sent to the worker's tmux window
  - Output: `interrupted my-agent`
  - Running command in worker receives SIGINT

### Scenario: Interrupt all running workers
- **Given**: Running tmux workers "agent-1", "agent-2", and stopped worker "done"
- **When**: `swarm interrupt --all` is executed
- **Then**:
  - Ctrl-C sent to "agent-1" and "agent-2"
  - Output: `interrupted agent-1` and `interrupted agent-2`
  - "done" is skipped (not running)

### Scenario: Interrupt --all with no running workers
- **Given**: All workers are stopped or non-tmux
- **When**: `swarm interrupt --all` is executed
- **Then**:
  - No output (nothing to interrupt)
  - Exit code is 0

### Scenario: Interrupt non-tmux worker
- **Given**: A running non-tmux (process) worker "bg-job"
- **When**: `swarm interrupt bg-job` is executed
- **Then**:
  - Error: `swarm: error: worker 'bg-job' is not a tmux worker`
  - Exit code is 1

### Scenario: Interrupt stopped worker
- **Given**: A stopped tmux worker "finished"
- **When**: `swarm interrupt finished` is executed
- **Then**:
  - Error: `swarm: error: worker 'finished' is not running`
  - Exit code is 1

### Scenario: Send EOF to worker
- **Given**: A running tmux worker "my-agent" waiting for input
- **When**: `swarm eof my-agent` is executed
- **Then**:
  - Ctrl-D sent to the worker's tmux window
  - Output: `sent eof to my-agent`

### Scenario: EOF to non-tmux worker
- **Given**: A running non-tmux worker "bg-job"
- **When**: `swarm eof bg-job` is executed
- **Then**:
  - Error: `swarm: error: worker 'bg-job' is not a tmux worker`
  - Exit code is 1

### Scenario: Worker not found
- **Given**: No worker named "ghost" in state
- **When**: `swarm interrupt ghost` is executed
- **Then**:
  - Error: `swarm: error: worker 'ghost' not found`
  - Exit code is 1

### Scenario: Interrupt without name or --all
- **Given**: Running workers exist
- **When**: `swarm interrupt` is executed without arguments
- **Then**:
  - Error: `swarm: error: worker name required when not using --all`
  - Exit code is 1

## Edge Cases

- **Worker running but tmux window killed externally**: Status refresh detects stopped state, error returned
- **Multiple Ctrl-C needed**: May need to run interrupt multiple times for some commands
- **EOF causes worker to exit**: Worker becomes "stopped" after Ctrl-D if it triggers logout
- **Interrupt during agent prompt**: Agent CLI may handle SIGINT gracefully or exit
- **Race condition with --all**: Workers are filtered before sending; if worker stops between filter and send, tmux command may fail silently

## Recovery Procedures

### Interrupt didn't stop the command
Some commands ignore SIGINT. Options:
1. Send interrupt again: `swarm interrupt <name>`
2. Send EOF: `swarm eof <name>`
3. Kill the worker: `swarm kill <name>`

### Worker exited unexpectedly after EOF
EOF can cause shells to exit. If this was unintended:
1. Check worker status: `swarm status <name>`
2. Respawn if needed: `swarm respawn <name>`

## Use Cases

### Stopping a Running Agent Task
```bash
# Agent is stuck or needs to be stopped
swarm interrupt my-agent
```

### Sending EOF to Complete Input
```bash
# Agent is waiting for input that you want to end
swarm eof my-agent
```

### Emergency Stop All Agents
```bash
# Stop whatever all agents are doing
swarm interrupt --all
```

## Implementation Notes

- `interrupt` supports `--all` flag; `eof` does not (intentional: EOF is more destructive)
- Status is refreshed via `refresh_worker_status()` before sending signal
- The `subprocess.run()` captures output but doesn't check return code (tmux send-keys may return non-zero if window doesn't exist)
- For `--all` mode, workers are filtered first, then signals sent; no partial failure handling
