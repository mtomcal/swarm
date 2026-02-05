# Kill Command

## Overview

The `kill` command terminates running workers. It handles both tmux-based workers (by killing the tmux window) and process-based workers (using SIGTERM with SIGKILL fallback). The command supports killing individual workers by name or all workers at once. When combined with `--rm-worktree`, it can also clean up git worktrees with protection against accidental data loss.

## Dependencies

- **External**:
  - tmux (for killing tmux windows)
  - POSIX signals (SIGTERM, SIGKILL)
  - Filesystem access for worktree operations
- **Internal**:
  - `state-management.md` (worker registry)
  - `worktree-isolation.md` (worktree removal)
  - `tmux-integration.md` (window and session management)
  - `ralph-loop.md` (ralph state management)

## Behavior

### Worker Selection

**Description**: Determine which workers to kill based on arguments.

**Inputs**:
- `name` (str, optional): Worker name to kill
- `--all` (flag, optional): Kill all workers

**Behavior**:
1. If `--all`: select all workers in registry
2. Else: look up worker by name

**Error Conditions**:
| Condition | Behavior |
|-----------|----------|
| Neither name nor `--all` provided | Exit 1 with "swarm: error: must specify worker name or --all" |
| Worker name not found | Exit 1 with "swarm: error: worker '<name>' not found" |

### Tmux Worker Termination

**Description**: Kill a worker running in a tmux window.

**Behavior**:
1. Build tmux command prefix (with socket if specified)
2. Run `tmux kill-window -t <session>:<window>`
3. Check if other workers share the same session
4. If no other workers remain, queue session for cleanup

**Side Effects**:
- Tmux window is destroyed
- Process running in window receives SIGHUP
- Session may be destroyed if empty

### Process Worker Termination

**Description**: Kill a worker running as background process.

**Behavior** (Graceful Shutdown):
1. Send SIGTERM to process
2. Poll process status every 0.1 seconds for up to 5 seconds
3. If process still alive after 5 seconds, send SIGKILL

**Side Effects**:
- Process receives SIGTERM (or SIGKILL if unresponsive)
- Process terminates

**Error Conditions**:
| Condition | Behavior |
|-----------|----------|
| Process already dead | Silently continue (ProcessLookupError caught) |
| Permission denied | Raises PermissionError |

### Worktree Removal

**Description**: Optionally remove git worktree after killing worker.

**Inputs**:
- `--rm-worktree` (flag, optional): Remove associated worktree
- `--force-dirty` (flag, optional): Force removal even with uncommitted changes

**Behavior**:
1. If `--rm-worktree` and worker has worktree:
2. Call `remove_worktree(path, force=force_dirty)`
3. If removal fails, print warning but continue

**Output on Failure**:
```
swarm: warning: cannot remove worktree for '<name>': <message>
swarm: use --force-dirty to remove anyway
```

### Ralph State Cleanup

**Description**: Clean up ralph state when killing ralph workers with `--rm-worktree`.

**Behavior**:
1. If `--rm-worktree` and worker is a ralph worker (has `metadata.ralph == true`):
2. Delete ralph state directory at `~/.swarm/ralph/<name>/`
3. This removes `state.json`, `iterations.log`, and any other ralph-related files
4. If deletion fails, print warning but continue

**Rationale**: When removing a worktree, the user typically intends to start fresh. Leaving ralph state behind causes issues when respawning with different configuration (e.g., new timeout values persist from old state).

**Output on Failure**:
```
swarm: warning: cannot remove ralph state for '<name>': <message>
```

**Note**: Ralph state is only cleaned when `--rm-worktree` is specified. A simple `swarm kill <name>` preserves ralph state, allowing later resume or inspection.

### Session Cleanup

**Description**: Clean up tmux sessions left empty after killing workers.

**Behavior**:
1. After killing all requested workers
2. For each session that had workers killed:
3. If no remaining workers use that session (considering socket), kill session

**Note**: Session cleanup considers both session name AND socket - a session with socket "test" is different from one with no socket.

