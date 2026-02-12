# Round 4: Spec Compliance Gaps — Orchestrator

This file is the orchestration runbook for the "Round 4 Spec Compliance Gaps" epic. **You are the director** — a human using an interactive Claude session that manages workers via `loop.sh`.

Workers run as `loop.sh` iterations (bare or Docker-sandboxed via `SANDBOX=1`). Each iteration spawns a fresh Claude worker that reads `PROMPT.md`, picks one incomplete task from `IMPLEMENTATION_PLAN.md`, completes it, commits, and exits. The loop then starts the next iteration. **Your job as director** is to start the loop, monitor progress, and intervene when something goes wrong.

## Epic Summary

Close the remaining gaps between specs and implementation:
- **Phase 1**: `swarm peek` command — entirely missing (3 tasks — low)
- **Phase 2**: Environment propagation for tmux workers (3 tasks — low)
- **Phase 3**: Transactional rollback in `cmd_spawn()` (3 tasks — medium)
- **Phase 4**: Corrupt state recovery in `State._load()` (2 tasks — trivial)
- **Phase 5**: Verification (3 tasks)

**Total: 14 tasks across 5 phases.**

## Quick Status
```bash
# Task progress
grep -cE '^\s*-\s*\[x\]' IMPLEMENTATION_PLAN.md   # Tasks done
grep -cE '^\s*-\s*\[ \]' IMPLEMENTATION_PLAN.md    # Tasks remaining

# Recent commits
git log --oneline -5

# Loop logs (if running in tmux)
tail -20 .loop-logs/iteration-*.log | head -60

# Container resources (if SANDBOX=1)
docker ps --filter "ancestor=sandbox-loop" --format '{{.Names}}'
docker stats <exact-container-name> --no-stream
```

## Start Worker

### Bare mode (no Docker)
```bash
tmux new-session -d -s loop './loop.sh 15 PROMPT.md'
tmux attach -t loop   # Watch live
```

### Sandbox mode (Docker)
```bash
tmux new-session -d -s loop 'SANDBOX=1 ./loop.sh 15 PROMPT.md'
tmux attach -t loop   # Watch live
```

This runs up to 15 iterations. Each iteration:
1. Spawns a fresh Claude worker (bare or inside Docker container)
2. Claude reads `IMPLEMENTATION_PLAN.md`, picks the next `[ ]` task, completes it
3. Claude commits and pushes the change
4. `loop.sh` checks for `/done` pattern — if found, the epic is complete
5. Otherwise, the loop starts the next iteration with a fresh context window

## Monitor

```bash
# Live loop output (if running in tmux)
tmux attach -t loop

# Iteration logs
ls -lt .loop-logs/iteration-*.log | head -5    # Recent logs
tail -50 .loop-logs/iteration-$(ls .loop-logs/iteration-*.log | wc -l).log  # Latest

# Container resources (sandbox mode)
docker ps --filter "ancestor=sandbox-loop" --format '{{.Names}}'
docker stats <exact-container-name> --no-stream

# Recent commits
git log --oneline -10

# Task progress
grep -cE '^\s*-\s*\[x\]' IMPLEMENTATION_PLAN.md
grep -cE '^\s*-\s*\[ \]' IMPLEMENTATION_PLAN.md
```

## Stop / Restart

```bash
# Kill the loop
tmux kill-session -t loop

# Restart fresh
tmux new-session -d -s loop './loop.sh 15 PROMPT.md'
```

## OOM Recovery (sandbox mode)

Exit code 137 means the container hit its memory limit. `loop.sh` auto-continues to the next iteration, but the killed iteration's work is lost. If OOM happens repeatedly, increase the memory cap:

```bash
tmux new-session -d -s loop 'SANDBOX=1 MEMORY_LIMIT=12g ./loop.sh 15 PROMPT.md'
```

## Director Checklist

1. **Start loop** with commands above
2. **Monitor progress** — check task counts, commits, and iteration logs every ~10 min
3. **Intervene on stuck iterations** — if the same task fails across multiple iterations, check iteration logs and update `PROMPT.md` or `IMPLEMENTATION_PLAN.md` to unblock the worker
4. **Adjust resources** if OOM or timeout errors are frequent (sandbox mode)
5. **Verify completion** — when all tasks are `[x]`, run the Phase 5 verification steps manually or confirm the done signal was emitted

## Phase-Specific Guidance

