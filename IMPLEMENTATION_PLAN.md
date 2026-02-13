# Implementation Plan: Round 5 — Ralph Robustness & CLI Ergonomics

**Created**: 2026-02-13
**Status**: PENDING
**Goal**: Implement FEEDBACK.md fixes (compaction detection, done-pattern auto-kill, send pre-clear) and close remaining spec-vs-code gaps (CLI defaults, aliases, crash-safe writes).

---

## Context

A spec-vs-implementation audit on 2026-02-13 found 14 gaps. The highest-impact items align with field-tested FEEDBACK.md issues from running ralph on real projects. This plan addresses all actionable gaps organized by priority.

### Gap Summary

| # | Gap | Spec | Severity |
|---|-----|------|----------|
| 1 | Fatal pattern detection (compaction kill) missing | `specs/ralph-loop.md` | P0 |
| 2 | `--done-pattern` doesn't auto-enable `--check-done-continuous` | `specs/ralph-loop.md` | P0 |
| 3 | Pre-clear sequence (Escape+Ctrl-U) missing from `tmux_send()` | `specs/send.md`, `specs/tmux-integration.md` | P0 |
| 4 | `--raw` flag missing from `swarm send` | `specs/send.md` | P1 |
| 5 | `--max-context` enforcement missing | `specs/ralph-loop.md` | P1 |
| 6 | `--max-iterations` required instead of default 50 | `specs/ralph-loop.md`, `specs/cli-interface.md` | P1 |
| 7 | `--worktree` defaults to False for ralph spawn (spec says True) | `specs/ralph-loop.md`, `specs/cli-interface.md` | P1 |
| 8 | `swarm ralph stop` alias missing | `specs/cli-interface.md` | P1 |
| 9 | `swarm heartbeat ls` alias missing | `specs/cli-interface.md` | P2 |
| 10 | `--no-check-done-continuous` flag missing | `specs/cli-interface.md` | P2 |
| 11 | Crash-safe write-to-temp-then-rename not implemented | `specs/state-management.md` | P2 |
| 12 | Window loss doesn't check done pattern against last content | `specs/ralph-loop.md` | P2 |
| 13 | Disambiguation notes missing from help text | `specs/cli-help-standards.md` | P3 |
| 14 | Respawn doesn't preserve `metadata` field | `specs/respawn.md` | P3 |

---

## Tasks

### Phase 1: Fatal Pattern Detection (Compaction Kill)

- [x] **1.1 Add fatal pattern detection to `detect_inactivity()`**
  - Add `FATAL_PATTERNS` constant: `["Compacting conversation"]`
  - In `detect_inactivity()` (~line 6307), after capturing pane content:
    1. Check content against `FATAL_PATTERNS`
    2. If matched, return `"compaction"` (new return value)
  - File: `swarm.py`

- [x] **1.2 Handle `"compaction"` return in ralph monitor loop**
  - In the outer ralph loop (~line 7010), when `detect_inactivity()` returns `"compaction"`:
    1. SIGTERM the worker process
    2. Log `[FATAL] iteration N -- compaction detected, killing` to iteration log
    3. Set `exit_reason: "compaction"` in RalphState
    4. Do NOT count as consecutive failure
    5. Proceed to next iteration
  - File: `swarm.py`

- [x] **1.3 Add unit tests for fatal pattern detection**
  - Test: compaction text in pane → returns `"compaction"`
  - Test: compaction triggers SIGTERM + next iteration (not failure)
  - Test: `exit_reason` is set to `"compaction"` in state
  - Test: non-fatal content → no compaction trigger
  - File: `test_cmd_ralph.py` (extend existing)

### Phase 2: Done-Pattern Auto-Enables Continuous Check

- [x] **2.1 Make `--check-done-continuous` default True when `--done-pattern` set**
  - Change `--check-done-continuous` from `store_true` to `BooleanOptionalAction` (~line 4011)
    - This gives both `--check-done-continuous` and `--no-check-done-continuous`
    - Default: `None`
  - After argparse, if `args.done_pattern` is set and `args.check_done_continuous is None`:
    - Set `args.check_done_continuous = True`
  - If `args.check_done_continuous` is explicitly `False` (via `--no-check-done-continuous`), respect it
  - File: `swarm.py` (argparse setup + `cmd_ralph_spawn()`)

