# Swarm Feedback: Director Experience Running Ralph Loop (2026-02-12)

## Context

Interactive Claude Code session (the "director") orchestrating a single Docker-sandboxed ralph worker for the `stick-rumble` project. Worker runs via `swarm ralph spawn --name dev --prompt-file PROMPT.md --max-iterations 50 -- ./sandbox.sh --dangerously-skip-permissions`.

## Friction Points

### 1. `swarm ralph logs` is too sparse for debugging launch failures

`swarm ralph logs dev` only shows iteration start/stop lines:
```
2026-02-12T13:24:20 [START] iteration 1/50
```

When the worker is stuck (e.g., at a login prompt), logs show nothing useful. The only way to diagnose was dropping down to raw tmux:
```bash
tmux capture-pane -t swarm-c1e90142:dev -p | tail -30
```

This revealed the OAuth login picker was blocking the agent — information completely invisible through swarm's own monitoring tools.

**Suggestion**: `swarm ralph logs` (or a `--verbose` flag) should include recent terminal output, not just iteration lifecycle events. Even a `swarm ralph peek dev` command that captures the last N lines of the tmux pane would help enormously.

### 2. No diagnostic tooling for "worker spawned but not doing anything"

The worker showed `Status: running, Iteration: 1/50, Consecutive failures: 0` — everything looked healthy. But the agent was stuck at an interactive prompt and doing zero work. There's no way to distinguish "working" from "stuck at a prompt" without manually inspecting tmux.

**Suggestion**: A health check that detects common stuck states (login prompts, theme pickers, permission dialogs) would save significant debugging time. Even a simple "last output changed N seconds ago" indicator in `swarm ralph status` would help.

### 3. Director should never need to know tmux exists

As a director (Claude Code session managing workers), `swarm ralph status` and `swarm ralph logs` were insufficient for every real debugging scenario we hit. To actually diagnose the stuck worker, I had to:
- Know that swarm uses tmux under the hood
- Discover the session name convention (`swarm-c1e90142`)
- Know that worker names map to tmux window names (`:dev`)
- Run `tmux capture-pane -t swarm-c1e90142:dev -p | tail -30`

Tmux is an implementation detail — the director should be able to rely entirely on swarm commands. Proposed changes:

1. **`swarm peek <name>`** — Capture last N lines of the worker's terminal output. This is the single most important missing command. It wraps `tmux capture-pane` so the director never needs to know tmux exists.
   ```bash
   swarm peek dev          # last 30 lines
   swarm peek dev -n 100   # last 100 lines
   ```

2. **`swarm ralph status` should include terminal context** — When a worker has been in the same iteration for >60s with no progress, `status` should automatically include the last few lines of terminal output. A stuck login prompt would be immediately visible:
   ```
   Ralph Loop: dev
   Status: running (possibly stuck — no output change for 90s)
   Iteration: 1/50
   Last output:
     Select login method:
     > 1. Claude account with subscription
   ```

3. **`swarm ralph logs --live`** — Stream the worker's terminal output in real-time (wraps `tmux capture-pane` in a watch loop or uses `tmux pipe-pane`). Different from `swarm attach` because it's read-only and doesn't risk accidentally sending keystrokes.

4. **Built-in stuck detection in ralph monitor** — The ralph loop already has inactivity timeout. Extend it to detect known stuck patterns in the terminal output:
   - "Select login method" → log warning: "Worker stuck at login prompt. Check auth credentials."
   - "Choose the text style" → log warning: "Worker stuck at theme picker. Check settings.local.json."
   - "Paste code here" → log warning: "Worker stuck at OAuth code entry."

   These warnings should appear in `swarm ralph logs` so the director sees them without having to peek.

The goal: a director should be able to manage workers using only `swarm` commands, never `tmux` directly.

### 4. Docker credential mounting is a minefield

We went through multiple iterations trying to get Claude Code to authenticate inside the container:

1. **Individual file mount (`:ro`)** — Claude Code couldn't refresh the token
2. **Individual file mount (`:rw`)** — Still showed login picker
3. **Full `~/.claude` directory mount** — Overwrote the Dockerfile's `settings.local.json` (theme picker fix), and Claude Code still showed login picker
4. **Pinned Claude Code version** — Same result

The root cause: Claude Code's interactive mode always shows a login picker on fresh launch, even with valid OAuth credentials in `.credentials.json`. Only `-p` (print) mode auto-authenticates. This is a Claude Code issue, not a swarm issue, but swarm's ralph mode depends on interactive sessions.

**Resolution path**: `ANTHROPIC_API_KEY` env var bypasses OAuth entirely. This should be the documented approach for Docker sandboxes.

**Suggestion**: The `sandbox.sh` template and sandbox docs should call out that OAuth credentials don't work for interactive Docker sessions and recommend `ANTHROPIC_API_KEY` as the primary auth method. The current docs suggest mounting `.credentials.json` which doesn't work.

### 5. `swarm ralph spawn` blocks by default — hostile to director agents

`swarm ralph spawn` blocks the calling process for the entire loop lifetime (potentially hours). This is a major problem for AI directors:

