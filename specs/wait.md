# Wait

## Overview

The `wait` command blocks until one or more workers exit. It supports waiting for a single worker, all workers, or with an optional timeout. Useful for scripts that need to synchronize on worker completion.

## Dependencies

- **External**: None
- **Internal**: state-management.md

## Behavior

### Wait for Worker(s) to Exit

**Description**: Poll worker status until worker(s) transition to "stopped" state.

**Inputs**:
- `name` (string, optional): Worker name to wait for (required if not using `--all`)
- `--all` (flag, optional): Wait for all running workers
- `--timeout` (int, optional): Maximum wait time in seconds

**Outputs**:
- Success: Prints `<name>: exited` for each worker that exits, exit code 0
- Timeout: Prints `<name>: still running (timeout)` for pending workers, exit code 1
- Error: Exit code 1 with error message

**Side Effects**:
- Polls worker status every 1 second
- Uses `refresh_worker_status()` to check actual state (not cached)

**Error Conditions**:

| Condition | Behavior |
|-----------|----------|
| Neither name nor `--all` provided | Print `swarm: error: name required (or use --all)` to stderr, exit 1 |
| Worker not found | Print `swarm: error: worker '<name>' not found` to stderr, exit 1 |
| Timeout reached | Print status for each pending worker, exit 1 |

## Algorithm

1. Load state and identify workers to wait for
2. Create pending set of worker names
3. Enter polling loop:
   - Check if timeout exceeded (if `--timeout` set)
   - For each pending worker, refresh status
   - If status is "stopped", print exit message and remove from pending
   - Sleep 1 second if any workers still pending
4. Exit with code 0 if all workers exited, code 1 if timeout

## Scenarios

### Scenario: Wait for single worker to exit
- **Given**: A running worker named "my-worker"
- **When**: `swarm wait my-worker` is executed, and worker exits
- **Then**:
  - Output: `my-worker: exited`
  - Exit code is 0

### Scenario: Wait for all workers
- **Given**: Running workers "worker-1" and "worker-2"
- **When**: `swarm wait --all` is executed, and both workers exit
- **Then**:
  - Output includes `worker-1: exited` and `worker-2: exited`
  - Exit code is 0

### Scenario: Wait with timeout - worker exits in time
- **Given**: A running worker "fast-worker" that exits within 5 seconds
- **When**: `swarm wait fast-worker --timeout 10` is executed
- **Then**:
  - Output: `fast-worker: exited`
  - Exit code is 0

### Scenario: Wait with timeout - timeout exceeded
- **Given**: A running worker "slow-worker" that does not exit within timeout
- **When**: `swarm wait slow-worker --timeout 2` is executed
- **Then**:
  - Output: `slow-worker: still running (timeout)`
  - Exit code is 1

### Scenario: Wait for all with timeout - partial completion
- **Given**: Workers "fast" and "slow" running; "fast" exits within 2 seconds, "slow" does not
- **When**: `swarm wait --all --timeout 3` is executed
- **Then**:
  - Output includes `fast: exited` and `slow: still running (timeout)`
  - Exit code is 1

### Scenario: Worker not found
- **Given**: No worker named "missing" in state
- **When**: `swarm wait missing` is executed
- **Then**:
  - Error: `swarm: error: worker 'missing' not found`
  - Exit code is 1

### Scenario: Wait called without name or --all
- **Given**: Running workers exist
- **When**: `swarm wait` is executed without arguments
- **Then**:
  - Error: `swarm: error: name required (or use --all)`
  - Exit code is 1

### Scenario: Wait for already-stopped worker
- **Given**: A worker "stopped-worker" in "stopped" status
- **When**: `swarm wait stopped-worker` is executed
- **Then**:
  - Output: `stopped-worker: exited`
  - Exit code is 0 (immediately, no waiting)

### Scenario: Wait --all with no running workers
- **Given**: No workers, or all workers are stopped
- **When**: `swarm wait --all` is executed
- **Then**:
  - No output (empty pending set)
  - Exit code is 0 (immediately)

## Edge Cases

- **Worker exits between status checks**: Detected on next poll cycle (up to 1 second delay)
- **Worker respawns during wait**: Will keep waiting since status becomes "running" again
- **Multiple workers with same timeout**: All checked in each cycle; exit message order may vary
- **Timeout of 0**: Immediately checks once and times out if worker still running
- **Large number of workers**: Each worker checked sequentially per cycle; may be slow with many workers

## Recovery Procedures

### Stuck wait
If `swarm wait` seems hung:
1. Ctrl-C to interrupt
2. Check worker status with `swarm status <name>`
3. If worker is stuck, use `swarm kill <name>`

### Workers not exiting
```bash
# Check what's happening
swarm logs <name>

# Force termination
swarm kill <name>
```

## Implementation Notes

- Status refresh happens via `refresh_worker_status()` which checks actual tmux window/process state
- Polling interval is hardcoded to 1 second
- Workers are checked in arbitrary order (dict iteration order)
- Exit messages are printed as each worker exits, not batched at the end
