# Swarm

> [!CAUTION]
> **Swarm is a research project. If your name is not Michael Tomcal then do not use.** Feel free to grab the specs and build your own. This software is experimental, unstable, and under active development. APIs will change without notice. Features may be incomplete or broken. There is no support, no documentation guarantees, and no warranty of any kind. Use at your own risk.

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
swarm peek agent1        # Quick look at terminal output (last 30 lines)
swarm status agent1      # Check if still running
swarm attach agent1      # Live view (Ctrl-B D to detach)
swarm logs agent1        # View output history
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
| `spawn` | Create worker process | `--tmux` `--worktree` `--ready-wait` `--tag` `--env` `--heartbeat` |
| `ls` | List workers | `--format json\|table\|names` `--status running\|stopped` `--tag` |
| `status` | Check worker state | Exit: 0=running, 1=stopped, 2=not found |
| `peek` | View terminal output | `-n/--lines` (default: 30) `--all` |
| `send` | Send text to worker | `--all` `--no-enter` |
| `attach` | Connect to tmux window | |
| `logs` | View worker output | `-f` (follow) `--history` `--lines` |
| `wait` | Block until exit | `--all` `--timeout` |
| `kill` | Terminate worker | `--rm-worktree` `--force-dirty` `--all` |
| `clean` | Remove stopped workers | `--all` `--rm-worktree` `--force-dirty` |
| `interrupt` | Send Ctrl-C | `--all` |
| `eof` | Send Ctrl-D | |
| `respawn` | Restart dead worker | `--clean-first` `--force-dirty` |

### Subcommand Groups

| Group | Description | Subcommands |
|-------|-------------|-------------|
| `ralph` | Autonomous looping | `spawn` `run` `init` `status` `logs` `pause` `resume` `list` `ls` `clean` |
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
swarm ralph status refactor    # Iteration count, ETA, status
swarm peek refactor            # Quick look at terminal output
swarm ralph logs refactor      # Iteration history
swarm ralph logs refactor --live  # Tail iteration log in real-time
swarm attach refactor          # Full interactive view (Ctrl-B D to detach)
```

`swarm ralph spawn` starts the monitoring loop in the background and returns immediately — you can start monitoring right away.

### How It Works

1. Each iteration reads your prompt file from disk and sends it to a fresh agent
2. The agent works until it exits or goes inactive (no output for 180s by default)
3. Loop restarts with fresh context, re-reading the prompt file (you can edit it mid-loop)
4. The same worktree is reused across iterations — work persists through git commits
5. Stops when: max iterations reached, `--done-pattern` matched, or 5 consecutive failures

### Key Options

| Flag | Default | Description |
|------|---------|-------------|
| `--prompt-file` | required | Prompt sent each iteration |
| `--max-iterations` | unlimited | Stop after N iterations |
| `--inactivity-timeout` | 180s | Restart after N seconds of no output |
| `--done-pattern` | none | Regex to stop loop when matched |
| `--check-done-continuous` | off | Check done pattern during iteration, not just after exit |
| `--foreground` | off | Block while the loop runs (for human terminal use) |
| `--replace` | off | Auto-clean existing worker before spawning |
| `--clean-state` | off | Reset ralph state only (keep worker/worktree) |
| `--no-run` | off | Spawn worker without starting the monitoring loop |

### Monitoring the Loop

```bash
swarm ralph status refactor    # Iteration progress + ETA (calculated from iteration durations)
swarm peek refactor            # Last 30 lines of terminal output
swarm peek refactor -n 100    # Last 100 lines
swarm ralph logs refactor      # Iteration history (start/stop/exit reasons)
swarm ralph logs refactor --live  # Tail iteration log in real-time
swarm attach refactor          # Full interactive tmux view
```

`swarm peek` is the fastest way to see what the agent is doing right now without risk of accidentally sending keystrokes (unlike `attach`).

### Controlling the Loop

```bash
swarm ralph pause refactor     # Pause after current iteration
swarm ralph resume refactor    # Continue paused loop
swarm ralph list               # List all ralph workers with status
swarm ralph ls                 # Alias for ralph list
swarm ralph clean refactor     # Remove ralph state for a worker
swarm ralph clean --all        # Remove all ralph state
swarm kill refactor            # Stop immediately
swarm kill refactor --rm-worktree  # Stop + remove worktree + ralph state
```

### Advanced Ralph Usage

**Foreground mode** (blocks until loop finishes — useful in a dedicated terminal):

```bash
swarm ralph spawn --name agent --prompt-file ./PROMPT.md --max-iterations 50 --foreground \
    -- claude --dangerously-skip-permissions
