# Swarm

**Orchestrate AI coding agents at scale.**

Swarm is a process manager for AI agent CLIs that lets you run multiple autonomous agents in parallel, each in its own isolated git worktree. Think of it as `tmux` + `git worktree` + agent lifecycle management, designed for engineers who want to scale AI-assisted development beyond a single chat session.

## Why Swarm?

When working with AI coding agents like Claude Code, you're limited to one conversation at a time. Swarm removes that bottleneck:

- **Parallel execution** — Run 3, 5, or 10 agents simultaneously working on different tasks
- **Git isolation** — Each agent works in its own worktree/branch, eliminating merge conflicts
- **Persistent sessions** — Agents run in tmux, so you can detach and reconnect
- **Automatic recovery** — Ralph mode restarts agents with fresh context when they stall
- **Zero coordination overhead** — Agents don't know about each other; just fan out work and collect results

### Real-World Use Cases

1. **Batch processing issues** — Spawn one agent per bug/feature from your issue tracker
2. **Parallel code review** — Multiple agents review the same PR for security, performance, style
3. **Long-running tasks** — Let agents work overnight with Ralph's autonomous looping
4. **CI/CD integration** — Trigger agent pipelines from scripts

## Quick Start

### Installation

```bash
# Install (downloads swarm.py to ~/.local/bin)
curl -fsSL https://raw.githubusercontent.com/mtomcal/swarm/main/setup.sh | sh

# Or install manually
curl -fsSL https://raw.githubusercontent.com/mtomcal/swarm/main/swarm.py -o ~/.local/bin/swarm
chmod +x ~/.local/bin/swarm
```

### First Usage

```bash
# 1. Spawn an agent in an isolated worktree
swarm spawn --name agent1 --tmux --worktree -- claude --dangerously-skip-permissions
```

This creates:
- A new directory `myrepo-worktrees/agent1/` (git worktree)
- A new branch called `agent1` based on your current HEAD
- A tmux window where Claude is running

```bash
# 2. Send it work
swarm send agent1 "Fix the auth bug in src/auth.py"
```

The agent receives your prompt and starts working autonomously.

```bash
# 3. Monitor progress
swarm attach agent1      # Live view (Ctrl-B D to detach)
swarm logs agent1        # View output history
swarm status agent1      # Check if still running
```

> **⚠️ Security:** The `--dangerously-skip-permissions` flag enables autonomous operation by bypassing Claude's interactive prompts. See [Security Considerations](#security-considerations) for sandboxing options.

## Core Concepts

### Worktree Isolation

Each `--worktree` worker gets its own git branch and working directory. This is the key to running agents in parallel without conflicts:

```bash
swarm spawn --name feature-auth --tmux --worktree -- claude --dangerously-skip-permissions
# Creates: ~/code/myrepo-worktrees/feature-auth/
# On branch: feature-auth (branched from current HEAD)
```

Workers can commit, push, and even create PRs independently. When done, clean up with:

```bash
swarm kill feature-auth --rm-worktree  # Removes worker + worktree + branch
```

### Readiness Detection

Swarm detects when an agent CLI is ready for input by watching for prompt patterns like `$`, `>`, or `#` in the tmux output. Use `--ready-wait` to block until the agent signals readiness:

```bash
swarm spawn --name w1 --tmux --worktree --ready-wait -- claude --dangerously-skip-permissions
swarm send w1 "Start working"  # Safe—agent is definitely ready
```

Without `--ready-wait`, you risk sending prompts before the agent has fully initialized, causing them to be lost. This is essential for scripted workflows where you need to send prompts immediately after spawn.

### Tmux Integration

All `--tmux` workers run in named tmux windows. You can:

```bash
swarm attach agent1          # Interactive view (Ctrl-B D to detach)
swarm logs agent1            # Dump scrollback buffer
swarm logs -f agent1         # Follow output in real-time
```

Workers persist across SSH disconnects. Reattach anytime with `swarm attach`.

## Usage Patterns

### Parallel Task Processing

Fan out work across multiple agents, one per task:

