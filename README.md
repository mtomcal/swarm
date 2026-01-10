# swarm

Unix-style process manager for AI agent CLIs. Spawn, track, and control multiple agent processes via tmux.

## Philosophy

**Do one thing well.** Swarm manages process lifecycles—nothing more. It doesn't understand your task tracker, your orchestration logic, or your agent framework. Compose it with other tools via shell scripts.

```bash
# Swarm + your tools = your orchestration
for task in $(your-task-tool list --ready | head -3); do
    swarm spawn --name "w-$task" --tmux --worktree -- claude
    swarm send "w-$task" "/implement $task"
done
swarm wait --all
swarm clean --all
```

## Install

```bash
# Single file, no dependencies beyond Python stdlib
cp swarm.py ~/.local/bin/swarm
chmod +x ~/.local/bin/swarm
```

Requires: Python 3.10+, tmux (for `--tmux` mode), git (for `--worktree` mode)

## Quick Start

```bash
# Spawn an agent in tmux with isolated worktree
swarm spawn --name agent1 --tmux --worktree -- claude

# Send a command to it
swarm send agent1 "Fix the auth bug in login.py"

# Check status
swarm ls

# Attach to watch it work
swarm attach agent1

# When done, clean up
swarm kill agent1 --rm-worktree
```

## Commands

| Command | Purpose |
|---------|---------|
| `spawn` | Create worker (tmux window or background process) |
| `ls` | List workers (`--format json\|table\|names`) |
| `status` | Check if worker is running (exit codes: 0=running, 1=stopped, 2=not found) |
| `send` | Send text to tmux worker (`--all` for broadcast) |
| `interrupt` | Send Ctrl-C |
| `eof` | Send Ctrl-D |
| `attach` | Connect to tmux window |
| `logs` | View output (`-f` to follow) |
| `kill` | Terminate process (`--rm-worktree` to clean worktree) |
| `wait` | Block until worker exits (`--all`, `--timeout`) |
| `clean` | Remove stopped workers from state |
| `respawn` | Restart dead worker with original config |

## Spawning Options

```bash
# Tmux window (interactive, capturable)
swarm spawn --name w1 --tmux -- claude

# Tmux + isolated git worktree
swarm spawn --name w1 --tmux --worktree -- claude

# Background process (logs to ~/.swarm/logs/)
swarm spawn --name w1 -- ./my-script.sh

# With environment variables
swarm spawn --name w1 --env MODEL=opus --env DEBUG=1 --tmux -- claude

# With tags for filtering
swarm spawn --name w1 --tag team-a --tag priority -- claude
swarm ls --tag team-a
```

## Composition Examples

**Fan-out pattern:**
```bash
#!/bin/bash
# Spawn workers for each ready task
for id in $(task-tool list --ready); do
    swarm spawn --name "w-$id" --tmux --worktree -- claude
    swarm send "w-$id" "/work-on $id"
done

# Wait for all, then clean up
swarm wait --all
swarm clean --all --rm-worktree
```

**Pipeline pattern:**
```bash
#!/bin/bash
# Get names of running workers, pipe to another tool
swarm ls --format names | xargs -I{} echo "Worker {} is active"
```

**Respawn on failure:**
```bash
#!/bin/bash
# Check and respawn dead workers
for name in $(swarm ls --format names); do
    if ! swarm status "$name" >/dev/null 2>&1; then
        swarm respawn "$name" --clean-first
    fi
done
```

## State & Logs

```
~/.swarm/
├── state.json              # Worker registry
└── logs/
    ├── worker1.stdout.log  # Background process stdout
    └── worker1.stderr.log  # Background process stderr
```

Tmux workers capture output in the tmux scrollback buffer—use `swarm logs` to view.

## Exit Codes

- `0` - Success
- `1` - Worker stopped / operation failed
- `2` - Worker not found

## Why Swarm?

Building AI tooling often means running multiple agent processes—each potentially needing:
- Isolated git branches (no merge conflicts)
- Interactive tmux sessions (for debugging)
- Process lifecycle tracking (who's alive?)
- Graceful shutdown and cleanup

Swarm handles these concerns without dictating your orchestration logic. It's a sharp knife, not a framework.

## License

MIT
