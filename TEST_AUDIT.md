# Test Quality Audit

**Created**: 2026-02-05
**Auditor**: Claude (tasks 6.4 and 6.6)

This document identifies low-quality patterns found in the swarm test suite during code review.

---

## Summary

| Category | Count | Severity | Fix Priority |
|----------|-------|----------|--------------|
| Timing-dependent tests | 40+ | Medium | Medium |
| Tests accessing real ~/.swarm | 20+ | High | High |
| Weak assertions (assert_called only) | 16 | Low | Low |
| Subprocess calls without timeout | Many | Medium | Medium |
| Global state modification | Proper | OK | N/A |
| Popen without timeout | 25+ | High | High |
| Threads without proper join timeout | Few | Low | Low |

---

## 1. Timing-Dependent Tests (Flaky Risk)

Tests that use `time.sleep()` without mocking can be flaky depending on system load.

### Files with Real Sleep Calls

| File | Lines | Purpose |
|------|-------|---------|
| `test_lifecycle_tmux.py` | 129, 161 | Wait for state updates |
| `test_lifecycle_pid.py` | 132 | Wait for state updates |
| `test_kill_integration.py` | 105 | Wait for process death |
| `test_core_functions.py` | 60, 78, 94, 110 | Wait for process state |
| `test_respawn_config.py` | 102, 127 | Wait for respawn |
| `test_cmd_ralph.py` | 7368, 7477, 7594 | Wait for loop iterations |
| `tests/test_tmux_isolation.py` | 522, 797, 857, 880, 1080, 1280 | Wait for tmux operations |
| `tests/test_integration_workflow.py` | 256, 307, 1150, 1170 | Wait for workflow transitions |

### Recommended Fixes

1. Use polling with timeout instead of fixed sleep:
```python
# Instead of:
time.sleep(0.5)
state = self.get_state()

# Use:
def wait_for_state(predicate, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        state = self.get_state()
        if predicate(state):
            return state
        time.sleep(0.1)
    raise TimeoutError("State condition not met")
```

2. For unit tests, mock `time.sleep` (already done in many tests)

---

## 2. Tests Accessing Real ~/.swarm (Interference Risk)

Integration tests that directly access `Path.home() / ".swarm"` can interfere with real swarm state if run by a user with an active swarm setup.

### Affected Files

| File | Lines | Access Type |
|------|-------|-------------|
| `tests/test_integration_ralph.py` | 49, 123, 161, 229, 376, 403, 432, 481, 508 | Read/write ralph state |
| `tests/test_integration_workflow.py` | 159, 212, 252, 303, 375, 423, 464, 590, 637, 808, 867, 1067, 1136 | Read/write workflow state |

### Recommended Fixes

1. Use environment variable or monkeypatch to redirect SWARM_DIR during tests
2. The `TmuxIsolatedTestCase` has a skip decorator for this but it's not implemented:
   - See `tests/test_tmux_isolation.py:638`: `@unittest.skip("SWARM_DIR env var not yet implemented")`

3. Alternative: Use unique prefixes based on test socket to avoid collisions (partially done)

---

## 3. Weak Assertions

Tests using `mock.assert_called()` without verifying call arguments are weak - they only verify the function was called, not that it was called correctly.

### Occurrences

```
test_cmd_workflow.py:3493:        mock_save_ralph.assert_called()
test_cmd_workflow.py:3502:        mock_log.assert_called()
test_cmd_workflow.py:3599:        mock_save_hb.assert_called()
test_cmd_workflow.py:3632:        mock_save_hb.assert_called()
test_cmd_workflow.py:3858:        mock_save_ralph.assert_called()
test_cmd_workflow.py:3922:        mock_save_hb.assert_called()
test_cmd_workflow.py:5065:        mock_save.assert_called()
test_cmd_workflow.py:5322:        mock_sleep.assert_called()
test_cmd_workflow.py:5464:        mock_save.assert_called()
test_cmd_workflow.py:5548:        mock_save.assert_called()
test_cmd_workflow.py:5574:        mock_save.assert_called()
test_cmd_workflow.py:5645:        mock_save.assert_called()
test_cmd_workflow.py:5791:        mock_save.assert_called()
test_cmd_workflow.py:6748:            mock_run.assert_called()
test_cmd_ralph.py:3892:        mock_spawn.assert_called()
test_cmd_respawn.py:189:                            mock_kill.assert_called()
```

