# Ralph CLI Feedback

Based on real-world usage attempting to run a README improvement loop, here are observations and suggestions for improving the Ralph CLI experience.

## Resolution Status

> **Updated 2026-02-06**: Issues and feature requests from this document have been triaged and addressed. See status markers on each item below.
>
> - ✅ **Resolved** — Fix or feature implemented
> - ⏳ **Deferred** — Not addressed in this cycle; tracked for future work
> - ℹ️ **Won't fix** — By design or not reproducible

## Issues Encountered

### 1. `ralph spawn` blocks by default - unexpected behavior ✅ Resolved (help text)

**Problem:** Running `swarm ralph spawn ...` blocks indefinitely, monitoring the loop until completion. This was surprising - I expected it to spawn and return like regular `swarm spawn`.

**Current workaround:** Use `--no-run` flag, then `swarm ralph run <name>` separately, or background with `&`.

**Suggestions:**
- Consider making non-blocking the default (matches `swarm spawn` behavior)
- Or rename to `swarm ralph run` to make blocking behavior obvious
- At minimum, add prominent note in `--help` output: "Note: This command blocks until the loop completes. Use --no-run for fire-and-forget."

**Resolution:** The blocking behavior is by design — it allows the monitor to detect inactivity and restart the agent. Help text has been updated to clearly document that `ralph spawn` blocks and to highlight `--no-run` for fire-and-forget usage. CLAUDE.md also documents both patterns.

### 2. Inactivity timeout default (60s) too short for repos with pre-commit hooks ✅ Resolved (B7)

**Problem:** The default 60s inactivity timeout caused premature restarts when commits triggered long-running pre-commit hooks (test suites). The agent appeared "inactive" while waiting for git commit to complete.

**Suggestions:**
- Increase default to 180s or 300s - most real work involves waiting for builds/tests
- Add guidance in help text: "Default: 60s. Increase for repos with CI hooks (e.g., --inactivity-timeout 300)"
- Consider detecting common patterns (e.g., "Running..." in output) to pause the inactivity timer

**Resolution:** Default inactivity timeout increased from 60s to 180s. Help text updated with guidance to increase for repos with slow CI hooks. Pattern-based timer pausing deferred as a future enhancement.

### 3. State persists after `kill --rm-worktree` - requires manual cleanup ✅ Resolved (B1)

**Problem:** After killing a ralph worker, the ralph state in `~/.swarm/ralph/<name>/` persisted. Respawning with different options (like a new timeout) kept the old settings.

**Current workaround:** Manually `rm -rf ~/.swarm/ralph/<name>` before respawning.

**Suggestions:**
- `swarm kill <name> --rm-worktree` should also clean ralph state when the worker is a ralph worker
- Add `swarm ralph clean <name>` command for explicit ralph state cleanup
- Or add `--clean-state` flag to `swarm ralph spawn` to start fresh

**Resolution:** `swarm kill <name> --rm-worktree` now automatically removes the ralph state directory (`~/.swarm/ralph/<name>/`) when killing a ralph worker. Additionally, `--clean-state` flag added to `swarm ralph spawn` for clearing state without killing the worker.

### 4. No `--tmux` flag for `ralph spawn` - confusing since regular spawn has it ✅ Resolved (B6)

**Problem:** Ran `swarm ralph spawn --tmux ...` and got a confusing error about `--tmux-socket` expecting an argument. Ralph is always tmux-based, but the inconsistency with regular spawn is confusing.

**Suggestions:**
- Accept `--tmux` as a no-op for consistency, or
- Provide clearer error: "Ralph workers always use tmux. The --tmux flag is not needed."

**Resolution:** `--tmux` is now accepted as a no-op flag on `ralph spawn`. When used, it prints an informational note: "Ralph workers always use tmux (--tmux flag has no effect)."

### 5. Errors during spawn leave partial state ✅ Resolved (B2)

**Problem:** Failed spawn attempts (due to existing worktree, git issues, etc.) left behind partial state that blocked subsequent attempts with "worker already exists" errors.

**Suggestions:**
- Atomic spawning: don't register worker until fully initialized
- Or auto-cleanup on spawn failure
- Better error messages: "Worker 'X' exists but is stopped. Use 'swarm clean X' or 'swarm ralph spawn --force X' to replace it."

**Resolution:** Ralph spawn is now transactional. If any step fails (worktree creation, tmux window, state registration), all previously created resources are rolled back in reverse order. No more orphaned partial state.

### 6. `git config core.bare` got set to `true` mysteriously ✅ Resolved (B3)

**Problem:** During worktree operations, the main repo's `.git/config` had `core.bare = true` set, causing all git commands to fail with "fatal: this operation must be run in a work tree". This blocked spawning new workers.

**Current workaround:** Manually run `git config core.bare false`.

**Suggestions:**
- Investigate what operation sets `bare = true` and prevent it
- Add a check in swarm commands that detects this misconfiguration and auto-fixes or warns
- Include this in troubleshooting docs

**Resolution:** Swarm now auto-detects and fixes `core.bare = true` before worktree operations. A `check_and_fix_core_bare()` function runs before creating worktrees, issuing a warning if it corrects the setting. Documented in CLAUDE.md troubleshooting section.

### 6. No way to see what timeout a running ralph loop is using ℹ️ Already works

**Problem:** After multiple attempts with different timeouts, I couldn't easily verify which timeout was active without reading the state file directly.

**Suggestion:** `swarm ralph status` already shows timeout (it does show "Inactivity timeout: 300s"), but it required reading a JSON file to debug during setup. Consider adding timeout to `swarm ls` output for ralph workers.

