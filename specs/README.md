# Swarm Specifications - Meta Spec

This document defines the protocol for generating comprehensive behavioral specifications for the Swarm project. An agent following this protocol will produce specs that enable complete system reconstruction.

---

## Purpose

Capture the **behavioral contract** of Swarm - what it does, not how. An agent reading the generated specs should be able to implement a fully compatible system from scratch.

## Audience

Primary: AI Agents tasked with understanding, maintaining, or rebuilding this system.

---

## Spec Generation Protocol

### Step 1: Source Analysis

Read these files to extract behavioral contracts:

| Source | Purpose |
|--------|---------|
| `swarm.py` | Primary implementation - extract all behaviors |
| `test_*.py` (23 files) | Test cases - convert to Given/When/Then scenarios |
| `README.md` | User-facing documentation |
| `CLAUDE.md` | Agent instructions and caveats |

### Step 2: Generate Spec Files

Create one markdown file per feature in `specs/` using flat naming (`kebab-case.md`).

### Step 3: Update TOC

Update the Table of Contents below, changing status from `Pending` to `Complete`.

---

## Spec File Template

Every spec file MUST follow this structure:

```markdown
# [Feature Name]

## Overview
One paragraph: what this feature does and why it exists.

## Dependencies
- External: (git, tmux, filesystem, etc.)
- Internal: (other specs this depends on)

## Behavior

### [Behavior Name]

**Description**: What this behavior accomplishes.

**Inputs**:
- `param_name` (type, required/optional): Description and constraints

**Outputs**:
- Success: Exact outcome on success
- Failure: Exact outcome on failure

**Side Effects**:
- State changes, file writes, process spawns, etc.

**Error Conditions**:
| Condition | Behavior |
|-----------|----------|
| [condition] | [error message or exit code] |

## Scenarios

### Scenario: [Descriptive Name]
- **Given**: Initial state and preconditions
- **When**: Action taken (command, function call)
- **Then**: Observable outcome

(Include scenarios for: happy path, edge cases, error cases)

## Edge Cases
Bullet list of boundary conditions and unusual inputs with expected behavior.

## Recovery Procedures
How to recover from each failure state. Include commands.

## Implementation Notes (Optional)
Critical implementation details an agent MUST know to maintain compatibility.
```

---

## Priority Tiers

Generate specs in this order:

### P0 - Critical (Generate First)

| Spec File | Description | Source Files | Status |
|-----------|-------------|--------------|--------|
| `worktree-isolation.md` | Git worktree creation, branch isolation, dirty state detection, cleanup | `swarm.py:295-397`, `test_worktree_protection.py` | Complete |
| `ready-detection.md` | Agent CLI readiness patterns, wait behavior, timeout handling | `swarm.py:550-607`, `test_ready_patterns.py`, `test_ready_wait_integration.py` | Complete |
| `state-management.md` | Worker registry, JSON persistence, fcntl locking, atomic operations | `swarm.py:157-277`, `test_state_file_locking.py` | Complete |

### P1 - Important

| Spec File | Description | Source Files | Status |
|-----------|-------------|--------------|--------|
| `spawn.md` | Worker creation in tmux/process modes, worktree integration | `swarm.py:854-978`, `test_cmd_spawn.py` | Complete |
| `kill.md` | Worker termination, worktree cleanup, force options | `swarm.py:1330-1419`, `test_cmd_clean.py` | Complete |
| `send.md` | Sending text input to tmux workers, broadcast | `swarm.py:1107-1159` | Complete |
| `tmux-integration.md` | Session/window management, socket isolation, capture | `swarm.py:403-549`, `tests/test_tmux_isolation.py` | Complete |

### P2 - Standard

