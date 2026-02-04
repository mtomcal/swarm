# Implementation Plan: Ralph UX Improvements

**Created**: 2026-02-04
**Status**: Pending
**Goal**: Improve ralph command usability with auto-start, continuous done-pattern checking, and better CLI help

---

## Problem Statement

Current ralph UX has friction points:
1. **Two-command workflow**: Users must run `ralph spawn` then `ralph run` separately
2. **Done pattern only checked after exit**: Wastes time waiting for timeout/exit when pattern already matched
3. **CLI help not agent-friendly**: `swarm ralph --help` doesn't explain prompt design principles
4. **Worktree behavior undocumented**: Spec didn't clarify that worktrees persist across iterations

---

## Solution Overview

| Feature | Description |
|---------|-------------|
| **Auto-start** | `ralph spawn` automatically runs the monitoring loop (add `--no-run` for old behavior) |
| **Continuous done-pattern** | `--check-done-continuous` flag to check pattern during monitoring, not just after exit |
| **CLI help improvements** | Add prompt design principles and workflow guidance to `--help` output |
| **Spec updates** | Document worktree persistence, prompt injection method, mid-iteration intervention |

---

## Tasks

### Phase 1: Auto-start Loop

- [x] **1.1 Add `--no-run` flag to ralph spawn parser**
  - Add `--no-run` boolean flag (default: False)
  - Update help text to explain auto-start is default

- [x] **1.2 Modify `cmd_ralph_spawn()` to auto-start loop**
  - After spawning worker and creating ralph state
  - Unless `--no-run` is set, call internal ralph run logic
  - Ensure proper signal handling for the combined command

- [x] **1.3 Update tests for auto-start behavior**
  - Add test: spawn without `--no-run` blocks and runs loop
  - Add test: spawn with `--no-run` returns immediately
  - Update existing tests that assume spawn-only behavior

### Phase 2: Continuous Done Pattern Checking

- [x] **2.1 Add `--check-done-continuous` flag**
  - Add to ralph spawn parser
  - Store in RalphState dataclass
  - Persist in ralph state JSON

- [x] **2.2 Modify `detect_inactivity()` to check done pattern**
  - If `check_done_continuous` is True
  - Check done pattern each poll cycle (every 2 seconds)
  - Return early if pattern matched (with distinct return value)

- [x] **2.3 Update `_run_ralph_loop()` to handle continuous done**
  - Distinguish between inactivity timeout vs done pattern match
  - Log appropriately: "[ralph] agent: done pattern matched, stopping loop"

- [x] **2.4 Add tests for continuous done pattern**
  - Test: pattern matched during monitoring stops loop immediately
  - Test: pattern NOT matched continues monitoring
  - Test: flag persists in ralph state

### Phase 3: CLI Help Improvements

- [x] **3.1 Enhance `swarm ralph --help` output**
  - Add overview of ralph workflow
  - Include prompt design principles
  - Reference `swarm ralph init` for template

- [x] **3.2 Enhance `swarm ralph spawn --help` output**
  - Document all flags with examples
  - Explain auto-start default behavior
  - Note that `swarm send` works for intervention

- [x] **3.3 Add epilog with examples to subparsers**
  - Show common usage patterns
  - Include worktree example
  - Show intervention example

### Phase 4: Documentation Updates

- [x] **4.1 Update `specs/ralph-loop.md`**
  - Add `--no-run` flag documentation
  - Add `--check-done-continuous` flag documentation
  - Add "Worktree Behavior" section
  - Add "Mid-Iteration Intervention" section
  - Add "Prompt Design Principles" section
  - Update scenarios for new behaviors

- [x] **4.2 Update CLAUDE.md**
  - Update ralph example to show single-command workflow
  - Add note about `--no-run` for scripting

### Phase 5: Verification

- [x] **5.1 Run unit tests**
  ```bash
  python3 -m unittest test_cmd_ralph -v
  ```

- [ ] **5.2 Run integration tests**
  ```bash
  timeout 120 python3 -m unittest tests.test_integration_ralph -v
  ```

- [ ] **5.3 Manual verification**
  ```bash
  # Test auto-start (should block)
  swarm ralph spawn --name test --prompt-file PROMPT.md --max-iterations 2 -- echo hi

  # Test --no-run (should return immediately)
  swarm ralph spawn --name test2 --prompt-file PROMPT.md --max-iterations 2 --no-run -- echo hi
  swarm ralph run test2

  # Test help output
  swarm ralph --help
  swarm ralph spawn --help
  ```

---

## Files to Modify

| File | Changes |
|------|---------|
| `swarm.py` | Add `--no-run`, `--check-done-continuous`, enhance help text, modify spawn/run logic |
| `test_cmd_ralph.py` | Add tests for new flags and behaviors |
| `tests/test_integration_ralph.py` | Add integration tests for auto-start |
| `specs/ralph-loop.md` | Already updated with new behaviors |
| `CLAUDE.md` | Update ralph examples |

---

## Design Decisions

1. **Auto-start as default**: Most users want spawn-and-run. Power users can use `--no-run`.
2. **Continuous check opt-in**: Default behavior unchanged to avoid surprises. Users opt-in with `--check-done-continuous`.
3. **Help as documentation**: CLI help should be comprehensive enough for agents to understand ralph without reading specs.
4. **Intervention via `swarm send`**: No new command needed - existing send works for tmux workers.

---

## Rollback Plan

If issues discovered:
1. `--no-run` can become `--run` (flip the default)
2. `--check-done-continuous` is additive, can be removed
3. Help text changes are non-breaking