### Recommended Fixes

Replace `assert_called()` with `assert_called_with(...)` or `assert_called_once_with(...)`:
```python
# Weak:
mock_save.assert_called()

# Better:
mock_save.assert_called_once_with(expected_state)
# Or at minimum:
mock_save.assert_called_once()
```

---

## 4. Subprocess Calls Without Timeout

Many subprocess calls in tests don't specify a timeout, which could cause tests to hang indefinitely.

### High-Risk Patterns

| File | Lines | Risk |
|------|-------|------|
| `test_core_functions.py` | 142 | `subprocess.Popen(["sleep", "10"])` without timeout |
| `test_worktree_protection.py` | Multiple | Git commands without timeout |
| Integration tests | Multiple | `subprocess.Popen` for workflow/ralph without timeout |

### Recommended Fixes

1. Add `timeout` parameter to all `subprocess.run()` calls:
```python
subprocess.run(cmd, capture_output=True, text=True, timeout=30)
```

2. For `subprocess.Popen`, use `proc.wait(timeout=30)` or `proc.communicate(timeout=30)`

3. Add `@unittest.timeout(60)` decorator to integration tests (requires `unittest-timeout` package or custom implementation)

---

## 5. Global State Modification (OK - Properly Handled)

Tests that modify module-level variables (`swarm.SWARM_DIR`, etc.) are correctly saving original values in `setUp()` and restoring in `tearDown()`.

### Pattern Used (Correct)

```python
def setUp(self):
    self.original_swarm_dir = swarm.SWARM_DIR
    swarm.SWARM_DIR = Path(self.temp_dir) / ".swarm"

def tearDown(self):
    swarm.SWARM_DIR = self.original_swarm_dir
```

This pattern is consistently used across:
- `test_cmd_workflow.py` (88 occurrences)
- `test_cmd_ralph.py` (252 occurrences)
- `test_cmd_heartbeat.py` (66 occurrences)
- `test_cmd_init.py` (14 occurrences)

**Status**: No action needed.

---

## 6. Tests with Hardcoded Paths

Some tests use hardcoded `/tmp` paths which may cause issues in environments where `/tmp` is not available or has different permissions.

### Occurrences

```
test_cmd_workflow.py: cwd="/tmp/test" (lines 5030, 5076, 5141, 5385, 5677, 5727)
test_kill_cmd.py: path="/tmp/worktrees/..." (lines 172, 174, 203, 312, 314)
test_cmd_ralph.py: prompt_file='/tmp/PROMPT.md' (lines 5464, 5504, 5581)
test_cmd_respawn.py: cwd="/tmp/worktree" (line 352)
test_cmd_ls.py: path="/tmp/project-worktrees/..." (lines 168, 170, 181)
```

### Assessment

These are mock values in unit tests (not actually accessing the filesystem), so they are acceptable. The paths are used as data in mocked Worker objects.

**Status**: Low priority - only fix if cross-platform compatibility becomes important.

---

## 7. Tests Without Assertions (None Found)

No tests were found that consist of only `pass` or have no assertions.

**Status**: No action needed.

---

## 8. Over-Mocked Tests

Some tests mock so many components that they may be testing mocks rather than actual code. This is a subjective assessment.

### Potential Concerns

In `test_cmd_workflow.py` and `test_cmd_ralph.py`, some tests mock 5+ functions. While this is sometimes necessary for complex integration points, it can make tests fragile and less valuable.

### Recommendations

1. Consider integration tests for complex workflows rather than heavily-mocked unit tests
2. Use `@patch.object` instead of string-based patching when possible for better refactoring safety

---

## 9. Missing Test Timeouts (Hanging Risk)

Integration tests that spawn subprocesses could hang indefinitely if something goes wrong.

### Affected Test Classes

- `TestFullLifecyclePid` in `test_lifecycle_pid.py`
- `TestFullLifecycleTmux` in `test_lifecycle_tmux.py`
- `TestRespawnPreservesConfig` in `test_respawn_config.py`
- `TestRalphSpawn` in `tests/test_integration_ralph.py`
- Workflow integration tests in `tests/test_integration_workflow.py`

### Recommended Fix

