# Respawn

## Overview

The `respawn` command restarts a dead worker using its original configuration (command, environment, tags, working directory, etc.). It can optionally clean the existing worktree before respawning. If the worker is still running, it will be killed first.

## Dependencies

- **External**: tmux, git, filesystem, signal handling
- **Internal**: state-management.md, worktree-isolation.md, tmux-integration.md, spawn.md

## Behavior

### Respawn Worker

**Description**: Restart a worker using its stored configuration, preserving command, env, tags, cwd, and worktree settings.

**Inputs**:
- `name` (string, required): Worker name to respawn
- `--clean-first` (flag, optional): Remove existing worktree before respawning
- `--force-dirty` (flag, optional): Force worktree removal even with uncommitted changes (requires `--clean-first`)

**Outputs**:
- Success (tmux): `respawned <name> (tmux: <session>:<window>)`
- Success (process): `respawned <name> (pid: <pid>)`
- Error: Error message and exit code 1

**Side Effects**:
- Kills existing worker if still running (tmux kill-window or SIGTERM/SIGKILL)
- Removes old worktree if `--clean-first` is set
- Creates new worktree if needed
- Creates new tmux window or spawns background process
- Updates state with new worker entry (removes old, adds new)
- Preserves original: cmd, cwd, env, tags, tmux session, worktree config

**Error Conditions**:

| Condition | Behavior |
|-----------|----------|
| Worker not found | Print `swarm: error: worker '<name>' not found` to stderr, exit 1 |
| Worktree removal fails (dirty, no --force-dirty) | Print error with path and suggestion, exit 1 |
| Worktree creation fails | Print `swarm: error: failed to create worktree: <error>` to stderr, exit 1 |
| Tmux window creation fails | Print `swarm: error: failed to create tmux window: <error>` to stderr, exit 1 |
| Process spawn fails | Print `swarm: error: failed to spawn process: <error>` to stderr, exit 1 |

## Algorithm

1. Look up worker by name
2. Refresh and check current status
3. If running, kill the worker:
   - Tmux: `kill-window`
   - Process: SIGTERM, wait up to 5 seconds, then SIGKILL if needed
4. If `--clean-first` and worktree exists:
   - Call `remove_worktree()` with `force=args.force_dirty`
   - On failure: Print error and exit 1
5. Store original configuration before removing from state:
   - cmd, cwd, env, tags, tmux, worktree
6. Remove old worker from state
7. Recreate worktree if needed:
   - If `--clean-first` or worktree doesn't exist: Call `create_worktree()`
   - If worktree exists: Reuse existing path
8. Spawn worker:
   - If tmux: Create new window in original session
   - If process: Spawn background process with original config
9. Create new Worker object with:
   - Original cmd, env, tags
   - New started timestamp
   - New pid or tmux info
   - Preserved worktree info
10. Add to state and print success

## Configuration Preservation

The following configuration is preserved across respawn:

| Field | Preserved? | Notes |
|-------|------------|-------|
| `cmd` | Yes | Full command with arguments |
| `cwd` | Yes | Working directory (updated if worktree recreated) |
| `env` | Yes | All environment variables |
| `tags` | Yes | All tags |
| `tmux.session` | Yes | Same session used for new window |
| `tmux.window` | Yes | Window name = worker name |
| `tmux.socket` | Yes | Same socket for isolation |
| `worktree.path` | Yes | Same path used |
| `worktree.branch` | Yes | Same branch name |
| `worktree.base_repo` | Yes | Same base repo |
| `started` | No | Updated to current timestamp |
| `status` | No | Set to "running" |
| `pid` | No | New PID assigned |

## Scenarios

### Scenario: Respawn stopped process worker
- **Given**: A stopped non-tmux worker "bg-worker" with original command `["python", "script.py"]`
- **When**: `swarm respawn bg-worker` is executed
- **Then**:
  - New process spawned with same command
  - Same env, tags, cwd preserved
  - Output: `respawned bg-worker (pid: <new-pid>)`
  - State updated with new PID and "running" status

### Scenario: Respawn stopped tmux worker
- **Given**: A stopped tmux worker "cli-agent" in session "swarm-abc"
- **When**: `swarm respawn cli-agent` is executed
- **Then**:
  - New tmux window created in same session
  - Same command executed in window
  - Output: `respawned cli-agent (tmux: swarm-abc:cli-agent)`