```bash
#!/bin/bash
# Process 3 tasks in parallel
TASKS=("fix-auth-bug" "add-logging" "update-docs")

for task in "${TASKS[@]}"; do
    swarm spawn --name "$task" --tmux --worktree --ready-wait -- claude --dangerously-skip-permissions
    swarm send "$task" "Complete the task described in tasks/$task.md"
done

# Wait for all to finish
swarm wait --all

# Review results in each worktree, then clean up
for task in "${TASKS[@]}"; do
    echo "=== $task ===" && git -C "../myrepo-worktrees/$task" log --oneline -3
done

swarm clean --all --rm-worktree
```

### Broadcasting to All Workers

```bash
swarm send --all "/status"       # Check status of all agents
swarm interrupt --all            # Send Ctrl-C to all workers
```

### Organizing with Tags

```bash
swarm spawn --name w1 --tag team-a --tag urgent --tmux -- claude --dangerously-skip-permissions
swarm spawn --name w2 --tag team-a --tmux -- claude --dangerously-skip-permissions
swarm spawn --name w3 --tag team-b --tmux -- claude --dangerously-skip-permissions

swarm ls --tag team-a            # List only team-a workers
```

## Command Reference

### Basic Commands

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

### Subcommand Groups

| Group | Description | Subcommands |
|-------|-------------|-------------|
| `ralph` | Autonomous looping | `spawn` `run` `init` `status` `pause` `resume` `list` `ls` `clean` |
| `heartbeat` | Rate limit recovery | `start` `stop` `list` `status` `pause` `resume` |

## Ralph Mode (Autonomous Looping)

For long-running tasks, Ralph mode automatically restarts agents when they stall or hit context limits. Each restart gets a fresh context window while preserving work through git commits.

