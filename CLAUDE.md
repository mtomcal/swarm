# Agent Instructions

## Swarm-Specific Caveats

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
swarm spawn --name <id> --tmux --worktree -- claude  # Start agent in isolated worktree
swarm ls                          # List all workers
swarm status <name>               # Check worker status
swarm send <name> "prompt"        # Send prompt to worker
swarm logs <name>                 # View worker output
swarm attach <name>               # Attach to tmux window
swarm kill <name> --rm-worktree   # Stop and cleanup
```

### Worktree Isolation
Each `--worktree` worker gets its own git branch and directory:
```bash
swarm spawn --name feature-auth --tmux --worktree -- claude
# Creates: <repo>-worktrees/feature-auth on branch 'feature-auth'
```

### Power User Tips
- `--ready-wait`: Block until agent is ready for input
- `--tag team-a`: Tag workers for filtering (`swarm ls --tag team-a`)
- `--env KEY=VAL`: Pass environment variables to worker
- `swarm send --all "msg"`: Broadcast to all running workers
- `swarm wait --all`: Wait for all workers to complete

State stored in `~/.swarm/state.json`. Logs in `~/.swarm/logs/`.

### Ralph Mode (Autonomous Looping)
Ralph mode enables autonomous agent looping with fresh context windows:
```bash
swarm spawn --name agent --ralph --prompt-file ./PROMPT.md --max-iterations 100 -- claude
swarm ralph status agent     # Check iteration progress
swarm ralph pause agent      # Pause the loop
swarm ralph resume agent     # Resume the loop
swarm ralph init             # Create starter PROMPT.md
```

Ralph uses **screen-stable inactivity detection**: restarts when tmux screen is unchanged for `--inactivity-timeout` seconds (default: 60s). State in `~/.swarm/ralph/<name>/state.json`.

## Project Structure

- `swarm.py` - Main implementation (~2876 lines)
- `test_cmd_ralph.py` - Unit tests for ralph mode (203 tests)
- `tests/test_integration_ralph.py` - Integration tests requiring tmux (17 tests)
- `tests/test_tmux_isolation.py` - TmuxIsolatedTestCase base class for integration tests
- `specs/` - Behavioral specifications (one per feature)

## Testing Guidelines

### Running Tests
```bash
python3 -m unittest test_cmd_ralph -v           # Ralph unit tests
python3 -m unittest tests.test_integration_ralph -v  # Integration tests (requires tmux)
```

### Integration Test Tips
- **Always use `timeout`** to prevent hanging tests: `timeout 60 python3 -m unittest ...`
- Integration tests use `TmuxIsolatedTestCase` from `tests/test_tmux_isolation.py`
- Each test gets a unique tmux socket for isolation
- Commands using `--ralph` call `wait_for_agent_ready()` which looks for prompt patterns
- Use commands that output ready patterns (e.g., `'bash', '-c', 'echo "$ ready"; sleep 30'`)
- Simple `sleep` commands will hang because they never produce a ready pattern