### Phase 1 (`swarm peek` command) — Low
Tasks 1.1-1.2 are tightly coupled: add the argparse subparser and implement `cmd_peek()`. Worker should combine 1.1+1.2 in one iteration, then 1.3 (tests) in the same or next iteration. The underlying `tmux_capture_pane()` already exists — this is just CLI wiring.

### Phase 2 (env propagation for tmux) — Low
Task 2.1 adds an `env` parameter to `create_tmux_window()` and wraps the command with `env KEY=VAL`. Task 2.2 threads it through callers (`cmd_spawn`, `_do_ralph_spawn`, `cmd_respawn`). These are tightly coupled — worker should combine 2.1+2.2, then 2.3 (tests).

### Phase 3 (transactional rollback in spawn) — Medium
Task 3.1 refactors `cmd_spawn()` to track created resources and wrap creation steps in try/except. Task 3.2 implements `_rollback_spawn()` helper. These are tightly coupled — combine 3.1+3.2. Then 3.3 (tests). This is the most complex phase — worker may need 2 iterations.

### Phase 4 (corrupt state recovery) — Trivial
Task 4.1 wraps `json.load(f)` in `State._load()` (~line 2774) with try/except for `json.JSONDecodeError`. On error: print warning, backup to `state.json.corrupted`, set empty workers list. Same pattern as ralph state recovery. Task 4.2 adds tests. A single iteration handles both.

### Phase 5 (verification)
Tasks 5.1-5.3 run tests and verify CLI. Worker should output `/done` after Phase 5 if all tasks are complete.

## Intervention Playbook

**Worker combines multiple tasks in one iteration**: This is fine. As long as all combined tasks pass tests and are marked `[x]`, let it proceed.

**Worker struggles with Phase 1 peek command**: The key helpers already exist. Point to them in PROMPT.md:
> "`tmux_capture_pane()` is at ~line 3200. `tmux_window_exists()` is at ~line 3196. `State.get_worker()` at ~line 2801. Follow the pattern of `cmd_status()` for error handling and exit codes."

**Worker struggles with Phase 2 env propagation**: The fix is a 5-line change. Add to PROMPT.md:
> "In `create_tmux_window()` (~line 3153), when env is non-empty, prepend `env KEY1=VAL1 KEY2=VAL2` to `cmd_str` using `shlex.quote()` on keys and values."

**Worker struggles with Phase 3 rollback**: The pattern exists in ralph spawn. Point to it:
> "See `_rollback_ralph_spawn()` (~line 5203) for the pattern. Track `created_worktree`, `created_tmux`, `spawned_pid` as local vars, wrap creation in try/except, call `_rollback_spawn()` on failure."

**Tests fail after code changes**: Check if the worker ran the correct test commands. The PROMPT.md specifies test commands per phase.

**Worker doesn't emit done signal**: PROMPT.md instructs the worker to output `/done` when all tasks are complete. If the worker keeps verifying without emitting it, check the latest log for what's happening.

**Done pattern mismatch**: `loop.sh` checks for `/done` by default. Make sure PROMPT.md uses a pattern that matches (or update `DONE_PATTERN` in the loop.sh invocation). Round 3 learned this the hard way — align patterns before starting.

## Timing Expectations

- Phase 1 iterations: ~15-20 min (new command, but simple wiring)
- Phase 2 iterations: ~10-15 min (small change + threading through callers)
- Phase 3 iterations: ~20-30 min (refactor + rollback helper, most complex)
- Phase 4 iterations: ~10 min (trivial try/except)
- Phase 5 iterations: ~10 min (verification only)
- Budget ~1.5-3 hours total, ~4-6 iterations

## Key Files

| File | Role |
|------|------|
| `ORCHESTRATOR.md` | This file — director runbook |
| `PROMPT.md` | Injected into each Claude worker iteration |
| `IMPLEMENTATION_PLAN.md` | Task checklist the worker reads and updates |
| `loop.sh` | Loop runner (bare or Docker sandbox via `SANDBOX=1`) |
| `sandbox.sh` | Docker wrapper for Claude (generated by `swarm init --with-sandbox`) |
| `Dockerfile.sandbox` | Docker image definition for the sandbox container |
| `swarm.py` | Main implementation file |
| `test_cmd_peek.py` | Peek command unit tests (new, created in Phase 1) |
| `test_cmd_spawn.py` | Spawn command tests (extended in Phases 2-3) |
| `test_state_file_locking.py` | State management tests (extended in Phase 4) |
