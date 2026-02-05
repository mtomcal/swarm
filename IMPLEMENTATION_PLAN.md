# Implementation Plan: Heartbeat, Workflow, and CLI Help Improvements

**Created**: 2026-02-04
**Status**: Not Started
**Goal**: Add heartbeat system for rate limit recovery, workflow orchestration for multi-stage pipelines, and comprehensive CLI help across all commands

---

## Problem Statement

1. **Rate limits interrupt work**: When agents hit API rate limits during overnight/unattended work, they sit idle until manually restarted
2. **No multi-stage orchestration**: Complex tasks (plan → build → validate) require manual handoffs between stages
3. **Inconsistent CLI help**: Most commands have minimal help text; agents struggle to learn swarm from `-h` alone
4. **No scheduling**: Can't queue work to start when rate limits renew (e.g., at 2am)

---

## Solution Overview

| Feature | Description | Spec |
|---------|-------------|------|
| **Heartbeat** | Periodic nudges to workers on configurable interval with expiration | `specs/heartbeat.md` |
| **Workflow** | Multi-stage pipelines defined in YAML with scheduling and failure handling | `specs/workflow.md` |
| **CLI Help** | Comprehensive help text with examples for all commands | `specs/cli-help-standards.md` |

---

## Tasks

### Phase 1: CLI Help Improvements (Existing Commands)

Improve help text for all existing commands to match the quality of `ralph spawn --help`.

- [x] **1.1 Enhance `swarm --help` (root command)**
  - Add overview of swarm purpose
  - Add quick start example
  - Group commands by category

- [x] **1.2 Enhance `swarm spawn --help`**
  - Add description paragraph explaining worker types
  - Add 4+ examples (basic, worktree, env vars, ready-wait)
  - Add "Common Patterns" section
  - Document all flag defaults explicitly

- [x] **1.3 Enhance `swarm ls --help`**
  - Add description explaining output formats
  - Add examples for each format (table, json, names)
  - Add filter examples (--status, --tag)

- [x] **1.4 Enhance `swarm status --help`**
  - Add description of status output fields
  - Add examples showing different worker states

- [x] **1.5 Enhance `swarm send --help`**
  - Add description explaining tmux requirement
  - Add examples: single worker, broadcast, no-enter
  - Add "Intervention Patterns" section

- [x] **1.6 Enhance `swarm kill --help`**
  - Add description with safety warnings
  - Add examples: basic, with worktree, force-dirty
  - Add "Warnings" section about data loss
  - Add recovery commands for mistakes

- [x] **1.7 Enhance `swarm logs --help`**
  - Add description of log storage
  - Add examples: basic, follow, tail

- [x] **1.8 Enhance `swarm wait --help`**
  - Add description of exit code propagation
  - Add examples: basic, with timeout, exit code check

- [x] **1.9 Enhance `swarm clean --help`**
  - Add description of what gets cleaned
  - Add "Warnings" section
  - Add examples with filters

- [x] **1.10 Enhance `swarm respawn --help`**
  - Add description of what's preserved
  - Add examples showing different scenarios

- [x] **1.11 Enhance `swarm interrupt --help`**
  - Add description of Ctrl-C behavior
  - Add examples and use cases

- [x] **1.12 Enhance `swarm eof --help`**
  - Add description of Ctrl-D behavior
  - Add examples and use cases

- [x] **1.13 Enhance `swarm attach --help`**
  - Add description of tmux attachment
  - Add detach instructions
  - Add examples

- [x] **1.14 Enhance `swarm init --help`**
  - Add description of what gets initialized
  - Add examples

### Phase 2: Heartbeat Implementation

- [x] **2.1 Add HeartbeatState dataclass**
  - Fields: worker_name, interval_seconds, expire_at, message, created_at, last_beat_at, beat_count, status
  - Add to data-structures section of swarm.py

- [x] **2.2 Add heartbeat state persistence**
  - Storage: `~/.swarm/heartbeats/<worker>.json`
  - Load/save functions with file locking
  - Status enum: active, paused, expired, stopped

- [x] **2.3 Implement `swarm heartbeat start`**
  - Parse --interval (duration string)
  - Parse --expire (duration string, optional)
  - Parse --message (string, default "continue")
  - Parse --force (replace existing)
  - Validate worker exists and is tmux
  - Create heartbeat state
  - Start background monitor thread

- [x] **2.4 Implement heartbeat monitor thread**
  - Check interval using monotonic time
  - Send message via `tmux send-keys`
  - Update last_beat_at and beat_count
  - Check expiration
  - Detect worker death and auto-stop

- [x] **2.5 Implement `swarm heartbeat stop`**
  - Set status to stopped
  - Terminate monitor thread

