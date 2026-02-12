# CLI Interface

## Overview

Swarm provides a command-line interface with subcommands for managing worker processes. The interface follows Unix conventions with exit codes, stderr for errors, and stdout for output. Arguments are parsed using Python's argparse module with a required subcommand pattern.

## Dependencies

- **External**:
  - Python argparse module
- **Internal**:
  - All command specs (spawn, kill, send, etc.)
  - state-management.md

## Behavior

### Program Structure

**Description**: Swarm uses a subcommand-based CLI structure similar to git or docker.

**Invocation Pattern**:
```bash
swarm <command> [options] [arguments]
```

**Help Flags**:
- `swarm --help` - Show top-level help
- `swarm <command> --help` - Show command-specific help

### Command Summary

| Command | Description | Has `--all` |
|---------|-------------|-------------|
| `spawn` | Spawn a new worker | No |
| `ls` | List workers | No |
| `status` | Get worker status | No |
| `send` | Send text to worker | Yes |
| `interrupt` | Send Ctrl-C to worker | Yes |
| `eof` | Send Ctrl-D to worker | No |
| `peek` | Capture worker terminal output | Yes |
| `attach` | Attach to tmux window | No |
| `logs` | View worker output | No |
| `kill` | Kill worker | Yes |
| `wait` | Wait for worker to finish | Yes |
| `clean` | Clean up dead workers | Yes |
| `respawn` | Respawn a dead worker | No |
| `init` | Initialize swarm in project | No |
| `ralph` | Ralph mode subcommands | No |

### Ralph Subcommands

| Subcommand | Description |
|------------|-------------|
| `ralph spawn` | Spawn a new ralph worker |
| `ralph status` | Get ralph worker status |
| `ralph pause` | Pause ralph loop |
| `ralph resume` | Resume ralph loop |
| `ralph logs` | View iteration history log |
| `ralph init` | Create PROMPT.md template |
| `ralph template` | Output template to stdout |
| `ralph list` | List ralph workers |
| `ralph ls` | Alias for `ralph list` (consistency with `swarm ls`) |
| `ralph clean` | Remove ralph state for one or all workers |
| `ralph run` | Run ralph loop (internal) |

### Ralph Spawn Arguments

Ralph spawn accepts most of the same arguments as regular `spawn`, plus ralph-specific arguments.

**Note**: The `--tmux` flag is accepted as a no-op for consistency with `swarm spawn`. Ralph workers always use tmux mode, so this flag has no effect but prevents confusing argument errors.

| Argument | Type | Required | Default | Description |
|----------|------|----------|---------|-------------|
| `--name` | string | Yes | - | Unique worker identifier |
| `--prompt-file` | string | Yes | - | Path to prompt file read each iteration |
| `--max-iterations` | int | Yes | - | Maximum number of loop iterations |
| `--inactivity-timeout` | int | No | 180 | Screen stability timeout (seconds) |
| `--done-pattern` | string | No | null | Regex pattern to stop loop |
| `--check-done-continuous` | bool | No | false | Check done pattern during monitoring |
| `--no-run` | bool | No | false | Spawn only, don't start loop |
| `--foreground` | bool | No | false | Block while loop runs (for human terminal use) |
| `--replace` | bool | No | false | Auto-clean existing worker before spawn |
| `--clean-state` | bool | No | false | Clear ralph state without affecting worker |
| `--tmux` | bool | No | (no-op) | Accepted for consistency, ralph always uses tmux |
| `--worktree` | bool | No | false | Create git worktree |
| `-- <cmd>` | remainder | Yes | - | Command to run |

### Ralph Logs Arguments

| Argument | Type | Required | Default | Description |
|----------|------|----------|---------|-------------|
| `<name>` | positional | Yes | - | Worker name |
| `--live` | bool | No | false | Tail the log file in real-time |
| `--lines` | int | No | all | Show last N entries |

### Ralph Clean Arguments

| Argument | Type | Required | Default | Description |
|----------|------|----------|---------|-------------|
| `<name>` | positional | No* | - | Worker name to clean |
| `--all` | bool | No* | false | Clean ralph state for all workers |

\* One of `<name>` or `--all` is required.

### Ralph Spawn Caveats

**`--worktree` + Docker sandbox**: `--worktree` should be omitted when the worker command is a Docker-based sandbox (e.g., `./sandbox.sh`). Docker provides its own filesystem isolation, making worktrees redundant. The worktree path on the host may not map correctly inside the container.

**`--done-pattern` + `--check-done-continuous`**: The prompt text is typed into the tmux pane via `send-keys`. Baseline filtering captures the pane content after prompt injection and excludes it from done-pattern scanning, preventing self-match. Using a unique signal pattern (e.g., `SWARM_DONE_X9K`) that won't appear in prompt prose is still recommended as a defense-in-depth measure.