- [x] **2.2 Add unit tests for auto-enable behavior**
  - Test: `--done-pattern X` without explicit flag → `check_done_continuous` is True
  - Test: `--done-pattern X --no-check-done-continuous` → `check_done_continuous` is False
  - Test: `--done-pattern X --check-done-continuous` → `check_done_continuous` is True
  - Test: no `--done-pattern` → `check_done_continuous` is False (unchanged)
  - File: `test_cmd_ralph.py` (extend existing)

### Phase 3: Pre-Clear Sequence in `tmux_send()`

- [x] **3.1 Add `pre_clear` parameter to `tmux_send()`**
  - Add `pre_clear: bool = True` parameter (~line 3235)
  - When `pre_clear=True`:
    1. Send `Escape` key: `send-keys -t <target> Escape`
    2. Send `C-u` key: `send-keys -t <target> C-u`
    3. Then send literal text via `send-keys -t <target> -l <text>`
    4. Send Enter if `enter=True`
  - When `pre_clear=False`: current behavior (send text directly)
  - File: `swarm.py` (`tmux_send()`)

- [x] **3.2 Add `--raw` flag to `swarm send`**
  - Add `--raw` argument to send subparser (~line 3680)
  - In `cmd_send()`, pass `pre_clear=not args.raw` to `tmux_send()`
  - File: `swarm.py` (parser + `cmd_send()`)

- [x] **3.3 Update internal callers to use `pre_clear=False`**
  - `send_prompt_to_worker()` — prompt injection should NOT pre-clear (it manages its own sequence)
  - `run_heartbeat_monitor()` — heartbeat nudges should NOT pre-clear (they may interrupt work)
  - Any other internal `tmux_send()` callers: audit and set `pre_clear=False` where appropriate
  - File: `swarm.py`

- [x] **3.4 Add unit tests for pre-clear**
  - Test: `tmux_send()` with `pre_clear=True` sends Escape + Ctrl-U before text
  - Test: `tmux_send()` with `pre_clear=False` sends text directly
  - Test: `--raw` flag skips pre-clear
  - Test: default `swarm send` uses pre-clear
  - File: `test_cmd_spawn.py` or new `test_tmux_send.py`

### Phase 4: `--max-context` Enforcement

- [x] **4.1 Add `--max-context` flag to ralph spawn**
  - Add `--max-context` argument: `type=int, default=None` (~line 3990)
  - Store in `RalphState` as `max_context: Optional[int] = None`
  - File: `swarm.py` (argparse + `RalphState` dataclass)

- [x] **4.2 Add context percentage scanning to `detect_inactivity()`**
  - After capturing pane content, if `max_context` is set:
    1. Scan last 3 lines for `(\d+)%` regex
    2. If percentage >= `max_context`: return `"context_nudge"` (first hit)
    3. If percentage >= `max_context + 15`: return `"context_threshold"` (force kill)
  - Track whether nudge was already sent (avoid spam) via flag in state or local var
  - File: `swarm.py` (`detect_inactivity()`)

- [x] **4.3 Handle context returns in ralph monitor loop**
  - `"context_nudge"`: send nudge message to worker via `tmux_send()`:
    `"You're at {n}% context. Commit WIP and /exit NOW."`
  - `"context_threshold"`: SIGTERM the worker, log `[FATAL] context threshold exceeded`, set `exit_reason: "context_threshold"`
  - File: `swarm.py` (ralph monitor loop)

- [x] **4.4 Add unit tests for max-context**
  - Test: pane with `72%` and `max_context=70` → returns nudge
  - Test: pane with `87%` and `max_context=70` → returns threshold (70+15=85)
  - Test: no `--max-context` → no scanning
  - Test: percentage below threshold → no action
  - Test: nudge sent only once per iteration
  - File: `test_cmd_ralph.py` (extend existing)

### Phase 5: CLI Defaults & Aliases

- [x] **5.1 Change `--max-iterations` to default 50**
  - Change from `required=True` to `default=50` (~line 4002)
  - File: `swarm.py`

- [x] **5.2 Change `--worktree` to default True for ralph spawn**
  - Change from `action="store_true"` to `action=argparse.BooleanOptionalAction, default=True` (~line 4030)
  - This gives `--worktree` (explicit True) and `--no-worktree` (explicit False)
  - File: `swarm.py`

- [x] **5.3 Add `swarm ralph stop` alias**
  - Add `stop` subparser to ralph subparsers that accepts `name`, `--rm-worktree`, `--force-dirty`
  - `cmd_ralph_stop()` delegates to `cmd_kill()` with equivalent args
  - File: `swarm.py`

