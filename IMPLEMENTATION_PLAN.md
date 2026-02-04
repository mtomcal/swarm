# Implementation Plan: Screen-Stable Inactivity Detection

**Created**: 2026-02-04
**Completed**: 2026-02-04
**Goal**: Replace brittle "ready pattern" inactivity detection with robust "screen stable" approach

---

## Problem Statement

The current `detect_inactivity` function in ralph mode is not reliably detecting when Claude is idle:

- **"ready" mode** looks for prompt patterns (`> `, `❯ `, `bypass permissions`, etc.) but these patterns may not match or may match incorrectly depending on Claude's UI state
- **"output" mode** compares full screen content but is affected by spinners, timestamps, and other noise
- **Default timeout of 300s (5 min)** is too long - Claude sits idle waiting for restart

---

## Solution: Screen-Stable Detection

Inspired by Playwright's `networkidle` pattern - wait until the screen has "settled" for a specified duration.

### Algorithm

1. Capture last 20 lines of tmux pane
2. Strip ANSI escape codes to normalize content
3. Hash the normalized content (MD5)
4. If hash unchanged for `--inactivity-timeout` seconds (default: 60s), trigger restart
5. Poll every 2 seconds

---

## Tasks

### Task 1: Update `detect_inactivity` function

**Status**: ✅ COMPLETE

**Location**: `swarm.py:2381-2450`

**Changes**:
1. Removed `mode` parameter entirely (no more `output|ready|both`)
2. Added helper function to normalize screen content:
   - Capture only last 20 lines
   - Strip ANSI escape codes using regex: `\x1b\[[0-9;]*m`
3. Hash normalized content with `hashlib.md5()`
4. Compare hashes instead of full strings
5. Changed poll interval from 1s to 2s
6. Removed all ready pattern matching logic

**New signature**:
```python
def detect_inactivity(worker: Worker, timeout: int) -> bool:
```

---

### Task 2: Update default inactivity timeout

**Status**: ✅ COMPLETE

**Locations updated**:
- `swarm.py:162` - `RalphState` dataclass default
- `swarm.py:193` - `RalphState.from_dict()` fallback
- `swarm.py:907` - argparse `--inactivity-timeout` default

**Change**: 300 → 60

---

### Task 3: Remove `--inactivity-mode` flag

**Status**: ✅ COMPLETE

**Locations updated**:
- `swarm.py:163` - Removed from `RalphState` dataclass
- `swarm.py:165-177` - Removed from `to_dict()`
- `swarm.py:182-193` - Removed from `from_dict()`
- `swarm.py:909-911` - Removed argparse argument
- `swarm.py:1222-1223` - Removed from spawn command
- `swarm.py:2168` - Removed from ralph status output
- `swarm.py:2814` - Removed from `detect_inactivity()` call
- `swarm.py:2826` - Removed mode from restart message

---

### Task 4: Update tests

**Status**: ✅ COMPLETE

**Files updated**:
- `test_cmd_ralph.py` - Removed tests for `inactivity_mode`, updated all references

**New tests added**:
- `TestScreenStableInactivityDetection` class with:
  - `test_detect_inactivity_no_tmux_returns_false`
  - `test_detect_inactivity_signature_no_mode_param`
  - `test_detect_inactivity_returns_true_when_screen_stable`
  - `test_detect_inactivity_returns_false_when_worker_exits`
  - `test_detect_inactivity_resets_timer_on_screen_change`
  - `test_detect_inactivity_strips_ansi_codes`
  - `test_detect_inactivity_uses_last_20_lines`
- `TestRalphSpawnWithDefaultTimeout` - Tests default timeout is 60s

**Removed test classes**:
- `TestInactivityModeArgument`
- `TestRalphStateInactivityMode`
- `TestDetectInactivityModes`
- `TestRalphSpawnWithInactivityMode`
- `TestRalphStatusShowsInactivityMode`
- `TestDetectInactivityReadyPatterns`

---

### Task 5: Update spec

**Status**: ✅ COMPLETE (was already updated)

**File**: `specs/ralph-loop.md`

The spec already reflects the screen-stable approach with:
- Default timeout of 60s documented
- Screen-stable algorithm documented in "Inactivity Detection" section
- No `--inactivity-mode` in CLI arguments table

---

## Verification

After implementation:
- [x] `python3 -m unittest test_cmd_ralph -v` passes (203 tests)
- [x] `python3 -m unittest tests.test_integration_ralph -v` passes (17 tests in ~10s)
- [x] Manual test: spawn ralph worker, verify it restarts within ~60s of Claude going idle
  - Verified via integration test `test_ralph_inactivity_triggers_restart` with 5s timeout
  - Full 60s timeout testing is optional for production validation
- [x] `--inactivity-timeout 10` works for quick testing (verified in integration tests)

---

## Notes

- Keeping spinner stripping out of scope for now - ANSI stripping should handle most noise
- If spinners remain a problem, can add spinner character stripping later (`⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏|/-\`)
