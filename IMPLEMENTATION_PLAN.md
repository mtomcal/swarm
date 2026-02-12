# Implementation Plan: Round 4 — Spec Compliance Gaps

**Created**: 2026-02-12
**Status**: PENDING
**Goal**: Close the remaining gaps between specs and implementation — `swarm peek` command, environment propagation for tmux workers, transactional rollback in `cmd_spawn()`, and corrupt state warning for `State._load()`.

---

## Context

A full spec-vs-implementation audit revealed 3 missing features and 1 incomplete behavior. The specs already define the required behavior; this plan covers the code changes and tests.

### Gap Summary

| # | Gap | Spec | Severity |
|---|-----|------|----------|
| 1 | `swarm peek` command entirely missing | `specs/peek.md` | P1 |
| 2 | `--env` not propagated to tmux workers | `specs/spawn.md` (Environment Propagation Chain) | P1 |
| 3 | `cmd_spawn()` lacks transactional rollback | `specs/spawn.md` (Transactional Spawn) | P1 |
| 4 | `State._load()` missing corrupt JSON recovery | `specs/state-management.md` | P2 |

---

## Tasks

### Phase 1: `swarm peek` Command

- [ ] **1.1 Add `peek` subparser to `main()`**
  - Add `peek_p = subparsers.add_parser("peek", ...)` after the existing `status` parser (~line 3601)
  - Arguments:
    - `name` (positional, nargs="?") — worker name
    - `-n/--lines` (int, default=30) — lines to capture
    - `--all` (flag) — peek all running workers
  - Validation: one of `name` or `--all` required
  - File: `swarm.py` (in `main()`)

- [ ] **1.2 Implement `cmd_peek(args)`**
  - Single-worker path:
    1. Load state, look up worker by name
    2. If not found → exit 2: `"swarm: error: worker '<name>' not found"`
    3. If no tmux info → exit 1: `"swarm: error: worker '<name>' is not a tmux worker"`
    4. Check tmux window alive via `tmux_window_exists()` → exit 1: `"swarm: error: worker '<name>' is not running"`
    5. Call `tmux_capture_pane(session, window, history_lines=args.lines, socket=socket)`
    6. Print result to stdout, exit 0
  - `--all` path:
    1. Load all workers, filter to running tmux workers
    2. For each, print `=== worker-name ===` header then captured content
    3. If no running tmux workers, print nothing, exit 0
  - Error on capture failure → exit 1: `"swarm: error: failed to capture pane for '<name>': <error>"`
  - File: `swarm.py` (new function near other `cmd_*` functions)

- [ ] **1.3 Add unit tests for `cmd_peek`**
  - Test: basic peek returns captured content
  - Test: `--all` shows headers for multiple workers
  - Test: `--all` with `-n` applies per worker
  - Test: non-existent worker → exit 2
  - Test: non-tmux worker → exit 1
  - Test: stopped tmux worker → exit 1
  - Test: capture failure → exit 1
  - Test: empty pane → exit 0, empty output
  - Test: `--all` with no running workers → exit 0
  - File: `test_cmd_peek.py` (new file)

### Phase 2: Environment Propagation for Tmux Workers

- [ ] **2.1 Update `create_tmux_window()` to accept env dict**
  - Add `env: Optional[dict[str, str]] = None` parameter
  - When env is non-empty, wrap `cmd_str` with `env KEY1=VAL1 KEY2=VAL2 <cmd_str>`
  - Use `shlex.quote()` on both keys and values for safety
  - File: `swarm.py` (~line 3153, `create_tmux_window()`)

- [ ] **2.2 Thread env through callers of `create_tmux_window()`**
  - `cmd_spawn()` (~line 4190): pass `env_dict` to `create_tmux_window()`
  - `cmd_ralph_spawn()` / `_do_ralph_spawn()`: pass env if available
  - `cmd_respawn()`: pass worker's stored env if applicable
  - File: `swarm.py`

- [ ] **2.3 Add unit tests for env propagation**
  - Test: `create_tmux_window()` with env wraps command correctly
  - Test: `create_tmux_window()` with empty/None env leaves command unchanged
  - Test: values containing spaces/special chars are properly quoted
  - File: `test_cmd_spawn.py` (extend existing)

### Phase 3: Transactional Rollback in `cmd_spawn()`

