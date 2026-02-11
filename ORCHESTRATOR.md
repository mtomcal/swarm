# Round 2 Spec Changes — Orchestrator

This file is the orchestration runbook for the "Round 2 Spec Changes" epic. **Claude is the orchestrator** — a human or Claude session reads this document and manages the sandboxed loop that executes the implementation plan.

The sandboxed loop (`loop.sh`) spawns a fresh Claude worker inside a Docker container for each iteration. The worker reads `PROMPT.md`, picks one incomplete task from `IMPLEMENTATION_PLAN.md`, completes it, commits, and exits. The loop then starts the next iteration. **Your job as orchestrator** is to start the loop, monitor progress, and intervene when something goes wrong.

## Epic Summary

Implement code changes from Round 2 spec updates:
- **Phase 1**: `ralph ls` alias (3 tasks — trivial)
- **Phase 2**: `ralph clean` command (4 tasks — straightforward)
- **Phase 3**: Theme picker not-ready detection (2 tasks — moderate)
- **Phase 4**: Done-pattern self-match baseline filtering (3 tasks — most complex)
- **Phase 5**: Verification (3 tasks)

**Total: 15 tasks across 5 phases.**

## Quick Status
```bash
git log --oneline -5
grep -cE '^\s*-\s*\[x\]' IMPLEMENTATION_PLAN.md  # Tasks done
grep -cE '^\s*-\s*\[ \]' IMPLEMENTATION_PLAN.md   # Tasks remaining
```

## Start the Sandboxed Loop

```bash
SANDBOX=1 ./loop.sh 20
```

This runs up to 20 iterations. Each iteration:
1. Pipes `PROMPT.md` into `claude -p` inside a Docker container
2. Claude reads `IMPLEMENTATION_PLAN.md`, picks the next `[ ]` task, completes it
3. Claude commits and pushes the change
4. The loop checks output for `/done` — if found, the epic is complete
5. Otherwise, the loop starts the next iteration with a fresh context window

## Monitor

Watch container resource usage and task progress while the loop runs.

```bash
# Container resource usage (get exact name first)
docker ps --filter "name=sandbox-loop"
docker stats <exact-container-name> --no-stream

# Recent commits
git log --oneline -5

# Task progress
grep -cE '^\s*-\s*\[x\]' IMPLEMENTATION_PLAN.md
grep -cE '^\s*-\s*\[ \]' IMPLEMENTATION_PLAN.md

# Tail the current iteration log
ls -t .loop-logs/iteration-*.log | head -1 | xargs tail -20
```

## Stop / Restart

Kill the loop and all running containers, then restart.

```bash
pkill -f "loop.sh"; docker kill $(docker ps -q --filter "name=sandbox-loop") 2>/dev/null
sleep 2
SANDBOX=1 ./loop.sh 20
```

## OOM Recovery

Exit code 137 means the container hit its memory limit. The loop auto-continues to the next iteration, but the killed iteration's work is lost. If OOM happens repeatedly, increase the memory cap:

```bash
SANDBOX=1 MEMORY_LIMIT=12g ./loop.sh 20
```

## Orchestrator Responsibilities

1. **Start the loop** with `SANDBOX=1 ./loop.sh 20`
2. **Monitor progress every ~5 minutes** — check task counts, commits, and container memory
3. **Intervene on stuck iterations** — if the same task fails across multiple iterations, investigate the logs in `.loop-logs/` and update `PROMPT.md` or `IMPLEMENTATION_PLAN.md` to unblock the worker
4. **Adjust resources** if OOM or timeout errors are frequent
5. **Verify completion** — when all tasks are `[x]`, run the Phase 5 verification steps manually or start a final iteration to confirm
6. **Report to the user proactively** — don't wait to be asked. Summarize what changed, what's stuck, and what you're doing about it

## Phase-Specific Guidance

### Phase 1 (ralph ls) — Trivial
Tasks 1.1-1.2 both edit `swarm.py`. 1.1 adds the subparser (~line 3820), 1.2 adds dispatch (~line 5035). These are independent and small. Task 1.3 adds tests. A single iteration should handle 1.1+1.2 easily; tests in a second iteration.

### Phase 2 (ralph clean) — Straightforward
Tasks 2.1-2.3 all edit `swarm.py`: subparser, implementation function, dispatch. These are tightly coupled — a worker may combine 2.1-2.3 in one iteration. Task 2.4 adds tests.

### Phase 3 (theme picker) — Moderate
Task 3.1 modifies `wait_for_agent_ready()` (~line 3176). Task 3.2 adds tests to `test_ready_patterns.py`. The not-ready patterns are: `Choose the text style`, `looks best with your terminal`.

### Phase 4 (done-pattern baseline) — Most Complex
Tasks 4.1-4.2 thread a baseline line count through `send_prompt_to_worker()` (~line 6009) into `detect_inactivity()` (~line 5786). Task 4.3 adds tests. Worker may need guidance if stuck — see Intervention section.

### Phase 5 (verification)
Tasks 5.1-5.3 run tests and verify CLI. The worker should output `/done` after Phase 5 if all tasks are complete.

## Intervention Playbook

**Worker combines multiple tasks in one iteration**: This is fine. As long as all combined tasks pass tests and are marked `[x]`, let it proceed.

**Worker stuck on Phase 4 baseline threading**: If the worker struggles with threading `prompt_baseline_lines` through ralph state, suggest in PROMPT.md:
> "For Phase 4, store baseline_lines in RalphState dataclass. After send_prompt_to_worker(), capture pane line count and save to ralph state. In detect_inactivity(), read baseline from ralph state and skip those lines before pattern matching."

**Tests fail after code changes**: Check if the worker ran the correct test commands. The PROMPT.md specifies test commands per phase.

**Worker doesn't emit `/done`**: PROMPT.md instructs the worker to output `/done` when all tasks are complete. If the worker keeps verifying without emitting it, check the latest log for what's happening.

## Timing Expectations

- Phase 1 iterations: ~10 min each (trivial changes)
- Phase 2 iterations: ~15 min each (new function + tests)
- Phase 3 iterations: ~15 min each (pattern matching changes)
- Phase 4 iterations: ~20-30 min each (most complex, cross-cutting change)
- Phase 5 iterations: ~10 min (verification only)
- Budget ~3-4 hours total for the full epic

## Key Files

| File | Role |
|------|------|
| `ORCHESTRATOR.md` | This file — orchestration runbook |
| `PROMPT.md` | Injected into each Claude worker iteration |
| `IMPLEMENTATION_PLAN.md` | Task checklist the worker reads and updates |
| `loop.sh` | Bash loop that spawns sandboxed Claude workers |
| `Dockerfile.sandbox` | Docker image definition for the sandbox container |
| `.loop-logs/` | Per-iteration output logs |
| `swarm.py` | Main implementation file (~2997 lines) |
| `test_cmd_ralph.py` | Ralph unit tests |
| `test_ready_patterns.py` | Ready pattern detection tests |