- [x] **2.6 Implement `swarm heartbeat list`**
  - Table output: worker, interval, next beat, expires, status, beats
  - JSON output option

- [x] **2.7 Implement `swarm heartbeat status`**
  - Detailed output for single heartbeat
  - Next beat time calculation
  - JSON output format support

- [x] **2.8 Implement `swarm heartbeat pause/resume`**
  - Set status to paused/active

- [x] **2.9 Add --heartbeat flag to spawn**
  - Parse --heartbeat (duration)
  - Parse --heartbeat-expire (duration)
  - Parse --heartbeat-message (string)
  - Auto-start heartbeat after spawn

- [x] **2.10 Add heartbeat cleanup on kill**
  - When worker killed, stop associated heartbeat

- [x] **2.11 Add comprehensive heartbeat help text**
  - Follow cli-help-standards.md
  - Include duration format docs
  - Include rate limit recovery explanation

- [x] **2.12 Add heartbeat unit tests**
  - Test state persistence
  - Test interval calculation
  - Test expiration
  - Test worker death detection

### Phase 3: Workflow Implementation

- [x] **3.1 Add WorkflowState and StageState dataclasses**
  - WorkflowState: name, status, current_stage, stages dict, timestamps
  - StageState: status, worker_name, attempts, timestamps, exit_reason

- [x] **3.2 Implement YAML parser for workflow definitions**
  - Parse all fields from workflow.md spec
  - Validate required fields
  - Validate stage types
  - Validate on-failure values
  - Handle both prompt and prompt-file

- [x] **3.3 Add workflow state persistence**
  - Storage: `~/.swarm/workflows/<name>/state.json`
  - Copy workflow YAML to state directory
  - Store workflow hash for change detection

- [x] **3.4 Implement `swarm workflow validate`**
  - Parse and validate YAML
  - Check prompt files exist
  - Report all errors

- [x] **3.5 Implement `swarm workflow run`**
  - Parse --at (time)
  - Parse --in (duration)
  - Parse --name (override)
  - Parse --force (overwrite)
  - If scheduled, set status and return
  - Otherwise, start first stage

- [x] **3.6 Implement stage spawning logic**
  - For worker type: spawn with done-pattern detection
  - For ralph type: ralph spawn with configured options
  - Apply global settings (heartbeat, worktree, cwd, env)
  - Apply stage overrides

- [x] **3.7 Implement stage completion detection**
  - Monitor worker output for done-pattern
  - Handle timeout
  - Detect worker exit

- [x] **3.8 Implement stage transition logic**
  - Mark stage completed/failed/skipped
  - Handle on-failure: stop/retry/skip
  - Handle on-complete: next/stop
  - Start next stage or complete workflow

- [x] **3.9 Implement workflow monitor loop**
  - Background process managing workflow execution
  - Handle scheduled start times
  - Manage stage transitions
  - Handle heartbeats

- [x] **3.10 Implement `swarm workflow status`**
  - Show overall workflow status
  - Show each stage status
  - Show current stage details
  - Show timing information

- [x] **3.11 Implement `swarm workflow list`**
  - Table: name, status, current stage, started, source
  - JSON output option

- [x] **3.12 Implement `swarm workflow cancel`**
  - Kill current stage worker
  - Stop heartbeats
  - Set status to cancelled

- [x] **3.13 Implement `swarm workflow resume`**
  - Parse --from (stage name)
  - Restart from failed/specified stage
  - Reset attempt counts if needed

- [x] **3.14 Implement `swarm workflow logs`**
  - Parse --stage (filter)
  - Show aggregated logs
  - Per-stage log viewing

- [x] **3.15 Add comprehensive workflow help text**
  - Follow cli-help-standards.md
  - Include full YAML schema in `run --help`
  - Include examples for all common patterns

- [x] **3.16 Add workflow unit tests**
  - Test YAML parsing
  - Test validation
  - Test state persistence
  - Test stage transitions

- [x] **3.17 Add workflow integration tests**
  - Test simple 2-stage workflow
  - Test retry behavior
  - Test skip behavior
  - Test scheduling

### Phase 4: Integration and Polish

- [x] **4.1 Add heartbeat support to ralph spawn**
  - Same --heartbeat flags as regular spawn
  - Heartbeat during ralph loop

- [x] **4.2 Add repo-local workflow discovery**
  - Check `.swarm/workflows/` before global
  - Document in help text

- [x] **4.3 Resume heartbeats on swarm startup**
  - Check for active heartbeats
  - Restart monitor threads

- [x] **4.4 Resume workflows on swarm startup**
  - Check for running workflows
  - Provide `swarm workflow resume-all` command

- [x] **4.5 Update CLAUDE.md**
  - Add heartbeat section
  - Add workflow section
  - Update examples

