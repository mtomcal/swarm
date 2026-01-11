# swarm

Process manager for AI agent CLIs. Spawn, track, and control multiple agents via tmux with git worktree isolation.

**Key features:** Process lifecycle management • Worktree isolation per worker • Tmux integration • Readiness detection

## Quick Start

```bash
# Install
curl -fsSL https://raw.githubusercontent.com/mtomcal/swarm/main/setup.sh | sh

# Spawn an agent in an isolated worktree
swarm spawn --name agent1 --tmux --worktree -- claude

# Send work and monitor
swarm send agent1 "Fix the auth bug"
swarm attach agent1
```

## Power User Workflows

### Multi-Agent Parallel Development

Fan out work across multiple isolated agents:

```bash
for task in $(bd ready --format=ids | head -3); do
    swarm spawn --name "w-$task" --tmux --worktree --ready-wait -- claude
    swarm send "w-$task" "/beads:implement-task $task"
done
swarm wait --all
swarm clean --all --rm-worktree
```

### Worktree Isolation

Each `--worktree` worker gets its own git branch and directory, preventing merge conflicts:

```bash
swarm spawn --name feature-auth --tmux --worktree -- claude
# Creates: <repo>-worktrees/feature-auth on branch 'feature-auth'
```

### Readiness Detection

Use `--ready-wait` to block until the agent is ready for input:

```bash
swarm spawn --name w1 --tmux --ready-wait -- claude --dangerously-skip-permissions
swarm send w1 "Start working immediately"  # Safe—agent is ready
```

### Broadcasting

Send commands to all running workers:

```bash
swarm send --all "/status"
swarm interrupt --all  # Ctrl-C all workers
```

### Worker Tags

Organize workers with tags for filtering:

```bash
swarm spawn --name w1 --tag team-a --tag urgent --tmux -- claude
swarm ls --tag team-a  # Filter workers by tag
```

## Command Reference

| Command | Description | Key Flags |
|---------|-------------|-----------|
| `spawn` | Create worker process | `--tmux` `--worktree` `--ready-wait` `--tag` `--env` |
| `ls` | List workers | `--format json\|table\|names` `--tag` |
| `status` | Check worker state | Exit: 0=running, 1=stopped, 2=not found |
| `send` | Send text to worker | `--all` `--no-enter` |
| `attach` | Connect to tmux window | |
| `logs` | View worker output | `-f` (follow) |
| `wait` | Block until exit | `--all` `--timeout` |
| `kill` | Terminate worker | `--rm-worktree` |
| `clean` | Remove stopped workers | `--all` `--rm-worktree` |
| `interrupt` | Send Ctrl-C | `--all` |
| `eof` | Send Ctrl-D | |
| `respawn` | Restart dead worker | `--clean-first` |

## Integration Patterns

### With Beads (Issue Tracking)

```bash
# Process ready issues in parallel
for id in $(bd ready --format=ids); do
    swarm spawn --name "bd-$id" --tmux --worktree --ready-wait -- claude
    swarm send "bd-$id" "/beads:full-cycle $id"
done
```

### With Git Worktrees

Swarm creates worktrees in `<repo>-worktrees/<worker-name>`:

```bash
swarm spawn --name feature-x --tmux --worktree -- claude
# Worktree: ~/code/myrepo-worktrees/feature-x
# Branch: feature-x (created from current branch)
```

### Scripted Orchestration

```bash
#!/bin/bash
# Respawn any failed workers
for name in $(swarm ls --format names); do
    swarm status "$name" || swarm respawn "$name" --clean-first
done
```

## State & Logs

```
~/.swarm/
├── state.json              # Worker registry
└── logs/
    ├── worker1.stdout.log  # Background process output
    └── worker1.stderr.log
```

Tmux workers use scrollback buffer—access via `swarm logs <name>`.

## Requirements

- Python 3.10+
- tmux (for `--tmux` mode)
- git (for `--worktree` mode)

## License

MIT