- [ ] **3.1 Wrap spawn steps in try/except with rollback**
  - Refactor `cmd_spawn()` (~line 4105) to track created resources:
    - `created_worktree: Optional[Path] = None` — set after worktree creation
    - `created_tmux: Optional[TmuxInfo] = None` — set after tmux window creation
    - `spawned_pid: Optional[int] = None` — set after process spawn
  - Wrap tmux/process creation and state add in try/except
  - On failure, call `_rollback_spawn(created_worktree, created_tmux, spawned_pid)`
  - File: `swarm.py` (`cmd_spawn()`)

- [ ] **3.2 Implement `_rollback_spawn()` helper**
  - Reverse-order cleanup:
    1. Kill tmux window if created (via `tmux kill-window`)
    2. Kill process if spawned (via `os.kill(pid, signal.SIGTERM)`)
    3. Remove worktree if created (via `git worktree remove --force`)
  - Print `"swarm: warning: spawn failed, cleaning up partial state"` before cleanup
  - Each cleanup step is best-effort (catch exceptions, warn on failure)
  - File: `swarm.py` (new helper near `cmd_spawn()`)

- [ ] **3.3 Add unit tests for transactional rollback**
  - Test: tmux failure after worktree → worktree removed, error printed
  - Test: process failure after worktree → worktree removed, error printed
  - Test: state update failure → worker killed + worktree removed
  - Test: rollback failure itself prints warning but still reports original error
  - Test: successful spawn does not trigger rollback
  - File: `test_cmd_spawn.py` (extend existing)

### Phase 4: Corrupt State Recovery in `State._load()`

- [ ] **4.1 Add JSONDecodeError handling to `State._load()`**
  - Wrap `json.load(f)` at line 2774 in try/except JSONDecodeError
  - On error:
    1. Print `"swarm: warning: corrupt state file, resetting"` to stderr
    2. Back up file to `~/.swarm/state.json.corrupted` (same pattern as ralph state)
    3. Set `self.workers = []`
  - File: `swarm.py` (~line 2764, `State._load()`)

- [ ] **4.2 Add unit tests for corrupt state recovery**
  - Test: corrupt JSON → workers is empty + warning printed + backup created
  - Test: empty file → workers is empty + warning printed
  - Test: valid JSON → works normally (no warning)
  - File: `test_state_file_locking.py` (extend existing)

### Phase 5: Verify

- [ ] **5.1 Run new unit tests**
  - `python3 -m unittest test_cmd_peek -v`
  - `python3 -m unittest test_cmd_spawn -v`
  - `python3 -m unittest test_state_file_locking -v`

- [ ] **5.2 Verify CLI**
  - `python3 swarm.py peek --help` → shows name, -n, --all
  - `python3 swarm.py spawn --help` → unchanged
  - `python3 swarm.py ralph spawn --help` → unchanged

- [ ] **5.3 Run full test suite**
  - `python3 -m unittest discover -s . -p 'test_*.py' -v`
  - Note: may crash swarm workers per CLAUDE.md caveat — run in isolation

---

## Files Modified

| File | Change |
|------|--------|
| `swarm.py` | New `cmd_peek()`, env propagation in `create_tmux_window()`, transactional rollback in `cmd_spawn()`, corrupt state recovery in `State._load()` |
| `test_cmd_peek.py` | New file — peek command unit tests |
| `test_cmd_spawn.py` | Extended — env propagation + rollback tests |
| `test_state_file_locking.py` | Extended — corrupt state recovery tests |

---

## Spec References

- `specs/peek.md` — Full peek command spec (P1)
- `specs/spawn.md` — Transactional Spawn + Environment Propagation Chain sections
- `specs/state-management.md` — Corrupt State Recovery section

---

## Complexity Notes

- **Phase 1 (peek)**: Low — CLI wiring + thin wrapper around existing `tmux_capture_pane()`, ~1 hour
- **Phase 2 (env propagation)**: Low — `env` prefix wrapper in `create_tmux_window()`, ~30 min
- **Phase 3 (transactional rollback)**: Medium — try/except refactor of `cmd_spawn()` with reverse-order cleanup, ~1 hour
- **Phase 4 (corrupt state)**: Trivial — add try/except to `State._load()`, ~15 min
- **Phase 5 (verify)**: Trivial — run tests, ~15 min

**Total estimated: ~3 hours of worker time, ~4-6 iterations**
