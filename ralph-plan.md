# Ralph Loop Implementation Plan

This document tracks the implementation progress of the Ralph Loop feature (autonomous agent looping) for swarm.

## Specification

See `specs/ralph-loop.md` for the full behavioral specification.

## Implementation Status

### Phase 1: Prompt Template Generation (COMPLETE)

The most fundamental feature enabling the Ralph Wiggum workflow - creating and managing prompt files.

| Feature | Status | Description |
|---------|--------|-------------|
| `RALPH_PROMPT_TEMPLATE` constant | Complete | Minimal, direct template following Ralph Wiggum methodology |
| `swarm ralph init` | Complete | Create PROMPT.md with starter template |
| `swarm ralph init --force` | Complete | Overwrite existing PROMPT.md |
| `swarm ralph template` | Complete | Output template to stdout for customization |

#### Implementation Details

- **Location**: `swarm.py` lines 67-78 (template constant), 1803-1854 (ralph functions)
- **Tests**: `test_cmd_ralph.py` with 32 comprehensive tests
- **Coverage**: All ralph functions are fully tested

#### Template Design

The template follows the Ralph Wiggum methodology principles:
- Minimal: Less prompt = more context for actual work
- Direct: Imperative instructions, no fluff
- Project-agnostic: References common conventions (specs/, CLAUDE.md)
- Customizable: User should edit for their project

### Phase 2: Spawn Integration (COMPLETE)

Add `--ralph` flag to spawn command with required dependencies.

| Feature | Status | Description |
|---------|--------|-------------|
| `--ralph` flag on spawn | Complete | Enable ralph loop mode |
| `--prompt-file` argument | Complete | Path to prompt file (required with --ralph) |
| `--max-iterations` argument | Complete | Maximum loop iterations (required with --ralph) |
| `--inactivity-timeout` argument | Not Started | Timeout in seconds (default: 300) |
| `--done-pattern` argument | Not Started | Regex pattern to stop loop |
| Auto-enable `--tmux` | Complete | Ralph requires tmux mode |
| Validation | Complete | Require prompt-file and max-iterations with --ralph |

#### Implementation Details

- **Location**: `swarm.py` lines 751-757 (argparser), 901-924 (validation)
- **Tests**: `test_cmd_ralph.py` with 52 comprehensive tests (20 new tests for Phase 2)
- **Coverage**: 100% for ralph-specific executable code

### Phase 3: Outer Loop Execution (NOT STARTED)

The main ralph loop that manages agent lifecycle.

| Feature | Status | Description |
|---------|--------|-------------|
| Loop initialization | Not Started | Create ralph state file, set iteration to 0 |
| Iteration management | Not Started | Increment counter, read prompt, spawn agent |
| Inactivity detection | Not Started | Detect when agent becomes stuck |
| Agent restart | Not Started | Kill current worker, spawn fresh agent |
| Done pattern matching | Not Started | Stop loop when pattern matched |
| Max iterations check | Not Started | Stop loop when limit reached |

### Phase 4: Ralph State Management (COMPLETE)

Persist ralph loop state between iterations.

| Feature | Status | Description |
|---------|--------|-------------|
| State file creation | Complete | `~/.swarm/ralph/<worker-name>/state.json` |
| State schema | Complete | JSON schema per spec (RalphState dataclass) |
| Iteration logging | Not Started | `~/.swarm/ralph/<worker-name>/iterations.log` |
| Worker metadata | Not Started | Add ralph_iteration to worker record |

#### Implementation Details

- **RalphState dataclass**: Complete implementation matching spec schema
- **Persistence functions**: `load_ralph_state()`, `save_ralph_state()`, `get_ralph_state_path()`
- **RALPH_DIR constant**: `~/.swarm/ralph/` directory for all ralph state

### Phase 5: Pause and Resume (COMPLETE)

| Feature | Status | Description |
|---------|--------|-------------|
| `swarm ralph pause <name>` | Complete | Pause the loop |
| `swarm ralph resume <name>` | Complete | Resume the loop |
| `swarm ralph status <name>` | Complete | Show ralph loop status |

#### Implementation Details

- **Location**: `swarm.py` lines 147-228 (RalphState class and helpers), lines 1933-2111 (ralph command functions)
- **Tests**: `test_cmd_ralph.py` with 84 comprehensive tests
- **Coverage**: All ralph functions are fully tested

#### Features

- **RalphState dataclass**: Stores ralph loop state with all required fields from spec
- **State persistence**: `~/.swarm/ralph/<worker-name>/state.json`
- **ralph status**: Shows iteration count, status, failure counts, and configuration
- **ralph pause**: Sets status to "paused", warns if already paused
- **ralph resume**: Sets status to "running", warns if not paused

### Phase 6: Failure Handling (NOT STARTED)

| Feature | Status | Description |
|---------|--------|-------------|
| Consecutive failure tracking | Not Started | Track non-zero exit codes |
| Exponential backoff | Not Started | Wait before retry |
| Stop after 5 failures | Not Started | Exit loop with code 1 |
| Backoff formula | Not Started | `min(2^(n-1), 300)` seconds |

## Testing

Test file: `test_cmd_ralph.py`

| Test Class | Tests | Status |
|------------|-------|--------|
| TestRalphSubparser | 5 | Passing |
| TestRalphPromptTemplate | 6 | Passing |
| TestCmdRalphInit | 9 | Passing |
| TestCmdRalphTemplate | 3 | Passing |
| TestCmdRalphDispatch | 5 | Passing |
| TestRalphIntegration | 4 | Passing |
| TestRalphScenarios | 4 | Passing |
| TestRalphSpawnArguments | 3 | Passing |
| TestRalphSpawnValidation | 7 | Passing |
| TestRalphSpawnScenarios | 5 | Passing |
| TestRalphSpawnEdgeCases | 5 | Passing |
| TestRalphStateDataclass | 4 | Passing |
| TestRalphStatePersistence | 4 | Passing |
| TestCmdRalphStatus | 3 | Passing |
| TestCmdRalphPause | 4 | Passing |
| TestCmdRalphResume | 4 | Passing |
| TestRalphSubcommandsCLI | 6 | Passing |
| TestRalphScenariosPauseResume | 4 | Passing |
| **Total** | **84** | **All Passing** |

## Next Steps

1. ~~Phase 2: Add `--ralph` flag to spawn with validation~~ (COMPLETE)
2. Phase 3: Implement outer loop execution
3. ~~Phase 4: Add ralph state management~~ (COMPLETE - RalphState dataclass and persistence)
4. ~~Phase 5: Implement pause/resume commands~~ (COMPLETE)
5. Phase 6: Add failure handling with backoff
