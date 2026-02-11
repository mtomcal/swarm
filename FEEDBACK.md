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

---

## Round 2 — Swarm + Docker Sandbox Issues (2026-02-11)

Real-world session attempting to run a ralph worker with a Docker sandbox (`sandbox.sh` wrapping `docker run ... claude`). Multiple blocking issues discovered.

### 8. `--done-pattern` self-matches against prompt content sent via `tmux send-keys` ✅ Resolved (docs/specs)

**Problem:** When using `--check-done-continuous`, the done pattern is checked against the entire tmux pane buffer. Since `send_prompt_to_worker()` types the full PROMPT.md content into the terminal via `tmux send-keys -l`, any done pattern that appears literally in the prompt text will immediately self-match, stopping the loop before the agent does any work.

**Example:** PROMPT.md contained the text `Output /done on its own line and stop.` The done pattern was `--done-pattern "/done"`. The loop stopped after 26 seconds with `exit_reason: done_pattern` — the agent had claimed the task but hadn't started working.

**Workaround:** Split the done signal across string concatenation so the literal pattern never appears in the prompt: `python3 -c "print('SWARM'+'_DONE'+'_X9K')"`. This is fragile and ugly.

**Suggestions:**
- **Best fix:** After sending the prompt via `tmux send-keys`, clear the terminal (`tmux send-keys -t ... C-l`) or mark a "baseline" buffer position. Only check for done patterns in output that appears AFTER the prompt was sent.
- **Alternative:** Don't scan the first N seconds after sending the prompt (grace period).
- **Alternative:** Strip the prompt content from the captured pane before pattern matching.
- **Document the footgun:** At minimum, warn in help text: "WARNING: The done pattern must NOT appear literally in your prompt file when using --check-done-continuous."

**Severity:** Critical — silently breaks the loop with no useful error. Appears to work (iteration starts, task is claimed) but stops immediately.

**Resolution:** Documented as a known footgun in `specs/ralph-loop.md` (Done Pattern Detection section), `specs/cli-interface.md` (Ralph Spawn Caveats), `CLAUDE.md` (Troubleshooting), and `README.md` (Caveats). Recommended mitigation: use a unique signal pattern (e.g., `SWARM_DONE_X9K`) that cannot appear in prompt prose. Baseline buffer position approach documented as the preferred code fix for future implementation.

### 9. `sandbox.sh` / Docker needs `-it` flags for interactive CLI tools ✅ Resolved (template fix)

**Problem:** The `sandbox.sh` template uses `docker run --rm` without `-it` (interactive + TTY). When tmux creates a window running `./sandbox.sh`, the tmux pane provides a TTY to `sandbox.sh` but Docker doesn't pass it through to the container. Claude Code inside Docker gets no TTY and exits immediately with: `Error: Input must be provided either through stdin or as a prompt argument when using --print`.

The tmux window dies silently (no error visible to swarm), then `send_prompt_to_worker()` tries `tmux send-keys` to a dead window and gets `exit status 1`.

**Fix:** Change `docker run --rm` to `docker run --rm -it` in `sandbox.sh`.

**Suggestions:**
- Document this requirement in the Dockerfile.sandbox / sandbox template.
- Consider having swarm detect that the tmux window died during spawn and provide a clearer error: "Worker window exited before agent became ready. Check your command."

**Resolution:** `SANDBOX_SH_TEMPLATE` in swarm.py and `sandbox.sh` in `specs/project-onboarding.md` updated to use `docker run --rm -it`. `docs/sandbox-loop-spec.md` updated with `-it` requirement and explanation. The `run_claude_sandboxed()` example also updated.

### 10. Docker container hits Claude Code first-time theme picker ✅ Resolved (Dockerfile fix)

**Problem:** Fresh Docker containers don't have Claude Code's theme preference set. When `claude` starts inside a new container, it shows an interactive theme picker ("Choose the text style that looks best with your terminal") which blocks all input. The prompt sent by `send_prompt_to_worker()` goes into the theme picker instead of the Claude Code prompt.

**Workaround:** Run workers natively (without Docker sandbox) to avoid the first-time setup. Or pre-configure the theme in the Docker image.