### Scenario: Respawn still-running worker
- **Given**: A running tmux worker "busy-worker"
- **When**: `swarm respawn busy-worker` is executed
- **Then**:
  - Existing window killed first
  - New window created
  - Output: `respawned busy-worker (tmux: <session>:<window>)`

### Scenario: Respawn running process worker
- **Given**: A running non-tmux worker with PID 12345
- **When**: `swarm respawn process-worker` is executed
- **Then**:
  - SIGTERM sent to PID 12345
  - Wait up to 5 seconds for termination
  - SIGKILL if still alive
  - New process spawned
  - Output: `respawned process-worker (pid: <new-pid>)`

### Scenario: Respawn with existing worktree
- **Given**: Stopped worker "wt-worker" with worktree at `<repo>-worktrees/wt-worker`
- **When**: `swarm respawn wt-worker` is executed (without --clean-first)
- **Then**:
  - Existing worktree reused (not recreated)
  - Worker spawned in existing worktree directory
  - Worktree info preserved in state

### Scenario: Respawn with --clean-first (clean worktree)
- **Given**: Stopped worker "clean-wt" with clean worktree (no uncommitted changes)
- **When**: `swarm respawn clean-wt --clean-first` is executed
- **Then**:
  - Worktree removed via `git worktree remove`
  - Fresh worktree created at same path with same branch
  - Worker spawned in fresh worktree

### Scenario: Respawn with --clean-first on dirty worktree
- **Given**: Stopped worker "dirty-wt" with uncommitted changes in worktree
- **When**: `swarm respawn dirty-wt --clean-first` is executed
- **Then**:
  - Error: `swarm: error: cannot remove worktree: <reason>`
  - Error: `swarm: worktree at: <path>`
  - Error: `swarm: use --force-dirty to remove anyway, or commit changes first`
  - Exit code is 1
  - Worker not respawned, state unchanged

### Scenario: Respawn with --clean-first --force-dirty
- **Given**: Stopped worker "dirty-wt" with uncommitted changes
- **When**: `swarm respawn dirty-wt --clean-first --force-dirty` is executed
- **Then**:
  - Dirty worktree forcibly removed (changes lost)
  - Fresh worktree created
  - Worker respawned
  - Output: `respawned dirty-wt (tmux: ...)`

### Scenario: Respawn with missing worktree directory
- **Given**: Worker "ghost-wt" with worktree.path pointing to deleted directory
- **When**: `swarm respawn ghost-wt` is executed (without --clean-first)
- **Then**:
  - New worktree created at original path
  - Worker spawned in recreated worktree

### Scenario: Worker not found
- **Given**: No worker named "missing" in state
- **When**: `swarm respawn missing` is executed
- **Then**:
  - Error: `swarm: error: worker 'missing' not found`
  - Exit code is 1

### Scenario: Respawn preserves all configuration
- **Given**: Worker with complex config (tags: ["a", "b"], env: {"X": "1"}, cmd: ["cmd", "arg"])
- **When**: Worker is killed and then respawned
- **Then**:
  - All tags preserved
  - All env vars preserved
  - Full command preserved
  - Working directory preserved

## Edge Cases

- **Process doesn't die with SIGTERM**: SIGKILL sent after 5 seconds (50 checks at 0.1s)
- **ProcessLookupError on kill**: Silently ignored (process already dead)
- **Worktree branch already exists**: `create_worktree()` handles this case
- **Tmux socket preserved**: Respawn uses same socket for test isolation
- **Empty env/tags**: Preserved as empty dict/list

## Recovery Procedures

### Respawn fails partway through
If respawn kills the old worker but fails to create new:
1. Worker will be removed from state
2. Worktree may still exist
3. Check state with `swarm ls`
4. Re-spawn manually with original config

### Orphaned worktree after respawn
```bash
# List worktrees
git worktree list

# Remove if not needed
git worktree remove <path>
```

## Implementation Notes

- Original worker is removed from state before spawning new worker (to avoid conflicts)
- New Worker object created with fresh timestamp and "running" status
- Tmux socket is extracted from original `worker.tmux.socket` and preserved
- WorktreeInfo is reconstructed with original path, branch, and base_repo
- The `create_tmux_window()` function receives the same session name to maintain grouping