| Spec File | Description | Source Files | Status |
|-----------|-------------|--------------|--------|
| `ls.md` | List workers with filters (status, tags, format) | `swarm.py:980-1063` | Pending |
| `status.md` | Check single worker status, exit codes | `swarm.py:1065-1105` | Pending |
| `logs.md` | View worker output, history, follow mode | `swarm.py:1218-1288` | Pending |
| `wait.md` | Block until worker exits, timeout, exit code propagation | `swarm.py:1290-1328` | Pending |
| `clean.md` | Remove stopped workers, log cleanup | `swarm.py:1458-1549`, `test_cmd_clean.py` | Pending |
| `respawn.md` | Restart dead workers with original config | `swarm.py:1551-1685`, `test_cmd_respawn.py` | Pending |
| `interrupt-eof.md` | Send Ctrl-C and Ctrl-D signals | `swarm.py:1161-1216` | Pending |
| `attach.md` | Interactive tmux attachment | `swarm.py` (attach command) | Pending |
| `init.md` | Inject swarm docs into project files | `swarm.py:1687-1773`, `test_cmd_init.py` | Pending |

### Supporting

| Spec File | Description | Source Files | Status |
|-----------|-------------|--------------|--------|
| `data-structures.md` | Worker, TmuxInfo, WorktreeInfo dataclass schemas | `swarm.py:66-129` | Pending |
| `environment.md` | Python 3.10+, tmux, git, fcntl, directory structure | `setup.sh`, `Makefile` | Pending |
| `cli-interface.md` | Argument parsing, exit codes, output formats | `swarm.py:709-851` | Pending |

---

## Environment Requirements

Document in `environment.md`:

| Requirement | Details |
|-------------|---------|
| Python | 3.10+ (dataclasses, type hints) |
| tmux | Required for `--tmux` mode |
| git | Required for `--worktree` mode |
| OS | Unix-like (fcntl file locking) |
| Directories | `~/.swarm/state.json`, `~/.swarm/logs/` |

---

## Extracting Scenarios from Tests

When reading test files, convert test methods to Given/When/Then:

**Example Conversion**:

```python
# From test_worktree_protection.py
def test_kill_refuses_dirty_worktree(self):
    # Setup: create worker with worktree, make uncommitted change
    # Action: swarm kill --rm-worktree
    # Assert: exits non-zero, worktree preserved
```

**Becomes**:

```markdown
### Scenario: Kill refuses to remove dirty worktree
- **Given**: A worker with `--worktree` containing uncommitted changes
- **When**: `swarm kill <name> --rm-worktree` is executed
- **Then**:
  - Exit code is non-zero
  - Error message indicates dirty worktree
  - Worktree directory is preserved
  - Worker is removed from state (but worktree remains)
```

---

## Critical Behaviors to Capture

### Worktree Isolation (P0)
- Worktrees created at `<repo>-worktrees/<worker-name>/`
- Branch name equals worker name
- Dirty detection before removal (uncommitted changes block cleanup)
- `--force-dirty` override behavior

### Ready Detection (P0)
- Pattern list for Claude Code, OpenCode, generic shells
- ANSI escape sequence handling in pattern matching
- 120-second default timeout
- Polling interval (0.5s)
- Return value semantics (true=ready, false=timeout)

### State Management (P0)
- JSON schema for `~/.swarm/state.json`
- fcntl exclusive locking protocol
- Atomic load-modify-save pattern
- Concurrent access behavior

---

## Validation Checklist

A spec is complete when:

- [ ] Overview clearly states purpose
- [ ] All inputs documented with types and constraints
- [ ] All outputs documented (success and failure)
- [ ] All error conditions enumerated with exact messages/codes
- [ ] Given/When/Then scenarios cover:
  - [ ] Happy path
  - [ ] Each error condition
  - [ ] Edge cases
- [ ] Recovery procedures documented
- [ ] Dependencies listed
- [ ] Status updated in this TOC

---

## Agent Instructions

To generate all specs:

```
1. Read this meta-spec completely
2. For each spec in P0, then P1, then P2, then Supporting:
   a. Read the source files listed
   b. Read corresponding test files
   c. Generate spec following the template
   d. Validate against checklist
   e. Update status in TOC to "Complete"
3. Final validation: ensure all specs cross-reference correctly
```
