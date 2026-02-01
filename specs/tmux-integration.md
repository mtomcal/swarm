# Tmux Integration

## Overview

Swarm provides deep tmux integration for running workers in persistent terminal sessions. This enables interactive debugging, log viewing via pane capture, and graceful input handling for agent CLIs. Swarm uses session isolation via hash-based naming to prevent conflicts between users and supports custom sockets for testing isolation.

## Dependencies

- **External**:
  - tmux (required)
  - hashlib (standard library, for session name generation)
- **Internal**:
  - `state-management.md` (TmuxInfo storage)

## Behavior

### Default Session Name Generation

**Description**: Generate isolated session name using hash of SWARM_DIR.

**Algorithm**:
1. Get resolved absolute path of `~/.swarm`
2. Compute SHA-256 hash of path string
3. Take first 8 characters of hex digest
4. Return `swarm-<hash>`

**Example**:
```
SWARM_DIR: /home/user/.swarm
Hash: sha256("/home/user/.swarm") = "a1b2c3d4..."
Session name: "swarm-a1b2c3d4"
```

**Purpose**: Different users (different home directories) get different session names, preventing conflicts when multiple users run swarm on the same system.

### Socket Isolation

**Description**: Optional tmux socket for complete server isolation.

**Inputs**:
- `socket` (str, optional): Tmux socket name

**Behavior**:
- If socket specified: use `tmux -L <socket> ...` prefix for all commands
- If not specified: use default tmux server

**Use Cases**:
- Testing: Each test gets unique socket for parallel execution
- Isolation: Completely separate tmux server from user's sessions

### Tmux Command Prefix

**Description**: Build command prefix with optional socket.

**Inputs**:
- `socket` (str, optional): Socket name

**Outputs**:
- Without socket: `["tmux"]`
- With socket: `["tmux", "-L", socket]`

### Session Management

#### Ensure Session Exists

**Description**: Create tmux session if it doesn't already exist.

**Inputs**:
- `session` (str, required): Session name
- `socket` (str, optional): Tmux socket

**Behavior**:
1. Run `tmux has-session -t <session>` to check existence
2. If returncode != 0: create with `tmux new-session -d -s <session>`

**Side Effects**:
- Creates detached session if it doesn't exist
- Idempotent: safe to call multiple times

#### Kill Session

**Description**: Terminate a tmux session.

**Inputs**:
- `session` (str, required): Session name
- `socket` (str, optional): Tmux socket

**Behavior**:
- Run `tmux kill-session -t <session>`
- Does not check for errors (session may already be gone)

### Window Management

#### Create Window

**Description**: Create a new window in a session and run command.

**Inputs**:
- `session` (str, required): Session name
- `window` (str, required): Window name (typically worker name)
- `cwd` (Path, required): Working directory
- `cmd` (list[str], required): Command to execute
- `socket` (str, optional): Tmux socket

**Behavior**:
1. Ensure session exists (creates if needed)
2. Build command string with proper shell quoting
3. Create window with: `tmux new-window -a -t <session> -n <window> -c <cwd> <cmd>`

**Flags Used**:
- `-a`: Append after current window (avoids base-index conflicts)
- `-t`: Target session
- `-n`: Window name
- `-c`: Working directory for the window

**Side Effects**:
- Creates new window in session
- Runs command in window
- Command inherits cwd as working directory

#### Check Window Exists

**Description**: Check if a tmux window exists.

**Inputs**:
- `session` (str): Session name
- `window` (str): Window name
- `socket` (str, optional): Tmux socket

**Outputs**:
- `True`: Window exists
- `False`: Window does not exist

**Implementation**:
```bash
tmux has-session -t <session>:<window>
# returncode 0 = exists, non-zero = doesn't exist
```

### Text Input

#### Send Keys

**Description**: Send text to a tmux window.

**Inputs**:
- `session` (str, required): Session name
- `window` (str, required): Window name
- `text` (str, required): Text to send
- `enter` (bool, optional): Append Enter key (default: True)
- `socket` (str, optional): Tmux socket

**Behavior**:
1. Build target: `<session>:<window>`
2. Send text: `tmux send-keys -t <target> -l <text>`
3. If enter: `tmux send-keys -t <target> Enter`

**Flags Used**:
- `-t`: Target window
- `-l`: Literal mode (send text as-is, no key interpretation)

**Note**: Enter is sent as separate command for reliability.

### Pane Capture

#### Capture Pane Content

**Description**: Capture visible or scrollback content from a pane.

**Inputs**:
- `session` (str, required): Session name
- `window` (str, required): Window name
- `history_lines` (int, optional): Lines of scrollback to include (default: 0 = visible only)
- `socket` (str, optional): Tmux socket

**Outputs**:
- String containing pane content

**Behavior**:
1. Build target: `<session>:<window>`
2. Run: `tmux capture-pane -t <target> -p [-S -<history_lines>]`
3. Return stdout

**Flags Used**:
- `-t`: Target pane
- `-p`: Print to stdout (instead of paste buffer)
- `-S -N`: Start capture N lines before visible (scrollback)

### Session Cleanup Logic

#### Check Other Workers in Session

**Description**: Determine if other workers share the same tmux session.

**Inputs**:
- `state` (State): Current swarm state
- `session` (str): Session name to check
- `exclude_worker` (str): Worker to exclude from check
- `socket` (str, optional): Socket name (must match)