- [x] **4.6 Final help text review**
  - Verify all commands meet cli-help-standards.md
  - Ensure consistency

### Phase 5: Verification

- [x] **5.1 Run all unit tests**
  ```bash
  python3 -m unittest discover -v
  ```

- [x] **5.2 Run integration tests**
  ```bash
  timeout 300 python3 -m unittest tests.test_integration_ralph -v
  ```

- [ ] **5.3 Manual verification - heartbeat**
  ```bash
  swarm spawn --name test --tmux -- bash -c 'while true; do sleep 10; done'
  swarm heartbeat start test --interval 30s --expire 5m --message "ping"
  swarm heartbeat status test
  swarm heartbeat list
  # Wait and observe beats
  swarm heartbeat stop test
  swarm kill test
  ```

- [ ] **5.4 Manual verification - workflow**
  ```bash
  cat > /tmp/test-workflow.yaml << 'EOF'
  name: test-workflow
  stages:
    - name: stage1
      type: worker
      prompt: |
        echo "Stage 1 complete"
        echo "/done"
      done-pattern: "/done"
      timeout: 1m
    - name: stage2
      type: worker
      prompt: |
        echo "Stage 2 complete"
        echo "/done"
      done-pattern: "/done"
      timeout: 1m
  EOF
  swarm workflow validate /tmp/test-workflow.yaml
  swarm workflow run /tmp/test-workflow.yaml
  swarm workflow status test-workflow
  swarm workflow list
  ```

- [ ] **5.5 Manual verification - help text**
  ```bash
  swarm --help
  swarm spawn --help
  swarm kill --help
  swarm heartbeat --help
  swarm heartbeat start --help
  swarm workflow --help
  swarm workflow run --help
  ```

### Phase 6: Coverage and Test Quality

Current coverage: 94% (181 lines missing). Target: 90%+ ✓

- [x] **6.1 Add tests for main() argument parsing**
  - The `main()` function (lines 4249-4905) has no direct test coverage
  - Add tests that invoke argument parsing for all commands
  - Test help text generation
  - Test argument validation and error messages
  - Use `unittest.mock` to avoid actual command execution

- [x] **6.2 Add tests for uncovered error paths**
  - Review lines 8229-8523 (workflow monitor, stage transitions)
  - Add tests for edge cases: worker death during stage, retry exhaustion
  - Add tests for workflow cancellation mid-stage
  - Test heartbeat expiration scenarios

- [x] **6.3 Add tests for uncovered utility functions**
  - Lines 9031-9187: review and add tests for any untested helpers
  - Lines 9241-9282: add tests for edge cases
  - Ensure all public functions have test coverage

- [x] **6.4 Audit tests for low-quality patterns**
  - Search for tests that only check "no exception thrown"
  - Search for tests with no assertions or weak assertions
  - Search for tests that mock too much (testing mocks, not code)
  - Search for flaky tests (timing-dependent, order-dependent)
  - Search for tests with hardcoded paths or environment assumptions
  - Document findings in `TEST_AUDIT.md`

- [x] **6.5 Fix or rewrite low-quality tests**
  - Implemented SWARM_DIR environment variable support for test isolation
  - Strengthened 16 weak `assert_called()` assertions to use `assert_called_once()` or proper call count checks with argument verification
  - All affected tests in test_cmd_workflow.py, test_cmd_ralph.py, and test_cmd_respawn.py now pass

- [x] **6.6 Search for risky test patterns**
  - Tests that modify global state without cleanup
  - Tests that leave temp files/directories behind
  - Tests that depend on execution order
  - Tests that could interfere with real swarm state (~/.swarm/)
  - Tests with subprocess calls that could hang indefinitely
  - Add `timeout` decorators to any test that could hang
  - **DONE**: Added timeout=5 to 15 proc.communicate() calls in test_cmd_workflow.py
  - **DONE**: Added timeout=5 to 7 proc.communicate() calls in tests/test_integration_workflow.py
  - **DONE**: Added timeout=30 to 14 git subprocess.run() calls in test_worktree_protection.py
  - **DONE**: Added timeout=30 to 2 proc.wait() calls in test_core_functions.py
  - **DONE**: Updated TEST_AUDIT.md with findings for sections 10-14

- [x] **6.7 Verify coverage reaches 90%+**
  ```bash
  python3 -m coverage run --source=swarm -m unittest discover -b
  python3 -m coverage report --fail-under=90
  ```
  - **DONE**: Added 41 tests in TestMainFunctionDispatch class in test_cmd_main.py
  - **DONE**: Coverage increased from 89% to 94%

### Phase 7: Memory Exhaustion Investigation

The test suite has caused memory exhaustion events that crash the system. This phase investigates and fixes the root causes.

