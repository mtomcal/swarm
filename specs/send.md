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

**Description**: Send text to tmux window via send-keys, with input clearing to handle autocomplete and pending input.

**Inputs**:
- `text` (str, required): Text to send
- `--no-enter` (flag, optional): Don't append Enter key
- `--raw` (flag, optional): Skip pre-clear sequence, send text directly via bare `send-keys` (for non-interactive or non-CLI targets)

**Default Behavior** (pre-clear sequence):
1. Send `Escape` to dismiss autocomplete dropdowns or cancel partial operations
2. Send `Ctrl-U` to clear any pending input on the current line
3. Use `tmux send-keys -t <session>:<window> -l <text>` for literal text
4. Unless `--no-enter`, follow with `tmux send-keys -t <target> Enter`

**Raw Mode** (`--raw`):
1. Use `tmux send-keys -t <session>:<window> -l <text>` for literal text (no pre-clear)
2. Unless `--no-enter`, follow with `tmux send-keys -t <target> Enter`

**Why Pre-Clear is Default**: Agent CLIs like Claude Code have autocomplete dropdowns that intercept slash commands (e.g., `/exit` triggers a menu). Without clearing first, the Enter key may select from the autocomplete menu instead of submitting the intended text. The Escape + Ctrl-U sequence reliably dismisses autocomplete and clears any partial input before typing the new text.

**Side Effects**:
- Text appears in tmux window as if typed
- Enter key submits the text (unless `--no-enter`)
- Any previously pending input is cleared (unless `--raw`)

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
| `--raw` | flag | No | false | Skip pre-clear sequence (Escape + Ctrl-U). Use for non-CLI targets or when pre-clearing is undesirable. |
| `--all` | flag | No* | false | Send to all tmux workers |

*Either `name` or `--all` must be specified.

## Scenarios

### Scenario: Send text to single worker (default pre-clear)
- **Given**: Worker "agent1" running in tmux
- **When**: `swarm send agent1 "implement the login feature"`
- **Then**:
  - Escape sent (dismiss autocomplete)
  - Ctrl-U sent (clear pending input)
  - Text "implement the login feature" sent to tmux window
  - Enter key sent after text
  - Output: "sent to agent1"

### Scenario: Send in raw mode (no pre-clear)
- **Given**: Worker "agent1" running in tmux
- **When**: `swarm send agent1 "text" --raw`
- **Then**:
  - Text "text" sent directly via send-keys (no Escape, no Ctrl-U)
  - Enter key sent after text
  - Output: "sent to agent1"

### Scenario: Send without Enter
- **Given**: Worker "agent1" running in tmux
- **When**: `swarm send agent1 "partial text" --no-enter`
- **Then**:
  - Escape and Ctrl-U sent first (pre-clear)
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

### Scenario: Steering a mid-generation agent
- **Given**: Worker "agent1" is actively generating output (mid-response)
- **When**: Director wants to redirect the agent
- **Then**:
  - Use `swarm interrupt agent1` first (sends Ctrl-C to stop generation)
  - Then `swarm send agent1 "try a different approach using X"`
  - The pre-clear sequence in send handles any leftover input state

## Edge Cases

- Empty text string is valid and will be sent (pre-clear still runs unless `--raw`)
- Text with special characters sent literally (using `-l` flag)
- Newlines in text are sent as-is (may cause multiple lines)
- Tab characters are sent as literal tabs
- Unicode text is supported
- Very long text is sent in a single send-keys call
- Quotes in text are handled correctly via literal mode
- Pre-clear sequence (Escape + Ctrl-U) is harmless if no autocomplete is active
- `--raw` combined with `--no-enter` sends bare text only (no pre-clear, no Enter)

## Recovery Procedures

### Text not appearing in window
```bash
# Verify window exists
tmux list-windows -t <session>

# Check pane is responsive
swarm attach <name>
# Try typing manually
```

### Agent ignoring sent text (mid-generation)
```bash
# The agent may be generating output and not reading input
# Interrupt first, then send
swarm interrupt <name>
swarm send <name> "your new instructions"
```

### Autocomplete eating slash commands
```bash
# This should not happen with the default pre-clear sequence
# If it persists, the Escape key may not be dismissing the menu
# Try interrupt + send pattern instead:
swarm interrupt <name>
swarm send <name> "/exit"
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
swarm interrupt <name>  # Ctrl-C to cancel

# If you used --no-enter but needed Enter
swarm send <name> "" # Send empty with Enter
```

## Implementation Notes

- **Pre-clear sequence**: Default sends Escape → Ctrl-U before text. This prevents autocomplete menus from intercepting slash commands and clears any stale input.
- **Escape key**: Sent as `tmux send-keys Escape` (not literal mode). Dismisses autocomplete dropdowns in Claude Code and similar agent CLIs.
- **Ctrl-U**: Sent as `tmux send-keys C-u` (not literal mode). Clears the current input line.
- **Literal mode**: Text itself uses `tmux send-keys -l` to prevent interpretation of special keys.
- **Enter as separate command**: Enter key sent as separate tmux command for reliability.
- **Raw mode**: `--raw` skips Escape + Ctrl-U, sending only the literal text + Enter. Use for non-CLI targets (plain bash shells, scripts) where pre-clear may have side effects.
- **Status refresh**: Status is refreshed before each send to ensure window still exists.
- **Silent skip**: `--all` mode silently skips non-running workers for better orchestration.
- **Socket support**: All tmux commands include socket parameter when worker was created with socket.
