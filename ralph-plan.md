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

### Phase 2: Spawn Integration (NOT STARTED)

Add `--ralph` flag to spawn command with required dependencies.

| Feature | Status | Description |
|---------|--------|-------------|
| `--ralph` flag on spawn | Not Started | Enable ralph loop mode |
| `--prompt-file` argument | Not Started | Path to prompt file (required with --ralph) |
| `--max-iterations` argument | Not Started | Maximum loop iterations (required with --ralph) |
| `--inactivity-timeout` argument | Not Started | Timeout in seconds (default: 300) |
| `--done-pattern` argument | Not Started | Regex pattern to stop loop |
| Auto-enable `--tmux` | Not Started | Ralph requires tmux mode |
| Validation | Not Started | Require prompt-file and max-iterations with --ralph |

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

### Phase 4: Ralph State Management (NOT STARTED)

Persist ralph loop state between iterations.

| Feature | Status | Description |
|---------|--------|-------------|
| State file creation | Not Started | `~/.swarm/ralph/<worker-name>/state.json` |
| State schema | Not Started | JSON schema per spec |
| Iteration logging | Not Started | `~/.swarm/ralph/<worker-name>/iterations.log` |
| Worker metadata | Not Started | Add ralph_iteration to worker record |

### Phase 5: Pause and Resume (NOT STARTED)

| Feature | Status | Description |
|---------|--------|-------------|
| `swarm ralph pause <name>` | Not Started | Pause the loop |
| `swarm ralph resume <name>` | Not Started | Resume the loop |
| `swarm ralph status <name>` | Not Started | Show ralph loop status |

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
| TestCmdRalphInit | 10 | Passing |
| TestCmdRalphTemplate | 3 | Passing |
| TestCmdRalphDispatch | 2 | Passing |
| TestRalphIntegration | 4 | Passing |
| TestRalphScenarios | 4 | Passing |
| **Total** | **32** | **All Passing** |

## Next Steps

1. Phase 2: Add `--ralph` flag to spawn with validation
2. Phase 3: Implement outer loop execution
3. Phase 4: Add ralph state management
4. Phase 5: Implement pause/resume commands
5. Phase 6: Add failure handling with backoff
