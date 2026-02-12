# Peek Command

## Overview

The `swarm peek` command captures the last N lines of a worker's terminal output by wrapping `tmux capture-pane`. This provides a lightweight, non-interactive way for directors and monitoring scripts to check what a worker is doing without attaching to the tmux session.

## Dependencies

- **External**:
  - tmux (for pane capture)
- **Internal**:
  - `tmux-integration.md` (tmux_capture_pane function)
  - `state-management.md` (worker lookup)

## Behavior

### Peek Command

**Description**: Capture and display recent terminal output from a worker.

**Command**:
```bash
swarm peek <name> [-n LINES] [--all]
```

**Inputs**:
- `<name>` (str, required unless `--all`): Worker name
- `-n/--lines` (int, optional): Number of lines to capture (default: 30)
- `--all` (flag, optional): Peek all running workers

**Behavior**:
1. Load worker from state registry
2. Verify worker is a tmux worker
3. Capture pane content via `tmux_capture_pane()` with `history_lines=N`
4. Print captured content to stdout

**`--all` Behavior**:
1. Load all workers from state registry
2. Filter to running tmux workers
3. For each worker, print header and captured content:
```
=== worker-name ===
[last N lines of terminal output]

=== another-worker ===
[last N lines of terminal output]
```

**Error Conditions**:
| Condition | Behavior |
|-----------|----------|
| Worker not found | Exit 2 with "swarm: error: worker '<name>' not found" |
| Worker not a tmux worker | Exit 1 with "swarm: error: worker '<name>' is not a tmux worker" |
| Worker stopped (tmux window dead) | Exit 1 with "swarm: error: worker '<name>' is not running" |
| tmux capture fails | Exit 1 with "swarm: error: failed to capture pane for '<name>': <error>" |

### CLI Arguments

| Argument | Type | Required | Default | Description |
|----------|------|----------|---------|-------------|
| `<name>` | positional | No* | - | Worker name |
| `-n/--lines` | int | No | 30 | Number of lines to capture |
| `--all` | flag | No | false | Peek all running workers |

\* One of `<name>` or `--all` is required.

### Exit Codes

| Exit Code | Meaning |
|-----------|---------|
| 0 | Success — output captured and printed |
| 1 | Error — worker not running, not tmux, or capture failed |
| 2 | Not found — worker does not exist |

## Scenarios

### Scenario: Basic peek
- **Given**: Worker "dev" is running in tmux
- **When**: `swarm peek dev`
- **Then**:
  - Last 30 lines of terminal output printed to stdout
  - Exit code 0

### Scenario: Custom line count
- **Given**: Worker "dev" is running in tmux
- **When**: `swarm peek dev -n 100`
- **Then**:
  - Last 100 lines of terminal output printed to stdout
  - Exit code 0

### Scenario: Peek all running workers
- **Given**: Workers "dev" and "builder" are running in tmux
- **When**: `swarm peek --all`
- **Then**:
  - Output shows each worker's terminal output with headers
  - Exit code 0

### Scenario: Peek non-tmux worker
- **Given**: Worker "bg-job" is running in process mode (no tmux)
- **When**: `swarm peek bg-job`
- **Then**:
  - Exit code 1
  - Error: "swarm: error: worker 'bg-job' is not a tmux worker"

### Scenario: Peek stopped worker
- **Given**: Worker "old" exists in state but is stopped
- **When**: `swarm peek old`
- **Then**:
  - Exit code 1
  - Error: "swarm: error: worker 'old' is not running"

### Scenario: Peek non-existent worker
- **Given**: No worker named "ghost" exists
- **When**: `swarm peek ghost`
- **Then**:
  - Exit code 2
  - Error: "swarm: error: worker 'ghost' not found"

## Edge Cases

- **Empty pane**: If the tmux pane has no output, an empty string is printed (exit code 0)
- **ANSI codes in output**: Captured output may contain ANSI escape codes from the worker's terminal; these are passed through as-is
- **Very large line count**: `-n 10000` captures up to 10000 lines of scrollback if available; fewer lines returned if scrollback is shorter
- **`--all` with no running workers**: Prints nothing, exit code 0
- **`--all` with `-n`**: The `-n` value applies to each worker individually

## Implementation Notes

- **tmux capture-pane**: Uses `tmux capture-pane -p -S -N` where N is the number of history lines to capture
- **No state changes**: `peek` is read-only — it does not modify worker state
- **Lightweight**: Designed as a quick diagnostic tool, faster than `swarm attach` (which is interactive) or `swarm logs` (which reads log files, not live terminal)
- **Director use case**: Directors can call `swarm peek dev` every few minutes to check worker progress without interrupting the worker
