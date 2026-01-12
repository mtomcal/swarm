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

Swarm integrates seamlessly with [beads](https://github.com/steveyegge/beads) for issue-driven development workflows.

#### Issue-Per-Worker Pattern

Each beads issue gets its own swarm worker with isolated worktree:
- Worker name matches issue ID for easy tracking
- Branch name matches issue ID
- Automatic worktree cleanup when work completes

```bash
# Start worker for specific issue
swarm spawn --name "bd-swarm-mlm.3" --tmux --worktree --ready-wait -- claude
swarm send "bd-swarm-mlm.3" "/beads:full-cycle swarm-mlm.3"
```

#### Automated Task Assignment

Script that pulls ready issues from beads and spawns workers automatically:

```bash
#!/bin/bash
# Process up to 3 ready issues in parallel
for id in $(bd ready --json | jq -r '.[].id' | head -3); do
    echo "Starting worker for issue $id"
    swarm spawn --name "bd-$id" --tmux --worktree --ready-wait -- claude
    swarm send "bd-$id" "/beads:full-cycle $id"
done

# Wait for all to complete
swarm wait --all

# Clean up completed workers and their worktrees
swarm clean --all
```

#### Session Completion Integration

Swarm workers should complete the full beads workflow before exit:

```bash
# Inside worker session - complete the cycle
/beads:full-cycle swarm-mlm.3

# Then land the plane (commit, push, close issue)
/commit "Document swarm + beads integration patterns"
/push
bd close swarm-mlm.3
```

#### Parallel Review Pattern

Multiple workers can review the same work simultaneously:

```bash
# Start parallel reviewers for a PR/issue
ISSUE="swarm-mlm.3"
for aspect in security performance style; do
    swarm spawn --name "review-$aspect" --tmux --ready-wait -- claude
    swarm send "review-$aspect" "Review $ISSUE focusing on $aspect aspects. Run: bd show $ISSUE"
done

# Collect results
for aspect in security performance style; do
    swarm logs "review-$aspect" > "review-$aspect.log"
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