### Global Exit Codes

**Description**: Exit codes follow Unix conventions with command-specific semantics.

| Exit Code | Meaning | When Used |
|-----------|---------|-----------|
| 0 | Success | Command completed successfully |
| 1 | General error | Command failed, validation error, or worker stopped |
| 2 | Not found | Requested worker does not exist |

**Command-Specific Exit Codes**:

| Command | Exit 0 | Exit 1 | Exit 2 |
|---------|--------|--------|--------|
| `spawn` | Worker created | Validation failed, spawn failed | - |
| `ls` | Listed workers | - | - |
| `status` | Worker is running | Worker is stopped | Worker not found |
| `send` | Text sent | Worker not running, not tmux | Worker not found |
| `interrupt` | Signal sent | Worker not running | Worker not found |
| `eof` | Signal sent | Worker not running | Worker not found |
| `attach` | (never returns on success) | Not tmux worker | Worker not found |
| `logs` | Output displayed | Error reading logs | Worker not found |
| `kill` | Worker killed | Kill failed, dirty worktree | Worker not found |
| `wait` | Worker exited | Timeout | Worker not found |
| `clean` | Worker cleaned | Dirty worktree | Worker not found |
| `respawn` | Worker respawned | Respawn failed | Worker not found |
| `init` | File updated | Error writing | - |
| `peek` | Output captured | Not running, not tmux | Worker not found |
| `ralph logs` | Output displayed | Log file not found | Worker not found |

### Error Message Format

**Description**: Error messages are written to stderr with a consistent prefix.

**Format**:
```
swarm: error: <message>
```

**Examples**:
```
swarm: error: worker 'test' not found
swarm: error: --name is required
swarm: error: tmux is required for --tmux mode
swarm: error: worktree has uncommitted changes
```

### Argument Parsing Rules

**Description**: Arguments follow argparse conventions with some swarm-specific patterns.

**Positional vs Named Arguments**:
| Pattern | Example |
|---------|---------|
| Required positional | `swarm status <name>` |
| Optional positional | `swarm kill [name]` (when `--all` used) |
| Named required | `swarm spawn --name <name>` |
| Named optional | `swarm spawn --tag team-a` |
| Repeatable | `swarm spawn --tag a --tag b` |
| Value pairs | `swarm spawn --env KEY=VAL` |
| Remainder | `swarm spawn ... -- <command>` |

**Command Delimiter**:
- `--` separates swarm arguments from the command to spawn
- Command after `--` is passed as-is to the worker

**Boolean Flags**:
| Flag | Meaning |
|------|---------|
| `--tmux` | Enable tmux mode |
| `--worktree` | Enable worktree isolation |
| `--ready-wait` | Wait for agent ready |
| `--no-enter` | Don't append Enter key |
| `--all` | Apply to all workers |
| `--rm-worktree` | Remove worktree on cleanup |
| `--force-dirty` | Force operation on dirty worktree |
| `--force` | Overwrite existing file |
| `--dry-run` | Preview without changes |
| `--history` | Include scrollback buffer |
| `--follow` | Continuously poll output |
| `--clean-first` | Clean before respawn |

### Output Formats

**Description**: The `ls` command supports multiple output formats.

**Table Format** (default):
```
NAME       STATUS   TAGS      STARTED        CMD
worker-1   running  team-a    2h ago         claude
worker-2   stopped            5m ago         bash
```

**JSON Format** (`--format json`):
```json
[
  {
    "name": "worker-1",
    "status": "running",
    "cmd": ["claude"],
    "started": "2024-01-15T10:30:00",
    "tags": ["team-a"],
    ...
  }
]
```

**Names Format** (`--format names`):
```
worker-1
worker-2
```

### Filtering Options

**Description**: Several commands support filtering workers.

**Status Filter** (`ls --status`):
| Value | Description |
|-------|-------------|
| `running` | Only running workers |
| `stopped` | Only stopped workers |
| `all` | All workers (default) |

**Tag Filter** (`ls --tag`):
- Filter to workers with matching tag
- Single tag only (no multiple `--tag` for filtering)

### spawn Command Arguments

**Description**: The spawn command has the most complex argument structure.

| Argument | Type | Required | Default | Description |
|----------|------|----------|---------|-------------|
| `--name` | string | Yes | - | Unique worker identifier |
| `--tmux` | flag | No | false | Run in tmux window |
| `--session` | string | No | hash-based | Tmux session name |
| `--tmux-socket` | string | No | null | Custom tmux socket |
| `--worktree` | flag | No | false | Create git worktree |
| `--branch` | string | No | same as name | Branch for worktree |
| `--worktree-dir` | string | No | `<repo>-worktrees` | Parent directory |
| `--tag` | string | No | [] | Tag (repeatable) |
| `--env` | string | No | {} | Environment variable (repeatable) |
| `--cwd` | string | No | current dir | Working directory |
| `--ready-wait` | flag | No | false | Wait for ready |
| `--ready-timeout` | int | No | 120 | Timeout seconds |
| `-- <cmd>` | remainder | Yes | - | Command to run |

