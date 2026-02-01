# Clean

## Overview

The `clean` command removes stopped workers from state and cleans up associated resources (log files, worktrees, tmux sessions). It refuses to clean running workers to prevent accidental data loss.

## Dependencies

- **External**: tmux, git, filesystem
- **Internal**: state-management.md, worktree-isolation.md, tmux-integration.md

## Behavior

### Clean Stopped Worker(s)

**Description**: Remove stopped workers from state, delete their log files, and optionally remove worktrees.

**Inputs**:
- `name` (string, optional): Worker name to clean (required if not using `--all`)
- `--all` (flag, optional): Clean all stopped workers
- `--rm-worktree` (flag, default: true): Remove git worktree if exists
- `--force-dirty` (flag, optional): Force removal of worktree even with uncommitted changes

**Outputs**:
- Success: Prints `cleaned <name>` for each cleaned worker
- Partial success (--all with running workers): Warning printed, running workers skipped
- Error: Error message and exit code 1

**Side Effects**:
- Removes worker entry from `~/.swarm/state.json`
- Deletes `~/.swarm/logs/<name>.stdout.log` if exists
- Deletes `~/.swarm/logs/<name>.stderr.log` if exists
- Removes git worktree if `--rm-worktree` (runs `git worktree remove`)
- Kills empty tmux sessions (sessions with no remaining windows)
- Refreshes and updates worker status in state before filtering (`--all` mode)

**Error Conditions**:

| Condition | Behavior |
|-----------|----------|
| Neither name nor `--all` provided | Print `swarm: error: must specify worker name or use --all` to stderr, exit 1 |
| Worker not found | Print `swarm: error: worker '<name>' not found` to stderr, exit 1 |
| Worker is running (single) | Print `swarm: error: cannot clean running worker '<name>'` to stderr, exit 1 |
| Worker is running (--all) | Print warning `swarm: warning: skipping '<name>' (still running)`, continue |
| Dirty worktree without --force-dirty | Print warning, preserve worktree, continue with state cleanup |

## Algorithm

1. Determine workers to clean:
   - If `--all`: Refresh all worker statuses, filter to those with status "stopped"
   - If single name: Look up by name
2. For each worker to clean:
   a. Refresh actual status (second check)
   b. If still running: error (single) or skip with warning (--all)
   c. Track tmux session for cleanup if no other workers use it
   d. If worktree exists and `--rm-worktree`:
      - Call `remove_worktree()` with `force=args.force_dirty`
      - On failure: Print warning, preserve worktree, continue
   e. Delete log files if they exist
   f. Remove worker from state
   g. Print success message
3. Kill empty tmux sessions (sessions with no remaining windows)

## Scenarios

### Scenario: Clean single stopped worker
- **Given**: A stopped worker named "finished-worker"
- **When**: `swarm clean finished-worker` is executed
- **Then**:
  - Worker removed from state
  - Log files deleted
  - Output: `cleaned finished-worker`
  - Exit code is 0

### Scenario: Clean all stopped workers
- **Given**: Stopped workers "done-1" and "done-2", running worker "active"
- **When**: `swarm clean --all` is executed
- **Then**:
  - "done-1" and "done-2" removed from state
  - "active" remains in state
  - Output: `cleaned done-1` and `cleaned done-2`
  - Exit code is 0

### Scenario: Attempt to clean running worker
- **Given**: A running worker named "busy-worker"
- **When**: `swarm clean busy-worker` is executed
- **Then**:
  - Error: `swarm: error: cannot clean running worker 'busy-worker'`
  - Exit code is 1
  - Worker remains in state

### Scenario: Clean worker with worktree
- **Given**: Stopped worker "wt-worker" with clean worktree at `<repo>-worktrees/wt-worker`
- **When**: `swarm clean wt-worker` is executed
- **Then**:
  - Worker removed from state
  - Worktree removed via `git worktree remove`
  - Output: `cleaned wt-worker`

### Scenario: Clean worker with dirty worktree
- **Given**: Stopped worker "dirty-worker" with uncommitted changes in worktree
- **When**: `swarm clean dirty-worker` is executed
- **Then**:
  - Worker removed from state
  - Worktree preserved (not deleted)
  - Warning: `swarm: warning: preserving worktree for 'dirty-worker': <reason>`
  - Warning: `swarm: worktree at: <path>`
  - Warning: `swarm: use --force-dirty to remove anyway`
  - Exit code is 0

### Scenario: Force clean dirty worktree
- **Given**: Stopped worker "dirty-worker" with uncommitted changes
- **When**: `swarm clean dirty-worker --force-dirty` is executed
- **Then**:
  - Worker removed from state
  - Worktree forcibly removed (uncommitted changes lost)
  - Output: `cleaned dirty-worker`

### Scenario: Clean worker without worktree flag
- **Given**: Stopped worker "keep-wt" with worktree
- **When**: `swarm clean keep-wt --rm-worktree=false` is executed
- **Then**:
  - Worker removed from state
  - Worktree preserved (not removed)
  - Log files deleted
  - Output: `cleaned keep-wt`

### Scenario: Worker not found
- **Given**: No worker named "nonexistent" in state
- **When**: `swarm clean nonexistent` is executed
- **Then**:
  - Error: `swarm: error: worker 'nonexistent' not found`
  - Exit code is 1

### Scenario: Clean called without name or --all
- **Given**: Workers exist in state
- **When**: `swarm clean` is executed without arguments
- **Then**:
  - Error: `swarm: error: must specify worker name or use --all`
  - Exit code is 1

### Scenario: Clean triggers tmux session cleanup
- **Given**: Stopped worker "last-worker" is the only worker in tmux session "swarm-abc123"
- **When**: `swarm clean last-worker` is executed
- **Then**:
  - Worker removed from state
  - Tmux session "swarm-abc123" killed (no remaining windows)

### Scenario: Clean does not kill shared tmux session
- **Given**: Stopped "done-1" and running "active" in same tmux session
- **When**: `swarm clean done-1` is executed
- **Then**:
  - "done-1" removed from state
  - Tmux session preserved (still has "active")

### Scenario: Clean --all refreshes status before filtering
- **Given**: Worker "stale" with cached status "running" but actually stopped
- **When**: `swarm clean --all` is executed
- **Then**:
  - Status refreshed to "stopped"
  - Worker cleaned (not skipped)
  - State updated with actual status

## Edge Cases

- **Missing log files**: Silently skipped (no error if files don't exist)
- **Worktree directory already deleted**: `remove_worktree()` called but may be no-op
- **Worker becomes running during clean --all**: Detected on second refresh, skipped with warning
- **Empty state after clean**: Valid state with empty workers array
- **Concurrent clean calls**: Protected by state file locking (fcntl)

## Recovery Procedures

### Orphaned worktree (state cleaned but worktree remains)
```bash
# Find orphaned worktrees
git worktree list

# Remove manually
git worktree remove <path> --force
```

### Orphaned log files
```bash
# Clean up log files for non-existent workers
ls ~/.swarm/logs/
rm ~/.swarm/logs/<orphan>.stdout.log
rm ~/.swarm/logs/<orphan>.stderr.log
```

### Empty tmux session left behind
```bash
# List sessions
tmux list-sessions

# Kill empty session
tmux kill-session -t <session-name>
```

## Implementation Notes

- Status is refreshed twice in `--all` mode: once for filtering, once for each worker during cleanup
- `--rm-worktree` defaults to True in the CLI parser
- Worktree removal failures produce warnings but don't fail the clean operation
- Session cleanup happens after all workers are processed to correctly handle batch operations
- The state save happens per-worker removal via `state.remove_worker()`