### State Update

**Description**: Update worker status and persist state.

**Behavior**:
1. Set each killed worker's status to "stopped"
2. Save state to disk

**Note**: Worker is NOT removed from state - it remains with status "stopped" until explicitly cleaned.

### Success Output

**Description**: Print confirmation for each killed worker.

**Output**:
```
killed <name>
```

## CLI Arguments

| Argument | Type | Required | Default | Description |
|----------|------|----------|---------|-------------|
| `name` | str | No* | - | Worker name to kill |
| `--all` | flag | No* | false | Kill all workers |
| `--rm-worktree` | flag | No | false | Remove git worktree |
| `--force-dirty` | flag | No | false | Force dirty worktree removal |

*Either `name` or `--all` must be specified.

## Scenarios

### Scenario: Kill single tmux worker
- **Given**: Worker "agent1" running in tmux session "swarm", window "agent1"
- **When**: `swarm kill agent1`
- **Then**:
  - Tmux command `kill-window -t swarm:agent1` executed
  - Worker status updated to "stopped"
  - Output: "killed agent1"

### Scenario: Kill single process worker
- **Given**: Worker "proc1" running with PID 12345
- **When**: `swarm kill proc1`
- **Then**:
  - SIGTERM sent to PID 12345
  - Waits up to 5 seconds for process to exit
  - Worker status updated to "stopped"
  - Output: "killed proc1"

### Scenario: Kill unresponsive process
- **Given**: Worker "stubborn" with process that ignores SIGTERM
- **When**: `swarm kill stubborn`
- **Then**:
  - SIGTERM sent
  - After 5 seconds, SIGKILL sent
  - Process forcefully terminated
  - Worker status updated to "stopped"

### Scenario: Kill all workers
- **Given**: Workers "w1", "w2", "w3" all running
- **When**: `swarm kill --all`
- **Then**:
  - All three workers terminated
  - Output: "killed w1", "killed w2", "killed w3"
  - All workers status = "stopped"

### Scenario: Kill with worktree removal (clean)
- **Given**: Worker "feature" with clean worktree at `/repo-worktrees/feature`
- **When**: `swarm kill feature --rm-worktree`
- **Then**:
  - Worker terminated
  - Worktree removed via `git worktree remove`
  - Output: "killed feature"

### Scenario: Kill with dirty worktree (no force)
- **Given**: Worker "dirty" with uncommitted changes in worktree
- **When**: `swarm kill dirty --rm-worktree`
- **Then**:
  - Worker terminated
  - Worktree NOT removed
  - Warning: "swarm: warning: cannot remove worktree for 'dirty': worktree has N uncommitted change(s)"
  - Worker status = "stopped"

### Scenario: Kill with dirty worktree (force)
- **Given**: Worker "dirty" with uncommitted changes in worktree
- **When**: `swarm kill dirty --rm-worktree --force-dirty`
- **Then**:
  - Worker terminated
  - Worktree removed (changes lost!)
  - Output: "killed dirty"

### Scenario: Kill ralph worker with worktree removal
- **Given**: Ralph worker "agent" with worktree at `/repo-worktrees/agent` and ralph state at `~/.swarm/ralph/agent/`
- **When**: `swarm kill agent --rm-worktree`
- **Then**:
  - Worker terminated
  - Worktree removed via `git worktree remove`
  - Ralph state directory `~/.swarm/ralph/agent/` deleted (including `state.json`, `iterations.log`)
  - Output: "killed agent"
  - Worker can now be respawned with fresh state

### Scenario: Kill ralph worker without --rm-worktree preserves state
- **Given**: Ralph worker "agent" with ralph state at `~/.swarm/ralph/agent/`
- **When**: `swarm kill agent`
- **Then**:
  - Worker terminated
  - Ralph state preserved at `~/.swarm/ralph/agent/`
  - Worker status updated to "stopped"
  - `swarm ralph resume agent` can continue the loop later