- [x] **5.4 Add `swarm heartbeat ls` alias**
  - Add `ls` subparser as alias for `list` in heartbeat subparsers
  - Route to same handler as `heartbeat list`
  - File: `swarm.py`

- [x] **5.5 Add unit tests for defaults and aliases**
  - Test: ralph spawn without `--max-iterations` uses 50
  - Test: ralph spawn without `--worktree` creates worktree
  - Test: `--no-worktree` skips worktree creation
  - Test: `swarm ralph stop <name>` kills worker
  - Test: `swarm heartbeat ls` lists heartbeats
  - File: `test_cmd_ralph.py`, `test_cmd_heartbeat.py` (extend existing)

### Phase 6: Crash-Safe State Writes

- [x] **6.1 Implement write-to-temp-then-rename for `State._save()`**
  - In `State._save()` (~line 2848):
    1. Write to `STATE_FILE.with_suffix('.json.tmp')`
    2. `os.replace()` temp file to `STATE_FILE` (atomic on POSIX)
  - Apply same pattern to `save_ralph_state()` and `save_heartbeat_state()`
  - File: `swarm.py`

- [x] **6.2 Add unit tests for crash-safe writes**
  - Test: state file is written atomically (temp file created, then renamed)
  - Test: interrupted write doesn't corrupt state file
  - File: `test_state_file_locking.py` (extend existing)

### Phase 7: Window Loss Done-Pattern Check

- [x] **7.1 Check done pattern against last captured content on window loss**
  - In `detect_inactivity()`, when `CalledProcessError` is caught:
    1. Check done pattern against `last_content` (the last successfully captured output)
    2. If matched, return `"done"` instead of `"exited"`
    3. Log `[END] iteration N -- tmux window lost`
  - File: `swarm.py`

- [x] **7.2 Add unit tests for window loss**
  - Test: window loss with done pattern in last content → returns `"done"`
  - Test: window loss without done pattern → returns `"exited"`
  - File: `test_cmd_ralph.py` (extend existing)

### Phase 8: Help Text & Metadata Fixes

- [x] **8.1 Add disambiguation notes to help text**
  - `STATUS_HELP_DESCRIPTION`: add note about `swarm ralph status`
  - `LOGS_HELP_DESCRIPTION`: add note about `swarm ralph logs`
  - `CLEAN_HELP_DESCRIPTION`: add note about `swarm ralph clean`
  - `RALPH_STATUS_HELP_EPILOG`: add note about `swarm status`
  - File: `swarm.py` (help constant strings)

- [x] **8.2 Preserve `metadata` in `cmd_respawn()`**
  - In `cmd_respawn()` (~line 5168), include `metadata` in preserved fields
  - Pass `metadata` to new Worker creation
  - File: `swarm.py`

- [x] **8.3 Add unit test for metadata preservation**
  - Test: respawned worker retains `metadata` from original
  - File: `test_cmd_spawn.py` (extend existing, respawn tests)

### Phase 9: Verify

- [x] **9.1 Run new/modified unit tests**
  - `python3 -m unittest test_cmd_ralph -v`
  - `python3 -m unittest test_cmd_spawn -v`
  - `python3 -m unittest test_cmd_heartbeat -v`
  - `python3 -m unittest test_state_file_locking -v`

- [x] **9.2 Verify CLI changes**
  - `python3 swarm.py ralph spawn --help` → shows `--max-context`, `--max-iterations` default 50, `--worktree`/`--no-worktree`
  - `python3 swarm.py send --help` → shows `--raw`
  - `python3 swarm.py ralph stop --help` → works
  - `python3 swarm.py heartbeat ls` → works

- [x] **9.3 Run full test suite**
  - `python3 -m unittest discover -s . -p 'test_*.py' -v`

---

## Files Modified

| File | Change |
|------|--------|
| `swarm.py` | Fatal pattern detection, done-pattern auto-enable, pre-clear in `tmux_send()`, `--raw` flag, `--max-context`, CLI defaults, aliases, crash-safe writes, window loss fix, help text, metadata preservation |
| `test_cmd_ralph.py` | Extended — compaction, done-pattern auto-enable, max-context, window loss tests |
| `test_cmd_spawn.py` | Extended — pre-clear, metadata preservation tests |
| `test_cmd_heartbeat.py` | Extended — heartbeat ls alias test |
| `test_state_file_locking.py` | Extended — crash-safe write tests |