- The director's Claude Code session is frozen waiting on a background task
- Every spawn attempt consumed a background task slot, and when spawns failed, stale task notifications trickled in for minutes afterward
- The director can't monitor, intervene, or do anything else while spawn is blocking
- Using `--no-run` + `swarm ralph run` is a workaround, but `ralph run` also blocks

The current default assumes a human running spawn in a dedicated terminal. An AI director doesn't have that luxury — it has one execution context.

**Suggestion**: `swarm ralph spawn` should be non-blocking by default. It should:
1. Spawn the worker
2. Start the monitoring loop in the background
3. Print a status confirmation and monitoring instructions, then return immediately

```
$ swarm ralph spawn --name dev --prompt-file PROMPT.md --max-iterations 50 -- ./sandbox.sh

Spawned dev (iteration 1/50)

Monitor:
  swarm ralph status dev    # loop progress
  swarm peek dev            # terminal output
  swarm ralph logs dev      # iteration history
  swarm kill dev            # stop worker

```

If someone really wants blocking behavior, offer `--block` or `--foreground`. But the default should return control to the caller immediately. This is especially important for AI directors that need to poll status, check task progress, and intervene — none of which they can do while blocked.

### 6. Ralph state file corruption

After 3 iterations (which were all stuck at login prompts), the ralph state JSON file got corrupted:
```
json.decoder.JSONDecodeError: Extra data: line 21 column 2 (char 5619)
```

This crashed the monitoring loop entirely. Required `swarm ralph clean dev` to recover.

**Suggestion**: `load_ralph_state()` should handle corrupt JSON gracefully — either recover from backup, reset state, or at minimum log a clear error and continue rather than crashing the entire loop.

### 7. `swarm ls` shows stale workers from previous sessions

`swarm ls` listed 18 workers, only 1 active. The 17 stopped workers from 11 hours ago cluttered the output and made it harder to spot the active worker.

**Suggestion**: `swarm ls` should have a `--running` or `--active` filter flag. Or at minimum, visually separate active vs stopped workers.

### 8. Multiple respawn attempts left background task zombies

Each failed `swarm ralph spawn` from the director session left a background task notification that fired later with stale error messages. We got 4 separate `task-notification` interruptions for old attempts long after we'd moved on. This is partly a Claude Code background task issue, but swarm's `--replace` flag should ensure cleaner teardown.

### 9. No pre-flight validation before starting the loop

We burned 4 spawn attempts (~10 minutes) before discovering auth was broken inside the container. Each time: spawn → wait 15-20s → peek tmux → see login prompt → kill → try fix → repeat.

Swarm could catch this on the first attempt with a pre-flight check:

**Suggestion**: `swarm ralph spawn` should run a quick validation before committing to the loop:
1. Launch the command (e.g., `./sandbox.sh --version` or `./sandbox.sh -p "say ok"`)
2. Verify it exits cleanly and produces expected output
3. Only then start the real loop

Or at minimum, after iteration 1 starts, peek the terminal after ~10s and check for known stuck patterns (login prompt, theme picker). If detected, abort immediately with a clear error instead of letting the inactivity timeout eventually kill it 3 minutes later.

```
$ swarm ralph spawn --name dev --prompt-file PROMPT.md --max-iterations 50 -- ./sandbox.sh

Pre-flight check... FAILED
Worker stuck at login prompt. Auth is not configured for the sandbox.
Fix: export ANTHROPIC_API_KEY=sk-ant-... and retry.
```

### 10. No way to pass env vars through ralph spawn to the sandbox

We needed `ANTHROPIC_API_KEY` inside the container. The `sandbox.sh` passes it via `-e ANTHROPIC_API_KEY`, which reads from the shell environment. But when ralph spawns the worker in a tmux window, it inherits the environment from the tmux server — not from the shell that called `swarm ralph spawn`.

`swarm ralph spawn` has `--env KEY=VAL` but it's unclear whether these propagate into the tmux window environment and then into Docker. The env chain is: director shell → swarm spawn → tmux window → sandbox.sh → docker run → claude. Every hop is a place where env vars can get lost.

**Suggestion**: Document the env propagation chain clearly. Test and guarantee that `--env ANTHROPIC_API_KEY=sk-ant-...` makes it all the way into the container. If tmux strips env vars, swarm should work around it (e.g., writing a wrapper script that re-exports them).

## What Worked Well

- `swarm ralph spawn --replace` cleanly killed and respawned workers
- `swarm ralph clean dev` recovered from corrupted state
- `swarm kill dev` was reliable and fast
- The Docker sandbox architecture (resource limits, network lockdown) is solid
- `sandbox.sh` auto-build is convenient
- The `next-task.py` task expansion (raw -> implement/review/test-review) is well-designed

## Summary

The main gap is **observability**. Swarm's monitoring tools (`status`, `logs`) report on the loop lifecycle but are blind to what's happening inside the agent's terminal. Every real debugging scenario required dropping to `tmux capture-pane`. For a director (human or AI) managing workers, the terminal state IS the most important diagnostic signal.