**Suggestions:**
- Add `claude --theme dark` or equivalent to the Dockerfile to pre-set the theme during image build.
- Or mount the host's full `~/.claude/` directory (not just credentials and settings) so the container inherits all preferences.
- Or add a `CLAUDE_THEME=dark` environment variable that skips the picker.
- The `wait_for_agent_ready()` function should detect the theme picker as a "not ready" state and handle it (e.g., send Enter to accept the default).

**Resolution:** `Dockerfile.sandbox` updated to pre-configure theme: `echo '{"theme":"dark"}' > settings.local.json`. Dockerfile examples in `docs/sandbox-loop-spec.md` and `specs/project-onboarding.md` also updated. Theme picker added as a "Not-Ready State" in `specs/ready-detection.md` with detection patterns and suggested handling. Code fix for `wait_for_agent_ready()` to auto-dismiss deferred.

### 11. `--worktree` + Docker sandbox fails (worktree path not accessible inside container) ✅ Resolved (docs)

**Problem:** When `--worktree` is used with a Docker sandbox, the worktree is created on the host at a path like `/home/user/code/.worktrees/worker-abc123/`. The Docker command in `sandbox.sh` mounts `$(pwd):/workspace`, but `pwd` inside the worktree is the worktree path. The Docker container mounts the worktree, but the worktree may have different path requirements or the Docker image may not be configured to handle arbitrary mount points.

**Workaround:** Skip `--worktree` when using Docker sandbox.

**Suggestions:**
- Document the incompatibility: "When using Docker sandbox, omit --worktree. The Docker container provides its own isolation."
- Or have swarm detect Docker commands and adjust worktree behavior automatically.

**Resolution:** Documented as incompatible in `specs/ralph-loop.md` (Docker Sandbox Caveats), `specs/cli-interface.md` (Ralph Spawn Caveats), `docs/sandbox-loop-spec.md` (Known Caveats), `CLAUDE.md` (Troubleshooting), and `README.md` (Caveats). Guideline: omit `--worktree` when using Docker sandbox. Auto-detection of Docker commands deferred.

### 12. `ralph run` exits silently when backgrounded from Claude Code ✅ Resolved (docs)

**Problem:** Running `swarm ralph run worker &` from within a Claude Code session (which itself runs in a sandbox) causes the monitoring loop to exit immediately with no output. The process starts but can't maintain the foreground monitoring connection when double-backgrounded.

**Workaround:** The worker continues running in tmux regardless of the monitor. Check on it manually with `swarm ralph status` and `tmux capture-pane`.

**Suggestions:**
- Document that `ralph run` must be run in a real terminal, not backgrounded from within another agent.
- Add a `--daemon` flag that properly daemonizes the monitor with PID file tracking.
- Consider using tmux itself to host the monitor (separate window) instead of relying on foreground process.

**Resolution:** Documented as a limitation in `specs/ralph-loop.md` (Docker Sandbox Caveats — Ralph Run Backgrounding) and `docs/sandbox-loop-spec.md` (Known Caveats). Workarounds documented: use `nohup`, run in its own tmux window, or use `ralph spawn` (which auto-starts the monitor). `--daemon` mode deferred as a future enhancement.

## Round 2 Summary

> **Updated 2026-02-11**: All Round 2 issues have been addressed with documentation, spec updates, and template fixes. See status markers on each item.

The main friction points in this session:
1. **Done pattern self-match** — prompt content typed into terminal matches the done pattern, silently stopping the loop → ✅ Documented footgun + mitigation in specs, CLAUDE.md, README.md
2. **Docker TTY** — missing `-it` flags cause silent container death → ✅ Fixed in SANDBOX_SH_TEMPLATE, sandbox-loop-spec, project-onboarding
3. **Theme picker** — fresh containers hit first-time setup blocking automation → ✅ Dockerfile.sandbox updated + theme picker added to ready-detection spec
4. **Worktree + Docker** — incompatible combination not documented → ✅ Documented in all relevant specs and docs
5. **Monitor backgrounding** — `ralph run` can't be backgrounded from within another agent → ✅ Documented limitation with workarounds; `--daemon` mode deferred

### Additional improvements in this round:
6. **`swarm ralph ls`** — added as alias for `swarm ralph list` (consistency with `swarm ls`)
7. **`swarm ralph clean`** — new command spec for cleaning ralph state (`<name>` or `--all`)
8. **README.md** — fixed `--inactivity-timeout` default from 60s to 180s
