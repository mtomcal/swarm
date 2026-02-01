# Swarm Spec Generation Plan

## Status: In Progress

This document tracks the progress of generating behavioral specifications for the Swarm project.

## Completed Work

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
- `swarm.py` (lines 66-607, 854-1773)
- `test_worktree_protection.py`
- `test_ready_patterns.py`
- `test_ready_wait_integration.py`
- `test_state_file_locking.py`

## Remaining Work

### P1 - Important (Next Priority)
- [ ] `spawn.md` - Worker creation in tmux/process modes
- [ ] `kill.md` - Worker termination, worktree cleanup
- [ ] `send.md` - Sending text input to tmux workers
- [ ] `tmux-integration.md` - Session/window management

### P2 - Standard
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

## Notes

- The P0 specs form the foundational behavioral contracts that other specs will reference
- `state-management.md` is the foundational spec with no internal dependencies
- `ready-detection.md` depends on tmux-integration (to be created)
- `worktree-isolation.md` depends on state-management for WorktreeInfo storage
- Cross-references between specs are noted in Dependencies sections