### Argument Validation

**Description**: Common validation rules applied before command execution.

| Validation | Commands | Error Message |
|------------|----------|---------------|
| Worker name required | status, send, logs, etc. | "name is required" |
| Worker not found | all with name arg | "worker 'X' not found" |
| Worker already exists | spawn | "worker 'X' already exists" |
| Name or --all required | kill, clean, wait | "name or --all is required" |
| Not a tmux worker | send, interrupt, eof, attach | "worker 'X' is not a tmux worker" |
| Worker not running | send, interrupt, eof | "worker 'X' is not running" |
| Not in git repository | spawn --worktree | "not a git repository" |
| Dirty worktree | kill --rm-worktree, clean | "worktree has uncommitted changes" |

## Scenarios

### Scenario: Help output
- **Given**: User is learning swarm
- **When**: `swarm --help` is run
- **Then**:
  - Lists all available commands
  - Shows program description
  - Exit code 0

### Scenario: Command-specific help
- **Given**: User wants to learn about spawn
- **When**: `swarm spawn --help` is run
- **Then**:
  - Lists all spawn arguments
  - Shows defaults and descriptions
  - Exit code 0

### Scenario: Unknown command
- **Given**: User runs non-existent command
- **When**: `swarm foo` is run
- **Then**:
  - argparse error message
  - Exit code 2 (argparse default)

### Scenario: Missing required argument
- **Given**: spawn requires --name
- **When**: `swarm spawn -- bash` is run (without --name)
- **Then**:
  - Error: "the following arguments are required: --name"
  - Exit code 2 (argparse default)

### Scenario: Invalid argument value
- **Given**: --status accepts specific values
- **When**: `swarm ls --status invalid` is run
- **Then**:
  - Error: "invalid choice: 'invalid'"
  - Exit code 2 (argparse default)

### Scenario: Repeatable arguments
- **Given**: spawn accepts multiple --tag
- **When**: `swarm spawn --name test --tag a --tag b -- bash`
- **Then**:
  - Worker created with tags ["a", "b"]
  - Exit code 0

### Scenario: Environment variable parsing
- **Given**: spawn accepts --env KEY=VAL
- **When**: `swarm spawn --name test --env FOO=bar --env BAZ=qux -- bash`
- **Then**:
  - Worker created with env {"FOO": "bar", "BAZ": "qux"}
  - Exit code 0

### Scenario: Command delimiter
- **Given**: Command has flags that conflict with swarm
- **When**: `swarm spawn --name test -- python --version`
- **Then**:
  - `--version` passed to python, not swarm
  - Worker runs `python --version`

### Scenario: JSON output
- **Given**: User wants machine-readable output
- **When**: `swarm ls --format json` is run
- **Then**:
  - Valid JSON array output
  - Exit code 0

### Scenario: Names output for scripting
- **Given**: User wants to pipe worker names
- **When**: `swarm ls --format names | xargs -I{} swarm status {}`
- **Then**:
  - Each line is a worker name
  - Composable with other commands

## Edge Cases

- **Empty command after `--`**: Validation error, command is required
- **Worker name with spaces**: Accepted but may cause issues with tmux
- **Worker name with `/`**: Rejected by tmux window naming
- **Very long worker names**: May truncate in table output
- **Unicode in arguments**: Depends on terminal encoding
- **Empty tags**: `--tag ""` creates empty string tag
- **Malformed `--env`**: Missing `=` causes parsing error
- **Negative timeout**: Accepted but may cause undefined behavior
- **Zero timeout**: Immediate timeout on ready-wait

## Recovery Procedures

### argparse error
If argparse shows confusing errors:
```bash
# Use explicit help
swarm <command> --help

# Check for missing --
swarm spawn --name test -- echo hello  # Note the --
```

### Wrong exit code in scripts
If scripts don't handle exit codes:
```bash
# Check exit code explicitly
swarm status test
echo "Exit code: $?"

# Or use shell conditionals
if swarm status test; then
    echo "Worker running"
else
    echo "Worker not running"
fi
```

## Implementation Notes

- **argparse version**: Uses Python's built-in argparse (no external dependencies)
- **Subcommand dispatch**: Uses `dest="command"` with `required=True` for mandatory subcommand
- **Remainder handling**: `nargs=argparse.REMAINDER` captures everything after `--`
- **Default values**: Stored in dataclasses, argparse defaults used for flags
- **stderr vs stdout**: Errors to stderr, output to stdout
- **Color output**: No ANSI color codes used in output (plain text only)
- **Interactive prompts**: None; all commands are non-interactive except `attach`