Based on the [Ralph Wiggum technique](https://github.com/ghuntley/how-to-ralph-wiggum).

### Basic Usage

```bash
# Create a prompt file that will be re-read each iteration
cat > PROMPT.md << 'EOF'
You are working on a large refactoring task.

1. Read PROGRESS.md to see what's been done
2. Continue the next item on the checklist
3. Commit your changes with a descriptive message
4. Update PROGRESS.md
5. Say "/done" if everything is complete

If you get stuck, say "/stuck" with details.
EOF

# Start the loop (max 20 iterations)
swarm ralph spawn --name refactor --prompt-file ./PROMPT.md --max-iterations 20 -- claude --dangerously-skip-permissions

# Monitor
swarm ralph status refactor    # Check iteration count, status
swarm attach refactor          # Watch live (Ctrl-B D to detach)
tail -f ~/.swarm/ralph/refactor/iterations.log  # Iteration history
```

### How It Works

1. Each iteration reads your prompt file and sends it to a fresh agent
2. The agent works until it exits or goes inactive (no output for 180s by default)
3. Loop restarts with fresh context, re-reading the prompt file
4. Stops when: max iterations reached, `--done-pattern` matched, or 5 consecutive failures

### Key Options

| Flag | Default | Description |
|------|---------|-------------|
| `--prompt-file` | required | Prompt sent each iteration |
| `--max-iterations` | unlimited | Stop after N iterations |
| `--inactivity-timeout` | 180s | Restart after N seconds of no output |
| `--done-pattern` | none | Regex to stop loop when matched |

### Controlling the Loop

```bash
swarm ralph pause refactor     # Pause after current iteration
swarm ralph resume refactor    # Continue paused loop
swarm ralph list               # List all ralph workers with status
swarm ralph ls                 # Alias for ralph list
swarm ralph clean refactor     # Remove ralph state for a worker
swarm ralph clean --all        # Remove all ralph state
swarm kill refactor            # Stop immediately
```

### Caveats

**Done pattern + prompt content**: When using `--done-pattern` with `--check-done-continuous`, the pattern must NOT appear literally in your prompt file. The prompt text is typed into the terminal, and the done pattern scans the full buffer — including the prompt. Use a unique signal pattern (e.g., `SWARM_DONE_X9K`).

**Docker sandbox**: If using `sandbox.sh`, ensure `docker run --rm -it` (needs `-it` for TTY). Fresh containers need theme pre-configuration in the Dockerfile to avoid the first-time theme picker. Omit `--worktree` with Docker (Docker provides its own isolation).

## Heartbeat (Rate Limit Recovery)

When agents hit API rate limits, they pause and wait. Rate limits often renew on fixed intervals (e.g., every 4 hours). Heartbeat sends periodic nudges to workers, prompting them to retry when limits renew.

### Basic Usage

```bash
# Start heartbeat for running worker (nudge every 4 hours, stop after 24h)
swarm heartbeat start agent --interval 4h --expire 24h

# Or attach heartbeat at spawn time
swarm spawn --name agent --tmux --worktree --heartbeat 4h --heartbeat-expire 24h -- claude --dangerously-skip-permissions

# Monitor heartbeats
swarm heartbeat list                     # List all heartbeats
swarm heartbeat status agent             # Detailed status for one worker
```

### How It Works

- If the agent is stuck on a rate limit, the nudge prompts it to retry
- If the agent is working normally, it ignores the nudge
- If the agent has exited, the nudge has no effect

The default message is "continue", or customize with `--message "please continue"`.

### Key Options

| Flag | Default | Description |
|------|---------|-------------|
| `--interval` | required | Time between nudges (e.g., "4h", "30m") |
| `--expire` | never | Stop heartbeat after duration |
| `--message` | "continue" | Message to send on each beat |

### Controlling Heartbeats

```bash
swarm heartbeat pause agent    # Pause temporarily
swarm heartbeat resume agent   # Resume
swarm heartbeat stop agent     # Stop permanently
```

## Orchestration via ORCHESTRATOR.md

For multi-stage tasks (plan → build → validate), use an **ORCHESTRATOR.md** document instead of code-level pipeline orchestration. A human or director agent reads the document and composes existing swarm primitives (`ralph`, `spawn`, `send`, `heartbeat`) in real-time.

This approach is simpler, more flexible, and follows Unix philosophy: keep primitives simple, compose via documents. See [`docs/autonomous-loop-guide.md`](docs/autonomous-loop-guide.md) for a full guide.

## Integration Examples

### Issue Tracker Integration

Connect swarm to your issue tracker for automated task processing:

```bash
#!/bin/bash
# Example: Process GitHub issues labeled "ai-task"
for issue in $(gh issue list --label ai-task --json number -q '.[].number' | head -3); do
    swarm spawn --name "issue-$issue" --tmux --worktree --ready-wait -- claude --dangerously-skip-permissions
    swarm send "issue-$issue" "Fix GitHub issue #$issue. Read it with: gh issue view $issue"
done

swarm wait --all
swarm clean --all --rm-worktree
```

### Parallel Code Review

Multiple agents review different aspects of the same code:

```bash
#!/bin/bash
PR_NUM=123

for aspect in security performance readability; do
    swarm spawn --name "review-$aspect" --tmux --ready-wait -- claude --dangerously-skip-permissions
    swarm send "review-$aspect" "Review PR #$PR_NUM focusing on $aspect. Run: gh pr diff $PR_NUM"
done

# Wait and collect results
swarm wait --all
for aspect in security performance readability; do
    echo "=== $aspect review ===" >> review-summary.md
    swarm logs "review-$aspect" >> review-summary.md
done

swarm clean --all
```

### Respawn Failed Workers

```bash
#!/bin/bash
# Check all workers and restart any that died
for name in $(swarm ls --format names); do
    if ! swarm status "$name" 2>/dev/null; then
        echo "Respawning failed worker: $name"
        swarm respawn "$name" --clean-first
    fi
done
```

## State & Logs

All state is stored in `~/.swarm/`:

```
~/.swarm/
├── state.json                        # Worker registry
├── logs/
│   └── <worker>.{stdout,stderr}.log  # Background process output
├── ralph/
│   └── <worker>/
│       ├── state.json                # Loop state (iteration, status)
│       └── iterations.log            # Timestamped iteration history
└── heartbeats/
    └── <worker>.json                 # Heartbeat state (interval, beats sent)
```

Useful debugging commands:

```bash
cat ~/.swarm/state.json | jq .                     # View all workers
swarm logs worker1                                  # Tmux scrollback
tail -f ~/.swarm/ralph/agent/iterations.log         # Watch Ralph progress
swarm heartbeat list                                # Check heartbeat status
```

## Security Considerations

Running autonomous AI agents requires careful thought about permissions and isolation.

### The Permission Tradeoff

Claude Code normally prompts for confirmation before running commands, editing files, or making network requests. The `--dangerously-skip-permissions` flag bypasses these prompts—**required for autonomous operation**, but it means agents can:

- Execute arbitrary shell commands
- Read, write, and delete any accessible files
- Make network requests
- Install packages

### Mitigation Strategies

**1. Worktree Isolation (Built-in)**

Always use `--worktree`. Each agent works in its own directory and branch, limiting blast radius.

**2. Docker Isolation (Recommended)**

Use `sandbox.sh` to run workers inside Docker containers with resource limits and network lockdown:

```bash
# Scaffold sandbox files
swarm init --with-sandbox

# Build image and set up network
docker build --build-arg USER_ID=$(id -u) --build-arg GROUP_ID=$(id -g) \
    -t sandbox-loop -f Dockerfile.sandbox .
sudo ./setup-sandbox-network.sh    # iptables allowlist (does not survive reboot)

# Run sandboxed worker
swarm ralph spawn --name dev --prompt-file PROMPT.md --max-iterations 50 \
    -- ./sandbox.sh --dangerously-skip-permissions
```

Provides hard memory caps (OOM kills container, not host), network allowlist, and filesystem isolation.

### Best Practices

1. **Use disposable environments** — VMs, containers, or cloud instances you can destroy
2. **Set iteration limits** — `--max-iterations` in Ralph prevents runaway loops
3. **Monitor activity** — `swarm attach` or `swarm logs -f` to watch agents
4. **Review before merge** — Treat all agent commits as untrusted code

## Requirements

| Dependency | Required For | Verify With |
|------------|--------------|-------------|
| Python 3.10+ | Core functionality | `python3 --version` |
| tmux | `--tmux` mode (recommended) | `tmux -V` |
| git | `--worktree` mode | `git --version` |

### Installing Dependencies

**macOS:**
```bash
brew install tmux git python@3.10
```

**Ubuntu/Debian:**
```bash
sudo apt update && sudo apt install -y tmux git python3
```

**Fedora/RHEL:**
```bash
sudo dnf install -y tmux git python3
```

## Troubleshooting

**Worker exits immediately after spawn**
- Check `swarm logs <name>` for error output
- Verify the command works when run directly
- Ensure tmux is installed: `tmux -V`

**Agent not receiving prompts**
- Use `--ready-wait` to ensure agent is ready before sending
- Check if agent is in a different state: `swarm attach <name>`

**Worktree cleanup fails**
- Dirty worktrees (uncommitted changes) block removal by default
- Use `--force-dirty` to override, or commit/discard changes first
- Manual cleanup: `git worktree remove <path>`

**Ralph loop stops unexpectedly**
- Check `~/.swarm/ralph/<name>/state.json` for failure count
- View iteration history: `cat ~/.swarm/ralph/<name>/iterations.log`
- 5 consecutive failures trigger automatic stop

**Heartbeat not sending**
- Check status: `swarm heartbeat status <worker>`
- Verify worker is tmux-based (heartbeat requires tmux)
- Stop and restart: `swarm heartbeat stop <w> && swarm heartbeat start <w> --interval 4h`

## Contributing

See the `specs/` directory for behavioral specifications that document expected behavior. When adding features:

1. Write a spec in `specs/<feature>.md` following the template in `specs/README.md`
2. Add tests in `test_cmd_<feature>.py`
3. Implement in `swarm.py`

## License

MIT