- [x] **7.1 Profile test suite memory usage**
  - Run tests with memory profiling (`memory_profiler` or `tracemalloc`)
  - Identify which test files/classes consume the most memory
  - Check for memory growth patterns during test runs
  - Document baseline memory usage per test file
  - **DONE**: Created `profile_test_memory.py` script, profiled all 31 test files
  - **DONE**: Added Section 15 to TEST_AUDIT.md with detailed findings
  - **FINDING**: Memory usage is healthy (45 MB peak), no leaks detected

- [x] **7.2 Identify memory leak patterns in tests**
  - Search for tests that create large data structures without cleanup
  - Check for subprocess/Popen objects not being properly terminated
  - Look for tmux sessions or processes left running between tests
  - Check for file handles not being closed
  - Review mock objects that might retain references
  - **DONE**: Comprehensive analysis found no memory leak patterns
  - **FINDING**: All subprocess/Popen properly terminated with try/finally or try/except TimeoutExpired
  - **FINDING**: All file handles use context managers (with open)
  - **FINDING**: TmuxIsolatedTestCase properly cleans up tmux sessions
  - **FINDING**: Mock objects use small, bounded side_effect lists
  - **FINDING**: No global data structure accumulation
  - Results documented in TEST_AUDIT.md Section 16

- [ ] **7.3 Audit subprocess and process management**
  - Review all `subprocess.Popen` usage in tests
  - Ensure all spawned processes are terminated in tearDown
  - Check for zombie processes accumulating
  - Verify `proc.communicate()` is called to collect output and prevent pipe buffer issues
  - Look for infinite loops or blocking reads on subprocess pipes

- [ ] **7.4 Review tmux session cleanup**
  - Check if tmux sessions are properly killed after tests
  - Look for orphaned tmux sessions from failed tests
  - Verify `TmuxIsolatedTestCase` cleanup is robust
  - Add tmux session listing before/after test runs to detect leaks

- [ ] **7.5 Check for large string/buffer accumulation**
  - Review tests that capture stdout/stderr (could accumulate large outputs)
  - Check for tests reading large files into memory
  - Look for log file contents being loaded entirely into memory
  - Review JSON parsing of potentially large state files

- [ ] **7.6 Add memory safeguards to test infrastructure**
  - Add memory limit warnings to test runner
  - Implement test isolation to prevent cross-test memory accumulation
  - Add periodic garbage collection between test classes
  - Consider running memory-heavy tests in separate processes

- [ ] **7.7 Fix identified memory issues**
  - Apply fixes for all identified memory leaks
  - Add cleanup code where missing
  - Optimize memory-heavy test patterns
  - Verify fixes with memory profiling

---

## Files to Create

| File | Description |
|------|-------------|
| `specs/heartbeat.md` | Heartbeat behavioral spec (DONE) |
| `specs/workflow.md` | Workflow behavioral spec (DONE) |
| `specs/cli-help-standards.md` | CLI help standards spec (DONE) |
| `test_cmd_heartbeat.py` | Heartbeat unit tests |
| `test_cmd_workflow.py` | Workflow unit tests |
| `tests/test_integration_workflow.py` | Workflow integration tests |

## Files to Modify

| File | Changes |
|------|---------|
| `swarm.py` | Add heartbeat, workflow commands; enhance all help text |
| `CLAUDE.md` | Add heartbeat, workflow documentation |
| `specs/README.md` | Add new specs to TOC (DONE) |

---

## Design Decisions

1. **Heartbeat as blind nudge**: Simpler than rate limit detection, handles many blocking scenarios
2. **Expiration for safety**: Prevents infinite nudging of abandoned workers
3. **YAML workflows**: Familiar format, supports inline prompts to reduce file litter
4. **Help text as documentation**: Agents primarily learn from `-h`, so it must be comprehensive
5. **Linear stages first**: DAG support deferred to avoid complexity
6. **Stage workers named `<workflow>-<stage>`**: Prevents naming conflicts

---

## Rollback Plan

All features are additive:
1. Heartbeat commands are new - can be removed without breaking existing functionality
2. Workflow commands are new - can be removed without breaking existing functionality
3. Help text improvements are backwards compatible

---

## Estimated Scope

| Phase | Tasks | Complexity |
|-------|-------|------------|
| Phase 1: CLI Help | 14 tasks | Low (text changes only) |
| Phase 2: Heartbeat | 12 tasks | Medium (new subsystem) |
| Phase 3: Workflow | 17 tasks | High (orchestration logic) |
| Phase 4: Integration | 6 tasks | Medium (cross-cutting) |
| Phase 5: Verification | 5 tasks | Low (testing) |
| Phase 6: Coverage & Test Quality | 7 tasks | Medium (test improvements) |
| Phase 7: Memory Investigation | 7 tasks | Medium (debugging/profiling) |

Total: 68 tasks
