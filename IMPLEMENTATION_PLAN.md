# Implementation Plan: Screen-Stable Inactivity Detection

**Created**: 2026-02-04
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

**Status**: NOT IMPLEMENTED

**Location**: `swarm.py:2381-2471`

**Changes**:
1. Remove `mode` parameter entirely (no more `output|ready|both`)
2. Add helper function to normalize screen content:
   - Capture only last 20 lines
   - Strip ANSI escape codes using regex: `\x1b\[[0-9;]*m`
3. Hash normalized content with `hashlib.md5()`
4. Compare hashes instead of full strings
5. Change poll interval from 1s to 2s
6. Remove all ready pattern matching logic

**Current signature**:
```python
def detect_inactivity(worker: Worker, timeout: int, mode: str = "ready") -> bool:
```

**New signature**:
```python
def detect_inactivity(worker: Worker, timeout: int) -> bool:
```

---

### Task 2: Update default inactivity timeout

**Status**: NOT IMPLEMENTED

**Locations**:
- `swarm.py:162` - `RalphState` dataclass default
- `swarm.py:196` - `RalphState.from_dict()` fallback
- `swarm.py:910` - argparse `--inactivity-timeout` default

**Change**: 300 → 60

---

### Task 3: Remove `--inactivity-mode` flag

**Status**: NOT IMPLEMENTED

**Locations**:
- `swarm.py:163` - Remove from `RalphState` dataclass
- `swarm.py:178-179` - Remove from `to_dict()`
- `swarm.py:196-197` - Remove from `from_dict()`
- `swarm.py:912` - Remove argparse argument
- `swarm.py:1229-1230` - Remove from spawn command
- `swarm.py:2175-2176` - Remove from ralph status output
- `swarm.py:2835` - Remove from `detect_inactivity()` call

---

### Task 4: Update tests

**Status**: NOT IMPLEMENTED

**Files to update**:
- `test_cmd_ralph.py` - Remove tests for `inactivity_mode`, update any that reference it
- `test_integration_ralph.py` - Update integration tests for new behavior

**New tests to add**:
- Test that ANSI codes are stripped before comparison
- Test that only last 20 lines are considered
- Test that screen stable for 60s triggers inactivity
- Test that changing screen resets the timer

---

### Task 5: Update spec

**Status**: NOT IMPLEMENTED

**File**: `specs/ralph-loop.md`

**Changes**:
- Lines 51-52: Change default from 300 to 60
- Lines 89-100: Replace detection methods section with screen-stable description
- Line 100: Remove `--inactivity-mode` documentation
- Line 473: Remove `--inactivity-mode` from CLI arguments table

---

## Verification

After implementation:
- [ ] `python3 -m pytest test_cmd_ralph.py -v` passes
- [ ] `python3 -m pytest tests/test_integration_ralph.py -v` passes (requires tmux)
- [ ] Manual test: spawn ralph worker, verify it restarts within ~60s of Claude going idle
- [ ] `--inactivity-timeout 10` works for quick testing

---

## Notes

- Keeping spinner stripping out of scope for now - ANSI stripping should handle most noise
- If spinners remain a problem, can add spinner character stripping later (`⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏|/-\`)