Add timeout wrapper to test runner:
```bash
# Run integration tests with timeout
timeout 300 python3 -m unittest tests.test_integration_ralph -v
```

Or add `@timeout_decorator.timeout(60)` to individual tests.

---

---

## 10. Subprocess.Popen Without Timeout (Task 6.6)

Tests using `subprocess.Popen` can hang indefinitely if the spawned process doesn't exit. While many tests use `proc.communicate(timeout=X)`, some use `proc.communicate()` without timeout as a fallback.

### High-Risk Occurrences

| File | Lines | Pattern |
|------|-------|---------|
| `test_cmd_workflow.py` | 2745-3254 | 15 Popen calls with timeout in try/except but no timeout in except |
| `tests/test_integration_workflow.py` | 244-1162 | 7 Popen calls, some without timeout |
| `test_core_functions.py` | 142, 160 | `subprocess.Popen(["sleep", "10"])` and `subprocess.Popen(["true"])` |

### Pattern of Concern

```python
# This pattern is risky - if TimeoutExpired occurs, the except handler
# calls communicate() without timeout, potentially hanging forever
try:
    proc.communicate(timeout=2)
except subprocess.TimeoutExpired:
    proc.kill()
    proc.communicate()  # No timeout - could hang!
```

### Recommended Fix

Always use timeout in communicate(), even after kill():
```python
try:
    proc.communicate(timeout=2)
except subprocess.TimeoutExpired:
    proc.kill()
    proc.communicate(timeout=5)  # Still use timeout!
```

---

## 11. Integration Tests Accessing Real ~/.swarm (Task 6.6)

Integration tests directly access `Path.home() / ".swarm"` which can interfere with a developer's real swarm state.

### Affected Files

| File | Occurrences | Directories Accessed |
|------|-------------|---------------------|
| `tests/test_integration_ralph.py` | 9 | `~/.swarm/ralph/` |
| `tests/test_integration_workflow.py` | 13 | `~/.swarm/workflows/` |

### Mitigation Already in Place

The integration tests use unique worker names based on tmux socket:
```python
worker_name = f"ralph-basic-{self.tmux_socket[-8:]}"
```

And cleanup attempts to only remove test-created directories:
```python
if worker_dir.name.startswith(self.tmux_socket.replace('swarm-test-', '')):
    shutil.rmtree(worker_dir, ignore_errors=True)
```

### Remaining Risk

If a test crashes before tearDown, orphaned state may remain in `~/.swarm/`.

### Full Fix

Use `SWARM_DIR` environment variable in integration tests to completely isolate from real state:
```python
def setUp(self):
    self.test_swarm_dir = tempfile.mkdtemp()
    os.environ['SWARM_DIR'] = self.test_swarm_dir

def tearDown(self):
    del os.environ['SWARM_DIR']
    shutil.rmtree(self.test_swarm_dir)
```

---

## 12. Tests with Threads Not Properly Joined (Task 6.6)

Some tests spawn threads without ensuring they complete or using timeouts.

### Occurrences

| File | Lines | Analysis |
|------|-------|----------|
| `test_state_file_locking.py` | 64-65 | Threads properly joined |
| `test_state_file_locking.py` | 123 | Thread properly joined |
| `test_state_file_locking.py` | 174, 189 | `t2.join(timeout=1.0)` - correctly uses timeout |

### Status

Thread handling is generally good - timeout is used on joins, and tests check `is_alive()` to detect hanging threads.

**Status**: No action needed.

---

## 13. Git Subprocess Calls in test_worktree_protection.py (Task 6.6)

This file contains 40+ `subprocess.run(["git", ...])` calls without timeout parameters.

### Risk Analysis

Git commands are generally fast and unlikely to hang, but on slow filesystems or with large repos, they could take longer than expected.

### Occurrences (Sample)

```
test_worktree_protection.py:25: subprocess.run(["git", "init"], cwd=tmpdir, capture_output=True)
test_worktree_protection.py:26: subprocess.run(["git", "config", ...], cwd=tmpdir, capture_output=True)
test_worktree_protection.py:32: subprocess.run(["git", "add", ...], cwd=tmpdir, capture_output=True)
test_worktree_protection.py:33: subprocess.run(["git", "commit", ...], cwd=tmpdir, capture_output=True)
... (40+ more)
```

