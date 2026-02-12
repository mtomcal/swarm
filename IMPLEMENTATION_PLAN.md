# Implementation Plan: Round 3 — Ralph Diagnostics & UX Improvements

**Created**: 2026-02-12
**Status**: COMPLETE
**Goal**: Implement code changes from the Round 3 spec updates — stuck pattern detection, pre-flight validation, corrupt state recovery, `--foreground` flag, screen change tracking in status, and login/OAuth not-ready patterns.

---

## Context

Round 3 feedback from directing a Docker-sandboxed ralph session surfaced several diagnostics and UX gaps. The specs and docs have already been updated (commit `58f9955`). The `sandbox.sh` template and `Dockerfile.sandbox` template changes in `swarm.py` are already committed. The remaining items below require implementation in `swarm.py` and new tests.

---

## Tasks

### Phase 1: Login/OAuth Not-Ready Patterns

- [x] **1.1 Add login/OAuth not-ready patterns to `wait_for_agent_ready()`**
  - Add patterns: `Select login method`, `Paste code here`
  - These join the existing theme picker patterns in `not_ready_patterns` list
  - When matched, send Enter to dismiss and continue polling (existing behavior)
  - File: `swarm.py` (~line 3279, `not_ready_patterns` list)

- [x] **1.2 Add unit tests for login/OAuth not-ready detection**
  - Test: `Select login method` text does not trigger ready detection
  - Test: `Paste code here` text does not trigger ready detection
  - Test: login prompt followed by real ready pattern eventually succeeds
  - File: `test_ready_patterns.py`

### Phase 2: Corrupt State Recovery

- [x] **2.1 Add JSONDecodeError handling to `load_ralph_state()`**
  - Catch `json.JSONDecodeError` in `load_ralph_state()` (~line 2604)
  - On error:
    1. Log warning: `"swarm: warning: corrupt ralph state for '<name>', resetting"`
    2. Back up corrupted file to `state.json.corrupted`
    3. Create and return fresh default RalphState (worker_name from param, prompt_file="PROMPT.md")
    4. Continue execution — do NOT crash
  - File: `swarm.py` (~line 2604-2619)

- [x] **2.2 Add unit tests for corrupt state recovery**
  - Test: corrupted JSON file → returns fresh RalphState + logs warning
  - Test: corrupted file is backed up to `state.json.corrupted`
  - Test: empty file → returns fresh RalphState
  - File: `test_cmd_ralph.py`

### Phase 3: Screen Change Tracking

- [x] **3.1 Add `last_screen_change` field to `RalphState`**
  - Add field: `last_screen_change: Optional[str] = None` (ISO format timestamp)
  - Add to `to_dict()` and `from_dict()` serialization
  - File: `swarm.py` (~line 1997, RalphState dataclass)

- [x] **3.2 Update `detect_inactivity()` to track screen changes**
  - When screen content hash changes, update `ralph_state.last_screen_change` to current ISO timestamp
  - Save updated ralph state after change
  - File: `swarm.py` (~line 5963, `detect_inactivity()`)

- [x] **3.3 Display `Last screen change` in `cmd_ralph_status()`**
  - Calculate seconds since `last_screen_change` and display as `"Last screen change: 5s ago"`
  - If no screen change recorded yet, display `"Last screen change: (none)"`
  - File: `swarm.py` (~line 5579, `cmd_ralph_status()`)

- [x] **3.4 Add unit tests for screen change tracking**
  - Test: `last_screen_change` field serializes/deserializes correctly
  - Test: status output includes `Last screen change` line
  - File: `test_cmd_ralph.py`

### Phase 4: Stuck Pattern Detection

- [x] **4.1 Define stuck patterns constant**
  - Create `STUCK_PATTERNS` dict mapping pattern strings to warning messages:
    - `"Select login method"` → `"Worker stuck at login prompt. Check auth credentials."`
    - `"Choose the text style"` → `"Worker stuck at theme picker. Check settings.local.json."`
    - `"looks best with your terminal"` → `"Worker stuck at theme picker. Check settings.local.json."`
    - `"Paste code here"` → `"Worker stuck at OAuth code entry. Use ANTHROPIC_API_KEY instead."`
  - File: `swarm.py` (near module-level constants)

- [x] **4.2 Implement stuck pattern detection in `detect_inactivity()`**
  - During each 2-second poll cycle, after hashing screen content, check normalized content against `STUCK_PATTERNS`
  - If a stuck pattern is detected and hasn't been warned about yet this iteration:
    - Log `[WARN]` to iterations.log: `"2026-02-12T13:24:30 [WARN] iteration 1: Worker stuck at login prompt. Check auth credentials."`
    - Track warned patterns in a set to avoid log spam (once per pattern per iteration)
  - File: `swarm.py` (~line 5963, `detect_inactivity()`)

