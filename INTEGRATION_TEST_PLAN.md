# Ralph Loop Integration Test Plan

## Priority Integration Tests

### 1. Test `spawn --ralph` sends prompt to worker (HIGHEST PRIORITY) - IMPLEMENTED
**Contract**: When `cmd_spawn` is called with `--ralph`, it must:
- Create worker state
- Create ralph state with iteration=1
- Send the prompt content to the worker via tmux

**Why this matters**: This is the entry point for the ralph loop. If spawn doesn't
send the initial prompt, the worker will never start working - it will just sit
there with no input.

**Tests added (TestRalphSpawnSendsPromptIntegration)**:
- `test_spawn_ralph_sends_prompt_to_worker`: Verifies tmux_send receives prompt content
- `test_spawn_ralph_reads_prompt_file_content`: Verifies file content is read, not path

### 2. Test `ralph run` monitoring loop calls `detect_inactivity` correctly
**Contract**: The `_run_ralph_loop` function must:
- Call `detect_inactivity` with correct worker, timeout, and mode
- Respect the blocking behavior (wait for inactivity or worker exit)
- React appropriately when inactivity is detected

**Why this matters**: If detect_inactivity is called with wrong parameters or
the loop doesn't properly wait for its result, the ralph loop will either
restart workers prematurely or hang forever.

**Existing tests (TestRalphRunIntegration)**:
- `test_ralph_run_calls_detect_inactivity_with_correct_params`: Verifies correct params

### 3. Test state flows: spawn creates iteration=1, worker exit triggers iteration=2
**Contract**:
- spawn with --ralph creates ralph state with current_iteration=1
- After worker exits and restarts, iteration increments to 2
- Iteration count is stored in both ralph state AND worker metadata

**Why this matters**: Incorrect iteration tracking breaks the max_iterations
limit and ralph status display.

**Existing tests (TestRalphRunIntegration)**:
- `test_ralph_run_increments_iteration_on_worker_exit`: Verifies iteration increment

### 4. Test `detect_inactivity` blocking behavior matches caller expectations
**Contract**:
- Returns True when inactivity timeout reached (blocks until then)
- Returns False when worker exits (unblocks early)
- Does not return until one of these conditions

**Why this matters**: If detect_inactivity returns early or doesn't block,
the ralph loop will spin rapidly or never restart workers.

**Status**: Covered by existing unit tests in TestDetectInactivity

## Implementation Progress

- [x] Plan created
- [x] Test 1: spawn --ralph sends prompt to worker (TestRalphSpawnSendsPromptIntegration)
- [x] Test 2: ralph run monitoring loop (TestRalphRunIntegration - existing)
- [x] Test 3: state flows across iterations (TestRalphRunIntegration - existing)
- [x] Test 4: detect_inactivity blocking (TestDetectInactivity - existing unit tests)

## Test Execution

Run the integration tests specifically:
```bash
python3 -m unittest test_cmd_ralph.TestRalphSpawnSendsPromptIntegration test_cmd_ralph.TestRalphRunIntegration -v
```

Note: Running `make test` in this repo will timeout because the test suite
spawns child workers that clobber ~/.swarm/state.json. Run specific test
files or classes instead.

## Notes

The existing tests use heavy mocking which is appropriate for unit testing,
but can hide integration bugs where components work in isolation but fail
together. The new tests in TestRalphSpawnSendsPromptIntegration use minimal
mocking (only at the tmux boundary) to verify the full integration flow.
