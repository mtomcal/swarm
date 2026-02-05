# Ralph CLI Feedback

Based on real-world usage attempting to run a README improvement loop, here are observations and suggestions for improving the Ralph CLI experience.

## Issues Encountered

### 1. `ralph spawn` blocks by default - unexpected behavior

**Problem:** Running `swarm ralph spawn ...` blocks indefinitely, monitoring the loop until completion. This was surprising - I expected it to spawn and return like regular `swarm spawn`.

**Current workaround:** Use `--no-run` flag, then `swarm ralph run <name>` separately, or background with `&`.

**Suggestions:**
- Consider making non-blocking the default (matches `swarm spawn` behavior)
- Or rename to `swarm ralph run` to make blocking behavior obvious
- At minimum, add prominent note in `--help` output: "Note: This command blocks until the loop completes. Use --no-run for fire-and-forget."

### 2. Inactivity timeout default (60s) too short for repos with pre-commit hooks

**Problem:** The default 60s inactivity timeout caused premature restarts when commits triggered long-running pre-commit hooks (test suites). The agent appeared "inactive" while waiting for git commit to complete.

**Suggestions:**
- Increase default to 180s or 300s - most real work involves waiting for builds/tests
- Add guidance in help text: "Default: 60s. Increase for repos with CI hooks (e.g., --inactivity-timeout 300)"
- Consider detecting common patterns (e.g., "Running..." in output) to pause the inactivity timer

### 3. State persists after `kill --rm-worktree` - requires manual cleanup

**Problem:** After killing a ralph worker, the ralph state in `~/.swarm/ralph/<name>/` persisted. Respawning with different options (like a new timeout) kept the old settings.

**Current workaround:** Manually `rm -rf ~/.swarm/ralph/<name>` before respawning.

**Suggestions:**
- `swarm kill <name> --rm-worktree` should also clean ralph state when the worker is a ralph worker
- Add `swarm ralph clean <name>` command for explicit ralph state cleanup
- Or add `--clean-state` flag to `swarm ralph spawn` to start fresh

### 4. No `--tmux` flag for `ralph spawn` - confusing since regular spawn has it

**Problem:** Ran `swarm ralph spawn --tmux ...` and got a confusing error about `--tmux-socket` expecting an argument. Ralph is always tmux-based, but the inconsistency with regular spawn is confusing.

**Suggestions:**
- Accept `--tmux` as a no-op for consistency, or
- Provide clearer error: "Ralph workers always use tmux. The --tmux flag is not needed."

### 5. Errors during spawn leave partial state

**Problem:** Failed spawn attempts (due to existing worktree, git issues, etc.) left behind partial state that blocked subsequent attempts with "worker already exists" errors.

**Suggestions:**
- Atomic spawning: don't register worker until fully initialized
- Or auto-cleanup on spawn failure
- Better error messages: "Worker 'X' exists but is stopped. Use 'swarm clean X' or 'swarm ralph spawn --force X' to replace it."

### 6. `git config core.bare` got set to `true` mysteriously

**Problem:** During worktree operations, the main repo's `.git/config` had `core.bare = true` set, causing all git commands to fail with "fatal: this operation must be run in a work tree". This blocked spawning new workers.

**Current workaround:** Manually run `git config core.bare false`.

**Suggestions:**
- Investigate what operation sets `bare = true` and prevent it
- Add a check in swarm commands that detects this misconfiguration and auto-fixes or warns
- Include this in troubleshooting docs

### 6. No way to see what timeout a running ralph loop is using

**Problem:** After multiple attempts with different timeouts, I couldn't easily verify which timeout was active without reading the state file directly.

**Suggestion:** `swarm ralph status` already shows timeout (it does show "Inactivity timeout: 300s"), but it required reading a JSON file to debug during setup. Consider adding timeout to `swarm ls` output for ralph workers.

### 7. "stopped" status is ambiguous - doesn't explain why or what's actually happening

**Problem:** After iteration 1 completed, `swarm ralph status` showed:
```
Status: stopped
Iteration: 2/5
```

But `swarm ls` showed the worker was still running:
```
readme-improver  running  swarm-c1e90142:readme-improver  38s  ...
```

The iteration log showed `reason=killed` even though the iteration completed successfully:
```
2026-02-05T15:58:56 [DONE] loop complete after 1 iterations reason=killed
```

This is very confusing. The **worker** is running but the **monitoring loop** stopped. There's no indication of:
- Why it stopped (monitor crashed? disconnected? intentional?)
- Whether the worker is still active
- What to do about it

**What actually happened:** The background monitoring process (`swarm ralph spawn` running in background) lost connection or crashed, but the tmux worker kept running. The agent continued working, but nobody was watching to restart it on stall.