---

## Spec References

- `specs/ralph-loop.md` — Fatal pattern detection, `--max-context`, done-pattern auto-enable, window loss
- `specs/send.md` — Pre-clear sequence, `--raw` flag
- `specs/tmux-integration.md` — `tmux_send()` pre-clear parameter
- `specs/cli-interface.md` — CLI defaults, aliases
- `specs/cli-help-standards.md` — Disambiguation notes
- `specs/state-management.md` — Crash-safe writes
- `specs/respawn.md` — Metadata preservation

---

## Complexity Notes

- **Phase 1 (compaction kill)**: Medium — new return path in `detect_inactivity()` + monitor loop handling, ~1 hour
- **Phase 2 (done-pattern auto-enable)**: Low — `BooleanOptionalAction` + default logic, ~20 min
- **Phase 3 (pre-clear)**: Medium — modify `tmux_send()`, audit all callers, ~1 hour
- **Phase 4 (max-context)**: Medium — regex scanning + nudge/kill logic, ~1.5 hours
- **Phase 5 (defaults & aliases)**: Low — argparse changes + thin wrappers, ~30 min
- **Phase 6 (crash-safe writes)**: Low — temp+rename pattern in 3 save functions, ~30 min
- **Phase 7 (window loss)**: Low — small change in error handler, ~20 min
- **Phase 8 (help text & metadata)**: Low — string edits + one-line fix, ~20 min
- **Phase 9 (verify)**: Trivial — run tests, ~15 min
- **Phase 10 (smoke tests)**: Medium — live tmux tests, each takes ~30-60s to run, ~15 min per iteration

**Total estimated: ~7 hours of worker time, ~8-12 iterations**

---

## Worker Guidance (for PROMPT.md)

- Phases 1-4 are the core work. Each phase is one iteration.
- Phase 5 (defaults & aliases) can be combined into one iteration since changes are small and independent.
- Phase 6+7 can be combined into one iteration.
- Phase 8 is a quick cleanup iteration.
- Phase 9 is verification.
- Phase 10 smoke tests: each task is one iteration. Worker writes a bash script or runs commands inline, asserts results, cleans up. These require tmux to be available.
- **Tightly-coupled tasks within a phase should be done together** (e.g., 1.1 + 1.2 are inseparable).
- Internal callers audit in 3.3 is critical — grep for all `tmux_send(` calls and set `pre_clear=False` on internal ones.

---

## Phase 10: Real-World Smoke Tests (FEEDBACK.md Validation)

Live-tmux integration tests that verify each FEEDBACK.md issue is actually fixed. Each task is a self-contained test — spawn a worker, wait for expected behavior, assert results, cleanup. Worker runs these one per iteration after Phases 1-9 are complete.

**Important**: These tests require tmux. The worker must run each test script, verify the assertions pass, and clean up before marking the task `[x]`.

### FEEDBACK #1 — Compaction detection kills iteration

