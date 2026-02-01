# Attach

## Overview

The `attach` command provides interactive access to a tmux worker's terminal. It selects the worker's window and attaches to its tmux session, giving the user full control of the worker's terminal.

## Dependencies

- **External**: tmux
- **Internal**: state-management.md, tmux-integration.md

## Behavior

### Attach to Worker

**Description**: Attach to a tmux worker's session for interactive control.

**Inputs**:
- `name` (string, required): Worker name to attach to

**Outputs**:
- Success: User is attached to tmux session (replaces current process)
- Error: Error message and exit code 1

**Side Effects**:
- Selects the worker's tmux window (`tmux select-window`)
- Replaces current process with tmux attach (`os.execvp`)
- Terminal is now controlled by tmux session

**Error Conditions**:

| Condition | Behavior |
|-----------|----------|
| Worker not found | Print `swarm: error: worker '<name>' not found` to stderr, exit 1 |
| Not a tmux worker | Print `swarm: error: worker '<name>' is not a tmux worker` to stderr, exit 1 |

## Implementation Details

### Two-Step Attachment

1. **Select Window**: First, select the worker's window within the session
   ```bash
   tmux select-window -t <session>:<window>
   ```

2. **Attach Session**: Then attach to the session (replaces current process)
   ```bash
   tmux attach-session -t <session>
   # Or with socket:
   tmux -L <socket> attach-session -t <session>
   ```

### Process Replacement

The attach command uses `os.execvp()` to replace the swarm process with tmux. This means:
- Control returns to tmux, not to swarm
- User must detach from tmux to return to their shell
- Any code after `execvp` never runs

### Socket Handling

If the worker has a custom tmux socket:
```python
os.execvp("tmux", ["tmux", "-L", socket, "attach-session", "-t", session])
```

Otherwise, use default socket:
```python
os.execvp("tmux", ["tmux", "attach-session", "-t", session])
```

## Scenarios

### Scenario: Attach to running tmux worker
- **Given**: A running tmux worker "my-agent" in session "swarm-abc"
- **When**: `swarm attach my-agent` is executed
- **Then**:
  - Window "my-agent" is selected in session "swarm-abc"
  - User is attached to the tmux session
  - Terminal shows the agent's interface

### Scenario: Attach to stopped tmux worker
- **Given**: A stopped tmux worker "finished-agent" (window still exists)
- **When**: `swarm attach finished-agent` is executed
- **Then**:
  - Window is selected and session is attached
  - User sees the stopped state of the worker
  - (Note: attach doesn't check worker status, only tmux info)

### Scenario: Attach to non-tmux worker
- **Given**: A non-tmux (process) worker "bg-job"
- **When**: `swarm attach bg-job` is executed
- **Then**:
  - Error: `swarm: error: worker 'bg-job' is not a tmux worker`
  - Exit code is 1

### Scenario: Worker not found
- **Given**: No worker named "ghost" in state
- **When**: `swarm attach ghost` is executed
- **Then**:
  - Error: `swarm: error: worker 'ghost' not found`
  - Exit code is 1

### Scenario: Attach to worker with custom socket
- **Given**: A tmux worker "isolated" with socket "test-socket"
- **When**: `swarm attach isolated` is executed
- **Then**:
  - Attach uses `-L test-socket` flag
  - User is attached to the isolated session

### Scenario: Session with multiple workers
- **Given**: Multiple workers in session "swarm-abc": "worker-1", "worker-2"
- **When**: `swarm attach worker-2` is executed
- **Then**:
  - Window "worker-2" is selected (switched to)
  - User is attached to session "swarm-abc"
  - User can navigate between windows within the session

## Edge Cases

- **Tmux window was killed externally**: `select-window` may fail silently or show error
- **Session doesn't exist**: `attach-session` will fail and tmux will print error
- **Already inside tmux**: Creates nested tmux session (usually not desired)
- **Worker status not checked**: Attach works as long as tmux info exists, regardless of worker status

## Recovery Procedures

### Detaching from tmux
Once attached, detach with:
- `Ctrl-b d` (default tmux detach)
- Or configure custom tmux prefix key

### Nested tmux session
If accidentally created nested tmux:
1. Detach inner: `Ctrl-b d`
2. Or kill inner: `Ctrl-b : kill-session`

### Can't find worker's window
If attached but window is missing:
```bash
# List windows in current session
Ctrl-b w

# Or from command mode
Ctrl-b :list-windows
```

### Session doesn't exist
If session was killed but worker still in state:
```bash
# Check actual tmux sessions
tmux list-sessions

# Clean up stale worker
swarm clean <name>
```

## Use Cases

### Interactive Debugging
```bash
# Attach to see what the agent is doing
swarm attach my-agent

# Once attached, can interact with the agent directly
# Detach with Ctrl-b d when done
```

### Monitoring Multiple Workers
```bash
# Attach to session with multiple workers
swarm attach worker-1

# Once in tmux, navigate between windows:
# Ctrl-b n (next window)
# Ctrl-b p (previous window)
# Ctrl-b <number> (jump to window number)
```

### Resuming After Disconnect
```bash
# Network disconnected while working with agent
# Simply re-attach to resume
swarm attach my-agent
```

## Implementation Notes

- `select-window` is called first to ensure correct window is active on attach
- `select-window` uses `check=True` which will raise on failure
- `execvp` replaces the process, so no cleanup code runs after attach
- The command intentionally doesn't validate worker status (running vs stopped) because the tmux window may still exist even if the worker's process has exited
- For isolated testing with custom sockets, the socket is passed to both `select-window` and `attach-session`
