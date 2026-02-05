# Implementation Plan: Ralph Bug Fixes and Improvements

**Created**: 2026-02-05
**Status**: IN PROGRESS
**Goal**: Fix ralph bugs from user feedback and add quality-of-life features

---

## Problem Statement

Real-world usage of `swarm ralph` revealed several bugs and UX issues:

1. **Status ambiguity**: Ralph status shows "stopped/killed" even for successful completions
2. **Stale state**: Ralph state persists after `kill --rm-worktree`, blocking respawns
3. **Failed spawns leave partial state**: No transaction rollback on spawn failure
4. **Git corruption**: Worktree operations can set `core.bare = true`, breaking git
5. **Monitor disconnect**: Monitor can stop while worker keeps running
6. **Inconsistent flags**: `--tmux` errors confusingly for ralph spawn
7. **Timeout too short**: 60s default doesn't work for repos with CI hooks

---

## Solution Overview

| Category | Changes |
|----------|---------|
| **Bug Fixes** | 7 fixes addressing state management, error handling, UX |
| **Features** | 5 new features for better workflow |
| **Spec Updates** | 7 specs need updates to match new behavior |

---

## Tasks

### Phase 1: Spec Updates

Update specs BEFORE implementation to define expected behavior.

- [x] **1.1 Update `specs/ralph-loop.md`**
  - Add `--replace` flag documentation (F1)
  - Add `--clean-state` flag documentation (F5)
  - Add `swarm ralph logs` command section (F2)
  - Update default inactivity timeout to 180s (B7)
  - Add `--tmux` as no-op note (B6)
  - Add ETA display in status output (F3)
  - Document exit_reason tracking (B4)
  - Document monitor disconnect handling (B5)

- [x] **1.2 Update `specs/kill.md`**
  - Add ralph state cleanup behavior for `--rm-worktree` (B1)
  - Add scenario: "Kill ralph worker with worktree removal"

- [x] **1.3 Update `specs/spawn.md`**
  - Add transactional spawn requirements (B2)
  - Document rollback behavior on failure

- [ ] **1.4 Update `specs/worktree-isolation.md`**
  - Add error handling for `git worktree add` failures (B3)
  - Document `core.bare` prevention/recovery
  - Add edge case scenarios

- [ ] **1.5 Update `specs/cli-interface.md`**
  - Document `--tmux` as no-op for ralph spawn (B6)
  - Add ralph logs command to CLI reference

- [ ] **1.6 Update `specs/data-structures.md`**
  - Add `exit_reason` field to RalphState (B4)
  - Document iteration timing for ETA (F3)

- [ ] **1.7 Update `specs/logs.md`**
  - Add cross-reference to `swarm ralph logs` (F2)

### Phase 2: Bug Fixes

- [ ] **2.1 Fix: Ralph state cleanup on kill (B1)**
  - In `cmd_kill()`, delete `~/.swarm/ralph/<name>/` when killing ralph workers with `--rm-worktree`
  - Test: Kill ralph worker with `--rm-worktree`, verify ralph state directory removed
  - File: `swarm.py` (cmd_kill function)

- [ ] **2.2 Fix: Transactional ralph spawn (B2)**
  - Wrap ralph spawn in try/except with rollback
  - If ralph state creation fails, remove worker from state
  - If tmux window creation fails, remove worktree
  - Test: Simulate failures at each stage, verify no orphaned state
  - File: `swarm.py` (cmd_ralph_spawn function)

- [ ] **2.3 Fix: Worktree error handling (B3)**
  - Add proper error checking in `create_worktree()`
  - Validate worktree actually created before returning
  - Add `core.bare` check and auto-fix at start of worktree operations
  - Test: Simulate worktree creation failure, verify clean state
  - File: `swarm.py` (create_worktree function)

