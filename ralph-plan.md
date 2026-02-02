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
| `--inactivity-timeout` argument | Complete | Timeout in seconds (default: 300) |
| `--done-pattern` argument | Complete | Regex pattern to stop loop |
| Auto-enable `--tmux` | Complete | Ralph requires tmux mode |
| Validation | Complete | Require prompt-file and max-iterations with --ralph |
| Create ralph state on spawn | Complete | Creates `~/.swarm/ralph/<name>/state.json` with initial values |
| Ralph mode success message | Complete | Shows iteration count in spawn output |

#### Implementation Details

- **Location**: `swarm.py` lines 837-846 (argparser), 999-1022 (validation), 1127-1137 (state creation)
- **Tests**: `test_cmd_ralph.py` with 92 comprehensive tests (8 new tests for spawn state creation)
- **Coverage**: All ralph-specific executable code is tested

### Phase 3: Outer Loop Execution (COMPLETE)

The main ralph loop that manages agent lifecycle.

| Feature | Status | Description |
|---------|--------|-------------|
| `swarm ralph run <name>` | Complete | Command to run the ralph loop for a worker |
| Loop initialization | Complete | Create ralph state file, set iteration to 0 |
| Iteration management | Complete | Increment counter, read prompt, spawn agent |
| Inactivity detection | Complete | Detect when agent becomes stuck (output-based) |
| Agent restart | Complete | Kill current worker, spawn fresh agent |
| Done pattern matching | Complete | Stop loop when pattern matched in output |
| Max iterations check | Complete | Stop loop when limit reached |
| Prompt file re-reading | Complete | Fresh read every iteration (allows editing mid-loop) |

#### Implementation Details

- **Location**: `swarm.py` lines 2213-2444 (helper functions), 2445-2689 (cmd_ralph_run)
- **Tests**: `test_cmd_ralph.py` with 22 new tests for Phase 3 (total: 133 tests)
- **Helper functions**:
  - `wait_for_worker_exit()`: Monitor worker for exit or timeout
  - `detect_inactivity()`: Output-based inactivity detection
  - `check_done_pattern()`: Regex pattern matching on output
  - `format_duration()`: Human-readable duration formatting
  - `kill_worker_for_ralph()`: Kill worker without removing from state
  - `spawn_worker_for_ralph()`: Spawn fresh worker for iteration
  - `send_prompt_to_worker()`: Send prompt content to agent

### Phase 4: Ralph State Management (COMPLETE)

Persist ralph loop state between iterations.

| Feature | Status | Description |
|---------|--------|-------------|
| State file creation | Complete | `~/.swarm/ralph/<worker-name>/state.json` |
| State schema | Complete | JSON schema per spec (RalphState dataclass) |
| Iteration logging | Complete | `~/.swarm/ralph/<worker-name>/iterations.log` with START/END/FAIL/TIMEOUT/DONE events |
| Worker metadata | Complete | Add `metadata` field with `ralph: true` and `ralph_iteration` to Worker record |

#### Implementation Details

- **RalphState dataclass**: Complete implementation matching spec schema
- **Persistence functions**: `load_ralph_state()`, `save_ralph_state()`, `get_ralph_state_path()`
- **RALPH_DIR constant**: `~/.swarm/ralph/` directory for all ralph state
- **Iteration logging**: `get_ralph_iterations_log_path()`, `log_ralph_iteration()` for all event types
- **Worker metadata**: `metadata` dict field added to Worker dataclass with `ralph` and `ralph_iteration` keys

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

### Phase 6: Failure Handling (COMPLETE)

| Feature | Status | Description |
|---------|--------|-------------|
| Consecutive failure tracking | Complete | Track non-zero exit codes in ralph state |
| Exponential backoff | Complete | Wait before retry using `min(2^(n-1), 300)` seconds |
| Stop after 5 failures | Complete | Exit loop with code 1 after 5 consecutive failures |
| Backoff formula | Complete | `min(2^(n-1), 300)` seconds implemented |

#### Implementation Details

