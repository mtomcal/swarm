# Agent Instructions

## Security: Autonomous Agent Permissions

Swarm workers require `--dangerously-skip-permissions` to operate autonomously. Without this flag, Claude will prompt for confirmation on each tool use, causing workers to stall.

### Required Flag
```bash
swarm spawn --name agent --tmux --worktree -- claude --dangerously-skip-permissions
```

### Sandboxing (Docker)

For unattended workers, use Docker isolation via `sandbox.sh`:

```bash
swarm init --with-sandbox                     # Scaffold sandbox files
docker build --build-arg USER_ID=$(id -u) --build-arg GROUP_ID=$(id -g) \
  -t sandbox-loop -f Dockerfile.sandbox .     # Build image
sudo ./setup-sandbox-network.sh               # Network lockdown (does not survive reboot)
swarm ralph spawn --name dev --prompt-file PROMPT.md --max-iterations 50 \
  -- ./sandbox.sh --dangerously-skip-permissions
```

See [README.md Security Considerations](README.md#security-considerations) for details.

## Swarm-Specific Caveats

**Pre-commit hook runs full test suite.** Every commit triggers the test suite (~94% coverage), which takes significant time. Plan for this when committing.

**Warning: Running `make test` in this repo will crash swarm workers.**

The test suite spawns many child workers that clobber `~/.swarm/state.json`, causing parent workers to lose their state entries and crash. When using `/swarm:director` in this repo:

1. **Workers will likely crash during test phase** - This is expected behavior in this repo
2. **Work is usually done but uncommitted** - Check worktrees for uncommitted changes
3. **Run specific tests instead of full suite** when possible:
   ```bash
   python3 -m unittest test_cmd_init -v      # Specific test file
   python3 -m unittest test_session_cleanup  # Instead of make test
   ```
4. **Always rescue incomplete workers**
5. **Manually create PRs** - Workers often crash before Phase 10 (PR creation)

This is a known limitation when developing swarm itself. Other repos using swarm won't have this issue.

## Process Management (swarm)

Swarm manages parallel agent workers in isolated git worktrees via tmux.

### Quick Reference
```bash
swarm spawn --name <id> --tmux --worktree -- claude --dangerously-skip-permissions  # Start agent
swarm ls --status running         # List running workers
swarm status <name>               # Check worker status
swarm peek <name>                 # Peek at terminal output (last 30 lines)
swarm send <name> "prompt"        # Send prompt to worker
swarm logs <name>                 # View worker output
swarm attach <name>               # Attach to tmux window
swarm kill <name> --rm-worktree   # Stop and cleanup
```

### Worktree Isolation
Each `--worktree` worker gets its own git branch and directory:
```bash
swarm spawn --name feature-auth --tmux --worktree -- claude --dangerously-skip-permissions
# Creates: <repo>-worktrees/feature-auth on branch 'feature-auth'
```

### Power User Tips
- `--ready-wait`: Block until agent is ready for input
- `--tag team-a`: Tag workers for filtering (`swarm ls --tag team-a`)
- `--env KEY=VAL`: Pass environment variables to worker
- `swarm send --all "msg"`: Broadcast to all running workers
- `swarm wait --all`: Wait for all workers to complete

State stored in `~/.swarm/state.json`. Logs in `~/.swarm/logs/`.

### Heartbeat (Rate Limit Recovery)
Heartbeat sends periodic nudges to workers to help recover from rate limits or other blocking states.

```bash
# Start heartbeat for running worker (nudge every 4 hours, expire after 24h)
swarm heartbeat start builder --interval 4h --expire 24h

# Check heartbeat status
swarm heartbeat list                     # List all heartbeats
swarm heartbeat status builder           # Detailed status for one worker

# Control heartbeat
swarm heartbeat pause builder            # Pause temporarily
swarm heartbeat resume builder           # Resume
swarm heartbeat stop builder             # Stop permanently
```

**Attach heartbeat at spawn time**:
```bash
swarm spawn --name agent --tmux --heartbeat 4h --heartbeat-expire 24h -- claude --dangerously-skip-permissions
swarm ralph spawn --name agent --prompt-file ./PROMPT.md --heartbeat 4h -- claude --dangerously-skip-permissions
```

State stored in `~/.swarm/heartbeats/<worker>.json`.

### Ralph Mode (Autonomous Looping)
Ralph mode enables autonomous agent looping with fresh context windows.

```bash
# Single command spawns worker AND starts monitoring loop (blocks until complete)
swarm ralph spawn --name agent --prompt-file ./PROMPT.md --max-iterations 100 -- claude --dangerously-skip-permissions

# Other commands
swarm ralph status agent     # Check iteration progress (includes ETA)
swarm ralph logs agent       # View iteration history
swarm ralph logs agent --live # Tail iteration log in real-time
swarm ralph pause agent      # Pause the loop
swarm ralph resume agent     # Resume the loop
swarm ralph init             # Create starter PROMPT.md
swarm ralph list             # List all ralph workers
swarm ralph ls               # Alias for ralph list
swarm ralph clean agent      # Remove ralph state for a worker
swarm ralph clean --all      # Remove all ralph state
```

**Scripting/Advanced**: Use `--no-run` to spawn without starting the loop:
```bash
swarm ralph spawn --name agent --prompt-file ./PROMPT.md --max-iterations 100 --no-run -- claude --dangerously-skip-permissions
swarm ralph run agent        # Start monitoring loop separately
```

**Replace existing worker** (auto-cleans worker, worktree, and ralph state):
```bash
swarm ralph spawn --name agent --replace --prompt-file ./PROMPT.md --max-iterations 100 -- claude --dangerously-skip-permissions
```

**Clean state only** (reset ralph state without killing worker/worktree):
```bash
swarm ralph spawn --name agent --clean-state --prompt-file ./PROMPT.md --max-iterations 100 -- claude --dangerously-skip-permissions
```

Ralph uses **screen-stable inactivity detection**: restarts when tmux screen is unchanged for `--inactivity-timeout` seconds (default: 180s). Increase for repos with slow CI/pre-commit hooks. State in `~/.swarm/ralph/<name>/state.json`. Iteration logs in `~/.swarm/ralph/<name>/iterations.log`.

### Ralph Troubleshooting

**Stale state blocking respawn**: If `swarm ralph spawn` fails with "worker already exists", use `--replace` to auto-clean:
```bash
swarm ralph spawn --name agent --replace --prompt-file ./PROMPT.md --max-iterations 100 -- claude --dangerously-skip-permissions
```

**`git config core.bare = true` corruption**: Worktree operations can sometimes set `core.bare = true`, breaking git. Swarm detects and auto-fixes this, but if you encounter it manually:
```bash
git config core.bare false
```

**Monitor disconnected but worker still running**: The ralph monitoring process can crash while the tmux worker keeps running. Check with:
```bash
swarm ralph status agent     # Shows exit_reason: monitor_disconnected
swarm status agent           # Shows if worker is still running
swarm ralph resume agent     # Resume monitoring if worker alive
```

**Inactivity timeout too short**: If ralph restarts the agent prematurely (e.g., during long pre-commit hooks), increase the timeout:
```bash
swarm ralph spawn --name agent --prompt-file ./PROMPT.md --max-iterations 100 --inactivity-timeout 300 -- claude --dangerously-skip-permissions
```

**Kill ralph worker with full cleanup**: Use `--rm-worktree` to remove worker, worktree, and ralph state:
```bash
swarm kill agent --rm-worktree  # Also removes ~/.swarm/ralph/agent/
```

**Done pattern self-matches prompt content**: When using `--done-pattern` with `--check-done-continuous`, the done pattern is checked against the full tmux pane buffer — including the prompt text typed via `tmux send-keys`. If your PROMPT.md contains the done pattern literally (e.g., `/done` appears in both the prompt and the done pattern), the loop stops immediately before the agent does any work. Fix: use a unique signal like `SWARM_DONE_X9K` that won't appear in prose.

**Docker sandbox: missing `-it` flags**: If using `sandbox.sh` (Docker wrapper), ensure `docker run --rm -it` (not just `docker run --rm`). Without `-it`, Claude gets no TTY and exits silently.

**Docker sandbox: theme picker blocking**: Fresh Docker containers without Claude preferences hit an interactive theme picker. Pre-configure in Dockerfile:
```dockerfile
RUN mkdir -p /home/loopuser/.claude && \
    echo '{"theme":"dark"}' > /home/loopuser/.claude/settings.local.json
```

**Docker sandbox: skip `--worktree`**: `--worktree` is incompatible with Docker-sandboxed workers. Docker already provides filesystem isolation; omit `--worktree` when using `sandbox.sh`.

## Project Structure

### Core Files
- `swarm.py` - Main implementation (~2997 lines), single-file CLI tool
- `IMPLEMENTATION_PLAN.md` - Current development plan with task checkboxes
- `specs/README.md` - Meta-spec defining how specs are written

### Specifications (`specs/`)
Behavioral specs in priority order (P0 = critical):
- **P0**: `worktree-isolation.md`, `ready-detection.md`, `state-management.md`
- **P1**: `spawn.md`, `ralph-loop.md`, `kill.md`, `send.md`, `tmux-integration.md`, `heartbeat.md`, `peek.md`
- **P2**: `ls.md`, `status.md`, `logs.md`, `wait.md`, `clean.md`, `respawn.md`, `interrupt-eof.md`, `attach.md`, `init.md`
- **Supporting**: `data-structures.md`, `environment.md`, `cli-interface.md`, `cli-help-standards.md`

### Test Files
Unit tests in root directory (`test_*.py`):
- `test_cmd_ralph.py` - Ralph mode unit tests
- `test_cmd_spawn.py`, `test_cmd_kill.py`, `test_cmd_ls.py`, etc. - Command-specific tests
- `test_cmd_heartbeat.py` - Heartbeat unit tests
- `test_state_file_locking.py` - State management tests
- `test_ready_patterns.py` - Agent readiness detection tests
- `test_worktree_protection.py` - Git worktree safety tests

Integration tests in `tests/`:
- `tests/test_integration_ralph.py` - Ralph integration tests (requires tmux)
- `tests/test_tmux_isolation.py` - `TmuxIsolatedTestCase` base class for tmux tests

## Testing Guidelines

### Running Tests
```bash
python3 -m unittest test_cmd_ralph -v           # Ralph unit tests
python3 -m unittest test_cmd_heartbeat -v       # Heartbeat unit tests
python3 -m unittest tests.test_integration_ralph -v     # Ralph integration tests (requires tmux)
python3 -m unittest test_cmd_spawn -v           # Spawn command tests
```

### Integration Test Tips
- **Always use `timeout`** to prevent hanging tests: `timeout 60 python3 -m unittest ...`
- Integration tests use `TmuxIsolatedTestCase` from `tests/test_tmux_isolation.py`
- Each test gets a unique tmux socket for isolation
- Use commands that output ready patterns (e.g., `'bash', '-c', 'echo "$ ready"; sleep 30'`)
- Simple `sleep` commands will hang because they never produce a ready pattern

### Test Patterns
- Unit tests mock `State()` and filesystem, don't require tmux
- Integration tests inherit from `TmuxIsolatedTestCase` and use `self.run_swarm()` helper
- Cleanup in `tearDown()`: kill workers, clean state, remove temp dirs

## Architecture Notes

### State Management
- Worker state: `~/.swarm/state.json` (fcntl locked for concurrent access)
- Ralph state: `~/.swarm/ralph/<name>/state.json`
- Ralph iteration logs: `~/.swarm/ralph/<name>/iterations.log`
- Heartbeat state: `~/.swarm/heartbeats/<worker>.json`
- Worker logs: `~/.swarm/logs/`

### Key Data Classes (swarm.py)
- `Worker` - Worker process record (name, status, cmd, tmux/worktree info, metadata)
- `TmuxInfo` - Tmux session/window/socket info
- `WorktreeInfo` - Git worktree path/branch/base_repo
- `RalphState` - Ralph loop state (iteration, status, failures, timeouts)
- `HeartbeatState` - Heartbeat state (interval, expire_at, message, beat_count, status)

### CLI Structure
Commands defined in `main()` via argparse subparsers. Each command has a `cmd_<name>(args)` handler function. Nested subparsers for:
- `swarm ralph <subcommand>` - Autonomous looping
- `swarm heartbeat <subcommand>` - Rate limit recovery nudges