- [ ] **2.4 Fix: Status/reason accuracy (B4)**
  - Add `exit_reason` field to RalphState
  - Track actual completion reason: `done_pattern`, `max_iterations`, `killed`, `failed`
  - Update `cmd_kill()` to only set `reason=killed` when actually killed
  - Update ralph status display to show accurate reason
  - Test: Complete ralph loop normally, verify reason shows correctly
  - File: `swarm.py` (RalphState, cmd_kill, _run_ralph_loop)

- [ ] **2.5 Fix: Monitor disconnect handling (B5)**
  - Add worker-alive verification after `detect_inactivity()` returns
  - Distinguish "monitor stopped" from "worker stopped" in status
  - Log why monitor stopped
  - Consider auto-recovery: if worker alive, resume monitoring
  - Test: Kill monitor process while worker runs, verify status reflects reality
  - File: `swarm.py` (_run_ralph_loop, detect_inactivity)

- [ ] **2.6 Fix: `--tmux` flag as no-op (B6)**
  - Add `--tmux` argument to ralph spawn parser (store_true, no effect)
  - Print informational message: "Note: Ralph workers always use tmux"
  - Test: Run `swarm ralph spawn --tmux ...`, verify no error
  - File: `swarm.py` (argparse for ralph spawn)

- [ ] **2.7 Fix: Increase default inactivity timeout (B7)**
  - Change default from 60s to 180s
  - Update help text to explain the default
  - Test: Spawn ralph without `--inactivity-timeout`, verify 180s used
  - File: `swarm.py` (argparse default)

### Phase 3: New Features

- [ ] **3.1 Feature: `--replace` flag for ralph spawn (F1)**
  - Add `--replace` argument to ralph spawn
  - If worker exists: kill it, remove worktree if present, remove ralph state
  - Then proceed with normal spawn
  - Test: Spawn, then spawn again with `--replace`, verify clean replacement
  - File: `swarm.py` (cmd_ralph_spawn)

- [ ] **3.2 Feature: `swarm ralph logs` command (F2)**
  - Add `ralph logs` subcommand
  - Show iteration log from `~/.swarm/ralph/<name>/iterations.log`
  - Add `--live` flag for tail -f behavior
  - Add `--lines N` flag for last N entries
  - Test: Run ralph, use `ralph logs` to view history
  - File: `swarm.py` (new cmd_ralph_logs function)

- [ ] **3.3 Feature: ETA in ralph status (F3)**
  - Track iteration start/end times in RalphState
  - Calculate average iteration duration
  - Display ETA in `swarm ralph status` output
  - Format: "Iteration: 3/10 (avg 4m/iter, ~28m remaining)"
  - Test: Run multi-iteration ralph, verify ETA displayed
  - File: `swarm.py` (RalphState, cmd_ralph_status)

- [ ] **3.4 Feature: `--clean-state` flag for ralph spawn (F5)**
  - Add `--clean-state` argument to ralph spawn
  - Delete existing ralph state directory before spawn (not worker/worktree)
  - Useful when respawning with different config
  - Test: Spawn, kill, spawn with `--clean-state`, verify fresh state
  - File: `swarm.py` (cmd_ralph_spawn)

- [ ] **3.5 Feature: Document test artifact prevention (F7)**
  - Add "Best Practices" section to `specs/ralph-loop.md`
  - Document prompt guidelines to avoid test file creation
  - Add example `.gitignore` patterns for common test artifacts
  - File: `specs/ralph-loop.md`

### Phase 4: Testing

- [ ] **4.1 Add unit tests for bug fixes**
  - Test ralph state cleanup on kill
  - Test transactional spawn rollback
  - Test worktree error handling
  - Test status/reason accuracy
  - Test `--tmux` no-op behavior
  - Test default timeout value
  - File: `test_cmd_ralph.py`

- [ ] **4.2 Add unit tests for new features**
  - Test `--replace` flag
  - Test `ralph logs` command
  - Test ETA calculation
  - Test `--clean-state` flag
  - File: `test_cmd_ralph.py`

