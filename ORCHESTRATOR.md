# Remove Workflow Subcommand - Orchestrator

This file is the orchestration runbook for the "Remove Workflow" epic. **Claude is the orchestrator** — a human or Claude session reads this document and manages the sandboxed loop that executes the implementation plan.

The sandboxed loop (`loop.sh`) spawns a fresh Claude worker inside a Docker container for each iteration. The worker reads `PROMPT.md`, picks one incomplete task from `IMPLEMENTATION_PLAN.md`, completes it, commits, and exits. The loop then starts the next iteration. **Your job as orchestrator** is to start the loop, monitor progress, and intervene when something goes wrong.

## Quick Status
```bash
git log --oneline -5
grep -cE '^\s*-\s*\[x\]' IMPLEMENTATION_PLAN.md  # Tasks done
grep -cE '^\s*-\s*\[ \]' IMPLEMENTATION_PLAN.md   # Tasks remaining
```

## Start the Sandboxed Loop

Each iteration runs Claude in a Docker container with capped memory, CPU, and PIDs. The worker operates with `--dangerously-skip-permissions` but is isolated by the container boundary.

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
# Container resource usage
docker stats --filter "name=sandbox-loop" --no-stream

# Recent commits
git log --oneline -5

# Task progress
grep -cE '^\s*-\s*\[x\]' IMPLEMENTATION_PLAN.md
grep -cE '^\s*-\s*\[ \]' IMPLEMENTATION_PLAN.md

# Tail the current iteration log
tail -f .loop-logs/iteration-*.log | head -100
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

As the orchestrator (human or Claude), you should:

1. **Start the loop** with `SANDBOX=1 ./loop.sh 20`
2. **Monitor progress every ~5 minutes** — check task counts, commits, and container memory
3. **Intervene on stuck iterations** — if the same task fails across multiple iterations, investigate the logs in `.loop-logs/` and update `PROMPT.md` or `IMPLEMENTATION_PLAN.md` to unblock the worker
4. **Adjust resources** if OOM or timeout errors are frequent
5. **Verify completion** — when all tasks are `[x]`, run the Phase 6 verification steps manually or start a final iteration to confirm
6. **Report to the user proactively** — don't wait to be asked. Summarize what changed, what's stuck, and what you're doing about it

## Operational Learnings

Lessons learned from running this epic. **Future orchestrators should read this first.**

### Docker Monitoring

- Container names include PID and iteration suffix: `sandbox-loop-<PID>-<ITERATION>` (e.g. `sandbox-loop-6324-1`)
- Use `docker ps --filter "name=sandbox-loop"` to find the current container, then pass the exact name to `docker stats`
- The `--filter` flag on `docker stats --no-stream` can miss containers; pass the exact container name instead
- Typical memory usage for a Claude worker: **~300 MiB / 8 GiB (3-4%)** — well within the 8g default limit
- If no container shows up, it's likely between iterations (container exited, loop hasn't spawned next one yet)

### Worker Behavior: Task Granularity Problem

**Critical issue observed on first run**: The IMPLEMENTATION_PLAN.md breaks Phase 1 into 5 separate tasks (1.1 data classes, 1.2 helper functions, 1.3 command handlers, 1.4 argparse, 1.5 constants). But the worker correctly identified that **these tasks are inseparable** — removing data classes (1.1) without removing the functions that reference them in type annotations (1.2, 1.3) breaks `import swarm` due to Python 3.11's eager annotation evaluation. This causes the worker to spend a long time deliberating about whether to follow the letter of the plan vs. keeping code functional.

**Intervention if stuck**: If the worker loops on this analysis without making progress, update PROMPT.md to say:
> "Phase 1 tasks 1.1-1.3 may be combined into a single operation if needed to keep the codebase importable. Mark all completed tasks."

Or consolidate tasks 1.1-1.5 in IMPLEMENTATION_PLAN.md into a single task.

### Monitoring Setup

**Use `sleep` + inline checks in a loop** — don't rely on background monitor scripts. The orchestrator should run `sleep 300` (5 minutes), then run the monitoring commands directly, then sleep again. This keeps the orchestrator actively in the conversation loop and ensures it actually sees and acts on problems.

Do NOT use background scripts that write to a log file — the orchestrator won't get woken up to read them. Background tasks only produce `<system-reminder>` nudges when there's new output, and the orchestrator only processes those when the user sends a message.

Each check should include:
- Task counts (`grep -cE` on IMPLEMENTATION_PLAN.md)
- Recent git commits
- Docker container memory/CPU/PIDs (use exact container name from `docker ps`)
- Whether `loop.sh` is still running (`pgrep -f "loop.sh"`)
- Last 3 lines of the latest iteration log

### Done Signal: PROMPT.md Must Tell Workers to Say `/done`

The loop checks for `/done` in the worker's output to terminate. **PROMPT.md must explicitly instruct the worker to output `/done` when all tasks are complete.** Without this, the worker will keep verifying everything is done each iteration but never emit the stop signal, wasting iterations.

### Timing Expectations

- Workers spend significant time **reading and analyzing** before making changes (5-10 min of reasoning is normal)
- A single iteration that removes ~2000 lines of code may take 10-20 minutes
- The pre-commit hook runs the full test suite, adding several minutes to each commit
- Budget ~30 min per complex iteration, ~10 min per simple one (doc updates, file deletions)

## Progress

| Phase | Description | Tasks |
|-------|-------------|-------|
| Phase 1 | Remove workflow code from swarm.py | 5 tasks |
| Phase 2 | Delete workflow test files | 2 tasks |
| Phase 3 | Delete workflow spec, update spec README | 2 tasks |
| Phase 4 | Update README.md, CLAUDE.md, cross-ref specs | 3 tasks |
| Phase 5 | Clean up remaining references | 2 tasks |
| Phase 6 | Verify tests pass, CLI clean, no stale refs | 3 tasks |

**Total: 17 tasks**

## Key Files

| File | Role |
|------|------|
| `ORCHESTRATOR.md` | This file — orchestration runbook for Claude or human |
| `PROMPT.md` | Injected into each Claude worker iteration |
| `IMPLEMENTATION_PLAN.md` | Task checklist the worker reads and updates |
| `loop.sh` | Bash loop that spawns sandboxed Claude workers |
| `Dockerfile.sandbox` | Docker image definition for the sandbox container |
| `.loop-logs/` | Per-iteration output logs |
