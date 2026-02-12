# Round 3: Ralph Diagnostics & UX — Orchestrator

This file is the orchestration runbook for the "Round 3 Ralph Diagnostics & UX" epic. **You are the director** — a human using an interactive Claude session that manages Docker-sandboxed workers.

Workers run as `swarm ralph` loops inside Docker containers via `sandbox.sh`. Each iteration spawns a fresh Claude worker that reads `PROMPT.md`, picks one incomplete task from `IMPLEMENTATION_PLAN.md`, completes it, commits, and exits. Ralph then starts the next iteration. **Your job as director** is to start the workers, monitor progress, and intervene when something goes wrong.

## Epic Summary

Implement code changes from Round 3 spec updates (commit `58f9955`):
- **Phase 1**: Login/OAuth not-ready patterns (2 tasks — trivial)
- **Phase 2**: Corrupt state recovery (2 tasks — low)
- **Phase 3**: Screen change tracking (4 tasks — low-medium)
- **Phase 4**: Stuck pattern detection (3 tasks — medium)
- **Phase 5**: Stuck detection in status output (2 tasks — low-medium)
- **Phase 6**: Pre-flight validation (2 tasks — medium)
- **Phase 7**: `--foreground` flag for ralph spawn (5 tasks — medium)
- **Phase 8**: Verification (3 tasks)

**Total: 23 tasks across 8 phases.**

## Quick Status
```bash
swarm ralph status dev
swarm ls --status running
swarm peek dev
git log --oneline -5
grep -cE '^\s*-\s*\[x\]' IMPLEMENTATION_PLAN.md  # Tasks done
grep -cE '^\s*-\s*\[ \]' IMPLEMENTATION_PLAN.md   # Tasks remaining
```

## Start Worker

```bash
swarm ralph spawn --name dev --prompt-file PROMPT.md --max-iterations 20 \
    -- ./sandbox.sh --dangerously-skip-permissions
```

This runs up to 20 iterations. Each iteration:
1. Spawns a fresh Claude worker inside a Docker container
2. Claude reads `IMPLEMENTATION_PLAN.md`, picks the next `[ ]` task, completes it
3. Claude commits and pushes the change
4. Ralph checks for `/done` pattern — if found, the epic is complete
5. Otherwise, ralph starts the next iteration with a fresh context window

## Monitor

Watch container resource usage and task progress while workers run.

```bash
# Worker terminal output (lightweight, non-interactive)
swarm peek dev
swarm peek dev -n 100         # more lines

# Worker status
swarm ls --status running
swarm ralph status dev
swarm ralph logs dev

# Container resource usage (get exact name first)
docker ps --filter "ancestor=sandbox-loop" --format '{{.Names}}'
docker stats <exact-container-name> --no-stream

# Recent commits
git log --oneline -5

# Task progress
grep -cE '^\s*-\s*\[x\]' IMPLEMENTATION_PLAN.md
grep -cE '^\s*-\s*\[ \]' IMPLEMENTATION_PLAN.md
```

## Stop / Restart

```bash
swarm kill dev --rm-worktree
swarm ralph spawn --name dev --replace --prompt-file PROMPT.md --max-iterations 20 \
    -- ./sandbox.sh --dangerously-skip-permissions
```

## OOM Recovery

Exit code 137 means the container hit its memory limit. Ralph auto-continues to the next iteration, but the killed iteration's work is lost. If OOM happens repeatedly, increase the memory cap:

```bash
MEMORY_LIMIT=12g swarm ralph spawn --name dev --replace \
    --prompt-file PROMPT.md --max-iterations 20 \
    -- ./sandbox.sh --dangerously-skip-permissions
```

## Director Checklist

1. **Start worker** with `swarm ralph spawn` command above
2. **Monitor progress** — check task counts, commits, and container memory via `swarm peek dev`
3. **Intervene on stuck iterations** — if the same task fails across multiple iterations, check `swarm ralph logs dev` and update `PROMPT.md` or `IMPLEMENTATION_PLAN.md` to unblock the worker
4. **Adjust resources** if OOM or timeout errors are frequent
5. **Verify completion** — when all tasks are `[x]`, run the Phase 8 verification steps manually or start a final iteration to confirm

## Phase-Specific Guidance

### Phase 1 (login/OAuth patterns) — Trivial
Task 1.1 adds 2 strings to the `not_ready_patterns` list in `wait_for_agent_ready()` (~line 3279). Task 1.2 adds tests to `test_ready_patterns.py`. A single iteration should handle both tasks.