- [ ] **4.3 Add integration tests**
  - Test full ralph lifecycle with new features
  - Test replace workflow
  - Test logs during active ralph
  - File: `tests/test_integration_ralph.py`

- [ ] **4.4 Run full test suite**
  ```bash
  python3 -m unittest discover -v
  ```

### Phase 5: Documentation

- [ ] **5.1 Update CLAUDE.md**
  - Document new ralph flags (`--replace`, `--clean-state`)
  - Document `ralph logs` command
  - Update default timeout mention
  - Add troubleshooting for common issues

- [ ] **5.2 Update help text**
  - Verify all new commands have comprehensive help
  - Follow `specs/cli-help-standards.md`

- [ ] **5.3 Update FEEDBACK.md**
  - Mark addressed issues as resolved
  - Note any deferred items

### Phase 6: Verification

- [ ] **6.1 Manual verification - bug fixes**
  ```bash
  # B1: Ralph state cleanup
  swarm ralph spawn --name test --prompt-file ./PROMPT.md --max-iterations 1 --worktree -- bash -c 'echo done'
  swarm kill test --rm-worktree
  ls ~/.swarm/ralph/test  # Should not exist

  # B3: Worktree error handling
  git config core.bare  # Should be false or unset

  # B7: Default timeout
  swarm ralph spawn --help | grep inactivity  # Should show 180
  ```

- [ ] **6.2 Manual verification - features**
  ```bash
  # F1: --replace
  swarm ralph spawn --name test --prompt-file ./PROMPT.md --max-iterations 1 --no-run -- bash
  swarm ralph spawn --name test --prompt-file ./PROMPT.md --max-iterations 1 --replace --no-run -- bash

  # F2: ralph logs
  swarm ralph logs test
  swarm ralph logs test --live

  # F5: --clean-state
  swarm ralph spawn --name test --prompt-file ./PROMPT.md --max-iterations 1 --clean-state --no-run -- bash
  ```

---

## Files to Modify

| File | Changes |
|------|---------|
| `swarm.py` | Bug fixes, new features, argparse updates |
| `specs/ralph-loop.md` | Major updates for all ralph changes |
| `specs/kill.md` | Ralph state cleanup |
| `specs/spawn.md` | Transactional spawn |
| `specs/worktree-isolation.md` | Error handling |
| `specs/cli-interface.md` | CLI updates |
| `specs/data-structures.md` | RalphState schema |
| `specs/logs.md` | Cross-reference |
| `test_cmd_ralph.py` | New tests |
| `tests/test_integration_ralph.py` | Integration tests |
| `CLAUDE.md` | Documentation |

---

## Design Decisions

1. **`--replace` vs `--force`**: Using `--replace` to be explicit about the destructive operation
2. **`--clean-state` separate from `--replace`**: Allows cleaning state without killing worker
3. **180s default timeout**: Balances responsiveness with CI hook compatibility
4. **ETA calculation**: Simple average, not weighted - keeps implementation simple
5. **Ralph logs separate from swarm logs**: Different format (iteration history vs tmux output)

---

## Rollback Plan

All changes are backwards compatible:
1. New flags are optional with sensible defaults
2. Bug fixes improve existing behavior without API changes
3. Spec updates document new behavior alongside existing

---

## Estimated Scope

| Phase | Tasks | Complexity |
|-------|-------|------------|
| Phase 1: Spec Updates | 7 tasks | Low (documentation) |
| Phase 2: Bug Fixes | 7 tasks | Medium (code changes) |
| Phase 3: Features | 5 tasks | Medium (new functionality) |
| Phase 4: Testing | 4 tasks | Medium (test coverage) |
| Phase 5: Documentation | 3 tasks | Low (docs) |
| Phase 6: Verification | 2 tasks | Low (manual testing) |

**Total: 28 tasks**