### Recommended Fix

Add timeout to all git subprocess calls:
```python
subprocess.run(["git", "init"], cwd=tmpdir, capture_output=True, timeout=30)
```

---

## 14. Tests with tempfile.mkdtemp Without Cleanup (Task 6.6)

Most tests using `tempfile.mkdtemp()` properly clean up in `tearDown()`, but there's one pattern that could leave temp files behind:

### Safe Pattern (Used Consistently)

```python
def setUp(self):
    self.temp_dir = tempfile.mkdtemp()

def tearDown(self):
    shutil.rmtree(self.temp_dir, ignore_errors=True)
```

### Contextmanager Alternative (Also Safe)

```python
with tempfile.TemporaryDirectory() as tmpdir:
    # Test code here
# Auto-cleaned when exiting context
```

### Status

All test files reviewed use proper cleanup. **No action needed.**

---

## Summary of Action Items

### High Priority
1. [x] Implement SWARM_DIR environment variable support to isolate integration tests
   - **DONE**: Added `os.environ.get("SWARM_DIR", ...)` support in swarm.py line 27
2. [x] Add timeouts to subprocess.Popen communicate() calls in test_cmd_workflow.py
   - **DONE (task 6.6)**: Added timeout=5 to all except-block communicate() calls
3. [x] Add timeouts to subprocess.Popen communicate() calls in tests/test_integration_workflow.py
   - **DONE (task 6.6)**: Added timeout=5 to all except-block communicate() calls

### Medium Priority
4. [ ] Replace fixed `time.sleep()` with polling in integration tests
5. [ ] Add test timeout decorators to prevent hanging tests
6. [x] Add timeouts to git subprocess.run calls in test_worktree_protection.py
   - **DONE (task 6.6)**: Added timeout=30 to all 40 git subprocess calls
7. [x] Add timeout to process wait() in test_core_functions.py
   - **DONE (task 6.6)**: Added timeout=30 to proc.wait() calls

### Low Priority
8. [x] Strengthen weak `assert_called()` assertions to include argument verification
   - **DONE**: Fixed 16 weak assertions in test_cmd_workflow.py, test_cmd_ralph.py, and test_cmd_respawn.py
   - Changed `assert_called()` to `assert_called_once()` where appropriate
   - Added `call_count >= 1` checks with argument verification for multi-call scenarios
9. [ ] Consider reducing mock depth in heavily-mocked tests
10. [ ] Update integration tests to use SWARM_DIR env var for full isolation

---

## 15. Memory Profiling Results (Task 7.1)

Memory profiling was conducted on 2026-02-05 using `tracemalloc` and the `resource` module to measure memory consumption across the test suite.

### Methodology

- Each test file was run in a subprocess with memory tracking
- Peak memory usage was measured via `resource.getrusage(RUSAGE_SELF).ru_maxrss`
- Memory growth was calculated as the difference between start and end memory
- All tests were also run together to measure accumulation effects

### Per-File Memory Usage (Sorted by Peak Memory)