**Outputs**:
- `True`: Other workers exist in same session+socket
- `False`: No other workers in session+socket

**Use Case**: After killing a worker, determine if the session should be cleaned up.

**Important**: Both session AND socket must match. A session "swarm-abc" with socket "test" is different from "swarm-abc" with no socket.

## TmuxInfo Schema

Stored in worker record:

```json
{
  "session": "swarm-a1b2c3d4",
  "window": "worker-name",
  "socket": "test-socket" | null
}
```

## Scenarios

### Scenario: Create window in new session
- **Given**: No session named "swarm-abc123" exists
- **When**: `create_tmux_window("swarm-abc123", "worker1", "/tmp", ["bash"])`
- **Then**:
  - Session "swarm-abc123" created (detached)
  - Window "worker1" created in session
  - "bash" running in window

### Scenario: Create window in existing session
- **Given**: Session "swarm-abc123" already exists with window "old"
- **When**: `create_tmux_window("swarm-abc123", "worker2", "/tmp", ["bash"])`
- **Then**:
  - No new session created
  - Window "worker2" added to existing session
  - Original window "old" unchanged

### Scenario: Send text with Enter
- **Given**: Window "worker1" running agent CLI
- **When**: `tmux_send("swarm", "worker1", "implement feature X")`
- **Then**:
  - Text "implement feature X" appears in pane
  - Enter key pressed, submitting input

### Scenario: Send text without Enter
- **Given**: Window "worker1" running
- **When**: `tmux_send("swarm", "worker1", "partial", enter=False)`
- **Then**:
  - Text "partial" appears in pane
  - No Enter pressed, cursor remains on same line

### Scenario: Capture visible pane content
- **Given**: Window with output "line1\nline2\nline3"
- **When**: `tmux_capture_pane("swarm", "worker1")`
- **Then**:
  - Returns "line1\nline2\nline3\n"

### Scenario: Capture with scrollback
- **Given**: Window with 500 lines scrolled off
- **When**: `tmux_capture_pane("swarm", "worker1", history_lines=1000)`
- **Then**:
  - Returns visible content plus up to 1000 lines of scrollback

### Scenario: Check window exists (true)
- **Given**: Window "worker1" in session "swarm"
- **When**: `tmux_window_exists("swarm", "worker1")`
- **Then**: Returns `True`

### Scenario: Check window exists (false)
- **Given**: Window "worker1" was killed
- **When**: `tmux_window_exists("swarm", "worker1")`
- **Then**: Returns `False`

### Scenario: Kill session after last worker
- **Given**: Session "swarm-abc" with single worker "w1"
- **When**: Worker "w1" killed, no other workers in session
- **Then**:
  - `session_has_other_workers()` returns False
  - Session "swarm-abc" killed

### Scenario: Preserve session with remaining workers
- **Given**: Session "swarm-abc" with workers "w1" and "w2"
- **When**: Worker "w1" killed
- **Then**:
  - `session_has_other_workers()` returns True
  - Session "swarm-abc" preserved

### Scenario: Socket isolation
- **Given**: Workers in default server and socket "test"
- **When**: Operations on socket "test" workers
- **Then**:
  - All commands use `tmux -L test ...`
  - Default server sessions unaffected

### Scenario: User session isolation
- **Given**: User has session "my-dev" with windows
- **When**: `swarm spawn --tmux -- claude`
- **Then**:
  - New session "swarm-<hash>" created
  - User's "my-dev" session completely unmodified

## Edge Cases

- Window names can contain alphanumeric and dash/underscore characters
- Session names are limited to valid tmux session name characters
- Hash collision in session name is extremely unlikely (8 hex chars = 4 billion combinations)
- Empty pane capture returns empty string (not error)
- Capture on non-existent window raises CalledProcessError
- Send to non-existent window raises CalledProcessError
- Multiple workers in same session use separate windows
- base-index tmux setting doesn't affect window creation (uses `-a` flag)

## Recovery Procedures

### Orphaned sessions
```bash
# List all swarm sessions
tmux list-sessions | grep '^swarm-'

# Kill specific session
tmux kill-session -t swarm-abc123

# Kill all swarm sessions
tmux list-sessions | grep '^swarm-' | cut -d: -f1 | xargs -I{} tmux kill-session -t {}
```

### Worker state shows running but window gone
```bash
# Refresh status via ls
swarm ls

# Clean stopped workers
swarm clean --all
```

### Tmux server crashed
```bash
# All workers will show as stopped on next ls
swarm ls

# Clean and respawn
swarm clean --all
# Manually respawn needed workers
```

### Custom socket cleanup
```bash
# Kill entire tmux server for socket
tmux -L <socket> kill-server
```

## Implementation Notes

- **Shell quoting**: Commands are shell-quoted with `shlex.quote()` to prevent injection
- **Literal send-keys**: Uses `-l` flag to prevent interpretation of special keys
- **Detached sessions**: Sessions created with `-d` to avoid stealing terminal
- **Append windows**: Uses `-a` flag to avoid conflicts with `base-index` setting
- **No ANSI stripping**: Capture returns raw output including ANSI escape codes
- **Error handling**: Most tmux command failures are caught and handled gracefully
- **Status refresh**: Window existence check is fast (single tmux command)