```

**Spawn without starting the loop** (manual two-step workflow):

```bash
# Step 1: Create worker only
swarm ralph spawn --name agent --prompt-file ./PROMPT.md --max-iterations 50 --no-run \
    -- claude --dangerously-skip-permissions

# Step 2: Start the monitoring loop later
swarm ralph run agent
```

**Replace an existing worker** (auto-cleans worker, worktree, and ralph state):

```bash
swarm ralph spawn --name agent --replace --prompt-file ./PROMPT.md --max-iterations 50 \
    -- claude --dangerously-skip-permissions
```

**Attach heartbeat for rate limit recovery**:

```bash
swarm ralph spawn --name agent --prompt-file ./PROMPT.md --heartbeat 4h --heartbeat-expire 24h \
    -- claude --dangerously-skip-permissions
```

### Stuck Worker Detection

Ralph detects common stuck states during the first iteration and logs warnings:

| Terminal Output | Meaning | Fix |
|----------------|---------|-----|
| `Select login method` | OAuth login prompt blocking agent | Use `ANTHROPIC_API_KEY` env var instead |
| `Choose the text style` | First-run theme picker | Pre-configure in Dockerfile (see [Docker Sandbox](#docker-sandbox)) |
| `Paste code here` | OAuth code entry prompt | Use `ANTHROPIC_API_KEY` env var instead |

On the first iteration, Ralph runs a pre-flight check: if a stuck pattern is detected within 10 seconds, it aborts immediately with an actionable error instead of waiting for the inactivity timeout.

Stuck pattern warnings also appear in `swarm ralph logs`, so you don't need to peek at the terminal to discover them.

### Monitor Disconnect Recovery

The ralph monitoring process can crash or disconnect while the tmux worker keeps running. When this happens:

```bash
swarm ralph status agent     # Shows exit_reason: monitor_disconnected
swarm status agent           # Shows worker is still running
swarm ralph resume agent     # Resume monitoring from where it left off
```

### Caveats

**Done pattern + prompt content**: When using `--done-pattern` with `--check-done-continuous`, Ralph captures a baseline of the terminal after injecting the prompt and only checks *new* output for the done pattern. This prevents self-matching when the pattern appears in your prompt text. As defense-in-depth, prefer a unique signal pattern (e.g., `SWARM_DONE_X9K`) that won't appear in prose.

**Docker sandbox**: If using `sandbox.sh`, ensure `docker run --rm -it` (needs `-it` for TTY). Fresh containers need theme pre-configuration in the Dockerfile to avoid the first-time theme picker. Omit `--worktree` with Docker (Docker provides its own isolation). See [Docker Sandbox](#docker-sandbox) for details.

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

## Scripting Tips

### Exit Codes

`swarm status` returns meaningful exit codes for scripting:

```bash
swarm status agent1
# Exit 0 = running
# Exit 1 = stopped
# Exit 2 = not found

# Use in conditionals
if swarm status agent1 2>/dev/null; then
    echo "agent1 is still running"
else
    echo "agent1 has stopped"
fi
```

### Machine-Readable Output

```bash
# JSON output for parsing with jq
swarm ls --format json | jq '.[] | select(.status == "running") | .name'

# Names only for piping
swarm ls --format names | xargs -I{} swarm peek {}

# Filter by status
swarm ls --status running              # Only running workers
swarm ls --status stopped              # Only stopped workers
swarm ls --status running --tag team-a # Combine filters
```

### Peek All Workers

```bash
# Quick snapshot of all running workers
swarm peek --all
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
swarm peek worker1                                  # Quick look at terminal output
swarm logs worker1                                  # Full tmux scrollback
swarm ralph logs agent                              # Ralph iteration history
swarm ralph logs agent --live                       # Tail Ralph iteration log
cat ~/.swarm/state.json | jq .                      # View all worker state
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

#### Worktree Isolation

Always use `--worktree`. Each agent works in its own directory and branch, limiting blast radius.

#### Docker Sandbox

Use `sandbox.sh` to run workers inside Docker containers with resource limits and network lockdown:

