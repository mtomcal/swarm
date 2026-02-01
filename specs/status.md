# status - Check Worker Status

## Overview

The `status` command retrieves and displays the current status of a single worker by name. It refreshes the worker's actual runtime status (by checking tmux window existence or process liveness), outputs a human-readable status line with details, and exits with a code indicating whether the worker is running or stopped. This command is useful for programmatic status checks in scripts.

## Dependencies

- **External**: None
- **Internal**:
  - `state-management.md` - Reads worker from state registry
  - `tmux-integration.md` - Uses `tmux_window_exists()` for tmux worker status refresh
  - `ls.md` - Shares `refresh_worker_status()` and `relative_time()` functions

## Behavior

### Get Worker Status

**Description**: Retrieves a specific worker by name, refreshes its actual status, and outputs a status line with relevant details.

**Inputs**:
- `name` (string, required): The worker name to query

**Outputs**:

- **Success (exit code 0)**: Worker is running
  - Prints status line to stdout: `<name>: running (<details>, uptime <time>)`

- **Stopped (exit code 1)**: Worker exists but is stopped
  - Prints status line to stdout: `<name>: stopped (<details>, uptime <time>)`

- **Not Found (exit code 2)**: Worker does not exist
  - Prints error to stderr: `swarm: error: worker '<name>' not found`

**Side Effects**:
- Reads state file with fcntl lock
- Checks tmux windows or processes to refresh status
- Does NOT modify state file (status refresh is ephemeral)

**Error Conditions**:
| Condition | Behavior |
|-----------|----------|
| Worker not found | Error to stderr, exit code 2 |
| State file missing | No workers exist, worker not found |
| State file corrupted | JSON parse error exception |

### Status Line Format

The output format is:

```
<name>: <status> (<mode_details>, uptime <relative_time>)
```

**Components**:
- `<name>`: Worker name
- `<status>`: Either `running` or `stopped`
- `<mode_details>`:
  - For tmux workers: `tmux window <session>:<window>`
  - For process workers: `pid <pid>`
- `<relative_time>`: Human-readable uptime (e.g., `5m`, `2h`, `3d`)

**Examples**:
```
worker-1: running (tmux window swarm-abc123:worker-1, uptime 15m)
worker-2: stopped (pid 12345, uptime 2h)
worker-3: running (tmux window swarm-def456:worker-3, worktree /path/to/worktree, uptime 30s)
```

If the worker has a worktree, it is included in the details section.

### Status Refresh Logic

Status is refreshed before display using the same logic as `ls`:

1. If worker has `tmux` info: Check if tmux window exists
   - Window exists → status = `"running"`
   - Window gone → status = `"stopped"`
2. Else if worker has `pid`: Check if process is alive
   - Process alive → status = `"running"`
   - Process dead → status = `"stopped"`
3. Else: status = `"stopped"` (no tmux or pid)

### Exit Code Semantics

Exit codes enable easy scripting:

| Exit Code | Meaning |
|-----------|---------|
| 0 | Worker is running |
| 1 | Worker is stopped |
| 2 | Worker not found |

This allows patterns like:
```bash
if swarm status my-worker; then
    echo "Worker is running"
else
    echo "Worker is stopped or not found"
fi
```

### Relative Time Format

Converts ISO timestamp to human-readable format (same as `ls`):
- `< 60 seconds`: `Ns` (e.g., `45s`)
- `< 1 hour`: `Nm` (e.g., `15m`)
- `< 1 day`: `Nh` (e.g., `6h`)
- `>= 1 day`: `Nd` (e.g., `3d`)

## Scenarios

### Scenario: Running tmux worker status
- **Given**: State contains `worker-1` with tmux info, and the tmux window exists
- **When**: `swarm status worker-1` is executed
- **Then**:
  - Exit code is 0
  - Output shows: `worker-1: running (tmux window <session>:<window>, uptime <time>)`

### Scenario: Stopped tmux worker status
- **Given**: State contains `worker-1` with tmux info, but the tmux window was killed externally
- **When**: `swarm status worker-1` is executed
- **Then**:
  - Exit code is 1
  - Output shows: `worker-1: stopped (tmux window <session>:<window>, uptime <time>)`

### Scenario: Running process worker status
- **Given**: State contains `worker-1` with pid, and the process is alive
- **When**: `swarm status worker-1` is executed
- **Then**:
  - Exit code is 0
  - Output shows: `worker-1: running (pid <pid>, uptime <time>)`

### Scenario: Stopped process worker status
- **Given**: State contains `worker-1` with pid 99999, but no such process exists
- **When**: `swarm status worker-1` is executed
- **Then**:
  - Exit code is 1
  - Output shows: `worker-1: stopped (pid 99999, uptime <time>)`

### Scenario: Worker with worktree
- **Given**: State contains `worker-1` with tmux info and worktree at `/path/to/worktree`
- **When**: `swarm status worker-1` is executed
- **Then**:
  - Exit code is 0 or 1 (depending on running state)
  - Output includes worktree path: `worker-1: running (tmux window <session>:<window>, worktree /path/to/worktree, uptime <time>)`

### Scenario: Worker not found
- **Given**: State contains no worker named `nonexistent`
- **When**: `swarm status nonexistent` is executed
- **Then**:
  - Exit code is 2
  - Stderr shows: `swarm: error: worker 'nonexistent' not found`
  - No output to stdout

### Scenario: Empty state file
- **Given**: State file exists but contains no workers
- **When**: `swarm status worker-1` is executed
- **Then**:
  - Exit code is 2
  - Stderr shows: `swarm: error: worker 'worker-1' not found`

### Scenario: Uptime display accuracy
- **Given**: Worker `worker-1` was started 5 minutes ago
- **When**: `swarm status worker-1` is executed
- **Then**:
  - Output shows `uptime 5m` (rounded to minutes)

## Edge Cases

- **Worker with no tmux and no pid**: Status is `stopped` (exit code 1)
- **Very long worker names**: Displayed as-is, no truncation
- **Special characters in worker names**: Handled correctly in output
- **Workers started seconds ago**: Show `Ns` format (e.g., `3s`)
- **Workers started days ago**: Show `Nd` format (e.g., `7d`)
- **Concurrent state access**: fcntl lock ensures consistent read
- **State file missing**: Treated as empty, worker not found
- **Invalid timestamp in state**: May raise exception during relative time calculation

## Recovery Procedures

### Worker appears stuck in "running" state

1. Check if tmux window actually exists:
   ```bash
   tmux list-windows -t <session-name>
   ```
2. Check if process actually exists:
   ```bash
   ps -p <pid>
   ```
3. Status is refreshed on each call; stale state file is normal
4. If tmux session was destroyed, status will correctly show `stopped`

### Exit code 2 when worker should exist

1. Verify worker name spelling (case-sensitive)
2. Check state file: `cat ~/.swarm/state.json | grep <worker-name>`
3. List all workers: `swarm ls --format names`
4. Worker may have been cleaned up with `swarm clean`

### Error parsing state file

1. Check state file for JSON syntax: `python3 -c "import json; json.load(open('$HOME/.swarm/state.json'))"`
2. If corrupted, backup and recreate: `mv ~/.swarm/state.json ~/.swarm/state.json.bak`

## Implementation Notes

- Status refresh is ephemeral - the state file is NOT updated with refreshed status
- This design prevents write contention on read-only operations
- The exit code semantics (0=running, 1=stopped, 2=not found) enable clean scripting patterns
- Output goes to stdout for the status line; only errors go to stderr
- Worktree information is included in output when present but doesn't affect status determination
- The command takes exactly one positional argument (worker name); no flags or options
