# Swarm Spec Generation Plan

## Status: ALL SPECS COMPLETE

This document tracks the progress of generating behavioral specifications for the Swarm project.

## Completed Work

### 2026-02-01: Supporting Specs Completed - ALL SPECS DONE

Generated all three Supporting specification files:

1. **`data-structures.md`** - Complete
   - Worker, TmuxInfo, WorktreeInfo dataclass schemas
   - JSON serialization/deserialization behavior
   - Field constraints and defaults
   - to_dict() and from_dict() methods
   - 7 scenarios covering serialization edge cases

2. **`environment.md`** - Complete
   - Python 3.10+ requirements and standard library modules
   - tmux command requirements and features used
   - git worktree command requirements
   - Unix fcntl locking requirements
   - Directory structure (~/.swarm/)
   - Installation script behavior
   - 7 scenarios covering platform and installation cases

3. **`cli-interface.md`** - Complete
   - All 13 subcommands documented
   - Exit code semantics (0/1/2) per command
   - Error message format
   - Argument parsing rules and validation
   - Output formats (table, json, names)
   - Filtering options
   - 10 scenarios covering CLI edge cases

**All 16 behavioral specifications are now complete.**

### 2026-02-01: P2 Standard Specs Completed

Generated all remaining P2 (Standard) specification files:

3. **`logs.md`** - Complete
   - View worker output from tmux pane or log files
   - History mode with scrollback buffer
   - Follow mode with 1-second polling
   - Non-tmux workers use `~/.swarm/logs/<name>.stdout.log`
   - 8 scenarios covering tmux, non-tmux, follow, and error cases

4. **`wait.md`** - Complete
   - Block until worker(s) exit
   - Support for single worker or --all
   - Timeout handling with exit code 1
   - 1-second polling interval
   - 9 scenarios covering single, all, timeout, and edge cases

5. **`clean.md`** - Complete
   - Remove stopped workers from state
   - Delete log files and optionally worktrees
   - Dirty worktree protection (--force-dirty override)
   - Tmux session cleanup when no remaining windows
   - Status refresh before filtering in --all mode
   - 11 scenarios covering various cleanup scenarios

6. **`respawn.md`** - Complete
   - Restart dead workers with original configuration
   - Preserves cmd, env, tags, cwd, worktree settings
   - --clean-first option to remove worktree before respawn
   - Kills running workers if still active
   - 10 scenarios covering process, tmux, worktree cases

7. **`interrupt-eof.md`** - Complete
   - Send Ctrl-C (interrupt) to tmux workers
   - Send Ctrl-D (eof) to tmux workers
   - --all flag for interrupt (broadcast)
   - Status validation before sending
   - 10 scenarios covering both commands

8. **`attach.md`** - Complete
   - Interactive tmux attachment via execvp
   - Window selection before attach
   - Socket handling for isolated sessions
   - 6 scenarios covering attach behavior

9. **`init.md`** - Complete
   - Initialize project with swarm instructions
   - Auto-discovery of AGENTS.md or CLAUDE.md
   - Idempotent marker detection
   - --force to replace existing section
   - --dry-run preview
   - 13 scenarios covering file discovery and edge cases

### 2026-02-01: P2 Standard Specs Continued

Generated the second P2 (Standard) specification file:

2. **`status.md`** - Complete
   - Check single worker status with name lookup
   - Exit code semantics: 0=running, 1=stopped, 2=not found
   - Status line format with tmux/pid details
   - Worktree information inclusion
   - Uptime display with relative time
   - 8 scenarios covering running, stopped, not found, and edge cases

### 2026-02-01: P2 Standard Specs Started

Generated the first P2 (Standard) specification file:

1. **`ls.md`** - Complete
   - List workers with filters (status, tags)
   - Output formats: table, json, names
   - Status refresh via tmux/process checks
   - Table column formatting with relative time
   - JSON schema documentation
   - 11 scenarios covering filters and edge cases

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
- `swarm.py` (full file: lines 66-1777)
- `test_worktree_protection.py`
- `test_ready_patterns.py`
- `test_ready_wait_integration.py`
- `test_state_file_locking.py`
- `test_cmd_spawn.py`
- `test_cmd_send.py`
- `test_cmd_clean.py`
- `test_cmd_respawn.py`
- `test_cmd_init.py`
- `test_respawn_config.py`
- `test_kill_cmd.py`
- `test_kill_integration.py`
- `tests/test_tmux_isolation.py`
- `test_status_integration.py`

## Remaining Work

### P2 - Standard (Complete)
- [x] `ls.md` - List workers with filters
- [x] `status.md` - Check worker status
- [x] `logs.md` - View worker output
- [x] `wait.md` - Block until worker exits
- [x] `clean.md` - Remove stopped workers
- [x] `respawn.md` - Restart dead workers
- [x] `interrupt-eof.md` - Send Ctrl-C/Ctrl-D
- [x] `attach.md` - Interactive tmux attachment
- [x] `init.md` - Inject swarm docs into projects

### Supporting (Complete)
- [x] `data-structures.md` - Worker, TmuxInfo, WorktreeInfo schemas
- [x] `environment.md` - Python 3.10+, tmux, git requirements
- [x] `cli-interface.md` - Argument parsing, exit codes

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

### P2 Specs Validation

All P2 specs have been validated against the checklist:

| Spec | Overview | Inputs | Outputs | Errors | Scenarios | Recovery | Dependencies |
|------|----------|--------|---------|--------|-----------|----------|--------------|
| ls.md | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| status.md | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| logs.md | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| wait.md | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| clean.md | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| respawn.md | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| interrupt-eof.md | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| attach.md | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| init.md | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |

### Supporting Specs Validation

All Supporting specs have been validated against the checklist:

| Spec | Overview | Inputs | Outputs | Errors | Scenarios | Recovery | Dependencies |
|------|----------|--------|---------|--------|-----------|----------|--------------|
| data-structures.md | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| environment.md | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| cli-interface.md | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |

## Notes

- P0 and P1 specs form the core behavioral contracts covering lifecycle operations
- `state-management.md` is the foundational spec with no internal dependencies
- `tmux-integration.md` is referenced by spawn, kill, send, and ready-detection
- `worktree-isolation.md` depends on state-management for WorktreeInfo storage
- `spawn.md` is the most heavily cross-referenced spec (creates workers using all other P0/P1 features)
- Cross-references between specs are noted in Dependencies sections