- [x] **10.1 Smoke test: compaction detection**
  - Write and run a test script that:
    1. Creates a minimal prompt file: `echo "just exit" > /tmp/fb1-prompt.md`
    2. Runs: `python3 swarm.py ralph spawn --name smoke-fb1 --prompt-file /tmp/fb1-prompt.md --max-iterations 3 --no-worktree -- bash -c 'echo "$ ready"; sleep 5; echo "Compacting conversation"; sleep 120'`
    3. Waits up to 30s, polling `python3 swarm.py ralph status smoke-fb1` until iteration > 1 or status shows compaction
    4. Asserts: ralph logs (`python3 swarm.py ralph logs smoke-fb1`) contain `compaction` or `FATAL`
    5. Asserts: iteration advanced past 1 (compaction didn't count as failure that stopped the loop)
    6. Cleanup: `python3 swarm.py kill smoke-fb1; python3 swarm.py ralph clean smoke-fb1`
  - If assertions pass, mark task `[x]`
  - File: run inline or as a temp script

### FEEDBACK #2 — Done pattern terminates agent promptly

- [x] **10.2 Smoke test: done-pattern auto-kills**
  - Write and run a test script that:
    1. Creates a minimal prompt file: `echo "just exit" > /tmp/fb2-prompt.md`
    2. Runs: `python3 swarm.py ralph spawn --name smoke-fb2 --prompt-file /tmp/fb2-prompt.md --max-iterations 3 --done-pattern "ALL_DONE" --no-worktree -- bash -c 'echo "$ ready"; sleep 5; echo "ALL_DONE"; sleep 300'`
    3. Does NOT pass `--check-done-continuous` (should auto-enable)
    4. Records start time. Waits up to 60s, polling `python3 swarm.py ralph status smoke-fb2` until loop stops
    5. Asserts: loop stopped within 30s of "ALL_DONE" appearing (NOT 180s inactivity timeout)
    6. Asserts: exit reason contains `done`
    7. Cleanup: `python3 swarm.py kill smoke-fb2; python3 swarm.py ralph clean smoke-fb2`
  - If assertions pass, mark task `[x]`

### FEEDBACK #3 — `swarm send` reliably delivers text

- [x] **10.3 Smoke test: send pre-clear delivers text**
  - Write and run a test script that:
    1. Runs: `python3 swarm.py spawn --name smoke-fb3 --tmux -- bash -c 'echo "$ ready"; read line; echo "GOT:$line"; sleep 10'`
    2. Waits for ready (poll `python3 swarm.py status smoke-fb3` until running)
    3. Runs: `python3 swarm.py send smoke-fb3 "hello-test"`
    4. Waits 3s, then captures: `python3 swarm.py peek smoke-fb3`
    5. Asserts: peek output contains `GOT:hello-test`
    6. Cleanup: `python3 swarm.py kill smoke-fb3`
  - If assertions pass, mark task `[x]`

### FEEDBACK #4 — Ralph monitor detects dead worker

- [ ] **10.4 Smoke test: ralph detects window loss**
  - Write and run a test script that:
    1. Creates a minimal prompt file: `echo "just exit" > /tmp/fb4-prompt.md`
    2. Runs: `python3 swarm.py ralph spawn --name smoke-fb4 --prompt-file /tmp/fb4-prompt.md --max-iterations 3 --no-worktree -- bash -c 'echo "$ ready"; sleep 8; exit 0'`
    3. Waits up to 30s, polling `python3 swarm.py ralph status smoke-fb4` until iteration > 1
    4. Asserts: iteration advanced past 1 within 30s (ralph detected the exit, didn't hang)
    5. Asserts: ralph logs show completion of iteration 1
    6. Cleanup: `python3 swarm.py kill smoke-fb4; python3 swarm.py ralph clean smoke-fb4`
  - If assertions pass, mark task `[x]`

### FEEDBACK #5 — Screen change tracking works

- [ ] **10.5 Smoke test: last screen change timestamp**
  - Write and run a test script that:
    1. Creates a minimal prompt file: `echo "just exit" > /tmp/fb5-prompt.md`
    2. Runs: `python3 swarm.py ralph spawn --name smoke-fb5 --prompt-file /tmp/fb5-prompt.md --max-iterations 2 --no-worktree -- bash -c 'echo "$ ready"; while true; do echo "tick"; sleep 2; done'`
    3. Waits 15s for several screen changes to accumulate
    4. Captures: `python3 swarm.py ralph status smoke-fb5`
    5. Asserts: status output contains `Last screen change:` followed by a real time value (NOT `(none)`)
    6. Cleanup: `python3 swarm.py kill smoke-fb5; python3 swarm.py ralph clean smoke-fb5`
  - If assertions pass, mark task `[x]`

### FEEDBACK #6 — `--max-context` nudges and kills

- [ ] **10.6 Smoke test: max-context enforcement**
  - Write and run a test script that:
    1. Creates a minimal prompt file: `echo "just exit" > /tmp/fb6-prompt.md`
    2. Runs: `python3 swarm.py ralph spawn --name smoke-fb6 --prompt-file /tmp/fb6-prompt.md --max-iterations 2 --max-context 70 --no-worktree -- bash -c 'echo "$ ready"; sleep 5; echo "72%"; sleep 20; echo "87%"; sleep 120'`
    3. Waits up to 60s, polling `python3 swarm.py ralph status smoke-fb6` and `python3 swarm.py ralph logs smoke-fb6`
    4. Asserts: ralph logs contain `context` or `threshold` (indicating context enforcement fired)
    5. Asserts: worker was killed (iteration advanced or loop stopped)
    6. Cleanup: `python3 swarm.py kill smoke-fb6; python3 swarm.py ralph clean smoke-fb6`
  - If assertions pass, mark task `[x]`