### Phase 2 (corrupt state recovery) — Low
Task 2.1 wraps `json.load()` in `load_ralph_state()` (~line 2604) with a try/except for `json.JSONDecodeError`. Task 2.2 adds tests. A single iteration handles both.

### Phase 3 (screen change tracking) — Low-Medium
Tasks 3.1-3.3 are tightly coupled: add field to `RalphState`, update `detect_inactivity()` to track changes, update `cmd_ralph_status()` to display. Worker should combine 3.1-3.3, then 3.4 (tests) in same or next iteration.

### Phase 4 (stuck pattern detection) — Medium
Task 4.1 defines the `STUCK_PATTERNS` constant. Task 4.2 integrates detection into the `detect_inactivity()` poll loop. These are tightly coupled — worker should combine 4.1+4.2, then 4.3 (tests).

### Phase 5 (stuck status output) — Low-Medium
Task 5.1 extends `cmd_ralph_status()` to show `(possibly stuck)` when screen unchanged >60s. Depends on Phase 3's `last_screen_change` field. Task 5.2 adds tests.

### Phase 6 (pre-flight validation) — Medium
Task 6.1 adds a 10-second post-prompt check on iteration 1 only. Depends on Phase 4's `STUCK_PATTERNS`. If stuck pattern detected, kill worker and exit with error. Task 6.2 adds tests.

### Phase 7 (`--foreground` flag) — Medium
Tasks 7.1-7.4 are tightly coupled: add parser arg, implement non-blocking default, update output, update `--replace` to terminate monitor PID. This is the most complex phase. Worker may need 2-3 iterations.

### Phase 8 (verification)
Tasks 8.1-8.3 run tests and verify CLI. Worker should output `/done` after Phase 8 if all tasks are complete.

## Intervention Playbook

**Worker combines multiple tasks in one iteration**: This is fine. As long as all combined tasks pass tests and are marked `[x]`, let it proceed.

**Worker struggles with Phase 3 screen change tracking**: If the worker has trouble threading `last_screen_change` through detect_inactivity → ralph state → status display, add to PROMPT.md:
> "For Phase 3, add `last_screen_change: Optional[str] = None` to RalphState. In detect_inactivity(), when screen hash changes, set `ralph_state.last_screen_change = datetime.now(timezone.utc).isoformat()` and save state. In cmd_ralph_status(), parse the ISO timestamp and show 'Last screen change: Ns ago'."

**Worker struggles with Phase 7 background process**: The non-blocking spawn needs to fork the monitoring loop. Suggest in PROMPT.md:
> "For Phase 7.2, use `subprocess.Popen(['python3', 'swarm.py', 'ralph', 'run', worker_name])` with `start_new_session=True` and redirect stdout/stderr to devnull. Store the PID in ralph state as `monitor_pid` for --replace cleanup."

**Tests fail after code changes**: Check if the worker ran the correct test commands. The PROMPT.md specifies test commands per phase.

**Worker doesn't emit `/done`**: PROMPT.md instructs the worker to output `/done` when all tasks are complete. If the worker keeps verifying without emitting it, check the latest log for what's happening.

## Timing Expectations

- Phase 1 iterations: ~5-10 min (trivial changes)
- Phase 2 iterations: ~10 min (simple try/except)
- Phase 3 iterations: ~15-20 min (3-4 coupled tasks)
- Phase 4 iterations: ~15-20 min (detection logic + tests)
- Phase 5 iterations: ~10-15 min (status display changes)
- Phase 6 iterations: ~15-20 min (pre-flight check)
- Phase 7 iterations: ~20-30 min each (background process management, most complex)
- Phase 8 iterations: ~10 min (verification only)
- Budget ~3-5 hours total for the full epic, ~8-12 iterations

## Key Files

| File | Role |
|------|------|
| `ORCHESTRATOR.md` | This file — director runbook |
| `PROMPT.md` | Injected into each Claude worker iteration |
| `IMPLEMENTATION_PLAN.md` | Task checklist the worker reads and updates |
| `loop.sh` | Standalone loop runner (bare or Docker sandbox) |
| `sandbox.sh` | Docker wrapper for Claude (generated by `swarm init --with-sandbox`) |
| `Dockerfile.sandbox` | Docker image definition for the sandbox container |
| `swarm.py` | Main implementation file |
| `test_cmd_ralph.py` | Ralph unit tests |
| `test_ready_patterns.py` | Ready pattern detection tests |
