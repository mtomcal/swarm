# Environment Requirements

## Overview

Swarm requires a Unix-like environment with Python 3.10+, optional tmux for interactive worker management, and optional git for worktree isolation. This spec documents all external dependencies, directory structures, and system requirements needed to run Swarm.

## Dependencies

- **External**:
  - Python 3.10+ (required)
  - tmux (optional, for `--tmux` mode)
  - git (optional, for `--worktree` mode)
  - Unix-like OS with fcntl support (required)
  - curl or wget (for installation script)
- **Internal**: None (foundational spec)

## Behavior

### Python Requirements

**Description**: Swarm is a single-file Python script with no external pip dependencies.

**Minimum Version**: Python 3.10

**Required Standard Library Modules**:
| Module | Purpose |
|--------|---------|
| `argparse` | CLI argument parsing |
| `fcntl` | File locking (Unix-only) |
| `hashlib` | Session name hashing |
| `json` | State file serialization |
| `os` | Environment and path operations |
| `shlex` | Shell command parsing |
| `signal` | Process signal handling |
| `subprocess` | External command execution |
| `sys` | Exit codes and stderr |
| `time` | Sleep and timeout handling |
| `contextlib` | Context managers |
| `dataclasses` | Data structure definitions |
| `datetime` | Timestamp generation |
| `pathlib` | Path manipulation |
| `typing` | Type hints |

**Python Features Used**:
- Dataclasses with default_factory
- Type hints including `list[str]`, `dict[str, str]`, `Optional[T]`
- Context managers via `@contextmanager`
- f-strings
- Walrus operator (`:=`)

### tmux Requirements

**Description**: tmux is required for `--tmux` mode which enables interactive worker management.

**Minimum Version**: No specific version required, but must support:
- `new-session` with `-d` (detached)
- `new-window` with `-t` and `-n`
- `kill-window`
- `kill-session`
- `send-keys` with `-l` (literal)
- `capture-pane` with `-p`, `-S`, `-E`
- `list-windows` with `-F`
- `select-window`
- `-L` socket option

**Features Used**:
| Command | Purpose |
|---------|---------|
| `tmux new-session -d -s <name>` | Create detached session |
| `tmux new-window -t <session> -n <name>` | Create named window |
| `tmux send-keys -t <session>:<window> -l <text>` | Send text literally |
| `tmux send-keys -t <session>:<window> Enter` | Send Enter key |
| `tmux send-keys -t <session>:<window> C-c` | Send Ctrl-C |
| `tmux send-keys -t <session>:<window> C-d` | Send Ctrl-D |
| `tmux capture-pane -t <session>:<window> -p` | Capture visible pane |
| `tmux capture-pane -t <session>:<window> -p -S -<N>` | Capture with scrollback |
| `tmux kill-window -t <session>:<window>` | Kill specific window |
| `tmux kill-session -t <session>` | Kill entire session |
| `tmux list-windows -t <session> -F "#{window_name}"` | List window names |
| `tmux select-window -t <session>:<window>` | Select window before attach |
| `tmux attach -t <session>` | Attach to session interactively |
| `tmux -L <socket>` | Use custom socket path |

**Error Conditions**:
| Condition | Behavior |
|-----------|----------|
| tmux not installed | `--tmux` fails with "tmux is required" error |
| tmux session doesn't exist | Commands fail with tmux error |

### git Requirements

**Description**: git is required for `--worktree` mode which provides branch isolation.

**Minimum Version**: Must support worktree commands (git 2.5+)

**Features Used**:
| Command | Purpose |
|---------|---------|
| `git rev-parse --show-toplevel` | Find repository root |
| `git worktree add <path> -b <branch>` | Create worktree with new branch |
| `git worktree remove <path>` | Remove worktree |
| `git worktree remove --force <path>` | Force remove dirty worktree |
| `git status --porcelain` | Check for uncommitted changes |
| `git branch -d <branch>` | Delete branch after worktree removal |

**Error Conditions**:
| Condition | Behavior |
|-----------|----------|
| git not installed | `--worktree` fails with error |
| Not in git repository | `--worktree` fails with "not a git repository" error |
| Branch already exists | `--worktree` may fail depending on git behavior |

### Operating System Requirements

**Description**: Swarm requires a Unix-like operating system due to fcntl file locking.

**Supported Platforms**:
- Linux (tested)
- macOS (tested)

**Unsupported Platforms**:
- Windows (fcntl not available)
- Windows Subsystem for Linux may work but is untested

**System Calls Used**:
| Call | Purpose |
|------|---------|
| `fcntl.flock(LOCK_EX)` | Exclusive file locking |
| `fcntl.flock(LOCK_UN)` | Lock release |
| `os.execvp()` | Replace process for tmux attach |
| `os.kill()` | Send signals to processes |
| `signal.SIGTERM` | Graceful termination signal |
| `signal.SIGKILL` | Force termination signal |

### Directory Structure