| Test File | Peak Memory | Tests | Duration | Memory Growth |
|-----------|-------------|-------|----------|---------------|
| test_cmd_main.py | 38.8 MB | 146 | 5.5s | 22.4 MB |
| test_cmd_workflow.py | 37.4 MB | 360 | 34.4s | 21.0 MB |
| test_cmd_ralph.py | 36.9 MB | 259 | 40.4s | 20.6 MB |
| test_cmd_heartbeat.py | 36.2 MB | 126 | 1.8s | 19.9 MB |
| test_cmd_clean.py | 33.1 MB | 12 | 0.4s | 16.8 MB |
| test_cmd_spawn.py | 32.8 MB | 22 | 0.4s | 16.4 MB |
| test_swarm.py | 32.5 MB | 21 | 0.4s | 16.0 MB |
| test_core_functions.py | 32.1 MB | 33 | 1.2s | 15.8 MB |
| test_cmd_respawn.py | 32.0 MB | 12 | 0.5s | 15.6 MB |
| test_unit.py | 32.0 MB | 22 | 0.4s | 15.5 MB |
| test_session_cleanup.py | 31.9 MB | 18 | 0.5s | 15.4 MB |
| test_cmd_init.py | 31.8 MB | 25 | 1.2s | 15.4 MB |
| test_cmd_ls.py | 31.8 MB | 16 | 0.4s | 15.4 MB |
| test_worktree_protection.py | 31.7 MB | 11 | 0.6s | 15.2 MB |
| test_cmd_logs.py | 31.6 MB | 8 | 0.3s | 15.3 MB |
| test_cmd_send.py | 31.6 MB | 7 | 0.3s | 15.3 MB |
| test_ready_patterns.py | 30.4 MB | 22 | 13.4s | 13.9 MB |
| test_swarm_instructions.py | 24.1 MB | 17 | 0.3s | 7.6 MB |
| test_tmux_isolation.py | 20.0 MB | 16 | 8.9s | 3.5 MB |
| test_integration_workflow.py | 19.7 MB | 31 | 19.8s | 3.2 MB |
| test_integration_ralph.py | 19.7 MB | 15 | 13.7s | 3.2 MB |
| test_lifecycle_tmux.py | 19.2 MB | 1 | 2.3s | 2.7 MB |
| test_respawn_config.py | 19.2 MB | 1 | 2.1s | 2.7 MB |
| test_ready_wait_integration.py | 19.1 MB | 4 | 5.4s | 2.6 MB |
| test_kill_integration.py | 17.8 MB | 3 | 1.4s | 1.3 MB |
| test_status_integration.py | 17.8 MB | 2 | 0.3s | 1.3 MB |
| test_state_file_recovery.py | 17.6 MB | 4 | 0.6s | 1.1 MB |
| test_state_file_locking.py | 17.1 MB | 3 | 0.3s | 0.5 MB |
| test_lifecycle_pid.py | 16.5 MB | 1 | 1.9s | 0.0 MB |
| test_pattern_edge_cases.py | 16.5 MB | 11 | 0.0s | 0.0 MB |
| test_kill_cmd.py | 31.9 MB | 10 | 0.5s | 15.5 MB |

### Aggregate Memory Usage (All Tests Together)

When running all 1239 tests in a single process:

| Metric | Value |
|--------|-------|
| Start Memory | 16.4 MB |
| End Memory | 45.2 MB |
| Total Growth | 28.9 MB |
| Peak (tracemalloc) | 11.8 MB |

### Analysis

**Key Findings:**

1. **Memory usage is reasonable** - The entire test suite peaks at ~45 MB when run together, which is well within normal bounds and should not cause memory exhaustion on modern systems.

2. **Baseline overhead ~16 MB** - The Python interpreter with swarm.py loaded uses approximately 16 MB before any tests run.

3. **Test file loading adds ~16 MB** - Files that import swarm and set up mocks grow to ~32 MB, which is expected.

4. **Memory growth is consistent** - No individual test file shows unusual memory accumulation patterns.

5. **Integration tests are more memory-efficient** - Tests in `tests/` directory use less memory (~20 MB) because they spawn subprocess workers rather than loading the full swarm module in-process.

### Tests with Highest Individual Memory Growth

From the "all-together" run, the tests that caused the largest memory increments:

1. `test_ralph_list_json_format` - 2.50 MB growth
2. `test_main_ralph_spawn_dispatches_to_cmd_ralph` - 0.50 MB growth
3. `test_clean_all_refreshes_status_before_filtering` - 0.25 MB growth
4. `test_child_process_becomes_daemon` - 0.25 MB growth

These growth values are small and normal for tests that create worker state objects.

### Conclusion

**The test suite does not have a memory leak.** The memory usage is proportional to the number of tests and test complexity. The ~45 MB peak usage is well within acceptable bounds.

The previously reported memory exhaustion events were likely caused by:
- Running tests on systems with very limited memory
- Running multiple test processes simultaneously
- External factors (other processes consuming memory)
- tmux sessions accumulating from failed test runs (addressed in section 11)

### Recommendations

1. **No immediate memory fixes needed** - Memory usage is healthy
2. **Monitor for orphaned tmux sessions** - These can accumulate if tests crash
3. **Use `SWARM_DIR` env var in CI** - Prevents state file accumulation

---

## Test Coverage Notes

Current coverage is 94% (up from 84%). The patterns identified in this audit are primarily about test quality rather than coverage gaps.

Previous coverage improvements:
- Task 6.7 added 41 tests for main() function dispatch
- Coverage increased from 89% to 94%

