# ls - List Workers

## Overview

The `ls` command lists workers registered in the swarm state, displaying their name, status, process/window information, start time, worktree path, and tags. It supports filtering by status and tag, and outputs in table, JSON, or names-only format. Before displaying, it refreshes each worker's status by checking actual process/tmux state.

## Dependencies

- **External**: None
- **Internal**:
  - `state-management.md` - Reads worker registry from state file
  - `tmux-integration.md` - Uses `tmux_window_exists()` for status refresh

## Behavior

### List Workers

**Description**: Retrieves all workers from state, refreshes their actual status, applies optional filters, and outputs in the specified format.

**Inputs**:
- `--format` (string, optional): Output format
  - `table` (default): Human-readable aligned columns
  - `json`: JSON array of worker objects
  - `names`: Worker names only, one per line
- `--status` (string, optional): Filter by worker status
  - `all` (default): Show all workers
  - `running`: Show only running workers
  - `stopped`: Show only stopped workers
- `--tag` (string, optional): Filter by tag (exact match on any tag in worker's tag list)

**Outputs**:

- **Success (exit code 0)**:
  - Table format: Aligned columns with header row, one worker per line
  - JSON format: JSON array of worker dictionaries with indentation
  - Names format: One worker name per line, no header
  - Empty output if no workers match filters (no error)

- **Failure**: None defined (always succeeds, even with no workers)

**Side Effects**:
- Reads state file with fcntl lock
- Checks tmux windows and process PIDs to refresh status
- Does NOT modify state file (status refresh is not persisted)

### Status Refresh

**Description**: Before displaying, each worker's status is refreshed by checking actual runtime state.

**Logic**:
1. If worker has `tmux` info: Check if tmux window exists
   - Window exists → status = `"running"`
   - Window gone → status = `"stopped"`
2. Else if worker has `pid`: Check if process is alive
   - Process alive → status = `"running"`
   - Process dead → status = `"stopped"`
3. Else: status = `"stopped"` (no tmux or pid)

### Table Format Columns

| Column | Content |
|--------|---------|
| NAME | Worker name |
| STATUS | `running` or `stopped` |
| PID/WINDOW | For tmux: `session:window`, for process: PID, else `-` |
| STARTED | Relative time (e.g., `5s`, `2m`, `1h`, `3d`) |
| WORKTREE | Worktree path or `-` if none |
| TAG | Comma-separated tags or `-` if none |

### Relative Time Format

Converts ISO timestamp to human-readable format:
- `< 60 seconds`: `Ns` (e.g., `45s`)
- `< 1 hour`: `Nm` (e.g., `15m`)
- `< 1 day`: `Nh` (e.g., `6h`)
- `>= 1 day`: `Nd` (e.g., `3d`)

### JSON Format Schema

Output is a JSON array of worker objects:

```json
[
  {
    "name": "worker-1",
    "status": "running",
    "cmd": ["claude"],
    "started": "2024-01-15T10:30:00",
    "cwd": "/home/user/project",
    "env": {"MY_VAR": "value"},
    "tags": ["team-a", "priority:high"],
    "tmux": {
      "session": "swarm-abc123",
      "window": "worker-1",
      "socket": null
    },
    "worktree": {
      "path": "/home/user/project-worktrees/worker-1",
      "branch": "worker-1",
      "base_repo": "/home/user/project"
    },
    "pid": null
  }
]
```

Fields that are `null` or empty may be omitted or present depending on worker configuration.

## Scenarios

### Scenario: List all workers in table format (default)
- **Given**: State contains workers `worker-1` (running, tmux) and `worker-2` (stopped, pid mode)
- **When**: `swarm ls` is executed
- **Then**:
  - Exit code is 0
  - Output shows aligned table with header row
  - Both workers are listed with current status
  - worker-1 shows `session:window` in PID/WINDOW column
  - worker-2 shows PID number in PID/WINDOW column

### Scenario: List workers as JSON
- **Given**: State contains one worker `worker-1`
- **When**: `swarm ls --format json` is executed
- **Then**:
  - Exit code is 0
  - Output is valid JSON array with one element
  - Object contains all worker fields (name, status, cmd, started, cwd, env, tags, tmux, worktree, pid)

### Scenario: List worker names only
- **Given**: State contains workers `alpha`, `beta`, `gamma`
- **When**: `swarm ls --format names` is executed
- **Then**:
  - Exit code is 0
  - Output is three lines: `alpha`, `beta`, `gamma`
  - No header row, no other columns

### Scenario: Filter by running status
- **Given**: State contains `worker-1` (running) and `worker-2` (stopped)
- **When**: `swarm ls --status running` is executed
- **Then**:
  - Exit code is 0
  - Only `worker-1` is displayed
  - `worker-2` is not shown

### Scenario: Filter by stopped status
- **Given**: State contains `worker-1` (running) and `worker-2` (stopped)
- **When**: `swarm ls --status stopped` is executed
- **Then**:
  - Exit code is 0
  - Only `worker-2` is displayed
  - `worker-1` is not shown

### Scenario: Filter by tag
- **Given**: State contains `worker-1` (tags: `team-a`, `priority:high`) and `worker-2` (tags: `team-b`)
- **When**: `swarm ls --tag team-a` is executed
- **Then**:
  - Exit code is 0
  - Only `worker-1` is displayed
  - `worker-2` is not shown (different tag)

### Scenario: Combined status and tag filters
- **Given**: State contains:
  - `w1` (running, tags: `team-a`)
  - `w2` (running, tags: `team-b`)
  - `w3` (stopped, tags: `team-a`)
- **When**: `swarm ls --status running --tag team-a` is executed
- **Then**:
  - Exit code is 0
  - Only `w1` is displayed
  - `w2` excluded (wrong tag), `w3` excluded (wrong status)

### Scenario: No workers match filters
- **Given**: State contains `worker-1` (running)
- **When**: `swarm ls --status stopped` is executed
- **Then**:
  - Exit code is 0
  - No output (empty table, no header printed)

### Scenario: Empty state
- **Given**: State file contains no workers
- **When**: `swarm ls` is executed
- **Then**:
  - Exit code is 0
  - No output

### Scenario: Status refresh detects externally killed tmux window
- **Given**: Worker `worker-1` is registered as `running` in state, but tmux window was killed externally
- **When**: `swarm ls` is executed
- **Then**:
  - Exit code is 0
  - Worker shows `stopped` status (detected via `tmux_window_exists()`)
  - State file is NOT updated (refresh is ephemeral)

### Scenario: Status refresh detects dead process
- **Given**: Worker `worker-1` (pid mode) is registered as `running` in state, but process has exited
- **When**: `swarm ls` is executed
- **Then**:
  - Exit code is 0
  - Worker shows `stopped` status (detected via `process_alive()`)

## Edge Cases

- **Worker with no tmux and no pid**: Status shown as `stopped`
- **Empty tags list**: TAG column shows `-`
- **No worktree**: WORKTREE column shows `-`
- **Very long worker names**: Table columns auto-expand to fit
- **Workers started > 24 hours ago**: Show days (e.g., `3d`)
- **Invalid timestamp format**: May raise exception (timestamps should always be valid ISO format)
- **Concurrent state access**: fcntl lock ensures consistent read
- **Tag filter with non-existent tag**: Returns empty list (no error)
- **Unicode in worker names**: Handled correctly in table output

## Recovery Procedures

### No workers appearing despite spawns

1. Check state file exists: `cat ~/.swarm/state.json`
2. Verify JSON is valid: `python3 -c "import json; json.load(open('$HOME/.swarm/state.json'))"`
3. Check for permission issues: `ls -la ~/.swarm/`
4. If state is corrupted, backup and recreate: `mv ~/.swarm/state.json ~/.swarm/state.json.bak`

### Status showing stale values

1. This is expected behavior - `ls` refreshes status on each call
2. Stale status in state file is normal; it's refreshed at display time
3. If tmux/process state is inconsistent, check:
   - `tmux list-windows -t <session>` for tmux workers
   - `ps -p <pid>` for process workers

### JSON parse errors in scripts

1. Ensure using `--format json` flag
2. Check for empty output before parsing (no workers case)
3. Handle the case where stdout is empty string

## Implementation Notes

- Status refresh is ephemeral - the state file is NOT updated with refreshed status
- This design choice prevents write contention on read operations
- Tag filtering uses `in` operator, checking if filter tag exists in worker's tag list
- Status filtering happens AFTER status refresh, ensuring accurate results
- Column widths are calculated dynamically based on content
- Empty table (no matching workers) produces no output, not even headers
