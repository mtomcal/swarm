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

## Advanced Recipes

### Multi-Agent Code Review

Spawn specialized reviewers for different aspects of code quality:

```bash
# Spawn reviewers for different aspects
swarm spawn --name security-review --tmux --tag review -- claude 'Review for security vulnerabilities and best practices'
swarm spawn --name perf-review --tmux --tag review -- claude 'Review for performance bottlenecks and optimization opportunities'
swarm spawn --name style-review --tmux --tag review -- claude 'Review code style, naming conventions, and readability'

# Send the code to all reviewers
for reviewer in $(swarm ls --tag review --format names); do
    swarm send "$reviewer" "Review this code: $(cat feature.py)"
done

# Collect results
swarm ls --tag review
swarm logs security-review  # View security review output
```

### Parallel Feature Development

Create isolated worktrees for concurrent feature development:

```bash
# Create separate worktrees for each feature team
swarm spawn --name feat-auth --worktree --tmux --tag backend -- claude
swarm spawn --name feat-api --worktree --tmux --tag backend -- claude
swarm spawn --name feat-ui --worktree --tmux --tag frontend -- claude

# Each worker gets their own branch and directory
# Work can proceed in parallel without conflicts
swarm send feat-auth "Implement JWT authentication system"
swarm send feat-api "Build REST API endpoints"
swarm send feat-ui "Create login component"

# Monitor progress by team
swarm ls --tag backend
swarm ls --tag frontend
```

### Batch Processing with Ready Detection

Process multiple files or tasks with guaranteed readiness:

```bash
# Start processor with readiness detection
swarm spawn --name processor --tmux --ready-wait -- claude

# Process files sequentially with confirmation
for file in data/*.txt; do
    swarm send processor "Process $file and summarize results"
    # Wait for completion signal or use swarm wait
    sleep 2  # Adjust based on task complexity
done

# Clean up when done
swarm kill processor
```

### Integration with Beads Issue Tracking

Automate issue processing from beads:

```bash
# Get next task from beads and spawn dedicated worker
TASK=$(bd ready --json | jq -r '.[0].id')
swarm spawn --name "bd-$TASK" --worktree --tmux --ready-wait -- claude
swarm send "bd-$TASK" "bd show $TASK && /beads:full-cycle $TASK"

# Or process multiple issues in parallel
for id in $(bd ready --json | jq -r '.[].id' | head -5); do
    swarm spawn --name "worker-$id" --worktree --tmux --ready-wait -- claude
    swarm send "worker-$id" "/beads:implement-task $id"
done

# Wait for all to complete
swarm wait --all
```

### Continuous Integration Workflow

Set up automated testing and deployment workers:

```bash
# Spawn CI workers for different environments
swarm spawn --name test-unit --tmux --tag ci -- claude 'Run unit tests continuously'
swarm spawn --name test-integration --tmux --tag ci -- claude 'Run integration tests'
swarm spawn --name deploy-staging --tmux --tag deploy -- claude 'Deploy to staging on green tests'

# Trigger on git push - send to all CI workers
for worker in $(swarm ls --tag ci --format names); do
    swarm send "$worker" "Run tests for commit: $(git rev-parse HEAD)"
done
swarm wait --all  # Wait for tests to pass
swarm send deploy-staging "Deploy if tests passed"
```

### Remote Development Setup

Manage agents on remote machines via SSH:

```bash
# Spawn on remote host (requires tmux on remote)
ssh remote-host "swarm spawn --name remote-dev --tmux -- claude"

# Send work remotely
ssh remote-host "swarm send remote-dev 'Work on remote feature'"

# Attach from local machine
ssh -t remote-host "swarm attach remote-dev"
```

### Error Recovery and Monitoring

Build resilient multi-agent systems:

```bash
#!/bin/bash
# Monitor and respawn failed workers
while true; do
    for name in $(swarm ls --format names); do
        if ! swarm status "$name" > /dev/null; then
            echo "Respawning failed worker: $name"
            swarm respawn "$name" --clean-first
        fi
    done
    sleep 60  # Check every minute
done
```

### Load Balancing Tasks

Distribute work across available agents:

```bash
# Get available workers and distribute tasks
WORKERS=$(swarm ls --format names --status running)
TASKS=("task1" "task2" "task3" "task4" "task5")

i=0
for task in "${TASKS[@]}"; do
    worker=$(echo "$WORKERS" | sed -n "$((i % $(echo "$WORKERS" | wc -l) + 1))p")
    swarm send "$worker" "Process $task"
    ((i++))
done
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