### Scenario: Kill nonexistent worker
- **Given**: No worker named "ghost"
- **When**: `swarm kill ghost`
- **Then**:
  - Exit code 1
  - Error: "swarm: error: worker 'ghost' not found"

### Scenario: Kill without name or --all
- **Given**: Any state
- **When**: `swarm kill` (no arguments)
- **Then**:
  - Exit code 1
  - Error: "swarm: error: must specify worker name or --all"

### Scenario: Kill already-dead process
- **Given**: Worker "zombie" with PID that no longer exists
- **When**: `swarm kill zombie`
- **Then**:
  - ProcessLookupError caught silently
  - Worker status updated to "stopped"
  - Output: "killed zombie"

### Scenario: Session cleanup after killing last worker
- **Given**: Workers "w1" and "w2" in same session "swarm", no other workers
- **When**: `swarm kill --all`
- **Then**:
  - Both workers killed
  - Session "swarm" is destroyed (via `tmux kill-session`)

### Scenario: Session preserved with remaining workers
- **Given**: Workers "w1" (tmux) and "w2" (tmux) in session "swarm", "w3" (process)
- **When**: `swarm kill w1`
- **Then**:
  - Window for "w1" killed
  - Session "swarm" preserved (w2 still using it)

### Scenario: Kill with custom tmux socket
- **Given**: Worker "isolated" using tmux socket "test-socket"
- **When**: `swarm kill isolated`
- **Then**:
  - Command: `tmux -L test-socket kill-window -t <session>:<window>`
  - Socket is preserved in command prefix

## Edge Cases

- Killing a worker that's already stopped still works (updates state, prints confirmation)
- Multiple workers in same session but different sockets are treated independently
- Session cleanup only happens after ALL requested workers are killed (not incrementally)
- Worktree removal failure is a warning, not an error (exit code still 0)
- Process termination timeout is 5 seconds (50 × 0.1s polls)
- SIGKILL is only sent if process is still alive after SIGTERM timeout
- Ralph state cleanup is tied to `--rm-worktree`, not to worktree existence (a ralph worker without worktree still gets ralph state cleaned with `--rm-worktree`)
- Ralph state cleanup failure is a warning, not an error (exit code still 0)
- When killing all workers with `--all --rm-worktree`, ralph state is cleaned for each ralph worker

## Recovery Procedures

### Worker killed but tmux window remains
```bash
# List windows
tmux list-windows -t <session>

# Manually kill window
tmux kill-window -t <session>:<window>
```

### Worker killed but process still running
```bash
# Find the process
ps aux | grep <command>

# Kill manually
kill -9 <pid>
```

### Orphaned worktree after kill
```bash
# Check git worktree status
git worktree list

# Remove manually
git worktree remove /path/to/worktree
# Or force if dirty
git worktree remove --force /path/to/worktree
```

### State shows worker as running but it's dead
```bash
# Status command refreshes
swarm status <name>

# Or list which refreshes all
swarm ls

# Then clean up
swarm clean <name>
```

### Ralph state persists after kill
```bash
# Option 1: Use --rm-worktree to clean everything
swarm kill <name> --rm-worktree

# Option 2: Use --clean-state on next spawn
swarm ralph spawn --name <name> --clean-state --prompt-file ./PROMPT.md --max-iterations 10 -- claude

# Option 3: Use --replace on next spawn
swarm ralph spawn --name <name> --replace --prompt-file ./PROMPT.md --max-iterations 10 -- claude

# Option 4: Manual cleanup
rm -rf ~/.swarm/ralph/<name>/
```

## Implementation Notes

- **Session tracking**: Uses set of (session, socket) tuples to track which sessions need cleanup
- **Graceful shutdown**: 5-second timeout for SIGTERM provides balance between responsiveness and allowing cleanup
- **Poll interval**: 0.1s polling during graceful shutdown provides quick detection of process exit
- **Worktree removal timing**: Worktree is removed AFTER process/window kill, ensuring no process is using it
- **State persistence**: Single save() call at end, after all workers processed
- **Status update**: Worker status changed to "stopped" even if process/window kill fails silently