```bash
# Scaffold sandbox files
swarm init --with-sandbox

# Build image and set up network
docker build --build-arg USER_ID=$(id -u) --build-arg GROUP_ID=$(id -g) \
    -t sandbox-loop -f Dockerfile.sandbox .
sudo ./setup-sandbox-network.sh    # iptables allowlist (does not survive reboot)

# Run sandboxed worker (use --env to pass API key into container)
swarm ralph spawn --name dev --prompt-file PROMPT.md --max-iterations 50 \
    --env ANTHROPIC_API_KEY="$ANTHROPIC_API_KEY" \
    -- ./sandbox.sh --dangerously-skip-permissions
```

Default container limits: 8 GB memory (no swap), 4 CPUs, 512 PIDs. OOM kills the container (not the host), and Ralph auto-continues on the next iteration.

**Authentication**: Use `ANTHROPIC_API_KEY` for Docker sandboxes. OAuth credentials (`.credentials.json`) don't work reliably in Docker — Claude Code's interactive mode shows a login picker even with valid tokens. The API key bypasses OAuth entirely and is the recommended auth method for containers.

**Environment variable propagation**: `--env KEY=VAL` on `swarm ralph spawn` propagates through tmux → `sandbox.sh` → `docker run -e` → the agent inside the container. Omit `--worktree` when using Docker (Docker provides its own filesystem isolation).

**Theme picker**: Fresh containers hit Claude Code's first-run theme picker. Pre-configure in your Dockerfile:

```dockerfile
RUN mkdir -p /home/loopuser/.claude && \
    echo '{"theme":"dark"}' > /home/loopuser/.claude/settings.local.json
```

See [`docs/autonomous-loop-guide.md`](docs/autonomous-loop-guide.md) for a complete setup walkthrough and [`docs/sandbox-loop-spec.md`](docs/sandbox-loop-spec.md) for the full technical spec.

### Best Practices

1. **Use disposable environments** — VMs, containers, or cloud instances you can destroy
2. **Set iteration limits** — `--max-iterations` in Ralph prevents runaway loops
3. **Monitor activity** — `swarm peek` for quick checks, `swarm attach` or `swarm logs -f` for full output
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
- Check what the agent is doing: `swarm peek <name>`
- If stuck at a prompt (login, theme picker), see [Stuck Worker Detection](#stuck-worker-detection)

**Worker spawned but not doing anything**
- `swarm peek <name>` to see terminal output — look for login prompts, theme pickers, or permission dialogs
- `swarm ralph status <name>` may show `running` even when stuck — status tracks the loop, not the agent's progress
- If the agent is at a login prompt: use `ANTHROPIC_API_KEY` env var (see [Docker Sandbox](#docker-sandbox))

**Worktree cleanup fails**
- Dirty worktrees (uncommitted changes) block removal by default
- Use `--force-dirty` to override, or commit/discard changes first
- Manual cleanup: `git worktree remove <path>`

**`git config core.bare = true` corruption**
- Worktree operations can sometimes set `core.bare = true`, breaking git commands
- Swarm detects and auto-fixes this, but if you encounter it manually: `git config core.bare false`

**Ralph loop stops unexpectedly**
- Check `~/.swarm/ralph/<name>/state.json` for failure count
- View iteration history: `swarm ralph logs <name>` or `cat ~/.swarm/ralph/<name>/iterations.log`
- 5 consecutive failures trigger automatic stop

**Ralph monitor disconnected but worker still running**
- `swarm ralph status <name>` shows `exit_reason: monitor_disconnected`
- `swarm status <name>` confirms worker is still alive
- `swarm ralph resume <name>` resumes monitoring from where it left off

**Ralph state file corrupted**
- Swarm recovers from corrupt JSON automatically (backs up to `state.json.corrupted`, reinitializes)
- If needed, manually reset: `swarm ralph clean <name>` then respawn

**Stale workers cluttering `swarm ls`**
- Filter to running workers: `swarm ls --status running`
- Clean up stopped workers: `swarm clean --all --rm-worktree`

**Docker auth not working (login picker appears)**
- OAuth credentials don't work reliably in Docker containers
- Use `ANTHROPIC_API_KEY` instead: `swarm ralph spawn --env ANTHROPIC_API_KEY="$ANTHROPIC_API_KEY" ...`
- Verify with `swarm peek <name>` — you should see the agent working, not a login prompt

**Ralph inactivity timeout too short**
- If Ralph restarts prematurely (e.g., during slow pre-commit hooks), increase the timeout:
  `swarm ralph spawn --inactivity-timeout 300 ...` (default: 180s)

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
