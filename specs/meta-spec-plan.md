# Swarm Spec Generation Plan

## Status: In Progress

This document tracks the progress of generating behavioral specifications for the Swarm project.

## Completed Work

### 2026-02-01: P1 Important Specs Generated

Generated all four P1 (Important) specification files:

1. **`spawn.md`** - Complete
   - Worker creation in tmux/process modes
   - Worktree integration
   - Environment variable parsing
   - Tag assignment
   - Ready-wait integration
   - CLI argument documentation

2. **`kill.md`** - Complete
   - Tmux worker termination (kill-window)
   - Process worker termination (SIGTERM/SIGKILL)
   - Graceful shutdown with 5-second timeout
   - Worktree removal with dirty protection
   - Session cleanup logic
   - --all flag for batch operations

3. **`send.md`** - Complete
   - Text transmission to tmux workers
   - Broadcast to all workers (--all)
   - --no-enter option
   - Status validation before send

4. **`tmux-integration.md`** - Complete
   - Session management (create, ensure, kill)
   - Window management (create, check exists)
   - Hash-based session naming for user isolation
   - Socket isolation for testing
   - Pane capture for ready detection
   - Send-keys with literal mode

### 2026-02-01: P0 Critical Specs Generated

Generated all three P0 (Critical) specification files:

1. **`state-management.md`** - Complete
   - JSON schema for worker registry
   - fcntl exclusive locking protocol
   - Atomic load-modify-save pattern
   - Concurrent access behavior
   - Recovery procedures for corrupted state

2. **`ready-detection.md`** - Complete
   - All 13+ ready patterns for Claude Code, OpenCode, and generic CLIs
   - ANSI escape sequence handling
   - Timeout handling (default 120s)
   - Polling interval (0.5s)
   - Integration with spawn --ready-wait

3. **`worktree-isolation.md`** - Complete
   - Worktree creation at `<repo>-worktrees/<worker>/`
   - Branch isolation (one branch per worktree)
   - Dirty detection (staged, unstaged, untracked)
   - Protection against accidental data loss
   - --force-dirty override behavior

### Source Files Analyzed
- `swarm.py` (lines 66-978, 1107-1419)
- `test_worktree_protection.py`
- `test_ready_patterns.py`
- `test_ready_wait_integration.py`
- `test_state_file_locking.py`
- `test_cmd_spawn.py`
- `test_kill_cmd.py`
- `test_kill_integration.py`
- `tests/test_tmux_isolation.py`

## Remaining Work

### P2 - Standard (Next Priority)
- [ ] `ls.md` - List workers with filters
- [ ] `status.md` - Check worker status
- [ ] `logs.md` - View worker output
- [ ] `wait.md` - Block until worker exits
- [ ] `clean.md` - Remove stopped workers
- [ ] `respawn.md` - Restart dead workers
- [ ] `interrupt-eof.md` - Send Ctrl-C/Ctrl-D
- [ ] `attach.md` - Interactive tmux attachment
- [ ] `init.md` - Inject swarm docs into projects

### Supporting
- [ ] `data-structures.md` - Worker, TmuxInfo, WorktreeInfo schemas
- [ ] `environment.md` - Python 3.10+, tmux, git requirements
- [ ] `cli-interface.md` - Argument parsing, exit codes

## Validation Status

### P0 Specs Validation

All P0 specs have been validated against the checklist:

| Spec | Overview | Inputs | Outputs | Errors | Scenarios | Recovery | Dependencies |
|------|----------|--------|---------|--------|-----------|----------|--------------|
| state-management.md | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| ready-detection.md | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| worktree-isolation.md | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |

### P1 Specs Validation

All P1 specs have been validated against the checklist:

| Spec | Overview | Inputs | Outputs | Errors | Scenarios | Recovery | Dependencies |
|------|----------|--------|---------|--------|-----------|----------|--------------|
| spawn.md | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| kill.md | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| send.md | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| tmux-integration.md | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |

## Notes

- P0 and P1 specs form the core behavioral contracts covering lifecycle operations
- `state-management.md` is the foundational spec with no internal dependencies
- `tmux-integration.md` is referenced by spawn, kill, send, and ready-detection
- `worktree-isolation.md` depends on state-management for WorktreeInfo storage
- `spawn.md` is the most heavily cross-referenced spec (creates workers using all other P0/P1 features)
- Cross-references between specs are noted in Dependencies sections
