# Implementation Plan: Consolidate Ralph Under Single Subcommand

**Created**: 2026-02-04
**Status**: Complete
**Goal**: Move all ralph functionality under `swarm ralph <subcommand>` namespace, eliminating the confusing `--ralph` flag from `spawn`

---

## Problem Statement

The current ralph CLI has two entry points creating confusion:
- `swarm spawn --ralph ...` - flag on spawn command
- `swarm ralph <subcommand>` - separate subcommand namespace

This split creates discoverability problems and cognitive overhead. Users/agents may not find `swarm ralph pause` after learning about `swarm spawn --ralph`.

---

## Solution: Option A - Everything Under `ralph` Subcommand

All ralph operations live under `swarm ralph`:
```bash
swarm ralph spawn --name agent --prompt-file ./PROMPT.md --max-iterations 10 -- claude
swarm ralph status agent
swarm ralph pause agent
swarm ralph resume agent
swarm ralph init
swarm ralph template
swarm ralph list
```

---

## Command Mapping

| Current | New |
|---------|-----|
| `swarm spawn --name agent --ralph --prompt-file ./PROMPT.md --max-iterations 10 -- claude` | `swarm ralph spawn --name agent --prompt-file ./PROMPT.md --max-iterations 10 -- claude` |
| `swarm ralph status agent` | (unchanged) |
| `swarm ralph pause agent` | (unchanged) |
| `swarm ralph resume agent` | (unchanged) |
| `swarm ralph init` | (unchanged) |
| `swarm ralph template` | (unchanged) |
| `swarm ralph list` | (unchanged) |
| `swarm ralph run <name>` | (unchanged) |

---

## Tasks

### Phase 1: CLI Refactoring

- [x] **1.1 Add `ralph spawn` subcommand parser** (`swarm.py:997-1031`)
  - Add `ralph_spawn_p = ralph_subparsers.add_parser("spawn", ...)`
  - Copy spawn arguments: `--name`, `--session`, `--tmux-socket`, `--worktree`, `--branch`, `--worktree-dir`, `--tag`, `--env`, `--cwd`, `--ready-wait`, `--ready-timeout`, `-- command...`
  - Make `--prompt-file` required (not conditional)
  - Make `--max-iterations` required (not conditional)
  - Include `--inactivity-timeout` and `--done-pattern`
  - No `--tmux` flag needed (implicit for ralph)
  - No `--ralph` flag needed (redundant under ralph subcommand)

- [x] **1.2 Remove ralph flags from spawn parser** (`swarm.py:901-910`)
  - Remove: `--ralph`, `--prompt-file`, `--max-iterations`, `--inactivity-timeout`, `--done-pattern`

- [x] **1.3 Update cmd_ralph dispatch** (`swarm.py:2062-2087`)
  - Add case for `args.ralph_command == "spawn"` → `cmd_ralph_spawn(args)`

### Phase 2: Implementation Refactoring

- [x] **2.1 Create `cmd_ralph_spawn()` function**
  - Extract ralph-specific spawn logic from `cmd_spawn()`
  - Combine with existing spawn infrastructure
  - Auto-enable tmux mode (no flag needed)
  - Validate `--prompt-file` and `--max-iterations` as required args
  - Create RalphState and send initial prompt

- [x] **2.2 Simplify `cmd_spawn()`** (`swarm.py:1066-1253`)
  - Remove ralph mode validation block (lines 1078-1101)
  - Remove ralph metadata creation (lines 1187-1193)
  - Remove ralph state creation (lines 1213-1238)
  - Remove ralph success message formatting (lines 1249-1250)

### Phase 3: Test Updates

- [x] **3.1 Update `test_cmd_ralph.py`**
  - Update `TestRalphSpawnArguments` - test `ralph spawn` subcommand
  - Update `TestRalphSpawnValidation` - new validation paths
  - Update `TestRalphIntegration` - CLI integration tests
  - Add tests for new `ralph spawn` parser
  - Remove tests for `spawn --ralph` flag

- [x] **3.2 Update `tests/test_integration_ralph.py`**
  - Change all `['spawn', '--name', ..., '--ralph', ...]` to `['ralph', 'spawn', '--name', ...]`

- [x] **3.3 Update `tests/test_tmux_isolation.py`**
  - Update `run_swarm` helper to inject `--tmux-socket` for `ralph spawn` commands

### Phase 4: Documentation Updates

- [x] **4.1 Update `specs/ralph-loop.md`**
  - Change all command examples
  - Update CLI Arguments section
  - Update Scenarios section

- [x] **4.2 Update `specs/cli-interface.md`**
  - Add `ralph spawn` to command summary
  - Update ralph subcommands documentation
  - (Note: CLAUDE.md already had correct syntax)

- [x] **4.3 Update `CLAUDE.md`**
  - Change ralph mode examples in "Ralph Mode (Autonomous Looping)" section
  - (Already had correct `swarm ralph spawn` syntax)

### Phase 5: Verification

- [x] **5.1 Run unit tests**
  ```bash
  python3 -m unittest test_cmd_ralph -v
  # Result: 199 tests passed
  ```

- [x] **5.2 Run integration tests**
  ```bash
  timeout 120 python3 -m unittest tests.test_integration_ralph -v
  # Result: 15 tests passed
  ```

- [x] **5.3 Manual CLI verification**
  ```bash
  # Verify old command fails
  swarm spawn --name test --ralph --prompt-file PROMPT.md --max-iterations 5 -- echo hi
  # Result: error: unrecognized arguments: --ralph

  # Verify new command works
  swarm ralph spawn --name test --prompt-file PROMPT.md --max-iterations 5 -- echo hi
  # Result: spawned test (tmux: swarm-xxx:test) [ralph mode: iteration 1/5]

  # Verify help shows new structure
  swarm ralph --help
  swarm ralph spawn --help
  ```

---

## Files Modified

| File | Changes |
|------|---------|
| `swarm.py` | CLI parser restructure, new `cmd_ralph_spawn()`, simplified `cmd_spawn()` |
| `test_cmd_ralph.py` | Updated all tests using `spawn --ralph` to use `ralph spawn` |
| `tests/test_integration_ralph.py` | Updated all tests using `spawn --ralph` to use `ralph spawn` |
| `tests/test_tmux_isolation.py` | Updated `run_swarm` helper for `ralph spawn` socket injection |
| `specs/ralph-loop.md` | Updated all command examples |

---

## Design Decisions

1. **No deprecation period** - Remove `--ralph` flag immediately
2. **All spawn flags supported** - `--worktree`, `--tag`, `--env`, `--ready-wait`, etc.
3. **`--tmux` implicit** - Ralph requires tmux, no need for explicit flag
4. **`--prompt-file` required** - No longer conditional
5. **`--max-iterations` required** - No longer conditional
6. **Internal function names preserved** - Names like `spawn_worker_for_ralph` are still accurate

---

## Rollback Plan

If issues discovered:
1. Git revert the commit
2. All previous functionality restored via `--ralph` flag