- [x] **4.3 Add unit tests for stuck pattern detection**
  - Test: stuck pattern in screen content triggers `[WARN]` log entry
  - Test: same stuck pattern only warned once per iteration (no spam)
  - Test: different stuck patterns each trigger their own warning
  - File: `test_cmd_ralph.py`

### Phase 5: Stuck Detection in Status Output

- [x] **5.1 Show "(possibly stuck)" in status when screen unchanged >60s**
  - In `cmd_ralph_status()`, if `last_screen_change` is older than 60 seconds:
    - Append `(possibly stuck — no output change for <N>s)` to the Status line
    - Display last 5 lines of terminal output under `"Last output:"` section
    - Use `tmux_capture_pane()` to get current terminal content
  - File: `swarm.py` (~line 5579, `cmd_ralph_status()`)

- [x] **5.2 Add unit tests for stuck detection in status**
  - Test: status shows `(possibly stuck)` when screen unchanged >60s
  - Test: status includes last 5 terminal lines when stuck
  - Test: status does NOT show stuck when screen changed recently
  - File: `test_cmd_ralph.py`

### Phase 6: Pre-flight Validation

- [x] **6.1 Implement pre-flight check after iteration 1 prompt injection**
  - After `send_prompt_to_worker()` on iteration 1 only:
    1. Wait 10 seconds
    2. Capture terminal output via `tmux_capture_pane()`
    3. Check against `STUCK_PATTERNS`
    4. If stuck pattern detected:
       - Log `[ERROR]` to iterations.log
       - Print actionable error to stderr: `"swarm: error: pre-flight check failed — <warning>.\n  fix: <fix instructions>"`
       - Kill worker and exit with code 1
    5. If no stuck pattern, continue normal monitoring
  - File: `swarm.py` (in ralph monitoring loop, after first `send_prompt_to_worker()`)

- [x] **6.2 Add unit tests for pre-flight validation**
  - Test: stuck pattern on iteration 1 → `[ERROR]` log + exit code 1
  - Test: no stuck pattern on iteration 1 → continues normally
  - Test: pre-flight only runs on iteration 1, not subsequent iterations
  - File: `test_cmd_ralph.py`

### Phase 7: `--foreground` Flag for Ralph Spawn

- [x] **7.1 Add `--foreground` argument to ralph spawn parser**
  - Add `--foreground` flag (default: False) to ralph spawn argparse
  - File: `swarm.py` (in `main()` argparse setup, ralph spawn subparser)

- [x] **7.2 Implement non-blocking default / foreground option in `cmd_ralph_spawn()`**
  - When `--foreground` is False (default) and `--no-run` is False:
    - Start monitoring loop as a background subprocess (e.g., `subprocess.Popen` running `swarm ralph run <name>`)
    - Print status + monitoring commands (peek, status, logs, kill)
    - Return immediately
  - When `--foreground` is True:
    - Call monitoring loop directly (blocking, current behavior)
  - When `--no-run` is True:
    - Skip starting the loop entirely (current behavior)
  - File: `swarm.py` (~line 5218, `cmd_ralph_spawn()`)

- [x] **7.3 Update spawn output to include monitoring commands**
  - After spawning with non-blocking default, print:
    ```
    spawned <name> (tmux: <session>:<window>) [ralph mode: iteration 1/100]

    Monitor:
      swarm ralph status <name>    # loop progress
      swarm peek <name>            # terminal output
      swarm ralph logs <name>      # iteration history
      swarm kill <name>            # stop worker
    ```
  - File: `swarm.py` (~line 5218, `cmd_ralph_spawn()`)

- [x] **7.4 Update `--replace` to terminate monitoring loop process**
  - When `--replace` is specified and an existing worker has a running ralph monitoring loop:
    - Find the monitoring loop process (store PID in ralph state or find by process name)
    - Send SIGTERM to terminate it
    - Then proceed with existing cleanup (kill worker, remove worktree, remove ralph state)
  - File: `swarm.py` (~line 5218, `cmd_ralph_spawn()`)

- [x] **7.5 Add unit tests for `--foreground` flag**
  - Test: default spawn without `--foreground` prints monitoring commands
  - Test: `--foreground` flag accepted by parser
  - Test: `--no-run` still works (no loop started)
  - File: `test_cmd_ralph.py`

### Phase 8: Verify

- [x] **8.1 Run unit tests**
  - `python3 -m unittest test_cmd_ralph -v`
  - `python3 -m unittest test_ready_patterns -v`

- [x] **8.2 Verify CLI**
  - `python3 swarm.py ralph spawn --help` → shows `--foreground` flag
  - `python3 swarm.py ralph status --help` → works

- [x] **8.3 Run full test suite**
  - `python3 -m unittest discover -s . -p 'test_*.py' -v`
  - Note: may crash swarm workers per CLAUDE.md caveat — run in isolation

---

## Files Modified

