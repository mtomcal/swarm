# Send Command

## Overview

The `send` command transmits text input to tmux-based workers. This enables orchestration scripts to send prompts, commands, or any text input to running agent CLIs. The command supports sending to individual workers or broadcasting to all running tmux workers simultaneously.

## Dependencies

- **External**:
  - tmux (required for send functionality)
- **Internal**:
  - `state-management.md` (worker registry)
  - `tmux-integration.md` (tmux_send function)

## Behavior

### Worker Selection

**Description**: Determine which workers to send text to.

**Inputs**:
- `name` (str, optional): Worker name
- `--all` (flag, optional): Send to all tmux workers

**Behavior**:
1. If `--all`: select all workers with tmux info (regardless of status)
2. Else: look up single worker by name

**Error Conditions**:
| Condition | Behavior |
|-----------|----------|
| Neither name nor `--all` | Exit 1 with "swarm: error: --name required when not using --all" |
| Worker not found | Exit 1 with "swarm: error: worker '<name>' not found" |
| Worker is not tmux (single) | Exit 1 with "swarm: error: worker '<name>' is not a tmux worker" |

### Status Validation

**Description**: Check worker is running before sending.

**Behavior**:
1. Refresh worker status (check tmux window exists)
2. Validate worker is "running"

**Differences by Mode**:
- Single worker: Error if not running
- `--all` mode: Silently skip non-running workers

**Error Conditions**:
| Condition | Behavior |
|-----------|----------|
| Single worker not running | Exit 1 with "swarm: error: worker '<name>' is not running" |

### Text Transmission

**Description**: Send text to tmux window via send-keys.

**Inputs**:
- `text` (str, required): Text to send
- `--no-enter` (flag, optional): Don't append Enter key

**Behavior**:
1. Use `tmux send-keys -t <session>:<window> -l <text>` for literal text
2. Unless `--no-enter`, follow with `tmux send-keys -t <target> Enter`

**Side Effects**:
- Text appears in tmux window as if typed
- Enter key submits the text (unless `--no-enter`)

### Success Output

**Description**: Print confirmation for each successful send.

**Output**:
```
sent to <name>
```

## CLI Arguments

| Argument | Type | Required | Default | Description |
|----------|------|----------|---------|-------------|
| `name` | str | No* | - | Worker name |
| `text` | str | Yes | - | Text to send |
| `--no-enter` | flag | No | false | Don't append Enter key |
| `--all` | flag | No* | false | Send to all tmux workers |

*Either `name` or `--all` must be specified.

## Scenarios

### Scenario: Send text to single worker
- **Given**: Worker "agent1" running in tmux
- **When**: `swarm send agent1 "implement the login feature"`
- **Then**:
  - Text "implement the login feature" sent to tmux window
  - Enter key sent after text
  - Output: "sent to agent1"

### Scenario: Send without Enter
- **Given**: Worker "agent1" running in tmux
- **When**: `swarm send agent1 "partial text" --no-enter`
- **Then**:
  - Text "partial text" sent to tmux window
  - No Enter key appended
  - Output: "sent to agent1"

### Scenario: Broadcast to all workers
- **Given**: Workers "w1", "w2" (tmux, running), "w3" (process)
- **When**: `swarm send --all "sync now"`
- **Then**:
  - Text sent to w1 and w2
  - w3 skipped (not tmux)
  - Output: "sent to w1", "sent to w2"

### Scenario: Broadcast skips stopped workers
- **Given**: Workers "running1" (running), "stopped1" (stopped)
- **When**: `swarm send --all "prompt"`
- **Then**:
  - Text sent only to running1
  - stopped1 silently skipped
  - Output: "sent to running1"

### Scenario: Send to non-tmux worker fails
- **Given**: Worker "proc1" running as process (not tmux)
- **When**: `swarm send proc1 "text"`
- **Then**:
  - Exit code 1
  - Error: "swarm: error: worker 'proc1' is not a tmux worker"

### Scenario: Send to stopped worker fails
- **Given**: Worker "dead" with status "stopped"
- **When**: `swarm send dead "text"`
- **Then**:
  - Exit code 1
  - Error: "swarm: error: worker 'dead' is not running"

### Scenario: Send to nonexistent worker
- **Given**: No worker named "ghost"
- **When**: `swarm send ghost "text"`
- **Then**:
  - Exit code 1
  - Error: "swarm: error: worker 'ghost' not found"

### Scenario: Send without name or --all
- **Given**: Any state
- **When**: `swarm send "text"` (no worker specified)
- **Then**:
  - Exit code 1
  - Error: "swarm: error: --name required when not using --all"

### Scenario: Send with custom tmux socket
- **Given**: Worker "isolated" using socket "test-socket"
- **When**: `swarm send isolated "text"`
- **Then**:
  - Command uses: `tmux -L test-socket send-keys ...`

## Edge Cases

- Empty text string is valid and will be sent
- Text with special characters sent literally (using `-l` flag)
- Newlines in text are sent as-is (may cause multiple lines)
- Tab characters are sent as literal tabs
- Unicode text is supported
- Very long text is sent in a single send-keys call
- Quotes in text are handled correctly via literal mode

## Recovery Procedures

### Text not appearing in window
```bash
# Verify window exists
tmux list-windows -t <session>

# Check pane is responsive
swarm attach <name>
# Try typing manually
```

### Worker shows running but send fails
```bash
# Refresh status
swarm status <name>

# If actually stopped, clean and respawn
swarm kill <name>
swarm clean <name>
swarm spawn --name <name> --tmux -- <command>
```

### Partial text sent (no Enter)
```bash
# If you forgot --no-enter but wanted it, send escape to clear
swarm send <name> $'\x03'  # Ctrl-C to cancel current input

# If you used --no-enter but needed Enter
swarm send <name> "" # Send empty with Enter
```

## Implementation Notes

- **Literal mode**: Uses `tmux send-keys -l` to prevent interpretation of special keys
- **Enter as separate command**: Enter key sent as separate tmux command for reliability
- **Status refresh**: Status is refreshed before each send to ensure window still exists
- **Silent skip**: `--all` mode silently skips non-running workers for better orchestration
- **Socket support**: All tmux commands include socket parameter when worker was created with socket