**Resolution:** No change needed — `swarm ralph status` already displays the inactivity timeout. Adding timeout to `swarm ls` output is deferred as a minor enhancement.

### 7. "stopped" status is ambiguous - doesn't explain why or what's actually happening ✅ Resolved (B4 + B5)

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

**Resolution:** Two fixes address this:
- **B4 (exit_reason tracking):** RalphState now tracks `exit_reason` with specific values: `done_pattern`, `max_iterations`, `killed`, `failed`, `monitor_disconnected`. Status output shows the reason, not just "stopped".
- **B5 (monitor disconnect handling):** When the monitor disconnects while the worker is still running, ralph status detects this and shows `exit_reason: monitor_disconnected` with a note about the worker's current status. Users can resume monitoring with `swarm ralph resume`.

## Help Text Improvements ✅ Resolved (5.2)

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

**Resolution:** Help text for all ralph commands has been updated to follow `specs/cli-help-standards.md`. Includes blocking behavior note, examples, and updated default values.

## Feature Requests

### 1. `swarm ralph spawn --replace` ✅ Resolved (F1)

Auto-clean existing worker/worktree/state before spawning. Saves the manual cleanup dance.

**Resolution:** `--replace` flag implemented. Automatically kills existing worker, removes worktree (if present), clears ralph state and heartbeat state, then proceeds with a fresh spawn.

### 2. Better inactivity detection ⏳ Deferred

Instead of pure screen-stability timeout, consider:
- Detecting "Running..." or spinner patterns and pausing timer
- Watching for specific "still working" indicators
- Option to use CPU/process activity instead of screen output

**Resolution:** Deferred for future work. The increased default timeout (180s) mitigates the most common case. Pattern-based detection adds complexity and risks false positives. May revisit if users continue to report premature restarts.

### 3. `swarm ralph logs` command ✅ Resolved (F2)

Show the iteration log (`~/.swarm/ralph/<name>/iterations.log`) without needing to know the path.

```bash
swarm ralph logs agent           # Show iteration history
swarm ralph logs agent --live    # Tail -f the iteration log
```

**Resolution:** `swarm ralph logs` command implemented with `--live` (tail -f) and `--lines N` (last N entries) flags.

### 4. Estimated time remaining ✅ Resolved (F3)

Based on average iteration duration, show ETA in `swarm ralph status`:
```
Iteration: 3/10 (avg 4m/iter, ~28m remaining)
```

**Resolution:** ETA calculation added to `swarm ralph status`. Shows average iteration duration and estimated time remaining when the loop is running and has completed at least one iteration.

### 5. `swarm kill --rm-worktree` should clean ralph state too ✅ Resolved (B1)

Currently you need to manually `rm -rf ~/.swarm/ralph/<name>` after killing a ralph worker. The `--rm-worktree` flag should also remove ralph state, or there should be a `--rm-state` flag.

**Resolution:** `swarm kill <name> --rm-worktree` now removes ralph state directory automatically. See Issue #3 above.

### 6. Commit messages getting replaced with "initial" ⏳ Deferred

**Problem:** The agent's descriptive commit messages (e.g., "docs: improve Quick Start section") were replaced with "initial" in the final commits. This may be caused by pre-commit hooks or some other interference.

**Impact:** Required manual squash/rewrite of commits after the loop completed.

**Suggestions:**
- Investigate what's overwriting commit messages
- Consider using `--no-verify` by default for ralph iterations, or make it an option
- Document this gotcha if it's repo-specific

**Resolution:** Deferred. This appears to be repo-specific behavior caused by pre-commit hooks that modify commit messages. Swarm does not control agent commit behavior — this should be addressed in the prompt file or repo hook configuration. Adding a `--no-verify` flag to ralph is tracked as a potential future enhancement.

### 7. Test artifact files committed accidentally ✅ Resolved (F7)

**Problem:** The agent created and committed `new.txt` and `test.txt` test files alongside the README changes. These had to be manually removed.

**Suggestions:**
- Add `.gitignore` patterns for common test artifacts
- Consider a `--verify-changes` flag that shows a diff before committing
- Document best practices for prompt files to discourage test file creation

**Resolution:** Best practices for preventing test artifact creation documented in `specs/ralph-loop.md`. Includes prompt guidelines to instruct agents not to create test files, and recommended `.gitignore` patterns for common test artifacts.

## Summary

The main friction points were:
1. **Unexpected blocking** - `ralph spawn` blocking was surprising → ✅ Documented in help text
2. **Timeout too short** - 60s default doesn't work for real repos with CI → ✅ Default now 180s
3. **Stale state** - cleanup after failed attempts was manual and tedious → ✅ Auto-cleanup + `--replace` + `--clean-state`
4. **Inconsistent flags** - `--tmux` works for spawn but not ralph spawn → ✅ Accepted as no-op
5. **Ambiguous "stopped" status** - doesn't explain why, or that the worker may still be running → ✅ `exit_reason` tracking + monitor disconnect detection
6. **Git bare repo corruption** - mysterious `core.bare = true` broke everything → ✅ Auto-detection and fix
7. **Commit message interference** - pre-commit hooks replaced messages with "initial" → ⏳ Deferred (repo-specific)
8. **Test artifacts committed** - agent created test files that got included → ✅ Best practices documented

Most issues have been addressed with better defaults, clearer help text, automatic cleanup of failed/killed workers, more informative status messages, and transactional spawn behavior. The two deferred items (better inactivity detection, commit message interference) are tracked for future work.
