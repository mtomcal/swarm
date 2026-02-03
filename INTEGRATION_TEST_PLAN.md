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

### 3. Test state flows: spawn creates iteration=1, worker exit triggers iteration=2 - IMPLEMENTED
**Contract**:
- spawn with --ralph creates ralph state with current_iteration=1
- After worker exits and restarts, iteration increments to 2
- Iteration count is stored in both ralph state AND worker metadata

**Why this matters**: Incorrect iteration tracking breaks the max_iterations
limit and ralph status display.

**Tests added (TestRalphStateFlowIntegration)**:
- `test_spawn_creates_iteration_1_then_run_increments_to_2`: End-to-end state flow test
  verifying spawn creates iteration=1, then ralph run advances through iterations 2 and 3
- `test_state_persists_across_load_save_cycles`: Verifies state survives serialization
  round-trips without data loss

**Existing tests (TestRalphRunIntegration)**:
- `test_ralph_run_increments_iteration_on_worker_exit`: Verifies iteration increment

### 4. Test `detect_inactivity` blocking behavior matches caller expectations - IMPLEMENTED
**Contract**:
- Returns True when inactivity timeout reached (blocks until then)
- Returns False when worker exits (unblocks early)
- Does not return until one of these conditions
- Timer resets when output changes

**Why this matters**: If detect_inactivity returns early or doesn't block,
the ralph loop will spin rapidly or never restart workers.

**Tests added (TestDetectInactivityBlockingIntegration)**:
- `test_detect_inactivity_returns_false_when_worker_exits`: Verifies quick return on worker exit
- `test_detect_inactivity_returns_true_after_timeout_output_mode`: Verifies blocking for output mode
- `test_detect_inactivity_returns_true_after_timeout_ready_mode`: Verifies blocking for ready mode
- `test_detect_inactivity_resets_timer_on_output_change`: Verifies timer reset behavior

### 5. Test inactivity triggers full restart cycle - IMPLEMENTED
**Contract**: When `detect_inactivity` returns True (inactivity detected):
1. `kill_worker_for_ralph` must be called to stop the inactive worker
2. Loop must increment iteration and spawn a new worker
3. `send_prompt_to_worker` must be called with prompt content for new worker
4. The full cycle (kill → increment → spawn → send prompt) must complete atomically

**Why this matters**: This is the core ralph loop functionality. A bug anywhere
in this chain means the loop will either:
- Leave zombie workers running (if kill fails)
- Not restart the worker (if spawn path isn't taken after kill)
- Start worker without prompt (if send_prompt is skipped after spawn)

**Test added (TestRalphInactivityRestartIntegration)**:
- `test_inactivity_triggers_kill_then_restart_with_prompt`: Full cycle verification
- `test_inactivity_restart_increments_iteration_before_spawn`: Verifies ordering

## Implementation Progress

- [x] Plan created
- [x] Test 1: spawn --ralph sends prompt to worker (TestRalphSpawnSendsPromptIntegration)
- [x] Test 2: ralph run monitoring loop (TestRalphRunIntegration - existing)
- [x] Test 3: state flows across iterations (TestRalphStateFlowIntegration - NEW)
- [x] Test 4: detect_inactivity blocking (TestDetectInactivityBlockingIntegration)
- [x] Test 5: inactivity triggers full restart cycle (TestRalphInactivityRestartIntegration)

## Test Execution

Run all ralph integration tests:
```bash
python3 -m unittest test_cmd_ralph.TestRalphSpawnSendsPromptIntegration test_cmd_ralph.TestRalphRunIntegration test_cmd_ralph.TestRalphInactivityRestartIntegration test_cmd_ralph.TestDetectInactivityBlockingIntegration test_cmd_ralph.TestRalphStateFlowIntegration -v
```

Run with timeout to catch hangs:
```bash
timeout 60 python3 -m unittest test_cmd_ralph.TestRalphStateFlowIntegration -v
```

Note: Running `make test` in this repo may cause issues because the test suite
spawns child workers that can clobber ~/.swarm/state.json. Run specific test
files or classes for safer testing.

## Notes

The existing tests use heavy mocking which is appropriate for unit testing,
but can hide integration bugs where components work in isolation but fail
together. The new tests use minimal mocking (only at the tmux boundary) to
verify the full integration flow.

### Most Important New Test: TestRalphStateFlowIntegration

The `TestRalphStateFlowIntegration` class was added as the highest priority
integration test because it catches bugs where:
- State is created but not persisted
- Iteration is stored in one place but not updated in another
- Worker metadata doesn't match ralph state
- State corruption during load/save cycles

This end-to-end test verifies the complete state flow from initial spawn
through multiple iterations of the ralph loop.