| File | Change |
|------|--------|
| `swarm.py` | Login/OAuth not-ready patterns, corrupt state recovery, screen change tracking, stuck patterns, pre-flight validation, `--foreground` flag, non-blocking spawn default, monitoring command output, `--replace` monitor termination |
| `test_cmd_ralph.py` | Tests for corrupt state, screen change tracking, stuck detection, pre-flight, `--foreground` |
| `test_ready_patterns.py` | Tests for login/OAuth not-ready patterns |

---

## Spec References

All spec changes are already committed in `58f9955`:
- `specs/ralph-loop.md` — Stuck Pattern Detection, Pre-flight Validation, Corrupt State Recovery, `--foreground` flag, non-blocking default, screen change tracking, stuck status output
- `specs/ready-detection.md` — Login/OAuth not-ready patterns
- `specs/spawn.md` — Environment propagation chain docs

---

## Complexity Notes

- **Phase 1 (login/OAuth patterns)**: Trivial — 2 pattern additions, 30 min
- **Phase 2 (corrupt state)**: Low — try/except + backup, 30 min
- **Phase 3 (screen change tracking)**: Low-Medium — new field + plumbing, 45 min
- **Phase 4 (stuck pattern detection)**: Medium — detection in poll loop + logging, 1 hour
- **Phase 5 (stuck status output)**: Low-Medium — conditional status display, 45 min
- **Phase 6 (pre-flight validation)**: Medium — timing + error handling, 1 hour
- **Phase 7 (`--foreground` flag)**: Medium — background process management + output changes, 1.5 hours
- **Phase 8 (verify)**: Trivial — run tests, 15 min

**Total estimated: ~6 hours of worker time, ~8-12 iterations**

---

## Execution Results

**Status**: COMPLETE
**Runner**: `loop.sh` with `SANDBOX=1` (Docker-sandboxed, `claude -p` pipe mode)
**Completed**: 2026-02-12

### Timeline

| Event | Time (UTC) |
|-------|------------|
| Epic kicked off | 14:29 |
| First attempt (ralph spawn, 180s timeout) | 14:29–14:51 — **failed** (7 iterations lost to inactivity timeout) |
| Second attempt (ralph spawn, 600s timeout) | 14:51 — killed, switched to loop.sh |
| Third attempt (loop.sh SANDBOX=1, tmux) | 14:53 — success |
| Phase 1 complete (login/OAuth patterns) | 14:55 |
| Phase 2 complete (corrupt state recovery) | 14:59 |
| Phase 3 complete (screen change tracking) | 15:11 |
| Phase 4 complete (stuck pattern detection) | 15:19 |
| Phase 5 complete (stuck status output) | 15:27 |
| Phase 6 complete (pre-flight validation) | 15:33 |
| Phase 7 complete (--foreground flag) | 15:47 |
| Phase 8 complete (verification) | 15:55 |
| Done signal emitted | 15:57 |

### Stats

| Metric | Value |
|--------|-------|
| Total wall time (successful run) | ~65 min (14:53–15:58) |
| Productive iterations | 8 (phases 1–8, one commit each) |
| Post-done iterations | 12 (iterations 9–20, worker re-confirmed done) |
| Total iterations used | 20/20 |
| Commits | 8 (7 feature + 1 verification) |
| Lines changed | +5,623 / -4,032 across 3 files |
| Files modified | `swarm.py` (+208), `test_cmd_ralph.py` (+5,367), `test_ready_patterns.py` (+48) |
| Test coverage | 95% (pre-commit hook) |

### Commits

| Commit | Phase | Description |
|--------|-------|-------------|
| `2cdc152` | 1 | feat: add login/OAuth not-ready patterns to wait_for_agent_ready() |
| `1e03f07` | 2 | feat: add corrupt ralph state recovery in load_ralph_state() |
| `31109b0` | 3 | feat: add screen change tracking to ralph status and detect_inactivity() |
| `949ad06` | 4 | feat: add stuck pattern detection to detect_inactivity() |
| `561c9d5` | 5 | feat: add stuck detection display to ralph status output |
| `c65cede` | 6 | feat: add pre-flight validation to ralph monitoring loop |
| `603db0e` | 7 | feat: add --foreground flag and background-default spawn to ralph |
| `05135f3` | 8 | chore: mark Phase 8 verification tasks complete in implementation plan |

### Lessons Learned

- **`swarm ralph spawn` with 180s inactivity timeout is too short for Docker-sandboxed workers** — Docker startup + Claude reasoning + pre-commit test suite exceeds it. Use `--inactivity-timeout 600` or higher.
- **`loop.sh` with `SANDBOX=1` is more reliable than `swarm ralph spawn` for Docker sandboxes** — no inactivity timeout to tune, `claude -p` pipe mode waits for completion naturally.
- **`loop.sh` needs a tmux session** — `docker run -it` requires a TTY, so `nohup` backgrounding fails. Use `tmux new-session -d` instead.
- **Done pattern mismatch**: `loop.sh` checks for `/done` but PROMPT.md uses `SWARM_DONE_X9K`. Worker completed but loop didn't stop — burned 12 extra iterations confirming done. Align patterns next time.