**Expected behavior:** If iteration 1 completed and iteration 2 started successfully, the status should be `running`, not `stopped`. The fact that it says "stopped" while on "Iteration: 2/5" is contradictory.

**Suggestions:**
- **Fix the core bug:** If `current_iteration` advanced and worker is alive, status should be `running`
- Distinguish between different "stopped" states:
  - `stopped: completed` - all iterations done or done-pattern matched
  - `stopped: monitor disconnected` - worker still running, but not being watched
  - `stopped: max failures` - too many consecutive failures
  - `stopped: user paused` - via `swarm ralph pause`
- Show worker status alongside ralph status: "Ralph: stopped (monitor disconnected), Worker: running"
- Log why the monitor stopped, not just that it stopped
- Consider auto-recovery: if worker is still running, resume monitoring automatically

## Help Text Improvements

### `swarm ralph spawn --help`

Current description is minimal. Suggest adding:

```
IMPORTANT NOTES:
  - This command BLOCKS until the loop completes (use --no-run to spawn only)
  - Default inactivity timeout is 60s - increase for repos with slow CI hooks
  - The prompt file is re-read each iteration, so you can modify it mid-loop

EXAMPLES:
  # Basic usage (blocks until complete)
  swarm ralph spawn --name agent --prompt-file ./PROMPT.md --max-iterations 10 --worktree -- claude --dangerously-skip-permissions

  # Fire-and-forget (spawn and return immediately)
  swarm ralph spawn --name agent --prompt-file ./PROMPT.md --max-iterations 10 --worktree --no-run -- claude --dangerously-skip-permissions
  swarm ralph run agent  # Start monitoring in background

  # With longer timeout for repos with pre-commit hooks
  swarm ralph spawn --name agent --prompt-file ./PROMPT.md --max-iterations 10 --inactivity-timeout 300 --worktree -- claude --dangerously-skip-permissions
```

## Feature Requests

### 1. `swarm ralph spawn --replace`

Auto-clean existing worker/worktree/state before spawning. Saves the manual cleanup dance.

### 2. Better inactivity detection

Instead of pure screen-stability timeout, consider:
- Detecting "Running..." or spinner patterns and pausing timer
- Watching for specific "still working" indicators
- Option to use CPU/process activity instead of screen output

### 3. `swarm ralph logs` command

Show the iteration log (`~/.swarm/ralph/<name>/iterations.log`) without needing to know the path.

```bash
swarm ralph logs agent           # Show iteration history
swarm ralph logs agent --live    # Tail -f the iteration log
```

### 4. Estimated time remaining

Based on average iteration duration, show ETA in `swarm ralph status`:
```
Iteration: 3/10 (avg 4m/iter, ~28m remaining)
```

### 5. `swarm kill --rm-worktree` should clean ralph state too

Currently you need to manually `rm -rf ~/.swarm/ralph/<name>` after killing a ralph worker. The `--rm-worktree` flag should also remove ralph state, or there should be a `--rm-state` flag.

### 6. Commit messages getting replaced with "initial"

**Problem:** The agent's descriptive commit messages (e.g., "docs: improve Quick Start section") were replaced with "initial" in the final commits. This may be caused by pre-commit hooks or some other interference.

**Impact:** Required manual squash/rewrite of commits after the loop completed.

**Suggestions:**
- Investigate what's overwriting commit messages
- Consider using `--no-verify` by default for ralph iterations, or make it an option
- Document this gotcha if it's repo-specific

### 7. Test artifact files committed accidentally

**Problem:** The agent created and committed `new.txt` and `test.txt` test files alongside the README changes. These had to be manually removed.

**Suggestions:**
- Add `.gitignore` patterns for common test artifacts
- Consider a `--verify-changes` flag that shows a diff before committing
- Document best practices for prompt files to discourage test file creation

## Summary

The main friction points were:
1. **Unexpected blocking** - `ralph spawn` blocking was surprising
2. **Timeout too short** - 60s default doesn't work for real repos with CI
3. **Stale state** - cleanup after failed attempts was manual and tedious
4. **Inconsistent flags** - `--tmux` works for spawn but not ralph spawn
5. **Ambiguous "stopped" status** - doesn't explain why, or that the worker may still be running
6. **Git bare repo corruption** - mysterious `core.bare = true` broke everything
7. **Commit message interference** - pre-commit hooks replaced messages with "initial"
8. **Test artifacts committed** - agent created test files that got included

Most of these could be addressed with better defaults, clearer help text, automatic cleanup of failed/killed workers, more informative status messages, and investigation into the git/commit issues.
