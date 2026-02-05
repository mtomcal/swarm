# Logs

## Overview

The `logs` command displays worker output. For tmux workers, it captures pane content; for non-tmux workers, it reads log files from `~/.swarm/logs/`. Supports follow mode for real-time monitoring.

## Dependencies

- **External**: tmux (for tmux workers), filesystem
- **Internal**: state-management.md, tmux-integration.md

## Behavior

### View Worker Output

**Description**: Display the output of a worker, either from tmux pane or log files.

**Inputs**:
- `name` (string, required): Worker name to view logs for
- `--history` (flag, optional): Include scrollback buffer instead of just visible pane (tmux only)
- `--lines` (int, optional, default: 1000): Number of scrollback lines to include when `--history` is set
- `--follow` (flag, optional): Continuously poll and display output

**Outputs**:
- Success (tmux worker): Captured pane content printed to stdout
- Success (non-tmux worker): Contents of `~/.swarm/logs/<name>.stdout.log`
- Failure: Error message and exit code 1

**Side Effects**:
- Follow mode: Continuous polling every 1 second until Ctrl-C
- Follow mode: Clears terminal screen on each update (ANSI escape `\033[2J\033[H`)
- Non-tmux follow: Replaces current process with `tail -f`

**Error Conditions**:

| Condition | Behavior |
|-----------|----------|
| Worker not found | Print `swarm: no worker named '<name>'` to stderr, exit 1 |
| Non-tmux worker has no log file | Print `swarm: no logs found for <name>` to stderr, exit 1 |

## Tmux Worker Behavior

### Default Mode (no flags)
- Captures visible pane content only (current screen)
- Uses `tmux_capture_pane()` with `history_lines=0`
- Prints output without trailing newline manipulation

### History Mode (--history)
- Captures scrollback buffer up to `--lines` lines (default 1000)
- Uses `tmux_capture_pane()` with `history_lines=<value>`
- Useful for viewing past output that has scrolled off screen

### Follow Mode (--follow)
- Polls every 1 second
- Clears screen before each update
- Shows last 30 lines of output
- Exits cleanly on Ctrl-C (KeyboardInterrupt)
- Respects `--history` and `--lines` flags for scrollback

## Non-Tmux Worker Behavior

### Default Mode
- Reads entire contents of `~/.swarm/logs/<name>.stdout.log`
- Prints to stdout without trailing newline

### Follow Mode (--follow)
- Uses `os.execvp("tail", ["tail", "-f", <log_path>])` to replace process
- User must interrupt with Ctrl-C

## Scenarios

### Scenario: View tmux worker visible pane
- **Given**: A running tmux worker named "my-worker" with visible output
- **When**: `swarm logs my-worker` is executed
- **Then**: The visible pane content is printed to stdout

### Scenario: View tmux worker with history
- **Given**: A tmux worker with output that has scrolled off screen
- **When**: `swarm logs my-worker --history` is executed
- **Then**: Up to 1000 lines of scrollback buffer are included in output

### Scenario: View tmux worker with custom history lines
- **Given**: A tmux worker with extensive history
- **When**: `swarm logs my-worker --history --lines 500` is executed
- **Then**: Up to 500 lines of scrollback buffer are captured

### Scenario: Follow tmux worker output
- **Given**: A running tmux worker producing output
- **When**: `swarm logs my-worker --follow` is executed
- **Then**:
  - Screen is cleared
  - Last 30 lines of output are displayed
  - Display updates every 1 second
  - Ctrl-C exits cleanly

### Scenario: View non-tmux worker logs
- **Given**: A non-tmux worker "bg-worker" with log file at `~/.swarm/logs/bg-worker.stdout.log`
- **When**: `swarm logs bg-worker` is executed
- **Then**: Contents of the log file are printed to stdout

### Scenario: Follow non-tmux worker logs
- **Given**: A non-tmux worker "bg-worker" with active log file
- **When**: `swarm logs bg-worker --follow` is executed
- **Then**: Process is replaced with `tail -f` on the log file

### Scenario: Worker not found
- **Given**: No worker named "nonexistent" in state
- **When**: `swarm logs nonexistent` is executed
- **Then**:
  - Error `swarm: no worker named 'nonexistent'` printed to stderr
  - Exit code is 1

### Scenario: Non-tmux worker with no log file
- **Given**: A non-tmux worker "orphan" exists but has no log file
- **When**: `swarm logs orphan` is executed
- **Then**:
  - Error `swarm: no logs found for orphan` printed to stderr
  - Exit code is 1

## Edge Cases

- **Empty pane**: Returns empty string, prints nothing
- **Binary content in logs**: Printed as-is, may corrupt terminal
- **Very large log files**: No pagination, entire file is read (non-tmux default mode)
- **Worker status**: Logs can be viewed regardless of worker status (running or stopped)
- **Follow mode with stopped tmux worker**: Will show static content, updating with same content each second

## Recovery Procedures

### Missing log files for non-tmux workers
Log files are stored at `~/.swarm/logs/<name>.stdout.log`. If missing:
1. Check if worker was spawned with correct name
2. Check if `~/.swarm/logs/` directory exists
3. Worker may have crashed before producing any output

### Corrupted terminal after binary output
```bash
reset  # Reset terminal to clean state
```

## Related Commands

### swarm ralph logs (for Ralph Workers)

For workers running in Ralph mode, there is a separate command to view **iteration history**:

```bash
swarm ralph logs <name>           # View iteration history
swarm ralph logs <name> --live    # Tail iteration log in real-time
swarm ralph logs <name> --lines 5 # Show last 5 entries
```

**Key differences**:

| Command | What it shows | Data source |
|---------|---------------|-------------|
| `swarm logs <name>` | Worker's tmux pane output (live session) | tmux `capture-pane` |
| `swarm ralph logs <name>` | Iteration history (timestamps, status, reasons) | `~/.swarm/ralph/<name>/iterations.log` |

**When to use each**:
- Use `swarm logs` to see what the worker is currently doing (real-time output)
- Use `swarm ralph logs` to see iteration history (when iterations started, completed, why they ended)

See `specs/ralph-loop.md` for full documentation of `swarm ralph logs`.

## Implementation Notes

- Tmux capture uses `capture-pane` with `-p` flag for stdout output
- For tmux follow mode, only last 30 lines are shown to fit in typical terminal
- Non-tmux follow mode fully replaces the process via `execvp`, so no cleanup runs
- The `--lines` flag only affects output when `--history` is also specified
