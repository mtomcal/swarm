# Round 5: Ralph Robustness & CLI Ergonomics — Orchestrator

This file is the orchestration runbook for the "Round 5 Ralph Robustness & CLI Ergonomics" epic. **You are the director** — a human using an interactive Claude session that manages workers via `loop.sh`.

Workers run as `loop.sh` iterations (bare or Docker-sandboxed via `SANDBOX=1`). Each iteration spawns a fresh Claude worker that reads `PROMPT.md`, picks one incomplete task from `IMPLEMENTATION_PLAN.md`, completes it, commits, and exits. The loop then starts the next iteration with a fresh context window. **Your job as director** is to start the loop, monitor progress, and intervene when something goes wrong.

## Epic Summary

Implement FEEDBACK.md fixes and close remaining spec-vs-code gaps:
- **Phase 1**: Fatal pattern detection — compaction kills iteration (3 tasks — medium)
- **Phase 2**: Done-pattern auto-enables `--check-done-continuous` (2 tasks — low)
- **Phase 3**: Pre-clear sequence in `tmux_send()` + `--raw` flag (4 tasks — medium)
- **Phase 4**: `--max-context` enforcement (4 tasks — medium)
- **Phase 5**: CLI defaults & aliases (5 tasks — low)
- **Phase 6**: Crash-safe state writes (2 tasks — low)
- **Phase 7**: Window loss done-pattern check (2 tasks — low)
- **Phase 8**: Help text & metadata fixes (3 tasks — low)
- **Phase 9**: Unit test verification (3 tasks)
- **Phase 10**: Real-world smoke tests (6 tasks — manual, post-loop)

**Total: 34 tasks across 10 phases. All automated by workers.**

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
5. **Verify completion** — when all tasks are `[x]` (including Phase 10 smoke tests), the done signal fires
6. **Phase 10 needs tmux** — smoke tests spawn real workers via tmux; ensure the loop environment has tmux available (bare mode or Docker with tmux installed)

## Phase-Specific Guidance

### Phase 1 (fatal pattern detection) — Medium
Tasks 1.1+1.2 are tightly coupled: add `FATAL_PATTERNS` constant and the detection logic in `detect_inactivity()`, then handle the `"compaction"` return in the ralph monitor loop. Worker should combine 1.1+1.2 in one iteration, then 1.3 (tests) in the same iteration. Key context: `detect_inactivity()` is at ~line 6307, the ralph outer loop is at ~line 7010.

### Phase 2 (done-pattern auto-enable) — Low
Task 2.1 changes `--check-done-continuous` from `store_true` to `BooleanOptionalAction` and adds default logic when `--done-pattern` is set. Small, self-contained change. Worker should combine 2.1+2.2 in one iteration.

### Phase 3 (pre-clear in tmux_send) — Medium
Tasks 3.1-3.3 are tightly coupled: modify `tmux_send()` to send Escape+Ctrl-U by default, add `--raw` flag, and audit ALL internal callers to pass `pre_clear=False`. **The caller audit in 3.3 is critical** — if internal callers (prompt injection, heartbeat) get pre-clear, they'll break. Worker should grep for all `tmux_send(` calls. Combine 3.1+3.2+3.3, then 3.4 (tests).

### Phase 4 (max-context) — Medium
Tasks 4.1-4.3 are tightly coupled: add `--max-context` argparse flag, add `max_context` to `RalphState`, scan last 3 lines for `(\d+)%` in `detect_inactivity()`, handle nudge/kill in the monitor loop. This is the most complex new feature — worker may need 2 iterations. The regex scanning must be careful about false positives (only check last 3 lines of pane output).

### Phase 5 (CLI defaults & aliases) — Low
Tasks 5.1-5.4 are all small independent argparse changes. Worker should combine all of them in one iteration. Key: `--max-iterations` goes from `required=True` to `default=50`, `--worktree` goes from `store_true` to `BooleanOptionalAction` with `default=True`. `ralph stop` is a thin wrapper around `cmd_kill()`. `heartbeat ls` is an alias for `heartbeat list`.

### Phase 6 (crash-safe writes) — Low
Task 6.1 applies the write-to-temp-then-rename pattern to three functions: `State._save()`, `save_ralph_state()`, and `save_heartbeat_state()`. Use `tempfile.NamedTemporaryFile` in the same directory + `os.replace()`. Small, repetitive change.

### Phase 7 (window loss done-pattern) — Low
Task 7.1 is a small change in the `CalledProcessError` handler in `detect_inactivity()`: check done pattern against `last_content` before returning `"exited"`. Combine with Phase 6 in one iteration.

### Phase 8 (help text & metadata) — Low
Tasks 8.1-8.2 are independent string edits and a one-line fix in `cmd_respawn()`. Quick cleanup iteration.

### Phase 9 (verification)
Tasks 9.1-9.3 run tests and verify CLI. Worker should output `/done` after Phase 9 if all tasks are complete.

### Phase 10 (real-world smoke tests) — Automated, one per iteration
Each smoke test is a self-contained task: the worker writes a script (or runs commands inline), spawns a test worker via `python3 swarm.py`, waits for expected behavior, asserts results, and cleans up. **Requires tmux to be available in the worker's environment.**

Each test uses `--no-worktree` and unique `smoke-fbN` names to avoid conflicts. Worker should poll with `sleep` + status/logs checks, assert expected strings in output, and clean up regardless of pass/fail.

If a smoke test fails, the worker should NOT mark it `[x]` — leave it for the next iteration to debug and retry.

## Expected Iteration Plan