- **Location**: Integrated into `cmd_ralph_run()` in `swarm.py`
- **Failure tracking**: Uses `consecutive_failures` and `total_failures` in RalphState
- **Backoff calculation**: `backoff = min(2 ** (consecutive_failures - 1), 300)`
- **Reset on success**: Consecutive failures reset to 0 when iteration succeeds

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
| TestRalphSpawnNewArguments | 3 | Passing |
| TestRalphStateCreation | 5 | Passing |
| TestRalphStateDataclass | 4 | Passing |
| TestRalphStatePersistence | 4 | Passing |
| TestCmdRalphStatus | 3 | Passing |
| TestCmdRalphPause | 4 | Passing |
| TestCmdRalphResume | 4 | Passing |
| TestRalphSubcommandsCLI | 6 | Passing |
| TestRalphScenariosPauseResume | 4 | Passing |
| TestRalphIterationLogging | 10 | Passing |
| TestWorkerMetadata | 5 | Passing |
| TestRalphSpawnMetadata | 5 | Passing |
| TestRalphRunSubparser | 2 | Passing |
| TestRalphHelperFunctions | 4 | Passing |
| TestCmdRalphRun | 8 | Passing |
| TestRalphRunDispatch | 1 | Passing |
| TestCheckDonePattern | 2 | Passing |
| TestDetectInactivity | 1 | Passing |
| TestKillWorkerForRalph | 2 | Passing |
| TestSpawnWorkerForRalph | 1 | Passing |
| TestSendPromptToWorker | 2 | Passing |
| TestRalphRunMainLoop | 6 | Passing |
| TestWaitForWorkerExit | 1 | Passing |
| TestRalphRunEdgeCases | 4 | Passing |
| **Total** | **144** | **All Passing** |

**Coverage**: Ralph-specific code coverage is **95.4%** (725/760 lines covered)

## Next Steps

All phases are now COMPLETE. The ralph loop feature is fully implemented.

Possible future enhancements:
- Add `--inactivity-mode` flag to select detection method (output|ready|both)
- Add integration tests with real tmux sessions
- Add `swarm ralph list` to show all ralph workers
- Add graceful shutdown on SIGTERM

## Recent Changes

### 2026-02-02: Improved Test Coverage

- Added `TestRalphRunEdgeCases` class with 4 new tests for edge cases:
  - `test_run_ralph_state_deleted_during_loop`: Handles ralph state deletion during loop
  - `test_run_paused_during_inner_loop`: Handles pause during inner monitoring loop
  - `test_run_prompt_file_read_error`: Handles permission errors reading prompt file
  - `test_run_spawn_failure_with_backoff_logging`: Tests full backoff path with logging
- Ralph-specific code coverage now at 95.4%
- Total: 144 tests, all passing

### 2026-02-02: Completed Phase 3 - Outer Loop Execution

- Added `swarm ralph run <name>` command to run the ralph loop
- Added helper functions for loop execution:
  - `wait_for_worker_exit()`: Monitor worker for exit or timeout
  - `detect_inactivity()`: Output-based inactivity detection
  - `check_done_pattern()`: Regex pattern matching on output
  - `format_duration()`: Human-readable duration formatting
  - `kill_worker_for_ralph()`: Kill worker without removing from state
  - `spawn_worker_for_ralph()`: Spawn fresh worker for iteration
  - `send_prompt_to_worker()`: Send prompt content to agent
- Added `cmd_ralph_run()` with main loop logic:
  - Iteration management with prompt file re-reading
  - Worker monitoring and restart
  - Done pattern detection
  - Max iterations check
  - Pause detection during loop
- Added 22 new tests for Phase 3 functionality (total: 133 tests)
- Phase 6 (Failure Handling) integrated into `cmd_ralph_run()`

### 2026-02-02: Completed Phase 4 - Ralph State Management

- Added `log_ralph_iteration()` function for logging iteration events (START, END, FAIL, TIMEOUT, DONE)
- Added `get_ralph_iterations_log_path()` function for getting iterations log file path
- Added `metadata` field to Worker dataclass for extensible metadata
- Worker metadata now includes `ralph: true` and `ralph_iteration` for ralph workers
- Ralph state now starts at iteration 1 (more intuitive for users)
- Spawn now logs iteration START event to iterations.log
- Added 19 new tests for iteration logging and worker metadata (total: 111 tests)

### 2026-02-02: Completed Spawn Integration

- Added `--inactivity-timeout` argument (default: 300 seconds)
- Added `--done-pattern` argument for regex pattern matching
- Added ralph state creation when spawning with `--ralph` flag
- Added ralph mode indication in spawn success message
- Added 8 new tests for spawn state creation (total: 92 tests)