**Description**: Swarm creates and uses directories under `~/.swarm/`.

**Directory Layout**:
```
~/.swarm/
├── state.json      # Worker registry
├── state.lock      # Lock file for concurrent access
└── logs/
    ├── <worker>.stdout.log  # stdout for non-tmux workers
    └── <worker>.stderr.log  # stderr for non-tmux workers
```

**Inputs**:
- None (uses hardcoded paths based on `$HOME`)

**Outputs**:
- Directories created on first use via `mkdir -p` equivalent

**Side Effects**:
- Creates `~/.swarm/` directory
- Creates `~/.swarm/logs/` directory

**Environment Variable Override**:
- No override available; paths are hardcoded to `$HOME/.swarm/`

### Installation

**Description**: Swarm can be installed via curl or wget from GitHub.

**Installation Command**:
```bash
curl -fsSL https://raw.githubusercontent.com/mtomcal/swarm/main/setup.sh | sh
```

Or with wget:
```bash
wget -qO- https://raw.githubusercontent.com/mtomcal/swarm/main/setup.sh | sh
```

**Installation Directory**:
- Default: `~/.local/bin/swarm`
- Override via `SWARM_INSTALL_DIR` environment variable

**Post-Installation**:
- Add `~/.local/bin` to PATH if not already present

**Installation Script Behavior**:
1. Creates `~/.local/bin/` if needed
2. Downloads `swarm.py` from GitHub
3. Renames to `swarm` (no extension)
4. Makes executable (`chmod +x`)
5. Prints PATH instructions if needed

## Scenarios

### Scenario: Fresh installation on Linux
- **Given**: Clean Linux system with Python 3.10+, tmux, git
- **When**: Installation script is run
- **Then**:
  - swarm installed to `~/.local/bin/swarm`
  - `swarm --help` displays usage

### Scenario: First run creates directories
- **Given**: swarm installed, `~/.swarm/` doesn't exist
- **When**: Any swarm command is run (e.g., `swarm ls`)
- **Then**:
  - `~/.swarm/` directory created
  - `~/.swarm/logs/` directory created
  - Empty state initialized

### Scenario: tmux not installed
- **Given**: System without tmux installed
- **When**: `swarm spawn --name test --tmux -- bash`
- **Then**:
  - Error message: "tmux is required for --tmux mode"
  - Exit code: non-zero

### Scenario: git not installed
- **Given**: System without git installed
- **When**: `swarm spawn --name test --worktree -- bash`
- **Then**:
  - Error message indicates git required
  - Exit code: non-zero

### Scenario: Not in git repository
- **Given**: Current directory is not a git repository
- **When**: `swarm spawn --name test --worktree -- bash`
- **Then**:
  - Error message: "not a git repository"
  - Exit code: non-zero

### Scenario: Run on macOS
- **Given**: macOS system with Python 3.10+, tmux, git
- **When**: swarm commands are run
- **Then**:
  - All features work correctly
  - fcntl locking works on APFS/HFS+

### Scenario: Custom installation directory
- **Given**: `SWARM_INSTALL_DIR=/opt/bin`
- **When**: Installation script is run
- **Then**:
  - swarm installed to `/opt/bin/swarm`

## Edge Cases

- **HOME not set**: Swarm will fail to determine state directory
- **Read-only home directory**: State file operations will fail
- **Disk full**: State file save will fail
- **tmux socket permissions**: Custom sockets need appropriate permissions
- **git hooks**: Pre-commit hooks may affect worktree operations
- **Python version**: Older Python 3 versions will fail on type hint syntax
- **Multiple Python versions**: shebang line uses `#!/usr/bin/env python3`

## Recovery Procedures

### tmux session in bad state

If tmux session becomes corrupted:
```bash
# List all sessions
tmux list-sessions

# Kill problematic session
tmux kill-session -t <session-name>

# Clean up swarm state
swarm clean --all
```

### Orphaned worktrees

If worktrees exist but not in swarm state:
```bash
# List git worktrees
git worktree list

# Remove orphaned worktree manually
git worktree remove <path>
```

### Permission issues

If swarm directories have wrong permissions:
```bash
# Fix permissions
chmod 700 ~/.swarm
chmod 600 ~/.swarm/state.json
chmod 600 ~/.swarm/state.lock
```

### Reinstallation

To reinstall swarm:
```bash
# Remove existing
rm ~/.local/bin/swarm

# Reinstall
curl -fsSL https://raw.githubusercontent.com/mtomcal/swarm/main/setup.sh | sh
```

## Implementation Notes

- **Single file**: Swarm is designed as a single Python file with no dependencies for easy installation and portability
- **No virtual environment**: No pip packages required, uses only standard library
- **Portable paths**: Uses `pathlib.Path.home()` for cross-platform home directory detection
- **Shebang**: Uses `#!/usr/bin/env python3` for Python discovery
- **Exit codes**: Standard Unix exit code conventions (0=success, non-zero=failure)