| Iteration | Phases | Tasks | Notes |
|-----------|--------|-------|-------|
| 1 | Phase 1 | 1.1+1.2+1.3 | Compaction detection + tests |
| 2 | Phase 2 | 2.1+2.2 | Done-pattern auto-enable + tests |
| 3 | Phase 3 | 3.1+3.2+3.3+3.4 | Pre-clear + raw flag + caller audit + tests |
| 4 | Phase 4 | 4.1+4.2+4.3+4.4 | Max-context (may spill to iteration 5) |
| 5 | Phase 5 | 5.1+5.2+5.3+5.4+5.5 | CLI defaults & aliases + tests |
| 6 | Phase 6+7 | 6.1+6.2+7.1+7.2 | Crash-safe writes + window loss fix |
| 7 | Phase 8 | 8.1+8.2+8.3 | Help text + metadata |
| 8 | Phase 9 | 9.1+9.2+9.3 | Full test suite verification |
| 9 | Phase 10 | 10.1 | Smoke: compaction detection |
| 10 | Phase 10 | 10.2 | Smoke: done-pattern auto-kill |
| 11 | Phase 10 | 10.3 | Smoke: send pre-clear |
| 12 | Phase 10 | 10.4 | Smoke: window loss detection |
| 13 | Phase 10 | 10.5 | Smoke: screen change tracking |
| 14 | Phase 10 | 10.6 + `/done` | Smoke: max-context enforcement |

**Budget: 12-15 iterations, ~7 hours wall time.**

## Intervention Playbook

**Worker combines multiple tasks in one iteration**: This is fine and expected. As long as all combined tasks pass tests and are marked `[x]`, let it proceed.

**Worker struggles with Phase 1 compaction detection**: The key function is `detect_inactivity()` at ~line 6307. Point to it in PROMPT.md:
> "Add a `FATAL_PATTERNS = ['Compacting conversation']` list. In `detect_inactivity()`, after `content = tmux_capture_pane(...)`, check `if any(p in content for p in FATAL_PATTERNS): return 'compaction'`. In the outer ralph loop, handle `'compaction'` like `'exited'` but log `[FATAL]` and don't increment failure count."

**Worker struggles with Phase 3 pre-clear caller audit**: The critical insight is that internal callers must NOT pre-clear. Add to PROMPT.md:
> "After modifying `tmux_send()` to default `pre_clear=True`, grep for all existing `tmux_send(` calls and add `pre_clear=False` to: `send_prompt_to_worker()`, `run_heartbeat_monitor()`, `cmd_interrupt()`, `cmd_eof()`, and any other internal callers. Only `cmd_send()` (the user-facing command) should use pre-clear."

**Worker struggles with Phase 4 max-context regex**: The regex must match Claude Code's status bar format. Add to PROMPT.md:
> "Scan last 3 lines of pane content for `r'(\d+)%'`. Extract the integer. Compare against `max_context` for nudge, `max_context + 15` for kill. Use a `context_nudge_sent` flag to avoid sending multiple nudges per iteration."

**Worker changes `--max-iterations` default but tests break**: Existing tests may hardcode `required=True` behavior or expect the flag to be mandatory. Worker needs to update test fixtures.

**Worker changes `--worktree` default but tests break**: Same issue — tests may assume `--worktree` defaults to False. Worker needs to update test assertions or add `--no-worktree` to test fixtures that don't want worktrees.

**Tests fail after code changes**: Check if the worker ran the correct test commands. The PROMPT.md specifies test commands per phase.

**Worker doesn't emit done signal**: PROMPT.md instructs the worker to output `/done` when all tasks are complete. If the worker keeps verifying without emitting it, check the latest log for what's happening.

**Done pattern mismatch**: `loop.sh` checks for `/done` by default. Make sure PROMPT.md uses a pattern that matches (or update `DONE_PATTERN` in the loop.sh invocation).

## Timing Expectations

- Phase 1 iterations: ~20 min (new detection path + monitor loop change + tests)
- Phase 2 iterations: ~15 min (argparse change + default logic + tests)
- Phase 3 iterations: ~25 min (tmux_send refactor + caller audit + tests)
- Phase 4 iterations: ~30 min (new feature, regex scanning, nudge/kill logic + tests)
- Phase 5 iterations: ~15 min (small argparse changes + alias wrappers + tests)
- Phase 6+7 iterations: ~15 min (temp+rename pattern + window loss fix)
- Phase 8 iterations: ~10 min (string edits + one-line fix)
- Phase 9 iterations: ~10 min (verification only)
- Phase 10 iterations: ~10-15 min each (spawn test worker, wait, assert, cleanup)
- **Budget: ~4-6 hours total, 12-15 iterations**

## Key Files

| File | Role |
|------|------|
| `ORCHESTRATOR.md` | This file — director runbook |
| `PROMPT.md` | Injected into each Claude worker iteration |
| `IMPLEMENTATION_PLAN.md` | Task checklist the worker reads and updates |
| `FEEDBACK.md` | Field notes from real ralph usage — the motivation for this round |
| `loop.sh` | Loop runner (bare or Docker sandbox via `SANDBOX=1`) |
| `sandbox.sh` | Docker wrapper for Claude (generated by `swarm init --with-sandbox`) |
| `Dockerfile.sandbox` | Docker image definition for the sandbox container |
| `swarm.py` | Main implementation file |
| `test_cmd_ralph.py` | Ralph unit tests (extended in Phases 1, 2, 4, 7) |
| `test_cmd_spawn.py` | Spawn/send unit tests (extended in Phase 3, 8) |
| `test_cmd_heartbeat.py` | Heartbeat unit tests (extended in Phase 5) |
| `test_state_file_locking.py` | State management tests (extended in Phase 6) |
